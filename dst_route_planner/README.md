# `dst_route_planner` 包说明

[项目首页](../README.md) · [English overview](../README.en.md)

本包把玩家看到的地皮、prefab 数量和方位线索转成 task、room 线索分值，再按目标给方向排序。根目录 README 介绍快速使用；这里列出各目标对应的世界生成线索和 JSON 输入字段。

## 运行

从仓库根目录启动。Python 3.10+，运行 CLI 使用标准库：

```powershell
python route_planner.py --demo
python route_planner.py --list-targets
python route_planner.py --target moonbase --observe-json examples/moonbase_observation.json
python route_planner.py --target panflute --observe-json examples/panflute_observation.json --seed 17
python route_planner.py --sample-graph --seed 17
```

`--seed` 默认为 `0`，同样的输入会使用同一组抽样连接图。`--sample-graph` 可以把一张连接图输出成 JSON。

启动本地网页的其他选项：

```powershell
python route_planner.py --ui --port 8766
python route_planner.py --ui --no-browser
```

默认地址是 `http://127.0.0.1:8765/`。`--port` 可指定本机端口；`--no-browser` 只启动服务并在终端显示地址。网页可以载入排箫示例、导入或下载 JSON 观测，也可以保存命名探索记录。

也可以载入 `examples/current_observation.json` 补充当前位置线索；已填写的方向会保留。导出的观测 JSON 会一起保存目标、随机种子、方向观测和当前位置线索。记录另存名称和世界备注，并保存同一份当前观测快照。

运行开发测试。开发依赖包含执行 Lua 桩测试的 Lupa；网页状态回归使用 Node.js：

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

## 网页输入与 HTTP API

页面由本机 Python 服务提供。方向卡片支持四方位，并可切换到八方位；每个方向可录入地皮、prefab 数量和补充提示。`GET /api/options` 返回目标、地皮、prefab 和方向选项；`GET /api/demo` 返回内置排箫观测；`POST /api/plan` 接收 JSON 并返回排序结果。

`POST /api/plan` 使用 schema version 1，至少要包含 `schema_version`、`target`、`seed` 和 `directions`。`current` 是可选的当前位置观测。方向条目和 `current` 可使用以下字段：

- `tile_types`、`prefabs_seen`：地皮和 prefab 标识符数组。
- `prefab_counts`：prefab ID 到非负整数数量的对象。
- `room_hints`、`task_hints`：可选的房间与 task 名称数组。
- `connection_like`、`background_like`：可选布尔值。
- `note`：可选备注文本。

请求示例：

```json
{
  "schema_version": 1,
  "target": "panflute",
  "seed": 0,
  "directions": {
    "north": {
      "tile_types": ["DECIDUOUS"],
      "prefab_counts": {"deciduoustree": 3, "flower": 2}
    }
  },
  "current": {
    "tile_types": ["GRASS"],
    "prefabs_seen": ["evergreen"]
  }
}
```

响应中的 `directions` 按推荐顺序列出 `direction`、`score`、`p_dir`、`p_task`、`p_room` 和 `explanation`。`current_tasks` 返回应用可选当前位置观测后的高分 task 信念。页面导出的观测 JSON 可以直接重新导入；页面也接受现有的无版本观测文件。

## 实时观测

启用 [`客户端采集器`](../mods/dst_route_collector/README.md) 后，用 `--ui --live-log <客户端日志路径>` 启动，再在页面勾选“实时跟随”。采集器把一秒一份的快照写入游戏日志，Python 读取最近的完整快照，更新坐标和方向建议。

实时快照采用独立的 `live_version: 1`，包括 `world_id`、`world_kind`、`session_id`、`sequence`、Unix 时间 `captured_at`、`position: {x,y,z}`、`camera_heading`、`current`、`directions`，以及可选的 `landmarks: [{prefab,x,z}]`。其中观测字段沿用现有的 observation 格式。世界坐标约定北为 `+Z`、东为 `+X`；镜头角度作为独立信息提供。

`GET /api/live?target=panflute&seed=0` 返回连接状态、快照和可用的 `plan`。`plan` 与 `/api/plan` 的结果格式相同。看到所选目标时，`visible_target` 提供最近目标的坐标与直线距离。超过五秒的快照会标记为 `stale`，停止生成实时建议。当前大陆知识库处理 `forest` 世界，其他世界会显示 `unsupported_world`。

这一版根据当前快照排列探索方向。探索轨迹、可通行地图和绕障碍的路径重规划列在 [`TODO.md`](../TODO.md)。采集器的 Lua 接口已对照本地源码，并通过桩环境检查；首次游戏内连通验证还需要启用 mod 后完成。

## 连续探索回放

网页实时跟随时，`/api/live` 收到的新快照会自动追加到 `.dst-route-planner/explorations/`。文件按世界和采集会话分开，重复轮询同一份快照不会重复记录。大陆保存坐标、线索、目标、随机种子和方向建议；洞穴先保存收到的坐标与线索。已有的命名记录继续保存当前观测快照。

在“探索回放”中可查看已记录的快照数量并下载 JSONL。下载文件的首行是 `replay_version: 1` 的会话信息，包含 `id`、`world_id`、`world_kind` 和 `session_id`；后续每行包含 `replay_version`、`received_at`、`target`、`seed`、完整的 `snapshot`，以及有方向建议时的 `plan`。快照内的 `captured_at` 和 `sequence` 保留采集时刻与顺序，方便之后复盘移动过程。

- `GET /api/explorations` 返回 `explorations` 摘要列表，最近的记录排在前面。
- `GET /api/explorations/<id>` 下载这次会话的 JSONL 文件。
- `/api/live` 的 `recording` 返回记录 ID、快照数量和保存状态；存储失败时网页提示问题，实时坐标与建议继续更新。

每个会话最多记录 10,000 份快照或 32 MiB，达到上限后保留已有文件供下载。回放保存在本机并由 Git 忽略。探索轨迹可以直接在网页查看；地点标记与可通行路径仍按路线图继续实现。

## 探索轨迹

“探索轨迹”按世界坐标绘制已观测的位置，北为 `+Z`、东为 `+X`，两个坐标轴使用相同比例。图上标出起点与最新位置；停在同一地点时也能看到位置标记。相邻快照的时间间隔超过五秒、时间没有前进，或位置相距超过 64 单位时，会断开轨迹线。

实时跟随首次连接一段回放时读取已有轨迹，之后把收到的新位置追加到图上。在已保存回放旁点击“查看轨迹”会暂停实时跟随；重新勾选后显示当前会话。轨迹读取失败时，当前坐标、方向建议和回放下载仍可使用。 可以点击“刷新轨迹”重新读取。图上最多显示 10,000 个位置；超出时保留起点与最近的 9,999 个位置，页面会提示。

`GET /api/explorations/<id>/trail` 返回 `trail_version: 1`、会话标识、`frame_count`、`points` 和 `bounds`。每个点包含 `sequence`、`captured_at`、`x`、`z`；边界包含 `min_x`、`max_x`、`min_z`、`max_z`，没有位置时为 `null`。接口只投影已有回放，不修改记录。

轨迹图连接已观测的位置。地皮、障碍和可行走路径会在后续地图功能中接入。

## 探索记录

页面支持保存当前探索记录、另存为新记录、列出已有记录并打开记录。每条记录保存一个当前快照，包括名称、世界备注、目标、随机种子、各方向观测和可选的 `current`。每次保存会更新当前快照；修改观测后再点击保存。

记录存放在当前仓库目录的 `.dst-route-planner/records/` 下，并由 Git 忽略。同一份 checkout 重启工具后仍可读取这些记录；用该 checkout 启动另一个浏览器会话或端口时，也能看到相同的记录。

记录 HTTP API：

- `GET /api/records` 返回记录摘要列表，例如：`{"records":[{"id":"<uuid>","name":"主世界排箫搜索","target":"panflute","saved_at":"<timestamp>"}]}`。
- `GET /api/records/<uuid>` 返回完整记录，形状如下：

```json
{
  "record_version": 1,
  "id": "<uuid>",
  "name": "主世界排箫搜索",
  "world_note": "出生点在桦树林附近",
  "saved_at": "<timestamp>",
  "observation": {
    "schema_version": 1,
    "target": "panflute",
    "seed": 0,
    "directions": {}
  }
}
```

- `POST /api/records` 接收同样的对象，但不包含 `saved_at`；`id` 可省略。

`observation` 使用现有的 schema version 1 观测结构。记录元数据不属于 `/api/plan` 的输入；普通 JSON 导入和导出仍只处理原有观测格式。

## 目标与世界生成线索

知识库登记 20 种目标。表格列出相关 task、room、setpiece 与可见地标。taskset 级 setpiece 会随生成 task 出现在不同区域，表中列出对应布局。

| 目标 prefab | task / room / layout | 可观察的相关地标 |
|---|---|---|
| `antlion_spawner` | `Lightning Bluff` → `LightningBluffAntlion` → `AntlionSpawningGround` | `oasis_cactus`, `houndbone`, `marsh_bush` |
| `beequeenhive` | `Beeeees!` → `BeeQueenBee` | `beehive`, `wasphive`, `flower` |
| `cave_entrance` | taskset 中多个 task → `CaveEntrance` layout | `rock1`, `rock2`, `evergreen`, `grass` |
| `dragonfly_spawner` | `Badlands` → `DragonflyArena` → `DragonflyArena` layout | `cactus`, `houndbone`, `rock_flintless`, `marsh_tree` |
| `lightninggoat` | `Lightning Bluff` → `LightningBluffLightning` | `oasis_cactus`, `marsh_bush`, `houndbone` |
| `mandrake_planted` | `For a nice walk` → `MandrakeHome` | `evergreen`, `flower`, `fireflies` |
| `mermhouse` | `Squeltch` → `SlightlyMermySwamp` | `tentacle`, `marsh_tree`, `marsh_bush`, `reeds` |
| `molehill` | `Mole Colony Rocks` → `MolesvilleRocky`; `Mole Colony Deciduous` → `DeciduousMole`; `Frogs and bugs` → `GrassyMoleColony` | rocks, deciduous trees, flowers, and nearby prefab counts |
| `moonbase` | `Forest hunters` → `MoonbaseOne` | `evergreen`, `sapling`, `grass` |
| `moose_nesting_ground` | `MooseBreedingTask` → `MooseGooseBreedingGrounds`; single-nest setpieces also appear in a taskset allowlist | Four nests point to the breeding area; a single nest is task-level evidence |
| `oasislake` | `Lightning Bluff` → `LightningBluffOasis` → `Oasis` layout | `oasis_cactus`, `houndbone`, `buzzardspawner` |
| `panflute` | `Speak to the king` → `MagicalDeciduous` → `DeciduousPond` | `pigking`, `statueglommer`, `deciduoustree`, `fireflies` |
| `pigking` | `Speak to the king` → `PigKingdom` → `DefaultPigking` layout | `pighouse`, `deciduoustree`, `statueglommer` |
| `resurrectionstone` | taskset 中多个 task → `ResurrectionStone` layout | `gravestone`, `rock1`, `evergreen`, `grass` |
| `spiderden` | `Kill the spiders` → `SpiderVillage` | `rock1`, `rock2`, `goldnugget` |
| `statueglommer` | `Speak to the king` → `MagicalDeciduous` → `DeciduousPond` | `pigking`, `panflute`, `deciduoustree`, `fireflies` |
| `tentacle` | `Squeltch` → `Marsh` | `reeds`, `pond_mos`, `marsh_tree` |
| `walrus_camp` | `Forest hunters` → `WalrusHut_Grassy` | `grass`, `pond`, `evergreen` |
| `wasphive` | `Killer bees!` → `Waspnests`; also `Beeeees!` → `BeeQueenBee` | `flower`, `beehive`, `grass`; Bee Queen landmarks on the second route |
| `wormhole` | taskset 中多个 task → `WormholeGrass` layout | `grass`, `rocks`, `sapling`, `evergreen` |

`cave_entrance`、`resurrectionstone` 和 `wormhole` 的候选 task 清单定义在 `knowledge/forest_default.py`。四个 `moose_nesting_ground` 的观测支持区分繁殖区的四巢布局与单巢 setpiece。

## Task 连接图

默认大陆 task 图从起始 task 开始，依据累计获得的 keys 把 task 连起来。连接时会记录哪些 key 让这个 task 接入；当没有尚未连接且满足 locks 的 task 时，worldgen 会把一个剩余 task 接到最近加入的 task 上，`forced` 标记能区分这类 fallback 边。

图里的连接关系按无向边处理，并用 BFS 计算 task 之间的最短跳数。导航把多次抽样得到的图距离汇总成 task 区域间的拓扑接近度，再与地皮、prefab、目标 room 等观察一起排列方向。

运行 `python route_planner.py --sample-graph --seed 17` 会输出这些 JSON 字段：

- `seed`：本次抽样使用的随机种子。
- `start_task`：图的起始 task。
- `tasks`：这次图中的 task。
- `selected_optional_tasks`：从 optional task 中选中的五个。
- `order`：task 加入图的顺序。
- `edges`：连接数组，含 `parent_task`、`child_task`、`forced` 和 `matched_keys`。

用相同 seed 可以复现抽样结果。默认值是 `0`。

## 输入 JSON

方向观测文件的顶层键是 `directions`，每个方向提供一份 observation：

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
      "note": "落叶林边界，像可以进入的 room"
    }
  }
}
```

- `tile_types`、`prefabs_seen` 使用游戏 prefab 和地皮标识符，大小写敏感。
- `prefab_counts` 可选。省略时会从 `prefabs_seen` 的重复项计数；同时提供时，数量表优先，额外列出的 prefab 至少计为 1。
- `room_hints`、`task_hints` 是可选的人工判断，名称应与知识库对应。
- `connection_like`、`background_like` 可用 `true` 或 `false` 表示方向观察；省略时不提供这类额外线索。
- `note` 供阅读，不参与计算。

`--current-json` 使用一份 observation 对象，字段同方向条目，但不带外层 `directions`。现成文件见 [`examples/`](../examples/)。

## 输出字段

- `score`：方向的综合排序分。
- `p_dir`：各候选方向分数归一化后的相对份额。
- `p_task`、`p_room`：观测对应到目标相关 task 和 room 的分值。
- explanation：说明可见地标、方向连接线索和目标相关性如何影响推荐。

## 包内模块

- `models.py` 定义 task、room、静态布局、观测、信念状态和方向得分。
- `knowledge/forest_default.py` 保存默认大陆的 task、room、setpiece 与目标线索。
- `inference.py` 根据地皮和 prefab 证据更新 task/room 分值。
- `navigation.py` 汇总目标线索并排列方向。
- `io.py` 读取方向观测和当前位置 JSON。
- `cli.py` 提供命令行、演示和目标列表。
- `app.py` 提供本地网页服务和方向计算 API，`static/app.html` 是观测录入与结果页面。
- `records.py` 保存和读取命名探索记录。
- `live.py` 校验并读取客户端日志中的实时快照，判断数据新鲜度和可见目标距离。
- `exploration.py` 保存连续探索回放并提供摘要和下载。
- `trail.py` 从回放提取世界坐标和轨迹边界。
- `world_sampler.py` 抽取带锁/钥匙来源记录的 task 连接图，并以 BFS 最短跳数计算图上的 task 接近度。

当前项目进度和下一步计划见根目录的 [`README.md`](../README.md) 与 [`TODO.md`](../TODO.md)。
