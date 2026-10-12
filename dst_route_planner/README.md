# `dst_route_planner` 包说明

本包实现一个外置 DST 大陆线索推理原型：把地皮、可见 prefab、数量和方向提示转换成 task/room 信念值，再为目标方向打分。知识库当前覆盖默认森林世界的 20 个 task、53 个 room 和 20 种目标。完整安装、JSON 格式、支持目标清单和路线图见仓库根目录的 [`README.md`](../README.md) 与 [`TODO.md`](../TODO.md)。

## 运行

从仓库根目录运行。Python 3.10+；CLI 运行只依赖标准库：

```powershell
python route_planner.py --demo
python route_planner.py --list-targets
python route_planner.py --target moonbase --observe-json examples/moonbase_observation.json
```

`--observe-json` 接收以 `directions` 为顶层键的 JSON；`--current-json` 接收一个不带 `directions` 外层键的观测对象。示例文件在 `examples/`。

## 数据与计算层

- `models.py`：task、room、静态布局、目标链、观测、信念状态和方向得分的数据模型。
- `knowledge/forest_default.py`：当前手工整理的默认大陆 task/room/目标线索。
- `inference.py`：地皮、prefab 出现/缺失和数量等证据评分，task/room 信念更新。
- `navigation.py`：结合目标 task/room、连接/背景提示和直接目标证据对候选方向排序。
- `io.py`：从 JSON 构建方向观测与单点观测。
- `cli.py`：命令行、内置演示、目标列表和结果输出。
- `world_sampler.py`：实验性的 task sampler，可复现地选择 5 of 10 optional tasks；严格锁/钥匙链可能省略已选但不可解锁的 optional task。尚未建模 `storygen.lua` 强制连接回退或空间地图。

`p_dir` 表示启发式方向分数归一化后的相对份额，不是经过真实世界评估的到达概率。原型没有游戏内读取功能、Lua mod 或 HUD。负证据和静态布局用于区分候选 room；taskset 级 cave entrance、resurrection stone、wormhole 和单个 moose nest 通过任务约束处理，不表示固定房间。
