# DST Mainland Route Planner

[中文](README.md)

Looking for a Pan Flute, Pig King, or Moonbase in *Don't Starve Together*? A lightweight client collector reads your character's coordinates, nearby tiles, and landmarks. The external Python page updates exploration suggestions as observations arrive. You can also enter clues manually, load examples, or reuse a world's saved record.

## Get started

You need Python 3.10 or newer. Clone the repository, then start the local web page from its folder:

```powershell
git clone https://github.com/hydrangeia/dst-route-planner.git
cd dst-route-planner
python route_planner.py --ui
```

On Windows, you can also double-click `start_planner.bat`. The page opens in your local browser; its current labels are in Chinese.

## Connect live observations

Install and enable [`mods/dst_route_collector`](mods/dst_route_collector/README.md) as a client mod, then enter a world. The tool finds the client log automatically on startup. On Windows, double-click `start_planner.bat`, or run:

```powershell
python route_planner.py --ui
```

Select “检查连接” (check connection) on the page to see the file being read and the next step. Once fresh snapshots arrive, check “实时跟随” (live following). The collector supplies coordinates and nearby clues once per second; the page recalculates directions automatically and shows straight-line distance when a target is visible. Move a little to check that coordinates change, then start exploring.

You can also check the connection from the terminal:

```powershell
python route_planner.py --check-live
```

If your log lives elsewhere, use `--live-log "actual/path/client_log.txt"`. Explicit `--live-log auto` uses the same automatic discovery as the default. Leave live following unchecked for manual entry.

Directions use fixed world coordinates: north is `+Z` and east is `+X`. Walkable routes around obstacles will follow as explored-map data is added.

While live following is active, the tool saves newly received snapshots locally, including coordinates, nearby clues, the current target, and direction suggestions. Download a JSONL file from “探索回放” (exploration replays) to keep the exploration session; saved replays remain available after restarting. Each world and collector session has its own recording.

“探索轨迹” (exploration trail) updates with live positions and marks the start and latest position. Select “查看轨迹” beside a saved replay to review that exploration; this pauses live following. Check live following again to return to the current session. North is `+Z` and east is `+X`; breaks in collection or sudden coordinate jumps leave gaps in the line.

The trail also marks where the selected target was previously seen. “已见目标” (observed targets) lists the last sighting time, coordinates, direction, and straight-line distance relative to the latest player observation. Switch targets to review their sightings, including in saved replays. Each marker records the position at the time of observation; a moving or collected target may no longer be there.

“显示已观测地皮” (show observed tiles) adds the collected terrain beneath the trail, with colors for grass, forest, rock, marsh, water, and other tiles. The layer grows as you move and stays in saved replays; blank areas have not been collected. Caves also support positions, trails, and terrain recording; direction inference is still to come. Hatching marks tile centers that fail the ground-terrain check. Hover over a tile to see its passability; missing checks are shown as unknown. Turn the layer off to view just the trail and targets. To update an existing collector, copy the repository's `mods/dst_route_collector` into the game's `mods/` folder again, then re-enter the world.

## Manual entry and saved records

1. Choose a target.
2. Enter the tiles, prefabs, and counts you see in each direction.
3. Click “计算方向” to see the direction ranking and its clues.
4. Return to DST and save. After restarting, open the world from the record list and continue adding and saving observations.

The page includes demo observations and lets you import or export observation JSON. You can also add a record name and world note, then select Save, or select Save as new to keep a separate copy. After restarting, or using another browser or port with the same checkout, open the world from the record list, add observations, and save again. Observation JSON import and export keep their existing format.

Each save updates the record's current observations; click Save again after making changes.

```text
Enable the collector and enter a world → start the tool; locate the log automatically
  ↓
Check connection → choose a target; collect coordinates, tiles, landmarks, and ground passability each second
  ↓
Client log → external Python; update the current position and directional clues
  ↓
Match room/task clues and use task-graph context to rank exploration directions
  ↓
The page updates suggestions and straight-line distance to a visible target
  ↓
New snapshots → local replay → trail with observed tiles, latest position, and observed targets
  ↓
Saved replay → view its trail or download coordinates, clues, and suggestions
  ↓
Keep moving → collect, calculate, and update again
  ↓
Save current observations and world notes to continue next time
```

The page marks observations stale if collection pauses for more than five seconds. Manual entry and JSON examples remain available.

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

The local Python engine ranks directions using 20 tasks, 53 rooms, 13 static layouts, and clues for 20 targets in the default mainland world. The task graph captures generation topology; automatically collected or manually entered tiles and landmarks add evidence from the area around you. Named records keep a target, world note, and current observations on this machine so you can continue after restarting.

The staged roadmap is in [`TODO.md`](TODO.md). Earlier development notes are in [`DST_ROUTE_PLANNER_WORK.md`](DST_ROUTE_PLANNER_WORK.md) and [`PHASE_5A_COMPLETION_REPORT.md`](PHASE_5A_COMPLETION_REPORT.md).
