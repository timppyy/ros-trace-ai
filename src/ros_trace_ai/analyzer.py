"""Parse ROS 1/2 console logs and identify common operational incidents.

The core intentionally has no ROS or third-party dependency, making it suitable
for uploaded logs as well as machines on which ROS is not installed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any, Iterable

SEVERITIES = ("DEBUG", "INFO", "WARN", "ERROR", "FATAL")
MAX_RETURNED_ENTRIES = 2_000
MAX_EVIDENCE_PER_INCIDENT = 50
MAX_RETURNED_INCIDENTS = 500

# ``message`` is deliberately greedy: ROS messages often contain colons.
_ANSI_CSI = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
_EXIT_CODE = re.compile(
    r"\bexit code\s*(?P<code>[+-]?(?:0x[0-9a-f]+|\d+))\b", re.IGNORECASE
)
_ROS2_LINE = re.compile(
    r"^\[(?P<process>[^\]]+)\]\s*"
    r"\[\s*(?P<severity>DEBUG|INFO|WARN|WARNING|ERROR|FATAL)\s*\]\s*"
    r"\[(?P<timestamp>[^\]]+)\]\s*"
    r"\[(?P<node>[^\]]+)\]\s*:\s*(?P<message>.*)$",
    re.IGNORECASE,
)
_ROS_LINE = re.compile(
    r"^\[\s*(?P<severity>DEBUG|INFO|WARN|WARNING|ERROR|FATAL)\s*\]\s*"
    r"\[(?P<timestamp>[^\]]+)\]"
    r"(?:\s*\[(?P<node>[^\]]+)\])?\s*:\s*(?P<message>.*)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class LogEntry:
    """A single parsed line; fields remain JSON-safe primitive values."""

    severity: str
    message: str
    raw: str
    timestamp: str | None = None
    node: str | None = None
    process: str | None = None
    line_number: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _severity(value: str) -> str:
    value = value.upper()
    return "WARN" if value == "WARNING" else value


def parse_line(line: str, line_number: int | None = None) -> LogEntry:
    """Parse one common ROS console line.

    Unknown or partially written lines are not errors: they are retained as an
    INFO entry so a crash or interleaved process output never aborts analysis.
    """

    raw = line.rstrip("\r\n")
    match_text = _ANSI_CSI.sub("", raw).strip()
    for pattern in (_ROS2_LINE, _ROS_LINE):
        match = pattern.match(match_text)
        if match:
            fields = match.groupdict()
            return LogEntry(
                severity=_severity(fields["severity"]),
                timestamp=fields["timestamp"].strip() or None,
                node=(fields.get("node") or "").strip() or None,
                process=(fields.get("process") or "").strip() or None,
                message=fields["message"].strip(),
                raw=raw,
                line_number=line_number,
            )
    return LogEntry(
        severity="INFO", message=raw, raw=raw, line_number=line_number
    )


def parse_log(text: str) -> list[LogEntry]:
    """Parse a complete log while retaining blank/interleaved malformed lines."""

    if not text:
        return []
    return [parse_line(line, number) for number, line in enumerate(text.splitlines(), 1)]


@dataclass(frozen=True)
class _Rule:
    kind: str
    patterns: tuple[re.Pattern[str], ...]
    title: str
    root_cause: str
    recommendation: str

    def matches(self, message: str) -> bool:
        return any(pattern.search(message) for pattern in self.patterns)


def _patterns(*values: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(value, re.IGNORECASE) for value in values)


# Order matters where phrases overlap (TF extrapolation is also a lookup error).
_RULES = (
    _Rule(
        "tf_extrapolation",
        _patterns(r"\bextrapolat(?:e|ed|ion|ing)\b", r"would require extrapolation"),
        "TF transform timestamp is outside the buffer",
        "The requested transform is older or newer than the data in the TF buffer, often due to clock skew or stale timestamps.",
        "Check /clock and message timestamps, then inspect the transform with `ros2 run tf2_ros tf2_echo <target> <source>`.",
    ),
    _Rule(
        "tf_lookup",
        _patterns(
            r"\b(?:tf|transform)\b.*\b(?:lookup|failed|failure|not found|unavailable)\b",
            r"\bcantransform\b.*\b(?:false|fail)",
            r"lookup(?:exception| failed)",
        ),
        "TF transform lookup failed",
        "The required frame transform is missing, disconnected, or not being published.",
        "Inspect the frame tree with `ros2 run tf2_tools view_frames` and verify the expected static or dynamic broadcaster.",
    ),
    _Rule(
        "qos_incompatibility",
        _patterns(
            r"\bincompatible\b.*\bqos\b",
            r"\bqos\b.*\bincompatible\b",
            r"\brequested (?:deadline|reliability|durability)\b.*\boffered\b",
        ),
        "DDS QoS policies are incompatible",
        "The publisher and subscriber use incompatible reliability, durability, deadline, or history policies, so discovery may succeed while messages are not delivered.",
        "Run `ros2 topic info <topic> --verbose`, compare offered and requested QoS profiles, and align the publisher and subscriber policies.",
    ),
    _Rule(
        "missing_topic",
        _patterns(
            r"\bno publishers?\b",
            r"\b(?:topic|subscription)\b.*\b(?:not published|missing|unavailable)\b",
            r"\bwaiting for (?:messages? (?:on|from)|topic)\b",
        ),
        "Topic has no active publisher",
        "A required topic is absent or its publisher has not started, is misnamed, or uses an incompatible namespace.",
        "Run `ros2 topic list` and `ros2 topic info <topic> --verbose`; confirm remappings, namespaces, and publisher health.",
    ),
    _Rule(
        "lifecycle_transition",
        _patterns(
            r"\b(?:lifecycle|transition)\b(?!.*\b(?:without (?:any )?|no )(?:error|failure)\b).*\b(?:fail|failed|failure|error)\b",
            r"\bfailed to transition\b.*\b(?:active|inactive|configured|finalized)\b",
            r"\bnode\b.*\b(?:unconfigured|inactive)\b.*\b(?:unexpected|stuck|remain)\b",
        ),
        "Lifecycle node failed to reach its target state",
        "A managed node could not complete a configure, activate, deactivate, or cleanup transition, often because a dependency or resource initialization failed.",
        "Run `ros2 lifecycle get <node>` and `ros2 lifecycle list <node>`, then inspect the node logs immediately before the failed transition.",
    ),
    _Rule(
        "resource_exhaustion",
        _patterns(
            r"\b(?:out of memory|cannot allocate memory|bad_alloc|oom[- ]killer)\b",
            r"\bno space left on device\b",
            r"\b(?:too many open files|resource temporarily unavailable)\b",
        ),
        "Host resource exhaustion interrupted the node",
        "The process could not obtain required memory, disk space, file descriptors, or another operating-system resource.",
        "Check memory, disk, and file-descriptor pressure on the host; identify the growing process or file set before restarting the node.",
    ),
    _Rule(
        "node_crash",
        _patterns(
            r"\bprocess\b.*\b(?:has died|died|terminated|crashed)\b",
            r"\bprocess\b.*\bexited\b.*\bexit code\s*[+-]?(?:0x[0-9a-f]+|\d+)",
            r"\bnode\b.*\b(?:has died|crashed|segmentation fault)\b",
            r"\bsegmentation fault\b",
            r"\bexit code\s*[+-]?(?:0x[0-9a-f]+|\d+)",
        ),
        "Node process exited unexpectedly",
        "A ROS node crashed or was terminated; nearby stderr and its exit code normally identify the immediate failure.",
        "Restart the node with debug logging, inspect the preceding stderr, and check its exit code and core dump.",
    ),
    _Rule(
        "control_loop_overrun",
        _patterns(
            r"\b(?:control|controller|costmap|update) loop\b.*\b(?:missed|overrun|late)\b",
            r"\bmissed (?:its )?desired rate\b",
            r"\bloop rate\b.*\b(?:missed|overrun|below)\b",
        ),
        "Control loop missed its target rate",
        "The controller or costmap update loop could not finish within its configured period, commonly because of CPU pressure, blocking callbacks, or expensive map processing.",
        "Measure CPU load and callback latency, inspect the configured update frequency, then profile the slow controller or costmap plugins before lowering the target rate.",
    ),
    _Rule(
        "timeout",
        _patterns(r"\btime(?:d|)\s*out\b", r"\btimeout\b", r"deadline (?:missed|exceeded)"),
        "Operation timed out",
        "A service, action, topic, or hardware response did not arrive within its configured deadline.",
        "Verify the dependency is running and reachable, measure its latency, then adjust the timeout only if the observed delay is expected.",
    ),
)


def _classify(entry: LogEntry) -> _Rule | None:
    searchable = f"{entry.process or ''} {entry.node or ''} {entry.message}"
    exit_match = _EXIT_CODE.search(searchable)
    clean_exit = False
    if exit_match:
        token = exit_match.group("code")
        base = 16 if token.lower().lstrip("+-").startswith("0x") else 10
        clean_exit = int(token, base) == 0 and not re.search(
            r"\b(?:has died|died|terminated|crashed|segmentation fault)\b",
            searchable,
            re.IGNORECASE,
        )
    return next(
        (
            rule
            for rule in _RULES
            if not (clean_exit and rule.kind == "node_crash")
            and rule.matches(searchable)
        ),
        None,
    )


def _normalize(message: str) -> str:
    """Remove volatile values so repetitions collapse into one incident."""

    normalized = message.lower().strip()
    normalized = re.sub(r"0x[0-9a-f]+", "<hex>", normalized)
    normalized = re.sub(r"\b\d+(?:\.\d+)?\b", "<n>", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def _generic_rule(entry: LogEntry) -> _Rule:
    return _Rule(
        "log_error" if entry.severity in {"ERROR", "FATAL"} else "log_warning",
        (),
        "Repeated ROS log event",
        "The component repeatedly emitted this warning or error; the message and nearby evidence identify the affected operation.",
        "Inspect the listed node and evidence lines, then enable debug logging around the first occurrence.",
    )


def _timestamp_key(timestamp: str) -> tuple[int, float | str]:
    try:
        return (0, float(timestamp))
    except ValueError:
        return (1, timestamp)


def _evidence(entry: LogEntry) -> dict[str, Any]:
    return {
        "line_number": entry.line_number,
        "timestamp": entry.timestamp,
        "node": entry.node,
        "severity": entry.severity,
        "message": entry.message,
        "raw": entry.raw,
    }


def _build_incidents(entries: Iterable[LogEntry]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str | None], dict[str, Any]] = {}
    for entry in entries:
        rule = _classify(entry)
        if rule is None and entry.severity not in {"WARN", "ERROR", "FATAL"}:
            continue
        rule = rule or _generic_rule(entry)
        key = (rule.kind, _normalize(entry.message), entry.node)
        if key not in grouped:
            grouped[key] = {
                "kind": rule.kind,
                "title": rule.title,
                "severity": entry.severity,
                "node": entry.node,
                "message": entry.message,
                "normalized_message": key[1],
                "count": 0,
                "first_timestamp": entry.timestamp,
                "last_timestamp": entry.timestamp,
                "root_cause": rule.root_cause,
                "recommendation": rule.recommendation,
                "evidence": [],
                "evidence_omitted": 0,
            }
        incident = grouped[key]
        incident["count"] += 1
        incident["last_timestamp"] = entry.timestamp or incident["last_timestamp"]
        if len(incident["evidence"]) < MAX_EVIDENCE_PER_INCIDENT:
            incident["evidence"].append(_evidence(entry))
        else:
            incident["evidence_omitted"] += 1
        # Preserve the highest severity observed in a mixed group.
        if SEVERITIES.index(entry.severity) > SEVERITIES.index(incident["severity"]):
            incident["severity"] = entry.severity

    incidents = list(grouped.values())
    for number, incident in enumerate(incidents, 1):
        incident["id"] = f"incident-{number:03d}"
    return incidents


def analyze_log(text: str) -> dict[str, Any]:
    """Return a completely JSON-serializable deterministic analysis report."""

    entries = parse_log(text)
    counts = {severity: 0 for severity in SEVERITIES}
    for entry in entries:
        counts[entry.severity] += 1

    timestamps = sorted(
        (entry.timestamp for entry in entries if entry.timestamp is not None),
        key=_timestamp_key,
    )
    nodes = sorted({entry.node for entry in entries if entry.node})
    incidents = _build_incidents(entries)
    return {
        "summary": {
            "total_lines": len(entries),
            "severity_counts": counts,
            "nodes": nodes,
            "time_range": {
                "start": timestamps[0] if timestamps else None,
                "end": timestamps[-1] if timestamps else None,
            },
            "incident_count": len(incidents),
            "incidents_omitted": max(0, len(incidents) - MAX_RETURNED_INCIDENTS),
            "entries_omitted": max(0, len(entries) - MAX_RETURNED_ENTRIES),
        },
        "incidents": incidents[:MAX_RETURNED_INCIDENTS],
        "entries": [entry.to_dict() for entry in entries[:MAX_RETURNED_ENTRIES]],
    }


# Friendly plural alias for callers that treat the input as a set of lines.
analyze_logs = analyze_log
