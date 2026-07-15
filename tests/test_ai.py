import json
from types import SimpleNamespace

from ros_trace_ai.ai import enrich_report


REPORT = {
    "summary": {"errors": 2, "warnings": 1, "nodes": 2, "incidents": 1},
    "incidents": [
        {
            "title": "TF timing mismatch",
            "severity": "ERROR",
            "evidence": ["Lookup would require extrapolation"],
            "recommendations": ["Check clock synchronization"],
        }
    ],
}


def test_enrichment_stays_offline_without_api_key():
    result = enrich_report(REPORT, api_key=None)

    assert result["ai_used"] is False
    assert result["ai_analysis"] is None
    assert result["ai"]["status"] == "not_requested"
    assert result["ai"]["analysis"] is None
    assert result["report"] == REPORT


def test_enrichment_calls_configured_model_with_bounded_report():
    class FakeResponses:
        def __init__(self):
            self.kwargs = None

        def create(self, **kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(
                output_text='{"root_cause":"Clock skew","next_steps":["Sync clocks"],"confidence":0.82}'
            )

    responses = FakeResponses()
    client = SimpleNamespace(responses=responses)

    result = enrich_report(REPORT, api_key="test-key", client=client, model="gpt-5.6")

    assert result["ai_used"] is True
    assert result["ai_analysis"]["root_cause"] == "Clock skew"
    assert result["ai_analysis"] == {
        "root_cause": "Clock skew",
        "next_steps": ["Sync clocks"],
        "confidence": 0.82,
    }
    assert result["ai"] == {
        "requested": True,
        "used": True,
        "status": "succeeded",
        "model": "gpt-5.6",
        "analysis": result["ai_analysis"],
        "error": None,
    }
    assert responses.kwargs["model"] == "gpt-5.6"
    assert "TF timing mismatch" in responses.kwargs["input"]
    assert "test-key" not in responses.kwargs["input"]


def test_model_input_is_redacted_and_bounded():
    long_secret = "sk-" + ("a" * 120)
    report = {
        "summary": REPORT["summary"],
        "incidents": [
            {
                "title": "Authentication failed",
                "severity": "ERROR",
                "node": "nav",
                "message": f"failed with token {long_secret} password=hunter2",
                "root_cause": "Bad credential",
                "recommendation": "Rotate credentials",
                "evidence": [
                    {
                        "line_number": index,
                        "raw": f"[ERROR] secret={long_secret} password=hunter2 payload {'x' * 400}",
                        "message": "credential failure",
                    }
                    for index in range(1, 50)
                ],
            }
        ],
        "entries": [
            {"line_number": index, "raw": "x" * 500, "message": "x" * 500}
            for index in range(1, 200)
        ],
    }

    class FakeResponses:
        def __init__(self):
            self.kwargs = None

        def create(self, **kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(
                output_text='{"root_cause":"Credential leak","next_steps":["Rotate key"],"confidence":0.7}'
            )

    responses = FakeResponses()
    result = enrich_report(
        report,
        api_key="test-key",
        client=SimpleNamespace(responses=responses),
        max_prompt_chars=2_200,
    )

    assert result["ai"]["status"] == "succeeded"
    prompt = responses.kwargs["input"]
    assert len(prompt) <= 2_200
    assert long_secret not in prompt
    assert "hunter2" not in prompt
    assert "[REDACTED]" in prompt
    assert '"entries"' not in prompt


def test_invalid_model_schema_falls_back_without_losing_report():
    client = SimpleNamespace(
        responses=SimpleNamespace(
            create=lambda **_: SimpleNamespace(
                output_text=json.dumps(
                    {
                        "root_cause": "",
                        "next_steps": ["x" * 500],
                        "confidence": 1.7,
                        "extra": "not allowed",
                    }
                )
            )
        )
    )

    result = enrich_report(REPORT, api_key="test-key", client=client)

    assert result["ai_used"] is False
    assert result["ai_analysis"] is None
    assert result["report"] == REPORT
    assert result["ai"]["status"] == "invalid_response"
    assert "Invalid model response" in result["ai"]["error"]


def test_invalid_model_output_falls_back_without_losing_report():
    client = SimpleNamespace(
        responses=SimpleNamespace(
            create=lambda **_: SimpleNamespace(output_text="not-json")
        )
    )

    result = enrich_report(REPORT, api_key="test-key", client=client)

    assert result["ai_used"] is False
    assert result["ai_analysis"] is None
    assert result["report"] == REPORT
    assert result["ai"]["status"] == "invalid_response"
    assert result["ai"]["analysis"] is None
    assert "invalid" in result["ai_error"].lower()


def test_provider_failure_reports_unavailable_status():
    def fail(**_):
        raise RuntimeError("network down")

    client = SimpleNamespace(responses=SimpleNamespace(create=fail))

    result = enrich_report(REPORT, api_key="test-key", client=client)

    assert result["ai_used"] is False
    assert result["ai"]["status"] == "unavailable"
    assert result["ai"]["error"] == "AI enrichment unavailable: network down"
    assert result["report"] == REPORT
