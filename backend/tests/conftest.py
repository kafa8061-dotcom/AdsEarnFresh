import os
from hashlib import sha256
from uuid import uuid4

os.environ["ENVIRONMENT"] = "development"
os.environ["SESSION_HMAC_SECRET"] = "test-only-session-secret-with-at-least-32-bytes"
os.environ["PAYMENT_ENCRYPTION_KEY"] = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
os.environ["ADMIN_EMAILS"] = "admin@example.com"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
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
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def session(client):
    return start_session(client)


def start_session(client, device_id=None):
    source = device_id or str(uuid4())
    fingerprint = sha256(source.encode()).hexdigest()
    response = client.post("/v1/session", json={"device_fingerprint": fingerprint})
    assert response.status_code == 200
    return response.json()


@pytest.fixture()
def auth(session):
    return {"Authorization": f"Bearer {session['access_token']}"}
