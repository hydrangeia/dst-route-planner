const assert = require("node:assert/strict");
const {findRoute, locatePassableTile, cameraRelativeDirection, findNearestTarget} = require("./dst_route_planner/static/checked_routes.js");

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

assert.deepEqual(locatePassableTile([], {x: 0, z: 0}), {status: "unknown", tile: null},
  "an old replay with no observed tiles cannot locate a target");
assert.deepEqual(locatePassableTile(undefined, {x: 0, z: 0}), {status: "unknown", tile: null});
assert.deepEqual(locatePassableTile([cell(0, 0)], null), {status: "unknown", tile: null});
assert.deepEqual(locatePassableTile([cell(0, 0)], {x: Infinity, z: 0}),
  {status: "unknown", tile: null}, "non-finite target coordinates stay unknown");
assert.deepEqual(locatePassableTile([cell(0, 0)], {x: 0, z: NaN}),
  {status: "unknown", tile: null});

const negativeTarget = locatePassableTile([cell(-8, -4)], {x: -9, z: -3});
assert.deepEqual(negativeTarget, {status: "found", tile: {x: -8, z: -4}});
assert.deepEqual(Object.keys(negativeTarget.tile).sort(), ["x", "z"],
  "located tiles expose only their center coordinates");
assert.deepEqual(locatePassableTile([cell(-4, 0), cell(0, 0)], {x: -2, z: 0}),
  {status: "found", tile: {x: 0, z: 0}}, "a shared lower boundary belongs to the eastern cell");
assert.deepEqual(locatePassableTile([cell(0, 0), cell(4, 0)], {x: 2, z: 0}),
  {status: "found", tile: {x: 4, z: 0}}, "a shared upper boundary belongs to the next cell");
assert.deepEqual(locatePassableTile([cell(0, 0)], {x: 2, z: 0}),
  {status: "unknown", tile: null}, "uncovered bounds are not snapped to a nearby tile");
assert.deepEqual(locatePassableTile([cell(-4, 0), cell(0, 0), cell(4, 0)], {x: -2, z: 0}).tile,
  route([cell(-4, 0), cell(0, 0), cell(4, 0)], {x: -2, z: 0}, {x: 0, z: 0}).start,
  "landmark lookup and route-start lookup use the same half-open cell rule");
assert.deepEqual(locatePassableTile([cell(-4, 0, false)], {x: -3, z: 0}),
  {status: "blocked", tile: {x: -4, z: 0}}, "a known false cell returns its center as blocked");
assert.deepEqual(locatePassableTile([{x: 0, z: 0, tile: "GRASS"}], {x: 0, z: 0}),
  {status: "unknown", tile: null}, "missing passability remains unknown");
for (const passable of [null, 0, 1, "true"]) {
  assert.deepEqual(locatePassableTile([cell(0, 0, passable)], {x: 0, z: 0}),
    {status: "unknown", tile: null}, "only strict boolean passability is known");
}
assert.deepEqual(locatePassableTile([cell(0, 0, false)], {x: 0, z: 0}),
  {status: "blocked", tile: {x: 0, z: 0}}, "strict false is distinguishable from unknown");
assert.deepEqual(locatePassableTile([cell(0, 0), cell(2, 0)], {x: 1, z: 0}),
  {status: "unknown", tile: null}, "overlapping cells make target lookup ambiguous");
assert.deepEqual(locatePassableTile([cell(0, 0), cell(0, 0, false)], {x: 0, z: 0}),
  {status: "unknown", tile: null}, "duplicate centers stay unknown even if one is blocked");
assert.deepEqual(locatePassableTile([cell(Number.MAX_VALUE, 0)], {x: Number.MAX_VALUE, z: 0}),
  {status: "unknown", tile: null}, "overflowing half-open bounds stay unknown");
assert.deepEqual(locatePassableTile([cell(1e100, 0)], {x: 1e100, z: 0}),
  {status: "unknown", tile: null}, "collapsed bounds stay unknown");
assert.deepEqual(locatePassableTile([cell(Infinity, 0)], {x: 0, z: 0}),
  {status: "unknown", tile: null}, "non-finite tile centers cannot cover a target");

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
const lookupStarted = Date.now();
const largeLookup = locatePassableTile(largeMap, {x: 9997, z: 0});
const lookupElapsed = Date.now() - lookupStarted;
assert.deepEqual(largeLookup, {status: "found", tile: {x: 9996, z: 0}});
assert.ok(lookupElapsed < 5000, "2500 terrain cells should support interactive target lookup");

const nearestDetourTiles = [
  cell(0, 0, true, {north: true}),
  cell(0, 4, true, {north: true, east: true}),
  cell(0, 8),
  cell(4, 4),
  cell(4, 0, true, {north: true}),
];
const misleadingLandmarks = [
  {prefab: "close-but-long-route", x: 4, z: 0},
  {prefab: "farther-but-short-route", x: 0, z: 8},
];
const nearestDetour = findNearestTarget(nearestDetourTiles, {x: 0, z: 0}, misleadingLandmarks);
assert.equal(Math.hypot(misleadingLandmarks[0].x, misleadingLandmarks[0].z), 4);
assert.equal(Math.hypot(misleadingLandmarks[1].x, misleadingLandmarks[1].z), 8);
assert.equal(route(nearestDetourTiles, {x: 0, z: 0}, {x: 4, z: 0}).distance, 12);
assert.equal(nearestDetour.landmark.prefab, "farther-but-short-route",
  "target selection minimizes checked route distance instead of direct distance");
assert.equal(nearestDetour.route.distance, 8);
assert.deepEqual(nearestDetour.destination, {x: 0, z: 8});

const unreachableAndUnknownTiles = [
  cell(0, 0, true, {east: true}),
  cell(4, 0),
  cell(8, 0),
  cell(12, 0, false),
];
const nonReachableLandmarks = [
  {prefab: "unreachable", x: 8, z: 0},
  {prefab: "unknown", x: 100, z: 100},
  {prefab: "blocked", x: 12, z: 0},
];
assert.equal(findNearestTarget(unreachableAndUnknownTiles, {x: 0, z: 0}, nonReachableLandmarks), null,
  "unreachable, unknown, and blocked targets are ignored");

const sameTileTiles = [cell(0, 0)];
const sameTileLandmark = [{prefab: "same-tile", x: 1, z: 1}];
const sameTileTarget = findNearestTarget(sameTileTiles, {x: 1, z: 1}, sameTileLandmark);
assert.equal(sameTileTarget.route.status, "arrived");
assert.equal(sameTileTarget.route.distance, 0);
assert.deepEqual(sameTileTarget.destination, {x: 0, z: 0},
  "target coordinates resolve to their containing tile center");
const sameTileAnchoredTarget = findNearestTarget(
  sameTileTiles,
  {x: 1, z: 1},
  sameTileLandmark,
  {x: 0, z: 0, clear: true}
);
assert.equal(sameTileAnchoredTarget.route.status, "found");
assert.equal(sameTileAnchoredTarget.route.distance, Math.SQRT2,
  "player-anchor distance remains part of the route, even for a same-tile target");
assert.deepEqual(sameTileAnchoredTarget.route.path, [{x: 1, z: 1}, {x: 0, z: 0}]);
assert.equal(findNearestTarget(sameTileTiles, {x: 1, z: 1}, sameTileLandmark,
  {x: 0, z: 0, clear: false}), null, "a blocked player anchor yields no candidate");
assert.equal(findNearestTarget(sameTileTiles, {x: 1, z: 1}, sameTileLandmark, null), null,
  "an invalid explicit player anchor yields no candidate");

const malformedLandmarks = [
  null,
  [],
  {x: 0, z: 0},
  {prefab: "", x: 0, z: 0},
  {prefab: "   ", x: 0, z: 0},
  {prefab: "bad-x", x: NaN, z: 0},
  {prefab: "bad-z", x: 0, z: Infinity},
  {prefab: 7, x: 0, z: 0},
  {prefab: "valid", x: 0, z: 0},
];
const malformedSelection = findNearestTarget(sameTileTiles, {x: 0, z: 0}, malformedLandmarks);
assert.equal(malformedSelection.landmark.prefab, "valid",
  "malformed candidates are skipped while later entries remain eligible");
assert.deepEqual(findNearestTarget(sameTileTiles, {x: 0, z: 0}, [malformedLandmarks[0]]), null);

const tiedTiles = [cell(0, 0, true, {east: true, north: true}), cell(4, 0), cell(0, 4)];
const tiedLandmarks = [
  {prefab: "first", x: 0, z: 4},
  {prefab: "second", x: 4, z: 0},
];
assert.equal(findNearestTarget(tiedTiles, {x: 0, z: 0}, tiedLandmarks).landmark.prefab, "first",
  "equal checked distances keep the first input candidate");

const elevenTileLine = Array.from({length: 11}, (_, index) =>
  cell(index * 4, 0, true, index < 10 ? {east: true} : {}));
const elevenLandmarks = Array.from({length: 11}, (_, index) => ({
  prefab: "candidate-" + index,
  x: (10 - index) * 4,
  z: 0,
}));
assert.equal(findNearestTarget(elevenTileLine, {x: 0, z: 0}, elevenLandmarks).landmark.prefab,
  "candidate-10", "selection considers entries after the recent-ten display window");

const boundaryLandmarks = Array.from({length: 499}, () => ({prefab: "bad", x: NaN, z: 0}));
boundaryLandmarks.push({prefab: "last-allowed", x: 4, z: 0});
boundaryLandmarks.push({prefab: "over-limit", x: 0, z: 0});
assert.equal(findNearestTarget(straight, {x: 0, z: 0}, boundaryLandmarks).landmark.prefab,
  "last-allowed", "the 500th candidate is considered and the 501st is outside the cap");

const immutableTiles = [cell(0, 0, true, {east: true}), cell(4, 0)];
const immutablePosition = {x: 1, z: 1};
const immutableLandmarks = [{prefab: "copy-me", x: 4, z: 0, metadata: {seen: true}}];
const immutableAnchor = {x: 0, z: 0, clear: true};
const immutableBefore = structuredClone({
  tiles: immutableTiles,
  position: immutablePosition,
  landmarks: immutableLandmarks,
  anchor: immutableAnchor,
});
findNearestTarget(immutableTiles, immutablePosition, immutableLandmarks, immutableAnchor);
assert.deepEqual({
  tiles: immutableTiles,
  position: immutablePosition,
  landmarks: immutableLandmarks,
  anchor: immutableAnchor,
}, immutableBefore, "target selection does not mutate its inputs");
const legacyNearest = findNearestTarget(straight, {x: 1, z: 1}, [{prefab: "legacy", x: 4, z: 0}]);
assert.deepEqual(legacyNearest.route, findRoute(straight, {x: 1, z: 1}, {x: 4, z: 0}),
  "omitting the anchor preserves the legacy grid route result shape");

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

const screenDirections = ["up", "upper_right", "right", "lower_right",
  "down", "lower_left", "left", "upper_left"];
const groundDirections = [
  [1, 0, "down"],
  [1, 1, "lower_right"],
  [0, 1, "right"],
  [-1, 1, "upper_right"],
  [-1, 0, "up"],
  [-1, -1, "upper_left"],
  [0, -1, "left"],
  [1, -1, "lower_left"],
];
const cameraOffsets = [
  {heading: 0, offset: 0},
  {heading: 45, offset: 1},
  {heading: 90, offset: 2},
  {heading: 180, offset: 4},
  {heading: 270, offset: 6},
  {heading: 315, offset: 7},
];
for (const {heading, offset} of cameraOffsets) {
  for (const [x, z, headingZeroDirection] of groundDirections) {
    const zeroIndex = screenDirections.indexOf(headingZeroDirection);
    const expected = screenDirections[(zeroIndex + offset) % screenDirections.length];
    assert.equal(cameraRelativeDirection({x: 0, z: 0}, {x, z}, heading), expected,
      "camera heading rotates each of the eight world directions into screen space");
  }
}

const diagonal = Math.SQRT1_2;
const basisChecks = [
  [0, -1, 0, "up"], [0, 0, 1, "right"],
  [90, 0, -1, "up"], [90, -1, 0, "right"],
  [180, 1, 0, "up"], [180, 0, -1, "right"],
  [270, 0, 1, "up"], [270, 1, 0, "right"],
  [45, -diagonal, -diagonal, "up"], [45, -diagonal, diagonal, "right"],
  [315, -diagonal, diagonal, "up"], [315, diagonal, diagonal, "right"],
];
for (const [heading, x, z, expected] of basisChecks) {
  assert.equal(cameraRelativeDirection({x: 0, z: 0}, {x, z}, heading), expected,
    "camera up and right basis vectors match the DST camera orientation");
}
assert.equal(cameraRelativeDirection({x: 0, z: 0}, {x: 0, z: 1}, 0), "right");
assert.equal(cameraRelativeDirection({x: 0, z: 0}, {x: 0, z: 1}, 90), "down",
  "changing camera heading rotates the same ground movement on screen");
assert.equal(cameraRelativeDirection({x: 0, z: 0}, {x: 1, z: 0}, 45), "lower_left");

for (const [heading, equivalent] of [[-45, 315], [450, 90], [360 * 1000000000000 + 45, 45],
  [Number.MAX_VALUE, Number.MAX_VALUE % 360]]) {
  assert.equal(
    cameraRelativeDirection({x: 0, z: 0}, {x: 1, z: 2}, heading),
    cameraRelativeDirection({x: 0, z: 0}, {x: 1, z: 2}, equivalent),
    "finite headings are reduced modulo 360 before trigonometry"
  );
}

for (const invalid of [null, [], {x: "0", z: 0}, {x: null, z: 0}, {x: true, z: 0},
  {x: NaN, z: 0}, {x: 0, z: Infinity}, {x: 0}, {z: 0}]) {
  assert.equal(cameraRelativeDirection(invalid, {x: 1, z: 0}, 0), null,
    "invalid or sparse source coordinates are rejected");
  assert.equal(cameraRelativeDirection({x: 0, z: 0}, invalid, 0), null,
    "invalid or sparse destination coordinates are rejected");
}
for (const heading of [null, "90", true, NaN, Infinity, -Infinity]) {
  assert.equal(cameraRelativeDirection({x: 0, z: 0}, {x: 1, z: 0}, heading), null,
    "heading must be a finite number");
}
assert.equal(cameraRelativeDirection({x: 1, z: 2}, {x: 1, z: 2}, 0), null,
  "zero displacement has no direction");
assert.equal(cameraRelativeDirection(
  {x: -Number.MAX_VALUE, z: 0}, {x: Number.MAX_VALUE, z: 0}, 0), null,
  "a coordinate subtraction that overflows is rejected");
assert.equal(cameraRelativeDirection(
  {x: 0, z: 0}, {x: Number.MAX_VALUE, z: Number.MAX_VALUE}, 0), "lower_right",
  "large finite coordinates are scaled before projection");
assert.equal(cameraRelativeDirection(
  {x: Number.MAX_VALUE / 2, z: -Number.MAX_VALUE / 2},
  {x: Number.MAX_VALUE, z: Number.MAX_VALUE / 2}, 0), "lower_right",
  "large finite deltas remain safe during camera projection");
assert.equal(cameraRelativeDirection(
  {x: 0, z: 0}, {x: Number.MIN_VALUE, z: 0}, 0), "down",
  "subnormal but nonzero displacement remains directional");
console.log("Checked-grid routes: routes, camera directions, target selection, boundaries, anchors, BFS, and 2500 cells passed");
