"""Contract tests for the deterministic ROS log analyzer."""

import json
import sys
from pathlib import Path

import pytest

# Keep the focused tests runnable before packaging metadata exists.
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from ros_trace_ai.analyzer import (
    MAX_EVIDENCE_PER_INCIDENT,
    MAX_RETURNED_ENTRIES,
    MAX_RETURNED_INCIDENTS,
    analyze_log,
    parse_line,
)


def test_parse_ros1_line():
    entry = parse_line("[ERROR] [1712345678.123]: Could not transform map to base_link")

    assert entry.severity == "ERROR"
    assert entry.timestamp == "1712345678.123"
    assert entry.node is None
    assert entry.message == "Could not transform map to base_link"


def test_parse_ros2_launch_prefixed_line():
    entry = parse_line(
        "[planner-1] [WARN] [1712345679.456] [nav2_planner]: timed out waiting for action server"
    )

    assert entry.severity == "WARN"
    assert entry.timestamp == "1712345679.456"
    assert entry.node == "nav2_planner"
    assert entry.process == "planner-1"
    assert entry.message == "timed out waiting for action server"


@pytest.mark.parametrize("severity_text", ["INFO", " INFO", "INFO ", " WARNING "])
def test_parse_accepts_padded_ros_severity(severity_text):
    entry = parse_line(
        f"[{severity_text}] [1712345678.1] [nav]: controller ready"
    )

    assert entry.severity == ("WARN" if "WARNING" in severity_text else "INFO")
    assert entry.timestamp == "1712345678.1"
    assert entry.node == "nav"


def test_parse_ignores_ansi_color_sequences():
    line = "\x1b[31m[ERROR] [1712345678.1] [nav]: timeout waiting for service\x1b[0m"

    entry = parse_line(line)

    assert entry.severity == "ERROR"
    assert entry.timestamp == "1712345678.1"
    assert entry.node == "nav"
    assert entry.message == "timeout waiting for service"
    assert entry.raw == line


def test_malformed_line_is_preserved_as_info():
    entry = parse_line("not actually a structured ROS line")

    assert entry.severity == "INFO"
    assert entry.timestamp is None
    assert entry.message == "not actually a structured ROS line"
    assert entry.raw == "not actually a structured ROS line"


def test_report_counts_nodes_time_range_and_is_json_serializable():
    report = analyze_log(
        "\n".join(
            [
                "[INFO] [1712345678.000] [camera]: ready",
                "[camera-1] [WARN] [1712345679.000] [camera]: frame delayed",
                "[ERROR] [1712345680.000]: failed",
                "unstructured detail",
            ]
        )
    )

    assert report["summary"]["total_lines"] == 4
    assert report["summary"]["severity_counts"] == {
        "DEBUG": 0,
        "INFO": 2,
        "WARN": 1,
        "ERROR": 1,
        "FATAL": 0,
    }
    assert report["summary"]["nodes"] == ["camera"]
    assert report["summary"]["time_range"] == {
        "start": "1712345678.000",
        "end": "1712345680.000",
    }
    json.dumps(report)


def test_report_caps_returned_entries_and_incident_evidence():
    total = MAX_RETURNED_ENTRIES + 100
    report = analyze_log(
        "\n".join(
            f"[WARN] [{index}.0] [camera]: no publishers for topic /scan"
            for index in range(total)
        )
    )

    assert report["summary"]["total_lines"] == total
    assert report["summary"]["entries_omitted"] == 100
    assert len(report["entries"]) == MAX_RETURNED_ENTRIES
    assert report["incidents"][0]["count"] == total
    assert len(report["incidents"][0]["evidence"]) == MAX_EVIDENCE_PER_INCIDENT
    assert report["incidents"][0]["evidence_omitted"] == total - MAX_EVIDENCE_PER_INCIDENT


def test_report_caps_returned_incidents_without_losing_total_count():
    total = MAX_RETURNED_INCIDENTS + 20
    report = analyze_log(
        "\n".join(
            f"[WARN] [{index}.0] [node_{index}]: component unavailable"
            for index in range(total)
        )
    )

    assert report["summary"]["incident_count"] == total
    assert report["summary"]["incidents_omitted"] == 20
    assert len(report["incidents"]) == MAX_RETURNED_INCIDENTS


def test_repeated_messages_are_normalized_and_grouped_with_evidence():
    report = analyze_log(
        "\n".join(
            [
                "[ERROR] [1712345678.000] [localizer]: Lookup would require extrapolation 0.12 seconds into the future",
                "[ERROR] [1712345679.000] [localizer]: Lookup would require extrapolation 0.87 seconds into the future",
            ]
        )
    )

    assert len(report["incidents"]) == 1
    incident = report["incidents"][0]
    assert incident["kind"] == "tf_extrapolation"
    assert incident["count"] == 2
    assert incident["severity"] == "ERROR"
    assert len(incident["evidence"]) == 2
    assert incident["evidence"][0]["line_number"] == 1


@pytest.mark.parametrize("code", ["0", "-0", "+0", "00", "0x0", "-0x0"])
def test_clean_exit_is_not_a_node_crash(code):
    report = analyze_log(
        f"[INFO] [1.0] [launch]: process worker exited with exit code {code}"
    )

    assert report["incidents"] == []


@pytest.mark.parametrize("severity", ["INFO", "WARN", "ERROR"])
def test_clean_exit_does_not_suppress_other_diagnostics(severity):
    report = analyze_log(
        f"[{severity}] [1.0] [launch]: timeout during cleanup; process exited with exit code 0"
    )

    assert report["incidents"][0]["kind"] == "timeout"


@pytest.mark.parametrize("code", [-11, 1, 134, "0x1"])
def test_nonzero_exit_code_is_a_node_crash(code):
    report = analyze_log(
        f"[ERROR] [1.0] [launch]: process worker exited with exit code {code}"
    )

    assert report["incidents"][0]["kind"] == "node_crash"


@pytest.mark.parametrize(
    "line",
    [
        "[INFO] [1.0] [manager]: Lifecycle transition completed without error",
        "[INFO] [2.0] [lidar]: QoS profiles are compatible on /scan",
        "[INFO] [3.0] [camera]: memory allocation completed",
        "[INFO] [4.0] [controller]: control loop rate is stable",
    ],
)
def test_known_rule_phrases_do_not_match_success_messages(line):
    assert analyze_log(line)["incidents"] == []


@pytest.mark.parametrize(
    ("line", "kind"),
    [
        ("[ERROR] [1.0]: TF lookup failed: canTransform returned false", "tf_lookup"),
        ("[WARN] [2.0]: no publishers for topic /scan", "missing_topic"),
        ("[ERROR] [3.0]: process [controller-2] has died [pid 42]", "node_crash"),
        ("[ERROR] [4.0]: timeout waiting for service /map", "timeout"),
        (
            "[WARN] [5.0] [controller_server]: Costmap update loop missed its desired rate",
            "control_loop_overrun",
        ),
        (
            "[WARN] [6.0] [lidar]: New subscription discovered with incompatible QoS on topic /scan",
            "qos_incompatibility",
        ),
        (
            "[ERROR] [7.0] [lifecycle_manager]: Failed to transition node map_server to active state",
            "lifecycle_transition",
        ),
        (
            "[FATAL] [8.0] [camera]: std::bad_alloc: cannot allocate memory",
            "resource_exhaustion",
        ),
    ],
)
def test_known_root_cause_rules(line, kind):
    report = analyze_log(line)

    assert report["incidents"][0]["kind"] == kind
    assert report["incidents"][0]["root_cause"]
    assert report["incidents"][0]["recommendation"]
