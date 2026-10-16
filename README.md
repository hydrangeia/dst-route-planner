# DST 大陆路线规划

[English](README.en.md)

想在《饥荒联机版》里找排箫、猪王或月台？轻量客户端采集器读取玩家坐标和周围地皮、地标，外置 Python 网页随着观测更新探索方向。也可以手动录入线索，载入示例或复用一局的探索记录。

## 开始使用

需要 Python 3.10 或更新版本。克隆仓库后，在仓库目录启动本地网页：

```powershell
git clone https://github.com/hydrangeia/dst-route-planner.git
cd dst-route-planner
python route_planner.py --ui
```

Windows 用户也可以双击 `start_planner.bat` 启动。页面在本机浏览器打开。

## 连接实时观测

把 [`mods/dst_route_collector`](mods/dst_route_collector/README.md) 安装为客户端 mod 并启用，进入一个世界。工具启动时会自动定位客户端日志；Windows 用户直接双击 `start_planner.bat`，或运行：

```powershell
python route_planner.py --ui
```

在网页点“检查连接”，查看正在读取的文件和下一步提示；收到新快照后，勾选“实时跟随”。采集器每秒提供坐标和周围线索，页面自动计算方向；看到目标时显示直线距离。移动一下，确认坐标跟着变化，就可以开始探索。

也可以在终端单独检查连接：

```powershell
python route_planner.py --check-live
```

日志存放在其他位置时，用 `--live-log "实际路径/client_log.txt"` 指定文件。`--live-log auto` 与默认的自动定位相同。手动录入时保持“实时跟随”未勾选即可。

方向使用固定世界坐标：北为 `+Z`，东为 `+X`。具体绕障碍的行走路径会随着已探索地图的接入继续实现。

实时跟随期间，工具会把新收到的快照保存在本机，包含坐标、周围线索、当前目标和当时的方向建议。在“探索回放”中下载 JSONL 文件，就能保留这次探索过程；重启后仍可下载已有回放。不同世界和采集会话分别记录。

“探索轨迹”会随着实时位置更新，标出起点和最新位置。也可以在已保存回放旁点击“查看轨迹”，回看一次探索；这会暂停实时跟随，重新勾选后回到当前会话。图上北为 `+Z`、东为 `+X`，采集中断或坐标跳变处会断开连线。

轨迹图还会标出所选目标曾被看到的位置。“已见目标”列出最近看到的时间、坐标，以及相对最新玩家观测的方向和直线距离。切换目标即可回看对应地标；重新打开历史回放时也能查看。标记记录的是看到它时的位置，移动或被采集的目标可能已不在原处。

## 手动录入与保存

1. 选择要找的目标。
2. 在各个方向填写看到的地皮、prefab 和数量。
3. 点击“计算方向”，查看方向排名及对应线索。
4. 回到 DST 探索并保存；下次启动时从记录列表打开本局，继续补充和保存观测。

界面提供示例数据，也可以导入或导出 JSON 观测。还可以填写记录名称和世界备注后点“保存”，或点“另存为新记录”保留一份副本。重启工具后，或在同一仓库目录下换浏览器或端口，都可以从记录列表打开本局、补充观测并再次保存。JSON 观测的导入和导出仍使用原来的格式。

每次保存都会更新这条记录的当前观测；修改后再点“保存”即可。

```text
启用采集器、进入世界 → 启动工具，自动定位日志
  ↓
检查连接 → 选择目标，实时采集玩家坐标、地皮与地标（每秒）
  ↓
客户端日志 → 外置 Python，更新当前位置与各方向线索
  ↓
知识库匹配 room / task，结合连接图排列探索方向
  ↓
网页自动更新建议；目标可见时显示直线距离
  ↓
新快照 → 本机探索回放 → 轨迹图，标出起点、最新位置与已见目标
  ↓
历史回放 → 查看轨迹，或下载坐标、线索与建议
  ↓
玩家继续移动 → 再次采集、计算和更新
  ↓
保存当前观测与世界备注，下次继续探索
```

采集暂停超过五秒时，网页会提示观测过期。手动录入和 JSON 示例仍可随时使用。

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

本地 Python 引擎结合默认大陆的 20 个 task、53 个 room、13 个静态布局和 20 种目标线索来排列方向。任务连接图描述世界生成中的拓扑关系，自动采集或手动填写的地皮与地标提供眼前的线索。命名记录把目标、世界备注和当前观测保存在本机，方便玩家重启后接着探索。

后续工作按阶段列在 [`TODO.md`](TODO.md)。早期开发记录见 [`DST_ROUTE_PLANNER_WORK.md`](DST_ROUTE_PLANNER_WORK.md) 和 [`PHASE_5A_COMPLETION_REPORT.md`](PHASE_5A_COMPLETION_REPORT.md)。
