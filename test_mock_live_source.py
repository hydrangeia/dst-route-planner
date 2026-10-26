from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from dst_route_planner.live import read_snapshot_batch, validate_snapshot
from examples.mock_live_source import make_snapshot


ROOT = Path(__file__).resolve().parent
MOCK_SOURCE = ROOT / "examples" / "mock_live_source.py"


def test_mock_source_appends_valid_fresh_snapshots_for_live_tools(tmp_path) -> None:
    log_path = tmp_path / "nested" / "mock-client.log"
    for _ in range(2):
        subprocess.run(
            [sys.executable, str(MOCK_SOURCE), "--output", str(log_path), "--once"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

    snapshots = read_snapshot_batch(log_path)
    assert len(snapshots) == 2
    assert snapshots[0]["sequence"] == snapshots[1]["sequence"] == 1
    assert snapshots[0]["session_id"] != snapshots[1]["session_id"]
    assert snapshots[1]["position"]["x"] == 2
    assert snapshots[1]["camera_heading"] == 15
    assert snapshots[1]["landmarks"][0]["prefab"] == "panflute"
    assert snapshots[1]["terrain"]["tiles"][0]["connections"] == {"east": True}
    assert validate_snapshot(snapshots[1]) == snapshots[1]


def test_mock_source_rejects_nonpositive_interval() -> None:
    result = subprocess.run(
        [sys.executable, str(MOCK_SOURCE), "--interval", "0"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "interval must be a positive number" in result.stderr


def test_mock_source_moves_player_and_camera_within_a_session() -> None:
    first = make_snapshot(1, "mock-session", captured_at=100)
    second = make_snapshot(2, "mock-session", captured_at=101)

    assert first["session_id"] == second["session_id"]
    assert second["sequence"] == first["sequence"] + 1
    assert second["position"]["x"] > first["position"]["x"]
    assert second["camera_heading"] != first["camera_heading"]
    assert validate_snapshot(first) == first
    assert validate_snapshot(second) == second
