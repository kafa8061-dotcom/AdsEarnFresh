from decimal import Decimal
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from sqlalchemy.orm import Session

from app.models import AdEvent, User
from app import main as api_main
from conftest import start_session

def test_daily_limit_is_enforced_from_server_records(client, auth, db_engine):
    user_id = client.get("/v1/dashboard", headers=auth).json()["user_id"]
    with Session(db_engine) as db:
        user = db.query(User).filter_by(public_id=user_id).one()
        for index in range(10):
            db.add(AdEvent(
                user_id=user.id,
                application_id="ca-app-pub-4973946737213196~3854510671",
                ad_unit_id="2667340525",
                calendar_day=datetime.now(timezone.utc).date(),
                status="completed",
                transaction_id=f"verified-test-event-{index}",
            ))
        db.commit()
    limited = client.post("/v1/ads/reservations", headers=auth)
    assert limited.status_code == 429
    assert limited.json()["detail"] == "You've reached today's limit. Come back tomorrow."


def test_parallel_ad_reservation_reuses_the_active_slot(client, auth):
    first = client.post("/v1/ads/reservations", headers=auth).json()
    second = client.post("/v1/ads/reservations", headers=auth).json()
    assert first["reservation_id"] == second["reservation_id"]


def test_cancelled_ad_reservation_releases_capacity(client, auth):
    reservation = client.post("/v1/ads/reservations", headers=auth).json()
    result = client.delete(f"/v1/ads/reservations/{reservation['reservation_id']}", headers=auth)
    assert result.status_code == 204
    assert client.post("/v1/ads/reservations", headers=auth).status_code == 201


def test_daily_quota_rolls_over_on_server_utc_date(client, auth, db_engine, monkeypatch):
    current_datetime = datetime
    today = current_datetime.now(timezone.utc).date()
    user_id = client.get("/v1/dashboard", headers=auth).json()["user_id"]
    with Session(db_engine) as db:
        user = db.query(User).filter_by(public_id=user_id).one()
        db.add(AdEvent(
            user_id=user.id,
            application_id="ca-app-pub-4973946737213196~3854510671",
            ad_unit_id="2667340525",
            calendar_day=today,
            status="completed",
            transaction_id="yesterdays-verified-event",
        ))
        db.commit()

    class NextUtcDay(current_datetime):
        @classmethod
        def now(cls, tz=None):
            return current_datetime.now(tz) + timedelta(days=1)

    monkeypatch.setattr(api_main, "datetime", NextUtcDay)
    assert client.get("/v1/dashboard", headers=auth).json()["daily_ads"] == 0
    assert client.post("/v1/ads/reservations", headers=auth).status_code == 201


def test_ad_completions_never_credit_wallet(client, auth):
    reservation = client.post("/v1/ads/reservations", headers=auth)
    assert reservation.status_code == 201
    wallet = client.get("/v1/wallet", headers=auth).json()
    assert wallet["available_balance"] == "0.00"
    assert wallet["transactions"] == []
    assert client.get("/v1/dashboard", headers=auth).json()["daily_ads"] == 0


def test_payment_method_is_validated_and_masked(client, auth):
    saved = client.put("/v1/payment-method", headers=auth, json={"country_iso": "SO", "phone": "612345678"})
    assert saved.status_code == 200
    assert saved.json()["country_code"] == "+252"
    assert saved.json()["phone_last4"] == "5678"
    assert client.get("/v1/payment-method", headers=auth).json()["country_iso"] == "SO"
    assert client.put("/v1/payment-method", headers=auth, json={"country_iso": "SO", "phone": "123"}).status_code == 422


def test_withdrawal_requires_payment_method_and_funded_wallet(client, auth):
    request = {"amount": "1.00", "request_key": str(uuid4())}
    assert client.post("/v1/withdrawals", headers=auth, json=request).status_code == 409
    assert client.put("/v1/payment-method", headers=auth, json={"country_iso": "US", "phone": "2025550125"}).status_code == 200
    response = client.post("/v1/withdrawals", headers=auth, json=request)
    assert response.status_code == 409
    assert "Insufficient" in response.json()["detail"]


def test_support_and_preferences_are_backend_persisted(client, auth):
    ticket = client.post("/v1/support", headers=auth, json={
        "category": "Technical Problem", "description": "The notification setting cannot be saved.",
    })
    assert ticket.status_code == 201
    assert ticket.json()["ticket_id"].startswith("TKT-")
    assert ticket.json()["status"] == "OPEN"
    prefs = {"daily_ads": False, "withdrawals": True, "support": False, "account": True}
    assert client.put("/v1/notification-preferences", headers=auth, json=prefs).json() == prefs
    assert client.get("/v1/notification-preferences", headers=auth).json() == prefs
    notifications = client.get("/v1/notifications", headers=auth).json()
    assert len(notifications) == 1
    assert notifications[0]["category"] == "support"


def test_support_replies_and_statuses_are_role_and_user_scoped(client, auth, db_engine):
    created = client.post("/v1/support", headers=auth, json={
        "category": "Wallet", "description": "Please explain the current wallet statement.",
    }).json()
    ticket_id = created["ticket_id"]
    user_tickets = client.get("/v1/support/tickets", headers=auth).json()
    assert user_tickets[0]["ticket_id"] == ticket_id

    other = start_session(client)
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}
    assert client.get("/v1/support/tickets", headers=other_headers).json() == []
    assert client.post(f"/v1/support/tickets/{ticket_id}/messages", headers=other_headers, json={
        "body": "This reply belongs to another user.",
    }).status_code == 404

    admin = start_session(client)
    admin_headers = {"Authorization": f"Bearer {admin['access_token']}"}
    assert client.put("/v1/profile", headers=admin_headers, json={
        "full_name": "Support Admin", "email": "admin@example.com",
        "country_iso": "US", "phone": "2025550125",
    }).status_code == 200
    with Session(db_engine) as db:
        admin_user = db.query(User).filter_by(public_id=admin["user_id"]).one()
        admin_user.role = "admin"
        db.commit()

    reply = client.post(f"/v1/admin/support/tickets/{ticket_id}/messages", headers=admin_headers, json={
        "body": "Your wallet contains no funded balance at this time.",
    })
    assert reply.status_code == 201
    status_response = client.put(f"/v1/admin/support/tickets/{ticket_id}", headers=admin_headers, json={
        "status": "WAITING FOR USER",
    })
    assert status_response.status_code == 200
    assert status_response.json()["messages"][0]["sender"] == "admin"
    user_reply = client.post(f"/v1/support/tickets/{ticket_id}/messages", headers=auth, json={
        "body": "Thank you, I understand the statement.",
    })
    assert user_reply.status_code == 201
    assert user_reply.json()["status"] == "IN REVIEW"
    user_notifications = client.get("/v1/notifications", headers=auth).json()
    assert any(item["title"] == "Support reply" for item in user_notifications)
    assert client.get("/v1/admin/support/tickets", headers=auth).status_code == 403


def test_user_cannot_read_another_users_data(client):
    first = start_session(client)
    second = start_session(client)
    first_headers = {"Authorization": "Bearer " + first["access_token"]}
    second_headers = {"Authorization": "Bearer " + second["access_token"]}
    client.put("/v1/profile", headers=first_headers, json={
        "full_name": "First User", "email": "first@example.com", "country_iso": "US", "phone": "2025550125",
    })
    assert client.get("/v1/profile", headers=second_headers).json()["full_name"] is None
    assert client.get("/v1/dashboard", headers=second_headers).json()["user_id"] == second["user_id"]


def test_wallet_reports_only_server_ledger_entries(client, auth):
    wallet = client.get("/v1/wallet", headers=auth).json()
    assert Decimal(str(wallet["available_balance"])) == Decimal("0.00")
    assert wallet["transactions"] == []
