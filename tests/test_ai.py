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
    assert result["report"] == REPORT


def test_enrichment_calls_configured_model_with_bounded_report():
    class FakeResponses:
        def __init__(self):
            self.kwargs = None

        def create(self, **kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(output_text='{"root_cause":"Clock skew","next_steps":["Sync clocks"]}')

    responses = FakeResponses()
    client = SimpleNamespace(responses=responses)

    result = enrich_report(REPORT, api_key="test-key", client=client, model="gpt-5.6")

    assert result["ai_used"] is True
    assert result["ai_analysis"]["root_cause"] == "Clock skew"
    assert responses.kwargs["model"] == "gpt-5.6"
    assert "TF timing mismatch" in responses.kwargs["input"]
    assert "test-key" not in responses.kwargs["input"]


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
    assert "invalid" in result["ai_error"].lower()
