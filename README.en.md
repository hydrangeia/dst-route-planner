# DST Mainland Route Planner

[中文](README.md)

Give DST Route Planner the tiles and landmarks you can see in each direction as JSON, and it ranks where to explore next for the Pan Flute, Pig King, Moonbase, and other mainland targets. It uses the default forest world's task and room generation rules.

## Get started

You need Python 3.10 or newer. In PowerShell, clone the repository and run the built-in demo:

```powershell
git clone https://github.com/hydrangeia/dst-route-planner.git
cd dst-route-planner
python route_planner.py --demo
```

List targets or run with observations for each direction:

```powershell
python route_planner.py --list-targets
python route_planner.py --target moonbase --observe-json examples/moonbase_observation.json
```

The default target is `panflute`. You can also provide clues from your current position alongside the observations around you:

```powershell
python route_planner.py --target panflute `
  --current-json examples/current_observation.json `
  --observe-json examples/panflute_observation.json
```

To run the development tests, install the development requirements first:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

## Reading the direction ranking

The output lists each direction, its score, and clues relevant to the target:

```text
north  score=... p_dir=... p_task=... p_room=...
       looks like target task Speak to the king; looks like target room MagicalDeciduous
```

`score` ranks the directions. `p_dir` is each candidate's share after the scores are normalized. `p_task` and `p_room` show how well the observation matches a task and room related to the target. The explanation says which tile, prefab, or connection clues affected the score. Seeing the target prefab gives that direction a strong boost.

## Targets

The knowledge base currently includes 20 target prefabs. These friendly names map to the prefab IDs used by JSON observations and `--target`:

| 中文名称 | English name | prefab ID |
|---|---|---|
| 蚁狮地形点 | Antlion sinkhole | `antlion_spawner` |
| 蜂后蜂巢 | Bee Queen hive | `beequeenhive` |
| 洞穴入口 | Cave entrance | `cave_entrance` |
| 龙蝇竞技场 | Dragonfly arena | `dragonfly_spawner` |
| 电羊 | Volt goat | `lightninggoat` |
| 曼德拉草 | Mandrake | `mandrake_planted` |
| 鱼人房 | Merm house | `mermhouse` |
| 鼹鼠丘 | Molehill | `molehill` |
| 月台 | Moonbase | `moonbase` |
| 麋鹿鹅巢 | Moose/goose nest | `moose_nesting_ground` |
| 绿洲湖 | Oasis lake | `oasislake` |
| 排箫 | Pan flute | `panflute` |
| 猪王 | Pig King | `pigking` |
| 复活石 | Touch Stone | `resurrectionstone` |
| 蜘蛛巢 | Spider den | `spiderden` |
| 格罗姆雕像 | Glommer statue | `statueglommer` |
| 触手 | Tentacle | `tentacle` |
| 海象营地 | Walrus camp | `walrus_camp` |
| 杀人蜂巢 | Wasp hive | `wasphive` |
| 虫洞 | Wormhole | `wormhole` |

For each target's task, room, and setpiece clues, see [`dst_route_planner/README.md`](dst_route_planner/README.md#目标与世界生成线索).

## Enter observations

The `--observe-json` file has a top-level `directions` object, with one entry for each compass direction. Here is a short example:

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

`tile_types` and `prefabs_seen` use the identifiers found in game and must match the knowledge-base spelling. Repeating a prefab records its count; you can also provide counts directly with `prefab_counts`. `room_hints` and `task_hints` are optional manual clues. `connection_like` and `background_like` are optional booleans. The `note` is for people reading the file.

`--current-json` takes one observation with the same fields as a direction entry, without the outer `directions` object. Start with a file in [`examples/`](examples/) and edit it to match what you see.

## Current state

The Python engine ranks directions from JSON observations. Its knowledge base covers 20 tasks, 53 rooms, 13 static layouts, and these 20 targets in the default mainland world. Sampled task graphs use the generation rules to compare how many connections separate task areas. Next, the project will collect visible terrain in game and add a HUD for choosing a target and viewing direction suggestions.

The staged roadmap is in [`TODO.md`](TODO.md). Earlier development notes are in [`DST_ROUTE_PLANNER_WORK.md`](DST_ROUTE_PLANNER_WORK.md) and [`PHASE_5A_COMPLETION_REPORT.md`](PHASE_5A_COMPLETION_REPORT.md).
