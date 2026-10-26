"""Write synthetic live-collector snapshots for trying the local planner UI."""

from __future__ import annotations

import argparse
import json
import math
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MARKER = "DST_ROUTE_PLANNER_LIVE_V1 "


def _load_example(name: str) -> dict[str, Any]:
    return json.loads((ROOT / "examples" / name).read_text(encoding="utf-8"))


def make_snapshot(sequence: int, session_id: str, *, captured_at: float | None = None) -> dict[str, Any]:
    """Build a clearly synthetic snapshot that follows the live protocol."""
    if type(sequence) is not int or sequence < 1:
        raise ValueError("sequence must be an integer of at least 1")

    x = sequence * 2.0
    first_tile_x = math.floor((x - 8) / 4) * 4
    tiles = []
    for index in range(5):
        tile_x = first_tile_x + index * 4
        tile: dict[str, Any] = {
            "x": tile_x,
            "z": 0,
            "tile": "DECIDUOUS" if index % 2 == 0 else "GRASS",
            "passable": True,
        }
        if index < 4:
            tile["connections"] = {"east": True}
        tiles.append(tile)

    current = _load_example("current_observation.json")
    directions = _load_example("panflute_observation.json")["directions"]
    return {
        "live_version": 1,
        "world_id": "mock-world",
        "world_kind": "forest",
        "session_id": session_id,
        "sequence": sequence,
        "captured_at": time.time() if captured_at is None else captured_at,
        "position": {"x": x, "y": 0, "z": 0},
        "camera_heading": (sequence * 15) % 360,
        "current": current,
        "directions": directions,
        "landmarks": [{"prefab": "panflute", "x": 20, "z": 0}],
        "terrain": {"tile_size": 4, "tiles": tiles},
    }


def append_snapshot(path: Path, snapshot: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as log_file:
        log_file.write(MARKER)
        json.dump(snapshot, log_file, ensure_ascii=False, separators=(",", ":"))
        log_file.write("\n")


def _positive_interval(value: str) -> float:
    try:
        interval = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("interval must be a positive number") from exc
    if not math.isfinite(interval) or interval <= 0:
        raise argparse.ArgumentTypeError("interval must be a positive number")
    return interval


def main(argv: list[str] | None = None) -> int:
    default_path = Path(tempfile.gettempdir()) / "dst-route-planner-mock-client_log.txt"
    parser = argparse.ArgumentParser(description="Write synthetic DST live snapshots for UI testing.")
    parser.add_argument("--output", type=Path, default=default_path, help="log file to append to")
    parser.add_argument("--interval", type=_positive_interval, default=1.0, help="seconds between snapshots (default: 1)")
    parser.add_argument("--once", action="store_true", help="write one snapshot and exit")
    args = parser.parse_args(argv)

    session_id = "mock-" + uuid.uuid4().hex
    sequence = 1
    print(f"Writing synthetic snapshots to {args.output}; Ctrl+C to stop.", flush=True)
    try:
        while True:
            append_snapshot(args.output, make_snapshot(sequence, session_id))
            if args.once:
                return 0
            sequence += 1
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("Mock snapshot stream stopped.", flush=True)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
