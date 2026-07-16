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
