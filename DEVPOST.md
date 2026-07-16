# Devpost Submission Copy — ROS-Trace AI

> Final submission copy, ready to paste into Devpost.

## Title

ROS-Trace AI

## Tagline

Evidence-backed ROS incident triage that works offline, with optional GPT-5.6 enrichment.

## Category

Developer Tools

## Links

- **Repository:** https://github.com/timppyy/ros-trace-ai
- **Public YouTube demo (<3 minutes):** https://youtu.be/e0SY_yYEviQ
- **Codex Session ID from `/feedback`:** `019f6560-cdb8-7da1-bec4-5ca79eac8ea7`
- **License:** See `LICENSE` in the public repository.

## Inspiration

Robotics failures rarely arrive as one clean exception. A navigation problem can produce interleaved transform warnings, sensor timeouts, planner errors, and repeated recovery messages across several nodes. The first useful clue may be hundreds of lines away from the final failure.

We wanted a tool that gives a robotics developer a credible starting point in seconds, without requiring a running robot, a complete ROS workstation, or permission to upload operational logs. That led to one central design decision: useful analysis had to be deterministic and offline first. AI should improve the explanation when a team opts in—not be a prerequisite for understanding the incident.

## What it does

ROS-Trace AI turns ROS-style text logs into a compact diagnostic report:

- a severity and health summary;
- an ordered incident timeline;
- grouping of repeated failures;
- likely root-cause hypotheses;
- the exact log evidence behind each hypothesis; and
- actionable checks or commands for the developer to try next; and
- a downloadable JSON report for sharing or downstream automation.

The web interface can run a bundled navigation-failure sample in one click or accept pasted logs, so judges can see a meaningful result immediately. Known signatures cover TF failures, missing topics, QoS incompatibility, lifecycle transitions, control-loop overruns, timeouts, node crashes, and host resource exhaustion. The deterministic path runs locally without ROS, an API key, or a network call. If an OpenAI key is explicitly configured, GPT-5.6 can enrich the structured findings with a clearer synthesis and prioritization.

ROS-Trace AI is intentionally a text-log analyzer rather than a binary ROS bag reader. Teams can export relevant console logs from ROS1 or ROS2 and analyze those locally.

## How we built it

The backend is Python 3.11 with FastAPI and Pydantic. The frontend is vanilla HTML, CSS, and JavaScript served by the same application, so there is no separate frontend toolchain or build step.

The analysis pipeline has four boundaries:

1. A tolerant parser normalizes common ROS1/ROS2-style records while handling malformed lines gracefully.
2. Deterministic logic calculates severity metrics, groups repeated events, and applies known diagnostic rules.
3. FastAPI exposes the result to the static browser interface.
4. An optional OpenAI adapter sends structured findings—not an unbounded autonomous workflow—to GPT-5.6 for enrichment.

We used Codex as an engineering partner to shape and implement the project. The highest-impact Codex decisions were to keep offline analysis as the core product, isolate model access behind an injectable boundary, define expected failure behavior before implementation, and optimize the demo around a bundled sample and a no-build UI. Those choices made the tool easier to test, explain, and evaluate than a model-only log chatbot.

GPT-5.6 has a separate runtime role: when enabled, it synthesizes the deterministic timeline, helps prioritize hypotheses, and turns structured evidence into a more concise incident narrative. The deterministic result remains available when no key is configured.

## Challenges we ran into

### Converting noisy text into evidence

ROS output varies by version, logger, launch setup, and copy/paste source. A parser that rejects one malformed line can make the tool brittle, while a parser that accepts everything can create false structure. We designed tolerant parsing and preserved evidence so that the report remains useful without pretending every line is perfectly normalized.

### Being useful without overclaiming

Logs support hypotheses, not certainty. We separated evidence, likely causes, and recommended checks instead of presenting generated prose as a proven diagnosis. That distinction matters even more when software recommendations can affect a physical robot.

### Adding AI without making it a dependency

The obvious implementation was to send raw logs directly to a model. We chose the harder but more robust architecture: deterministic code first, optional GPT-5.6 second. This supports offline and privacy-sensitive environments, creates stable test boundaries, and gives users a result even when credentials or network access are unavailable.

### Keeping the judging path short

A robotics tool can easily accumulate environment requirements. Serving a vanilla interface from FastAPI and analyzing plain text lets evaluators run the project without installing ROS or connecting hardware.

## Accomplishments that we're proud of

- Built an offline-first developer tool instead of an AI-dependent demo.
- Made each diagnosis evidence-backed and paired it with a next action.
- Put the primary evidence line, timestamp range, likely cause, and recommended action directly in each incident card.
- Added bounded JSON export and explicit omission counts for large reports.
- Created a bundled sample workflow that reaches useful output quickly.
- Kept the application runnable without ROS, robot hardware, or an API key.
- Isolated optional GPT-5.6 enrichment from deterministic parsing and analysis.
- Used a single FastAPI process and no-build frontend to minimize setup friction.
- Designed tests around parser behavior, AI fallback, and API behavior.

## What we learned

The most valuable AI architecture is sometimes a narrow layer on top of dependable software. Parsing, grouping, and known diagnostic patterns benefit from deterministic behavior; synthesis and prioritization are where a language model can add the most value.

We also learned that explainability is a product feature for developer tools. Showing the triggering lines beside a hypothesis makes the output easier to trust and easier to challenge. Finally, designing for a judge with no ROS environment improved the product for real users who need to inspect logs away from the robot.

## What's next

- Add more deterministic signatures for sensors, plugin loading, ros2_control hardware initialization, and DDS transport failures.
- Support rosbag/MCAP extraction through explicit local adapters.
- Add log redaction previews before optional model enrichment.
- Compare incidents across two runs to detect regressions.
- Export reports as Markdown/JSON and link incidents to issue trackers.
- Add configurable organization-specific diagnostic rules.
- Validate packaging and UX across Linux, macOS, and Windows.
- Evaluate model-assisted remediation against a curated ROS failure benchmark.

## Testing instructions for judges

### Requirements

- Python 3.11+
- `uv`
- A modern browser
- Optional: `OPENAI_API_KEY` for GPT-5.6 enrichment

### Run locally

```bash
git clone https://github.com/timppyy/ros-trace-ai.git
cd ros-trace-ai
uv sync
uv run uvicorn ros_trace_ai.app:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>.

### Recommended evaluation path

1. Load the bundled navigation failure.
2. Run the default offline analysis.
3. Inspect severity metrics, the incident timeline, cited evidence, and recommended actions.
4. Duplicate an error or add a malformed line, then rerun to inspect grouping and parser tolerance.
5. If you want to evaluate enrichment, restart with:

```bash
export OPENAI_API_KEY="your-key"
uv run uvicorn ros_trace_ai.app:app --host 127.0.0.1 --port 8000
```

6. Compare AI-enriched explanation with the deterministic baseline.

Run automated tests from the repository root:

```bash
uv sync --extra dev
uv run pytest -v
```

Focused test paths:

```bash
uv run pytest tests/test_analyzer.py -v
uv run pytest tests/test_ai.py -v
uv run pytest tests/test_api.py -v
```

No deployed URL or specific test result is claimed in this draft; use the submitted public repository revision and the commands above.

---

# Demo Video Script and Storyboard (Target: 2:40–2:55)

**Requirement reminders:** keep the final upload under 3:00, make it public on YouTube, include spoken audio, and verbally explain both Codex and GPT-5.6.

## 0:00–0:15 — Hook

**On screen:** ROS-Trace AI title, then the app with the bundled log visible.

**Narration:**

> “A robot can emit hundreds of interleaved messages before one navigation failure. ROS-Trace AI turns those logs into an evidence-backed incident timeline and practical next steps—in seconds, and offline by default.”

## 0:15–0:35 — Problem and promise

**On screen:** Scroll briefly through noisy raw log lines, then point to the offline-mode indicator.

**Narration:**

> “Manually correlating transform, sensor, planner, and recovery messages is slow. Sending operational logs to a hosted model may also be impossible. This tool needs no robot, no ROS installation, and no API key for its core analysis.”

## 0:35–1:15 — Working offline demo

**On screen:** Click **Load sample**, then run analysis. Move deliberately through severity metrics and the timeline.

**Narration:**

> “I’ll load the bundled navigation failure and analyze it locally. The parser normalizes ROS-style records, tolerates malformed input, counts severity, and groups repeated events. Here is the ordered incident timeline. Each likely cause is paired with the exact supporting lines and concrete checks, so the result is inspectable rather than a black-box answer.”

**Capture note:** Pause long enough for viewers to read one hypothesis, one evidence line, and one action.

## 1:15–1:35 — Robustness and actionability

**On screen:** Add or duplicate one representative error, rerun, and highlight the changed repeat count or grouping. Show a suggested command/action.

**Narration:**

> “Repeated failures are grouped instead of flooding the report, and a bad line does not invalidate the rest of the trace. The goal is not to claim certainty—it is to narrow the search and give the developer a defensible next step.”

## 1:35–2:05 — Codex contribution

**On screen:** Show the repository tree, tests, and briefly highlight `analyzer.py`, `ai.py`, and `app.py`.

**Narration:**

> “Codex helped make the key engineering decisions and implement them: deterministic analysis is the core product; parsing, diagnosis, model access, API, and UI are separate testable layers; missing credentials degrade cleanly; and the vanilla UI keeps setup to one FastAPI process. Codex also helped define tests around malformed logs, repeated errors, offline fallback, and API behavior before implementation.”

**Capture note:** Include the final Codex Session ID in the repository or end card after running `/feedback`.

## 2:05–2:30 — GPT-5.6 contribution

**On screen:** Show AI mode only if a key is configured. Compare a deterministic finding with its enriched narrative. If live model access is unavailable during recording, show the AI boundary in code/diagram and honestly state that the visible run is offline—do not simulate a response.

**Narration:**

> “GPT-5.6 is optional and has a focused role. It receives structured diagnostic findings and enriches prioritization and explanation. It does not replace parsing or become a single point of failure; without a key, this offline result still works. Teams can therefore choose the privacy and connectivity boundary that fits their robot.”

## 2:30–2:48 — Reproducibility and close

**On screen:** Show the README quick-start commands, public repository URL, license, and tests command.

**Narration:**

> “The public repository includes the license, sample, setup instructions, and test paths. Clone it, run `uv sync`, start the FastAPI app, and load the sample. ROS-Trace AI turns noisy robot logs into the evidence you need to debug the next failure.”

## 2:48–2:55 — End card

**On screen:**

```text
ROS-Trace AI
Developer Tools
https://github.com/timppyy/ros-trace-ai
019f6560-cdb8-7da1-bec4-5ca79eac8ea7
```

No additional narration is required, but leave the end card visible long enough to read.

## Recording checklist

- [x] Final runtime is below 3:00.
- [x] Video is uploaded publicly to YouTube.
- [x] Spoken audio clearly explains the problem and working demo.
- [x] Spoken audio explicitly identifies Codex's engineering decisions.
- [x] Spoken audio explicitly identifies GPT-5.6's optional runtime role.
- [x] At least one evidence-backed incident and action is legible.
- [x] No API key, private log, terminal secret, or personal notification appears.
- [x] Repository URL and license are visible.
- [x] Codex Session ID from `/feedback` is added to the submission.
- [x] All submission links are final and public.
