"""Contract tests for the deterministic ROS log analyzer."""

import json
import sys
from pathlib import Path

import pytest

# Keep the focused tests runnable before packaging metadata exists.
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from ros_trace_ai.analyzer import analyze_log, parse_line


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


@pytest.mark.parametrize(
    ("line", "kind"),
    [
        ("[ERROR] [1.0]: TF lookup failed: canTransform returned false", "tf_lookup"),
        ("[WARN] [2.0]: no publishers for topic /scan", "missing_topic"),
        ("[ERROR] [3.0]: process [controller-2] has died [pid 42]", "node_crash"),
        ("[ERROR] [4.0]: timeout waiting for service /map", "timeout"),
    ],
)
def test_known_root_cause_rules(line, kind):
    report = analyze_log(line)

    assert report["incidents"][0]["kind"] == kind
    assert report["incidents"][0]["root_cause"]
    assert report["incidents"][0]["recommendation"]
