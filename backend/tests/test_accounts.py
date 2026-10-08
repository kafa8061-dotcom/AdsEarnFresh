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


def test_device_fingerprint_alone_cannot_recover_an_existing_account(client):
    from cryptography.hazmat.primitives.asymmetric import ec

    victim = start_session(client, "known-device-fingerprint")
    victim_headers = {"Authorization": f"Bearer {victim['access_token']}"}
    saved = client.put("/v1/profile", headers=victim_headers, json={
        "full_name": "Private Profile", "email": "private@example.com",
        "country_iso": "US", "phone": "2025550125",
    })
    assert saved.status_code == 200

    attacker = start_session(
        client, "known-device-fingerprint", device_key=ec.generate_private_key(ec.SECP256R1()),
    )
    attacker_headers = {"Authorization": f"Bearer {attacker['access_token']}"}
    assert attacker["user_id"] != victim["user_id"]
    assert client.get("/v1/profile", headers=attacker_headers).json()["full_name"] is None
    assert client.get("/v1/wallet", headers=attacker_headers).json()["available_balance"] == "0.00"
    assert client.get("/v1/profile", headers=victim_headers).json()["full_name"] == "Private Profile"


def test_device_session_challenge_is_single_use(client):
    import base64
    from hashlib import sha256
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    fingerprint = sha256(b"challenge-replay-test").hexdigest()
    challenge = client.post("/v1/session/challenge", json={"device_fingerprint": fingerprint}).json()
    key = ec.generate_private_key(ec.SECP256R1())
    public_key = key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    message = f"AdsEarn device session v1\n{fingerprint}\n{challenge['nonce']}".encode("ascii")
    signature = key.sign(message, ec.ECDSA(hashes.SHA256()))
    request = {
        "device_fingerprint": fingerprint,
        "challenge_id": challenge["challenge_id"],
        "public_key": base64.urlsafe_b64encode(public_key).decode().rstrip("="),
        "signature": base64.urlsafe_b64encode(signature).decode().rstrip("="),
    }
    first = client.post("/v1/session", json=request)
    assert first.status_code == 200
    assert client.post("/v1/session", json=request).status_code == 401


def test_device_proof_cannot_be_rebound_to_another_public_key(client):
    import base64
    from hashlib import sha256
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    fingerprint = sha256(b"key-tamper-test").hexdigest()
    challenge = client.post("/v1/session/challenge", json={"device_fingerprint": fingerprint}).json()
    key = ec.generate_private_key(ec.SECP256R1())
    other_key = ec.generate_private_key(ec.SECP256R1())
    public_key = key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    other_public_key = other_key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    message = f"AdsEarn device session v1\n{fingerprint}\n{challenge['nonce']}".encode("ascii")
    signature = key.sign(message, ec.ECDSA(hashes.SHA256()))
    result = client.post("/v1/session", json={
        "device_fingerprint": fingerprint,
        "challenge_id": challenge["challenge_id"],
        "public_key": base64.urlsafe_b64encode(other_public_key).decode().rstrip("="),
        "signature": base64.urlsafe_b64encode(signature).decode().rstrip("="),
    })
    assert result.status_code == 401


def test_production_anonymous_sessions_fail_closed_until_explicitly_enabled(client, monkeypatch):
    from app import main as api_main

    monkeypatch.setattr(api_main.settings, "environment", "production")
    challenge = client.post("/v1/session/challenge", json={
        "device_fingerprint": "a" * 64,
    })
    assert challenge.status_code == 503
    assert "not enabled" in challenge.json()["detail"]
    direct_session = client.post("/v1/session", json={
        "device_fingerprint": "a" * 64,
        "challenge_id": "00000000-0000-0000-0000-000000000000",
        "public_key": "A" * 100,
        "signature": "B" * 100,
    })
    assert direct_session.status_code == 503


def test_enabled_production_session_still_requires_integrity_token(client, monkeypatch):
    from app import main as api_main

    monkeypatch.setattr(api_main.settings, "environment", "production")
    monkeypatch.setattr(api_main.settings, "anonymous_sessions_enabled", True)
    monkeypatch.setattr(api_main.settings, "edge_rate_limiting_configured", True)
    challenge = client.post("/v1/session/challenge", json={
        "device_fingerprint": "b" * 64,
    })
    response = client.post("/v1/session", json={
        "device_fingerprint": "b" * 64,
        "challenge_id": challenge.json()["challenge_id"],
        "public_key": "A" * 100,
        "signature": "B" * 100,
    })
    assert response.status_code == 401
    assert "attestation is required" in response.json()["detail"]


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
    assert client.get("/health/ready").json() == {"status": "ok"}
    assert client.get("/health/live").json() == {"status": "ok"}
    assert client.get("/health").headers["cache-control"] == "no-store"


def test_readiness_reports_database_unavailable_without_leaking_connection_details(client, monkeypatch):
    from app.database import get_db

    class UnavailableDatabase:
        def execute(self, _statement):
            from sqlalchemy.exc import OperationalError

            raise OperationalError("SELECT 1", {}, RuntimeError("private connection detail"))

    def unavailable_db():
        yield UnavailableDatabase()

    from app.main import app
    app.dependency_overrides[get_db] = unavailable_db
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "dependency": "database"}


def test_readiness_rejects_schema_behind_application_revision(client, db_engine):
    from sqlalchemy import text

    with db_engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num = 'stale_revision'"))
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "dependency": "database_schema"}


def test_production_rejects_plain_http_transport(monkeypatch):
    from fastapi.testclient import TestClient
    from app import main as api_main

    monkeypatch.setattr(api_main.settings, "environment", "production")
    with TestClient(api_main.app, base_url="http://testserver") as insecure_client:
        response = insecure_client.get("/v1/profile")
    assert response.status_code == 400
    assert response.json() == {"detail": "HTTPS is required"}


def test_production_configuration_rejects_non_postgres_and_accepts_secure_values():
    import pytest

    with pytest.raises(ValueError, match="PostgreSQL"):
        Settings(environment="production", database_url="sqlite:///./production.db").validate_deployment()

    production = Settings(
        environment="production",
        database_url="postgresql+psycopg://db.adsearn.com/adsearn?sslmode=verify-full",
        session_hmac_secret="session-secret-value-with-more-than-32-characters",
        device_binding_secret="device-binding-secret-with-more-than-32-characters",
        payment_encryption_key="MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
        public_base_url="https://api.adsearn.com/",
        allowed_hosts="api.adsearn.com",
        cors_origins="https://app.adsearn.com",
        forwarded_allow_ips="10.0.0.10",
        admin_emails="ops@adsearn.com",
        admob_app_id="ca-app-pub-4973946737213196~3854510671",
        admob_rewarded_unit_id="2667340525",
        play_integrity_cloud_project_number=123456789012,
        play_integrity_package_name="com.adsearn.mobile",
        play_integrity_certificate_sha256="MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
    )
    production.validate_deployment()


def test_production_configuration_rejects_placeholders_wildcard_cors_and_unverified_database_tls():
    import pytest

    valid = {
        "environment": "production",
        "database_url": "postgresql+psycopg://db.adsearn.com/adsearn?sslmode=verify-full",
        "session_hmac_secret": "session-secret-value-with-more-than-32-characters",
        "device_binding_secret": "device-binding-secret-with-more-than-32-characters",
        "payment_encryption_key": "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
        "public_base_url": "https://api.adsearn.com/",
        "allowed_hosts": "api.adsearn.com",
        "cors_origins": "https://app.adsearn.com",
        "forwarded_allow_ips": "10.0.0.10",
        "admin_emails": "ops@adsearn.com",
        "play_integrity_cloud_project_number": 123456789012,
        "play_integrity_certificate_sha256": "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
    }
    for overrides, error in (
        ({"database_url": "postgresql+psycopg://db.adsearn.com/adsearn?sslmode=require"}, "verify-full"),
        ({"database_url": "postgresql+psycopg://db.adsearn.com/adsearn?sslmode=verify-full&sslmode=require"}, "verify-full"),
        ({"cors_origins": "*"}, "CORS_ORIGINS"),
        ({"session_hmac_secret": "development-only-session-secret-change-before-production"}, "SESSION_HMAC_SECRET"),
        ({"public_base_url": "https://<real-production-api-domain>/"}, "HTTPS public API URL"),
        ({"admin_emails": "<approved-administrator-email-addresses>"}, "ADMIN_EMAILS"),
    ):
        with pytest.raises(ValueError, match=error):
            Settings(**(valid | overrides)).validate_deployment()


def test_production_sessions_stay_disabled_without_play_configuration():
    import pytest

    values = {
        "environment": "production",
        "database_url": "postgresql+psycopg://db.adsearn.com/adsearn?sslmode=verify-full",
        "session_hmac_secret": "session-secret-value-with-more-than-32-characters",
        "device_binding_secret": "device-binding-secret-with-more-than-32-characters",
        "payment_encryption_key": "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
        "public_base_url": "https://api.adsearn.com/",
        "allowed_hosts": "api.adsearn.com",
        "cors_origins": "https://app.adsearn.com",
        "forwarded_allow_ips": "10.0.0.10",
        "admin_emails": "ops@adsearn.com",
    }
    Settings(**values).validate_deployment()
    with pytest.raises(ValueError, match="PLAY_INTEGRITY_CLOUD_PROJECT_NUMBER"):
        Settings(**(values | {
            "anonymous_sessions_enabled": True,
            "edge_rate_limiting_configured": True,
        })).validate_deployment()


def test_production_withdrawals_require_server_reward_funding_policy():
    import pytest

    values = {
        "environment": "production",
        "database_url": "postgresql+psycopg://db.adsearn.com/adsearn?sslmode=verify-full",
        "session_hmac_secret": "session-secret-value-with-more-than-32-characters",
        "device_binding_secret": "device-binding-secret-with-more-than-32-characters",
        "payment_encryption_key": "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
        "public_base_url": "https://api.adsearn.com/",
        "allowed_hosts": "api.adsearn.com",
        "cors_origins": "https://app.adsearn.com",
        "forwarded_allow_ips": "10.0.0.10",
        "admin_emails": "ops@adsearn.com",
    }
    Settings(**values).validate_deployment()
    with pytest.raises(ValueError, match="funding policy"):
        Settings(**(values | {"withdrawals_enabled": True})).validate_deployment()


def test_database_urls_use_psycopg_three_for_application_and_migrations():
    from app.database import normalize_database_url

    assert normalize_database_url("postgres://user:pass@db.example/app") == (
        "postgresql+psycopg://user:pass@db.example/app"
    )
    assert normalize_database_url("postgresql://user:pass@db.example/app") == (
        "postgresql+psycopg://user:pass@db.example/app"
    )
    assert normalize_database_url("postgresql+psycopg://user:pass@db.example/app") == (
        "postgresql+psycopg://user:pass@db.example/app"
    )


def test_internal_user_id_cannot_be_written_by_profile(client, session, db_engine):
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    result = client.put("/v1/profile", headers=headers, json={
        "full_name": "Ada", "email": "ada@example.com", "country_iso": "US",
        "phone": "2025550125", "user_id": "USR-FORGED", "role": "admin",
    })
    assert result.status_code == 200
    assert result.json()["user_id"] == session["user_id"]

    from sqlalchemy.orm import Session
    from app.models import User

    with Session(db_engine) as db:
        user = db.query(User).filter_by(public_id=session["user_id"]).one()
        assert user.role == "user"


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
