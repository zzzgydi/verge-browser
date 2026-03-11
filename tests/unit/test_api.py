from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_healthz() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_and_get_sandbox() -> None:
    created = client.post("/sandboxes", json={"width": 1440, "height": 900})
    assert created.status_code == 201
    payload = created.json()
    sandbox_id = payload["id"]
    assert payload["browser"]["viewport"] == {"width": 1440, "height": 900}
    fetched = client.get(f"/sandboxes/{sandbox_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == sandbox_id
    assert fetched.json()["browser"]["viewport"] == {"width": 1440, "height": 900}


def test_vnc_ticket_requires_existing_sandbox() -> None:
    response = client.post("/sandboxes/sb_missing/vnc/tickets")
    assert response.status_code == 404
