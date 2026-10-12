from __future__ import annotations

import json
from pathlib import Path

import pytest

from dst_route_planner.io import (
    InputValidationError,
    direction_observations_from_dict,
    load_direction_observations,
    observation_from_dict,
)


ROOT = Path(__file__).resolve().parent


def test_legacy_examples_load_without_a_schema_version() -> None:
    directions = load_direction_observations(ROOT / "examples" / "panflute_observation.json")
    current_data = json.loads((ROOT / "examples" / "current_observation.json").read_text(encoding="utf-8"))
    current = observation_from_dict(current_data)

    assert [item.direction.value for item in directions] == ["north", "east", "south", "west"]
    assert directions[0].observation.prefab_counts["flower"] == 1
    assert current.prefab_counts["grass"] == 2


def test_versioned_direction_container_and_current_observation_are_supported() -> None:
    container = {
        "schema_version": 1,
        "directions": {
            "schema_version": 1,
            "north": {"tile_types": ["DECIDUOUS"]},
        },
    }
    current = observation_from_dict({"schema_version": 1, "prefabs_seen": ["panflute"]})

    parsed = direction_observations_from_dict(container)
    assert len(parsed) == 1
    assert parsed[0].direction.value == "north"
    assert parsed[0].observation.tile_types == frozenset({"DECIDUOUS"})
    assert current.prefabs_seen == frozenset({"panflute"})


def test_counts_preserve_duplicates_and_accept_zero_as_omitted_evidence() -> None:
    duplicated = observation_from_dict({"prefabs_seen": ["flower", "flower", "flower"]})
    zero_only = observation_from_dict({"prefab_counts": {"flower": 0}})
    seen_with_zero = observation_from_dict(
        {"prefabs_seen": ["flower"], "prefab_counts": {"flower": 0}}
    )

    assert duplicated.prefab_counts == {"flower": 3}
    assert zero_only.prefab_counts == {}
    assert seen_with_zero.prefab_counts == {"flower": 1}


@pytest.mark.parametrize("count", [True, False, 1.5, -1, "2"])
def test_boolean_fractional_negative_and_string_counts_are_rejected(count) -> None:
    with pytest.raises(InputValidationError, match="non-negative integer"):
        observation_from_dict({"prefab_counts": {"flower": count}})


@pytest.mark.parametrize("version", [0, 2, True, "1", None])
def test_unsupported_or_malformed_schema_versions_are_rejected(version) -> None:
    with pytest.raises(InputValidationError, match="schema_version"):
        observation_from_dict({"schema_version": version})


@pytest.mark.parametrize("name", ["unknown", "northwest-ish", "UNKNOWN", ""])
def test_unknown_directions_are_rejected(name) -> None:
    with pytest.raises(InputValidationError, match="unknown direction"):
        direction_observations_from_dict({"directions": {name: {}}})


def test_invalid_observation_field_types_are_rejected() -> None:
    with pytest.raises(InputValidationError, match="connection_like"):
        observation_from_dict({"connection_like": 1})
    with pytest.raises(InputValidationError, match="tile_types"):
        observation_from_dict({"tile_types": "GRASS"})
    with pytest.raises(InputValidationError, match="directions must be"):
        direction_observations_from_dict({"directions": []})
