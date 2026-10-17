const assert = require("node:assert/strict");
const {findRoute} = require("./dst_route_planner/static/checked_routes.js");

function cell(x, z, passable = true, connections) {
  return {
    x, z, tile: "GRASS", last_sequence: 1, passable,
    ...(connections === undefined ? {} : {connections})
  };
}
function route(tiles, position, destination) {
  return findRoute(tiles, position, destination);
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

console.log("Checked-grid routes: statuses, boundaries, strict edges, BFS, replacement, and 2500 cells passed");
