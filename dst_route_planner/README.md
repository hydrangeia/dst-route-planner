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

### 安装客户端采集器

从仓库根目录运行安装命令，并传入已经存在的 DST `mods/` 目录：

```powershell
python route_planner.py --install-collector "D:\SteamLibrary\steamapps\common\Don't Starve Together\mods"
```

命令只会复制或更新 `collector.lua`、`modmain.lua` 和 `modinfo.lua` 到该目录下的 `dst_route_collector/`，并保留目标文件夹中的其他文件和其他 mod。替换内容有变化的旧 Lua 文件前，会把旧文件备份到仓库的 `.dst-route-planner/collector-backups/`；再次运行且文件内容相同时，不会改动目标文件或备份。命令会报告安装目标、采集器版本、备份位置（如有）和后续操作。随后在游戏客户端模组列表启用采集器、重新进入世界，运行 `python route_planner.py --check-live` 检查连接，再用 `python route_planner.py --ui` 打开网页。

也可以按 [`采集器说明`](../mods/dst_route_collector/README.md) 手动复制整个 `mods/dst_route_collector` 文件夹。

启动本地网页的其他选项：

```powershell
python route_planner.py --ui --port 8766
python route_planner.py --ui --no-browser
python route_planner.py --check-live
python route_planner.py --ui --live-log "实际路径/client_log.txt"
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

启用 [`客户端采集器`](../mods/dst_route_collector/README.md) 后，用 `--ui` 启动，点击“检查连接”，收到新快照后再勾选“实时跟随”。采集器把一秒一份的快照写入游戏日志；网页读取最新完整快照，更新坐标和方向建议。

实时快照采用独立的 `live_version: 1`，包括 `world_id`、`world_kind`、`session_id`、`sequence`、Unix 时间 `captured_at`、`position: {x,y,z}`、`camera_heading`、`current`、`directions`，以及可选的 `landmarks: [{prefab,x,z}]` 和 `terrain: {tile_size:4,tiles:[{x,z,tile}]}`。地皮坐标为引擎给出的格中心，每格边长为 4 个世界单位；只采集玩家附近、地图已揭示的格。每份快照最多接受 256 格，同一份内的格中心不能重复。旧快照可省略 `terrain`。每格还可携带 `passable` 布尔值；`true` 或 `false` 表示格中心的地形通行检查结果，省略表示未知，`null` 或其他类型会被拒绝。每格的可选 `connections` 对象可包含布尔值 `east`、`north`，分别表示到世界坐标 `x+4`、`z+4` 相邻格的双向直连检查结果。包含这些结果时，本格及对应邻格必须都在本份快照中且 `passable: true`；省略对象或某个方向表示未知。其中观测字段沿用现有的 observation 格式。世界坐标约定北为 `+Z`、东为 `+X`；镜头角度作为独立信息提供。

可选的 `player_anchor: {x,z,clear}` 记录玩家当前位置到所在格中心的接入检查。`x`、`z` 必须引用本份 `terrain` 中 `passable: true` 的格，且该格是唯一包含玩家位置的已采格；格的范围为 `[x-2,x+2)`、`[z-2,z+2)`。`clear` 是严格布尔值，`false` 保留受阻结果。该对象必须恰好包含这三个字段；旧快照可省略。

`GET /api/live?target=panflute&seed=0` 返回连接状态、最新快照和可用的 `plan`。`plan` 与 `/api/plan` 的结果格式相同。看到所选目标时，`visible_target` 提供最近目标的坐标与直线距离。超过五秒的快照会标记为 `stale`，不再生成实时建议。接口读取最新完整的标记行；若该行无效，会返回错误，不回退到更早的快照。网页读取只用于显示，不会推进后台录制位置。当前大陆知识库处理 `forest` 世界，其他世界会显示 `unsupported_world`。

这一版根据当前快照排列探索方向，也可在地图上选择已观测且可通行的格作为路线终点，沿已检查通过的相邻格连接查看最少步数路线。轨迹图保存已见目标并显示已观测地皮。采集器的 Lua 接口已对照本地源码并通过桩环境检查；首次游戏内连通验证仍待启用 mod 后完成。

## 自动定位与连接检查

`--ui`、`--check-live` 和 `--watch-live` 默认自动定位客户端日志；`--live-log auto` 显式选择同一行为，也可以用 `--live-log <路径>` 指定文件。Windows 使用系统当前的文档目录，包含重定向后的目录；macOS 使用 `~/Documents/Klei/DoNotStarveTogether/client_log.txt`，Linux 使用 `~/.klei/DoNotStarveTogether/client_log.txt`。默认日志位置依据 [Klei 的日志说明](https://support.klei.com/hc/en-us/articles/360029881191-Logs-and-Useful-Information-for-Bug-Reports-for-Don-t-Starve-Together)。

网页的“检查连接”和终端的 `python route_planner.py --check-live` 都会显示所选日志、当前连接状态和下一步操作。检查只读取最新的完整快照，不追加回放。运行 `python route_planner.py --ui` 后，后台独立录制探索快照；网页是否打开、是否实时跟随都不影响录制。

`python route_planner.py --watch-live` 每秒检查一次，持续等待游戏或采集器就绪。新快照和连接状态改变时输出一行状态、序号、新鲜度、世界类型、X/Z 坐标、镜头朝向，以及地标、地皮、通行与连接检查摘要；同一份快照的新鲜度递增不会重复刷屏，超过五秒后仍会报告 `stale`。读取错误后继续等待后续有效快照；按 `Ctrl+C` 正常结束并返回 `0`，启动时无法定位日志则返回 `2`。可用 `--live-log <路径>` 指定检查文件。

单次终端检查的退出码：`0` 表示收到新鲜快照，`1` 表示还需启动游戏、启用采集或恢复游戏，`2` 表示文件读取或快照格式出错。洞穴中的新鲜快照也表示采集器已连接，方向推理仍按世界支持情况处理。

`GET /api/live-check` 返回 `check_version: 1`、`status` 和 `log_path`，并在可用时提供 `age_seconds`、`world_kind`、`sequence`、`position`，以及来自同一份快照的 `captured_at` 和 `camera_heading`；出错时提供 `error`。状态为 `disabled`、`missing_log`、`waiting`、`live`、`stale` 或 `error`。有最近有效快照时（`live` 或 `stale`），响应还会增加可选的 `observation_summary`，并由同一份已校验快照生成。字段包括 `landmarks`（地标数量）、`terrain_available`（是否提供地形）、`terrain_tiles`（地皮数量）、`passable_tiles`、`blocked_tiles`、`unknown_tiles`（分别为可通行、受阻和状态未知的地皮数）、`clear_connections`、`blocked_connections`（已检查连接中通过和受阻的数量）以及 `player_anchor`（`clear`、`blocked` 或 `unknown`，表示玩家到所在格中心的接入检查状态）。旧快照缺少可选数据仍可读取；未提供地形时，地皮和连接计数为 0，`player_anchor` 为 `unknown`。等待数据、日志缺失或快照无效时不提供摘要。快照过期时仍显示摘要且状态保持 `stale`；网页收到新鲜快照前不会恢复导航。`observation_summary` 是 `check_version: 1` 响应中的可选字段，不改变版本号，旧响应仍兼容。这个接口不调用规划器，也不追加回放。

## 连续探索回放

运行 `python route_planner.py --ui` 时，后台读取器每秒扫描客户端日志末尾的 1 MiB，并按日志顺序处理其中完整的快照行，写入 `.dst-route-planner/explorations/`；录制不依赖网页轮询。不同世界和采集会话分别保存。森林记录包含坐标、线索、目标、随机种子和方向建议；洞穴先保存收到的坐标与线索。坏行会跳过并继续处理后续有效行，最后一行尚未写完时留到下次扫描。仍只记录最近五秒内的新鲜快照，过期帧不补录；重复的 `sequence` 不会重复记录。扫描范围限于日志末尾 1 MiB，离线或积压期间超出此范围的历史帧不保证补录。关闭网页、查看历史回放或取消“实时跟随”不会停止后台录制；只有退出 Python 工具时录制才结束。已有的命名记录继续保存当前观测快照。

每份回放段最多包含 10,000 帧且不超过 32 MiB。若追加下一份快照会让当前段超过任一上限，后台会在写入该快照前创建下一段；旧段文件保留。分段沿用同一 `world_id`、`world_kind` 和 `session_id`，快照的原始 `sequence` 跨段递增，不在边界重置。重启工具后，新鲜快照继续写入该会话最新一段；若最新一段已满，再按同一规则开始下一段。每段自身只包含该段的帧。

初次启动时后台规划使用 `panflute` 和随机种子 `0`。之后采用最近一次有效 `GET /api/live` 请求中的 `target` 与 `seed`；网页更改目标后，会在下一次实时请求时同步给后台规划。森林回放保存对应方向建议；洞穴快照照常记录，方向推理仍按世界支持情况处理。自动读取不会改变观测 JSON 或 `replay_version: 1` 的回放格式；手动观测、命名记录和早先导出的回放仍按原有规则使用。

在“探索回放”中可查看已记录的快照数量并下载 JSONL。每段标为“第 N 段”，都可单独下载、导入和查看。列表初次显示最近 10 项；点“显示更多回放”可显示较早的回放段。下载文件的首行是 `replay_version: 1` 的会话信息，包含 `id`、`world_id`、`world_kind` 和 `session_id`；第二段及之后还包含可选的 `segment`。后续每行包含 `replay_version`、`received_at`、`target`、`seed`、完整的 `snapshot`，以及有方向建议时的 `plan`。快照内的 `captured_at` 和 `sequence` 保留采集时刻与顺序，方便之后复盘移动过程。

第一段沿用现有的确定性 ID，且其文件头、摘要和轨迹响应都省略 `segment`，因此已有回放的身份和结构不变。第二段及之后使用会话三元组与段号生成各自确定的 ID；文件头中的 `segment` 必须是 JSON 整数，范围为 2 到 `2**53 - 1`。相应摘要和轨迹响应会带上该段的 `segment`。这些可选字段不改变 `replay_version: 1` 或 `trail_version: 1`，旧的无 `segment` 回放按第一段读取。

- `GET /api/explorations` 返回 `explorations` 摘要列表，最近的记录排在前面。
- `GET /api/explorations/<id>` 下载这次会话的 JSONL 文件。
- `/api/live` 的 `recording` 返回当前会话最新一段的记录 ID、段号（第一段省略）、快照数量和保存状态。网页请求与后台读取共用同一份回放，重复 `sequence` 不会重复追加；存储失败时网页提示问题，实时坐标与建议继续更新。跨段时，实时页保留有上限的本地轨迹连续性，新段 JSONL 只保存本段的帧。

`POST /api/explorations/import` 接收原始 UTF-8 `application/x-ndjson` 内容。有效回放必须满足严格的版本、会话身份和帧序号校验；每个文件（单独一段）最多 10,000 帧、32 MiB。旧回放可以没有地皮或 `player_anchor`，缺失字段保持为空。导入时省略 `segment` 表示第一段；提供时必须为真正的 JSON 整数，范围为 2 到 `2**53 - 1`。

同一个精确段 ID 且内容相同的回放可重复导入：首次返回 `201`，之后返回 `200`，响应包含 `exploration` 和 `created`。相同段 ID 但内容不同会返回 `409`，并保留已有段；同一会话的其他段使用各自的 ID，可以分别导入。导入兄弟段时也校验序号范围：较低段的最后一个 `sequence` 必须小于较高段的第一个 `sequence`；若已有兄弟段与待导入段的范围重叠或顺序相反，返回 `409` 并保留现有文件。无效内容返回 `400`，超过大小或帧数上限返回 `413`。

点“探索回放”旁的“导入回放”会打开文件选择器；选中单段 JSONL 后立即上传。上传成功且当前轨迹视图未改变时，页面自动打开导入段并暂停实时跟随。若上传期间切换了视图或世界，当前视图会保留，页面仍提供“查看导入轨迹”按钮供手动打开导入段；该按钮不受列表初次显示最近 10 项的限制。手动打开回放也会暂停实时跟随，重新勾选后返回当前会话。上传失败只显示错误，不改变当前视图。

回放保存在本机并由 Git 忽略。探索轨迹、已见目标、地皮底图和格网路线都可以在网页查看。

## 探索轨迹

“探索轨迹”按世界坐标绘制已观测的位置，北为 `+Z`、东为 `+X`，两个坐标轴使用相同比例。图上标出起点与最新位置；停在同一地点时也能看到位置标记。相邻快照的时间间隔超过五秒、时间没有前进，或位置相距超过 64 单位时，会断开轨迹线。

实时跟随首次连接当前会话时读取最新回放段的轨迹，之后把收到的新位置追加到图上。换段后，实时页的有上限本地地图继续保留轨迹连续性；磁盘上的新段文件只含本段快照。在某段旁点击“查看轨迹”会暂停实时跟随，历史视图只读取所选段；重新勾选后显示当前会话。历史进度的截止序号不超过该段最后一帧的 `sequence`，不会从相邻段补入帧。轨迹读取失败时，当前坐标、方向建议和回放下载仍可使用。可以点击“刷新轨迹”重新读取。图上最多显示 10,000 个位置；超出时保留起点与最近的 9,999 个位置，页面会提示。

地图视野可通过“全图”“跟随位置”“放大”和“缩小”调整。初次打开默认按全部已观测数据自动适配；处于全图状态时，新观测加入后视野会继续适配。点“全图”可恢复自动适配。点“跟随位置”后，视图以最新记录位置为中心；实时地图使用最新观测，历史回放使用最后一条记录的位置，玩家移动时局部视野随之移动。跟随视野的初始纵向跨度为 64 个世界单位；每次放大或缩小将跨度减半或加倍，范围为 32 到 512 个世界单位。没有可用位置时会显示提示，并禁用“跟随位置”“放大”和“缩小”。切换世界、采集会话或历史回放会恢复全图；普通刷新保留当前缩放。实时导航暂停时保留当前地图视野，既有导航暂停规则继续适用。

`GET /api/explorations/<id>/trail` 返回 `trail_version: 1`、会话标识、该段的 `frame_count`、`points` 和 `bounds`。第二段及之后的响应还包含 `segment`；第一段省略它。每个点包含 `sequence`、`captured_at`、`x`、`z`，以及该帧提供时的 `player_anchor` 和有限数值 `camera_heading`；下一帧缺少接入检查或镜头朝向时，不继承上一帧的对应字段。边界包含 `min_x`、`max_x`、`min_z`、`max_z`，没有位置时为 `null`。接口只投影所请求段已有的回放，不修改记录。可选的 `segment` 与 `camera_heading` 不改变 `trail_version: 1`；`live_version: 1` 快照已包含镜头字段。

`GET /api/explorations/<id>/trail?through_sequence=N` 要求正整数 `N`，只用所选段中 `sequence <= N` 的快照生成轨迹投影，并在原有字段外增加 `playback` 元数据：`through_sequence` 回显请求截止序号，`total_frame_count` 为所选段的快照总数。序号可以不连续；网页把进度滑块位置映射到该段的实际观测帧，所以前后翻帧不会显示空帧。省略查询参数时，接口继续返回所选段的完整轨迹。

轨迹图的“已见目标”按当前所选目标筛选，最多显示最近看到的十个位置。菱形标记上的编号与列表一致；列表包含坐标、最近看到的时间，以及相对最新玩家观测的方位和直线距离。离开目标附近后，标记仍保留在本次会话与历史回放中。当前视野内目标的距离继续在实时观测区域显示。

轨迹接口新增 `landmarks` 和 `landmarks_truncated`。每个地标包含 `prefab`、`x`、`z`、`first_seen`、`last_seen`、`first_sequence` 和 `last_sequence`。同一 prefab 的完全相同坐标合并为一个观测位置；不同坐标分别记录。每个会话的投影最多保留最近观测到的 500 个位置，超过时设置截断标记；原始 JSONL 回放仍保留完整快照。未记录地标的旧回放返回空列表。`bounds` 继续只表示玩家轨迹范围，网页绘图会一起纳入当前展示的目标位置。

查看历史回放时，可以从帧进度控件切换同一世界、同一采集会话的上一段或下一段。段号有空缺时，按钮按现存段号排序浏览；帧进度只作用于当前段。

这些标记表示当时看到的位置。目标移动、被采集或消失后，记录仍可用来复盘。

### 已观测地皮

“显示已观测地皮”默认打开。每个色块是一格 4×4 世界单位的地皮，颜色按草地、森林、岩地、沼泽、水域和其他地皮分组；指向色块可以查看原始地皮名和坐标。未采集的位置留空，关闭开关即可只看轨迹和目标。地皮颜色用于识别区域，斜线标出格中心地形检查不通过的位置。色块提示和地皮状态栏区分可通行、不可通行与未知。该检查排除水和船平台；Pathfinder 的墙障碍会参与邻格直连检查。路线终点取格中心；玩家实际位置通过下述接入检查连接，已见目标精确位置到格中心的接入段、实体碰撞和角色移动能力仍待接入。

轨迹接口的 `terrain` 包含 `tile_size: 4`、`tiles` 和 `truncated`。每格包含 `x`、`z`、`tile`、Unix 时间 `last_seen` 和 `last_sequence`。每格还可包含布尔值 `passable`。同一格按最新观测顺序整体替换；新观测没有 `passable` 时回到未知，不沿用旧结果。投影最多保留最近观测到的 2,500 格，超出时设置 `truncated`，原始回放仍保留完整快照。旧回放没有地皮时返回空列表。`bounds` 仍只包含玩家轨迹，网页会把显示的格边缘纳入绘图范围。

### 邻格直连检查

“显示邻格检查”默认关闭。打开后，地图显示已有检查结果的相邻格连线，并统计通过与受阻的数量。未知连接留空；缺少邻格或任一格的最新地形状态不为可通行时，不展示这条连接。关闭地皮底图后仍可单独看连接层。

每个地皮条目的可选 `connections` 只含 `east` 和 `north` 布尔值。每对格由西侧或南侧格保存一次，东为 `+X`、北为 `+Z`。采集器只在本次采到两端且地形检查均通过时调用 `Pathfinder:IsClear`，正向和反向均成功返回布尔值后取 AND；调用失败或接口缺失时省略方向。选项为 `ignorewalls: false`、`ignorecreep: true`，包含 Pathfinder 注册的墙障碍。它检查相邻中心间的线段，路线搜索只沿已检查通过的连接进行。

回放投影保留 `connections`；同一格的新观测整体替换旧值，省略字段会清除旧结果。旧回放不推断连接，仍可查看原有轨迹和地皮。

采集器 0.2.0 起提供地皮中心，0.3.0 起提供地形通行检查，0.4.0 起提供邻格直连检查，0.5.0 起提供玩家接入检查。更新已有安装时可重新运行上面的安装命令或手动复制采集器文件夹，然后重新进入世界；已有玩家轨迹和目标标记可继续回看。

### 格网路线

已见目标列表或地图菱形上的“前往所在格”会把记录位置所属格的中心设为终点，并显示来源目标。只有所在格已出现在观测地图且 `passable: true` 时才能选择；未采集、通行状态未知或不可通行时会提示，且不会猜测相邻格。这个操作使用记录地点所在格的中心，不使用 prefab 的精确位置，也不会跟踪已经移动的目标。

地图可以在“路线终点”中选择一格已观测且地形检查为可通行的地皮，也可直接点击该地皮。格网部分沿已检查通过的双向邻格连接寻找步数最少的路线，每步 4 个世界单位。

采集器 0.5.0 每帧还检查玩家当前点的地形通行，并双向检查当前位置到所在格中心的一段，选项与邻格直连检查相同。玩家地形检查为 `false` 时记录 `clear: false`；检查缺失、失败或非布尔时省略接入结果。只有当前格已采集且中心 `passable: true` 时才输出 `player_anchor`。

当最新位置带有 `clear: true` 的接入结果时，页面显示“玩家位置路线”：起点是实际玩家坐标，总距离为接入段直线长度加格网长度，下一步会先指向所在格中心。玩家已经在中心时直接显示下一格；终点在同格但玩家还没到中心时，仍显示这一小段。`clear: false` 会提示接入受阻并撤下路线。没有接入结果的旧数据继续显示“格中心路线”。

“前往最近可达目标”会在点击时比较当前目标的全部保留已见位置（最多 500 个），将各位置映射到已观测且可通行的所在格，再按已检查路线的总距离选出最近可达的一处。距离相同时采用记录列表中靠前的一处。比较使用当前展示帧的位置和玩家接入结果；历史帧不会使用后续发现的位置。选定后复用原有终点和来源目标，后续快照只重算到该终点的路线；没有已知可达路线时保留已有终点。实时导航暂停时按钮停用。

玩家移动或新检查到来时自动重算，历史回放使用最后位置对应的接入结果。没有路径时显示“未连通”；未知连接不作推断。手动选择路线终点或清除路线时会移除来源目标。切换当前目标类型后，若路线来自另一类型目标的已见记录，就清除这条路线；手动选格保留。切换世界或采集会话时清空终点。

下一步还会根据该帧记录的 `camera_heading`（镜头当前朝向），显示路线下一段在地面平面内相对镜头的方位提示。镜头朝向随新帧变化时，即使玩家坐标不变，提示也会更新；历史回放按所选帧的朝向计算。旧帧没有镜头朝向时只显示世界方向和坐标。地图格网和路线仍使用固定世界坐标，北为 `+Z`、东为 `+X`。本地源码显示 `GetHeading()` 返回当前镜头角度，`Apply` 用它设置镜头基向量；`GetRightVec` / `GetDownVec` 则基于 `headingtarget` 提供输入方向向量。相关路径相对 DST `scripts/` 目录：`cameras/followcamera.lua:104-112`、`cameras/followcamera.lua:232-283`、`cameras/followcamera.lua:328-333` 和 `components/playercontroller.lua:22-26`。

实时导航只由最新有效快照驱动。采集暂停、连接错误、手动停止，或等待 `/api/live` 响应期间最后有效快照超过五秒时，网页显示“导航已暂停”，隐藏紫色实时路线和下一步提示；已观测地皮、最后轨迹位置、终点及来源目标保留。收到新有效快照后自动恢复。此状态只影响实时导航，历史回放仍按记录显示路线。

实时跟随中的 `/api/live` 请求（包括 JSON 数据的传输与读取）五秒未完成时会超时，超时后网页等待一秒再重试。停止实时跟随或查看历史回放后不再发送请求；迟到的旧响应会被丢弃，不覆盖当前数据。服务恢复并返回新鲜快照后，导航自动恢复，无需手动切换。

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
- `connection.py` 自动定位客户端日志并生成一次连接检查结果。
- `exploration.py` 保存连续探索回放并提供摘要和下载。
- `trail.py` 从回放提取世界坐标和轨迹边界。
- `world_sampler.py` 抽取带锁/钥匙来源记录的 task 连接图，并以 BFS 最短跳数计算图上的 task 接近度。

当前项目进度和下一步计划见根目录的 [`README.md`](../README.md) 与 [`TODO.md`](../TODO.md)。
