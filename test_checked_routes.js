const assert = require("node:assert/strict");
const {findRoute} = require("./dst_route_planner/static/checked_routes.js");

function cell(x, z, passable = true, connections) {
  return {
    x, z, tile: "GRASS", last_sequence: 1, passable,
    ...(connections === undefined ? {} : {connections})
  };
}
function route(tiles, position, destination, playerAnchor) {
  return findRoute(tiles, position, destination, playerAnchor);
}

assert.equal(route([], {x: 0, z: 0}, null).status, "no_destination");
assert.equal(route([], null, {x: 0, z: 0}).status, "no_position");
assert.equal(route([], {x: 0, z: 0}, {x: Infinity, z: 0}).status, "no_destination");
assert.equal(route([], {x: NaN, z: 0}, {x: 0, z: 0}).status, "no_position");

const straight = [
  cell(0, 0, true, {east: true}),
  cell(4, 0)
];
assert.deepEqual(route(straight, {x: 1.5, z: -1}, {x: 4, z: 0}), {
  status: "found",
  start: {x: 0, z: 0},
  goal: {x: 4, z: 0},
  path: [{x: 0, z: 0}, {x: 4, z: 0}],
  distance: 4,
  steps: 1,
  next: {x: 4, z: 0, direction: "east"}
});
assert.deepEqual(route(straight, {x: 0, z: 0}, {x: 0, z: 0}), {
  status: "arrived",
  start: {x: 0, z: 0},
  goal: {x: 0, z: 0},
  path: [{x: 0, z: 0}],
  distance: 0,
  steps: 0,
  next: null
});

assert.equal(route([{x: 0, z: 0, tile: "GRASS"}], {x: 0, z: 0}, {x: 0, z: 0}).status, "start_unknown");
assert.equal(route([cell(0, 0, false)], {x: 0, z: 0}, {x: 0, z: 0}).status, "start_blocked");
assert.equal(route([cell(0, 0)], {x: 0, z: 0}, {x: 4, z: 0}).status, "goal_unknown");
assert.equal(route([cell(0, 0), cell(4, 0, false)], {x: 0, z: 0}, {x: 4, z: 0}).status, "goal_blocked");
assert.equal(route([cell(0, 0)], {x: 0, z: 0}, {x: 4, z: 0}).goal.x, 4);

assert.equal(route([cell(0, 0), cell(4, 0)], {x: 0, z: 0}, {x: 4, z: 0}).status, "unreachable",
  "missing edge data stays unknown");
assert.equal(route([cell(0, 0, true, {east: false}), cell(4, 0)], {x: 0, z: 0}, {x: 4, z: 0}).status,
  "unreachable", "false edges stay blocked");
assert.equal(route([cell(0, 0, true, {east: true}), cell(4, 0, false)], {x: 0, z: 0}, {x: 4, z: 0}).status,
  "goal_blocked", "a walkable owner cannot connect through a blocked neighbor");
assert.equal(route([cell(0, 0, true, {east: true})], {x: 0, z: 0}, {x: 4, z: 0}).status,
  "goal_unknown", "an absent endpoint is not inferred");

const reverse = route([cell(0, 0, true, {east: true}), cell(4, 0)], {x: 4, z: 0}, {x: 0, z: 0});
assert.equal(reverse.status, "found");
assert.deepEqual(reverse.path, [{x: 4, z: 0}, {x: 0, z: 0}]);
assert.deepEqual(reverse.next, {x: 0, z: 0, direction: "west"});

const north = route([cell(0, -4, true, {north: true}), cell(0, 0)], {x: 0, z: 0}, {x: 0, z: -4});
assert.equal(north.status, "found");
assert.deepEqual(north.next, {x: 0, z: -4, direction: "south"});

const detour = [
  cell(0, 0, true, {east: false, north: true}),
  cell(4, 0, true, {east: true, north: true}),
  cell(8, 0),
  cell(0, 4, true, {east: true}),
  cell(4, 4, true, {east: false})
];
const detourResult = route(detour, {x: 0, z: 0}, {x: 8, z: 0});
assert.equal(detourResult.status, "found");
assert.equal(detourResult.steps, 4);
assert.equal(detourResult.distance, 16);
assert.deepEqual(detourResult.path, [
  {x: 0, z: 0}, {x: 0, z: 4}, {x: 4, z: 4}, {x: 4, z: 0}, {x: 8, z: 0}
]);

const disconnected = [
  cell(0, 0, true, {east: true}),
  cell(4, 0),
  cell(100, 100)
];
assert.equal(route(disconnected, {x: 0, z: 0}, {x: 100, z: 100}).status, "unreachable");

const boundaryTiles = [
  cell(-4, 0),
  cell(0, 0),
  cell(4, 0)
];
assert.deepEqual(route(boundaryTiles, {x: -2, z: 0}, {x: 4, z: 0}).start, {x: 0, z: 0},
  "a shared lower boundary belongs to the cell centered at zero");
assert.deepEqual(route(boundaryTiles, {x: 2, z: 0}, {x: 4, z: 0}).start, {x: 4, z: 0},
  "a shared upper boundary belongs to the next cell");
assert.equal(route([cell(0, 0)], {x: 2, z: 0}, {x: 0, z: 0}).status, "start_unknown",
  "the planner does not snap an uncovered boundary to the nearest cell");
assert.equal(route([cell(0, 0)], {x: 2.001, z: 0}, {x: 0, z: 0}).status, "start_unknown");

assert.equal(route([cell(0, 0), cell(2, 0)], {x: 1, z: 0}, {x: 0, z: 0}).status,
  "start_unknown", "overlapping half-open tile bounds are ambiguous");
assert.equal(route([cell(1e100, 0)], {x: 1e100, z: 0}, {x: 1e100, z: 0}).status,
  "start_unknown", "tile bounds that overflow coordinate precision stay unknown");
assert.equal(route([cell(Number.MAX_VALUE, 0, true, {east: true})],
  {x: Number.MAX_VALUE, z: 0}, {x: Number.MAX_VALUE, z: 0}).status, "start_unknown");
assert.equal(route([cell(0, 0), cell(0, 0)], {x: 0, z: 0}, {x: 0, z: 0}).status,
  "start_unknown", "duplicate centers make start selection ambiguous");

const changing = [cell(0, 0, true, {east: true}), cell(4, 0)];
assert.equal(route(changing, {x: 0, z: 0}, {x: 4, z: 0}).status, "found");
changing[0] = cell(0, 0, true, {east: false});
assert.equal(route(changing, {x: 0, z: 0}, {x: 4, z: 0}).status, "unreachable",
  "each call rebuilds edges from the current tile snapshot");

const largeMap = Array.from({length: 2500}, (_, index) =>
  cell(index * 4, 0, true, index === 2499 ? {} : {east: true}));
const started = Date.now();
const largeRoute = route(largeMap, {x: 0, z: 0}, {x: 9996, z: 0});
const elapsed = Date.now() - started;
assert.equal(largeRoute.status, "found");
assert.equal(largeRoute.steps, 2499);
assert.equal(largeRoute.distance, 9996);
assert.equal(largeRoute.path.length, 2500);
assert.ok(elapsed < 5000, "2500 terrain cells should route interactively");

const anchored = route(straight, {x: 1, z: 1}, {x: 4, z: 0}, {x: 0, z: 0, clear: true});
assert.equal(anchored.status, "found");
assert.deepEqual(anchored.start, {x: 1, z: 1}, "player-origin routes retain the actual player position");
assert.deepEqual(anchored.grid_start, {x: 0, z: 0});
assert.deepEqual(anchored.path, [{x: 1, z: 1}, {x: 0, z: 0}, {x: 4, z: 0}],
  "the checked player segment enters the current tile center before the grid path");
assert.equal(anchored.steps, 1, "the player-to-center segment does not count as a grid step");
assert.equal(anchored.anchor_distance, Math.SQRT2);
assert.equal(anchored.grid_distance, 4);
assert.equal(anchored.distance, Math.SQRT2 + 4);
assert.deepEqual(anchored.next, {kind: "anchor", direction: "southwest", x: 0, z: 0});
for (const [x, z, direction] of [[0, -1, "north"], [-1, -1, "northeast"], [-1, 0, "east"],
  [-1, 1, "southeast"], [0, 1, "south"], [1, 1, "southwest"], [1, 0, "west"], [1, -1, "northwest"]]) {
  const bearing = route([cell(0, 0)], {x, z}, {x: 0, z: 0}, {x: 0, z: 0, clear: true});
  assert.equal(bearing.next.direction, direction, "anchor bearing follows the fixed eight-way world compass");
}
assert.equal(route(straight, {x: 1, z: 1}, {x: 4, z: 0}, undefined).origin, undefined,
  "explicit undefined keeps the legacy grid-center result shape");
assert.deepEqual(route(straight, {x: 1, z: 1}, {x: 4, z: 0}, undefined),
  route(straight, {x: 1, z: 1}, {x: 4, z: 0}));

const sameCellGoal = route(straight, {x: 0.5, z: 0.5}, {x: 0, z: 0}, {x: 0, z: 0, clear: true});
assert.equal(sameCellGoal.status, "found", "the player has not arrived until reaching the goal center");
assert.deepEqual(sameCellGoal.path, [{x: 0.5, z: 0.5}, {x: 0, z: 0}]);
assert.equal(sameCellGoal.steps, 0);
assert.equal(sameCellGoal.distance, Math.hypot(0.5, 0.5));
assert.equal(sameCellGoal.next.kind, "anchor");
assert.equal(route(straight, {x: 0, z: 0}, {x: 0, z: 0}, {x: 0, z: 0, clear: true}).status, "arrived");
assert.deepEqual(route(straight, {x: 0, z: 0}, {x: 0, z: 0}, {x: 0, z: 0, clear: true}).path,
  [{x: 0, z: 0}], "the player-to-center point is emitted only once when both positions match");

const blockedAnchor = route(straight, {x: 1, z: 1}, {x: 4, z: 0}, {x: 0, z: 0, clear: false});
assert.equal(blockedAnchor.status, "anchor_blocked");
assert.deepEqual(blockedAnchor.path, [], "a failed current-point check never draws an unchecked player segment");
for (const invalidAnchor of [null, {x: 0, z: 0, clear: 1}, {x: 0, z: 0},
  {x: 0, z: 0, clear: true, extra: 1}, {x: NaN, z: 0, clear: true}, {x: 4, z: 0, clear: true}]) {
  const result = route(straight, {x: 1, z: 1}, {x: 4, z: 0}, invalidAnchor);
  assert.equal(result.status, "anchor_unknown", "invalid or mismatched player anchors stay unknown");
  assert.deepEqual(result.path, []);
}
assert.equal(route([cell(0, 0, false)], {x: 1, z: 1}, {x: 0, z: 0},
  {x: 0, z: 0, clear: false}).status, "anchor_unknown",
  "a player anchor must reference the unique currently passable tile center");
assert.equal(route([cell(1e100, 0)], {x: 1e100, z: 0}, {x: 1e100, z: 0},
  {x: 1e100, z: 0, clear: true}).status, "anchor_unknown",
  "anchors in numerically unreliable tile intervals are rejected");
assert.equal(route(straight, {x: 1, z: 1}, null, null).status, "no_destination",
  "missing destination keeps the original input priority");
assert.equal(route(straight, null, {x: 4, z: 0}, null).status, "no_position",
  "missing player position keeps the original input priority");

const farEnough = route(largeMap, {x: 0, z: 0}, {x: 9996, z: 0}, {x: 0, z: 0, clear: true});
assert.equal(farEnough.status, "found");
assert.ok(Number.isFinite(farEnough.distance), "large checked routes keep finite total distances");
assert.equal(farEnough.steps, 2499);

console.log("Checked-grid routes: statuses, boundaries, strict edges, player anchors, BFS, and 2500 cells passed");
