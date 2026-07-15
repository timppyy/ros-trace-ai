from fastapi.testclient import TestClient

from ros_trace_ai.app import app


client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "ros-trace-ai"}


def test_root_serves_web_interface():
    response = client.get("/")
    assert response.status_code == 200
    assert "ROS-TRACE" in response.text
    assert "Analyze trace" in response.text


def test_sample_endpoint_returns_navigation_log():
    response = client.get("/api/sample")
    assert response.status_code == 200
    payload = response.json()
    assert "log_text" in payload
    assert "extrapolation" in payload["log_text"]


def test_analyze_endpoint_returns_offline_report():
    response = client.post(
        "/api/analyze",
        json={
            "log_text": "[ERROR] [1712345678.1] [nav]: Action server timed out",
            "use_ai": False,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ai_used"] is False
    assert payload["ai"] == {
        "requested": False,
        "used": False,
        "status": "not_requested",
        "model": "gpt-5.6",
        "analysis": None,
        "error": None,
    }
    assert payload["report"]["summary"]["severity_counts"]["ERROR"] == 1
    assert payload["report"]["incidents"][0]["kind"] == "timeout"


def test_analyze_endpoint_exposes_missing_key_status(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    response = client.post(
        "/api/analyze",
        json={
            "log_text": "[ERROR] [1712345678.1] [nav]: Action server timed out",
            "use_ai": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ai_used"] is False
    assert payload["ai_error"] == "AI enrichment requested but OPENAI_API_KEY is not configured."
    assert payload["ai"]["requested"] is True
    assert payload["ai"]["status"] == "missing_api_key"
    assert payload["ai"]["error"] == payload["ai_error"]
    assert payload["report"]["incidents"][0]["kind"] == "timeout"


def test_analyze_rejects_empty_or_oversized_logs():
    empty = client.post("/api/analyze", json={"log_text": "  ", "use_ai": False})
    oversized = client.post(
        "/api/analyze", json={"log_text": "x" * 1_000_001, "use_ai": False}
    )

    assert empty.status_code == 422
    assert oversized.status_code == 422
