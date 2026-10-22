from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dst_route_planner.connection import (
    LiveLogDiscoveryError,
    inspect_live_log,
    resolve_live_log_path,
)
from dst_route_planner.collector_install import CollectorInstallError, install_collector
from dst_route_planner.inference import initial_belief, top_items, update_belief
from dst_route_planner.io import load_direction_observations, observation_from_dict
from dst_route_planner.knowledge import build_forest_default_kb
from dst_route_planner.models import Direction, DirectionObservation, Observation
from dst_route_planner.navigation import probabilities_by_direction, rank_directions
from dst_route_planner.world_sampler import build_random_task_graph


def demo_observations(target: str = "panflute") -> list[DirectionObservation]:
    demo_data = {
        "panflute": [
            DirectionObservation(
                Direction.NORTH,
                Observation(
                    tile_types=frozenset({"DECIDUOUS"}),
                    prefabs_seen=frozenset({"deciduoustree", "fireflies", "flower"}),
                    connection_like=True,
                    background_like=False,
                    note="dense deciduous edge",
                ),
            ),
            DirectionObservation(
                Direction.EAST,
                Observation(
                    tile_types=frozenset({"SAVANNA"}),
                    prefabs_seen=frozenset({"grass", "rabbithole"}),
                    connection_like=True,
                    background_like=False,
                    note="savanna/plain",
                ),
            ),
            DirectionObservation(
                Direction.SOUTH,
                Observation(
                    tile_types=frozenset({"FOREST"}),
                    prefabs_seen=frozenset({"evergreen", "spiderden"}),
                    connection_like=False,
                    background_like=True,
                    note="background forest",
                ),
            ),
            DirectionObservation(
                Direction.WEST,
                Observation(
                    tile_types=frozenset({"DECIDUOUS"}),
                    prefabs_seen=frozenset({"pigking", "pighouse"}),
                    connection_like=True,
                    background_like=False,
                    note="pig king visible",
                ),
            ),
        ],
        "moonbase": [
            DirectionObservation(
                Direction.NORTH,
                Observation(
                    tile_types=frozenset({"FOREST"}),
                    prefabs_seen=frozenset({"evergreen", "sapling", "grass"}),
                    connection_like=True,
                    background_like=False,
                    note="moonbase area: forest with lunar features",
                ),
            ),
            DirectionObservation(
                Direction.EAST,
                Observation(
                    tile_types=frozenset({"GRASS"}),
                    prefabs_seen=frozenset({"grass", "flower", "sapling"}),
                    connection_like=True,
                    background_like=False,
                    note="clearing area",
                ),
            ),
            DirectionObservation(
                Direction.SOUTH,
                Observation(
                    tile_types=frozenset({"FOREST"}),
                    prefabs_seen=frozenset({"evergreen", "evergreen"}),
                    connection_like=False,
                    background_like=True,
                    note="deep forest background",
                ),
            ),
            DirectionObservation(
                Direction.WEST,
                Observation(
                    tile_types=frozenset({"ROCKY"}),
                    prefabs_seen=frozenset({"rock1", "gravestone"}),
                    connection_like=False,
                    background_like=True,
                    note="rocky/graveyard background",
                ),
            ),
        ],
        "walrus_camp": [
            DirectionObservation(
                Direction.NORTH,
                Observation(
                    tile_types=frozenset({"GRASS"}),
                    prefabs_seen=frozenset({"grass", "pond"}),
                    connection_like=True,
                    background_like=False,
                    note="grassland and pond, walrus camp area",
                ),
            ),
            DirectionObservation(
                Direction.EAST,
                Observation(
                    tile_types=frozenset({"GRASS"}),
                    prefabs_seen=frozenset({"grass", "evergreen"}),
                    connection_like=True,
                    background_like=False,
                    note="grass and forest boundary",
                ),
            ),
            DirectionObservation(
                Direction.SOUTH,
                Observation(
                    tile_types=frozenset({"FOREST"}),
                    prefabs_seen=frozenset({"evergreen", "evergreen", "spiderden"}),
                    connection_like=False,
                    background_like=True,
                    note="deep forest background",
                ),
            ),
            DirectionObservation(
                Direction.WEST,
                Observation(
                    tile_types=frozenset({"GRASS"}),
                    prefabs_seen=frozenset({"grass", "sapling"}),
                    connection_like=True,
                    background_like=False,
                    note="grassy area",
                ),
            ),
        ],
        "beequeenhive": [
            DirectionObservation(
                Direction.NORTH,
                Observation(
                    tile_types=frozenset({"GRASS"}),
                    prefabs_seen=frozenset({"flower", "flower", "beehive"}),
                    connection_like=True,
                    background_like=False,
                    note="many flowers, beehive visible, bee queen area",
                ),
            ),
            DirectionObservation(
                Direction.EAST,
                Observation(
                    tile_types=frozenset({"GRASS"}),
                    prefabs_seen=frozenset({"flower", "wasphive"}),
                    connection_like=True,
                    background_like=False,
                    note="flowers and wasp hive, bee area",
                ),
            ),
            DirectionObservation(
                Direction.SOUTH,
                Observation(
                    tile_types=frozenset({"FOREST"}),
                    prefabs_seen=frozenset({"evergreen", "sapling"}),
                    connection_like=False,
                    background_like=True,
                    note="forest background, not bee area",
                ),
            ),
            DirectionObservation(
                Direction.WEST,
                Observation(
                    tile_types=frozenset({"GRASS"}),
                    prefabs_seen=frozenset({"flower", "flower", "flower", "beehive", "wasphive"}),
                    connection_like=True,
                    background_like=False,
                    note="abundant flowers and hives, bee queen core area",
                ),
            ),
        ],
        "mandrake_planted": [
            DirectionObservation(
                Direction.NORTH,
                Observation(
                    tile_types=frozenset({"GRASS"}),
                    prefabs_seen=frozenset({"evergreen", "fireflies", "flower"}),
                    connection_like=True,
                    background_like=False,
                    note="grassy room with trees, fireflies and flowers, possible mandrake location",
                ),
            ),
            DirectionObservation(
                Direction.EAST,
                Observation(
                    tile_types=frozenset({"SAVANNA"}),
                    prefabs_seen=frozenset({"grass", "flower", "beefalo"}),
                    connection_like=True,
                    background_like=False,
                    note="savanna/plain area",
                ),
            ),
            DirectionObservation(
                Direction.SOUTH,
                Observation(
                    tile_types=frozenset({"FOREST"}),
                    prefabs_seen=frozenset({"evergreen", "evergreen", "spiderden"}),
                    connection_like=False,
                    background_like=True,
                    note="deep forest background with spiders",
                ),
            ),
            DirectionObservation(
                Direction.WEST,
                Observation(
                    tile_types=frozenset({"GRASS"}),
                    prefabs_seen=frozenset({"evergreen", "flower", "fireflies"}),
                    connection_like=True,
                    background_like=False,
                    note="grassy room with trees, flowers and fireflies, mandrake task area",
                ),
            ),
        ],
    }

    return demo_data.get(target, demo_data["panflute"])


def _port_number(value: str) -> int:
    try:
        port = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("port must be an integer") from error
    if not 0 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 0 and 65535")
    return port


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DST mainland route planner.")
    parser.add_argument("--target", default="panflute", help="Target prefab (default: panflute).")
    parser.add_argument("--list-targets", action="store_true", help="List supported target prefabs and exit.")
    parser.add_argument("--observe-json", type=Path, help="JSON file containing directional observations.")
    parser.add_argument("--current-json", type=Path, help="Optional current-position observation JSON object.")
    parser.add_argument("--demo", action="store_true", help="Run a built-in example.")
    parser.add_argument("--seed", type=int, default=0, help="Random seed for repeatable task graph sampling (default: 0).")
    parser.add_argument("--sample-graph", action="store_true", help="Print a sampled mainland task connection graph as JSON and exit.")
    parser.add_argument("--ui", action="store_true", help="Start the local browser interface.")
    parser.add_argument("--check-live", action="store_true", help="Check the client collector connection once and exit.")
    parser.add_argument(
        "--install-collector",
        type=Path,
        metavar="MODS_DIR",
        help="Install or update the client collector in the game's mods folder.",
    )
    parser.add_argument("--port", type=_port_number, default=8765, help="Local interface port (default: 8765).")
    parser.add_argument("--no-browser", action="store_true", help="Start the interface without opening a browser.")
    parser.add_argument(
        "--live-log",
        type=Path,
        default=Path("auto"),
        help="Client log path, or auto (default: auto).",
    )
    return parser


def _report_live_check(result: dict) -> int:
    path = result.get("log_path")
    print(f"Client log: {path if path is not None else '(disabled)'}")
    status = result.get("status")

    if status in {"live", "stale"}:
        position = result["position"]
        age = result["age_seconds"]
        kind = result.get("world_kind", "unknown")
        label = "connected" if status == "live" else "stale snapshot"
        print(
            f"Live check: {label} (age {age:.1f}s; {kind}; "
            f"position x={float(position['x']):g}, y={float(position['y']):g}, "
            f"z={float(position['z']):g})."
        )
        if status == "live":
            print("Next: start the interface with --ui and enable live following.")
            return 0
        print("Next: return to DST and unpause live collection to refresh the snapshot.")
        return 1

    messages = {
        "disabled": (
            "Live check: disabled.",
            "Next: pass --live-log PATH or use --live-log auto.",
        ),
        "missing_log": (
            "Live check: client log not found.",
            "Next: start DST once to create the client log, then check again.",
        ),
        "waiting": (
            "Live check: no collector snapshot found yet.",
            "Next: enable the client collector mod and enter a world.",
        ),
        "error": (
            f"Live check: error: {result.get('error', 'the client log could not be read.')}",
            "Next: check that the log is readable and its latest collector line is valid.",
        ),
    }
    message, next_step = messages.get(
        status,
        ("Live check: error: unknown status.", "Next: check the client log and try again."),
    )
    print(message)
    print(next_step)
    if status == "error" or status not in {"disabled", "missing_log", "waiting"}:
        return 2
    return 1


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.ui and args.check_live:
        parser.error("--ui and --check-live cannot be used together.")
    if args.check_live and (
        args.list_targets
        or args.sample_graph
        or args.demo
        or args.observe_json is not None
        or args.current_json is not None
    ):
        parser.error("--check-live cannot be combined with other planner modes or observations.")
    if args.install_collector is not None and (
        args.ui
        or args.check_live
        or args.sample_graph
        or args.demo
        or args.list_targets
        or args.observe_json is not None
        or args.current_json is not None
    ):
        parser.error(
            "--install-collector cannot be combined with --ui, --check-live, "
            "--sample-graph, --demo, --list-targets, --observe-json, or --current-json."
        )

    if args.install_collector is not None:
        try:
            result = install_collector(args.install_collector)
        except (CollectorInstallError, OSError) as error:
            print(f"Unable to install collector: {error}", file=sys.stderr)
            return 2
        print(f"Collector install: {result['status']}")
        print(f"Destination: {result['destination']}")
        print(f"Version: {result['version']}")
        if result["backup_path"] is not None:
            print(f"Backup: {result['backup_path']}")
        print(
            "Next: enable the client collector in DST's Mods menu and re-enter the world, "
            "then run `python route_planner.py --check-live` and "
            "`python route_planner.py --ui`."
        )
        return 0

    if args.ui:
        from dst_route_planner.app import run_app

        try:
            live_log = resolve_live_log_path(args.live_log)
            run_app(
                port=args.port,
                open_browser=not args.no_browser,
                live_log=live_log,
            )
        except LiveLogDiscoveryError as error:
            print(f"Unable to resolve the client log: {error}", file=sys.stderr)
            return 2
        except OSError as error:
            print(f"Unable to start the local interface: {error}", file=sys.stderr)
            return 2
        return 0
    if args.check_live:
        try:
            live_log = resolve_live_log_path(args.live_log)
        except LiveLogDiscoveryError as error:
            return _report_live_check(
                {
                    "status": "error",
                    "log_path": "auto (unavailable)",
                    "error": str(error),
                }
            )
        return _report_live_check(inspect_live_log(live_log))
    kb = build_forest_default_kb()
    if args.sample_graph:
        graph = build_random_task_graph(kb, seed=args.seed)
        print(json.dumps({
            "seed": args.seed,
            "start_task": graph.start_task,
            "tasks": list(graph.tasks),
            "selected_optional_tasks": list(graph.selected_optional_tasks),
            "order": list(graph.order),
            "edges": [
                {
                    "parent_task": edge.parent_task,
                    "child_task": edge.child_task,
                    "forced": edge.forced,
                    "matched_keys": list(edge.matched_keys),
                }
                for edge in graph.edges
            ],
        }, indent=2))
        return 0
    if args.list_targets:
        print("Known targets:")
        for target in sorted(kb.target_chains):
            print(f"  {target:24} {len(kb.target_chains[target])} chain(s)")
        return 0
    if args.target not in kb.target_chains:
        print(f"Unsupported target: {args.target}")
        print(f"Known targets: {', '.join(kb.target_chains)}")
        return 2

    belief = initial_belief(kb)
    try:
        if args.current_json:
            current = observation_from_dict(json.loads(args.current_json.read_text(encoding="utf-8")))
            belief = update_belief(kb, belief, current)

        if args.observe_json:
            observations = load_direction_observations(args.observe_json)
        else:
            observations = demo_observations(args.target)
    except (OSError, ValueError) as error:
        print(f"Unable to read observations: {error}", file=sys.stderr)
        return 2

    scores = rank_directions(kb, args.target, belief, observations, seed=args.seed)
    probs = probabilities_by_direction(scores)

    print(f"Target: {args.target}")
    print("Current top task beliefs:")
    for name, prob in top_items(dict(belief.task_probs), 5):
        print(f"  {name:24} {prob:.3f}")

    print("\nDirection ranking:")
    for score in scores:
        print(
            f"  {score.direction.value:10} score={score.score:.3f} "
            f"p_dir={probs[score.direction.value]:.3f} "
            f"p_task={score.target_task_probability:.3f} "
            f"p_room={score.target_room_probability:.3f}"
        )
        print(f"    {'; '.join(score.explanation)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
