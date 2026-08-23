from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_engines_default_is_auto() -> None:
    response = client.get("/api/v1/engines")
    assert response.status_code == 200
    body = response.json()
    assert body["default"] == "auto"
    ids = [item["id"] for item in body["engines"]]
    assert ids == ["auto", "native", "paddleocr"]


def test_create_job_returns_immediately() -> None:
    response = client.post(
        "/api/v1/jobs",
        files={"file": ("note.pdf", b"%PDF-1.1\n", "application/pdf")},
        data={"engine": "auto", "language": "ru"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"queued", "preparing", "triaging", "running", "failed", "completed"}
    assert "id" in body


def test_rejects_unsupported_file() -> None:
    response = client.post(
        "/api/v1/jobs",
        files={"file": ("note.txt", b"hello", "text/plain")},
        data={"engine": "auto", "language": "ru"},
    )
    assert response.status_code == 415
