# 开发路线 / Roadmap

先把大陆推理引擎做扎实，再接上游戏内观测和方向提示。 / Build the mainland inference engine, then connect in-game observations and direction hints.

## 已完成 / Completed

- [x] 公开 GitHub 仓库、中英文 README、JSON 示例和 Python 3.10/3.13 自动测试。 / Public GitHub repository, Chinese and English READMEs, JSON examples, and Python 3.10/3.13 CI.
- [x] 20 个 task、53 个 room、13 个静态布局和 20 种目标，以及知识库引用完整性检查。 / 20 tasks, 53 rooms, 13 static layouts, 20 targets, and knowledge-reference integrity checks.
- [x] 每次从 10 个可选 task 中选 5 个，支持随机种子复现。 / Select five of ten optional tasks per sample, with reproducible seeds.
- [x] 按 `LinkNodesByKeys` 构建 task 连接图，保留强制连接，再按最短连接跳数计算目标接近度。 / Build task graphs using `LinkNodesByKeys`, retain forced connections, and score target proximity by shortest connection hops.
- [x] `--seed` 复现方向建议，`--sample-graph` 输出图结构 JSON。 / Repeat recommendations with `--seed` and inspect graph JSON with `--sample-graph`.

## 1. 生成数据校对 / Generation data

- [x] 核对 53 个 room 的地皮、20 个 task 的字段与数量，修正关键房间内容，并记录源文件 SHA256。 / Check tiles for 53 rooms, fields and counts for 20 tasks, correct selected room contents, and record source-file SHA256 hashes.
- [x] 把随机数量的表达式、范围和模型使用的平均值写入 [来源清单](dst_route_planner/knowledge/source_audit.json)。 / Record random-count expressions, ranges, and modeled averages in the [source manifest](dst_route_planner/knowledge/source_audit.json).
- [ ] 继续补充房间内容、成组 prefab 选择和节日布局。 / Expand room contents, grouped prefab choices, and event layouts.

## 2. 游戏内观测 / In-game observations

- [ ] 定义带版本的 JSON 观测协议，检查输入格式。 / Define a versioned JSON observation format and validate inputs.
- [ ] 做 DST mod 采集层，导出玩家附近的地皮、prefab 数量和方向。 / Build a DST mod collector for nearby tiles, prefab counts, and directions.
- [ ] 接通采集文件与 Python 引擎。 / Connect captured observations to the Python engine.
- [ ] 做 HUD 目标选择器，显示推荐方向、理由和观测状态。 / Add a HUD target picker with directions, reasons, and observation status.

## 3. 连续探索与地图导航 / Exploration and map navigation

- [ ] 保存已探索区域、目标位置和重复观测。 / Save explored areas, target locations, and repeated observations.
- [ ] 加入 task 的起终点环路、房间内连接、道路和岛屿连接。 / Add task start/end loops, room connections, roads, and island links.
- [ ] 加入坐标、视野范围、移动代价和路线重规划。 / Add coordinates, view range, movement costs, and route replanning.

## 4. 游戏地图评估 / Evaluation in game worlds

- [ ] 在多个世界种子中记录观测、推荐方向、目标发现位置和探索距离。 / Record observations, directions, target discoveries, and exploration distances across multiple world seeds.
- [ ] 留出独立验证数据，比较不同评分规则的效果和运行开销。 / Keep held-out data and compare scoring rules and runtime.
- [ ] 用评估结果校准方向分值。 / Calibrate direction scores using evaluation results.

## 5. 更多世界内容 / More world content

- [ ] 加入海洋、月岛和洞穴知识模块。 / Add ocean, lunar-island, and cave knowledge modules.
- [ ] 加入 boons、世界设置和 retrofit 规则。 / Add boons, world settings, and retrofit rules.
