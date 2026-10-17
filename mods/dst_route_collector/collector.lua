local G = GLOBAL

local SAMPLE_RADIUS = 16
local CURRENT_RADIUS = 4
local TILE_SIZE = 4
local MAX_TERRAIN_TILES = 256
local SAMPLE_STEP = 4
local SAMPLE_RADIUS_SQ = SAMPLE_RADIUS * SAMPLE_RADIUS
local CURRENT_RADIUS_SQ = CURRENT_RADIUS * CURRENT_RADIUS
local CARDINAL_SLOPE = 0.41421356237309503
local COLLECTOR_EPOCH = tostring(G.os.time())
local session_generation = 0

local DIRECTION_NAMES = {
    "north",
    "northeast",
    "east",
    "southeast",
    "south",
    "southwest",
    "west",
    "northwest",
}

local EXCLUDED_TAGS = {
    "FX",
    "DECOR",
    "INLIMBO",
    "player",
    "playerghost",
    "CLASSIFIED",
    "NOCLICK",
}

local LANDMARK_PREFABS = {
    antlion_spawner = true,
    beequeenhive = true,
    cave_entrance = true,
    dragonfly_spawner = true,
    lightninggoat = true,
    mandrake_planted = true,
    mermhouse = true,
    molehill = true,
    moonbase = true,
    moose_nesting_ground = true,
    oasislake = true,
    panflute = true,
    pigking = true,
    resurrectionstone = true,
    spiderden = true,
    statueglommer = true,
    tentacle = true,
    walrus_camp = true,
    wasphive = true,
    wormhole = true,
}

local function make_tile_names()
    local names = {}
    for name, tile in pairs(G.WORLD_TILES or {}) do
        if type(name) == "string" and type(tile) == "number" then
            names[tile] = name
        end
    end
    for name, tile in pairs(G.GROUND or {}) do
        if type(name) == "string" and type(tile) == "number" and names[tile] == nil then
            names[tile] = name
        end
    end
    return names
end

local TILE_NAMES = make_tile_names()

local function valid_entity(inst)
    return inst ~= nil and (inst.IsValid == nil or inst:IsValid())
end

local function is_dedicated()
    local net = G.TheNet
    return net ~= nil and net.IsDedicated ~= nil and net:IsDedicated()
end

local function can_see_point(player, map, x, z)
    if player.CanSeePointOnMiniMap ~= nil then
        return player:CanSeePointOnMiniMap(x, 0, z) == true
    end

    local classified = player.player_classified
    local explorer = classified ~= nil and classified.MapExplorer or nil
    if explorer == nil or explorer.IsTileSeeable == nil then
        return false
    end

    local tx, ty = map:GetTileXYAtPoint(x, 0, z)
    return explorer:IsTileSeeable(tx, ty) == true
end

local function tile_name(map, x, z)
    local tile = map:GetTileAtPoint(x, 0, z)
    return TILE_NAMES[tile]
end

local function visible_tile_center(player, map, tx, ty)
    if player.CanSeeTileOnMiniMap ~= nil then
        if player:CanSeeTileOnMiniMap(tx, ty) ~= true then
            return nil
        end
        local center_x, _, center_z = map:GetTileCenterPoint(tx, ty)
        if type(center_x) == "number" and type(center_z) == "number" then
            return center_x, center_z
        end
        return nil
    end

    local center_x, _, center_z = map:GetTileCenterPoint(tx, ty)
    if type(center_x) == "number" and type(center_z) == "number"
        and can_see_point(player, map, center_x, center_z) then
        return center_x, center_z
    end
    return nil
end

local function add_terrain_connections(world, tiles)
    local pathfinder = world.Pathfinder
    if pathfinder == nil or pathfinder.IsClear == nil then
        return
    end

    local tiles_by_x = {}
    for _, tile in ipairs(tiles) do
        local column = tiles_by_x[tile.x]
        if column == nil then
            column = {}
            tiles_by_x[tile.x] = column
        end
        column[tile.z] = tile
    end

    local function check_connection(first, second)
        if first.passable ~= true or second.passable ~= true then
            return nil
        end

        local options = { ignorewalls = false, ignorecreep = true }
        local forward_ok, forward = pcall(
            pathfinder.IsClear,
            pathfinder,
            first.x,
            0,
            first.z,
            second.x,
            0,
            second.z,
            options
        )
        local backward_ok, backward = pcall(
            pathfinder.IsClear,
            pathfinder,
            second.x,
            0,
            second.z,
            first.x,
            0,
            first.z,
            options
        )
        if forward_ok and backward_ok
            and type(forward) == "boolean" and type(backward) == "boolean" then
            return forward and backward
        end
        return nil
    end

    for _, tile in ipairs(tiles) do
        local connections = {}
        local east_column = tiles_by_x[tile.x + TILE_SIZE]
        local east = east_column ~= nil and east_column[tile.z] or nil
        if east ~= nil then
            local clear = check_connection(tile, east)
            if clear ~= nil then
                connections.east = clear
            end
        end

        local north_column = tiles_by_x[tile.x]
        local north = north_column ~= nil and north_column[tile.z + TILE_SIZE] or nil
        if north ~= nil then
            local clear = check_connection(tile, north)
            if clear ~= nil then
                connections.north = clear
            end
        end

        if next(connections) ~= nil then
            tile.connections = connections
        end
    end
end

local function sample_terrain(world, player, map, x, z)
    if map.GetTileCenterPoint == nil then
        return nil
    end

    local player_tx, player_ty = map:GetTileXYAtPoint(x, 0, z)
    if type(player_tx) ~= "number" or type(player_ty) ~= "number" then
        return nil
    end

    local tiles = {}
    local invalid_tile = G.WORLD_TILES ~= nil and G.WORLD_TILES.INVALID or nil
    for offset_x = -SAMPLE_RADIUS / TILE_SIZE, SAMPLE_RADIUS / TILE_SIZE do
        for offset_y = -SAMPLE_RADIUS / TILE_SIZE, SAMPLE_RADIUS / TILE_SIZE do
            local tx = player_tx + offset_x
            local ty = player_ty + offset_y
            local center_x, center_z = visible_tile_center(player, map, tx, ty)
            if center_x ~= nil and center_z ~= nil then
                local dx = center_x - x
                local dz = center_z - z
                if dx * dx + dz * dz <= SAMPLE_RADIUS_SQ then
                    local tile = map:GetTileAtPoint(center_x, 0, center_z)
                    local name = TILE_NAMES[tile]
                    if name ~= nil and name ~= "INVALID" and tile ~= invalid_tile
                        and #tiles < MAX_TERRAIN_TILES then
                        local sampled_tile = { x = center_x, z = center_z, tile = name }
                        if map.IsPassableAtPoint ~= nil then
                            local ok, passable = pcall(
                                map.IsPassableAtPoint,
                                map,
                                center_x,
                                0,
                                center_z,
                                false,
                                true
                            )
                            if ok and type(passable) == "boolean" then
                                sampled_tile.passable = passable
                            end
                        end
                        table.insert(tiles, sampled_tile)
                    end
                end
            end
        end
    end

    if #tiles == 0 then
        return nil
    end
    table.sort(tiles, function(left, right)
        if left.x ~= right.x then
            return left.x < right.x
        end
        return left.z < right.z
    end)
    add_terrain_connections(world, tiles)
    return { tile_size = TILE_SIZE, tiles = tiles }
end

local function direction_for_offset(dx, dz)
    local abs_x = math.abs(dx)
    local abs_z = math.abs(dz)
    if abs_x <= abs_z * CARDINAL_SLOPE then
        return dz >= 0 and "north" or "south"
    elseif abs_z <= abs_x * CARDINAL_SLOPE then
        return dx >= 0 and "east" or "west"
    elseif dz >= 0 then
        return dx >= 0 and "northeast" or "northwest"
    else
        return dx >= 0 and "southeast" or "southwest"
    end
end

local function new_observation()
    return {
        tile_types = {},
        tile_set = {},
        prefab_counts = {},
    }
end

local function add_tile(observation, name)
    if name ~= nil and not observation.tile_set[name] then
        observation.tile_set[name] = true
        table.insert(observation.tile_types, name)
    end
end

local function finalize_observation(observation)
    table.sort(observation.tile_types)
    if next(observation.tile_types) == nil then
        observation.tile_types = nil
    end
    if next(observation.prefab_counts) == nil then
        observation.prefab_counts = nil
    end
    observation.tile_set = nil
    observation.note = "" -- Keep an empty observation a JSON object.
    return observation
end

local function add_prefab(observation, prefab)
    local counts = observation.prefab_counts
    counts[prefab] = (counts[prefab] or 0) + 1
end

local function has_excluded_tag(inst)
    if inst.HasTag == nil then
        return false
    end
    for _, tag in ipairs(EXCLUDED_TAGS) do
        if inst:HasTag(tag) then
            return true
        end
    end
    return false
end

local function entity_is_observable(player, map, inst)
    if not valid_entity(inst) or inst.prefab == nil or has_excluded_tag(inst) then
        return false
    end

    local visual = inst.entity
    if visual == nil or visual.IsVisible == nil or not visual:IsVisible() then
        return false
    end

    if inst.Transform == nil or inst.Transform.GetWorldPosition == nil then
        return false
    end
    local x, _, z = inst.Transform:GetWorldPosition()
    return can_see_point(player, map, x, z)
end

local function sorted_landmarks(landmarks)
    if #landmarks == 0 then
        return nil
    end
    table.sort(landmarks, function(left, right)
        if left.prefab ~= right.prefab then
            return left.prefab < right.prefab
        elseif left.x ~= right.x then
            return left.x < right.x
        end
        return left.z < right.z
    end)
    return landmarks
end

local function sample(world, player, sequence, world_id, session_id)
    local map = world.Map
    if map == nil or map.GetTileAtPoint == nil or map.GetTileXYAtPoint == nil then
        return nil
    end

    local x, y, z = player.Transform:GetWorldPosition()
    local current = new_observation()
    local direction_observations = {}
    for _, name in ipairs(DIRECTION_NAMES) do
        direction_observations[name] = new_observation()
    end

    for dx = -SAMPLE_RADIUS, SAMPLE_RADIUS, SAMPLE_STEP do
        for dz = -SAMPLE_RADIUS, SAMPLE_RADIUS, SAMPLE_STEP do
            local distance_sq = dx * dx + dz * dz
            if distance_sq <= SAMPLE_RADIUS_SQ then
                local point_x = x + dx
                local point_z = z + dz
                if can_see_point(player, map, point_x, point_z) then
                    local name = tile_name(map, point_x, point_z)
                    local observation = distance_sq <= CURRENT_RADIUS_SQ
                        and current
                        or direction_observations[direction_for_offset(dx, dz)]
                    add_tile(observation, name)
                end
            end
        end
    end

    local landmarks = {}
    local entities = G.TheSim:FindEntities(x, 0, z, SAMPLE_RADIUS)
    for _, inst in ipairs(entities) do
        if entity_is_observable(player, map, inst) then
            local entity_x, _, entity_z = inst.Transform:GetWorldPosition()
            local dx = entity_x - x
            local dz = entity_z - z
            local distance_sq = dx * dx + dz * dz
            if distance_sq <= SAMPLE_RADIUS_SQ then
                local prefab = inst.prefab
                local observation = distance_sq <= CURRENT_RADIUS_SQ
                    and current
                    or direction_observations[direction_for_offset(dx, dz)]
                add_prefab(observation, prefab)

                if LANDMARK_PREFABS[prefab] then
                    table.insert(landmarks, { prefab = prefab, x = entity_x, z = entity_z })
                end
            end
        end
    end

    for name, observation in pairs(direction_observations) do
        direction_observations[name] = finalize_observation(observation)
    end

    local heading = 0
    if G.TheCamera ~= nil and G.TheCamera.GetHeading ~= nil then
        heading = G.TheCamera:GetHeading() or 0
    end

    local snapshot = {
        live_version = 1,
        world_id = world_id,
        world_kind = world.worldprefab == "forest" and "forest"
            or world.worldprefab == "cave" and "cave"
            or "other",
        session_id = session_id,
        sequence = sequence,
        captured_at = G.os.time(),
        position = { x = x, y = y, z = z },
        camera_heading = heading,
        current = finalize_observation(current),
        directions = direction_observations,
    }

    local terrain = sample_terrain(world, player, map, x, z)
    if terrain ~= nil then
        snapshot.terrain = terrain
    end

    local nonempty_landmarks = sorted_landmarks(landmarks)
    if nonempty_landmarks ~= nil then
        snapshot.landmarks = nonempty_landmarks
    end
    return snapshot
end

local function world_identifier(world)
    local meta = world.meta or {}
    local identifier = meta.session_identifier or meta.worldGUID or world.worldGUID or world.GUID
    if identifier == nil then
        identifier = "world-" .. tostring(G.os.time())
    end
    return tostring(identifier)
end

local function attach_world_task(world)
    if world == nil or world.DoPeriodicTask == nil or is_dedicated() then
        return
    end

    local active_world = nil
    local active_player = nil
    local active_session_id = nil
    local sequence = 0

    world:DoPeriodicTask(1, function()
        if G.TheWorld ~= world then
            active_world = nil
            active_player = nil
            active_session_id = nil
            sequence = 0
            return
        end

        local player = G.ThePlayer
        if not valid_entity(player) or player.Transform == nil then
            active_player = nil
            active_session_id = nil
            sequence = 0
            return
        end

        if active_world ~= world or active_player ~= player or active_session_id == nil then
            active_world = world
            active_player = player
            session_generation = session_generation + 1
            active_session_id = COLLECTOR_EPOCH .. "-" .. tostring(session_generation)
            sequence = 0
        end

        local next_sequence = sequence + 1
        local snapshot = sample(world, player, next_sequence, world_identifier(world), active_session_id)
        if snapshot ~= nil then
            sequence = next_sequence
            print("DST_ROUTE_PLANNER_LIVE_V1 " .. G.json.encode_compliant(snapshot))
        end
    end)
end

AddSimPostInit(function(world)
    attach_world_task(world or G.TheWorld)
end)
