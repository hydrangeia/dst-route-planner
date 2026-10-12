# DST 大陆寻路推理器

[English](README.en.md)

这是一个外置 Python 原型：根据玩家当前能看到的地皮、prefab 和方向线索，为寻找目标物品或地标的路线排列优先级。当前知识库覆盖《饥荒联机版》（DST）默认森林世界的 20 个 task、53 个 room 和 20 种目标。它不会读取或修改游戏，也不包含 Lua mod、屏幕采集器或 HUD。

目前最适合把输出看作**基于手工整理规则的候选方向排序**。`p_dir` 是各候选方向分数归一化后的相对值，不是经过实测校准的成功概率；本项目没有真实玩家路线数据，也没有报告过经验证的寻路准确率。

## 快速开始

需要 Python 3.10 或更高版本。运行时只用 Python 标准库，不需要安装第三方包。克隆仓库后，在仓库根目录执行：

```powershell
git clone https://github.com/hydrangeia/dst-route-planner.git
cd dst-route-planner
python route_planner.py --demo
python route_planner.py --list-targets
python route_planner.py --target moonbase --observe-json examples/moonbase_observation.json
```

默认目标是 `panflute`。`--observe-json` 读取各方向的观测；`--current-json` 可选，用来提供当前位置观测并更新初始信念：

```powershell
python route_planner.py --target panflute `
  --current-json examples/current_observation.json `
  --observe-json examples/panflute_observation.json
```

若要运行开发测试，安装开发依赖并运行 pytest：

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

开发依赖不是运行 CLI 所必需的。

## 支持的目标

下表概括当前知识库登记的 20 种 prefab 目标及其简化 task/room 链。taskset 级 setpiece 会受具体生成任务约束，不能据此认定某个固定 room。

| 目标 prefab | 当前记录的主要生成线索 |
|---|---|
| `antlion_spawner` | `Lightning Bluff` → `LightningBluffAntlion` |
| `beequeenhive` | `Beeeees!` → `BeeQueenBee` |
| `cave_entrance` | taskset 级 setpiece；使用允许的 task 列表，没有固定 room |
| `dragonfly_spawner` | `Badlands` → `DragonflyArena` |
| `lightninggoat` | `Lightning Bluff` → `LightningBluffLightning` |
| `mandrake_planted` | `For a nice walk` → `MandrakeHome` |
| `mermhouse` | `Squeltch` → `SlightlyMermySwamp` |
| `molehill` | `Mole Colony Rocks`、`Mole Colony Deciduous` 或 `Frogs and bugs` 下的鼹鼠房间 |
| `moonbase` | `Forest hunters` → `MoonbaseOne` |
| `moose_nesting_ground` | `MooseBreedingTask`；四个巢支持识别繁殖区域，单个巢按 taskset 约束处理 |
| `oasislake` | `Lightning Bluff` → `LightningBluffOasis` |
| `panflute` | `Speak to the king` → `MagicalDeciduous` → `DeciduousPond` |
| `pigking` | `Speak to the king` → `PigKingdom` |
| `resurrectionstone` | taskset 级 setpiece；使用允许的 task 列表，没有固定 room |
| `spiderden` | `Kill the spiders` → `SpiderVillage` |
| `statueglommer` | `Speak to the king` → `MagicalDeciduous` → `DeciduousPond` |
| `tentacle` | `Squeltch` → `Marsh` |
| `walrus_camp` | `Forest hunters` → `WalrusHut_Grassy` |
| `wasphive` | `Killer bees!` → `Waspnests`；也记录了 `Beeeees!` 下的相关线索 |
| `wormhole` | taskset 级 setpiece；使用允许的 task 列表，没有固定 room |

可用 `--list-targets` 查看 CLI 当前登记的目标。

## 观测 JSON

方向观测文件顶层使用 `directions` 对象。方向名支持八方位；每个方向可包含以下字段：

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
      "note": "落叶林边缘"
    }
  }
}
```

- `tile_types`、`prefabs_seen`：可见地皮和 prefab 的游戏内标识符。标识符区分大小写。
- `prefab_counts`：可选的数量字典。若省略，会按 `prefabs_seen` 中的重复项计数；若两者都提供，明确数量优先，同时会为只出现在 `prefabs_seen` 的条目补上至少 1。
- `room_hints`、`task_hints`：可选的人工线索名称，应与知识库名称一致。
- `connection_like`、`background_like`：可选布尔线索；省略时由模型按其他证据处理。
- `note`：仅供阅读，不参与打分。

`--current-json` 接收单个观测对象，字段与每个方向对象相同，但不需要外层 `directions`。仓库中的输入样例位于 [`examples/`](examples/) 中。

输出里的 `score` 是方向排序分数；`p_dir` 是这些分数归一化后的相对份额，不代表校准过的到达概率。`p_task` 和 `p_room` 是当前规则模型给出的 task/room 信念值。输出同时列出加分或扣分解释，便于人工判断。

## 当前能力与边界

- 用地皮、prefab 的出现和缺失、部分数量证据、静态布局、人工 task/room 提示和连接/背景提示推断 task 与 room。
- 对各方向进行启发式打分，并在直接看到目标时提升该方向优先级。
- 内含实验性的 task sampler：以随机种子可复现地从 10 个 optional task 中选 5 个。`sample_task_graph` 统计被选入 taskset 的成员关系；`build_random_valid_chain` 只返回严格符合锁/钥匙顺序的链，因此被选中但暂时不可解锁的 optional task 不一定出现在链里。距离估算只包含实际进入链的 task；例如没有选中 `Make a Beehat` 时，`Killer bees!` 可能被选中但不会进入严格链。该原型尚未实现 `storygen.lua` 在缺少合法父节点时强制连接的规则，也未模拟空间邻接、道路或行走距离。
- 当前数据是默认大陆知识库的手工整理切片。模型推断分数未经真实世界校准；合成回归样例不能替代游戏内评估。
- 没有游戏内视野采集、Lua mod、HUD、持久化探索地图，也未覆盖海洋、月岛地形、洞穴生态、boons 或后期 retrofit。

## 项目结构

```text
route_planner.py                     CLI 启动脚本
requirements-dev.txt                开发测试依赖
dst_route_planner/
  models.py                          数据模型
  inference.py                       task/room 证据评分与信念更新
  navigation.py                      方向评分和排序
  io.py                              JSON 观测读取
  cli.py                             命令行和内置演示
  world_sampler.py                   实验性 task 锁/钥匙链抽样
  knowledge/forest_default.py        默认森林大陆知识库
examples/                            JSON 观测与区分样例
test_knowledge_integrity.py          知识库完整性检查
test_world_sampler.py                task sampler 回归测试
test_phase*.py                       回归测试
DST_GENERATION_RULES.md              task/room 生成规则笔记
TODO.md                              后续路线图
```

旧阶段记录见 [`DST_ROUTE_PLANNER_WORK.md`](DST_ROUTE_PLANNER_WORK.md) 和 [`PHASE_5A_COMPLETION_REPORT.md`](PHASE_5A_COMPLETION_REPORT.md)；两者描述的是历史工作，不应视为当前功能规格或准确率报告。
