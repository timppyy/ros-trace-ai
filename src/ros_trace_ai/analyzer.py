"""Parse ROS 1/2 console logs and identify common operational incidents.

The core intentionally has no ROS or third-party dependency, making it suitable
for uploaded logs as well as machines on which ROS is not installed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any, Iterable

SEVERITIES = ("DEBUG", "INFO", "WARN", "ERROR", "FATAL")

# ``message`` is deliberately greedy: ROS messages often contain colons.
_ROS2_LINE = re.compile(
    r"^\[(?P<process>[^\]]+)\]\s*"
    r"\[(?P<severity>DEBUG|INFO|WARN|WARNING|ERROR|FATAL)\]\s*"
    r"\[(?P<timestamp>[^\]]+)\]\s*"
    r"\[(?P<node>[^\]]+)\]\s*:\s*(?P<message>.*)$",
    re.IGNORECASE,
)
_ROS_LINE = re.compile(
    r"^\[(?P<severity>DEBUG|INFO|WARN|WARNING|ERROR|FATAL)\]\s*"
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
    for pattern in (_ROS2_LINE, _ROS_LINE):
        match = pattern.match(raw.strip())
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
        "node_crash",
        _patterns(
            r"\bprocess\b.*\b(?:has died|died|exited|terminated|crashed)\b",
            r"\bnode\b.*\b(?:has died|crashed|segmentation fault)\b",
            r"\bsegmentation fault\b",
            r"\bexit code\s*-?\d+",
        ),
        "Node process exited unexpectedly",
        "A ROS node crashed or was terminated; nearby stderr and its exit code normally identify the immediate failure.",
        "Restart the node with debug logging, inspect the preceding stderr, and check its exit code and core dump.",
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
    return next((rule for rule in _RULES if rule.matches(searchable)), None)


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
            }
        incident = grouped[key]
        incident["count"] += 1
        incident["last_timestamp"] = entry.timestamp or incident["last_timestamp"]
        incident["evidence"].append(_evidence(entry))
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
        },
        "incidents": incidents,
        "entries": [entry.to_dict() for entry in entries],
    }


# Friendly plural alias for callers that treat the input as a set of lines.
analyze_logs = analyze_log
