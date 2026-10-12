# 历史记录：寻路原型起步

> 本文保留早期开发记录。它不描述完整的当前功能；当前行为、命令、数据范围和限制以仓库根目录 [`README.md`](README.md) 为准，后续工作见 [`TODO.md`](TODO.md)。

最初的目标是把有限视野里的地皮、prefab 和方向线索转换成寻找排箫的候选方向排序。早期原型建立了 `TaskDef`、`RoomDef`、`Observation`、`BeliefState` 和 `ActionScore` 等模型，并实现了默认森林知识、task/room 证据评分、信念更新、方向排序与 JSON/CLI 输入。

之后的实现已从单一排箫示例扩展到默认大陆知识库的多种目标、负面 prefab 证据、数量线索、静态布局，以及 taskset 级目标约束。知识库当前覆盖 20 个 task、53 个 room 和 20 种目标。仓库还加入了可复现的 5-of-10 optional-task 选择和实验性锁/钥匙顺序抽样；严格链可能省略已选但不可解锁的 optional task，也不模拟 `storygen.lua` 的强制连接回退、空间图、道路或移动代价。

早期建议里提到的 world sampler、游戏内采集、几何地图等方向仍需分阶段完善。请以 [`TODO.md`](TODO.md) 中的当前路线图为准；尚未完成的功能不要从这份历史记录推断为已实现。
