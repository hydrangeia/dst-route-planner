# DST Mainland Route Planner

[中文](README.md)

Looking for a Pan Flute, Pig King, or Moonbase in *Don't Starve Together*? Open the local web page, choose a target, and enter the tiles and landmarks you see in each direction. The planner ranks where to explore next and shows the clues behind its suggestions.

## Get started

You need Python 3.10 or newer. Clone the repository, then start the local web page from its folder:

```powershell
git clone https://github.com/hydrangeia/dst-route-planner.git
cd dst-route-planner
python route_planner.py --ui
```

On Windows, you can also double-click `start_planner.bat`. The page opens in your local browser; its current labels are in Chinese.

## Using the planner

1. Choose a target.
2. Enter the tiles, prefabs, and counts you see in each direction.
3. Click “计算方向” to see the direction ranking and its clues.
4. Explore in DST, update the observations, and calculate again.

The page includes demo observations and lets you import or export observation JSON.

```text
Choose a target and enter visible tiles and landmarks for each direction
  ↓
Python matches the observations to room and task clues in its knowledge base
  ↓
Task-graph context and visible evidence rank the directions
  ↓
Review the suggested direction and the reasons behind it
  ↓
Explore in DST, update the observations, and calculate again
```

For now, enter observations in the web page. A future in-game collector can send the same JSON observations to the Python engine.

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

JSON fields and CLI examples are documented in [`dst_route_planner/README.md`](dst_route_planner/README.md).

## Current state

The local Python engine ranks directions using 20 tasks, 53 rooms, 13 static layouts, and clues for 20 targets in the default mainland world. The task graph captures generation topology; the tiles and landmarks entered in the page add evidence from the area around you.

The staged roadmap is in [`TODO.md`](TODO.md). Earlier development notes are in [`DST_ROUTE_PLANNER_WORK.md`](DST_ROUTE_PLANNER_WORK.md) and [`PHASE_5A_COMPLETION_REPORT.md`](PHASE_5A_COMPLETION_REPORT.md).
