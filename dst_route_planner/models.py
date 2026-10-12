from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping


class Direction(str, Enum):
    NORTH = "north"
    NORTHEAST = "northeast"
    EAST = "east"
    SOUTHEAST = "southeast"
    SOUTH = "south"
    SOUTHWEST = "southwest"
    WEST = "west"
    NORTHWEST = "northwest"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RoomDef:
    name: str
    tile: str
    required_prefabs: frozenset[str] = frozenset()
    countprefabs: Mapping[str, float] = field(default_factory=dict)
    distributeprefabs: Mapping[str, float] = field(default_factory=dict)
    countstaticlayouts: Mapping[str, float] = field(default_factory=dict)
    tags: frozenset[str] = frozenset()
    negative_prefabs: frozenset[str] = frozenset()
    prefab_exclusions: Mapping[str, float] = field(default_factory=dict)
    prefab_weights: Mapping[str, float] = field(default_factory=dict)
    min_prefab_counts: Mapping[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class TaskDef:
    name: str
    locks: tuple[str, ...]
    keys_given: tuple[str, ...]
    room_choices: Mapping[str, float]
    room_bg: str
    background_room: str
    required: bool = False
    optional_weight: float = 0.0


@dataclass(frozen=True)
class StaticLayoutDef:
    name: str
    prefabs: frozenset[str]
    source: str


@dataclass(frozen=True)
class TargetChain:
    target_prefab: str
    task: str
    room: str
    landmark_prefabs: tuple[str, ...]
    static_layout: str = ""
    weight: float = 1.0
    note: str = ""
    min_count: int = 1
    max_count: int = 0


@dataclass(frozen=True)
class TaskGraphEdge:
    """A task-level parent connection recorded during graph sampling."""

    parent_task: str
    child_task: str
    forced: bool = False
    matched_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class SampledTaskGraph:
    """Sampled task nodes, parent edges, and attachment order."""

    tasks: tuple[str, ...]
    selected_optional_tasks: tuple[str, ...]
    edges: tuple[TaskGraphEdge, ...]
    start_task: str | None
    order: tuple[str, ...]


@dataclass(frozen=True)
class KnowledgeBase:
    tasks: Mapping[str, TaskDef]
    rooms: Mapping[str, RoomDef]
    static_layouts: Mapping[str, StaticLayoutDef]
    target_chains: Mapping[str, tuple[TargetChain, ...]]
    lock_to_keys: Mapping[str, tuple[str, ...]]
    start_tasks: tuple[str, ...]


@dataclass(frozen=True)
class Observation:
    """What a player can currently see.

    All fields are intentionally simple so that observations can be typed by a
    human, loaded from JSON, or later produced by an in-game mod.
    """

    tile_types: frozenset[str] = frozenset()
    prefabs_seen: frozenset[str] = frozenset()
    prefab_counts: Mapping[str, int] = field(default_factory=dict)
    room_hints: frozenset[str] = frozenset()
    task_hints: frozenset[str] = frozenset()
    connection_like: bool | None = None
    background_like: bool | None = None
    note: str = ""


@dataclass(frozen=True)
class DirectionObservation:
    direction: Direction
    observation: Observation


@dataclass(frozen=True)
class BeliefState:
    task_probs: Mapping[str, float]
    room_probs: Mapping[str, float]
    known_keys: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ActionScore:
    direction: Direction
    score: float
    target_task_probability: float
    target_room_probability: float
    connection_score: float
    explanation: tuple[str, ...]
