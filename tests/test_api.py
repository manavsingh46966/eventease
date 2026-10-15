import os, sys, tempfile
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "t.db")
os.environ["ADMIN_KEY"] = "test-key"
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from fastapi.testclient import TestClient
from main import app, limiter

H = {"X-Admin-Key": "test-key"}


@pytest.fixture(autouse=True)
def reset_limits():
    limiter.reset()


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def make_event(client, seats=2):
    r = client.post("/api/admin/events", headers=H, json={
        "title": "Hack Night", "date": "2026-11-01", "venue": "Lab 3", "total_seats": seats})
    assert r.status_code == 201
    return r.json()["id"]


def test_admin_requires_key(client):
    r = client.post("/api/admin/events", json={})
    assert r.status_code == 401
    r = client.post("/api/admin/events", headers={"X-Admin-Key": "wrong"}, json={})
    assert r.status_code == 401


def test_register_and_seat_count(client):
    eid = make_event(client, 2)
    r = client.post(f"/api/events/{eid}/register", json={"name": "Asha Rao", "roll_no": "cs101"})
    assert r.status_code == 201 and r.json()["seats_left"] == 1
    ev = [e for e in client.get("/api/events").json() if e["id"] == eid][0]
    assert ev["seats_left"] == 1


def test_duplicate_rejected(client):
    eid = make_event(client, 5)
    body = {"name": "Ravi K", "roll_no": "CS202"}
    assert client.post(f"/api/events/{eid}/register", json=body).status_code == 201
    r = client.post(f"/api/events/{eid}/register", json={"name": "Ravi K", "roll_no": "cs202"})
    assert r.status_code == 409


def test_full_event_rejected(client):
    eid = make_event(client, 1)
    assert client.post(f"/api/events/{eid}/register", json={"name": "A One", "roll_no": "R001"}).status_code == 201
    r = client.post(f"/api/events/{eid}/register", json={"name": "B Two", "roll_no": "R002"})
    assert r.status_code == 409 and "full" in r.json()["detail"]


def test_validation(client):
    eid = make_event(client)
    assert client.post(f"/api/events/{eid}/register", json={"name": "<script>", "roll_no": "R1234"}).status_code == 422
    assert client.post(f"/api/events/{eid}/register", json={"name": "Ok Name", "roll_no": "a b!"}).status_code == 422
    assert client.post("/api/events/9999/register", json={"name": "Ok Name", "roll_no": "R1234"}).status_code == 404


def test_rate_limit_returns_429(client):
    eid = make_event(client, 50)
    codes = [client.post(f"/api/events/{eid}/register",
                         json={"name": "Spam Bot", "roll_no": f"BOT{i}"}).status_code for i in range(8)]
    assert codes[:5] == [201] * 5
    assert 429 in codes[5:]


def test_security_headers(client):
    r = client.get("/api/events")
    assert "max-age" in r.headers["strict-transport-security"]
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["cache-control"] == "no-store"
    assert "x-served-by" in r.headers


def test_admin_list_and_delete(client):
    eid = make_event(client)
    client.post(f"/api/events/{eid}/register", json={"name": "Meera S", "roll_no": "EC300"})
    regs = client.get(f"/api/admin/events/{eid}/registrations", headers=H).json()
    assert regs[0]["roll_no"] == "EC300"
    assert client.delete(f"/api/admin/events/{eid}", headers=H).status_code == 200


def test_frontend_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "EventEase" in r.text
