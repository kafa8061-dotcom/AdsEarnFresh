from conftest import start_session
from app.config import Settings


def test_anonymous_session_is_unique_and_revocable(client):
    first = start_session(client)
    second = start_session(client)
    assert first["user_id"].startswith("USR-")
    assert first["user_id"] != second["user_id"]
    headers = {"Authorization": f"Bearer {first['access_token']}"}
    assert client.get("/v1/profile", headers=headers).status_code == 200
    assert client.post("/v1/session/logout", headers=headers).status_code == 204
    assert client.get("/v1/profile", headers=headers).status_code == 401


def test_profile_is_validated_and_stays_private(client, session):
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    saved = client.put("/v1/profile", headers=headers, json={
        "full_name": "Ada Example",
        "email": "ADA@example.com",
        "country_iso": "KE",
        "phone": "712345678",
    })
    assert saved.status_code == 200
    assert saved.json()["phone"] == "+254712345678"
    assert saved.json()["country_code"] == "+254"
    assert client.get("/v1/profile", headers=headers).json()["full_name"] == "Ada Example"

    invalid = client.put("/v1/profile", headers=headers, json={
        "full_name": "Ada", "email": "ada@example.com", "country_iso": "KE", "phone": "123",
    })
    assert invalid.status_code == 422
    other = start_session(client)
    wallet = client.get("/v1/wallet", headers={"Authorization": f"Bearer {other['access_token']}"}).json()
    assert wallet["available_balance"] == "0.00"


def test_international_phone_country_and_calling_codes(client):
    countries = [
        ("KE", "712345678", "+254712345678", "+254"),
        ("SO", "612345678", "+252612345678", "+252"),
        ("US", "2025550125", "+12025550125", "+1"),
        ("GB", "7400123456", "+447400123456", "+44"),
    ]
    for region, phone, expected_e164, expected_code in countries:
        auth_session = start_session(client)
        result = client.put(
            "/v1/profile",
            headers={"Authorization": f"Bearer {auth_session['access_token']}"},
            json={
                "full_name": "Phone Test",
                "email": f"phone-{region.lower()}@example.com",
                "country_iso": region,
                "phone": phone,
            },
        )
        assert result.status_code == 200, f"{region}: {result.text}"
        assert result.json()["phone"] == expected_e164
        assert result.json()["country_code"] == expected_code


def test_missing_or_invalid_session_cannot_access_profile(client):
    assert client.get("/v1/profile").status_code == 401
    assert client.get("/v1/profile", headers={"Authorization": "Bearer invalid"}).status_code == 401
    assert client.post("/v1/session", json={"device_fingerprint": "not-a-valid-device-binding"}).status_code == 422


def test_health_checks_database(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_production_configuration_rejects_non_postgres_and_accepts_secure_values():
    import pytest

    with pytest.raises(ValueError, match="PostgreSQL"):
        Settings(environment="production", database_url="sqlite:///./production.db").validate_deployment()

    production = Settings(
        environment="production",
        database_url="postgresql+psycopg://db.adsearn.com/adsearn",
        session_hmac_secret="session-secret-value-with-more-than-32-characters",
        device_binding_secret="device-binding-secret-with-more-than-32-characters",
        payment_encryption_key="MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
        public_base_url="https://api.adsearn.com/",
        admob_app_id="ca-app-pub-4973946737213196~3854510671",
        admob_rewarded_unit_id="2667340525",
    )
    production.validate_deployment()


def test_internal_user_id_cannot_be_written_by_profile(client, session):
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    result = client.put("/v1/profile", headers=headers, json={
        "full_name": "Ada", "email": "ada@example.com", "country_iso": "US",
        "phone": "2025550125", "user_id": "USR-FORGED",
    })
    assert result.status_code == 200
    assert result.json()["user_id"] == session["user_id"]


def test_reinstall_on_same_device_recovers_private_account_and_revokes_old_token(client):
    first = start_session(client, "same-android-install-id")
    headers = {"Authorization": f"Bearer {first['access_token']}"}
    saved = client.put("/v1/profile", headers=headers, json={
        "full_name": "Persistent profile", "email": "person@example.com",
        "country_iso": "US", "phone": "2025550125",
    })
    assert saved.status_code == 200
    reinstalled = start_session(client, "same-android-install-id")
    assert reinstalled["user_id"] == first["user_id"]
    assert client.get("/v1/profile", headers=headers).status_code == 401
    restored = client.get("/v1/profile", headers={"Authorization": f"Bearer {reinstalled['access_token']}"})
    assert restored.json()["full_name"] == "Persistent profile"
