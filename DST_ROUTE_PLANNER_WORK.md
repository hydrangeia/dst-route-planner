# 历史记录：寻路原型起步

这份记录介绍原型起步时的工作。使用说明见 [`README.md`](README.md)，开发安排见 [`TODO.md`](TODO.md)。

最初的目标是把有限视野里的地皮、prefab 和方向线索转换成寻找排箫的候选方向排序。早期原型建立了 `TaskDef`、`RoomDef`、`Observation`、`BeliefState` 和 `ActionScore` 等模型，并实现了默认森林知识、task/room 证据评分、信念更新、方向排序与 JSON/CLI 输入。

之后逐步加入了更多大陆目标、负面 prefab 证据、数量线索、静态布局，以及 taskset 级目标约束。首次公开发布时，知识库包含 20 个 task、53 个 room 和 20 种目标；采样器支持从 10 个可选 task 中选 5 个，并生成锁和钥匙顺序。

后续工作沿着连接图、游戏内采集和几何导航继续推进。
