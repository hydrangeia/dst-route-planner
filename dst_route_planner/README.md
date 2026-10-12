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
- `world_sampler.py` 抽取带锁/钥匙来源记录的 task 连接图，并以 BFS 最短跳数计算图上的 task 接近度。

当前项目进度和下一步计划见根目录的 [`README.md`](../README.md) 与 [`TODO.md`](../TODO.md)。
