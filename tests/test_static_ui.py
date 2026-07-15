from pathlib import Path


STATIC_DIR = Path(__file__).parents[1] / "src" / "ros_trace_ai" / "static"


def test_ui_has_dedicated_ai_result_region():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    assert 'id="ai-panel"' in html
    assert 'id="ai-root-cause"' in html
    assert 'id="ai-next-steps"' in html
    assert 'id="ai-confidence"' in html
    assert 'id="ai-status-detail"' in html


def test_browser_render_targets_ai_contract_fields():
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert "function renderAiAnalysis" in script
    assert "payload.ai.analysis" in script
    assert "analysis.root_cause" in script
    assert "analysis.next_steps" in script
    assert "analysis.confidence" in script
    assert "ai-status-detail" in script
