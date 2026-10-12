# DST Mainland Route Inference Prototype

[中文](README.md)

This external Python prototype ranks candidate directions from visible ground tiles, prefabs, and directional clues to help search for a target item or landmark. The current knowledge base covers 20 tasks, 53 rooms, and 20 target prefabs in the default *Don't Starve Together* forest world. It does not read or modify the game and includes no Lua mod, screen collector, or HUD.

Treat the output as a **candidate direction ranking based on curated rules**. `p_dir` is each direction's normalized share of the ranking scores, not an empirically calibrated chance of success. The project has no real player-route dataset and makes no validated navigation-accuracy claim.

## Quick start

Python 3.10 or newer is required. The CLI uses only the Python standard library. Clone the repository and run from its root:

```powershell
git clone https://github.com/hydrangeia/dst-route-planner.git
cd dst-route-planner
python route_planner.py --demo
python route_planner.py --list-targets
python route_planner.py --target moonbase --observe-json examples/moonbase_observation.json
```

The default target is `panflute`. `--observe-json` loads observations for each direction. Optionally, `--current-json` supplies an observation at the current position and updates the initial belief:

```powershell
python route_planner.py --target panflute `
  --current-json examples/current_observation.json `
  --observe-json examples/panflute_observation.json
```

To run the development tests, install the development requirements and run pytest:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Development dependencies are not required to run the CLI.

## Supported targets

The table lists all 20 target prefabs currently registered in the knowledge base and their simplified task/room chains. Taskset-level setpieces are constrained by the generated task; they do not imply a fixed room.

| Target prefab | Main generation clue currently modeled |
|---|---|
| `antlion_spawner` | `Lightning Bluff` → `LightningBluffAntlion` |
| `beequeenhive` | `Beeeees!` → `BeeQueenBee` |
| `cave_entrance` | Taskset-level setpiece; modeled with an allowed-task list, no fixed room |
| `dragonfly_spawner` | `Badlands` → `DragonflyArena` |
| `lightninggoat` | `Lightning Bluff` → `LightningBluffLightning` |
| `mandrake_planted` | `For a nice walk` → `MandrakeHome` |
| `mermhouse` | `Squeltch` → `SlightlyMermySwamp` |
| `molehill` | Mole rooms under `Mole Colony Rocks`, `Mole Colony Deciduous`, or `Frogs and bugs` |
| `moonbase` | `Forest hunters` → `MoonbaseOne` |
| `moose_nesting_ground` | `MooseBreedingTask`; four nests support breeding-area identification, while a single nest is treated as a taskset constraint |
| `oasislake` | `Lightning Bluff` → `LightningBluffOasis` |
| `panflute` | `Speak to the king` → `MagicalDeciduous` → `DeciduousPond` |
| `pigking` | `Speak to the king` → `PigKingdom` |
| `resurrectionstone` | Taskset-level setpiece; modeled with an allowed-task list, no fixed room |
| `spiderden` | `Kill the spiders` → `SpiderVillage` |
| `statueglommer` | `Speak to the king` → `MagicalDeciduous` → `DeciduousPond` |
| `tentacle` | `Squeltch` → `Marsh` |
| `walrus_camp` | `Forest hunters` → `WalrusHut_Grassy` |
| `wasphive` | `Killer bees!` → `Waspnests`; related clues under `Beeeees!` are also recorded |
| `wormhole` | Taskset-level setpiece; modeled with an allowed-task list, no fixed room |

Run `--list-targets` to see the targets currently exposed by the CLI.

## Observation JSON

Directional observation files have a top-level `directions` object. Direction keys support the eight compass points. Each direction can contain these fields:

```json
{
  "directions": {
    "north": {
      "tile_types": ["DECIDUOUS"],
      "prefabs_seen": ["deciduoustree", "fireflies", "flower", "flower"],
      "prefab_counts": {"flower": 2, "fireflies": 1},
      "room_hints": [],
      "task_hints": [],
      "connection_like": true,
      "background_like": false,
      "note": "Deciduous forest edge"
    }
  }
}
```

- `tile_types` and `prefabs_seen`: in-game identifiers for visible ground tiles and prefabs. Identifiers are case-sensitive.
- `prefab_counts`: optional counts by prefab. If omitted, repeated values in `prefabs_seen` are counted. If both are provided, explicit counts take precedence and names found only in `prefabs_seen` receive a minimum count of 1.
- `room_hints` and `task_hints`: optional human-supplied names that should match the knowledge base.
- `connection_like` and `background_like`: optional boolean clues. When omitted, the model uses the other evidence it has.
- `note`: for people to read; it does not affect scoring.

`--current-json` takes one observation object with the same fields as a direction entry, without the outer `directions` object. Input examples are in [`examples/`](examples/).

In the output, `score` is the direction ranking score. `p_dir` is the normalized share of those scores and is not a calibrated probability of reaching the target. `p_task` and `p_room` are task and room belief values from the current rule model. Explanations list evidence that raised or lowered each direction's score.

## Current capabilities and limits

- Uses tile and prefab presence/absence, some count evidence, static layouts, optional human task/room hints, and connection/background hints to score tasks and rooms.
- Heuristically ranks directions and gives a boost to a direction where the target itself is visible.
- Includes an experimental task sampler that reproducibly selects 5 of 10 optional tasks when given a seed. `sample_task_graph` counts taskset membership; `build_random_valid_chain` returns only a strict lock/key-valid sequence, so a selected but currently unreachable optional task may be absent from the sequence. Distance estimates include only tasks that enter the sequence. For example, `Killer bees!` can be selected but omitted from the strict sequence when `Make a Beehat` was not selected. The prototype does not yet implement `storygen.lua`'s forced-connection fallback or model spatial adjacency, roads, or travel distance.
- The data is a curated slice of the default mainland knowledge base. Inference scores are not calibrated against in-game observations, and synthetic regression examples are not a substitute for gameplay evaluation.
- There is no in-game vision collector, Lua mod, HUD, persistent exploration map, or support yet for ocean, lunar-island terrain, cave biomes, boons, or late-game retrofit.

## Project structure

```text
route_planner.py                     CLI entry point
requirements-dev.txt                Development test dependencies
dst_route_planner/
  models.py                          Data models
  inference.py                       Task/room evidence scoring and belief updates
  navigation.py                      Direction scoring and ranking
  io.py                              Observation JSON loading
  cli.py                             CLI and built-in demos
  world_sampler.py                   Experimental lock/key task-chain sampler
  knowledge/forest_default.py        Default forest mainland knowledge base
examples/                            JSON observations and discrimination cases
test_knowledge_integrity.py          Knowledge-base integrity checks
test_world_sampler.py                Task sampler regression tests
test_phase*.py                       Regression tests
DST_GENERATION_RULES.md              Notes on task/room generation rules
TODO.md                              Roadmap
```

See [`DST_ROUTE_PLANNER_WORK.md`](DST_ROUTE_PLANNER_WORK.md) and [`PHASE_5A_COMPLETION_REPORT.md`](PHASE_5A_COMPLETION_REPORT.md) for historical records. They describe earlier work and are not current feature specifications or accuracy reports.
