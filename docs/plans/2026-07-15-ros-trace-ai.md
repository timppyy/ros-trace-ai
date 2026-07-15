# ROS-Trace AI Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Build a judge-ready ROS developer tool that turns ROS logs into an incident timeline, likely root causes, and actionable fixes, with optional GPT-5.6 enrichment.

**Architecture:** A FastAPI service exposes deterministic offline analysis and an optional OpenAI Responses API enrichment layer. A static single-page interface lets judges load bundled sample logs or paste their own, then renders health metrics, incidents, evidence, and recommended commands without requiring ROS or an API key.

**Tech Stack:** Python 3.11, FastAPI, Pydantic, OpenAI Python SDK, vanilla HTML/CSS/JavaScript, pytest.

---

### Task 1: Establish testable analysis contract

**Objective:** Define log parsing and incident analysis behavior before implementation.

**Files:**
- Create: `tests/test_analyzer.py`
- Create: `src/ros_trace_ai/__init__.py`
- Create: `src/ros_trace_ai/analyzer.py`

**Steps:**
1. Write tests for ROS1/ROS2 line parsing, malformed-line tolerance, severity counts, repeated-error grouping, and known root-cause rules.
2. Run `uv run pytest tests/test_analyzer.py -v` and verify import/behavior failures.
3. Implement the minimal parser and deterministic analyzer.
4. Re-run the focused test and full suite.

### Task 2: Add optional GPT-5.6 enrichment

**Objective:** Provide a safe, injectable AI enrichment layer while preserving offline operation.

**Files:**
- Create: `tests/test_ai.py`
- Create: `src/ros_trace_ai/ai.py`

**Steps:**
1. Write tests for no-key offline behavior, structured prompt construction, and client response parsing.
2. Verify RED, implement the minimal client adapter, then verify GREEN.
3. Ensure raw secrets never enter prompts or responses.

### Task 3: Expose API and bundled demo

**Objective:** Make analysis runnable through HTTP with sample data.

**Files:**
- Create: `tests/test_api.py`
- Create: `src/ros_trace_ai/app.py`
- Create: `samples/navigation_failure.log`

**Steps:**
1. Write endpoint tests for health, sample loading, valid analysis, and input validation.
2. Verify RED, implement FastAPI endpoints, verify GREEN.

### Task 4: Build judge-ready web interface

**Objective:** Provide a polished no-build demo UI.

**Files:**
- Create: `src/ros_trace_ai/static/index.html`
- Create: `src/ros_trace_ai/static/styles.css`
- Create: `src/ros_trace_ai/static/app.js`

**Steps:**
1. Add API/static integration test and verify failure.
2. Build responsive dark interface with sample loader, paste/upload, offline/AI mode badge, metrics, incident cards, evidence, and copyable fixes.
3. Verify UI loads and API calls work in a live server smoke test.

### Task 5: Package, document, and automate checks

**Objective:** Make the repository reproducible and submission-ready.

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `LICENSE`
- Create: `.gitignore`
- Create: `.github/workflows/ci.yml`
- Create: `DEVPOST.md`

**Steps:**
1. Document installation, supported platforms, offline sandbox, OpenAI setup, architecture, sample workflow, Codex/GPT-5.6 usage, and judging instructions.
2. Run tests, compile checks, API smoke test, and scan for secrets.
3. Initialize Git, commit, create a public GitHub repository, push, and verify the public URL.
