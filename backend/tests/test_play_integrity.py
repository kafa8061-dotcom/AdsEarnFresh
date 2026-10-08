import base64
import hashlib
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from hashlib import sha256

from app import main as api_main
from app import play_integrity
from app.config import Settings
from app.play_integrity import session_request_hash, verify_integrity_payload

PACKAGE_NAME = "com.adsearn.mobile"
CERTIFICATE_DIGEST = base64.b64encode(b"c" * 32).decode("ascii")
EXPECTED_HASH = "a" * 64


@pytest.fixture()
def play_settings(monkeypatch):
    configured = Settings(
        play_integrity_package_name=PACKAGE_NAME,
        play_integrity_certificate_sha256=CERTIFICATE_DIGEST,
    )
    monkeypatch.setattr(play_integrity, "get_settings", lambda: configured)
    return configured


def integrity_payload(now_ms, **overrides):
    request_details = {
        "requestPackageName": overrides.get("request_package", PACKAGE_NAME),
        "requestHash": overrides.get("request_hash", EXPECTED_HASH),
        "timestampMillis": str(overrides.get("timestamp", now_ms)),
    }
    app_integrity = {
        "packageName": overrides.get("app_package", PACKAGE_NAME),
        "appRecognitionVerdict": overrides.get("app_verdict", "PLAY_RECOGNIZED"),
        "certificateSha256Digest": [overrides.get("certificate", CERTIFICATE_DIGEST)],
    }
    device_integrity = {
        "deviceRecognitionVerdict": overrides.get("device_verdict", ["MEETS_DEVICE_INTEGRITY"]),
    }
    account_details = {"appLicensingVerdict": overrides.get("licensing", "LICENSED")}
    return {"tokenPayloadExternal": {
        "requestDetails": request_details,
        "appIntegrity": app_integrity,
        "deviceIntegrity": device_integrity,
        "accountDetails": account_details,
    }}


def test_valid_play_integrity_payload_is_accepted(play_settings):
    current_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    verify_integrity_payload(integrity_payload(current_ms), EXPECTED_HASH, now_ms=current_ms)


@pytest.mark.parametrize("payload", [
    {},
    {"tokenPayloadExternal": {}},
    {"tokenPayloadExternal": {
        "requestDetails": {},
        "appIntegrity": {},
        "deviceIntegrity": {},
        "accountDetails": {},
    }},
])
def test_malformed_play_integrity_payloads_are_rejected(play_settings, payload):
    with pytest.raises(HTTPException) as error:
        verify_integrity_payload(payload, EXPECTED_HASH, now_ms=1_800_000_000_000)
    assert error.value.status_code == 401


def test_expired_play_integrity_token_is_rejected(play_settings):
    now_ms = 1_800_000_000_000
    with pytest.raises(HTTPException, match="expired"):
        verify_integrity_payload(
            integrity_payload(now_ms - 120_001), EXPECTED_HASH, now_ms=now_ms,
        )


@pytest.mark.parametrize("overrides", [
    {"request_package": "com.attacker.app"},
    {"app_package": "com.attacker.app"},
    {"request_hash": "b" * 64},
    {"app_verdict": "UNRECOGNIZED_VERSION"},
    {"certificate": base64.b64encode(b"x" * 32).decode("ascii")},
    {"device_verdict": ["MEETS_BASIC_INTEGRITY"]},
    {"licensing": "UNLICENSED"},
])
def test_wrong_identity_binding_or_integrity_verdict_fails(overrides, play_settings):
    now_ms = 1_800_000_000_000
    with pytest.raises(HTTPException) as error:
        verify_integrity_payload(
            integrity_payload(now_ms, **overrides), EXPECTED_HASH, now_ms=now_ms,
        )
    assert error.value.status_code == 401


def test_google_decode_failure_fails_closed(monkeypatch):
    monkeypatch.setattr(
        play_integrity, "decode_integrity_token",
        lambda _token: (_ for _ in ()).throw(HTTPException(status_code=503, detail="Google unavailable")),
    )
    with pytest.raises(HTTPException) as error:
        play_integrity.verify_integrity_token("opaque-integrity-token", EXPECTED_HASH)
    assert error.value.status_code == 503


def test_google_rejection_of_malformed_token_fails_closed(monkeypatch):
    class Response:
        def raise_for_status(self):
            raise play_integrity.RequestException("Google rejected token")

    class Authorized:
        def post(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr(play_integrity.google.auth, "default", lambda **_kwargs: (object(), None))
    monkeypatch.setattr(play_integrity, "AuthorizedSession", lambda _credentials: Authorized())
    with pytest.raises(HTTPException) as error:
        play_integrity.decode_integrity_token("malformed-integrity-token")
    assert error.value.status_code == 503


def test_google_token_decode_uses_canonical_api_request_and_validates_response(monkeypatch, play_settings):
    current_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    expected_payload = integrity_payload(current_ms)

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return expected_payload

    class Authorized:
        def post(self, url, **kwargs):
            assert url == (
                "https://playintegrity.googleapis.com/v1/"
                f"{PACKAGE_NAME}:decodeIntegrityToken"
            )
            assert kwargs["json"] == {"integrityToken": "valid-google-token"}
            assert kwargs["timeout"] == 8
            return Response()

    monkeypatch.setattr(play_integrity.google.auth, "default", lambda **_kwargs: (object(), None))
    monkeypatch.setattr(play_integrity, "AuthorizedSession", lambda _credentials: Authorized())
    assert play_integrity.verify_integrity_token("valid-google-token", EXPECTED_HASH) == (
        hashlib.sha256(b"valid-google-token").hexdigest()
    )


def _production_session_request(client, source, token, device_key=None):
    fingerprint = sha256(source.encode()).hexdigest()
    challenge = client.post("/v1/session/challenge", json={"device_fingerprint": fingerprint}).json()
    key = device_key or ec.generate_private_key(ec.SECP256R1())
    public_key = key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    public_key_text = base64.urlsafe_b64encode(public_key).decode().rstrip("=")
    request_hash = session_request_hash(
        PACKAGE_NAME, fingerprint, challenge["challenge_id"], challenge["nonce"], public_key_text,
    )
    proof = key.sign(
        f"AdsEarn device session v1\n{fingerprint}\n{challenge['nonce']}".encode("ascii"),
        ec.ECDSA(hashes.SHA256()),
    )
    return {
        "device_fingerprint": fingerprint,
        "challenge_id": challenge["challenge_id"],
        "public_key": public_key_text,
        "signature": base64.urlsafe_b64encode(proof).decode().rstrip("="),
        "integrity_token": token,
    }, request_hash


def test_production_session_requires_and_accepts_server_verified_integrity(client, monkeypatch):
    monkeypatch.setattr(api_main.settings, "environment", "production")
    monkeypatch.setattr(api_main.settings, "play_integrity_package_name", PACKAGE_NAME)
    monkeypatch.setattr(api_main.settings, "anonymous_sessions_enabled", True)
    monkeypatch.setattr(api_main.settings, "edge_rate_limiting_configured", True)
    token = "valid-integrity-token"
    request, expected_hash = _production_session_request(client, "valid-production-session", token)
    monkeypatch.setattr(
        api_main, "verify_integrity_token",
        lambda supplied, request_hash: hashlib.sha256(supplied.encode()).hexdigest()
        if supplied == token and request_hash == expected_hash
        else (_ for _ in ()).throw(HTTPException(status_code=401, detail="invalid integrity")),
    )
    response = client.post("/v1/session", json=request)
    assert response.status_code == 200
    assert response.json()["user_id"].startswith("USR-")


def test_production_session_rejects_replayed_integrity_token(client, monkeypatch):
    monkeypatch.setattr(api_main.settings, "environment", "production")
    monkeypatch.setattr(api_main.settings, "play_integrity_package_name", PACKAGE_NAME)
    monkeypatch.setattr(api_main.settings, "anonymous_sessions_enabled", True)
    monkeypatch.setattr(api_main.settings, "edge_rate_limiting_configured", True)
    token = "single-use-integrity-token"
    token_digest = hashlib.sha256(token.encode()).hexdigest()
    monkeypatch.setattr(api_main, "verify_integrity_token", lambda _token, _hash: token_digest)
    first, _ = _production_session_request(client, "integrity-first-device", token)
    second, _ = _production_session_request(client, "integrity-second-device", token)
    assert client.post("/v1/session", json=first).status_code == 200
    replay = client.post("/v1/session", json=second)
    assert replay.status_code == 401
    assert "already been used" in replay.json()["detail"]
