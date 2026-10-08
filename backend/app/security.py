import hashlib
import hmac
import secrets
from datetime import timedelta

from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import User, UserSession, now_utc

bearer = HTTPBearer(auto_error=False)


def digest_token(token: str) -> str:
    return hmac.new(get_settings().session_hmac_secret.encode(), token.encode(), hashlib.sha256).hexdigest()


def create_session(db: Session, device_fingerprint: str) -> tuple[User, str]:
    binding = hmac.new(
        get_settings().device_binding_secret.encode(),
        device_fingerprint.encode(),
        hashlib.sha256,
    ).hexdigest()
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
            user = User(public_id=public_id, device_binding=binding)
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
