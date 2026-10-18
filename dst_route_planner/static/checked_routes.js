(function (root, factory) {
  "use strict";

  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  if (root) {
    root.CheckedRoutes = api;
  }
})(typeof globalThis === "undefined" ? this : globalThis, function () {
  "use strict";

  const DIRECTIONS = [
    {name: "east", dx: 4, dz: 0},
    {name: "north", dx: 0, dz: 4},
  ];
  const DIRECTION_ORDER = {east: 0, north: 1, west: 2, south: 3};

  function isRecord(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function isFinitePoint(value) {
    return isRecord(value) && Number.isFinite(value.x) && Number.isFinite(value.z);
  }

  function coordinateKey(x, z) {
    return String(x) + "," + String(z);
  }

  function cellInterval(center) {
    const lower = center - 2;
    const upper = center + 2;
    if (!Number.isFinite(lower) || !Number.isFinite(upper) ||
        lower >= center || upper <= center || upper - lower !== 4) {
      return null;
    }
    return [lower, upper];
  }

  function couldBeInImpreciseCell(position, x, z) {
    return Math.abs(position.x - x) <= 2 && Math.abs(position.z - z) <= 2;
  }

  function buildTileEntries(tiles) {
    const entries = [];
    const counts = new Map();
    if (Array.isArray(tiles)) {
      for (const tile of tiles) {
        if (!isRecord(tile) || !Number.isFinite(tile.x) || !Number.isFinite(tile.z)) {
          continue;
        }
        const key = coordinateKey(tile.x, tile.z);
        entries.push({x: tile.x, z: tile.z, key, tile});
        counts.set(key, (counts.get(key) || 0) + 1);
      }
    }
    return {entries, counts};
  }

  function locateContainingEntry(entries, position) {
    if (!isFinitePoint(position)) return null;
    let match = null;
    let matchCount = 0;
    let impreciseMatch = false;
    for (const entry of entries) {
      const xInterval = cellInterval(entry.x);
      const zInterval = cellInterval(entry.z);
      if (!xInterval || !zInterval) {
        if (couldBeInImpreciseCell(position, entry.x, entry.z)) {
          impreciseMatch = true;
        }
        continue;
      }
      if (position.x >= xInterval[0] && position.x < xInterval[1] &&
          position.z >= zInterval[0] && position.z < zInterval[1]) {
        match = entry;
        matchCount += 1;
      }
    }
    return impreciseMatch || matchCount !== 1 ? null : match;
  }

  function point(x, z) {
    return {x, z};
  }

  function makeResult(status, start, goal, path, next) {
    const hasPath = path.length > 0;
    const steps = hasPath ? path.length - 1 : 0;
    return {
      status,
      start: start ? point(start.x, start.z) : null,
      goal: goal ? point(goal.x, goal.z) : null,
      path,
      distance: steps * 4,
      steps,
      next: next || null,
    };
  }

  function movementDirection(from, to) {
    if (to.z === from.z) {
      if (to.x === from.x + 4) return "east";
      if (from.x === to.x + 4) return "west";
    }
    if (to.x === from.x) {
      if (to.z === from.z + 4) return "north";
      if (from.z === to.z + 4) return "south";
    }
    return null;
  }

  function findGridRoute(tiles, position, destination) {
    const goalInput = isFinitePoint(destination) ? point(destination.x, destination.z) : null;
    if (!goalInput) {
      return makeResult("no_destination", null, null, [], null);
    }
    if (!isFinitePoint(position)) {
      return makeResult("no_position", null, goalInput, [], null);
    }

    const {entries, counts} = buildTileEntries(tiles);
    const startEntry = locateContainingEntry(entries, position);
    if (!startEntry) {
      return makeResult("start_unknown", null, goalInput, [], null);
    }

    const start = point(startEntry.x, startEntry.z);
    if (startEntry.tile.passable === false) {
      return makeResult("start_blocked", start, goalInput, [], null);
    }
    if (startEntry.tile.passable !== true || counts.get(startEntry.key) !== 1) {
      return makeResult("start_unknown", start, goalInput, [], null);
    }

    const goalCount = counts.get(coordinateKey(goalInput.x, goalInput.z)) || 0;
    if (goalCount !== 1) {
      return makeResult("goal_unknown", start, goalInput, [], null);
    }
    const goalEntry = entries.find(
      entry => entry.x === goalInput.x && entry.z === goalInput.z
    );
    if (!goalEntry || goalEntry.tile.passable !== true) {
      return makeResult(
        goalEntry && goalEntry.tile.passable === false ? "goal_blocked" : "goal_unknown",
        start,
        goalInput,
        [],
        null
      );
    }
    const goal = point(goalEntry.x, goalEntry.z);
    if (startEntry.key === goalEntry.key) {
      return makeResult("arrived", start, goal, [point(start.x, start.z)], null);
    }

    const uniqueEntries = entries.filter(entry => counts.get(entry.key) === 1);
    const entryByCoordinate = new Map(uniqueEntries.map(entry => [entry.key, entry]));
    const graph = new Map();
    for (const entry of uniqueEntries) {
      if (entry.tile.passable === true) {
        graph.set(entry.key, new Set());
      }
    }
    for (const entry of uniqueEntries) {
      if (!graph.has(entry.key)) continue;
      const connections = entry.tile.connections;
      if (!isRecord(connections)) continue;
      for (const direction of DIRECTIONS) {
        if (connections[direction.name] !== true) continue;
        const neighborX = entry.x + direction.dx;
        const neighborZ = entry.z + direction.dz;
        if (!Number.isFinite(neighborX) || !Number.isFinite(neighborZ) ||
            (neighborX === entry.x && neighborZ === entry.z)) {
          continue;
        }
        const neighborKey = coordinateKey(neighborX, neighborZ);
        const neighbor = entryByCoordinate.get(neighborKey);
        if (!neighbor || neighbor.tile.passable !== true || !graph.has(neighborKey)) {
          continue;
        }
        graph.get(entry.key).add(neighborKey);
        graph.get(neighborKey).add(entry.key);
      }
    }

    for (const [key, neighbors] of graph) {
      const from = entryByCoordinate.get(key);
      const sorted = Array.from(neighbors);
      sorted.sort((leftKey, rightKey) => {
        const left = entryByCoordinate.get(leftKey);
        const right = entryByCoordinate.get(rightKey);
        return DIRECTION_ORDER[movementDirection(from, left)] -
          DIRECTION_ORDER[movementDirection(from, right)];
      });
      graph.set(key, sorted);
    }

    const parent = new Map([[startEntry.key, null]]);
    const queue = [startEntry.key];
    let head = 0;
    while (head < queue.length && !parent.has(goalEntry.key)) {
      const currentKey = queue[head++];
      for (const neighborKey of graph.get(currentKey) || []) {
        if (parent.has(neighborKey)) continue;
        parent.set(neighborKey, currentKey);
        queue.push(neighborKey);
      }
    }
    if (!parent.has(goalEntry.key)) {
      return makeResult("unreachable", start, goal, [], null);
    }

    const reversePath = [];
    let currentKey = goalEntry.key;
    while (currentKey !== null) {
      const entry = entryByCoordinate.get(currentKey);
      reversePath.push(point(entry.x, entry.z));
      currentKey = parent.get(currentKey);
    }
    const path = reversePath.reverse();
    const direction = movementDirection(path[0], path[1]);
    return makeResult(
      "found",
      start,
      goal,
      path,
      direction ? {x: path[1].x, z: path[1].z, direction} : null
    );
  }

  function locatePassableTile(tiles, targetPoint) {
    if (!isFinitePoint(targetPoint)) return {status: "unknown", tile: null};
    const {entries, counts} = buildTileEntries(tiles);
    const entry = locateContainingEntry(entries, targetPoint);
    if (!entry || counts.get(entry.key) !== 1) {
      return {status: "unknown", tile: null};
    }
    const center = point(entry.x, entry.z);
    if (entry.tile.passable === false) return {status: "blocked", tile: center};
    if (entry.tile.passable !== true) return {status: "unknown", tile: null};
    return {status: "found", tile: center};
  }

  function isPlayerAnchor(value) {
    if (!isRecord(value) || !Number.isFinite(value.x) || !Number.isFinite(value.z) ||
        typeof value.clear !== "boolean") return false;
    const keys = Object.keys(value);
    return keys.length === 3 && keys.includes("x") && keys.includes("z") && keys.includes("clear");
  }

  function samePoint(left, right) {
    return !!left && !!right && left.x === right.x && left.z === right.z;
  }

  function anchorBearing(from, to) {
    const dx = to.x - from.x;
    const dz = to.z - from.z;
    const directions = ["north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest"];
    const octant = Math.round(Math.atan2(dx, dz) / (Math.PI / 4));
    return directions[(octant + directions.length) % directions.length];
  }

  function anchorFailure(status, position, destination, gridStart = null, anchorDistance = null) {
    const goal = isFinitePoint(destination) ? point(destination.x, destination.z) : null;
    const result = makeResult(status, isFinitePoint(position) ? position : null, goal, [], null);
    result.origin = "player";
    if (gridStart) result.grid_start = point(gridStart.x, gridStart.z);
    if (Number.isFinite(anchorDistance)) result.anchor_distance = anchorDistance;
    return result;
  }

  function findRoute(tiles, position, destination, playerAnchor) {
    if (playerAnchor === undefined) return findGridRoute(tiles, position, destination);

    const goalInput = isFinitePoint(destination) ? point(destination.x, destination.z) : null;
    if (!goalInput) return makeResult("no_destination", null, null, [], null);
    if (!isFinitePoint(position)) return makeResult("no_position", null, goalInput, [], null);
    if (!isPlayerAnchor(playerAnchor)) {
      return anchorFailure("anchor_unknown", position, destination);
    }

    const actualPosition = point(position.x, position.z);
    const center = point(playerAnchor.x, playerAnchor.z);
    const anchorDistance = Math.hypot(actualPosition.x - center.x, actualPosition.z - center.z);
    if (!Number.isFinite(anchorDistance)) {
      return anchorFailure("anchor_unknown", position, destination);
    }

    // An arrived result means the actual position and the supplied center resolve to
    // the same unique, reliable, currently passable tile under the half-open bounds.
    const anchorCell = findGridRoute(tiles, actualPosition, center);
    if (anchorCell.status !== "arrived" || !samePoint(anchorCell.start, center)) {
      return anchorFailure("anchor_unknown", actualPosition, destination);
    }
    if (!playerAnchor.clear) {
      return anchorFailure("anchor_blocked", actualPosition, destination, center, anchorDistance);
    }

    const gridRoute = findGridRoute(tiles, center, destination);
    const gridDistance = gridRoute.distance;
    const successful = gridRoute.status === "found" || gridRoute.status === "arrived";
    const positionAtCenter = samePoint(actualPosition, center);
    const status = gridRoute.status === "arrived" && !positionAtCenter ? "found" : gridRoute.status;
    let path = [];
    if (successful) {
      path = gridRoute.path.map(item => point(item.x, item.z));
      if (!positionAtCenter) path.unshift(actualPosition);
    }
    const distance = successful ? anchorDistance + gridDistance : 0;
    if (!Number.isFinite(distance)) {
      return anchorFailure("anchor_unknown", actualPosition, destination);
    }

    let next = gridRoute.next;
    if (successful && !positionAtCenter) {
      next = {kind: "anchor", direction: anchorBearing(actualPosition, center), x: center.x, z: center.z};
    }
    return {
      status,
      start: actualPosition,
      goal: gridRoute.goal,
      path,
      distance,
      steps: gridRoute.steps,
      next: next || null,
      origin: "player",
      grid_start: center,
      anchor_distance: anchorDistance,
      grid_distance: gridDistance,
    };
  }

  return {findRoute, locatePassableTile};
});
