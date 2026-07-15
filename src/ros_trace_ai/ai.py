"""Optional GPT-5.6 enrichment for deterministic ROS analysis reports."""

from __future__ import annotations

import json
import re
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


DEFAULT_MAX_PROMPT_CHARS = 12_000
MAX_INCIDENTS_FOR_AI = 8
MAX_EVIDENCE_PER_INCIDENT = 3
MAX_TEXT_FIELD_CHARS = 600

_SECRET_PATTERNS = (
    re.compile(
        r"(?i)\bauthorization\s*[:=]\s*(?:basic|bearer)\s+[^\s,;]+"
    ),
    re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^@\s/]+@"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(
        r"(?i)\b(password|passwd|token|secret|api[_-]?key|authorization)\s*[:=]\s*[^\s,;]+"
    ),
    re.compile(
        r"(?i)\b(token|secret|api[_-]?key)\s+(?:is\s+)?[A-Za-z0-9._~+/=-]{16,}\b"
    ),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}"),
)


class AIAnalysis(BaseModel):
    """Stable structured model response accepted by the application."""

    model_config = ConfigDict(extra="forbid")

    root_cause: str = Field(min_length=1, max_length=1_200)
    next_steps: list[str] = Field(min_length=1, max_length=6)
    confidence: float = Field(ge=0, le=1)

    @field_validator("root_cause")
    @classmethod
    def root_cause_must_have_signal(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("root_cause must not be blank")
        return value

    @field_validator("next_steps")
    @classmethod
    def next_steps_must_be_short_actions(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item and item.strip()]
        if not cleaned:
            raise ValueError("next_steps must include at least one action")
        too_long = [item for item in cleaned if len(item) > 180]
        if too_long:
            raise ValueError("next_steps must be short actions")
        return cleaned


def _redact_text(value: str) -> str:
    redacted = value
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    if len(redacted) > MAX_TEXT_FIELD_CHARS:
        return redacted[: MAX_TEXT_FIELD_CHARS - 15].rstrip() + " ...[truncated]"
    return redacted


def _safe_value(value: Any) -> Any:
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, list):
        return [_safe_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _safe_value(item) for key, item in value.items()}
    return value


def _bounded_incident(incident: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = (
        "id",
        "kind",
        "title",
        "severity",
        "node",
        "message",
        "count",
        "first_timestamp",
        "last_timestamp",
        "root_cause",
        "recommendation",
    )
    bounded = {key: incident.get(key) for key in allowed_keys if key in incident}
    evidence = incident.get("evidence") or []
    if isinstance(evidence, list):
        bounded["evidence"] = [
            _safe_value(item) for item in evidence[:MAX_EVIDENCE_PER_INCIDENT]
        ]
        bounded["evidence_omitted"] = max(0, len(evidence) - MAX_EVIDENCE_PER_INCIDENT)
    return _safe_value(bounded)


def _report_for_model(report: dict[str, Any]) -> dict[str, Any]:
    incidents = report.get("incidents") or []
    if not isinstance(incidents, list):
        incidents = []
    return {
        "summary": _safe_value(report.get("summary") or {}),
        "incidents": [
            _bounded_incident(incident)
            for incident in incidents[:MAX_INCIDENTS_FOR_AI]
            if isinstance(incident, dict)
        ],
        "limits": {
            "entries_omitted": True,
            "incident_limit": MAX_INCIDENTS_FOR_AI,
            "incidents_omitted": max(0, len(incidents) - MAX_INCIDENTS_FOR_AI),
            "evidence_per_incident": MAX_EVIDENCE_PER_INCIDENT,
        },
    }


def _compact_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _trim_prompt_payload(payload: dict[str, Any], max_chars: int, prefix_chars: int) -> str:
    compact = _compact_json(payload)
    if len(compact) + prefix_chars <= max_chars:
        return compact

    trimmed = dict(payload)
    incidents = list(trimmed.get("incidents") or [])
    while len(incidents) > 1:
        incidents.pop()
        trimmed["incidents"] = incidents
        trimmed["limits"] = {**trimmed["limits"], "prompt_truncated": True}
        compact = _compact_json(trimmed)
        if len(compact) + prefix_chars <= max_chars:
            return compact

    if incidents:
        incident = dict(incidents[0])
        incident.pop("evidence", None)
        incident["evidence_omitted"] = "all"
        trimmed["incidents"] = [incident]
        trimmed["limits"] = {**trimmed["limits"], "prompt_truncated": True}
        compact = _compact_json(trimmed)
        if len(compact) + prefix_chars <= max_chars:
            return compact

    minimal = {
        "summary": trimmed.get("summary", {}),
        "incidents": [],
        "limits": {**trimmed.get("limits", {}), "prompt_truncated": True},
    }
    compact = _compact_json(minimal)
    if len(compact) + prefix_chars <= max_chars:
        return compact

    summary = _compact_json({"summary": minimal["summary"]})
    payload_budget = max_chars - prefix_chars
    base = {
        "summary": {"truncated": ""},
        "incidents": [],
        "limits": {"prompt_truncated": True},
    }
    if payload_budget < 2:
        return ""
    if len(_compact_json(base)) > payload_budget:
        return "{}"

    low, high = 0, len(summary)
    best = _compact_json(base)
    while low <= high:
        midpoint = (low + high) // 2
        candidate = {
            **base,
            "summary": {"truncated": summary[:midpoint]},
        }
        serialized = _compact_json(candidate)
        if len(serialized) <= payload_budget:
            best = serialized
            low = midpoint + 1
        else:
            high = midpoint - 1
    return best


def _prompt_for(
    report: dict[str, Any], *, max_prompt_chars: int = DEFAULT_MAX_PROMPT_CHARS
) -> str:
    prefix = (
        "You are a senior ROS reliability engineer. Analyze the deterministic "
        "triage report below. Return JSON only with exactly these keys: "
        "root_cause (non-empty string), next_steps (1-6 short commands/actions), "
        "and confidence (number from 0 to 1). Do not invent evidence. "
        "Use only the provided incidents and evidence.\nREPORT:\n"
    )
    if max_prompt_chars < len(prefix) + 2:
        return "{}" if max_prompt_chars >= 2 else ""
    compact = _trim_prompt_payload(
        _report_for_model(report), max_prompt_chars, len(prefix)
    )
    return prefix + compact


def _ai_payload(
    *,
    requested: bool,
    used: bool,
    status: str,
    model: str,
    analysis: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "requested": requested,
        "used": used,
        "status": status,
        "model": model,
        "analysis": analysis,
        "error": error,
    }


def _base_result(report: dict[str, Any], *, requested: bool, model: str) -> dict[str, Any]:
    return {
        "report": report,
        "ai_used": False,
        "ai_analysis": None,
        "ai": _ai_payload(
            requested=requested,
            used=False,
            status="not_requested",
            model=model,
        ),
    }


def _parse_analysis(output_text: str) -> dict[str, Any]:
    parsed = json.loads(output_text)
    if not isinstance(parsed, dict):
        raise ValueError("model output is not a JSON object")
    return AIAnalysis.model_validate(parsed).model_dump()


def enrich_report(
    report: dict[str, Any],
    *,
    api_key: str | None,
    client: Any | None = None,
    model: str = "gpt-5.6",
    requested: bool = False,
    max_prompt_chars: int = DEFAULT_MAX_PROMPT_CHARS,
) -> dict[str, Any]:
    """Return the report plus optional structured GPT enrichment.

    Offline mode is the default. The caller must explicitly supply an API key;
    the key is used only to construct the SDK client and is never included in
    the model prompt or returned payload.
    """

    requested = requested or bool(api_key)
    result = _base_result(report, requested=requested, model=model)
    if not api_key:
        if requested:
            message = "AI enrichment requested but OPENAI_API_KEY is not configured."
            result["ai_error"] = message
            result["ai"] = _ai_payload(
                requested=True,
                used=False,
                status="missing_api_key",
                model=model,
                error=message,
            )
        return result

    try:
        sdk = client or OpenAI(api_key=api_key)
        response = sdk.responses.create(
            model=model,
            input=_prompt_for(report, max_prompt_chars=max_prompt_chars),
        )
        output_text = response.output_text
    except Exception:  # SDK/provider failures should preserve offline analysis.
        message = "AI enrichment is temporarily unavailable."
        result["ai_error"] = message
        result["ai"] = _ai_payload(
            requested=True,
            used=False,
            status="unavailable",
            model=model,
            error=message,
        )
        return result

    try:
        analysis = _parse_analysis(output_text)
    except (json.JSONDecodeError, TypeError, ValueError, ValidationError):
        message = "AI enrichment returned an invalid response."
        result["ai_error"] = message
        result["ai"] = _ai_payload(
            requested=True,
            used=False,
            status="invalid_response",
            model=model,
            error=message,
        )
        return result
    result["ai_used"] = True
    result["ai_analysis"] = analysis
    result["ai"] = _ai_payload(
        requested=True,
        used=True,
        status="succeeded",
        model=model,
        analysis=analysis,
    )
    return result
