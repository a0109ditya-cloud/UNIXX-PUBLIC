from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "genuine_440hz_4s.wav"


def test_health_endpoints(client: TestClient):
    live = client.get("/api/v1/health/live")
    ready = client.get("/api/v1/health/ready")
    assert live.status_code == 200
    assert ready.status_code == 200
    assert live.json()["status"] == "ok"


def test_user_registration_and_login(client: TestClient):
    payload = {"email": "alice@example.com", "password": "secretpass123", "name": "Alice"}
    register = client.post("/api/v1/auth/register", json=payload)
    assert register.status_code == 201, register.text
    body = register.json()
    assert body["email"] == payload["email"]
    assert "access_token" in body

    login = client.post("/api/v1/auth/login", json={"email": payload["email"], "password": payload["password"]})
    assert login.status_code == 200, login.text
    assert login.json()["access_token"]


def test_voice_upload_and_analysis(client: TestClient):
    auth = client.post(
        "/api/v1/auth/register",
        json={"email": "bob@example.com", "password": "secretpass123", "name": "Bob"},
    )
    token = auth.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    with FIXTURE.open("rb") as audio_file:
        upload = client.post(
            "/api/v1/voice/upload",
            headers=headers,
            files={"file": (FIXTURE.name, audio_file, "audio/wav")},
        )

    assert upload.status_code == 201, upload.text
    voice_file = upload.json()["voice_file"]
    analysis = client.post(f"/api/v1/voice/files/{voice_file['id']}/analyze", headers=headers)
    assert analysis.status_code == 200, analysis.text
    body = analysis.json()
    assert body["status"] in {"completed", "failed"}
    assert body["model_name"] in {"AASIST", "AASIST"}


def test_unauthorized_access(client: TestClient):
    response = client.get("/api/v1/users/me")
    assert response.status_code == 403
