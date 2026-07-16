import asyncio

from fastapi.testclient import TestClient

from ros_trace_ai.app import MAX_LOG_LINES, RequestBodyLimitMiddleware, app


client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "ros-trace-ai"}


def test_capabilities_report_ai_availability(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    offline = client.get("/api/capabilities")

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    configured = client.get("/api/capabilities")

    assert offline.status_code == 200
    assert offline.json() == {
        "offline_available": True,
        "ai_available": False,
        "model": "gpt-5.6",
    }
    assert configured.json()["ai_available"] is True


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


def test_analyze_rejects_http_body_before_model_validation():
    marker = "oversized-private-marker"
    response = client.post(
        "/api/analyze",
        json={"log_text": marker + ("x" * 2_000_000), "use_ai": False},
    )

    assert response.status_code == 413
    assert len(response.content) < 1_000
    assert marker not in response.text


def test_analyze_rejects_chunked_http_body():
    def body_chunks():
        yield b'{"log_text":"'
        yield b"x" * 600_000
        yield b"x" * 600_000
        yield b'","use_ai":false}'

    response = client.post(
        "/api/analyze",
        content=body_chunks(),
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 413
    assert len(response.content) < 1_000


def test_body_limit_middleware_propagates_disconnect_without_replaying_request():
    async def exercise(messages):
        seen = []

        async def downstream(_scope, receive, _send):
            seen.append(await receive())

        queue = iter(messages)

        async def receive():
            return next(queue)

        async def send(_message):
            return None

        middleware = RequestBodyLimitMiddleware(downstream, max_bytes=100)
        scope = {"type": "http", "method": "POST", "headers": []}
        await middleware(scope, receive, send)
        return seen

    for messages in (
        [{"type": "http.disconnect"}],
        [
            {"type": "http.request", "body": b"partial", "more_body": True},
            {"type": "http.disconnect"},
        ],
    ):
        seen = asyncio.run(exercise(messages))
        assert seen == [{"type": "http.disconnect"}]


def test_analyze_rejects_empty_or_oversized_logs():
    empty = client.post("/api/analyze", json={"log_text": "  ", "use_ai": False})
    oversized = client.post(
        "/api/analyze", json={"log_text": "x" * 1_000_001, "use_ai": False}
    )

    assert empty.status_code == 422
    assert oversized.status_code == 422


def test_analyze_rejects_excessive_lines_without_reflecting_input():
    marker = "private-log-marker"
    log_text = "\n".join([marker] + ["x"] * MAX_LOG_LINES)

    response = client.post(
        "/api/analyze", json={"log_text": log_text, "use_ai": False}
    )

    assert response.status_code == 422
    assert len(response.content) < 2_000
    assert marker not in response.text


def test_analyze_line_limit_uses_parser_line_boundaries():
    for separator in ("\r", "\v", "\f", "\u2028"):
        log_text = separator.join(["x"] * (MAX_LOG_LINES + 1))

        response = client.post(
            "/api/analyze", json={"log_text": log_text, "use_ai": False}
        )

        assert response.status_code == 422
