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

First install the repository's [`mods/dst_route_collector`](mods/dst_route_collector/README.md) into the game's `mods/` folder, which must already exist. On Windows, run this from the repository folder:

```powershell
python route_planner.py --install-collector "D:\SteamLibrary\steamapps\common\Don't Starve Together\mods"
```

Replace the example path with the game's actual `mods/` folder. You can also copy the whole folder by following the collector guide. After installation, enable DST Route Planner Live Collector in the game's client mod list and enter a world. The tool finds the client log automatically on startup. On Windows, double-click `start_planner.bat`, or run:

```powershell
python route_planner.py --ui
```

Select “检查连接” (check connection) to see the log path, coordinates, and observation summary, review terrain, landmarks, and passability checks, and follow the next step. Check “实时跟随” (live following) to show live positions and navigation suggestions in the page. While the tool runs, it records new snapshots in the background. If the log emits several snapshots at once, the tool records them in log order. The collector supplies coordinates and nearby clues once per second; the page recalculates directions automatically and shows straight-line distance when a target is visible. Move a little to check that coordinates change, then start exploring.

You can also check the connection from the terminal:

```powershell
python route_planner.py --check-live
```

For the first connection, watch the collector continuously:

```powershell
python route_planner.py --watch-live
```

It checks once per second and prints coordinates, camera heading, and an observation summary when a new snapshot or status change arrives. In the game, move, turn the camera, then pause and resume to check the updates; press `Ctrl+C` to end the check.

If your log lives elsewhere, use `--live-log "actual/path/client_log.txt"`. Explicit `--live-log auto` uses the same automatic discovery as the default. Leave live following unchecked for manual entry.

Directions use fixed world coordinates: north is `+Z` and east is `+X`. The map opens fitted to all observed areas. Select “全图” (Full map) to restore that view, or “跟随位置” (Follow position) to keep the latest position in a local view; “放大” (Zoom in) and “缩小” (Zoom out) change its range.

On the trail map, choose “路线终点” (route endpoint) or click an observed passable tile. The planner finds the route with the fewest grid steps over checked clear neighbor links. Collector 0.5.0 also checks the segment from your current position to your tile center. When that check passes, the route starts at your actual position and shows its total length and the next direction and coordinates. Next-step guidance also gives a ground direction relative to that frame’s camera heading (for example, “screen right”); it updates with new snapshots as you turn the camera, and replays use the selected frame’s heading. A blocked entry segment is reported; older data can still show tile-center routes. Routes recalculate as the player moves or new checks arrive, including in saved replays. The endpoint is the selected tile center, and each grid step is 4 world units. If no path connects the tiles, the page shows “未连通” (not connected). Switching worlds or collector sessions clears the endpoint.

During live following, a paused collector, an error, a manual stop, or a last valid snapshot older than five seconds pauses navigation. The map shows “导航已暂停” (navigation paused) and hides the purple live route and next-step guidance while keeping observed terrain, the last trail position, the route endpoint, and its target source. A live request that takes five seconds to complete times out; after the timeout, the page waits one second before retrying. Navigation resumes automatically when a fresh snapshot arrives; you do not need to toggle live following. Saved replay routes remain visible.

While the tool runs, it saves new snapshots to local JSONL files, including coordinates, nearby clues, the current target, and the direction suggestion at that time. When adding a snapshot would take the current replay part past 10,000 frames or 32 MiB, the tool starts the next part automatically. Earlier parts stay available, and each part can be downloaded, imported, and reviewed on its own. After a restart, new snapshots continue in the latest part for that world and collector session. Closing the page, viewing history, or turning off live following does not interrupt recording. Recording ends when you exit the Python tool (press Ctrl+C in the terminal).

The replay list initially shows the 10 most recent items. Select “显示更多回放” (Show more replays) to reveal older ones. Each part is labeled “第 N 段” (Part N). The live trail stays continuous across parts; history shows only the selected part through its final recorded frame.

While viewing a replay, use “上一段” (Previous part) and “下一段” (Next part) to move through recordings from the same world and collector session. Missing segment numbers are skipped. Frame-by-frame playback stays within the selected part.

“探索轨迹” (exploration trail) updates with live positions and marks the start and latest position. Select “查看轨迹” beside a saved replay to review it. Viewing a replay pauses live following; check it again to return to the current session. An existing or imported replay opens at its latest observed frame. Use “回放进度” (Replay progress), “上一帧” (Previous frame), “下一帧” (Next frame), or “跳到最新” (Go to latest) to step through recorded frames. Each frame shows only positions, terrain, connections, and targets observed by then. These history controls are hidden during live following while background recording continues.

In “探索回放” (exploration replays), choose “导入回放” (Import replay) to open a file picker, then select a JSONL file downloaded from the tool. It uploads automatically. After a successful upload, the page opens the imported trail if the current view has not changed. If you switch views or worlds during upload, the page keeps the current view; choose “查看导入轨迹” (View imported trail) to open the imported replay manually. Imported trails include positions, terrain, observed targets, and grid routes. North is `+Z` and east is `+X`; breaks in collection or sudden coordinate jumps leave gaps in the line.

The trail also marks where the selected target was previously seen. “已见目标” (observed targets) lists up to the 10 most recent sightings, with time, coordinates, direction, and straight-line distance relative to the latest player observation. Switch targets to review their sightings, including in saved replays. Each marker records the position at the time of observation; a moving or collected target may no longer be there. Choose “前往所在格” (Go to observed tile) in the list or click a map diamond to set the observed, passable tile at that recorded location as the route endpoint. The route shows which target sighting it came from and leads to the tile center. Select “前往最近可达目标” (Go to nearest reachable target) to choose the shortest checked route among all retained sightings of the current target. Once selected, that endpoint stays fixed while the route updates as you move.

“显示已观测地皮” (show observed tiles) adds the collected terrain beneath the trail, with colors for grass, forest, rock, marsh, water, and other tiles. The layer grows as you move and stays in saved replays; blank areas have not been collected. Caves also support positions, trails, and terrain recording; direction inference is still to come. Hatching marks tile centers that fail the ground-terrain check. Hover over a tile to see its passability; missing checks are shown as unknown. Turn the layer off to view just the trail and targets. To update an existing collector, rerun the install command above or follow the collector guide's manual copy steps, then re-enter the world.

Enable “显示邻格检查” (show neighbor checks) to view checked connections between observed neighboring tiles. The legend distinguishes clear and blocked connections in both live maps and saved replays; connections without a result stay blank.

## Manual entry and saved records

1. Choose a target.
2. Enter the tiles, prefabs, and counts you see in each direction.
3. Click “计算方向” to see the direction ranking and its clues.
4. Return to DST and save. After restarting, open the world from the record list and continue adding and saving observations.

The page includes demo observations and lets you import or export observation JSON. You can also add a record name and world note, then select Save, or select Save as new to keep a separate copy. After restarting, or using another browser or port with the same checkout, open the world from the record list, add observations, and save again. Observation JSON import and export keep their existing format.

Each save updates the record's current observations; click Save again after making changes.

```text
Install the collector → enable it in the game's client mod list and enter a world → start the tool; locate the log automatically
  ↓
Check connection / --watch-live → check movement, camera turns, pause and resume → choose a target
  ↓
Collect coordinates, tiles, landmarks, and ground passability each second
  ↓
Collector: check the player-to-tile-center segment and connections between observed neighbors
  ↓
Client log → Python records snapshots in log order and updates position and direction suggestions
  ↓
Match room/task clues and use task-graph context to rank exploration directions
  ↓
The page updates suggestions and straight-line distance to a visible target
  ↓
Observed target list or map diamond → Go to observed tile; or Go to nearest reachable target → set the route endpoint
  ↓
Use the player position to find a route and show the next move’s world direction, coordinates, and camera-relative ground direction
  ↓
Player moves or a new connection check arrives → update the route
  ↓
Collection pause / error / manual stop / stale snapshot → pause; request timeout → wait one second → retry; fresh snapshot → resume (no retries after stop or in history)
  ↓
New snapshots → local replay (automatically start another part before reaching a per-part limit) → page shows a continuous trail and route with observed tiles, latest position, and observed targets
  ↓
Choose “第 N 段” (Part N) → view its trail and route → Previous part / Next part within the same session → use the slider or frame buttons to review the selected part
  ↓
Download a part’s JSONL → import that part → view its trail and route
  ↓
Keep moving → collect, calculate, and update again
  ↓
Save current observations and world notes to continue next time
```

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
