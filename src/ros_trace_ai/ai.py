"""Optional GPT-5.6 enrichment for deterministic ROS analysis reports."""

from __future__ import annotations

import json
from typing import Any

from openai import OpenAI


def _prompt_for(report: dict[str, Any]) -> str:
    compact = json.dumps(report, ensure_ascii=False, separators=(",", ":"))
    return (
        "You are a senior ROS reliability engineer. Analyze the deterministic "
        "triage report below. Return JSON only with keys root_cause (string), "
        "next_steps (array of short commands/actions), and confidence "
        "(number from 0 to 1). Do not invent evidence.\nREPORT:\n" + compact
    )


def enrich_report(
    report: dict[str, Any],
    *,
    api_key: str | None,
    client: Any | None = None,
    model: str = "gpt-5.6",
) -> dict[str, Any]:
    """Return the report plus optional structured GPT enrichment.

    Offline mode is the default. The caller must explicitly supply an API key;
    the key is used only to construct the SDK client and is never included in
    the model prompt or returned payload.
    """

    result: dict[str, Any] = {
        "report": report,
        "ai_used": False,
        "ai_analysis": None,
    }
    if not api_key:
        return result

    sdk = client or OpenAI(api_key=api_key)
    try:
        response = sdk.responses.create(
            model=model,
            input=_prompt_for(report),
        )
        parsed = json.loads(response.output_text)
        if not isinstance(parsed, dict):
            raise ValueError("model output is not a JSON object")
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        result["ai_error"] = f"Invalid model response: {exc}"
        return result
    except Exception as exc:  # Network/provider failures should preserve offline analysis.
        result["ai_error"] = f"AI enrichment unavailable: {exc}"
        return result

    result["ai_used"] = True
    result["ai_analysis"] = parsed
    return result
