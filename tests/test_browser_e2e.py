import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright


PROJECT_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def live_server():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "ros_trace_ai.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=PROJECT_DIR,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    base_url = f"http://127.0.0.1:{port}"

    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(f"{base_url}/health", timeout=0.5) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("test server did not become healthy within 10 seconds")
        yield base_url
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def test_sample_analysis_journey_renders_and_exports_report(live_server):
    console_errors = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(accept_downloads=True)
            page.on(
                "console",
                lambda message: console_errors.append(message.text)
                if message.type == "error"
                else None,
            )
            page.on("pageerror", lambda error: console_errors.append(str(error)))

            page.goto(live_server)
            expect(page.get_by_text("AI: KEY REQUIRED")).to_be_visible()
            expect(
                page.get_by_role("checkbox", name="AI enrichment")
            ).to_be_disabled()

            page.get_by_role("button", name="Run sample analysis").click()

            expect(page.locator("#analysis-state")).to_have_text("OFFLINE COMPLETE")
            expect(page.locator(".incident-card")).to_have_count(5)
            expect(page.locator("#results-title")).to_be_focused()

            with page.expect_download() as download_info:
                page.get_by_role("button", name="Export JSON").click()
            download = download_info.value
            report = json.loads(Path(download.path()).read_text(encoding="utf-8"))

            assert download.suggested_filename == "ros-trace-report.json"
            assert report["report"]["summary"]["incident_count"] == 5
            assert len(report["report"]["incidents"]) == 5
            first_incident = report["report"]["incidents"][0]
            assert first_incident["title"]
            assert first_incident["root_cause"]
            assert first_incident["evidence"]
            assert report["ai_used"] is False
            assert console_errors == []
        finally:
            browser.close()


def test_markdown_export_is_human_readable(live_server):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(accept_downloads=True)
            page.set_viewport_size({"width": 390, "height": 844})
            page.goto(live_server)
            page.get_by_role("button", name="Run sample analysis").click()
            expect(page.locator("#analysis-state")).to_have_text("OFFLINE COMPLETE")
            expect(page.get_by_role("button", name="Export Markdown")).to_be_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

            with page.expect_download() as download_info:
                page.get_by_role("button", name="Export Markdown").click()
            download = download_info.value
            markdown = Path(download.path()).read_text(encoding="utf-8")

            assert download.suggested_filename == "ros-trace-report.md"
            assert markdown.startswith("# ROS Trace Diagnostic Report\n")
            assert "- **Incidents:** 5" in markdown
            assert "## Incident 1 — Control loop missed its target rate" in markdown
            assert "- **Severity:** WARN" in markdown
            assert "### Likely cause" in markdown
            assert "### Evidence" in markdown
            assert "Costmap update loop missed its desired rate" in markdown
            assert "### Recommended action" in markdown
        finally:
            browser.close()


def test_markdown_export_escapes_untrusted_content(live_server):
    payload = {
        "ai_used": False,
        "report": {
            "summary": {
                "incident_count": 1,
                "incidents_omitted": 2,
                "entries_omitted": 3,
                "severity_counts": {},
            },
            "incidents": [
                {
                    "title": "# forged heading",
                    "severity": "ERROR",
                    "root_cause": "<script>alert(1)</script>",
                    "recommendation": "- delete everything",
                    "evidence": [{"raw": "[click](javascript:alert(1))"}],
                }
            ],
        },
    }

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(live_server)
            markdown = page.evaluate(
                "payload => buildMarkdownReport(payload)", payload
            )

            assert "<script>" not in markdown
            assert "&lt;script&gt;alert\\(1\\)&lt;/script&gt;" in markdown
            assert "\\# forged heading" in markdown
            assert "\\[click\\]\\(javascript:alert\\(1\\)\\)" in markdown
            assert "\\- delete everything" in markdown
            assert "- **Incidents omitted:** 2" in markdown
            assert "- **Raw entries omitted:** 3" in markdown
        finally:
            browser.close()
