"""FastAPI application for ROS-Trace AI."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from .ai import enrich_report
from .analyzer import analyze_log

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parents[1]
STATIC_DIR = PACKAGE_DIR / "static"
SAMPLE_FILE = PROJECT_DIR / "samples" / "navigation_failure.log"

app = FastAPI(
    title="ROS-Trace AI",
    description="Evidence-backed ROS log triage with optional GPT-5.6 enrichment.",
    version="0.1.0",
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class AnalyzeRequest(BaseModel):
    log_text: str = Field(max_length=1_000_000)
    use_ai: bool = False

    @field_validator("log_text")
    @classmethod
    def log_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("log_text must not be blank")
        return value


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "ros-trace-ai"}


@app.get("/api/sample")
def sample() -> dict[str, str]:
    return {
        "name": SAMPLE_FILE.name,
        "log_text": SAMPLE_FILE.read_text(encoding="utf-8"),
    }


@app.post("/api/analyze")
def analyze(request: AnalyzeRequest) -> dict:
    report = analyze_log(request.log_text)
    api_key = os.getenv("OPENAI_API_KEY") if request.use_ai else None
    model = os.getenv("OPENAI_MODEL", "gpt-5.6")
    return enrich_report(report, api_key=api_key, model=model, requested=request.use_ai)


def run() -> None:
    import uvicorn

    uvicorn.run("ros_trace_ai.app:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    run()
