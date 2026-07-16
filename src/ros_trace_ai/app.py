"""FastAPI application for ROS-Trace AI."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from .ai import enrich_report
from .analyzer import analyze_log

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parents[1]
STATIC_DIR = PACKAGE_DIR / "static"
SAMPLE_FILE = PROJECT_DIR / "samples" / "navigation_failure.log"
MAX_LOG_LINES = 20_000
MAX_REQUEST_BODY_BYTES = 1_100_000


class RequestBodyLimitMiddleware:
    """Reject oversized HTTP bodies before JSON parsing or model validation."""

    def __init__(self, app, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or scope.get("method") not in {
            "POST",
            "PUT",
            "PATCH",
        }:
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        content_length = headers.get(b"content-length")
        if content_length:
            try:
                if int(content_length) > self.max_bytes:
                    await JSONResponse(
                        status_code=413, content={"detail": "Request body too large"}
                    )(scope, receive, send)
                    return
            except ValueError:
                pass

        received = 0
        body_parts: list[bytes] = []
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":

                async def replay_disconnect():
                    return message

                await self.app(scope, replay_disconnect, send)
                return
            if message["type"] != "http.request":
                await self.app(scope, receive, send)
                return
            chunk = message.get("body", b"")
            received += len(chunk)
            if received > self.max_bytes:
                await JSONResponse(
                    status_code=413, content={"detail": "Request body too large"}
                )(scope, receive, send)
                return
            body_parts.append(chunk)
            if not message.get("more_body", False):
                break

        body = b"".join(body_parts)
        replayed = False

        async def replay_receive():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        await self.app(scope, replay_receive, send)


app = FastAPI(
    title="ROS-Trace AI",
    description="Evidence-backed ROS log triage with optional GPT-5.6 enrichment.",
    version="0.1.0",
)
app.add_middleware(RequestBodyLimitMiddleware, max_bytes=MAX_REQUEST_BODY_BYTES)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.exception_handler(RequestValidationError)
async def sanitized_validation_error(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    detail = [
        {"loc": error.get("loc"), "type": error.get("type"), "msg": error.get("msg")}
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": detail})


class AnalyzeRequest(BaseModel):
    log_text: str = Field(max_length=1_000_000)
    use_ai: bool = False

    @field_validator("log_text")
    @classmethod
    def log_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("log_text must not be blank")
        if len(value.splitlines()) > MAX_LOG_LINES:
            raise ValueError(f"log_text must not exceed {MAX_LOG_LINES} lines")
        return value


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "ros-trace-ai"}


@app.get("/api/capabilities")
def capabilities() -> dict[str, bool | str]:
    return {
        "offline_available": True,
        "ai_available": bool(os.getenv("OPENAI_API_KEY")),
        "model": os.getenv("OPENAI_MODEL", "gpt-5.6"),
    }


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
