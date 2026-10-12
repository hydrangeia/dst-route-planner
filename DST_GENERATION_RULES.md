# DST 大陆地形生成规律：tasks 与 rooms

本文记录本地 DST 源码中的生成规则；源码尚未固定到具体游戏版本，手工知识库也尚未全量同步。当前实现范围见 [README.md](README.md)，字段校对与连接图工作见 [TODO.md](TODO.md)。`locks` 和 `keys_given` 描述建图时的连接约束，不是玩家游玩期间解锁地形的条件：默认大陆的固定地形在创建世界时生成。

本文暂时不考虑 `boons`、海上内容、后期 retrofit、玩家行为和容器随机 loot。只把 `taskset -> tasks -> rooms -> room contents/static layouts` 作为变量。

## 基本层级

大陆地形生成的核心层级是：

```text
taskset
  -> task 地形块
      -> rooms 房间/生态节点
          -> room contents
              -> distributeprefabs / countprefabs / countstaticlayouts
```

在默认大陆世界中，入口文件主要是：

- `scripts/map/tasksets/forest.lua`
- `scripts/map/tasks/dst_tasks_forestworld.lua`
- `scripts/map/rooms/forest/*.lua`
- `scripts/map/static_layouts/*.lua`
- `scripts/map/storygen.lua`
- `scripts/map/lockandkey.lua`

## taskset 如何选 task

默认 DST 森林世界使用 `AddTaskSet("default", ...)`。

`scripts/map/tasksets/forest.lua` 中默认 taskset 包含固定 tasks：

```lua
tasks = {
    "Make a pick",
    "Dig that rock",
    "Great Plains",
    "Squeltch",
    "Beeeees!",
    "Speak to the king",
    "Forest hunters",
    "Badlands",
    "For a nice walk",
    "Lightning Bluff",

    "MoonIsland_IslandShards",
    "MoonIsland_Beach",
    "MoonIsland_Forest",
    "MoonIsland_Baths",
    "MoonIsland_Mine",
}
```

并从 optional tasks 中随机选 `5` 个：

```lua
numoptionaltasks = 5
optionaltasks = {
    "Befriend the pigs",
    "Kill the spiders",
    "Killer bees!",
    "Make a Beehat",
    "The hunters",
    "Magic meadow",
    "Frogs and bugs",
    "Mole Colony Deciduous",
    "Mole Colony Rocks",
    "MooseBreedingTask",
}
```

起始 task 固定从 `valid_start_tasks` 里选：

```lua
valid_start_tasks = { "Make a pick" }
```

所以默认大陆主链一定有 `Make a pick`，也一定有 `Speak to the king`。

## task 内如何生成 rooms

每个 task 在 `scripts/map/tasks/dst_tasks_forestworld.lua` 里定义。

一个 task 的关键字段：

- `locks`: 这个 task 连接到已有世界前需要哪些锁被打开。
- `keys_given`: 这个 task 生成后向后续 task 提供哪些 key。
- `room_choices`: 这个 task 内部一定或随机生成哪些 rooms。
- `room_bg`: task 的主地皮类型。
- `background_room`: 填充空白区域时使用的背景 room。
- `entrance_room`: 有些 task 会在入口边界放阻塞/守卫 room。

例如猪王地形：

```lua
AddTask("Speak to the king", {
    locks={LOCKS.PIGKING, LOCKS.TIER2},
    keys_given={KEYS.PIGS, KEYS.GOLD, KEYS.TIER3},
    room_choices={
        ["PigKingdom"] = 1,
        ["MagicalDeciduous"] = 1,
        ["DeepDeciduous"] = function() return 3 + math.random(SIZE_VARIATION) end,
    },
    room_bg=WORLD_TILES.GRASS,
    background_room="BGDeciduous",
})
```

结论：

- `Speak to the king` 是默认大陆必选 task。
- 它内部固定包含 `PigKingdom` room 1 个。
- 它内部固定包含 `MagicalDeciduous` room 1 个。
- 它内部还包含若干 `DeepDeciduous` room。

## task 与 task 如何连接

连接逻辑在 `scripts/map/storygen.lua` 和 `scripts/map/lockandkey.lua`。

生成流程简化为：

1. 从起始 task 开始，默认是 `Make a pick`。
2. 对未使用 task，检查它的 `locks` 是否能被已生成 task 的 `keys_given` 解开。
3. 能解锁的 task 进入候选。
4. 从候选里随机选一个接到已有图上。
5. 新 task 的 `keys_given` 加入可用 key 池。
6. 重复直到所有选中的 tasks 都接入。

`lockandkey.lua` 里说明：

```lua
-- Locks are unlocked if ANY key is provided.
-- However, ALL locks must be opened for a task to be unlocked.
```

意思是：

- 一个 task 可能有多个 lock，所有 lock 都必须满足。
- 对每个 lock，只要拥有它允许的任意一个 key 即可。

例如 `Speak to the king`：

```lua
locks={LOCKS.PIGKING, LOCKS.TIER2}
```

`LOCKS.PIGKING` 需要：

```lua
KEYS.TRINKETS
```

`LOCKS.TIER2` 可由：

```lua
KEYS.TIER2 或 KEYS.TIER3
```

因此 `Speak to the king` 会连接在已经提供 `TRINKETS`，并且达到 `TIER2` 的地形之后。默认链路里常见来源是：

- `Dig that rock` 给 `KEYS.TRINKETS` 和 `KEYS.TIER1`
- `Great Plains`、`Beeeees!` 等给 `KEYS.TIER2`

所以猪王地形通常不是起点附近第一块，而是在较外层、已解锁到中期资源层后接入。

## room 内如何生成实体

room 定义在 `scripts/map/rooms/forest/*.lua`。

room contents 常见字段：

- `distributepercent`: 用多少可用点位分布随机 prefab。
- `distributeprefabs`: 随机分布 prefab 的权重表。
- `countprefabs`: 固定数量 prefab。
- `countstaticlayouts`: 固定布局。布局来自 `scripts/map/static_layouts/*.lua`。
- `required_prefabs`: 标记该 room 必须满足的重要 prefab，常用于保证世界唯一关键物。

## 排箫的大陆固定链路

排箫 `panflute` 的关键大陆链路是：

```text
default taskset
  -> task: Speak to the king
      -> room: MagicalDeciduous
          -> countstaticlayouts: DeciduousPond = 1
              -> static_layout: deciduous_pond.lua
                  -> statueglommer
                  -> panflute
```

### 1. 默认 taskset 必含猪王 task

`scripts/map/tasksets/forest.lua` 默认 taskset 的 `tasks` 里固定包含：

```lua
"Speak to the king"
```

### 2. 猪王 task 必含格罗姆 room

`scripts/map/tasks/dst_tasks_forestworld.lua`：

```lua
AddTask("Speak to the king", {
    room_choices={
        ["PigKingdom"] = 1,
        ["MagicalDeciduous"] = 1,
        ["DeepDeciduous"] = function() return 3 + math.random(SIZE_VARIATION) end,
    },
})
```

### 3. `MagicalDeciduous` 必放 `DeciduousPond`

`scripts/map/rooms/forest/DLCrooms.lua`：

```lua
AddRoom("MagicalDeciduous", {
    value = WORLD_TILES.DECIDUOUS,
    required_prefabs = {"statueglommer"},
    contents = {
        countprefabs = {
            catcoonden = 1,
        },
        countstaticlayouts = {
            ["DeciduousPond"] = 1,
            ["HalloweenPumpkinCarving"] = function()
                return IsSpecialEventActive(SPECIAL_EVENTS.HALLOWED_NIGHTS) and 1 or 0
            end,
        },
    },
})
```

### 4. `DeciduousPond` 布局里有格罗姆雕像和排箫

`scripts/map/static_layouts/deciduous_pond.lua` 中：

```lua
type = "statueglommer"
```

以及：

```lua
type = "panflute"
properties = {
    ["chance"] = ".5"
}
```

当前这条生成路径里，`forest_map.lua` 的实体添加函数只处理 `data`、`id`、`scenario`，没有处理 static layout 对象上的 `chance` 字段。因此在这份源码逻辑下，`panflute` 随 `DeciduousPond` 布局一起生成。

## 对排箫的大陆寻找规律

只考虑 tasks 和 rooms 时：

1. 先找默认大陆中的 `Speak to the king` task，也就是猪王所在的大型落叶林地形。
2. 这个 task 内必有 `PigKingdom`，也必有 `MagicalDeciduous`。
3. `MagicalDeciduous` 里必有 `DeciduousPond`。
4. `DeciduousPond` 静态布局中有 `statueglommer`，旁边就是 `panflute`。

实际地图上表现为：

- 猪王地形整体是落叶林生态。
- 猪王与格罗姆雕像同属 `Speak to the king` task，但不一定在同一个 room。
- 格罗姆雕像在 `MagicalDeciduous` room 的 `DeciduousPond` 布局里。
- 排箫就在格罗姆雕像旁边。

## 月基地 (Moonbase) 生成规律

### 生成路径

1. **必有 task**: `Forest hunters`（默认大陆固定 task，建图连接锁：ADVANCED_COMBAT + MONSTERS_DEFEATED + TIER3）
2. **Room 数量**: `Forest hunters.room_choices` 固定包含 1 个 `MoonbaseOne`，其他 room 也同时生成
3. **静态布局**: `MoonbaseOne` 房间必有 `MoonbaseOne` 静态布局
4. **地点特征**: `MoonbaseOne` 静态布局包含 `moonbase` 实体

### 实际地图表现

- 月基地在森林生态（FOREST tile）区域
- 随 `Forest hunters` task 在创建世界时生成
- 标志性物品：evergreen（针叶树）、sapling（树苗）、grass（草）
- 与 walrus_camp 同属 `Forest hunters` 任务，但在不同房间

## 海象营地 (Walrus Camp) 生成规律

### 生成路径

1. **必有 task**: `Forest hunters`（默认大陆固定 task）
2. **Room 数量**: `Forest hunters.room_choices` 固定包含 1 个 `WalrusHut_Grassy`（草地类型）
3. **房间特征**: `WalrusHut_Grassy` 必须包含 `walrus_camp` prefab
4. **地点特征**: 草地和池塘环境

### 实际地图表现

- 海象营地在草地生态（GRASS tile）区域
- 随 `Forest hunters` task 在创建世界时生成
- 标志性物品：grass（草）、pond（池塘）、evergreen（针叶树）
- 与 moonbase 同属 `Forest hunters` 地形块

## 蜜蜂女王 (Beequeenhive) 生成规律

### 生成路径

1. **必有 task**: `Beeeees!`（默认大陆固定 task，建图连接锁：BEEHIVE + TIER1）
2. **Room 数量**: `Beeeees!.room_choices` 固定包含 1 个 `BeeQueenBee`（蜜蜂女王房间）
3. **房间数量**: `BeeQueenBee.countprefabs` 包含 1 个 `beequeenhive`、1 个 `beehive` 和随机 1–2 个 `wasphive`
4. **地点特征**: 花朵的分布权重为 5，不能把该权重直接解释成固定 5 朵花

### 实际地图表现

- 蜜蜂女王在草地/清晰地区（GRASS tile）
- 随 `Beeeees!` task 在创建世界时生成
- 标志性物品：flower（花朵）、beehive（蜜蜂巢）、wasphive（黄蜂巢）
- 花朵密度很高，是识别该区域的关键

## 曼德拉草 (Mandrake Planted) 生成规律

### 生成路径

1. **Task**: `For a nice walk`（默认大陆固定 task，建图连接锁：BASIC_COMBAT + TIER2）
2. **Room 数量**: `For a nice walk.room_choices` 包含 `1 + math.random(SIZE_VARIATION)` 个 `MandrakeHome`
3. **房间特征**: `MandrakeHome` 房间必有 1 个 `mandrake_planted` prefab
4. **地点特征**: 本地源码定义的 room 地皮为 `GRASS`，分布中包含针叶树、花朵和萤火虫；当前知识库仍使用 `FOREST`，待进一步校对

### 实际地图表现

- `MandrakeHome` 使用草地地皮（GRASS tile），内容具有森林特征，所在 task 的背景为森林
- 随 `For a nice walk` task 在创建世界时生成
- 标志性物品：evergreen（针叶树）、flower（花朵）、fireflies（萤火虫）
- 与深森林（Deep Forest）易混，需注意fireflies标记

## 泛化到其他实体

如果要查另一个实体 `X` 的生成规律，只看 tasks/rooms 时按这个顺序：

1. 在 `scripts/map/rooms` 搜 `X`。
2. 如果在 `distributeprefabs`，记录 room 名和权重。
3. 如果在 `countprefabs`，记录 room 名和数量。
4. 如果没在 rooms 里直接出现，搜 `scripts/map/static_layouts`。
5. 找到 static layout 后，反查哪个 room 的 `countstaticlayouts` 引用它。
6. 找到 room 后，反查哪个 task 的 `room_choices` 引用它。
7. 找到 task 后，查 taskset 是否固定包含它，还是 optional 随机包含它。
8. 最后查 task 的 `locks` 和 `keys_given`，判断它大概会接在地形链的哪个阶段。
