# 开发路线 / Roadmap

先接上玩家坐标与周围线索的实时采集，让外置工具随着游戏自动更新，再加入已探索地图和具体路径。 / Connect live player positions and nearby observations so the external tool updates during play, then add explored maps and concrete routes.

## 已完成 / Completed

- [x] 公开 GitHub 仓库、中英文 README、JSON 示例和 Python 3.10/3.13 自动测试。 / Public GitHub repository, Chinese and English READMEs, JSON examples, and Python 3.10/3.13 CI.
- [x] 20 个 task、53 个 room、13 个静态布局和 20 种目标，以及知识库引用完整性检查。 / 20 tasks, 53 rooms, 13 static layouts, 20 targets, and knowledge-reference integrity checks.
- [x] 每次从 10 个可选 task 中选 5 个，支持随机种子复现。 / Select five of ten optional tasks per sample, with reproducible seeds.
- [x] 按 `LinkNodesByKeys` 构建 task 连接图，保留强制连接，再按最短连接跳数计算目标接近度。 / Build task graphs using `LinkNodesByKeys`, retain forced connections, and score target proximity by shortest connection hops.
- [x] `--seed` 复现方向建议，`--sample-graph` 输出图结构 JSON。 / Repeat recommendations with `--seed` and inspect graph JSON with `--sample-graph`.
- [x] 用本机 Python 标准库提供浏览器界面；可用 `python route_planner.py --ui` 或 Windows 的 `start_planner.bat` 启动。 / Provide a browser interface with the local Python standard library; start it with `python route_planner.py --ui` or, on Windows, `start_planner.bat`.
- [x] 提供 schema version 1 和输入校验，同时兼容无版本的旧观测 JSON。 / Define schema version 1 and validate input while keeping compatibility with older observation JSON without a version.
- [x] 网页支持载入示例、导入和导出观测 JSON，并显示方向排名与判断理由。 / Let the page load a demo, import and export observation JSON, and show ranked directions with reasons.
- [x] 核对 53 个 room 的地皮、20 个 task 的字段与数量，修正关键房间内容，并记录源文件 SHA256。 / Check tiles for 53 rooms, fields and counts for 20 tasks, correct selected room contents, and record source-file SHA256 hashes.
- [x] 把随机数量的表达式、范围和模型使用的平均值写入 [来源清单](dst_route_planner/knowledge/source_audit.json)。 / Record random-count expressions, ranges, and modeled averages in the [source manifest](dst_route_planner/knowledge/source_audit.json).

## 实时探索 / Live exploration

- [x] 客户端采集玩家坐标、当前地皮和附近地标，把每秒快照送给外置 Python。 / Collect player coordinates, the current tile, and nearby landmarks on the client, and send one snapshot per second to external Python.
- [x] 网页实时展示位置与方向建议，识别采集暂停和世界切换。 / Show live positions and direction suggestions, and detect paused collection and world changes.

采集器与网页已通过 Lua 桩、日志回放和浏览器验证。 / The collector and page have passed Lua-stub, log-replay, and browser checks.

- [x] 启动时自动定位客户端日志，提供网页和终端的一次连接检查，显示读取路径与下一步操作。 / Locate the client log automatically on startup and provide page/terminal connection checks with the selected path and next steps.
- [ ] 在游戏中验证日志输出、坐标方向、地标采集、地形通行与邻格直连状态，记录一次完整探索过程。 / Verify log output, coordinate directions, landmarks, ground passability, and neighbor connections in game, and record a complete exploration run.
- [x] 实时跟随时记录连续坐标、观测和方向建议，按世界与会话保存本机 JSONL 回放，并支持重启后下载。 / Record successive positions, observations, and suggestions during live following, save local JSONL replays per world/session, and download them after restarting.
- [x] 显示实时探索轨迹、起点和最新位置，并能打开已保存回放的轨迹；采集间隔与位置跳变处分段。 / Show live trails with start/latest positions, open trails from saved replays, and split lines at capture gaps and position jumps.
- [x] 在实时与历史轨迹图上标记已见目标位置，显示最近看到的时间，以及相对最新玩家观测的方向和直线距离。 / Mark observed targets on live and saved trails, with last sighting time, direction, and straight-line distance from the latest player observation.
- [x] 采集附近地图已揭示格的地皮中心与类型，在实时和历史轨迹下显示地皮底图。 / Collect centers and types of nearby revealed tiles and show a terrain layer under live and saved trails.
- [x] 记录已观测格中心的地形通行状态，在实时与历史底图上标出检查不通过的位置，并区分未知状态。 / Record ground passability at observed tile centers, mark failed checks on live/saved maps, and keep unknown states distinct.
- [x] 双向检查已观测相邻格中心的直连状态，在实时与历史地图上区分通过、受阻和未知连接。 / Check observed neighboring tile centers in both directions and distinguish clear, blocked, and unknown connections on live/saved maps.
- [ ] 根据已检查的连接生成具体路径，接入实体碰撞、角色移动能力和路径重规划。 / Build concrete routes from checked connections, then add entity collisions, character movement capabilities, and replanning.

## 1. 生成数据校对 / Generation data

- [ ] 继续核对房间内容、成组 prefab 选择和节日布局。 / Continue checking room contents, grouped prefab choices, and event layouts.

## 2. 连续手动探索 / Ongoing manual exploration

- [x] 保存并打开命名探索记录；记录包含目标、世界备注、随机种子和当前观测，重启或换浏览器/端口后也能继续补充。 / Save and reopen a named exploration record with its target, world note, random seed, and current observations, then continue after restarting or switching browsers/ports.
- [ ] 为记录加入观测历史和已发现地点，方便回看同一张地图。 / Add observation history and discovered locations so players can review the same world over time.
- [ ] 在实战中检查手动保存和更新是否顺手，并按反馈调整流程。 / Check whether saving and updating records feels convenient during play, and refine the flow from that feedback.

## 3. 实战使用与评估 / Play-world evaluation

- [ ] 在多个世界中记录手动观测、推荐方向、实际选择、目标发现位置和探索距离。 / In multiple worlds, record manual observations, suggested directions, actual choices, target locations, and exploration distance.
- [ ] 留出独立世界记录，比较方向建议是否有帮助，并留意操作负担与运行开销。 / Set aside records from separate worlds to check whether recommendations help, along with input effort and runtime.
- [ ] 根据实战记录校准方向分值。 / Calibrate direction scores using play-world records.

## 4. 路线与地图推理 / Route and map reasoning

- [ ] 加入 task 的起终点环路、房间内连接、道路和岛屿连接。 / Add task start/end loops, room connections, roads, and island links.
- [ ] 利用坐标和地皮观测，加入视野范围、移动代价和路线重规划。 / Use position and terrain observations to add view range, movement costs, and route replanning.

## 5. 游戏内展示 / In-game display

- [ ] 视需要加入 HUD 目标选择器，显示推荐方向、理由和观测状态。 / If useful, add a HUD target picker that shows suggested directions, reasons, and observation status.

## 6. 更多世界内容 / More world content

- [ ] 加入海洋、月岛和洞穴知识模块。 / Add ocean, lunar-island, and cave knowledge modules.
- [ ] 加入 boons、世界设置和 retrofit 规则。 / Add boons, world settings, and retrofit rules.
