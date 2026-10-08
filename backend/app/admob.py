import base64
import binascii
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AdEvent, GoogleSsvKey, User, now_utc


def _decode_signature(signature: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(status_code=400, detail="Invalid SSV signature") from exc


def _signed_payload(raw_query: str) -> tuple[bytes, dict[str, str]]:
    if len(raw_query) > 8192:
        raise HTTPException(status_code=413, detail="SSV callback is too large")
    segments = raw_query.split("&")
    names = [segment.partition("=")[0] for segment in segments]
    if len(segments) < 3 or names[-2:] != ["signature", "key_id"] or len(names) != len(set(names)):
        raise HTTPException(status_code=400, detail="Malformed signed SSV query")
    try:
        values = parse_qs(raw_query, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Malformed SSV query") from exc
    if any(len(items) != 1 for items in values.values()):
        raise HTTPException(status_code=400, detail="Duplicate SSV parameters are not allowed")
    params = {key: items[-1] for key, items in values.items()}
    if "signature" not in params or "key_id" not in params:
        raise HTTPException(status_code=400, detail="Missing SSV signature")
    prefix = "&".join(segments[:-2])
    if not prefix:
        raise HTTPException(status_code=400, detail="Invalid SSV payload")
    return prefix.encode("ascii"), params


def _fetch_google_keys(db: Session, force: bool = False) -> dict[int, str]:
    settings = get_settings()
    cached = db.scalars(select(GoogleSsvKey)).all()
    fresh = cached and min(key.refreshed_at for key in cached) > now_utc() - timedelta(hours=12)
    if force or not fresh:
        try:
            response = httpx.get(settings.admob_ssv_key_url, timeout=5.0)
            response.raise_for_status()
            data = response.json()
            fetched = {
                int(item["keyId"]): (item["pem"], datetime.fromtimestamp(int(item["keyExpirationTime"]) / 1000, timezone.utc))
                for item in data["keys"]
            }
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise HTTPException(status_code=503, detail="SSV verification keys are temporarily unavailable") from exc
        for key_id, (pem, expires_at) in fetched.items():
            row = db.get(GoogleSsvKey, key_id)
            if row is None:
                db.add(GoogleSsvKey(key_id=key_id, pem=pem, refreshed_at=now_utc(), expires_at=expires_at))
            else:
                row.pem = pem
                row.refreshed_at = now_utc()
                row.expires_at = expires_at
        db.commit()
        cached = db.scalars(select(GoogleSsvKey)).all()
    current = now_utc()
    return {key.key_id: key.pem for key in cached if key.expires_at > current}


def verify_google_ssv(db: Session, raw_query: str) -> tuple[dict[str, str], AdEvent]:
    payload, params = _signed_payload(raw_query)
    required = (
        "ad_network", "ad_unit", "user_id", "custom_data",
        "transaction_id", "timestamp", "signature", "key_id",
    )
    if any(not params.get(key) for key in required):
        raise HTTPException(status_code=400, detail="Incomplete SSV callback")
    try:
        key_id = int(params["key_id"])
        timestamp = int(params["timestamp"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid SSV callback") from exc
    keys = _fetch_google_keys(db)
    pem = keys.get(key_id)
    if pem is None:
        keys = _fetch_google_keys(db, force=True)
        pem = keys.get(key_id)
    if pem is None:
        raise HTTPException(status_code=400, detail="Unknown SSV verification key")
    try:
        public_key = serialization.load_pem_public_key(pem.encode("ascii"))
        if not isinstance(public_key, ec.EllipticCurvePublicKey):
            raise ValueError("Unsupported Google SSV key")
        public_key.verify(_decode_signature(params["signature"]), payload, ec.ECDSA(hashes.SHA256()))
    except (ValueError, InvalidSignature, binascii.Error) as exc:
        raise HTTPException(status_code=400, detail="Invalid SSV signature") from exc
    if abs(int(time.time() * 1000) - timestamp) > 10 * 60 * 1000:
        raise HTTPException(status_code=400, detail="SSV callback timestamp is outside the allowed window")
    reservation = db.scalar(select(AdEvent).where(AdEvent.reservation_id == params["custom_data"]))
    if reservation is None or reservation.ad_unit_id != params["ad_unit"]:
        raise HTTPException(status_code=409, detail="SSV reservation is invalid or already processed")
    if (
        params["ad_unit"] != get_settings().admob_rewarded_unit_id
        or reservation.application_id != get_settings().admob_app_id
    ):
        raise HTTPException(status_code=400, detail="SSV callback application does not match")
    reservation_created_at = reservation.created_at
    if reservation_created_at.tzinfo is None:
        reservation_created_at = reservation_created_at.replace(tzinfo=timezone.utc)
    if now_utc() - reservation_created_at > timedelta(minutes=20):
        raise HTTPException(status_code=409, detail="SSV reservation has expired")
    if reservation.status == "completed" and reservation.transaction_id == params["transaction_id"]:
        return params, reservation
    if reservation.status != "reserved":
        raise HTTPException(status_code=409, detail="SSV reservation is invalid or already processed")
    user = db.get(User, reservation.user_id)
    if user is None or user.public_id != params["user_id"]:
        raise HTTPException(status_code=403, detail="SSV user association does not match")
    event_day = datetime.fromtimestamp(timestamp / 1000, timezone.utc).date()
    db.scalar(select(User).where(User.id == reservation.user_id).with_for_update())
    db.refresh(reservation)
    if reservation.status == "completed" and reservation.transaction_id == params["transaction_id"]:
        return params, reservation
    if reservation.status != "reserved":
        raise HTTPException(status_code=409, detail="SSV reservation is invalid or already processed")
    completed_today = db.query(AdEvent).filter(
        AdEvent.user_id == reservation.user_id,
        AdEvent.calendar_day == event_day,
        AdEvent.status == "completed",
    ).count()
    if completed_today >= 10:
        raise HTTPException(status_code=409, detail="Daily rewarded ad limit reached")
    duplicate = db.scalar(select(AdEvent.id).where(AdEvent.transaction_id == params["transaction_id"]))
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="SSV transaction was already processed")
    return params, reservation
