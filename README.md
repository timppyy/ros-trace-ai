# ROS-Trace AI

> Turn noisy ROS logs into an incident timeline, evidence-backed root-cause hypotheses, and practical next steps—locally first, with optional GPT-5.6 enrichment.

**Hackathon category:** Developer Tools

<!-- SUBMISSION TODO: Replace every [PLACEHOLDER: ...] below before publishing. -->

- **Public repository:** https://github.com/timppyy/ros-trace-ai
- **Demo video (<3 minutes, public, with audio):** [PLACEHOLDER: public YouTube URL]
- **Live demo:** Not currently claimed; run the project locally using the instructions below.
- **Codex Session ID (`/feedback`):** [PLACEHOLDER: add the submitted Codex Session ID]
- **License:** See [`LICENSE`](LICENSE).

## Why ROS-Trace AI?

When a robot fails, the useful signal is often buried in interleaved logs from navigation, transforms, sensors, middleware, and application nodes. Searching those lines manually is slow, and sending operational logs to a hosted model is not always possible.

ROS-Trace AI provides a deterministic offline path that works without ROS and without an API key. It parses pasted or bundled ROS-style logs, groups related failures, surfaces supporting evidence, and proposes actionable checks. Teams that opt in can add GPT-5.6 enrichment for a clearer incident narrative while retaining the deterministic analysis as the baseline.

## What it does

- Accepts ROS log text through a no-build web interface.
- Includes a bundled navigation-failure sample for a fast judging path.
- Tolerates malformed or unstructured lines instead of failing the entire analysis.
- Parses common ROS1/ROS2-style records and summarizes severity counts.
- Groups repeated errors into incidents and builds a compact timeline.
- Applies deterministic rules to generate likely causes, evidence, and recommended actions.
- Runs fully offline by default—no ROS installation and no OpenAI key required.
- Optionally asks GPT-5.6 to enrich the deterministic result when an API key is explicitly configured.

> **Scope:** Suggested causes are diagnostic hypotheses, not guarantees. Validate recommendations against the robot, its safety procedures, and the complete system state before acting.

## Judge quick start

### Prerequisites

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/) (recommended)
- A modern browser
- Optional: an OpenAI API key for AI enrichment

### Install and run

```bash
git clone https://github.com/timppyy/ros-trace-ai.git
cd ros-trace-ai
uv sync
uv run uvicorn ros_trace_ai.app:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>.

If you already have the repository checked out, begin with `uv sync` in its root directory.

### 60-second judging path

1. Start the server and open the local URL above.
2. Choose **Load sample** to load the bundled navigation failure.
3. Run the analysis in the default offline mode.
4. Review the severity summary, ordered incident cards, cited log evidence, and suggested checks/commands.
5. Paste a malformed line or duplicate error into the input and analyze again to see tolerant parsing and repeated-event grouping.
6. Optionally enable GPT-5.6 as described below and compare the enriched explanation with the deterministic baseline.

No robot, ROS installation, cloud deployment, or API key is needed for steps 1–5.

## Optional GPT-5.6 enrichment

Set an API key only if you want model-assisted enrichment:

```bash
export OPENAI_API_KEY="your-key"
uv run uvicorn ros_trace_ai.app:app --host 127.0.0.1 --port 8000
```

Enable **AI enrichment** in the UI to request model-assisted analysis. Without `OPENAI_API_KEY`, the application remains in deterministic offline mode.

The intended AI boundary is narrow: deterministic code parses and groups the logs first; GPT-5.6 receives structured diagnostic context and improves prioritization and explanation. The offline result remains useful on its own. Do not paste secrets, credentials, or personally sensitive data into logs.

## Use your own log

Paste ROS console output into the text area (or use the UI's file input, if supported by your browser), then run the analyzer. Plain-text ROS1/ROS2-style output is the target input; malformed lines are retained as best-effort evidence where possible.

A bundled example is available at:

```text
samples/navigation_failure.log
```

This is a log analyzer, not a bag-file reader: convert binary `.bag`, `.db3`, or MCAP recordings to relevant text logs before analysis.

## API

The FastAPI service powers both the static interface and the analyzer. Once running, interactive endpoint documentation is available at:

- Swagger UI: <http://127.0.0.1:8000/docs>
- OpenAPI schema: <http://127.0.0.1:8000/openapi.json>

Use the generated schema as the authoritative request/response contract.

## How it works

```text
ROS text logs
    │
    ▼
Tolerant parser ──► normalized events + severity metrics
    │
    ▼
Deterministic grouping/rules ──► timeline + hypotheses + evidence + actions
    │
    ├──► Offline result (default)
    │
    └──► Optional GPT-5.6 enrichment (explicit opt-in)
                    │
                    ▼
             FastAPI JSON response
                    │
                    ▼
             Vanilla HTML/CSS/JS UI
```

### Design principles

1. **Offline first:** core diagnostics do not depend on a model or network connection.
2. **Evidence before prose:** every diagnosis should be traceable to parsed events.
3. **Graceful degradation:** malformed records and missing credentials should not break the default workflow.
4. **Actionable output:** recommended checks are more useful than an unranked log summary.
5. **Small deployment surface:** FastAPI plus a vanilla static UI avoids a separate frontend build.

## How Codex and GPT-5.6 were used

### Codex: engineering and product decisions

Codex was used as an implementation partner across the repository. The important decisions were not merely code generation:

- Made deterministic offline analysis the primary product rather than a fallback.
- Separated parsing, incident analysis, AI enrichment, API transport, and UI concerns so each layer can be tested independently.
- Defined behavior around malformed lines, repeated errors, known failure patterns, and absent API credentials before implementation.
- Kept the browser client build-free to shorten the judge setup path.
- Designed the demo around one bundled failure trace so evaluators can reach meaningful output immediately.
- Added testable boundaries around the optional OpenAI client instead of coupling network calls to parsing.

**Required submission metadata:** run `/feedback` in the Codex environment used for the project and paste the resulting Session ID here before submission:

```text
[PLACEHOLDER: Codex Session ID]
```

### GPT-5.6: optional runtime intelligence

GPT-5.6 is used only for opt-in enrichment of already structured diagnostic findings. Its role is to synthesize the timeline, prioritize hypotheses, and improve the clarity of next steps. It does not replace deterministic parsing, and the app remains demonstrable without a key.

The demo video should show both states and explain this division of responsibility aloud.

## Testing

Run the complete test suite from the repository root:

```bash
uv sync --extra dev
uv run pytest -v
```

Useful focused paths:

```bash
uv run pytest tests/test_analyzer.py -v
uv run pytest tests/test_ai.py -v
uv run pytest tests/test_api.py -v
```

Manual smoke test:

```bash
uv run uvicorn ros_trace_ai.app:app --host 127.0.0.1 --port 8000
```

Then open <http://127.0.0.1:8000>, load the sample, and run an offline analysis. This README intentionally does not claim a particular test result; evaluators can run the commands above against the submitted revision.

## Supported platforms

The application targets Python 3.11+ on Linux, macOS, and Windows. The primary command examples use a POSIX shell. On Windows PowerShell, environment variables can be set with:

```powershell
$env:OPENAI_API_KEY = "your-key"
uv run uvicorn ros_trace_ai.app:app --host 127.0.0.1 --port 8000
```

Because ROS-Trace AI analyzes text and does not import ROS packages, the local demo should not require a ROS distribution. Platform-specific behavior should still be validated in the evaluator's environment.

## Repository map

```text
src/ros_trace_ai/
├── analyzer.py          # parsing and deterministic incident analysis
├── ai.py                # optional OpenAI/GPT-5.6 enrichment
├── app.py               # FastAPI application and static hosting
└── static/              # vanilla browser interface
samples/
└── navigation_failure.log
tests/                   # analyzer, AI-boundary, and API tests
DEVPOST.md                # ready-to-paste submission copy and demo script
```

## Privacy and safety

- Offline mode is the appropriate choice for sensitive logs.
- AI mode sends diagnostic context to the configured OpenAI service; review and redact input first.
- Never include API keys or credentials in pasted logs.
- Treat generated recommendations as investigation aids, especially on physical robots.

## Submission checklist

- [ ] Replace the repository URL placeholder with a public repository.
- [ ] Confirm the repository includes the declared license.
- [ ] Run installation and tests from a clean checkout.
- [ ] Record a public YouTube demo shorter than three minutes, with audio.
- [ ] Explain Codex's engineering decisions and GPT-5.6's runtime role in the video.
- [ ] Run `/feedback` and add the Codex Session ID.
- [ ] Replace the YouTube placeholder.
- [ ] Remove this checklist item only after searching for all `[PLACEHOLDER:` markers.

## License

See [`LICENSE`](LICENSE) for the repository's license terms.
