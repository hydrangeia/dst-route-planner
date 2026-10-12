# DST 大陆路线规划

[English](README.en.md)

把《饥荒联机版》中各个方向看到的地皮和地标写成 JSON，这个工具会结合默认大陆的 task、room 生成线索，为寻找排箫、猪王或月台给出方向建议。

## 开始使用

需要 Python 3.10 或更新版本。在 PowerShell 里克隆仓库并运行内置示例：

```powershell
git clone https://github.com/hydrangeia/dst-route-planner.git
cd dst-route-planner
python route_planner.py --demo
```

列出目标，或用自己的方向观测运行：

```powershell
python route_planner.py --list-targets
python route_planner.py --target moonbase --observe-json examples/moonbase_observation.json
```

默认目标是 `panflute`。你也可以同时提供当前位置线索和各方向观测：

```powershell
python route_planner.py --target panflute `
  --current-json examples/current_observation.json `
  --observe-json examples/panflute_observation.json
```

想运行开发测试时，先安装开发依赖：

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

## 如何读方向建议

结果会列出每个方向的分数，以及与目标相关的线索：

```text
north  score=... p_dir=... p_task=... p_room=...
       looks like target task Speak to the king; looks like target room MagicalDeciduous
```

`score` 用于排列方向；`p_dir` 是各候选方向分数归一化后的相对份额。`p_task` 和 `p_room` 显示观测与目标相关 task、room 的匹配程度。解释文字会指出哪些地皮、prefab 或连接线索影响了排序。看到目标 prefab 会显著提高该方向的优先级。

## 可以寻找什么

知识库目前登记 20 种目标 prefab。这里用容易识别的名称列出目标；括号中的代码是 JSON 和 `--target` 使用的 prefab ID。

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

各目标对应的 task、room 和 setpiece 线索见 [`dst_route_planner/README.md`](dst_route_planner/README.md#目标与世界生成线索)。

## 输入观察

`--observe-json` 文件以 `directions` 为顶层对象，方向名使用八方位。下面是一个简化例子：

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

`tile_types` 和 `prefabs_seen` 使用游戏里的标识符，大小写要与知识库一致。重复填写 prefab 会计入数量；也可以用 `prefab_counts` 直接提供数量。`room_hints` 和 `task_hints` 可以填写你判断出的房间或地形块，`connection_like` 和 `background_like` 是可选布尔值。`note` 用来记录备注。

`--current-json` 接受一个观测对象，字段与方向对象相同，但不需要外层 `directions`。可以从仓库的 [`examples/`](examples/) 样例开始改。

## 当前进度

Python 引擎可从 JSON 观测给出方向排序，知识库覆盖默认大陆的 20 个 task、53 个 room、13 个静态布局和这 20 种目标。task 图按世界生成规则抽样，帮助比较地形块在图上的远近；下一步是接入游戏内采集，并在 HUD 中选择目标、查看方向建议。

后续工作按阶段列在 [`TODO.md`](TODO.md)。早期开发记录见 [`DST_ROUTE_PLANNER_WORK.md`](DST_ROUTE_PLANNER_WORK.md) 和 [`PHASE_5A_COMPLETION_REPORT.md`](PHASE_5A_COMPLETION_REPORT.md)。
