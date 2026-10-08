import hashlib
import hmac
import time
from collections.abc import Mapping
from urllib.parse import quote

import google.auth
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import AuthorizedSession
from requests import RequestException
from fastapi import HTTPException

from app.config import get_settings

PLAY_INTEGRITY_SCOPE = "https://www.googleapis.com/auth/playintegrity"
MAX_TOKEN_AGE_MS = 2 * 60 * 1000
MAX_FUTURE_SKEW_MS = 30 * 1000


def session_request_hash(
    package_name: str,
    device_fingerprint: str,
    challenge_id: str,
    nonce: str,
    public_key: str,
) -> str:
    canonical_request = "\n".join((
        "adsearn-session-v1",
        package_name,
        device_fingerprint,
        challenge_id,
        nonce,
        public_key,
    )).encode("ascii")
    return hashlib.sha256(canonical_request).hexdigest()


def integrity_token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def decode_integrity_token(token: str) -> Mapping[str, object]:
    settings = get_settings()
    if not token or len(token) > 20_000:
        raise HTTPException(status_code=401, detail="Play Integrity token is invalid")
    try:
        credentials, _ = google.auth.default(scopes=[PLAY_INTEGRITY_SCOPE])
        authorized_session = AuthorizedSession(credentials)
        response = authorized_session.post(
            "https://playintegrity.googleapis.com/v1/"
            f"{quote(settings.play_integrity_package_name, safe='')}:decodeIntegrityToken",
            json={"integrityToken": token},
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
    except (GoogleAuthError, RequestException, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Play Integrity verification is temporarily unavailable") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=401, detail="Play Integrity token is invalid")
    return payload


def verify_integrity_payload(
    payload: Mapping[str, object],
    expected_request_hash: str,
    *,
    now_ms: int | None = None,
) -> None:
    settings = get_settings()
    try:
        token_payload = payload["tokenPayloadExternal"]
        if not isinstance(token_payload, Mapping):
            raise TypeError
        request_details = token_payload["requestDetails"]
        app_integrity = token_payload["appIntegrity"]
        device_integrity = token_payload["deviceIntegrity"]
        account_details = token_payload["accountDetails"]
        if not all(isinstance(value, Mapping) for value in (
            request_details, app_integrity, device_integrity, account_details,
        )):
            raise TypeError
        request_hash = request_details["requestHash"]
        request_package = request_details["requestPackageName"]
        timestamp = int(request_details["timestampMillis"])
        app_package = app_integrity["packageName"]
        app_recognition = app_integrity["appRecognitionVerdict"]
        certificate_digests = app_integrity["certificateSha256Digest"]
        device_verdicts = device_integrity["deviceRecognitionVerdict"]
        licensing_verdict = account_details["appLicensingVerdict"]
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Play Integrity response is incomplete") from exc

    if (
        not isinstance(request_hash, str)
        or not hmac.compare_digest(request_hash, expected_request_hash)
        or request_package != settings.play_integrity_package_name
    ):
        raise HTTPException(status_code=401, detail="Play Integrity request binding does not match")

    current_ms = int(time.time() * 1000) if now_ms is None else now_ms
    age_ms = current_ms - timestamp
    if age_ms < -MAX_FUTURE_SKEW_MS or age_ms > MAX_TOKEN_AGE_MS:
        raise HTTPException(status_code=401, detail="Play Integrity token is expired")

    if (
        app_package != settings.play_integrity_package_name
        or app_recognition != "PLAY_RECOGNIZED"
        or not isinstance(certificate_digests, list)
        or not any(
            isinstance(digest, str) and digest in settings.play_integrity_certificate_digests
            for digest in certificate_digests
        )
    ):
        raise HTTPException(status_code=401, detail="Play Integrity app identity is not recognized")
    if not isinstance(device_verdicts, list) or "MEETS_DEVICE_INTEGRITY" not in device_verdicts:
        raise HTTPException(status_code=401, detail="Play Integrity device verdict is insufficient")
    if licensing_verdict != "LICENSED":
        raise HTTPException(status_code=401, detail="Google Play has not licensed this app installation")


def verify_integrity_token(token: str, expected_request_hash: str) -> str:
    payload = decode_integrity_token(token)
    verify_integrity_payload(payload, expected_request_hash)
    return integrity_token_digest(token)
