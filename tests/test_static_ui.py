from pathlib import Path


STATIC_DIR = Path(__file__).parents[1] / "src" / "ros_trace_ai" / "static"


def test_ui_reports_real_ai_availability_and_privacy_boundary():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert 'id="model-status"' in html
    assert 'id="ai-toggle-detail"' in html
    assert "structured diagnostic context" in html
    assert "async function loadCapabilities" in script
    assert 'fetch("/api/capabilities")' in script


def test_ui_has_dedicated_ai_result_region():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    assert 'id="ai-panel"' in html
    assert 'id="ai-root-cause"' in html
    assert 'id="ai-next-steps"' in html
    assert 'id="ai-confidence"' in html
    assert 'id="ai-status-detail"' in html


def test_incident_cards_are_evidence_first_and_labeled():
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert "Likely cause" in script
    assert "Recommended action" in script
    assert "Primary evidence" in script
    assert "first_timestamp" in script
    assert "last_timestamp" in script


def test_ui_supports_focus_transfer_and_reduced_motion():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    styles = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")

    assert 'id="results-title" tabindex="-1"' in html
    assert '$("results-title").focus' in script
    assert ":focus-visible" in styles
    assert "prefers-reduced-motion" in styles


def test_ui_uses_response_model_name_for_enrichment_status():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert "GPT-5.6 ENRICHED" not in script
    assert "GPT-5.6 assessment" not in html
    assert 'id="ai-title"' in html
    assert '$("ai-title").textContent' in script
    assert "payload.ai.model" in script
    assert "verify before acting" in script.lower()


def test_ui_handles_clipboard_failure_without_unhandled_rejection():
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert "Clipboard unavailable" in script
    assert "navigator.clipboard.writeText" in script


def test_browser_render_targets_ai_contract_fields():
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert "function renderAiAnalysis" in script
    assert "payload.ai.analysis" in script
    assert "analysis.root_cause" in script
    assert "analysis.next_steps" in script
    assert "analysis.confidence" in script
    assert "ai-status-detail" in script


def test_ui_can_export_the_complete_analysis_as_json():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert 'id="export-button"' in html
    assert "function exportAnalysis" in script
    assert "application/json" in script
    assert "ros-trace-report.json" in script


def test_empty_state_offers_one_click_sample_analysis():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert "Run sample analysis" in html
    assert "async function runSampleAnalysis" in script
    assert '$("empty-sample-button").addEventListener("click", runSampleAnalysis)' in script
