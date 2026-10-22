# DST 实时采集器 / Live collector

这个轻量客户端 mod 每秒读取玩家坐标、当前地皮和附近可见的地标，把观测交给外置 Python 规划器。本机作为房主时也可以使用。

## 安装与连接

在仓库目录运行安装命令，并把参数设为已经存在的 DST `mods/` 目录：

```powershell
python route_planner.py --install-collector "D:\SteamLibrary\steamapps\common\Don't Starve Together\mods"
```

也可以手动将整个 `mods/dst_route_collector` 文件夹复制到 DST 的 `mods/` 下。之后在游戏的客户端模组列表启用 DST Route Planner Live Collector 并进入一个世界，再双击规划器的 `start_planner.bat` 或在仓库目录启动。工具会自动定位客户端日志：

```powershell
python route_planner.py --ui
```

工具运行期间会自动在后台记录新快照。在网页点“检查连接”查看连接状态；勾选“实时跟随”可显示实时位置和导航建议。移动角色，确认 X/Z 坐标跟着变化。关闭网页或取消实时跟随不会停止录制；退出 Python 工具（终端按 Ctrl+C）后录制结束。日志路径不同时，用 `--live-log "实际路径/client_log.txt"` 启动；终端也可用 `python route_planner.py --check-live` 检查。

For English setup, run the command above from the planner checkout and pass the existing DST `mods/` folder. You can also copy this whole folder manually. Then enable DST Route Planner Live Collector in the game's client mod list and enter a world. Start the planner after that. The tool automatically records new snapshots in the background while it runs. Select “检查连接” (check connection) to see the connection status; enable “实时跟随” (live following) to show live positions and navigation suggestions. Closing the page or turning off live following does not stop recording; recording ends when you exit the Python tool (press Ctrl+C in the terminal). Use `--live-log "actual/path/client_log.txt"` for another log location, or `python route_planner.py --check-live` for a terminal check. Move your character to check that X/Z updates.

更新现有安装时，可重新运行安装命令或手动复制采集器文件夹，然后在游戏中重新进入世界。0.5.0 版新增玩家当前位置到所在格中心的接入检查。 / To update an existing installation, rerun the install command or copy the collector folder manually, then re-enter the world. Version 0.5.0 adds an entry check from the player's current position to the center of the tile they occupy.

## 采集内容

采样半径是 16 个游戏坐标单位，当前位置附近使用 4 单位范围。更远的地皮和地标分到八个方向。北为 `+Z`，东为 `+X`，方位固定在世界坐标系中；镜头角度作为额外信息输出。

采集器结合实体可见状态与玩家地图探索状态筛选线索，记录 prefab 数量。地皮本身不足以判断房间连接，因此连接线索留给后续地图推理。看到已登记目标时，同时输出目标坐标，用于显示直线距离。

采集器还会枚举半径 16 单位内、地图已揭示格的中心与地皮类型，通过 `terrain: {tile_size:4,tiles:[{x,z,tile}]}` 发送给外置工具，绘制并保存地皮底图。格中心由游戏 API 提供，每格边长 4 世界单位；无地皮数据时省略这个字段。 / The collector also sends centers and types of nearby revealed tiles within 16 world units, using the optional `terrain` field above. Tile centers come from the game API; each tile is 4 world units wide. The external tool draws and saves this layer.

每格可选的 `passable` 布尔值来自 `Map:IsPassableAtPoint(x,0,z,false,true)`：只检查格中心地面地形，排除水和船平台。没有可用结果时省略该字段，外置工具显示未知；墙障碍由下述邻格检查处理。 / Each tile may include a boolean `passable` from the ground-terrain check at its center, excluding water and boat platforms. An unavailable result is omitted and shown as unknown. Registered wall obstacles are checked through the neighbor checks below.

同一份观测中的相邻格地形检查都通过时，采集器双向调用 `Pathfinder:IsClear`，记录该格 `connections` 对象中的 `east`（`x+4`）或 `north`（`z+4`）。两次布尔结果取 AND，保留受阻的 `false`；接口缺失、调用失败或非布尔结果时省略方向。每对邻格只记录一次，不查询未采到的格。选项保留 Pathfinder 的墙障碍检查并忽略 creep。 / When both observed neighboring centers pass the ground check, the collector checks the segment in both directions and stores the AND of the boolean results in `connections.east` or `connections.north`. Missing or failed checks stay unknown. Each pair is stored once, and unsampled tiles are not queried. Registered wall blockers participate in the check; creep is ignored.

快照还可能包含 `player_anchor: {x,z,clear}`。`x`、`z` 是游戏 API 返回的玩家所在格中心，并且只在该格已出现在 `terrain.tiles` 且中心 `passable` 为 `true` 时发送。采集器检查玩家当前位置的地面通行状态；若当前位置不通行，仍发送中心并将 `clear` 设为 `false`。当前位置可通行时，从实际玩家坐标到格中心双向调用 `Pathfinder:IsClear`，两次布尔结果取 AND。接口缺失、调用失败、非布尔结果、中心未采到或中心不通行时省略整个字段。每帧重新检查，不读取额外未揭示地形。 / A snapshot may also contain `player_anchor: {x,z,clear}`. Its coordinates are the tile center returned by the game API, and the field is sent only when that center is present in `terrain.tiles` with `passable: true`. The collector checks ground passability at the player's actual position. If that point is impassable, it still sends the center with `clear: false`; otherwise, it checks the path in both directions between the actual position and center, and ANDs the two boolean results. Missing APIs, failed calls, non-boolean results, an unsampled center, or an impassable center omit the field. It is recalculated every frame without querying additional unrevealed terrain.

每秒输出一行 `DST_ROUTE_PLANNER_LIVE_V1 ` 加标准 JSON。Python 读取最近完整的一行；超过五秒没有新快照时，网页暂停实时建议。游戏日志的实际写入和缓冲还需要完成首次游戏内连通验证，记录在根目录 TODO 中。

## 源码依据

以下路径相对 DST 的 `scripts/` 目录：

- `prefabs/player_common_extensions.lua:946-952`：玩家已探索地图的可见性检查，以及世界坐标到地皮索引的转换。
- `prefabs/player_common.lua:2304`：为玩家实例安装地图可见性方法。
- `components/playercontroller.lua:5102`：按世界坐标检查可见区域。
- `components/autoterraformer.lua:116`：世界坐标转换为地皮索引。
- `constants.lua:17`、`components/map.lua:447`：地皮边长 `TILE_SCALE = 4`。
- `debugcommands.lua:298-300`：按地皮索引检查地图可见性，读取格中心世界坐标。
- `entityscript.lua:1818-1820`、`componentutil.lua:1097-1107`：地形通行 API 的水与船平台参数。
- `actions.lua:168-184`：地面、船平台与水面的通行区别。
- `prefabs/world.lua:443-448`：世界初始化安装 Pathfinder。
- `components/penguinspawner.lua:261-263`：不忽略墙、忽略 creep 的 `IsClear` 调用。
- `components/locomotor.lua:1834-1849`：直连 LOS 检查与完整路径搜索分开处理。
- `prefabs/walls.lua:3-11`、`prefabs/fence.lua:312-320`：注册 Pathfinder 的墙障碍。
- `prefabs/compass.lua:23`：读取镜头角度。
- `worldgen_main.lua:473`、`mainfunctions.lua:1120`：世界会话及世界类型。
- `modutil.lua:340`、`gamelogic.lua:967`：世界载入后的初始化回调。
- `mods.lua:312`、`modindex.lua:678`：客户端 mod 环境与配置。
- `json.lua:163`、`json.lua:495`：外部 JSON 转义与空表编码；输出使用 `encode_compliant`，空观测保留对象字段。

Lua 桩测试执行本仓库的采集器，并模拟玩家移动、实体可见性和世界切换。测试无需安装游戏或读取上述外部源码。
