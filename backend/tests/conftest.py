import os
from hashlib import sha256
from functools import lru_cache
from uuid import uuid4

os.environ["ENVIRONMENT"] = "development"
os.environ["SESSION_HMAC_SECRET"] = "test-only-session-secret-with-at-least-32-bytes"
os.environ["PAYMENT_ENCRYPTION_KEY"] = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
os.environ["ADMIN_EMAILS"] = "admin@example.com"

import pytest
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


@pytest.fixture()
def db_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"
        ))
        connection.execute(text(
            "INSERT INTO alembic_version (version_num) VALUES ('0001_initial')"
        ))
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def client(db_engine):
    session_factory = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def session(client):
    return start_session(client)


@lru_cache(maxsize=None)
def _test_device_key(device_id):
    return ec.generate_private_key(ec.SECP256R1())


def start_session(client, device_id=None, device_key=None):
    source = device_id or str(uuid4())
    fingerprint = sha256(source.encode()).hexdigest()
    key = device_key or _test_device_key(source)
    challenge = client.post("/v1/session/challenge", json={"device_fingerprint": fingerprint})
    assert challenge.status_code == 200
    nonce = challenge.json()["nonce"]
    public_key = key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    payload = f"AdsEarn device session v1\n{fingerprint}\n{nonce}".encode("ascii")
    signature = key.sign(payload, ec.ECDSA(hashes.SHA256()))
    import base64

    response = client.post("/v1/session", json={
        "device_fingerprint": fingerprint,
        "challenge_id": challenge.json()["challenge_id"],
        "public_key": base64.urlsafe_b64encode(public_key).decode("ascii").rstrip("="),
        "signature": base64.urlsafe_b64encode(signature).decode("ascii").rstrip("="),
    })
    assert response.status_code == 200
    return response.json()


@pytest.fixture()
def auth(session):
    return {"Authorization": f"Bearer {session['access_token']}"}
