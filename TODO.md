# 路线图 / Roadmap

本文区分当前原型与尚未实现的工作。阶段可按可用性逐步交付。

## 现状 / Current state

- [x] 已发布公开 GitHub 仓库，提供中英文 README、JSON 样例和 Python 3.10/3.13 自动测试工作流。 / Published a public GitHub repository with Chinese and English READMEs, JSON examples, and a Python 3.10/3.13 test workflow.
- 默认大陆知识库当前记录 20 个 task、53 个 room 和 20 种目标。知识数据仍是手工整理的切片。 / The default mainland knowledge base currently records 20 tasks, 53 rooms, and 20 targets; its data is still a curated slice.
- [x] 已完成知识完整性核查：覆盖 20 个 task、53 个 room、11 个静态布局和 20 种目标，并为补充的 room 定义记录了源码相对路径。 / Knowledge integrity review is complete: 20 tasks, 53 rooms, 11 static layouts, and 20 targets are covered, with source-relative paths recorded for added room definitions.
- taskset 选择层可复现地从 10 个 optional task 中选 5 个；严格链只加入按锁/钥匙顺序可解锁的任务，因此某个已选 optional task 可能不在链或距离估算中。`storygen.lua` 的强制连接回退和空间地图还未建模。 / Taskset selection reproducibly chooses 5 of 10 optional tasks; the strict chain only adds tasks reachable through lock/key order, so a selected optional task may be absent from the chain and distance estimates. The `storygen.lua` forced-connection fallback and spatial map are not modeled yet.
- `p_dir` 是归一化的启发式排序分数，不是经真实世界校准的成功概率。 / `p_dir` is a normalized heuristic ranking score, not a real-world calibrated success probability.

## 阶段 1：生成规则与回归基线 / Phase 1: Worldgen fidelity and regression baseline

- [x] 已完成 5-of-10 taskset 选择、seed 可复现性、taskset 成员统计及成员/可达性差异的回归覆盖。 / Regression coverage is complete for 5-of-10 selection, seeded reproducibility, taskset membership, and membership versus reachability.
- [x] 已为目标链、负证据、重复 prefab 数量和采样边界输入建立回归基线；当前共有 25 项测试。 / A 25-test regression baseline covers target chains, negative evidence, repeated prefab counts, and sampler edge cases.
- [ ] 对照固定版本的 DST 源码校对全量房间字段和随机数量。目前发现的待核对项包括 `MandrakeHome` 的源码地皮为 `GRASS`（知识库为 `FOREST`），以及 `BeeQueenBee` 的花朵权重和黄蜂巢随机数量。调整推理与回归输入时保留有限视野下跨房间观测的区别。 / Audit all room fields and random counts against a pinned DST source version. Known discrepancies include `MandrakeHome` using `GRASS` in the source but `FOREST` in the KB, and `BeeQueenBee` flower weights and random wasp-hive counts. Preserve the distinction between source room contents and partial observations spanning room boundaries.
- [ ] 实现 DST `storygen.lua` 的强制连接回退和连接图；保留 taskset 成员、严格锁钥顺序、实际连接和距离样本的区别。 / Implement DST's forced-connection fallback and connection graph, keeping taskset membership, strict unlock order, actual connections, and distance samples distinct.

## 阶段 2：游戏内观测采集 / Phase 2: In-game observation collection

- 定义稳定、带版本的 JSON 观测协议和输入校验。 / Define a stable, versioned observation JSON contract and validate its inputs.
- 开发可选 DST mod，将玩家可见的地皮、prefab、数量和方向信息导出为该协议。 / Build an optional DST mod that exports visible tiles, prefabs, counts, and directions through that contract.
- 让原型能加载采集文件，并保留人工输入与演示模式。 / Let the prototype load captured observations while keeping manual input and demo mode available.
- 开发 HUD，提供目标选择器并显示当前方向推荐、理由和观测状态。 / Build a HUD with a target picker and a display for the recommended direction, its reasons, and observation status.

## 阶段 3：持久探索与几何导航 / Phase 3: Persistent exploration and geometric navigation

- 记录已探索区域、重复观测和目标位置，避免把同一区域反复当作新线索。 / Track explored areas, repeated observations, and target locations so revisited areas are not treated as new evidence.
- 加入坐标、视野范围、地形边界、移动代价和道路连通信息。 / Add coordinates, view range, terrain boundaries, movement costs, and road connectivity.
- 在方向排序之外计算可解释的下一段路线，并支持地图更新后的重规划。 / Produce an explainable next route segment in addition to direction rankings, and replan when the map changes.

## 阶段 4：真实世界评估与校准 / Phase 4: Real-world evaluation and calibration

- 在多个种子生成的世界中记录输入、推荐和实际发现，保留未参与调参的验证集合。 / Record observations, recommendations, and discoveries across worlds generated from multiple seeds, with a held-out evaluation set.
- 衡量目标命中、探索距离、方向排序质量和运行成本；报告数据量与不确定性。 / Measure target discovery, exploration distance, direction-ranking quality, and runtime; report sample size and uncertainty.
- 只有完成评估后才把输出解释为概率；按目标和世界条件校准，持续检查偏差。 / Describe outputs as probabilities only after evaluation; calibrate by target and world conditions and monitor error.

## 阶段 5：拓展世界内容 / Phase 5: Expand world coverage

- 按独立知识模块加入海洋、月岛地形和洞穴生态。 / Add ocean, lunar-island terrain, and cave biomes as separate knowledge modules.
- 再建模 boons、世界选项和后期 retrofit 对生成规则的影响。 / Then model how boons, world settings, and late-game retrofit affect generation.
- 为每个模块补充来源记录、可复现样例和评估覆盖后再纳入默认范围。 / Add source notes, reproducible examples, and evaluation coverage for each module before including it in the supported scope.
