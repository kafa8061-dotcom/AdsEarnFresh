import base64
import time
from urllib.parse import quote
from uuid import uuid4

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException
from sqlalchemy.orm import sessionmaker

from app import admob
from app.models import User, Wallet, WalletTransaction


def test_admin_is_required(client, auth):
    assert client.put("/v1/admin/withdrawals/nope", headers=auth, json={"status": "PAID"}).status_code == 403


def test_paid_requires_reference_and_rejection_refunds(client, session, db_engine):
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    client.put("/v1/profile", headers=headers, json={
        "full_name": "Admin", "email": "admin@example.com", "country_iso": "US", "phone": "2025550125",
    })
    client.put("/v1/payment-method", headers=headers, json={"country_iso": "US", "phone": "2025550125"})
    factory = sessionmaker(bind=db_engine, expire_on_commit=False)
    with factory() as db:
        user = db.query(User).filter_by(public_id=session["user_id"]).one()
        user.role = "admin"
        wallet = db.get(Wallet, user.id)
        wallet.available_balance = 15
        db.add(WalletTransaction(
            user_id=user.id, transaction_type="business_credit", amount=15, status="COMPLETED",
        ))
        db.commit()
    request = {"amount": "10.00", "request_key": str(uuid4())}
    withdrawal = client.post("/v1/withdrawals", headers=headers, json=request)
    assert withdrawal.status_code == 201
    wid = withdrawal.json()["withdrawal_id"]
    duplicate = client.post("/v1/withdrawals", headers=headers, json=request)
    assert duplicate.status_code == 201
    assert duplicate.json()["withdrawal_id"] == wid
    client.put("/v1/payment-method", headers=headers, json={"country_iso": "US", "phone": "4155552671"})
    assert client.put(f"/v1/admin/withdrawals/{wid}", headers=headers, json={"status": "PAID"}).status_code == 409
    rejected = client.put(f"/v1/admin/withdrawals/{wid}", headers=headers, json={"status": "REJECTED"})
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"
    wallet = client.get("/v1/wallet", headers=headers).json()
    assert str(wallet["available_balance"]) == "15.00"
    destination = client.get(f"/v1/admin/withdrawals/{wid}/payment-destination", headers=headers)
    assert destination.json()["waafi_phone"] == "+12025550125"
    second_withdrawal = client.post("/v1/withdrawals", headers=headers, json={
        "amount": "10.00", "request_key": str(uuid4()),
    }).json()
    second_id = second_withdrawal["withdrawal_id"]
    assert client.put(f"/v1/admin/withdrawals/{second_id}", headers=headers, json={"status": "APPROVED"}).status_code == 200
    assert client.put(f"/v1/admin/withdrawals/{second_id}", headers=headers, json={"status": "PAID"}).status_code == 422
    paid = client.put(f"/v1/admin/withdrawals/{second_id}", headers=headers, json={
        "status": "PAID", "payment_reference": "actual-transfer-reference",
    })
    assert paid.status_code == 200
    assert paid.json()["payment_reference"] == "actual-transfer-reference"


def _signed_callback(private_key, reservation_id, user_id, transaction_id):
    timestamp = str(int(time.time() * 1000))
    parameters = {
        "ad_network": "5450213213286189855",
        "ad_unit": "2667340525",
        "custom_data": reservation_id,
        "reward_amount": "1",
        "reward_item": "reward",
        "timestamp": timestamp,
        "transaction_id": transaction_id,
        "user_id": user_id,
    }
    signed = "&".join(f"{key}={value}" for key, value in sorted(parameters.items()))
    signature = private_key.sign(signed.encode("ascii"), ec.ECDSA(hashes.SHA256()))
    encoded = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    return f"{signed}&signature={quote(encoded)}&key_id=42"


def test_google_signed_ssv_records_activity_without_creating_money(client, auth, monkeypatch):
    private_key = ec.generate_private_key(ec.SECP256R1())
    pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    monkeypatch.setattr(admob, "_fetch_google_keys", lambda db, force=False: {42: pem})
    reservation = client.post("/v1/ads/reservations", headers=auth).json()
    query = _signed_callback(private_key, reservation["reservation_id"], reservation["user_id"], "ssv-transaction-1")
    result = client.get("/v1/admob/ssv?" + query)
    assert result.status_code == 200
    assert result.json() == {"status": "verified"}
    assert client.get("/v1/dashboard", headers=auth).json()["daily_ads"] == 1
    assert client.get("/v1/wallet", headers=auth).json()["available_balance"] == "0.00"
    assert client.get("/v1/admob/ssv?" + query).status_code == 200


def test_daily_ten_completion_quota_survives_valid_signed_callbacks(client, auth, monkeypatch):
    private_key = ec.generate_private_key(ec.SECP256R1())
    pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    monkeypatch.setattr(admob, "_fetch_google_keys", lambda db, force=False: {42: pem})
    for index in range(10):
        reservation = client.post("/v1/ads/reservations", headers=auth)
        assert reservation.status_code == 201
        event = reservation.json()
        query = _signed_callback(private_key, event["reservation_id"], event["user_id"], f"quota-event-{index}")
        assert client.get("/v1/admob/ssv?" + query).status_code == 200
    assert client.get("/v1/dashboard", headers=auth).json()["daily_ads"] == 10
    limited = client.post("/v1/ads/reservations", headers=auth)
    assert limited.status_code == 429
    assert limited.json()["detail"] == "You've reached today's limit. Come back tomorrow."


def test_ssv_key_unavailability_does_not_accept_forged_callback(client, auth, monkeypatch):
    monkeypatch.setattr(
        admob, "_fetch_google_keys",
        lambda db, force=False: (_ for _ in ()).throw(HTTPException(status_code=503, detail="Unavailable")),
    )
    reservation = client.post("/v1/ads/reservations", headers=auth).json()
    invalid = (
        f"ad_network=5450213213286189855&ad_unit=2667340525"
        f"&custom_data={reservation['reservation_id']}&reward_amount=1&reward_item=reward"
        f"&timestamp={int(time.time() * 1000)}&transaction_id=fake&user_id={reservation['user_id']}"
        "&signature=ZmFrZQ&key_id=42"
    )
    assert client.get("/v1/admob/ssv?" + invalid).status_code == 503


def test_ssv_rejects_tampered_user_and_duplicate_query_parameters(client, auth, monkeypatch):
    private_key = ec.generate_private_key(ec.SECP256R1())
    pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    monkeypatch.setattr(admob, "_fetch_google_keys", lambda db, force=False: {42: pem})
    reservation = client.post("/v1/ads/reservations", headers=auth).json()
    signed = _signed_callback(private_key, reservation["reservation_id"], reservation["user_id"], "tamper-check")
    tampered = signed + "&user_id=USR-ATTACKER"
    assert client.get("/v1/admob/ssv?" + tampered).status_code == 400
    duplicate = signed.replace("&ad_unit=", "&user_id=USR-ATTACKER&ad_unit=", 1)
    assert client.get("/v1/admob/ssv?" + duplicate).status_code == 400
