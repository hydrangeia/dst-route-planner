# 历史记录：Phase 5a 负面证据整理

这轮工作主要整理房间之间的区分线索。使用说明见 [`README.md`](README.md)，后续安排见 [`TODO.md`](TODO.md)。

Phase 5a 整理了部分默认森林 room 的 prefab 出现、缺失和数量线索，重点关注猪王/猪村、落叶林、蜜蜂、海象营地、曼德拉草和月基地等容易混淆的区域。相关启发式目前体现在 `dst_route_planner/knowledge/forest_default.py` 与 `dst_route_planner/inference.py`：正向证据、排除线索、必要 prefab、数量和静态布局都可参与 room 评分。

参考文件位于 DST 源码的 `scripts/map/rooms/forest/`，包括 `pigs.lua`、`bee.lua`、`walrus.lua`、`mandrake.lua` 和 `DLCrooms.lua`。

当时笔记里的 30–40% 提升来自少量人工构造的示例，现已移除这个估计。保留下来的回归测试用于检查具体观察条件下的房间排名。

后续评估会在多个世界种子上记录推荐方向、目标发现位置和探索距离。
