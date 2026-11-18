import os

os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL", "sqlite:///./test_itsm.db")
os.environ["ENABLE_BACKGROUND_JOBS"] = "false"
os.environ["BCRYPT_ROUNDS"] = "4"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import database, models  # noqa: E402,F401
from app.database import Base  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import PASSWORD, seed  # noqa: E402


@pytest.fixture()
def db():
    Base.metadata.drop_all(bind=database.engine)
    Base.metadata.create_all(bind=database.engine)
    session = database.SessionLocal()
    seed(session)
    session.commit()
    yield session
    session.close()


@pytest.fixture()
def client(db):
    with TestClient(app) as c:
        yield c


def login(client, email: str) -> dict:
    r = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture()
def admin(client):
    return login(client, "admin@example.com")


@pytest.fixture()
def employee(client):
    return login(client, "rohan@example.com")


@pytest.fixture()
def employee2(client):
    return login(client, "neha@example.com")


def service_id(client, headers, name: str) -> int:
    meta = client.get("/api/meta", headers=headers).json()
    return next(s["id"] for s in meta["services"] if s["name"] == name)
