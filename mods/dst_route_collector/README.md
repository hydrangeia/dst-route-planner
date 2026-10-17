# DST 实时采集器 / Live collector

这个轻量客户端 mod 每秒读取玩家坐标、当前地皮和附近可见的地标，把观测交给外置 Python 规划器。本机作为房主时也可以使用。

## 安装与连接

1. 将仓库中的整个 `mods/dst_route_collector` 文件夹复制到 DST 安装目录的 `mods/` 下。
2. 在游戏的客户端模组列表中启用 DST Route Planner Live Collector，进入一个世界。
3. 双击规划器的 `start_planner.bat`，或在仓库目录启动。工具会自动定位客户端日志：

```powershell
python route_planner.py --ui
```

4. 在网页点“检查连接”，收到新快照后勾选“实时跟随”。移动角色，确认 X/Z 坐标跟着变化。日志路径不同时，用 `--live-log "实际路径/client_log.txt"` 启动；终端也可用 `python route_planner.py --check-live` 检查。

For English setup: copy this whole folder into the DST installation's `mods/` folder, enable it as a client mod, enter a world, run the command above from the planner checkout, then select “检查连接” (check connection) and enable “实时跟随” (live following). The tool locates the client log automatically; use `--live-log "actual/path/client_log.txt"` for another location, or `python route_planner.py --check-live` for a terminal check. Move your character to check that X/Z updates.

更新已有采集器时，重新复制这个文件夹并覆盖原文件，再重新进入世界。0.3.0 版新增地形通行检查。 / To update an existing installation, copy this folder over the previous files and re-enter the world. Version 0.3.0 adds ground-passability checks.

## 采集内容

采样半径是 16 个游戏坐标单位，当前位置附近使用 4 单位范围。更远的地皮和地标分到八个方向。北为 `+Z`，东为 `+X`，方位固定在世界坐标系中；镜头角度作为额外信息输出。

采集器结合实体可见状态与玩家地图探索状态筛选线索，记录 prefab 数量。地皮本身不足以判断房间连接，因此连接线索留给后续地图推理。看到已登记目标时，同时输出目标坐标，用于显示直线距离。

采集器还会枚举半径 16 单位内、地图已揭示格的中心与地皮类型，通过 `terrain: {tile_size:4,tiles:[{x,z,tile}]}` 发送给外置工具，绘制并保存地皮底图。格中心由游戏 API 提供，每格边长 4 世界单位；无地皮数据时省略这个字段。 / The collector also sends centers and types of nearby revealed tiles within 16 world units, using the optional `terrain` field above. Tile centers come from the game API; each tile is 4 world units wide. The external tool draws and saves this layer.

每格可选的 `passable` 布尔值来自 `Map:IsPassableAtPoint(x,0,z,false,true)`：只检查格中心地面地形，排除水和船平台。没有可用结果时省略该字段，外置工具显示未知；墙体与实体碰撞等检查留给路径采集。 / Each tile may include a boolean `passable` from the ground-terrain check at its center, excluding water and boat platforms. An unavailable result is omitted and shown as unknown. Walls and entity collisions will be added with path sampling.

每秒输出一行 `DST_ROUTE_PLANNER_LIVE_V1 ` 加标准 JSON。Python 读取最近完整的一行；超过五秒没有新快照时，网页暂停实时建议。游戏日志的实际写入和缓冲还需要完成首次游戏内连通验证，记录在根目录 TODO 中。

## 源码依据

以下路径相对 DST 的 `scripts/` 目录：

- `prefabs/player_common_extensions.lua:946`：玩家已探索地图的可见性检查。
- `prefabs/player_common.lua:2304`：为玩家实例安装地图可见性方法。
- `components/playercontroller.lua:5102`：按世界坐标检查可见区域。
- `components/autoterraformer.lua:116`：世界坐标转换为地皮索引。
- `constants.lua:17`、`components/map.lua:447`：地皮边长 `TILE_SCALE = 4`。
- `debugcommands.lua:298-300`：按地皮索引检查地图可见性，读取格中心世界坐标。
- `entityscript.lua:1818-1820`、`components/componentutil.lua:1104-1107`：地形通行 API 的水与船平台参数。
- `actions.lua:168-184`：地面、船平台与水面的通行区别。
- `prefabs/compass.lua:23`：读取镜头角度。
- `worldgen_main.lua:473`、`mainfunctions.lua:1120`：世界会话及世界类型。
- `modutil.lua:340`、`gamelogic.lua:967`：世界载入后的初始化回调。
- `mods.lua:312`、`modindex.lua:678`：客户端 mod 环境与配置。
- `json.lua:163`、`json.lua:495`：外部 JSON 转义与空表编码；输出使用 `encode_compliant`，空观测保留对象字段。

Lua 桩测试执行本仓库的采集器，并模拟玩家移动、实体可见性和世界切换。测试无需安装游戏或读取上述外部源码。
