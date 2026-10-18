from __future__ import annotations

import json
from pathlib import Path

import pytest

try:
    from lupa import LuaRuntime
except ImportError:  # Lupa is a development-only test dependency.
    LuaRuntime = None


ROOT = Path(__file__).resolve().parent
MOD_ROOT = ROOT / "mods" / "dst_route_collector"
MARKER = "DST_ROUTE_PLANNER_LIVE_V1 "
DIRECTIONS = {
    "north",
    "northeast",
    "east",
    "southeast",
    "south",
    "southwest",
    "west",
    "northwest",
}


def _from_lua(value):
    if hasattr(value, "keys") and hasattr(value, "items"):
        keys = list(value.keys())
        if not keys:
            return []
        if all(type(key) is int for key in keys):
            largest = max(keys)
            if set(keys) == set(range(1, largest + 1)):
                return [_from_lua(value[index]) for index in range(1, largest + 1)]
        return {str(key): _from_lua(item) for key, item in value.items()}
    return value


def _make_stub(
    *,
    dedicated: bool = False,
    player_present: bool = True,
    visibility_mode: str = "point",
    has_tile_center_api: bool = True,
    has_passability_api: bool = True,
    passability_mode: str = "boolean",
    has_pathfinder_api: bool = True,
    pathfinder_mode: str = "true",
    player_x: float = 0,
    player_z: float = 0,
):
    lines: list[str] = []
    sim_callbacks = []
    lua = LuaRuntime(unpack_returned_tuples=True)

    def add_sim_post_init(callback):
        sim_callbacks.append(callback)

    def encode(value):
        return json.dumps(_from_lua(value), separators=(",", ":"), sort_keys=True)

    lua.globals().AddSimPostInit = add_sim_post_init
    lua.globals().print = lines.append
    lua.globals().encode_snapshot = encode
    lua.execute(
        """
        local function make_map()
            local origin_x, origin_z = 101, -53
            local tile_reads = {}
            local passability_reads = {}
            return {
                tile_reads = tile_reads,
                passability_reads = passability_reads,
                GetTileXYAtPoint = function(self, x, y, z)
                    return math.floor((x - origin_x) / 4), math.floor((z - origin_z) / 4)
                end,
                GetTileCenterPoint = function(self, tx, ty)
                    return origin_x + tx * 4 + 2, 0, origin_z + ty * 4 + 2
                end,
                GetTileAtPoint = function(self, x, y, z)
                    tile_reads[#tile_reads + 1] = { x = x, z = z }
                    local tx, ty = self:GetTileXYAtPoint(x, y, z)
                    if tx == -24 and ty == 13 then return 65535 end
                    if x <= -10 then return 3 end
                    if x >= 4 then return 2 end
                    return 1
                end,
                IsPassableAtPoint = function(self, x, y, z, allow_water, ignore_platforms)
                    passability_reads[#passability_reads + 1] = {
                        x = x,
                        y = y,
                        z = z,
                        allow_water = allow_water,
                        ignore_platforms = ignore_platforms,
                    }
                    if self.passability_mode == "error" then error("passability unavailable") end
                    if self.passability_mode == "nil" then return nil end
                    if self.passability_mode == "nonboolean" then return "unknown" end
                    if self.passability_mode == "center_false" then
                        return not (x == -1 and z == 1)
                    end
                    return x < 4
                end,
            }
        end

        function make_world(world_id, world_kind, omit_center_api)
            local map = make_map()
            local pathfinder_reads = {}
            local pathfinder = {
                IsClear = function(self, ax, ay, az, bx, by, bz, options)
                    pathfinder_reads[#pathfinder_reads + 1] = {
                        ax = ax,
                        ay = ay,
                        az = az,
                        bx = bx,
                        by = by,
                        bz = bz,
                        options = options,
                    }
                    if self.mode == "error" then error("pathfinder unavailable") end
                    if self.mode == "nil" then return nil end
                    if self.mode == "nonboolean" then return "unknown" end
                    if self.mode == "forward_nil" and (ax < bx or az < bz) then return nil end
                    if self.mode == "reverse_nil" and (ax > bx or az > bz) then return nil end
                    if self.mode == "reverse_false" then return ax < bx or az < bz end
                    if self.mode == "forward_false" then return ax > bx or az > bz end
                    if self.mode == "anchor_flip" then return ax < 0.1 and bx < 0.1 end
                    if self.mode == "anchor_one_way_blocked" then return ax == 0 end
                    return true
                end,
                reads = pathfinder_reads,
            }
            if omit_center_api then map.GetTileCenterPoint = nil end
            return {
                worldprefab = world_kind,
                meta = { session_identifier = world_id },
                Map = map,
                Pathfinder = pathfinder,
                pathfinder_reads = pathfinder_reads,
                DoPeriodicTask = function(self, period, callback)
                    self.period = period
                    self.callback = callback
                end,
            }
        end

        function make_player(x, y, z, visibility_mode)
            local position = { x = x, y = y, z = z }
            local player = {
                Transform = {
                    GetWorldPosition = function(self)
                        return position.x, position.y, position.z
                    end,
                },
                IsValid = function(self) return true end,
                SetWorldPosition = function(self, next_x, next_y, next_z)
                    position.x = next_x
                    position.y = next_y
                    position.z = next_z
                end,
            }
            if visibility_mode == "point" or visibility_mode == "tile" then
                player.CanSeePointOnMiniMap = function(self, px, py, pz)
                    return px * px + pz * pz <= 12 * 12 and px > -10
                end
            end
            if visibility_mode == "tile" then
                player.CanSeeTileOnMiniMap = function(self, tx, ty)
                    return tx % 2 == 0
                end
            elseif visibility_mode == "explorer" then
                player.player_classified = {
                    MapExplorer = {
                        IsTileSeeable = function(self, tx, ty) return tx >= -26 end,
                    },
                }
            end
            return player
        end

        function make_entity(prefab, x, z, visible, tags)
            tags = tags or {}
            return {
                prefab = prefab,
                Transform = {
                    GetWorldPosition = function(self) return x, 0, z end,
                },
                entity = {
                    IsVisible = function(self) return visible end,
                },
                IsValid = function(self) return true end,
                HasTag = function(self, tag) return tags[tag] == true end,
            }
        end
        """
    )

    g = lua.table()
    g["os"] = lua.table_from({"time": lua.eval("function() return 1700000000 end")})
    g["json"] = lua.table_from({"encode_compliant": lua.globals().encode_snapshot})
    g["WORLD_TILES"] = lua.table_from({"INVALID": 65535})
    g["GROUND"] = lua.table_from({"GRASS": 1, "MARSH": 2, "SECRET": 3})
    g["TheNet"] = lua.table_from(
        {"IsDedicated": lua.eval(f"function(self) return {'true' if dedicated else 'false'} end")}
    )
    g["TheCamera"] = lua.table_from(
        {"GetHeading": lua.eval("function(self) return 73 end")}
    )
    g["TheSim"] = lua.table_from(
        {
            "FindEntities": lua.eval(
                "function(self, x, y, z, radius) "
                "assert(radius == 16); return self.entities end"
            ),
            "entities": lua.table(),
        }
    )
    world = lua.globals().make_world("forest-session-1", "forest", not has_tile_center_api)
    world["Map"]["passability_mode"] = passability_mode
    if not has_passability_api:
        world["Map"]["IsPassableAtPoint"] = None
    world["Pathfinder"]["mode"] = pathfinder_mode
    if not has_pathfinder_api:
        world["Pathfinder"] = None
    g["TheWorld"] = world
    if player_present:
        g["ThePlayer"] = lua.globals().make_player(
            player_x, 0, player_z, visibility_mode
        )
    g["GLOBAL"] = g
    lua.globals()["GLOBAL"] = g
    lua.execute((MOD_ROOT / "collector.lua").read_text(encoding="utf-8"))

    return {
        "g": g,
        "lines": lines,
        "lua": lua,
        "sim_callbacks": sim_callbacks,
        "world": world,
    }


def _snapshot(lines: list[str]) -> dict:
    assert lines
    assert lines[-1].startswith(MARKER)
    assert "\n" not in lines[-1]
    return json.loads(lines[-1][len(MARKER) :])


def _add_entities(runtime, entities) -> None:
    lua = runtime["lua"]
    runtime["g"]["TheSim"]["entities"] = lua.table_from(entities)


def _pathfinder_reads(runtime) -> list[dict]:
    return _from_lua(runtime["world"]["pathfinder_reads"])


def test_mod_is_client_only_and_uses_one_marked_line_per_snapshot() -> None:
    modinfo = (MOD_ROOT / "modinfo.lua").read_text(encoding="utf-8")
    modmain = (MOD_ROOT / "modmain.lua").read_text(encoding="utf-8")
    collector = (MOD_ROOT / "collector.lua").read_text(encoding="utf-8")

    assert "client_only_mod = true" in modinfo
    assert 'version = "0.5.0"' in modinfo
    assert 'modimport("collector.lua")' in modmain
    assert MARKER.strip() in collector
    assert "print(\"DST_ROUTE_PLANNER_LIVE_V1 \" .. G.json.encode_compliant(snapshot))" in collector


@pytest.mark.skipif(LuaRuntime is None, reason="install the development-only Lupa dependency")
def test_stub_emits_eight_world_axis_sectors_and_only_observable_entities() -> None:
    runtime = _make_stub()
    lua = runtime["lua"]
    entities = [
        lua.globals().make_entity("grass", 2, 2, True),
        lua.globals().make_entity("tentacle", 0, 8, True),
        lua.globals().make_entity("moonbase", 8, 8, True),
        lua.globals().make_entity("pigking", 8, 0, True),
        lua.globals().make_entity("wasphive", 8, -8, True),
        lua.globals().make_entity("cave_entrance", 0, -8, True),
        lua.globals().make_entity("walrus_camp", -8, -8, True),
        lua.globals().make_entity("spiderden", -8, 0, True),
        lua.globals().make_entity("beequeenhive", -8, 8, True),
        lua.globals().make_entity("oasislake", 4, -10, False),
        lua.globals().make_entity("lightninggoat", -10, 0, True),
        lua.globals().make_entity("fx_spark", 4, 8, True, lua.table_from({"FX": True})),
        lua.globals().make_entity("decor", 4, -8, True, lua.table_from({"DECOR": True})),
        lua.globals().make_entity("limbo_item", -4, 8, True, lua.table_from({"INLIMBO": True})),
        lua.globals().make_entity("remote_player", 0, 8, True, lua.table_from({"player": True})),
        lua.globals().make_entity("private_classified", -8, 4, True, lua.table_from({"CLASSIFIED": True})),
    ]
    _add_entities(runtime, entities)

    runtime["sim_callbacks"][0](runtime["world"])
    assert runtime["world"]["period"] == 1
    runtime["world"]["callback"]()
    first = _snapshot(runtime["lines"])
    runtime["world"]["callback"]()
    second = _snapshot(runtime["lines"])

    assert first["live_version"] == 1
    assert first["world_id"] == "forest-session-1"
    assert first["world_kind"] == "forest"
    assert first["position"] == {"x": 0, "y": 0, "z": 0}
    assert first["camera_heading"] == 73
    assert first["sequence"] == 1
    assert second["sequence"] == 2
    assert first["session_id"] == second["session_id"]
    assert first["player_anchor"] == {"x": -1, "z": 1, "clear": True}
    assert set(first["player_anchor"]) == {"x", "z", "clear"}
    assert set(first["directions"]) == DIRECTIONS
    assert first["current"]["prefab_counts"] == {"grass": 1}
    assert "GRASS" in first["current"]["tile_types"]
    assert "MARSH" in first["directions"]["east"]["tile_types"]
    assert first["directions"]["north"]["prefab_counts"] == {"tentacle": 1}
    assert first["directions"]["northeast"]["prefab_counts"] == {"moonbase": 1}
    assert first["directions"]["east"]["prefab_counts"] == {"pigking": 1}
    assert first["directions"]["southeast"]["prefab_counts"] == {"wasphive": 1}
    assert first["directions"]["south"]["prefab_counts"] == {"cave_entrance": 1}
    assert first["directions"]["southwest"]["prefab_counts"] == {"walrus_camp": 1}
    assert first["directions"]["west"]["prefab_counts"] == {"spiderden": 1}
    assert first["directions"]["northwest"]["prefab_counts"] == {"beequeenhive": 1}
    assert {item["prefab"] for item in first["landmarks"]} == {
        "beequeenhive",
        "cave_entrance",
        "moonbase",
        "pigking",
        "spiderden",
        "tentacle",
        "walrus_camp",
        "wasphive",
    }
    serialized = json.dumps(first)
    for hidden_prefab in ("oasislake", "lightninggoat", "fx_spark", "decor", "limbo_item", "remote_player", "private_classified"):
        assert hidden_prefab not in serialized
    assert "connection_like" not in serialized
    for observation in [first["current"], *first["directions"].values()]:
        if "tile_types" in observation:
            assert observation["tile_types"]


@pytest.mark.skipif(LuaRuntime is None, reason="install the development-only Lupa dependency")
def test_terrain_uses_map_tile_centers_and_only_reads_revealed_noninvalid_tiles() -> None:
    from dst_route_planner.live import validate_snapshot

    runtime = _make_stub(visibility_mode="tile")
    runtime["sim_callbacks"][0](runtime["world"])
    runtime["world"]["callback"]()
    first = _snapshot(runtime["lines"])

    terrain = first["terrain"]
    assert terrain["tile_size"] == 4
    tiles = terrain["tiles"]
    assert 0 < len(tiles) <= 256
    assert [(tile["x"], tile["z"]) for tile in tiles] == sorted(
        (tile["x"], tile["z"]) for tile in tiles
    )
    assert len({(tile["x"], tile["z"]) for tile in tiles}) == len(tiles)
    assert all((tile["x"] - 103) % 8 == 0 for tile in tiles)
    assert all(
        tile["x"] * tile["x"] + tile["z"] * tile["z"] <= 16 * 16
        for tile in tiles
    )
    # The real tile containing the player is centered at (-1, 1) because the
    # test map has a nonzero origin; a world-coordinate / 4 guess misses it.
    assert any(tile["x"] == -1 and tile["z"] == 1 for tile in tiles)
    # CanSeeTileOnMiniMap takes precedence over the narrower point wrapper.
    assert any(tile["x"] == 15 and tile["z"] == 1 for tile in tiles)
    # The visible INVALID cell is queried, then removed from the output.
    assert not any(tile["x"] == 7 and tile["z"] == 1 for tile in tiles)
    # The hidden center at (3, 1) has an odd x index and must never be queried.
    reads = _from_lua(runtime["world"]["Map"]["tile_reads"])
    assert not any(read["x"] == 3 and read["z"] == 1 for read in reads)

    passability_reads = _from_lua(runtime["world"]["Map"]["passability_reads"])
    player_point_reads = [
        read for read in passability_reads if (read["x"], read["z"]) == (0, 0)
    ]
    assert len(player_point_reads) == 1
    terrain_passability_reads = [read for read in passability_reads if read not in player_point_reads]
    assert {(read["x"], read["z"]) for read in terrain_passability_reads} == {
        (tile["x"], tile["z"]) for tile in tiles
    }
    assert all(
        read["y"] == 0
        and read["allow_water"] is False
        and read["ignore_platforms"] is True
        for read in terrain_passability_reads + player_point_reads
    )
    assert not any(read["x"] == 7 and read["z"] == 1 for read in passability_reads)
    assert not any(read["x"] == 3 and read["z"] == 1 for read in passability_reads)
    assert not any(read["x"] == 15 and read["z"] == 13 for read in passability_reads)
    assert next(tile for tile in tiles if tile["x"] == -1 and tile["z"] == 1)["passable"] is True
    assert next(tile for tile in tiles if tile["x"] == 15 and tile["z"] == 1)["passable"] is False

    validate_snapshot(first)

    runtime["g"]["ThePlayer"] = runtime["lua"].globals().make_player(
        0.2, 0, 0.2, "tile"
    )
    runtime["world"]["callback"]()
    second = _snapshot(runtime["lines"])
    assert second["terrain"]["tiles"] == tiles


@pytest.mark.skipif(LuaRuntime is None, reason="install the development-only Lupa dependency")
def test_player_anchor_uses_actual_player_point_and_native_tile_center() -> None:
    from dst_route_planner.live import validate_snapshot

    runtime = _make_stub()
    runtime["sim_callbacks"][0](runtime["world"])
    runtime["world"]["callback"]()
    snapshot = _snapshot(runtime["lines"])

    # The fake map has a nonzero origin. The map API maps (0, 0) to center (-1, 1).
    anchor = snapshot["player_anchor"]
    assert anchor == {"x": -1, "z": 1, "clear": True}
    assert set(anchor) == {"x", "z", "clear"}
    assert next(
        tile
        for tile in snapshot["terrain"]["tiles"]
        if (tile["x"], tile["z"]) == (-1, 1)
    )["passable"] is True

    anchor_reads = [
        read
        for read in _pathfinder_reads(runtime)
        if (read["ax"], read["ay"], read["az"]) == (0, 0, 0)
        and (read["bx"], read["by"], read["bz"]) == (-1, 0, 1)
        or (read["ax"], read["ay"], read["az"]) == (-1, 0, 1)
        and (read["bx"], read["by"], read["bz"]) == (0, 0, 0)
    ]
    assert len(anchor_reads) == 2
    assert anchor_reads[0]["options"] == {"ignorewalls": False, "ignorecreep": True}
    assert anchor_reads[1]["options"] == {"ignorewalls": False, "ignorecreep": True}
    validate_snapshot(snapshot)


@pytest.mark.skipif(LuaRuntime is None, reason="install the development-only Lupa dependency")
def test_player_anchor_records_false_when_the_actual_player_point_is_not_passable() -> None:
    from dst_route_planner.live import validate_snapshot

    runtime = _make_stub(player_x=4.2)
    runtime["sim_callbacks"][0](runtime["world"])
    runtime["world"]["callback"]()
    snapshot = _snapshot(runtime["lines"])

    assert snapshot["player_anchor"] == {"x": 3, "z": 1, "clear": False}
    assert next(
        tile
        for tile in snapshot["terrain"]["tiles"]
        if (tile["x"], tile["z"]) == (3, 1)
    )["passable"] is True
    reads = _from_lua(runtime["world"]["Map"]["passability_reads"])
    assert any(read["x"] == 4.2 and read["z"] == 0 for read in reads)
    assert not any(
        read["ax"] == 4.2 or read["bx"] == 4.2 for read in _pathfinder_reads(runtime)
    )
    validate_snapshot(snapshot)


@pytest.mark.skipif(LuaRuntime is None, reason="install the development-only Lupa dependency")
def test_player_anchor_uses_both_path_checks_even_when_player_is_at_tile_center() -> None:
    offset_runtime = _make_stub(pathfinder_mode="anchor_one_way_blocked")
    offset_runtime["sim_callbacks"][0](offset_runtime["world"])
    offset_runtime["world"]["callback"]()
    offset_snapshot = _snapshot(offset_runtime["lines"])
    assert offset_snapshot["player_anchor"] == {"x": -1, "z": 1, "clear": False}

    offset_reads = [
        read
        for read in _pathfinder_reads(offset_runtime)
        if (read["ax"], read["az"], read["bx"], read["bz"])
        in {(0, 0, -1, 1), (-1, 1, 0, 0)}
    ]
    assert len(offset_reads) == 2

    centered_runtime = _make_stub(player_x=-1, player_z=1)
    centered_runtime["sim_callbacks"][0](centered_runtime["world"])
    centered_runtime["world"]["callback"]()
    centered_snapshot = _snapshot(centered_runtime["lines"])
    assert centered_snapshot["player_anchor"] == {"x": -1, "z": 1, "clear": True}
    center_reads = [
        read
        for read in _pathfinder_reads(centered_runtime)
        if (read["ax"], read["az"], read["bx"], read["bz"])
        == (-1, 1, -1, 1)
    ]
    assert len(center_reads) == 2


@pytest.mark.skipif(LuaRuntime is None, reason="install the development-only Lupa dependency")
def test_player_anchor_is_omitted_without_a_sampled_passable_visible_center() -> None:
    hidden_center = _make_stub(visibility_mode="tile", player_x=12.2)
    hidden_center["sim_callbacks"][0](hidden_center["world"])
    hidden_center["world"]["callback"]()
    hidden_snapshot = _snapshot(hidden_center["lines"])
    hidden_tiles = hidden_snapshot["terrain"]["tiles"]
    assert hidden_tiles
    assert not any((tile["x"], tile["z"]) == (11, 1) for tile in hidden_tiles)
    assert "player_anchor" not in hidden_snapshot
    assert not any(
        read["x"] == 12.2 and read["z"] == 0
        for read in _from_lua(hidden_center["world"]["Map"]["passability_reads"])
    )

    blocked_center = _make_stub(passability_mode="center_false")
    blocked_center["sim_callbacks"][0](blocked_center["world"])
    blocked_center["world"]["callback"]()
    blocked_snapshot = _snapshot(blocked_center["lines"])
    assert "player_anchor" not in blocked_snapshot
    assert not any(
        read["x"] == 0 and read["z"] == 0
        for read in _from_lua(blocked_center["world"]["Map"]["passability_reads"])
    )


@pytest.mark.skipif(LuaRuntime is None, reason="install the development-only Lupa dependency")
def test_player_anchor_is_rechecked_after_each_player_movement() -> None:
    runtime = _make_stub(pathfinder_mode="anchor_flip")
    runtime["sim_callbacks"][0](runtime["world"])
    runtime["world"]["callback"]()
    first = _snapshot(runtime["lines"])

    player = runtime["g"]["ThePlayer"]
    player["SetWorldPosition"](player, 0.2, 0, 0.2)
    runtime["world"]["callback"]()
    second = _snapshot(runtime["lines"])

    assert first["player_anchor"] == {"x": -1, "z": 1, "clear": True}
    assert second["player_anchor"] == {"x": -1, "z": 1, "clear": False}
    assert second["sequence"] == first["sequence"] + 1
    reads = _pathfinder_reads(runtime)
    for player_x in (0, 0.2):
        assert sum(
            (read["ax"], read["az"], read["bx"], read["bz"])
            == (player_x, player_x, -1, 1)
            or (read["ax"], read["az"], read["bx"], read["bz"])
            == (-1, 1, player_x, player_x)
            for read in reads
        ) == 2
    point_reads = _from_lua(runtime["world"]["Map"]["passability_reads"])
    for player_x in (0, 0.2):
        assert sum(read["x"] == player_x and read["z"] == player_x for read in point_reads) == 1


@pytest.mark.skipif(LuaRuntime is None, reason="install the development-only Lupa dependency")
def test_terrain_falls_back_to_point_visibility_and_omits_it_without_center_api() -> None:
    runtime = _make_stub(visibility_mode="point")
    runtime["sim_callbacks"][0](runtime["world"])
    runtime["world"]["callback"]()
    snapshot = _snapshot(runtime["lines"])
    assert snapshot["terrain"]["tiles"]
    assert all(
        tile["x"] * tile["x"] + tile["z"] * tile["z"] <= 12 * 12
        and tile["x"] > -10
        for tile in snapshot["terrain"]["tiles"]
    )

    without_centers = _make_stub(has_tile_center_api=False)
    without_centers["sim_callbacks"][0](without_centers["world"])
    without_centers["world"]["callback"]()
    old_snapshot = _snapshot(without_centers["lines"])
    assert "terrain" not in old_snapshot
    assert "player_anchor" not in old_snapshot
    assert old_snapshot["current"].get("tile_types")


@pytest.mark.skipif(LuaRuntime is None, reason="install the development-only Lupa dependency")
@pytest.mark.parametrize(
    ("stub_options", "expect_reads"),
    [
        ({"has_passability_api": False}, False),
        ({"passability_mode": "error"}, True),
        ({"passability_mode": "nil"}, True),
        ({"passability_mode": "nonboolean"}, True),
    ],
)
def test_terrain_passability_failure_or_unknown_keeps_snapshot_and_omits_status(
    stub_options: dict, expect_reads: bool
) -> None:
    from dst_route_planner.live import validate_snapshot

    runtime = _make_stub(visibility_mode="tile", **stub_options)
    runtime["sim_callbacks"][0](runtime["world"])
    runtime["world"]["callback"]()
    snapshot = _snapshot(runtime["lines"])

    terrain_tiles = snapshot["terrain"]["tiles"]
    assert terrain_tiles
    assert all("passable" not in tile for tile in terrain_tiles)
    assert "player_anchor" not in snapshot
    reads = _from_lua(runtime["world"]["Map"]["passability_reads"])
    assert len(reads) == (len(terrain_tiles) if expect_reads else 0)
    assert _from_lua(runtime["world"]["pathfinder_reads"]) == []
    validate_snapshot(snapshot)


@pytest.mark.skipif(LuaRuntime is None, reason="install the development-only Lupa dependency")
@pytest.mark.parametrize(
    ("pathfinder_mode", "expected_clear"),
    [("true", True), ("reverse_false", False), ("forward_false", False)],
)
def test_terrain_connections_require_bidirectional_clear_checks_and_use_neighbor_centers(
    pathfinder_mode: str, expected_clear: bool
) -> None:
    from dst_route_planner.live import validate_snapshot

    runtime = _make_stub(visibility_mode="point", pathfinder_mode=pathfinder_mode)
    runtime["sim_callbacks"][0](runtime["world"])
    runtime["world"]["callback"]()
    snapshot = _snapshot(runtime["lines"])

    tiles = snapshot["terrain"]["tiles"]
    by_position = {(tile["x"], tile["z"]): tile for tile in tiles}
    west_tile = by_position[(-1, 1)]
    east_tile = by_position[(3, 1)]
    assert west_tile["passable"] is True
    assert east_tile["passable"] is True
    assert west_tile["connections"]["east"] is expected_clear

    reads = _from_lua(runtime["world"]["pathfinder_reads"])
    assert reads
    assert len(reads) % 2 == 0
    assert len(reads) // 2 <= 2 * len(tiles)
    checked_pairs = set()
    for index in range(0, len(reads), 2):
        forward, reverse = reads[index : index + 2]
        assert (forward["ax"], forward["ay"], forward["az"]) == (
            reverse["bx"],
            reverse["by"],
            reverse["bz"],
        )
        assert (forward["bx"], forward["by"], forward["bz"]) == (
            reverse["ax"],
            reverse["ay"],
            reverse["az"],
        )
        assert forward["ay"] == forward["by"] == reverse["ay"] == reverse["by"] == 0
        for read in (forward, reverse):
            assert read["options"] == {"ignorewalls": False, "ignorecreep": True}
        if (forward["bx"] - forward["ax"], forward["bz"] - forward["az"]) not in {
            (4, 0),
            (0, 4),
        }:
            # Only the player-to-center pair may differ from tile adjacency.
            assert (forward["ax"], forward["az"], forward["bx"], forward["bz"]) == (
                0, 0, -1, 1
            )
            continue
        pair = ((forward["ax"], forward["az"]), (forward["bx"], forward["bz"]))
        assert pair not in checked_pairs
        checked_pairs.add(pair)
        for read in (forward, reverse):
            start = by_position[(read["ax"], read["az"])]
            end = by_position[(read["bx"], read["bz"])]
            assert start["passable"] is True
            assert end["passable"] is True

    target_pair_reads = [
        read
        for read in reads
        if {(read["ax"], read["az"]), (read["bx"], read["bz"])}
        == {(-1, 1), (3, 1)}
    ]
    assert len(target_pair_reads) == 2
    assert (target_pair_reads[0]["ax"], target_pair_reads[0]["az"]) == (-1, 1)
    assert (target_pair_reads[0]["bx"], target_pair_reads[0]["bz"]) == (3, 1)
    assert (target_pair_reads[1]["ax"], target_pair_reads[1]["az"]) == (3, 1)
    assert (target_pair_reads[1]["bx"], target_pair_reads[1]["bz"]) == (-1, 1)

    # Cells that were not sampled, including hidden, outside-radius, and
    # non-passable cells, cannot be Pathfinder endpoints.
    assert not any(read["ax"] == 7 or read["bx"] == 7 for read in reads)
    validate_snapshot(snapshot)


@pytest.mark.skipif(LuaRuntime is None, reason="install the development-only Lupa dependency")
def test_terrain_connections_are_omitted_without_pathfinder_api() -> None:
    from dst_route_planner.live import validate_snapshot

    runtime = _make_stub(visibility_mode="point", has_pathfinder_api=False)
    runtime["sim_callbacks"][0](runtime["world"])
    runtime["world"]["callback"]()
    snapshot = _snapshot(runtime["lines"])

    assert all("connections" not in tile for tile in snapshot["terrain"]["tiles"])
    assert "player_anchor" not in snapshot
    assert _from_lua(runtime["world"]["pathfinder_reads"]) == []
    validate_snapshot(snapshot)


@pytest.mark.skipif(LuaRuntime is None, reason="install the development-only Lupa dependency")
@pytest.mark.parametrize(
    "pathfinder_mode",
    ["error", "nil", "nonboolean", "forward_nil", "reverse_nil"],
)
def test_terrain_connections_keep_unknown_when_pathfinder_fails_or_returns_nonboolean(
    pathfinder_mode: str,
) -> None:
    from dst_route_planner.live import validate_snapshot

    runtime = _make_stub(visibility_mode="point", pathfinder_mode=pathfinder_mode)
    runtime["sim_callbacks"][0](runtime["world"])
    runtime["world"]["callback"]()
    snapshot = _snapshot(runtime["lines"])

    assert all("connections" not in tile for tile in snapshot["terrain"]["tiles"])
    assert "player_anchor" not in snapshot
    reads = _from_lua(runtime["world"]["pathfinder_reads"])
    assert reads and len(reads) % 2 == 0
    validate_snapshot(snapshot)


@pytest.mark.skipif(LuaRuntime is None, reason="install the development-only Lupa dependency")
def test_stub_waits_for_player_and_resets_session_for_player_and_world_changes() -> None:
    runtime = _make_stub(player_present=False)
    lua = runtime["lua"]
    runtime["sim_callbacks"][0](runtime["world"])
    runtime["world"]["callback"]()
    assert runtime["lines"] == []

    runtime["g"]["ThePlayer"] = lua.globals().make_player(0, 0, 0, "point")
    runtime["world"]["callback"]()
    first = _snapshot(runtime["lines"])
    runtime["world"]["callback"]()
    second = _snapshot(runtime["lines"])
    assert first["sequence"] == 1
    assert second["sequence"] == 2
    assert first["session_id"] == second["session_id"]

    runtime["g"]["ThePlayer"] = lua.globals().make_player(1, 0, 0, "point")
    runtime["world"]["callback"]()
    replaced_player = _snapshot(runtime["lines"])
    assert replaced_player["sequence"] == 1
    assert replaced_player["session_id"] != first["session_id"]

    new_world = lua.globals().make_world("cave-session-2", "cave")
    runtime["g"]["TheWorld"] = new_world
    runtime["sim_callbacks"][0](new_world)
    new_world["callback"]()
    replaced_world = _snapshot(runtime["lines"])
    assert replaced_world["world_id"] == "cave-session-2"
    assert replaced_world["world_kind"] == "cave"
    assert replaced_world["sequence"] == 1
    assert replaced_world["session_id"] != replaced_player["session_id"]


@pytest.mark.skipif(LuaRuntime is None, reason="install the development-only Lupa dependency")
def test_stub_falls_back_to_map_explorer_revealed_tiles_and_skips_dedicated_servers() -> None:
    runtime = _make_stub()
    runtime["g"]["ThePlayer"] = runtime["lua"].globals().make_player(0, 0, 0, "explorer")
    runtime["sim_callbacks"][0](runtime["world"])
    runtime["world"]["callback"]()
    snapshot = _snapshot(runtime["lines"])
    tile_types = {
        tile
        for observation in [snapshot["current"], *snapshot["directions"].values()]
        for tile in observation.get("tile_types", [])
    }
    assert "SECRET" not in tile_types
    assert snapshot["terrain"]["tiles"]
    assert all(
        round((tile["x"] - 103) / 4) >= -26
        for tile in snapshot["terrain"]["tiles"]
    )
    assert all(tile["tile"] != "SECRET" for tile in snapshot["terrain"]["tiles"])

    dedicated = _make_stub(dedicated=True)
    dedicated["sim_callbacks"][0](dedicated["world"])
    assert dedicated["world"]["callback"] is None
    assert dedicated["lines"] == []


@pytest.mark.skipif(LuaRuntime is None, reason="install the development-only Lupa dependency")
def test_empty_observations_and_quoted_identity_are_valid_external_json() -> None:
    from dst_route_planner.live import validate_snapshot

    runtime = _make_stub()
    lua = runtime["lua"]
    runtime["g"]["ThePlayer"]["CanSeePointOnMiniMap"] = lua.eval("function() return false end")
    runtime["world"]["meta"]["session_identifier"] = "world's quoted identity"
    runtime["sim_callbacks"][0](runtime["world"])
    runtime["world"]["callback"]()
    result = _snapshot(runtime["lines"])
    assert result["world_id"] == "world's quoted identity"
    assert result["current"] == {"note": ""}
    assert all(value == {"note": ""} for value in result["directions"].values())
    assert "terrain" not in result
    validate_snapshot(result)
