import hashlib
import hmac
import secrets
import base64
import binascii
from datetime import timedelta
from uuid import uuid4

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import DeviceChallenge, User, UserSession, now_utc

bearer = HTTPBearer(auto_error=False)
SESSION_CHALLENGE_TTL = timedelta(minutes=5)


def digest_token(token: str) -> str:
    return hmac.new(get_settings().session_hmac_secret.encode(), token.encode(), hashlib.sha256).hexdigest()


def _device_binding(device_fingerprint: str, public_key: str) -> str:
    identity = f"{device_fingerprint}\n{public_key}".encode("ascii")
    return hmac.new(get_settings().device_binding_secret.encode(), identity, hashlib.sha256).hexdigest()


def issue_device_challenge(db: Session, device_fingerprint: str) -> DeviceChallenge:
    challenge = DeviceChallenge(
        challenge_id=str(uuid4()),
        device_binding=hmac.new(
            get_settings().device_binding_secret.encode(),
            device_fingerprint.encode("ascii"),
            hashlib.sha256,
        ).hexdigest(),
        nonce=secrets.token_urlsafe(32),
        expires_at=now_utc() + SESSION_CHALLENGE_TTL,
    )
    db.add(challenge)
    db.commit()
    return challenge


def create_session(
    db: Session,
    device_fingerprint: str,
    challenge_id: str,
    public_key: str,
    signature: str,
    integrity_token_digest: str | None,
) -> tuple[User, str]:
    challenge = db.scalar(
        select(DeviceChallenge).where(
            DeviceChallenge.challenge_id == challenge_id,
            DeviceChallenge.used_at.is_(None),
            DeviceChallenge.expires_at > now_utc(),
        ).with_for_update()
    )
    if challenge is None:
        raise HTTPException(status_code=401, detail="Device verification is invalid or expired")
    expected_challenge_binding = hmac.new(
        get_settings().device_binding_secret.encode(),
        device_fingerprint.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(challenge.device_binding, expected_challenge_binding):
        challenge.used_at = now_utc()
        db.commit()
        raise HTTPException(status_code=401, detail="Device verification is invalid or expired")

    if get_settings().environment.casefold() == "production" and integrity_token_digest is None:
        raise HTTPException(status_code=401, detail="Play Integrity attestation is required")
    if integrity_token_digest is not None:
        replayed = db.scalar(
            select(DeviceChallenge.challenge_id).where(
                DeviceChallenge.integrity_token_digest == integrity_token_digest,
            )
        )
        if replayed is not None:
            raise HTTPException(status_code=401, detail="Play Integrity token has already been used")

    challenge.used_at = now_utc()
    challenge.integrity_token_digest = integrity_token_digest
    db.commit()
    try:
        public_key_der = base64.b64decode(
            public_key + "=" * (-len(public_key) % 4), altchars=b"-_", validate=True,
        )
        signature_der = base64.b64decode(
            signature + "=" * (-len(signature) % 4), altchars=b"-_", validate=True,
        )
        canonical_public_key = base64.urlsafe_b64encode(public_key_der).rstrip(b"=").decode("ascii")
        if not hmac.compare_digest(public_key, canonical_public_key):
            raise ValueError("Non-canonical device key")
        parsed_key = serialization.load_der_public_key(public_key_der)
        if not isinstance(parsed_key, ec.EllipticCurvePublicKey) or not isinstance(parsed_key.curve, ec.SECP256R1):
            raise ValueError("Unsupported device key")
        signed_payload = f"AdsEarn device session v1\n{device_fingerprint}\n{challenge.nonce}".encode("ascii")
        parsed_key.verify(signature_der, signed_payload, ec.ECDSA(hashes.SHA256()))
    except (ValueError, binascii.Error, InvalidSignature) as exc:
        raise HTTPException(status_code=401, detail="Device verification failed") from exc

    binding = _device_binding(device_fingerprint, public_key)
    for _ in range(5):
        user = db.scalar(select(User).where(User.device_binding == binding).with_for_update())
        if user is not None:
            token = secrets.token_urlsafe(40)
            db.query(UserSession).filter(
                UserSession.user_id == user.id, UserSession.revoked_at.is_(None)
            ).update({UserSession.revoked_at: now_utc()})
            db.add(UserSession(
                user_id=user.id,
                token_hash=digest_token(token),
                expires_at=now_utc() + timedelta(days=get_settings().session_ttl_days),
            ))
            db.commit()
            return user, token
        public_id = "USR-" + secrets.token_hex(4).upper()
        if db.scalar(select(User.id).where(User.public_id == public_id)) is None:
            user = User(public_id=public_id, device_binding=binding, device_public_key=public_key)
            db.add(user)
            try:
                db.flush()
                token = secrets.token_urlsafe(40)
                db.add(UserSession(
                    user_id=user.id,
                    token_hash=digest_token(token),
                    expires_at=now_utc() + timedelta(days=get_settings().session_ttl_days),
                ))
                db.commit()
                db.refresh(user)
                return user, token
            except IntegrityError:
                db.rollback()
                continue
    raise HTTPException(status_code=503, detail="Could not create a secure account")


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="A valid session is required")
    session = db.scalar(
        select(UserSession).where(
            UserSession.token_hash == digest_token(credentials.credentials),
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now_utc(),
        )
    )
    if session is None:
        raise HTTPException(status_code=401, detail="Session is invalid or expired")
    user = db.get(User, session.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Session is invalid or expired")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin" or not user.email or user.email.casefold() not in get_settings().admins:
        raise HTTPException(status_code=403, detail="Administrator access required")
    return user


def encrypt_payment_number(phone: str) -> str:
    key = get_settings().payment_encryption_key
    if not key:
        raise HTTPException(status_code=503, detail="Payment storage is not configured")
    return Fernet(key.encode()).encrypt(phone.encode()).decode()


def decrypt_payment_number(ciphertext: str) -> str:
    key = get_settings().payment_encryption_key
    if not key:
        raise HTTPException(status_code=503, detail="Payment storage is not configured")
    return Fernet(key.encode()).decrypt(ciphertext.encode()).decode()
