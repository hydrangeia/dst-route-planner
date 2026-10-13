# DST 大陆路线规划

[English](README.en.md)

想在《饥荒联机版》里找排箫、猪王或月台？打开本地网页，选好目标，填入各方向看到的地皮和地标，工具就会给出接下来值得探索的方向和判断理由。

## 开始使用

需要 Python 3.10 或更新版本。克隆仓库后，在仓库目录启动本地网页：

```powershell
git clone https://github.com/hydrangeia/dst-route-planner.git
cd dst-route-planner
python route_planner.py --ui
```

Windows 用户也可以双击 `start_planner.bat` 启动。页面在本机浏览器打开。

## 使用步骤

1. 选择要找的目标。
2. 在各个方向填写看到的地皮、prefab 和数量。
3. 点击“计算方向”，查看方向排名及对应线索。
4. 回到 DST 探索并保存；下次启动时从记录列表打开本局，继续补充和保存观测。

界面提供示例数据，也可以导入或导出 JSON 观测。还可以填写记录名称和世界备注后点“保存”，或点“另存为新记录”保留一份副本。重启工具后，或在同一仓库目录下换浏览器或端口，都可以从记录列表打开本局、补充观测并再次保存。JSON 观测的导入和导出仍使用原来的格式。

每次保存都会更新这条记录的当前观测；修改后再点“保存”即可。

```text
选择目标并填写各方向看到的地皮与地标
  ↓
点击计算，Python 根据知识库匹配 room 和 task 线索
  ↓
结合 task 连接图和可见证据排列方向
  ↓
查看推荐方向与判断理由，回到 DST 探索
  ↓
更新观测并保存命名记录（名称和世界备注）
  ↓
下次打开记录，接着观察、计算和保存
```

目前观测由玩家在网页中填写；后续的游戏内采集器可以把同一种 JSON 观测交给 Python 引擎。

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

JSON 字段说明和 CLI 示例见 [`dst_route_planner/README.md`](dst_route_planner/README.md)。

## 当前进度

本地 Python 引擎结合默认大陆的 20 个 task、53 个 room、13 个静态布局和 20 种目标线索来排列方向。任务连接图描述世界生成中的拓扑关系，网页里填写的地皮与地标提供眼前的线索。命名记录把目标、世界备注和当前观测保存在本机，方便玩家重启后接着探索。

后续工作按阶段列在 [`TODO.md`](TODO.md)。早期开发记录见 [`DST_ROUTE_PLANNER_WORK.md`](DST_ROUTE_PLANNER_WORK.md) 和 [`PHASE_5A_COMPLETION_REPORT.md`](PHASE_5A_COMPLETION_REPORT.md)。
