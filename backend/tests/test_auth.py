import os
from pathlib import Path

os.environ["APP_ENV"] = "development"
os.environ["SECRET_KEY"] = "test-secret-key-that-is-long-enough-for-tests"
os.environ["DATABASE_URL"] = f"sqlite:///{(Path(__file__).resolve().parents[1] / 'test-lifeos.db').as_posix()}"

import pytest
from fastapi.testclient import TestClient

from backend.main import Base, engine, app

ORIGIN = "http://localhost:5500"
HEADERS = {"Origin": ORIGIN}
EMPTY_DATA = {
    "tasks": [],
    "habits": [],
    "goals": [],
    "events": [],
    "notes": [],
    "transactions": [],
    "wellness": [],
    "budgets": {"Food": 500},
}


@pytest.fixture
def client():
    Base.metadata.drop_all(bind=engine)
    with TestClient(app) as test_client:
        yield test_client
    Base.metadata.drop_all(bind=engine)


def register(client: TestClient, email: str) -> dict:
    response = client.post(
        "/api/auth/register",
        headers=HEADERS,
        json={"display_name": "Test User", "email": email, "password": "a-very-long-test-password"},
    )
    assert response.status_code == 201
    return response.json()


def auth_headers(token: str) -> dict[str, str]:
    return {**HEADERS, "Authorization": f"Bearer {token}"}


def test_registration_login_and_password_hash_are_private(client: TestClient):
    response = client.post(
        "/api/auth/register",
        headers=HEADERS,
        json={"display_name": "Test User", "email": "Person@example.com", "password": "a-very-long-test-password"},
    )
    assert response.status_code == 201
    created = response.json()
    assert created["user"]["email"] == "person@example.com"
    assert "password" not in created["user"]
    assert "httponly" in response.headers["set-cookie"].lower()

    duplicate = client.post(
        "/api/auth/register",
        headers=HEADERS,
        json={"display_name": "Other Person", "email": "person@example.com", "password": "a-very-long-test-password"},
    )
    assert duplicate.status_code == 409

    login = client.post(
        "/api/auth/login",
        headers=HEADERS,
        json={"email": "PERSON@example.com", "password": "a-very-long-test-password"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["id"] == created["user"]["id"]

    invalid_login = client.post(
        "/api/auth/login",
        headers=HEADERS,
        json={"email": "person@example.com", "password": "wrong-password"},
    )
    assert invalid_login.status_code == 401


def test_workspace_is_private_between_accounts(client: TestClient):
    person_a = register(client, "a@example.com")
    person_b = register(client, "b@example.com")

    saved = client.put(
        "/api/data",
        headers=auth_headers(person_a["access_token"]),
        json={"data": {**EMPTY_DATA, "notes": [{"id": "private", "title": "A private note"}]}},
    )
    assert saved.status_code == 200

    data_a = client.get("/api/data", headers=auth_headers(person_a["access_token"]))
    data_b = client.get("/api/data", headers=auth_headers(person_b["access_token"]))
    assert data_a.json()["data"]["notes"][0]["title"] == "A private note"
    assert data_b.json() == {"data": None}


def test_workspace_requires_auth_and_rejects_invalid_shape(client: TestClient):
    assert client.get("/api/data", headers=HEADERS).status_code == 401
    user = register(client, "shape@example.com")
    invalid = client.put(
        "/api/data",
        headers=auth_headers(user["access_token"]),
        json={"data": {"notes": []}},
    )
    assert invalid.status_code == 422


def test_refresh_rotates_cookie_and_logout_revokes_access(client: TestClient):
    registered = register(client, "session@example.com")
    original_cookie = client.cookies.get("lifeos_refresh")
    old_access_token = registered["access_token"]

    refreshed = client.post(
        "/api/auth/refresh",
        headers={**HEADERS, "X-LifeOS-Request": "1"},
    )
    assert refreshed.status_code == 200
    assert client.cookies.get("lifeos_refresh") != original_cookie

    missing_csrf_header = client.post("/api/auth/refresh", headers=HEADERS)
    assert missing_csrf_header.status_code == 403

    logout = client.post(
        "/api/auth/logout",
        headers={**HEADERS, "X-LifeOS-Request": "1"},
    )
    assert logout.status_code == 204
    assert client.get("/api/auth/me", headers=auth_headers(refreshed.json()["access_token"])).status_code == 401
    assert client.get("/api/auth/me", headers=auth_headers(old_access_token)).status_code == 401


def test_mutations_require_an_allowed_browser_origin(client: TestClient):
    untrusted = client.post(
        "/api/auth/register",
        headers={"Origin": "https://not-lifeos.example"},
        json={"display_name": "Other User", "email": "other@example.com", "password": "a-very-long-test-password"},
    )
    assert untrusted.status_code == 403
