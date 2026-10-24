const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const appHtml = fs.readFileSync("dst_route_planner/static/app.html", "utf8");
const checkedRoutesSource = fs.readFileSync("dst_route_planner/static/checked_routes.js", "utf8");
const source = appHtml.match(/<script>([\s\S]*?)<\/script>/)[1].replace("    initialize();", "");
const elements = new Map();
let nextTimerId = 0;
const scheduledTimers = new Map();
function fakeSetTimeout(callback, delay = 0) {
  const id = ++nextTimerId;
  scheduledTimers.set(id, {callback, delay});
  return id;
}
function fakeClearTimeout(id) { scheduledTimers.delete(id); }
function fireScheduledTimer(id) {
  const timer = scheduledTimers.get(id);
  assert.ok(timer, "timer " + id + " is scheduled");
  scheduledTimers.delete(id);
  timer.callback();
}
function element(id) {
  if (!elements.has(id)) elements.set(id, {
    value: "", checked: false, disabled: false, textContent: "", innerHTML: "",
    className: "", href: "", hidden: true, listeners: Object.create(null),
    classList: {add() {}, remove() {}, toggle() {}, contains() { return false; }},
    querySelectorAll() { return []; }, click() { this.clickCount = (this.clickCount || 0) + 1; },
    addEventListener(name, handler) { this.listeners[name] = handler; },
    removeAttribute(name) { if (name === "href") this.href = ""; }
  });
  return elements.get(id);
}
const context = vm.createContext({
  document: {getElementById: element}, AbortController,
  fetch: async () => { throw new Error("unexpected fetch"); },
  setTimeout: fakeSetTimeout, clearTimeout: fakeClearTimeout, routeTestNow: 0
});
vm.runInContext(checkedRoutesSource, context);
vm.runInContext(source, context);
run('routeFreshness.now=()=>routeTestNow');
assert.ok(appHtml.includes('<script src="/static/checked_routes.js"></script>'), "the route finder loads before the page script");
const routeDestinationElement = element("routeDestinationSelect");
let routeOptionsMarkup = routeDestinationElement.innerHTML;
routeDestinationElement.optionMarkupWrites = 0;
Object.defineProperty(routeDestinationElement, "innerHTML", {
  get() { return routeOptionsMarkup; },
  set(value) { routeDestinationElement.optionMarkupWrites += 1; routeOptionsMarkup = value; }
});
function run(code) { return vm.runInContext(code, context); }
function apiResponse(payload) { return {ok: true, json: async () => payload}; }
function trailPoint(sequence, capturedAt, x, z, playerAnchor = undefined, cameraHeading = undefined) {
  return {sequence, captured_at: capturedAt, x, z,
    ...(playerAnchor === undefined ? {} : {player_anchor: playerAnchor}),
    ...(cameraHeading === undefined ? {} : {camera_heading: cameraHeading})};
}
function remembered(prefab, x, z, firstSequence, lastSequence, firstSeen = firstSequence, lastSeen = lastSequence) {
  return {prefab, x, z, first_seen: firstSeen, last_seen: lastSeen, first_sequence: firstSequence, last_sequence: lastSequence};
}
function terrainCell(x, z, tile, lastSequence, lastSeen = lastSequence, passable, connections) {
  return {x, z, tile, last_seen: lastSeen, last_sequence: lastSequence,
    ...(arguments.length < 6 ? {} : {passable}), ...(arguments.length < 7 ? {} : {connections})};
}
function trailPayload(summary, points, landmarks = undefined, landmarksTruncated = false, terrain = undefined) {
  const xs = points.map(point => point.x), zs = points.map(point => point.z);
  return {
    trail_version: 1, id: summary.id, world_id: summary.world_id,
    world_kind: summary.world_kind, session_id: summary.session_id,
    ...(Object.prototype.hasOwnProperty.call(summary, "segment") ? {segment: summary.segment} : {}),
    frame_count: points.length, points,
    bounds: points.length ? {min_x: Math.min(...xs), max_x: Math.max(...xs), min_z: Math.min(...zs), max_z: Math.max(...zs)} : null,
    ...(landmarks === undefined ? {} : {landmarks, landmarks_truncated: landmarksTruncated}),
    ...(terrain === undefined ? {} : {terrain})
  };
}
function trailPlaybackPayload(summary, points, throughSequence, totalFrameCount, landmarks = undefined, terrain = undefined) {
  return {...trailPayload(summary, points, landmarks, false, terrain),
    playback: {through_sequence: throughSequence, total_frame_count: totalFrameCount}};
}
run('state.options={targets:["panflute","moonbase"],tile_types:["GRASS"],prefabs:["grass"],directions:DIRS.slice()}; live.following=true;');
function replaySummary(id, options = {}) {
  return {
    id,
    world_id: options.worldId || "world-a",
    world_kind: options.worldKind || "forest",
    session_id: options.session || "two",
    frame_count: options.frames ?? 1,
    started_at: options.startedAt || "2026-10-14T10:00:00.000Z",
    last_captured_at: options.lastCapturedAt === undefined ? "2026-10-14T10:01:00.000Z" : options.lastCapturedAt,
    status: options.status || "recording",
    ...(options.segment === undefined ? {} : {segment: options.segment}),
    ...(options.error ? {error: options.error} : {})
  };
}
function frame(session = "one", sequence = 1, recording = null, worldId = "world-a", trail = {}) {
  const result = {
    status: "live", age_seconds: 0.5,
    snapshot: {
      world_id: worldId, world_kind: trail.worldKind || "forest", session_id: session, sequence,
      captured_at: trail.capturedAt === undefined ? sequence : trail.capturedAt,
      position: {x: trail.x === undefined ? 12 : trail.x, y: 0, z: trail.z === undefined ? 30 : trail.z},
      current: {prefab_counts: {observed_custom_prefab: 2}},
      directions: {north: {tile_types: ["CUSTOM_TILE"], prefab_counts: {panflute: 1}}}
    },
    plan: {directions: [{direction: "north", score: 4, p_dir: 1, p_task: 0, p_room: 0, explanation: []}], current_tasks: []},
    visible_target: {x: 12, z: 34, distance: 4}
  };
  if (recording) result.recording = recording;
  if (Object.prototype.hasOwnProperty.call(trail, "landmarks")) result.snapshot.landmarks = trail.landmarks;
  if (Object.prototype.hasOwnProperty.call(trail, "terrain")) result.snapshot.terrain = trail.terrain;
  if (Object.prototype.hasOwnProperty.call(trail, "player_anchor")) result.snapshot.player_anchor = trail.player_anchor;
  if (Object.prototype.hasOwnProperty.call(trail, "camera_heading")) result.snapshot.camera_heading = trail.camera_heading;
  return result;
}
const legacyReplay = replaySummary("9".repeat(64));
const normalizedLegacyReplay = run("normalizeExplorationSummary(" + JSON.stringify(legacyReplay) + ")");
assert.equal(run("replaySegment(" + JSON.stringify(legacyReplay) + ")"), 1, "an omitted segment means part one");
assert.equal(Object.hasOwn(normalizedLegacyReplay, "segment"), false, "normalizing a legacy summary preserves its omitted segment field");
for (const invalidSegment of [true, "2", 1, 0, -1, 1.5, null, Number.MAX_SAFE_INTEGER + 1]) {
  const invalidSummary = {...legacyReplay, segment: invalidSegment};
  assert.equal(run("normalizeExplorationSummary(" + JSON.stringify(invalidSummary) + ")"), null,
    "summary segment values must be safe integers of at least two: " + String(invalidSegment));
}
const maxSegmentReplay = {...legacyReplay, segment: Number.MAX_SAFE_INTEGER};
assert.equal(run("normalizeExplorationSummary(" + JSON.stringify(maxSegmentReplay) + ").segment"), Number.MAX_SAFE_INTEGER,
  "the largest safe segment number is accepted");
const segmentTwoReplay = replaySummary("8".repeat(64), {worldId: "segment-world", session: "segment-session", segment: 2});
const legacyPayload = run("validateTrailPayload(" + JSON.stringify(trailPayload(legacyReplay, [trailPoint(1, 1, 3, 4)])) + "," +
  JSON.stringify(legacyReplay) + ")");
assert.equal(Object.hasOwn(legacyPayload, "segment"), false, "legacy trail payload normalization preserves an omitted segment field");
assert.throws(() => run("validateTrailPayload(" + JSON.stringify(trailPayload(segmentTwoReplay, [trailPoint(1, 1, 3, 4)])) + "," +
  JSON.stringify({...segmentTwoReplay, segment: 3}) + ")"), /轨迹数据/, "a trail segment must agree with its expected summary");
const projection = run("projectTrailCoordinates([{sequence:1,captured_at:1,x:0,z:0},{sequence:2,captured_at:2,x:10,z:0},{sequence:3,captured_at:3,x:0,z:10}])");
assert.ok(projection.points[1].x > projection.points[0].x, "east (+X) projects right");
assert.ok(projection.points[2].y < projection.points[0].y, "north (+Z) projects up");
assert.ok(Math.abs((projection.points[1].x - projection.points[0].x) - (projection.points[0].y - projection.points[2].y)) < 1e-9,
  "equal world distances use the same map scale on X and Z");
assert.equal(run("projectTrailCoordinates([]).points.length"), 0);
assert.equal(run("projectTrailCoordinates([{sequence:1,captured_at:1,x:-1e308,z:0},{sequence:2,captured_at:2,x:1e308,z:0}]).error"), true,
  "extreme finite coordinates fail cleanly instead of producing invalid SVG values");
const landmarkProjection = run("projectTrailCoordinates([{sequence:1,captured_at:1,x:0,z:0}],[{prefab:'panflute',x:100,z:0}])");
assert.equal(landmarkProjection.ranges.max_x, 100, "displayed target positions expand map bounds");
assert.ok(landmarkProjection.landmarks[0].x > landmarkProjection.points[0].x, "target markers share the map's world projection");
assert.equal(run("landmarkRelativeLabel({x:0,z:20},{x:0,z:0})"), "北 · 直线距离 20.0");
assert.equal(run("landmarkRelativeLabel({x:20,z:0},{x:0,z:0})"), "东 · 直线距离 20.0");
assert.equal(run("landmarkRelativeLabel({x:0,z:0},{x:0,z:0})"), "同一位置 · 直线距离 0.0");
for (const [x, z, heading] of [[1, 1, "东北"], [1, -1, "东南"], [-1, -1, "西南"], [-1, 1, "西北"], [0, -5, "南"], [-5, 0, "西"]]) {
  const bearing = run("landmarkRelativeLabel(" + JSON.stringify({x, z}) + ",{x:0,z:0})");
  assert.ok(bearing.startsWith(heading + " · 直线距离 "), heading + " bearing uses +Z north and +X east");
}
const stationaryProjection = run("projectTrailCoordinates([{sequence:1,captured_at:1,x:7,z:-4},{sequence:2,captured_at:2,x:7,z:-4}])");
assert.deepEqual(
  {x: stationaryProjection.points[0].x, y: stationaryProjection.points[0].y},
  {x: stationaryProjection.points[1].x, y: stationaryProjection.points[1].y}
);
run('trailState.points=[];trailState.error="";renderTrail()');
assert.ok(element("trailSvg").innerHTML.includes("还没有可绘制的坐标"));
assert.ok(element("terrainConnectionStatus").textContent.includes("0.4.0"), "missing connection data prompts the collector update");
run('trailState.points=[{sequence:1,captured_at:1,x:7,z:-4},{sequence:2,captured_at:2,x:7,z:-4}];renderTrail()');
assert.ok(element("trailSvg").innerHTML.includes('class="trail-route"'));
assert.ok(element("trailSvg").innerHTML.includes('class="trail-first"'));
assert.ok(element("trailSvg").innerHTML.includes('class="trail-latest"'));
assert.ok(element("trailSvg").innerHTML.includes("起点") && element("trailSvg").innerHTML.includes("最新位置"));
assert.equal(element("terrainToggle").checked, true, "observed terrain is on by default");
assert.equal(element("terrainConnectionToggle").checked, false, "neighbor checks are off by default");
assert.ok(appHtml.includes('id="terrainLegend"') && appHtml.includes('aria-label="地皮图例"'), "the map has a named terrain legend");
assert.ok(appHtml.includes('id="terrainConnectionLegend"') && appHtml.includes('aria-label="邻格检查图例"'), "neighbor checks have a named legend");
assert.ok(appHtml.includes("显示邻格检查"), "the independent neighbor-check switch has the requested label");
for (const label of ["草地", "森林", "岩地", "沼泽", "水域", "其他"]) assert.ok(appHtml.includes(">" + label + "</span>"), "legend includes " + label);
assert.ok(appHtml.includes(".terrain-water { background: #83b9c9; fill: #83b9c9; }"), "SVG terrain classes define fill colors");
assert.ok(appHtml.includes("斜线：格中心不可通行"), "terrain legend explains the blocked-center slash");
const storedPassableFalse = JSON.parse(run(`JSON.stringify(normalizeStoredTerrainTile({x:1,z:2,tile:"GRASS",last_seen:3,last_sequence:4,passable:false}))`));
assert.equal(storedPassableFalse.passable, false, "stored normalization preserves passable=false");
const storedPassableTrue = JSON.parse(run(`JSON.stringify(normalizeStoredTerrainTile({x:1,z:2,tile:"GRASS",last_seen:3,last_sequence:4,passable:true}))`));
assert.equal(storedPassableTrue.passable, true, "stored normalization preserves passable=true");
const storedUnknownPassability = JSON.parse(run(`JSON.stringify(normalizeStoredTerrainTile({x:1,z:2,tile:"GRASS",last_seen:3,last_sequence:4}))`));
assert.ok(!Object.hasOwn(storedUnknownPassability, "passable"), "unknown stored passability stays omitted");
assert.equal(run(`normalizeStoredTerrainTile({x:1,z:2,tile:"GRASS",last_seen:3,last_sequence:4,passable:null})`), null,
  "stored normalization rejects null optional passability");
const badStoredPassability = run(`validateTrailTerrain({tile_size:4,tiles:[{x:1,z:2,tile:"GRASS",last_seen:3,last_sequence:4,passable:0}],truncated:false})`);
assert.ok(badStoredPassability.error.includes("地皮位置"), "invalid saved passability becomes a terrain-panel error");
const normalizedSnapshotTerrain = JSON.parse(run(`JSON.stringify(normalizeSnapshotTerrain({sequence:4,captured_at:3,terrain:{tile_size:4,tiles:[{x:0,z:0,tile:"GRASS",passable:false},{x:4,z:0,tile:"ROCKY",passable:true},{x:8,z:0,tile:"MARSH"}]}}))`));
assert.deepEqual(normalizedSnapshotTerrain.tiles.map(tile => tile.passable), [false, true, undefined],
  "snapshot normalization preserves false and true while leaving unknown omitted");
assert.ok(!Object.hasOwn(normalizedSnapshotTerrain.tiles[2], "passable"));
assert.equal(run(`(()=>{try{normalizeSnapshotTerrain({sequence:4,captured_at:3,terrain:{tile_size:4,tiles:[{x:0,z:0,tile:"GRASS",passable:null}]}});return ""}catch(error){return error.message}})()`),
  "实时地皮位置格式无法识别。", "live normalization rejects invalid optional passability");
const mergedNewerKnown = JSON.parse(run(`JSON.stringify(mergeTrailTerrain([{x:1,z:2,tile:"GRASS",last_seen:1,last_sequence:1,passable:true}],[{x:1,z:2,tile:"MARSH",last_seen:2,last_sequence:2,passable:false}]).tiles)`));
assert.equal(mergedNewerKnown[0].passable, false, "a newer terrain sequence replaces the full tile and preserves false");
const mergedNewerUnknown = JSON.parse(run(`JSON.stringify(mergeTrailTerrain([{x:1,z:2,tile:"GRASS",last_seen:1,last_sequence:1,passable:false}],[{x:1,z:2,tile:"FOREST",last_seen:2,last_sequence:2}]).tiles)`));
assert.ok(!Object.hasOwn(mergedNewerUnknown[0], "passable"), "a newer unknown tile clears old passability instead of inheriting it");
const storedConnections = JSON.parse(run(`JSON.stringify(normalizeStoredTerrainTile({x:1,z:2,tile:"GRASS",last_seen:3,last_sequence:4,connections:{east:true,north:false}}))`));
assert.deepEqual(storedConnections.connections, {east: true, north: false}, "stored normalization preserves false connection results");
const storedUnknownConnections = JSON.parse(run(`JSON.stringify(normalizeStoredTerrainTile({x:1,z:2,tile:"GRASS",last_seen:3,last_sequence:4}))`));
assert.ok(!Object.hasOwn(storedUnknownConnections, "connections"), "unknown stored connections stay omitted");
for (const invalidConnections of [null, [], {east: 1}, {west: true}, {north: "true"}]) {
  const encoded = JSON.stringify(invalidConnections);
  assert.equal(run(`normalizeStoredTerrainTile({x:1,z:2,tile:"GRASS",last_seen:3,last_sequence:4,connections:${encoded}})`), null,
    "stored normalization rejects malformed connection dictionaries");
  const invalidSaved = run(`validateTrailTerrain({tile_size:4,tiles:[{x:1,z:2,tile:"GRASS",last_seen:3,last_sequence:4,connections:${encoded}}],truncated:false})`);
  assert.ok(invalidSaved.error.includes("地皮"), "malformed saved connections stay a terrain-panel error");
  assert.equal(run(`(()=>{try{normalizeSnapshotTerrain({sequence:4,captured_at:3,terrain:{tile_size:4,tiles:[{x:0,z:0,tile:"GRASS",connections:${encoded}}]}});return ""}catch(error){return error.message}})()`),
    "实时地皮位置格式无法识别。", "live normalization rejects malformed connection dictionaries");
}
const mergedNewerConnections = JSON.parse(run(`JSON.stringify(mergeTrailTerrain([{x:1,z:2,tile:"GRASS",last_seen:1,last_sequence:1,connections:{east:true,north:false}}],[{x:1,z:2,tile:"MARSH",last_seen:2,last_sequence:2,connections:{east:false}}]).tiles)`));
assert.deepEqual(mergedNewerConnections[0].connections, {east: false}, "a newer connection dictionary replaces the whole old dictionary");
const mergedNoConnections = JSON.parse(run(`JSON.stringify(mergeTrailTerrain([{x:1,z:2,tile:"GRASS",last_seen:1,last_sequence:1,connections:{east:true}}],[{x:1,z:2,tile:"FOREST",last_seen:2,last_sequence:2}]).tiles)`));
assert.ok(!Object.hasOwn(mergedNoConnections[0], "connections"), "a newer tile without connections clears the older dictionary");
const normalizedConnectionSnapshot = JSON.parse(run(`JSON.stringify(normalizeSnapshotTerrain({sequence:4,captured_at:3,terrain:{tile_size:4,tiles:[{x:0,z:0,tile:"GRASS",connections:{east:false,north:true}},{x:4,z:0,tile:"ROCKY",connections:{east:true}},{x:8,z:0,tile:"MARSH"}]}}))`));
assert.deepEqual(normalizedConnectionSnapshot.tiles.map(tile => tile.connections), [{east:false,north:true},{east:true},undefined],
  "live normalization preserves false and omitted connection directions");
const terrainProjection = run('projectTrailCoordinates([{sequence:1,captured_at:1,x:0,z:0},{sequence:2,captured_at:2,x:4,z:0}],[],[{x:0,z:0,tile:"GRASS"},{x:4,z:0,tile:"OCEAN"},{x:8,z:0,tile:"OTHER"}])');
assert.ok(Math.abs((terrainProjection.points[1].x - terrainProjection.points[0].x) - 4 * terrainProjection.scale) < 1e-9,
  "terrain cells and player positions use the same X/Z scale");
const projectedConnectionMap = run('projectTrailCoordinates([],[],[{x:0,z:0,tile:"GRASS",passable:true,connections:{east:true,north:false}},{x:4,z:0,tile:"GRASS",passable:true},{x:0,z:4,tile:"GRASS",passable:true}])');
assert.deepEqual(JSON.parse(JSON.stringify(projectedConnectionMap.terrain[0].connections)), {east: true, north: false},
  "terrain projection preserves connection results");
context.projectedConnectionMap = projectedConnectionMap;
const projectedEdges = JSON.parse(run("JSON.stringify(projectTerrainConnections(projectedConnectionMap.terrain))"));
assert.equal(projectedEdges.edges.length, 2, "east and north checks each create one neighbor edge");
for (const edge of projectedEdges.edges) {
  const delta = edge.direction === "east" ? Math.abs(edge.x2 - edge.x1) : Math.abs(edge.y2 - edge.y1);
  assert.ok(Math.abs(delta - 4 * projectedConnectionMap.scale) < 1e-9, "neighbor edges use the same four-unit map scale");
}
context.hugeConnectionProjection = run('projectTrailCoordinates([],[],[{x:1e20,z:0,tile:"GRASS",passable:true,connections:{east:true}}])');
context.hugeConnectionProjection.error = false;
context.hugeConnectionProjection.terrain = context.hugeConnectionProjection.terrain || [];
context.projectedConnectionMap = context.hugeConnectionProjection;
const noSelfConnection = JSON.parse(run("JSON.stringify(projectTerrainConnections(projectedConnectionMap.terrain))"));
assert.equal(noSelfConnection.edges.length, 0, "large coordinates that cannot represent an eastward step do not create self-edges");
run('trailState.mode="live";trailState.points=[{sequence:1,captured_at:1,x:0,z:0},{sequence:2,captured_at:2,x:4,z:0}];trailState.terrainTiles=[{x:0,z:0,tile:"GRASS",last_seen:1,last_sequence:1,passable:false},{x:4,z:0,tile:"OCEAN",last_seen:2,last_sequence:2,passable:true},{x:8,z:0,tile:"<img&x>",last_seen:3,last_sequence:3}];trailState.terrainAvailable=true;trailState.terrainTruncated=false;trailState.terrainError="";renderTrail()');
const terrainSvg = element("trailSvg").innerHTML;
assert.equal((terrainSvg.match(/class="terrain-cell/g) || []).length, 3);
assert.ok(terrainSvg.includes("terrain-grass") && terrainSvg.includes("terrain-water") && terrainSvg.includes("terrain-other"),
  "known grass and water names are grouped, and unknown names stay neutral");
assert.ok(terrainSvg.includes("&lt;img&amp;x&gt;") && !terrainSvg.includes("<img"), "tile names are escaped inside SVG titles");
assert.ok(terrainSvg.includes("X 8.0 / Z 0.0"), "tile titles include world coordinates");
assert.equal((terrainSvg.match(/class="terrain-blocked"/g) || []).length, 1,
  "only passable=false terrain gets the center slash; true and unknown stay uncluttered");
assert.ok(terrainSvg.includes("地形不可通行 · 格中心检查失败") && terrainSvg.includes("地形可通行") && terrainSvg.includes("未采集通行状态"),
  "tile SVG titles distinguish blocked, passable, and unknown checks");
assert.ok(element("terrainStatus").textContent.includes("共 3 格") && element("terrainStatus").textContent.includes("已知 2") &&
  element("terrainStatus").textContent.includes("不可通行 1") && element("terrainStatus").textContent.includes("未知 1"),
  "terrain status reports total, known, blocked, and unknown check counts");
assert.equal(element("terrainLegend").hidden, false, "terrain legend is shown with the terrain layer");
assert.ok(terrainSvg.indexOf('class="terrain-cell') < terrainSvg.indexOf('class="trail-route-halo"'), "terrain is drawn below the trail halo");
const grassRect = terrainSvg.match(/class="terrain-cell terrain-grass" x="[^"]*" y="[^"]*" width="([^"]*)" height="([^"]*)"/);
assert.ok(grassRect && Math.abs(Number(grassRect[1]) - Number(grassRect[2])) < 1e-9, "four-unit tile cells render as squares");
const renderedWidth = Number(grassRect[1]);
assert.ok(Math.abs(renderedWidth - 4 * terrainProjection.scale) < 0.02, "cell edges use the same scale as coordinate movement");
element("terrainToggle").checked = false;
element("terrainToggle").listeners.change();
assert.ok(!element("trailSvg").innerHTML.includes("terrain-cell"), "the terrain toggle hides cells");
assert.ok(!element("trailSvg").innerHTML.includes("terrain-blocked"), "the terrain toggle hides blocked-cell marks");
assert.equal(element("terrainLegend").hidden, true, "the terrain toggle hides its legend");
assert.ok(element("terrainStatus").textContent.includes("3 格") && element("terrainStatus").textContent.includes("已隐藏"));
element("terrainToggle").checked = true;
element("terrainToggle").listeners.change();
assert.equal(element("terrainLegend").hidden, false, "turning terrain back on restores its legend");
const connectionFixture = [
  terrainCell(0, 0, "GRASS", 1, 1, true, {east: true, north: false}),
  terrainCell(4, 0, "GRASS", 1, 1, true), terrainCell(0, 4, "GRASS", 1, 1, true),
  terrainCell(8, 0, "ROCKY", 1, 1, false, {north: true}), terrainCell(8, 4, "GRASS", 1, 1, true),
  terrainCell(16, 0, "GRASS", 1, 1, true, {east: false}),
  terrainCell(24, 0, "GRASS", 1, 1, true, {east: true}),
  {x: 32, z: 0, tile: "GRASS", last_seen: 1, last_sequence: 1, connections: {east: true}},
  terrainCell(36, 0, "GRASS", 1, 1, true)
];
context.connectionFixture = connectionFixture;
run('trailState.mode="history";trailState.points=[{sequence:1,captured_at:1,x:0,z:0},{sequence:2,captured_at:2,x:4,z:4}];trailState.terrainTiles=connectionFixture;trailState.terrainAvailable=true;trailState.terrainTruncated=false;trailState.terrainError="";renderTrail()');
element("terrainToggle").checked = false;
element("terrainToggle").listeners.change();
element("terrainConnectionToggle").checked = true;
element("terrainConnectionToggle").listeners.change();
let connectionSvg = element("trailSvg").innerHTML;
assert.equal((connectionSvg.match(/class="terrain-connection terrain-connection-passable"/g) || []).length, 1,
  "only the east check with two passable observed tiles renders as passable");
assert.equal((connectionSvg.match(/class="terrain-connection terrain-connection-blocked"/g) || []).length, 1,
  "false north connection renders a distinct blocked edge");
assert.ok(!connectionSvg.includes('class="terrain-cell'), "neighbor checks can show while terrain colors are hidden");
assert.ok(connectionSvg.indexOf('class="terrain-connection') < connectionSvg.indexOf('class="trail-route"'),
  "neighbor edges draw under the player's trail");
assert.equal(element("terrainConnectionLegend").hidden, false, "enabling neighbor checks shows its legend");
assert.ok(element("terrainConnectionStatus").textContent.includes("通过 1 / 受阻 1") &&
  element("terrainConnectionStatus").textContent.includes("当前可显示 2 条"),
  "neighbor status counts currently displayable checked edges");
assert.ok(connectionSvg.includes("邻格直连检查 · 通过") && connectionSvg.includes("邻格直连检查 · 受阻"));
connectionFixture[1].passable = false;
run("renderTrail()");
assert.equal((element("trailSvg").innerHTML.match(/class="terrain-connection terrain-connection-passable"/g) || []).length, 0,
  "a neighbor updated to blocked suppresses its edge");
delete connectionFixture[1].passable;
run("renderTrail()");
assert.equal((element("trailSvg").innerHTML.match(/class="terrain-connection terrain-connection-passable"/g) || []).length, 0,
  "a neighbor updated to unknown suppresses its edge");
connectionFixture[1].passable = true;
element("terrainConnectionToggle").checked = false;
element("terrainConnectionToggle").listeners.change();
assert.ok(!element("trailSvg").innerHTML.includes('class="terrain-connection'), "the neighbor-check toggle hides checked edges");
assert.equal(element("terrainConnectionLegend").hidden, true, "the neighbor-check toggle hides its legend");
element("terrainToggle").checked = true;
element("terrainToggle").listeners.change();
run('trailState.mode="history";trailState.points=[{sequence:1,captured_at:1,x:0,z:0}];trailState.terrainTiles=[{x:0,z:0,tile:"GRASS",last_seen:1,last_sequence:1}];trailState.terrainAvailable=true;trailState.terrainTruncated=false;trailState.terrainError="";renderTrail()');
assert.ok(!element("trailSvg").innerHTML.includes("terrain-blocked"), "legacy replay tiles without passability stay unknown");
assert.ok(!element("trailSvg").innerHTML.includes("terrain-connection"), "legacy replay tiles without connections stay unknown");
assert.ok(element("terrainConnectionStatus").textContent.includes("0.4.0"), "legacy replay without connection checks prompts the collector update");
assert.ok(element("trailSvg").innerHTML.includes("未采集通行状态"), "legacy replay SVG title identifies unknown passability");
assert.ok(element("terrainStatus").textContent.includes("已知 0") && element("terrainStatus").textContent.includes("未知 1"),
  "legacy replay status counts passability as unknown");
run('trailState.mode="history";trailState.points=[{sequence:1,captured_at:1,x:0,z:0},{sequence:2,captured_at:2,x:10000,z:0}];trailState.terrainTiles=[{x:0,z:0,tile:"GRASS",last_seen:1,last_sequence:1,passable:false},{x:4,z:0,tile:"GRASS",last_seen:2,last_sequence:2}];trailState.terrainAvailable=true;trailState.terrainTruncated=false;trailState.terrainError="";renderTrail()');
const smallCellSvg = element("trailSvg").innerHTML;
const smallCell = smallCellSvg.match(/class="terrain-cell terrain-grass" x="([^"]+)" y="([^"]+)" width="([^"]+)" height="([^"]+)"/);
const smallSlash = smallCellSvg.match(/class="terrain-blocked" d="M([^ ]+) ([^L]+)L([^ ]+) ([^"]+)" style="stroke-width:([^p]+)px"/);
assert.ok(smallCell && smallSlash, "a distant trail still renders a small blocked-cell mark");
const [cellX, cellY, cellWidth] = [Number(smallCell[1]), Number(smallCell[2]), Number(smallCell[3])];
const centerX = cellX + cellWidth / 2, centerY = cellY + cellWidth / 2;
const slashPoints = [[Number(smallSlash[1]), Number(smallSlash[2])], [Number(smallSlash[3]), Number(smallSlash[4])]];
const slashStroke = Number(smallSlash[5]);
assert.ok(slashPoints.every(([x, y]) => Math.abs(x - centerX) + slashStroke / 2 < cellWidth / 2 &&
  Math.abs(y - centerY) + slashStroke / 2 < cellWidth / 2),
  "the blocked slash and its stroke stay inside its small cell and cannot mark a neighbor");
run('trailState.mode="idle";trailState.points=[];trailState.terrainTiles=[];trailState.terrainAvailable=false;trailState.terrainTruncated=false;trailState.terrainError="";renderTrail()');
const segmentLengths = JSON.parse(JSON.stringify(run(`splitTrailSegments([
  {sequence:1,captured_at:1,x:0,z:0}, {sequence:2,captured_at:6,x:64,z:0},
  {sequence:3,captured_at:11,x:65,z:0}, {sequence:4,captured_at:17,x:65,z:0},
  {sequence:5,captured_at:18,x:130,z:0}, {sequence:6,captured_at:18,x:131,z:0}
]).map(segment => segment.length)`)));
assert.deepEqual(segmentLengths, [3, 1, 1, 1], "five-second/64-unit edges connect; nonpositive time, long gaps, and jumps split segments");
run('trailState.points=[{sequence:1,captured_at:1,x:0,z:0},{sequence:2,captured_at:7,x:0,z:0},{sequence:3,captured_at:8,x:100,z:0}];trailState.mode="history";renderTrail()');
assert.equal((element("trailSvg").innerHTML.match(/class="trail-isolated"/g) || []).length, 3,
  "samples on either side of breaks remain visible as isolated points");
run('trailState.points=[];trailState.mode="idle";renderTrail()');
run('trailState.live={identity:null,id:null,localPoints:[],storedPoints:[],trimmed:false,localLandmarks:[],storedLandmarks:[],landmarksTruncated:false,landmarkError:""};trailState.mode="idle";state.liveRecording=null;');
context.liveLandmarkFrame = frame("sight-session", 4, null, "sight-world", {
  capturedAt: 100, x: 0, z: 0,
  landmarks: [
    {prefab: "panflute", x: 10, z: 20}, {prefab: "panflute", x: 10, z: 20},
    {prefab: "panflute", x: 11, z: 20}, {prefab: "moonbase", x: 10, z: 20}
  ]
}).snapshot;
run("recordLiveTrailSnapshot(liveLandmarkFrame)");
context.liveLandmarkFrame = frame("sight-session", 5, null, "sight-world", {
  capturedAt: 105, x: 1, z: 0,
  landmarks: [{prefab: "panflute", x: 10, z: 20}]
}).snapshot;
run("recordLiveTrailSnapshot(liveLandmarkFrame)");
let localSightings = JSON.parse(run("JSON.stringify(trailState.live.localLandmarks)"));
assert.equal(localSightings.length, 3, "exact prefab and coordinate repeats deduplicate while different locations remain separate");
const repeatedSighting = localSightings.find(item => item.prefab === "panflute" && item.x === 10);
assert.deepEqual({first: repeatedSighting.first_sequence, last: repeatedSighting.last_sequence,
  firstSeen: repeatedSighting.first_seen, lastSeen: repeatedSighting.last_seen}, {first: 4, last: 5, firstSeen: 100, lastSeen: 105});
context.liveLandmarkFrame = frame("new-session", 1, null, "sight-world", {
  capturedAt: 200, x: 2, z: 0, landmarks: [{prefab: "panflute", x: 99, z: 100}]
}).snapshot;
run("recordLiveTrailSnapshot(liveLandmarkFrame)");
localSightings = JSON.parse(run("JSON.stringify(trailState.live.localLandmarks)"));
assert.equal(localSightings.length, 1, "a new session does not carry remembered positions across sessions");
assert.equal(localSightings[0].x, 99);
run('trailState.live={identity:null,id:null,localPoints:[],storedPoints:[],trimmed:false,localLandmarks:[],storedLandmarks:[],landmarksTruncated:false,landmarkError:""};');
context.capSnapshot = {
  world_id: "cap-world", world_kind: "forest", session_id: "cap-session", sequence: 3, captured_at: 300,
  position: {x: 0, y: 0, z: 0},
  landmarks: Array.from({length: 501}, (_, x) => ({prefab: "panflute", x, z: 0}))
};
run("recordLiveTrailSnapshot(capSnapshot)");
const cappedLocalSightings = JSON.parse(run("JSON.stringify(trailState.live.localLandmarks)"));
assert.equal(cappedLocalSightings.length, 500, "live aggregation keeps at most 500 unique positions");
assert.equal(Math.min(...cappedLocalSightings.map(item => item.x)), 0);
assert.equal(Math.max(...cappedLocalSightings.map(item => item.x)), 499,
  "one-frame live overflow keeps the same deterministic first 500 as the backend");
assert.equal(run("trailState.live.landmarksTruncated"), true);

const validationSummary = replaySummary("9".repeat(64), {worldId: "validate-world", session: "validate-session"});
context.validationSummary = validationSummary;
context.validationPayload = trailPayload(validationSummary, []);
const legacyTrail = JSON.parse(JSON.stringify(run("validateTrailPayload(validationPayload, validationSummary)")));
assert.deepEqual(legacyTrail.landmarks, [], "version 1 historical trails without optional landmarks remain supported");
assert.equal(legacyTrail.landmarksTruncated, false);
assert.equal(legacyTrail.terrainTiles.length, 0, "older trail payloads without terrain remain valid");
assert.equal(legacyTrail.terrainAvailable, false);
assert.ok(!Object.hasOwn(legacyTrail.points[0] || {}, "player_anchor"), "legacy v1 trail points keep the anchor unknown");
const anchoredValidationPayload = trailPayload(validationSummary, [
  trailPoint(1, 10, 2, 3, {x: 2, z: 2, clear: false}),
  trailPoint(2, 11, 6, 3, {x: 6, z: 2, clear: true}),
  trailPoint(3, 12, 10, 3)
]);
context.validationPayload = anchoredValidationPayload;
const anchoredValidation = JSON.parse(run("JSON.stringify(validateTrailPayload(validationPayload, validationSummary))"));
assert.deepEqual(anchoredValidation.points.map(point => point.player_anchor), [
  {x: 2, z: 2, clear: false}, {x: 6, z: 2, clear: true}, undefined
], "trail point normalization retains both clear values and omits unknown anchors");
assert.ok(!Object.hasOwn(anchoredValidation.points[2], "player_anchor"));
context.validationPayload = trailPayload(validationSummary, [
  trailPoint(1, 10, 2, 3, undefined, -27.5), trailPoint(2, 11, 6, 3)
]);
const headedValidation = JSON.parse(run("JSON.stringify(validateTrailPayload(validationPayload, validationSummary))"));
assert.deepEqual(headedValidation.points.map(point => point.camera_heading), [-27.5, undefined],
  "historical trail normalization preserves a finite camera heading and leaves legacy headings absent");
assert.ok(!Object.hasOwn(headedValidation.points[1], "camera_heading"));
for (const invalidHeading of [null, "90", NaN, Infinity, -Infinity]) {
  context.invalidCameraHeading = invalidHeading;
  assert.equal(run("normalizeTrailPoint({sequence:1,captured_at:10,x:2,z:3,camera_heading:invalidCameraHeading}) === null"), true,
    "a non-finite or non-number optional camera heading rejects its trail point");
}
context.validationPayload = trailPayload(validationSummary, [{...trailPoint(1, 10, 2, 3), camera_heading: "90"}]);
assert.throws(() => run("validateTrailPayload(validationPayload, validationSummary)"), undefined,
  "an invalid saved camera heading cannot be inherited from another frame");
for (const invalidAnchor of [null, [], {x: 2, z: 2}, {x: 2, z: 2, clear: 0},
  {x: NaN, z: 2, clear: true}, {x: 2, z: Infinity, clear: true}, {x: 2, z: 2, clear: true, extra: 1}]) {
  context.validationPayload = trailPayload(validationSummary, [
    {...trailPoint(1, 10, 2, 3), player_anchor: invalidAnchor}
  ]);
  assert.throws(() => run("validateTrailPayload(validationPayload, validationSummary)"), undefined,
    "malformed historical anchors invalidate the trail point instead of inheriting an older value");
}
context.validationPayload = trailPayload(validationSummary, []);
const validTerrainPayload = trailPayload(validationSummary, [trailPoint(1, 10, 2, 3)], undefined, false,
  {tile_size: 4, tiles: [terrainCell(2, 3, "GRASS", 1, 10)], truncated: false});
context.validationPayload = validTerrainPayload;
const normalizedTerrainPayload = JSON.parse(run("JSON.stringify(validateTrailPayload(validationPayload, validationSummary))"));
assert.equal(normalizedTerrainPayload.terrainAvailable, true);
assert.deepEqual(normalizedTerrainPayload.terrainTiles, [terrainCell(2, 3, "GRASS", 1, 10)]);
const malformedTerrainPayload = trailPayload(validationSummary, [trailPoint(1, 10, 2, 3)], undefined, false,
  {tile_size: true, tiles: [], truncated: false});
context.validationPayload = malformedTerrainPayload;
const malformedTerrainResult = JSON.parse(run("JSON.stringify(validateTrailPayload(validationPayload, validationSummary))"));
assert.equal(malformedTerrainResult.points.length, 1, "bad optional terrain does not discard player trail points");
assert.ok(malformedTerrainResult.terrainError.includes("地皮"));
const malformedPassabilityPayload = trailPayload(validationSummary, [trailPoint(1, 10, 2, 3)], undefined, false,
  {tile_size: 4, tiles: [terrainCell(2, 3, "GRASS", 1, 10, null)], truncated: false});
context.validationPayload = malformedPassabilityPayload;
const malformedPassabilityResult = JSON.parse(run("JSON.stringify(validateTrailPayload(validationPayload, validationSummary))"));
assert.equal(malformedPassabilityResult.points.length, 1, "bad optional passability does not discard saved trail points");
assert.ok(malformedPassabilityResult.terrainError.includes("地皮"));
assert.equal(run('terrainCategory("__proto__")'), "other");
assert.equal(run('terrainCategory("constructor")'), "other");
context.terrainSnapshot = {sequence: 1, captured_at: 10, terrain: {tile_size: true, tiles: []}};
assert.throws(() => run("normalizeSnapshotTerrain(terrainSnapshot)"), undefined, "boolean tile_size is rejected for live snapshots");
context.terrainSnapshot = {sequence: 1, captured_at: 10, terrain: {tile_size: 4, tiles: [
  {x: 1, z: 2, tile: "GRASS"}, {x: 1, z: 2, tile: "FOREST"}
]}};
assert.throws(() => run("normalizeSnapshotTerrain(terrainSnapshot)"), undefined, "duplicate live snapshot coordinates invalidate only terrain");
context.terrainSnapshot = {sequence: 1, captured_at: 10, terrain: {tile_size: 4, tiles: [{x: 1, z: 2, tile: "   "}]}};
assert.throws(() => run("normalizeSnapshotTerrain(terrainSnapshot)"), undefined, "empty tile identifiers are rejected");
context.manyTerrain = Array.from({length: 2501}, (_, x) => terrainCell(x, 0, "GRASS", 9, x));
const cappedTerrain = JSON.parse(run("JSON.stringify(mergeTrailTerrain([], manyTerrain, false, false))"));
assert.equal(cappedTerrain.tiles.length, 2500);
assert.deepEqual([cappedTerrain.tiles[0].x, cappedTerrain.tiles[2499].x], [0, 2499], "terrain overflow keeps deterministic (-sequence,x,z) order");
assert.equal(cappedTerrain.truncated, true);
assert.equal(run("mergeTrailTerrain([manyTerrain[0]], [], true, false).truncated"), true, "terrain truncation stays sticky");
run('trailState.mode="history";trailState.points=[];trailState.terrainTiles=[];trailState.terrainAvailable=false;trailState.terrainError="";renderTrail()');
assert.ok(element("terrainStatus").textContent.includes("没有地皮数据"));
run('trailState.mode="idle";renderTrail()');
const malformedLandmarkPayload = trailPayload(validationSummary, [trailPoint(1, 10, 2, 3)], [
  {prefab: "panflute", x: Number.NaN, z: 4, first_seen: 1, last_seen: 2, first_sequence: 0, last_sequence: 1}
]);
context.validationPayload = malformedLandmarkPayload;
const malformedOptional = JSON.parse(JSON.stringify(run("validateTrailPayload(validationPayload, validationSummary)")));
assert.equal(malformedOptional.points.length, 1, "invalid optional landmark data does not discard the player trail");
assert.ok(malformedOptional.landmarkError.includes("格式无法识别"));
context.malformedOptional = malformedOptional;
run('state.result={directions:[{direction:"north"}]};liveEl.target.textContent="排箫已在附近 · 直线距离 4.0";trailState.error="";trailState.points=malformedOptional.points;trailState.landmarkError=malformedOptional.landmarkError;renderTrail()');
assert.ok(element("seenLandmarksStatus").textContent.includes("读取失败"));
assert.ok(!element("trailStatus").textContent.includes("读取失败"), "an optional landmark error stays in its own panel");
assert.equal(run("state.result.directions[0].direction"), "north");
assert.ok(element("liveTarget").textContent.includes("排箫已在附近"), "remembered sightings do not replace the current visible-target message");
const sameFrameSightings = Array.from({length: 501}, (_, x) => ({
  prefab: "panflute", x, z: 0, first_seen: 10, last_seen: 10, first_sequence: 4, last_sequence: 4
}));
context.validationPayload = trailPayload(validationSummary, [], sameFrameSightings, false);
const cappedSightings = JSON.parse(JSON.stringify(run("validateTrailPayload(validationPayload, validationSummary)")));
assert.equal(cappedSightings.landmarks.length, 500);
assert.deepEqual(cappedSightings.landmarks.map(item => item.x).sort((a, b) => a - b).slice(0, 2), [0, 1]);
assert.equal(Math.max(...cappedSightings.landmarks.map(item => item.x)), 499,
  "same-frame overflow retains the deterministic first 500 by prefab/x/z");
assert.equal(cappedSightings.landmarksTruncated, true);const mixedPrefabOverflow = Array.from({length: 499}, (_, x) => remembered("a", x, 0, 1, 1, 4, 4))
  .concat(Array.from({length: 3}, (_, x) => remembered("B", x, 10, 1, 1, 4, 4)));
context.validationPayload = trailPayload(validationSummary, [], mixedPrefabOverflow, false);
const mixedPrefabCapped = JSON.parse(JSON.stringify(run("validateTrailPayload(validationPayload, validationSummary)")));
assert.equal(mixedPrefabCapped.landmarks.length, 500);
assert.equal(mixedPrefabCapped.landmarks.filter(item => item.prefab === "B").length, 3,
  "ordinal prefab ordering matches the backend for mixed-case same-frame overflow");
assert.equal(mixedPrefabCapped.landmarks.filter(item => item.prefab === "a").length, 497);
assert.equal(Math.max(...mixedPrefabCapped.landmarks.filter(item => item.prefab === "a").map(item => item.x)), 496);
assert.equal(mixedPrefabCapped.landmarksTruncated, true);

run('state.target="panflute";trailState.mode="history";trailState.error="";trailState.landmarkError="";trailState.landmarksTruncated=false;trailState.points=[{sequence:8,captured_at:Date.now()/1000,x:0,z:0}];trailState.landmarks=[{prefab:"panflute",x:0,z:20,first_seen:Date.now()/1000-5,last_seen:Date.now()/1000-5,first_sequence:1,last_sequence:2},{prefab:"panflute",x:20,z:0,first_seen:Date.now()/1000-10,last_seen:Date.now()/1000-10,first_sequence:0,last_sequence:1},{prefab:"moonbase",x:500,z:500,first_seen:1,last_seen:2,first_sequence:1,last_sequence:2}];renderTrail()');
assert.ok(element("seenLandmarksStatus").textContent.includes("显示最近 2 / 2 处"));
assert.ok(element("seenLandmarksList").innerHTML.includes("panflute"));
assert.ok(!element("seenLandmarksList").innerHTML.includes("moonbase"), "the sightings list filters by the selected target");
assert.ok(element("seenLandmarksList").innerHTML.includes("最近看到"));
assert.ok(element("seenLandmarksList").innerHTML.includes("相对最新观测：北"));
assert.equal((element("trailSvg").innerHTML.match(/class="trail-landmark-marker"/g) || []).length, 3);
assert.ok(element("trailSvg").innerHTML.includes("已见目标"));
let targetChangeFetches = 0;
context.fetch = async () => { targetChangeFetches += 1; throw new Error("target change must not fetch"); };
element("targetSelect").value = "moonbase";
element("targetSelect").listeners.change();
assert.equal(targetChangeFetches, 0, "changing target immediately rerenders stored sightings without fetching a trail");
assert.ok(element("seenLandmarksList").innerHTML.includes("moonbase"));
assert.ok(!element("seenLandmarksList").innerHTML.includes("panflute"));
element("targetSelect").value = "pigking";
element("targetSelect").listeners.change();
assert.ok(element("seenLandmarksStatus").textContent.includes("暂未记录目标"));
context.injectedLandmark = remembered('<img src=x onerror=boom>', 1, 2, 1, 1, 1, 1);
run('state.target="<img src=x onerror=boom>";trailState.landmarks=[injectedLandmark];renderTrail()');
assert.ok(element("seenLandmarksList").innerHTML.includes("&lt;img"));
assert.ok(!element("seenLandmarksList").innerHTML.includes("<img"), "untrusted prefab names are escaped in the sightings list");
assert.ok(!element("trailSvg").innerHTML.includes("<img"), "untrusted prefab names never enter SVG markup");
element("targetSelect").value = "panflute";
element("targetSelect").listeners.change();

for (const field of ["id", "world_id", "world_kind", "session_id"]) {
  const payload = trailPayload(validationSummary, []);
  payload[field] = "wrong-" + field;
  context.validationSummary = validationSummary;
  context.validationPayload = payload;
  assert.throws(() => run("validateTrailPayload(validationPayload, validationSummary)"), undefined,
    "trail payload validates " + field);
}
element("recordName").value = "My world";
element("worldNote").value = "Exploration note";
run('state.activeRecordId="00000000-0000-4000-8000-000000000001";');
context.reply = frame();
run("applyLiveResult(reply)");
assert.equal(run("state.activeRecordId"), "00000000-0000-4000-8000-000000000001");
assert.equal(element("recordName").value, "My world");
assert.ok(element("livePosition").textContent.includes("12.0"));
assert.ok(element("liveTarget").textContent.includes("4.0"));
assert.equal(element("diagonalToggle").disabled, true);
const saved = JSON.parse(run("JSON.stringify(createRecordPayload())"));
assert.equal(saved.observation.current.prefab_counts.observed_custom_prefab, 2);
assert.equal(saved.observation.directions.north.tile_types[0], "CUSTOM_TILE");
context.reply = {status: "stale", snapshot: frame().snapshot};
run("applyLiveResult(reply)");
assert.equal(run("state.result"), null);
assert.equal(element("liveTarget").textContent, "");
assert.ok(element("resultsArea").innerHTML.includes("超过五秒"));
context.reply = frame("two", 1);
run("applyLiveResult(reply)");
assert.equal(run("state.activeRecordId"), null);
assert.equal(element("recordName").value, "");
context.reply = frame("two", 3);
run("applyLiveResult(reply)");
context.reply = frame("two", 2);
run("applyLiveResult(reply)");
assert.equal(run("state.result"), null);
assert.ok(element("liveStatus").textContent.includes("倒序"));
run('stopLive(); state.options.tile_types=["GRASS"]; state.options.prefabs=["grass"];');
context.loaded = saved.observation;
run('applyPayload(loaded,"saved live record",{id:"00000000-0000-4000-8000-000000000001",name:"Restored world",world_note:"saved note"})');
assert.equal(JSON.parse(run("JSON.stringify(createRecordPayload())")).observation.current.prefab_counts.observed_custom_prefab, 2);
run('live.following=true;state.result=null;');

function trailDestinationSyntheticEvent(type, x, z, key = "", preventDefault = () => {}) {
  const cell = {dataset: {terrainX: String(x), terrainZ: String(z)}};
  const event = {target: {closest(selector) {
    return selector === ".terrain-cell[data-terrain-x][data-terrain-z]" ? cell : null;
  }}, key, preventDefault};
  element("trailSvg").listeners[type](event);
}
function landmarkAttributes(markup, index) {
  const escapedIndex = String(index).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = markup.match(new RegExp('data-landmark-index="' + escapedIndex + '" data-landmark-revision="(\\d+)" data-landmark-prefab="([^"]*)" data-landmark-x="([^"]*)" data-landmark-z="([^"]*)"'));
  assert.ok(match, "landmark " + index + " has a current interactive event identity");
  return {index, revision: Number(match[1]), prefab: match[2], x: match[3], z: match[4]};
}
function landmarkListButton(index) {
  const markup = element("seenLandmarksList").innerHTML;
  const buttons = [...markup.matchAll(/<button class="button seen-landmark-go"[\s\S]*?<\/button>/g)].map(match => match[0]);
  const button = buttons.find(item => item.includes('data-landmark-index="' + index + '"'));
  assert.ok(button, "the sightings list contains button " + index);
  return button;
}
function landmarkListSyntheticClick(index, forcedDisabled = false) {
  const buttonMarkup = landmarkListButton(index);
  const attributes = landmarkAttributes(buttonMarkup, index);
  const button = {dataset: {landmarkIndex: String(index), landmarkRevision: String(attributes.revision),
    landmarkPrefab: attributes.prefab, landmarkX: attributes.x, landmarkZ: attributes.z},
    disabled: forcedDisabled || /\sdisabled>/.test(buttonMarkup)};
  const event = {target: {closest(selector) {
    return selector === "button.seen-landmark-go[data-landmark-index][data-landmark-revision]" ? button : null;
  }}};
  element("seenLandmarksList").listeners.click(event);
}
function nearestTargetSyntheticClick() {
  element("nearestSeenTargetButton").listeners.click({target: element("nearestSeenTargetButton")});
}
function landmarkMapSyntheticEvent(type, attributes, key = "", preventDefault = () => {}) {
  const marker = {dataset: {landmarkIndex: String(attributes.index), landmarkRevision: String(attributes.revision),
    landmarkPrefab: attributes.prefab, landmarkX: String(attributes.x), landmarkZ: String(attributes.z)}};
  const event = {target: {closest(selector) {
    return selector === ".trail-landmark-marker[data-landmark-index][data-landmark-revision]" ? marker : null;
  }}, key, preventDefault};
  element("trailSvg").listeners[type](event);
}
(async () => {
  let resolve;
  context.fetch = () => new Promise(done => { resolve = done; });
  const pending = run("pollLive()");
  run("stopLive()");
  resolve(apiResponse(frame("two", 4)));
  await pending;
  assert.equal(run("state.result"), null);
  assert.equal(element("diagonalToggle").disabled, false);
  assert.equal(run("live.timer"), null);

  let historyCalls = 0;
  let historyPayload = [];
  context.fetch = async url => {
    if (url !== "/api/explorations") throw new Error("unexpected fetch " + url);
    historyCalls += 1;
    return apiResponse({explorations: historyPayload});
  };
  async function settle() { await new Promise(resolveTurn => setImmediate(resolveTurn)); }

  const firstId = "a".repeat(64);
  const first = replaySummary(firstId, {session: "two"});
  historyPayload = [first];
  context.reply = frame("two", 4, first);
  run("applyLiveResult(reply)");
  await settle();
  assert.equal(element("liveReplayLink").href, "/api/explorations/" + firstId);
  assert.equal(element("liveReplayLink").hidden, false);
  assert.ok(element("liveReplayLink").textContent.includes("第 1 段"));
  assert.ok(element("liveRecordingStatus").textContent.includes("已自动记录"));
  assert.ok(element("liveRecordingStatus").textContent.includes("第 1 段"));
  assert.ok(element("liveRecordingStatus").textContent.includes("1 帧"));

  context.reply = frame("two", 5, {...first, frame_count: 2});
  run("applyLiveResult(reply)");
  await settle();
  assert.equal(historyCalls, 1, "one replay must not trigger a list request on every frame");

  const limitId = "b".repeat(64);
  const limited = replaySummary(limitId, {session: "two", frames: Number.MAX_SAFE_INTEGER, status: "limit_reached"});
  historyPayload = [limited, first];
  context.reply = frame("two", 6, limited);
  run("applyLiveResult(reply)");
  await settle();
  assert.equal(element("liveReplayLink").href, "/api/explorations/" + limitId);
  assert.ok(element("liveRecordingStatus").textContent.includes("本段已满"));
  assert.ok(element("liveRecordingStatus").textContent.includes("下一帧将自动开始新段"));
  assert.ok(element("liveRecordingStatus").textContent.includes(String(Number.MAX_SAFE_INTEGER)));

  const errorId = "c".repeat(64);
  const failed = replaySummary(errorId, {session: "two", frames: Number.MAX_SAFE_INTEGER, status: "error", error: "disk full"});
  historyPayload = [failed, limited, first];
  context.reply = frame("two", 7, failed);
  run("applyLiveResult(reply)");
  await settle();
  assert.equal(run("state.result.directions[0].direction"), "north");
  assert.ok(element("liveStatus").textContent.includes("实时更新"));
  assert.ok(element("liveRecordingStatus").textContent.includes("disk full"));

  const noIdError = {status: "error", error: "disk unavailable"};
  context.reply = frame("two", 8, noIdError);
  run("applyLiveResult(reply)");
  assert.equal(run("state.result.directions[0].direction"), "north");
  assert.ok(element("liveStatus").textContent.includes("实时更新"));
  assert.ok(element("liveRecordingStatus").textContent.includes("disk unavailable"));
  assert.ok(!element("liveRecordingStatus").textContent.includes("格式无法识别"));
  assert.equal(element("liveReplayLink").href, "/api/explorations/" + errorId);
  assert.equal(element("liveReplayLink").hidden, false);

  context.reply = {status: "stale", snapshot: frame("two", 8).snapshot};
  run("applyLiveResult(reply)");
  assert.equal(run("state.result"), null);
  assert.equal(element("liveReplayLink").href, "/api/explorations/" + errorId);
  assert.equal(element("liveReplayLink").hidden, false);
  assert.ok(element("liveRecordingStatus").textContent.includes("world-a"));

  context.reply = {status: "waiting"};
  run("applyLiveResult(reply)");
  assert.equal(run("state.result"), null);
  assert.equal(element("liveTarget").textContent, "");
  assert.equal(element("liveReplayLink").href, "/api/explorations/" + errorId);
  assert.ok(element("liveRecordingStatus").textContent.includes("world-a"));

  const oldLink = element("liveReplayLink").href;
  context.reply = frame("two", 9, replaySummary("../unsafe", {session: "two"}));
  run("applyLiveResult(reply)");
  assert.equal(element("liveReplayLink").href, oldLink, "an unsafe ID must not replace the prior download link");
  assert.ok(element("liveRecordingStatus").textContent.includes("格式无法识别"));

  const reorderedId = "e".repeat(64);
  context.reply = frame("two", 8, replaySummary(reorderedId, {session: "two"}));
  run("applyLiveResult(reply)");
  assert.equal(element("liveReplayLink").href, oldLink, "an out-of-order frame must not replace the replay link");
  assert.equal(run("state.liveRecording.id"), errorId);

  run('state.activeRecordId="00000000-0000-4000-8000-000000000001";');
  const worldId = "d".repeat(64);
  const newWorld = replaySummary(worldId, {session: "three", worldId: "world-b"});
  historyPayload = [newWorld, failed, limited, first];
  context.reply = frame("three", 1, newWorld, "world-b");
  run("applyLiveResult(reply)");
  await settle();
  assert.equal(element("liveReplayLink").href, "/api/explorations/" + worldId);
  assert.ok(element("liveRecordingStatus").textContent.includes("world-b"));
  assert.equal(run("state.activeRecordId"), null, "a new world session clears the editable saved-record association");

  context.reply = frame("four", 1, noIdError, "world-b");
  run("applyLiveResult(reply)");
  assert.equal(run("state.result.directions[0].direction"), "north");
  assert.ok(element("liveStatus").textContent.includes("实时更新"));
  assert.ok(element("liveRecordingStatus").textContent.includes("disk unavailable"));
  assert.equal(element("liveReplayLink").hidden, true, "a session change must hide the prior session download");
  assert.equal(element("liveReplayLink").href, "");
  assert.ok(element("explorationList").innerHTML.includes("/api/explorations/" + worldId));

  context.reply = frame("five", 1, null, "world-c");
  run("applyLiveResult(reply)");
  assert.equal(element("liveReplayLink").hidden, true, "a new world without a recording summary must not retain the old link");
  assert.ok(element("liveRecordingStatus").textContent.includes("等待当前会话"));

  const persisted = Array.from({length: 22}, (_, index) => replaySummary(
    index.toString(16).padStart(64, "0"),
    {worldId: index === 0 ? '<img src=x onerror="x">' : "saved-world-" + index, frames: index + 1,
      ...(index === 0 ? {} : {segment: index + 1})}
  ));
  persisted.push({...persisted[0], id: "../../bad"});
  context.fetch = async url => {
    if (url === "/api/explorations") return apiResponse({explorations: persisted});
    throw new Error("unexpected fetch " + url);
  };
  await run('refreshExplorations({quiet:true})');
  assert.equal(run("state.explorations.length"), 22, "the client retains every normalized replay summary");
  assert.ok(element("explorationList").innerHTML.includes("/api/explorations/" + persisted[0].id));
  assert.ok(!element("explorationList").innerHTML.includes(persisted[10].id), "the initial page shows ten replays");
  assert.ok(element("explorationList").innerHTML.includes("&lt;img"));
  assert.ok(!element("explorationList").innerHTML.includes("<img"));
  assert.ok(!element("explorationList").innerHTML.includes("../../bad"));
  assert.ok(element("explorationsStatus").textContent.includes("读取到 22 条有效回放，显示最近 10 条。"));
  assert.ok(element("explorationsStatus").textContent.includes("已忽略 1 条格式不完整的项目。"));
  assert.equal(element("showMoreExplorationsButton").hidden, false);
  element("showMoreExplorationsButton").listeners.click();
  assert.ok(element("explorationList").innerHTML.includes(persisted[19].id), "one click reveals ten more replays");
  assert.ok(!element("explorationList").innerHTML.includes(persisted[20].id));
  assert.ok(element("explorationList").innerHTML.includes("第 20 段"));
  await run('refreshExplorations({quiet:true})');
  assert.equal(run("state.explorations.length"), 22);
  assert.equal(run("state.explorationsVisibleCount"), 20, "refresh keeps the useful visible count");
  assert.ok(element("explorationList").innerHTML.includes(persisted[19].id));
  assert.ok(!element("explorationList").innerHTML.includes(persisted[20].id));
  element("showMoreExplorationsButton").listeners.click();
  assert.ok(element("explorationList").innerHTML.includes(persisted[21].id), "another click reveals the remaining older parts");
  assert.ok(element("explorationList").innerHTML.includes('/api/explorations/' + persisted[21].id));
  assert.ok(element("explorationList").innerHTML.includes("第 22 段"));
  assert.equal(element("showMoreExplorationsButton").hidden, true);
  context.fetch = async url => {
    if (url !== "/api/explorations/" + persisted[21].id + "/trail") throw new Error("unexpected old replay fetch " + url);
    return apiResponse(trailPayload(persisted[21], [trailPoint(4, 4, 40, 50)]));
  };
  const olderOpenButton = {dataset: {explorationId: persisted[21].id}};
  element("explorationList").listeners.click({target: {closest: selector => selector === "button.trail-open[data-exploration-id]" ? olderOpenButton : null}});
  await settle();
  assert.equal(run("trailState.id"), persisted[21].id, "an older segment opens its own trail");
  assert.ok(element("trailPlaybackStatus").textContent.includes("第 22 段"));

  context.fetch = async url => {
    if (url !== "/api/explorations") throw new Error("unexpected fetch " + url);
    return apiResponse({explorations: [{...persisted[0], id: "e".repeat(64), started_at: undefined, created_at: "2026-10-14T10:00:00.000Z"}]});
  };
  await run('refreshExplorations({quiet:true})');
  assert.equal(run("state.explorations.length"), 0, "created_at must not substitute for started_at");
  assert.ok(element("explorationsStatus").textContent.includes("格式不完整"));

  assert.ok(appHtml.includes('id="importExplorationButton"') && appHtml.includes('id="explorationImportFile"'));
  assert.ok(appHtml.includes('accept=".jsonl,application/x-ndjson"'), "replay import uses its own JSONL picker");
  assert.ok(appHtml.includes('id="viewImportedExplorationButton"'), "the most recently imported replay has a dedicated view action");
  let rejectedImportRequests = 0;
  context.fetch = async () => { rejectedImportRequests += 1; throw new Error("size checks should happen before fetch"); };
  context.emptyImportFile = {name: "empty.jsonl", size: 0};
  context.largeImportFile = {name: "large.jsonl", size: 32 * 1024 * 1024 + 1};
  assert.equal(await run("importExplorationFile(emptyImportFile)"), null);
  assert.ok(element("explorationImportStatus").textContent.includes("空文件"));
  assert.equal(await run("importExplorationFile(largeImportFile)"), null);
  assert.ok(element("explorationImportStatus").textContent.includes("32 MiB"));
  assert.equal(rejectedImportRequests, 0, "empty and oversized files are rejected before upload");

  const importedPartOne = replaySummary("f".repeat(64), {worldId: "imported-world", session: "imported-session", frames: 8});
  const importedOnce = replaySummary("0".repeat(64), {worldId: "imported-world", session: "imported-session", frames: 2, segment: 2});
  const rawImportFile = {name: "run.jsonl", size: 37};
  const importRequests = [];
  function importResponse(status, summary, created) {
    return {ok: status >= 200 && status < 300, status, json: async () => ({exploration: summary, created})};
  }
  context.fetch = async (url, options = {}) => {
    if (url === "/api/explorations/import") {
      importRequests.push({url, options});
      return importResponse(201, importedOnce, true);
    }
    if (url === "/api/explorations/" + importedOnce.id + "/trail") {
      return apiResponse(trailPayload(importedOnce, [trailPoint(0, 10, 5, 9)]));
    }
    throw new Error("unexpected import fetch " + url);
  };
  run("state.explorations=" + JSON.stringify([importedPartOne]) + ';state.explorationsVisibleCount=10;renderExplorations();el.explorationsStatus.textContent="还没有探索回放。";');
  run('state.target="moonbase";state.seed="41";el.target.value="moonbase";el.seed.value="41";el.recordName.value="keep this name";el.worldNote.value="keep this world";state.dirs.north.note="keep observation";live.following=true;liveEl.follow.checked=true;trailState.mode="live";trailState.revision++;trailState.id=null;trailState.identity=null;trailState.summary=null;');
  context.rawImportFile = rawImportFile;
  const importedResult = await run("importExplorationFile(rawImportFile)");
  assert.equal(importedResult.id, importedOnce.id);
  assert.equal(run("state.explorations.length"), 2, "importing a sibling segment keeps the existing part");
  assert.ok(!element("explorationsStatus").textContent.includes("还没有探索回放"),
    "importing clears the stale no-replays status");
  assert.ok(element("explorationsStatus").textContent.includes("显示 2 条回放") &&
    element("explorationsStatus").textContent.includes("含刚导入的回放"),
    "the list status reports the imported replay and its visible count");
  assert.ok(element("explorationList").innerHTML.includes("第 1 段") &&
    element("explorationList").innerHTML.includes("第 2 段"), "sibling imports show their segment labels");
  assert.ok(element("explorationList").innerHTML.includes('/api/explorations/' + importedPartOne.id) &&
    element("explorationList").innerHTML.includes('/api/explorations/' + importedOnce.id),
    "sibling segments keep separate download URLs");
  assert.equal(importRequests.length, 1);
  assert.equal(importRequests[0].options.method, "POST");
  assert.equal(importRequests[0].options.headers["Accept"], "application/json");
  assert.equal(importRequests[0].options.headers["Content-Type"], "application/x-ndjson");
  assert.equal(importRequests[0].options.body, rawImportFile, "the original File/Blob object is sent without text decoding or re-encoding");
  assert.equal(run("trailState.mode"), "history", "a successful import opens its trail when the view revision is unchanged");
  assert.equal(run("trailState.id"), importedOnce.id);
  assert.equal(run("live.following"), false, "opening an imported trail pauses live following");
  assert.equal(element("viewImportedExplorationButton").hidden, false);
  assert.equal(run("state.target"), "moonbase");
  assert.equal(run("state.seed"), "41");
  assert.equal(element("recordName").value, "keep this name");
  assert.equal(element("worldNote").value, "keep this world");
  assert.equal(run("state.dirs.north.note"), "keep observation");
  await settle();
  assert.equal(run("trailState.points[0].x"), 5);

  context.fetch = async (url, options = {}) => {
    if (url === "/api/explorations/import") {
      assert.equal(options.body, rawImportFile, "a repeat import also sends its original file object");
      return importResponse(200, importedOnce, false);
    }
    if (url === "/api/explorations/" + importedOnce.id + "/trail") {
      return apiResponse(trailPayload(importedOnce, [trailPoint(0, 10, 5, 9)]));
    }
    throw new Error("unexpected duplicate import fetch " + url);
  };
  const duplicateResult = await run("importExplorationFile(rawImportFile)");
  assert.equal(duplicateResult.id, importedOnce.id);
  assert.ok(element("explorationImportStatus").textContent.includes("已存在"), "HTTP 200 duplicate imports are successful");
  assert.equal(run('state.explorations.filter(item => item.id === "' + importedOnce.id + '").length'), 1);

  const liveBeforeFailure = replaySummary("8".repeat(64), {worldId: "live-import-world", session: "live-import-session"});
  run('live.following=true;liveEl.follow.checked=true;trailState.mode="live";trailState.id="' + liveBeforeFailure.id +
    '";trailState.revision++;trailState.identity=explorationReplayIdentity(' + JSON.stringify(liveBeforeFailure) + ');trailState.summary=' +
    JSON.stringify(liveBeforeFailure) + ';state.target="panflute";state.seed="99";el.target.value="panflute";el.seed.value="99";' +
    'el.recordName.value="record preserved";el.worldNote.value="note preserved";el.file.value="manual-observations.json";');
  element("fileInput").files = [{name: "manual-observations.json"}];
  const failedViewRevision = run("trailState.revision");
  const failedExplorations = JSON.parse(run("JSON.stringify(state.explorations.map(item=>item.id))"));
  context.failImportFile = {name: '<img src=x onerror="bad">.jsonl', size: 20};
  context.fetch = async (url) => {
    assert.equal(url, "/api/explorations/import");
    return {ok: false, status: 409, json: async () => ({error: '<b>世界冲突</b>'})};
  };
  assert.equal(await run("importExplorationFile(failImportFile)"), null);
  assert.equal(run("live.following"), true, "a failed import leaves live following active");
  assert.equal(run("trailState.mode"), "live");
  assert.equal(run("trailState.id"), liveBeforeFailure.id);
  assert.equal(run("trailState.revision"), failedViewRevision);
  assert.equal(element("liveFollow").checked, true);
  assert.equal(element("fileInput").value, "manual-observations.json");
  assert.equal(element("fileInput").files[0].name, "manual-observations.json");
  assert.equal(run("state.target"), "panflute");
  assert.equal(run("state.seed"), "99");
  assert.equal(element("recordName").value, "record preserved");
  assert.equal(element("worldNote").value, "note preserved");
  assert.deepEqual(JSON.parse(run("JSON.stringify(state.explorations.map(item=>item.id))")), failedExplorations);
  assert.ok(element("explorationImportStatus").textContent.includes("<b>世界冲突</b>"),
    "service errors and filenames are written as text, never treated as HTML");

  const lateImport = replaySummary("6".repeat(64), {worldId: "late-import", session: "late-import-session", frames: 3});
  const viewChosenDuringUpload = replaySummary("7".repeat(64), {worldId: "chosen-world", session: "chosen-session"});
  let resolveLateImport;
  context.lateImportFile = {name: "late.jsonl", size: 48};
  context.fetch = (url, options = {}) => {
    if (url === "/api/explorations/import") {
      return new Promise(resolve => { resolveLateImport = () => resolve(importResponse(201, lateImport, true)); });
    }
    if (url === "/api/explorations/" + viewChosenDuringUpload.id + "/trail") {
      return Promise.resolve(apiResponse(trailPayload(viewChosenDuringUpload, [trailPoint(0, 10, 30, 40)])));
    }
    if (url === "/api/explorations/" + lateImport.id + "/trail") {
      return Promise.resolve(apiResponse(trailPayload(lateImport, [trailPoint(0, 10, 60, 70)])));
    }
    throw new Error("unexpected late import fetch " + url);
  };
  const lateImportPending = run("importExplorationFile(lateImportFile)");
  const chosenDuringUpload = run("openExplorationTrail(" + JSON.stringify(viewChosenDuringUpload) + ")");
  assert.equal(chosenDuringUpload, true);
  const chosenViewRevision = run("trailState.revision");
  resolveLateImport();
  assert.equal((await lateImportPending).id, lateImport.id);
  assert.equal(run("trailState.id"), viewChosenDuringUpload.id, "a late successful import does not take over a newer view");
  assert.equal(run("trailState.revision"), chosenViewRevision);
  assert.ok(element("explorationImportStatus").textContent.includes("当前视图已变化"));
  const latestTenWithoutImport = Array.from({length: 10}, (_, index) =>
    replaySummary((index + 10).toString(16).padStart(64, "0"), {worldId: "recent-" + index}));
  run("state.explorations=" + JSON.stringify(latestTenWithoutImport) + ";renderExplorations()");
  assert.equal(run('state.explorations.some(item => item.id === "' + lateImport.id + '")'), false,
    "the imported replay can be absent from the latest ten");
  assert.ok(!element("explorationList").innerHTML.includes(lateImport.id));
  element("viewImportedExplorationButton").listeners.click();
  assert.equal(run("trailState.id"), lateImport.id,
    "the dedicated action opens the imported summary even when it is not in the recent list");
  await settle();

  const repeatedFile = {name: "same-file.jsonl", size: 12};
  const repeatedSummary = replaySummary("a".repeat(64), {worldId: "repeat-world", session: "repeat-session"});
  const repeatedBodies = [];
  let resolveRepeatedFirst;
  let repeatedUploadCount = 0;
  context.fetch = (url, options = {}) => {
    if (url === "/api/explorations/import") {
      repeatedBodies.push(options.body);
      repeatedUploadCount += 1;
      if (repeatedUploadCount === 1) {
        return new Promise(resolve => { resolveRepeatedFirst = () => resolve(importResponse(200, repeatedSummary, false)); });
      }
      return Promise.resolve(importResponse(200, repeatedSummary, false));
    }
    if (url === "/api/explorations/" + repeatedSummary.id + "/trail") {
      return Promise.resolve(apiResponse(trailPayload(repeatedSummary, [trailPoint(0, 10, 11, 12)])));
    }
    throw new Error("unexpected repeated import fetch " + url);
  };
  element("importExplorationButton").listeners.click();
  assert.equal(element("explorationImportFile").clickCount, 1, "the import button opens its separate file picker");
  context.repeatedFile = repeatedFile;
  element("explorationImportFile").files = [repeatedFile];
  element("explorationImportFile").value = "selected-file";
  element("explorationImportFile").listeners.change();
  assert.equal(element("explorationImportFile").value, "", "the picker clears its value after selection");
  assert.equal(run("state.importingExploration"), true);
  assert.equal(await run("importExplorationFile(repeatedFile)"), null, "a concurrent second upload is ignored");
  assert.equal(repeatedUploadCount, 1, "only one upload starts at a time");
  resolveRepeatedFirst();
  await settle();
  assert.equal(element("importExplorationButton").disabled, false);
  assert.equal(repeatedBodies[0], repeatedFile);
  element("explorationImportFile").files = [repeatedFile];
  element("explorationImportFile").value = "selected-file";
  element("explorationImportFile").listeners.change();
  assert.equal(element("explorationImportFile").value, "", "the same file can be selected again after completion");
  await settle();
  assert.equal(repeatedUploadCount, 2);
  assert.equal(repeatedBodies[1], repeatedFile);

  const refreshRaceImport = replaySummary("b".repeat(64), {worldId: "refresh-race", session: "refresh-session"});
  const staleListSummary = replaySummary("c".repeat(64), {worldId: "old-list"});
  let resolveStaleImportList;
  let raceListRequests = 0;
  context.fetch = (url, options = {}) => {
    if (url === "/api/explorations") {
      raceListRequests += 1;
      if (raceListRequests === 1) {
        return new Promise(resolve => { resolveStaleImportList = () => resolve(apiResponse({explorations: [staleListSummary]})); });
      }
      return Promise.resolve(apiResponse({explorations: [refreshRaceImport, staleListSummary]}));
    }
    if (url === "/api/explorations/import") return Promise.resolve(importResponse(201, refreshRaceImport, true));
    if (url === "/api/explorations/" + refreshRaceImport.id + "/trail") {
      return Promise.resolve(apiResponse(trailPayload(refreshRaceImport, [trailPoint(0, 10, 1, 2)])));
    }
    throw new Error("unexpected refresh race fetch " + url);
  };
  const pendingOldList = run('refreshExplorations({quiet:true})');
  const racedImport = await run("importExplorationFile(" + JSON.stringify({name: "race.jsonl", size: 10}) + ")");
  assert.equal(racedImport.id, refreshRaceImport.id);
  resolveStaleImportList();
  await pendingOldList;
  await settle();
  assert.ok(raceListRequests >= 2, "a refresh racing with import is repeated after the stale response");
  assert.ok(element("explorationsStatus").textContent.includes("共 2 条有效回放。"),
    "the refresh following an import updates the list count instead of restoring an empty-list status");
  assert.equal(run('state.explorations.some(item => item.id === "' + refreshRaceImport.id + '")'), true,
    "a pre-import refresh response cannot remove the imported replay");

  const liveTrailId = "1".repeat(64);
  const liveTrailSummary = replaySummary(liveTrailId, {worldId: "trail-world", session: "trail-session", frames: 3});
  run(`trailState.mode="idle";trailState.revision++;trailState.id=null;trailState.identity=null;trailState.summary=null;trailState.points=[];trailState.error="";trailState.loading=false;trailState.trimmed=false;trailState.requests.clear();trailState.live={identity:null,id:null,localPoints:[],storedPoints:[],trimmed:false,localLandmarks:[],storedLandmarks:[],landmarksTruncated:false,landmarkError:""};trailState.landmarks=[];trailState.landmarksTruncated=false;trailState.landmarkError="";state.liveRecording=null;state.explorations=[${JSON.stringify(liveTrailSummary)}];state.explorationIdsSeen.add("${liveTrailId}");live.following=true;liveEl.follow.checked=true;live.key=null;live.sequence=0;resumeLiveTrailView();`);
  let resolveLiveTrail;
  let trailCalls = 0;
  context.fetch = url => {
    if (url !== "/api/explorations/" + liveTrailId + "/trail") throw new Error("unexpected fetch " + url);
    trailCalls += 1;
    return new Promise(resolve => { resolveLiveTrail = resolve; });
  };
  context.reply = frame("trail-session", 1, liveTrailSummary, "trail-world", {x: 1, z: 1, capturedAt: 100,
    landmarks: [{prefab: "panflute", x: 1, z: 1}], terrain: {tile_size: 4, tiles: [{x: 4, z: 1, tile: "GRASS", passable: true, connections: {east: true}}]}});
  run("applyLiveResult(reply)");
  context.reply = frame("trail-session", 2, {...liveTrailSummary, frame_count: 2}, "trail-world", {x: 2, z: 1, capturedAt: 101,
    landmarks: [{prefab: "panflute", x: 1, z: 1}, {prefab: "panflute", x: 2, z: 1}],
    terrain: {tile_size: 4, tiles: [{x: 4, z: 1, tile: "FOREST", passable: true, connections: {east: false}}]}});
  run("applyLiveResult(reply)");
  assert.equal(run("trailState.live.localTerrain[0].passable"), true, "live trail retains passable=true");
  assert.deepEqual(JSON.parse(run("JSON.stringify(trailState.live.localTerrain[0].connections)")), {east: false},
    "live trail retains false connection checks and drops omitted directions");
  context.reply = frame("trail-session", 3, liveTrailSummary, "trail-world", {x: 3, z: 1, capturedAt: 102,
    terrain: {tile_size: 4, tiles: [{x: 4, z: 1, tile: "ROCKY"}]}});
  run("applyLiveResult(reply)");
  assert.equal(trailCalls, 1, "live updates append locally without a journal request per frame");
  assert.equal(run("trailState.live.localPoints.length"), 3);
  resolveLiveTrail(apiResponse(trailPayload(liveTrailSummary, [
    trailPoint(0, 99, 0, 0), trailPoint(2, 101, 222, 222)
  ], [
    remembered("panflute", 1, 1, 0, 1, 99, 100),
    remembered("panflute", 9, 9, 0, 0, 99, 99)
  ], false, {tile_size: 4, tiles: [terrainCell(4, 1, "MARSH", 1, 99, false, {east: true, north: false}), terrainCell(20, 1, "OCEAN", 0, 99)], truncated: false})));
  await settle();
  const mergedLivePoints = JSON.parse(run("JSON.stringify(trailState.points)"));
  assert.deepEqual(mergedLivePoints.map(point => point.sequence), [0, 1, 2, 3]);
  assert.deepEqual({x: mergedLivePoints[2].x, z: mergedLivePoints[2].z}, {x: 2, z: 1}, "accepted local points win duplicate sequences");
  const mergedLiveLandmarks = JSON.parse(run("JSON.stringify(trailState.landmarks)"));
  const mergedPosition = mergedLiveLandmarks.find(item => item.prefab === "panflute" && item.x === 1);
  assert.deepEqual({first: mergedPosition.first_sequence, last: mergedPosition.last_sequence,
    firstSeen: mergedPosition.first_seen, lastSeen: mergedPosition.last_seen}, {first: 0, last: 2, firstSeen: 99, lastSeen: 101},
    "historical and subsequently accepted live sightings merge first/last sequence endpoints");
  assert.ok(mergedLiveLandmarks.some(item => item.x === 2) && mergedLiveLandmarks.some(item => item.x === 9));
  const mergedLiveTerrain = JSON.parse(run("JSON.stringify(trailState.terrainTiles)"));
  const terrainAtFour = mergedLiveTerrain.find(item => item.x === 4 && item.z === 1);
  assert.deepEqual({tile: terrainAtFour.tile, sequence: terrainAtFour.last_sequence}, {tile: "ROCKY", sequence: 3},
    "newer local terrain wins over stored history at the same coordinate");
  assert.ok(!Object.hasOwn(terrainAtFour, "passable"),
    "newer local unknown passability clears an older stored blocked result during merging");
  assert.ok(!Object.hasOwn(terrainAtFour, "connections"),
    "newer local terrain without connections clears an older stored dictionary during merging");
  assert.ok(mergedLiveTerrain.some(item => item.x === 20 && item.tile === "OCEAN"));
  context.reply = frame("trail-session", 3, {...liveTrailSummary, frame_count: 3}, "trail-world", {x: 9, z: 1, capturedAt: 102});
  run("applyLiveResult(reply)");
  assert.equal(run("trailState.live.localPoints.length"), 3, "local trail points deduplicate by sequence");
  assert.equal(trailCalls, 1);

  const raceA = replaySummary("2".repeat(64), {worldId: "race-a", session: "same-session", frames: 1});
  const raceB = replaySummary("3".repeat(64), {worldId: "race-b", session: "same-session", frames: 1});
  const pendingTrails = new Map();
  const trailCallCounts = new Map();
  context.fetch = url => {
    const match = url.match(/^\/api\/explorations\/([a-f0-9]{64})\/trail$/);
    if (!match) throw new Error("unexpected fetch " + url);
    const id = match[1];
    trailCallCounts.set(id, (trailCallCounts.get(id) || 0) + 1);
    return new Promise(resolve => pendingTrails.set(id, resolve));
  };
  context.reply = frame("same-session", 1, raceA, "race-a", {x: 500, z: 0, capturedAt: 200,
    landmarks: [{prefab: "panflute", x: 500, z: 0}], terrain: {tile_size: 4, tiles: [{x: 500, z: 0, tile: "GRASS", passable: false, connections: {east: true}}]}});
  run("applyLiveResult(reply)");
  context.reply = frame("same-session", 1, raceB, "race-b", {x: 50, z: 0, capturedAt: 200,
    player_anchor: {x: 50, z: 0, clear: false},
    landmarks: [{prefab: "panflute", x: 50, z: 0}], terrain: {tile_size: 4, tiles: [{x: 50, z: 0, tile: "MARSH", passable: false, connections: {east: false}}]}});
  run("applyLiveResult(reply)");
  assert.equal(run("trailState.identity"), "race-b\u0000forest\u0000same-session");
  pendingTrails.get(raceA.id)(apiResponse(trailPayload(raceA, [trailPoint(0, 1, 500, 0)], [remembered("panflute", 500, 0, 0, 0)], false,
    {tile_size: 4, tiles: [terrainCell(500, 0, "GRASS", 0, 1, false, {east: true})], truncated: false})));
  await settle();
  assert.equal(run("trailState.id"), raceB.id, "late world trail responses cannot replace the active world");
  assert.ok(JSON.parse(run("JSON.stringify(trailState.points)")).every(point => point.x !== 500));
  assert.ok(JSON.parse(run("JSON.stringify(trailState.landmarks)")).every(item => item.x !== 500),
    "a late response from another world cannot replace remembered sightings");
  assert.ok(JSON.parse(run("JSON.stringify(trailState.terrainTiles)")).every(item => item.x !== 500),
    "a late response from another world cannot replace observed terrain");
  assert.deepEqual(JSON.parse(run("JSON.stringify(trailState.terrainTiles[0].connections)")), {east: false},
    "a late response cannot replace the active world's connection checks");
  assert.equal(run("trailState.points.find(point=>point.sequence===1).player_anchor.clear"), false,
    "the active world's local failed anchor is retained while its stored trail response is pending");
  pendingTrails.get(raceB.id)({ok: false, status: 500, json: async () => ({error: "trail unavailable"})});
  await settle();
  assert.ok(element("trailStatus").textContent.includes("trail unavailable"));
  assert.equal(run("state.result.directions[0].direction"), "north", "trail failure does not remove live recommendations");
  assert.ok(element("livePosition").textContent.includes("50.0"));
  assert.equal(element("liveReplayLink").href, "/api/explorations/" + raceB.id, "trail failure does not remove replay download");
  assert.equal(trailCallCounts.get(raceB.id), 1);
  context.fetch = async url => {
    if (url !== "/api/explorations/" + raceB.id + "/trail") throw new Error("unexpected fetch " + url);
    trailCallCounts.set(raceB.id, trailCallCounts.get(raceB.id) + 1);
    return apiResponse({...trailPayload(raceB, [trailPoint(0, 199, 49, 0)]), world_id: "wrong-world"});
  };
  run("refreshSelectedTrail()");
  await settle();
  assert.equal(trailCallCounts.get(raceB.id), 2, "explicit refresh retries a failed trail request");
  assert.ok(run("trailState.error").includes("身份不匹配"), "trail payload world/session identity is validated");
  context.fetch = async url => {
    if (url !== "/api/explorations/" + raceB.id + "/trail") throw new Error("unexpected fetch " + url);
    trailCallCounts.set(raceB.id, trailCallCounts.get(raceB.id) + 1);
    return apiResponse(trailPayload(raceB, [trailPoint(1, 199, 49, 0, {x: 50, z: 0, clear: true})],
      [remembered("panflute", 49, 0, 0, 0)], false,
      {tile_size: 4, tiles: [terrainCell(50, 0, "MARSH", 0, 199, true, {east: true})], truncated: false}));
  };
  run("refreshSelectedTrail()");
  await settle();
  assert.equal(trailCallCounts.get(raceB.id), 3);
  assert.equal(run("trailState.error"), "");
  assert.equal(run("trailState.terrainTiles[0].passable"), false,
    "newer local blocked terrain wins over stored history in the live view");
  assert.deepEqual(JSON.parse(run("JSON.stringify(trailState.terrainTiles[0].connections)")), {east: false},
    "newer local connection results win over stored history in the live view");
  assert.equal(run("trailState.points.find(point=>point.sequence===1).player_anchor.clear"), false,
    "a local same-sequence anchor replaces the stored anchor as a whole");
  context.reply = frame("same-session", 1, raceB, "race-b", {x: 50, z: 0, capturedAt: 201});
  run("applyLiveResult(reply)");
  assert.ok(!Object.hasOwn(JSON.parse(run("JSON.stringify(trailState.points.find(point=>point.sequence===1))")), "player_anchor"),
    "a newer local point at the same sequence without an anchor clears the stored anchor");

  const newerRaceB = {...raceB, frame_count: 4};
  context.fetch = async url => {
    if (url !== "/api/explorations/" + raceB.id + "/trail") throw new Error("unexpected fetch " + url);
    trailCallCounts.set(raceB.id, trailCallCounts.get(raceB.id) + 1);
    return apiResponse(trailPayload(newerRaceB, [
      trailPoint(0, 199, 49, 0), trailPoint(1, 200, 50, 0, {x: 50, z: 0, clear: true}),
      trailPoint(2, 201, 51, 0), trailPoint(3, 202, 52, 0)
    ], [remembered("panflute", 49, 0, 0, 2, 199, 201)], false,
      {tile_size: 4, tiles: [terrainCell(50, 0, "MARSH", 0, 199, true, {east: true})], truncated: false}));
  };
  run(`state.explorations=[${JSON.stringify(newerRaceB)}];renderExplorations();live.following=true;liveEl.follow.checked=true;`);
  const trailButton = {dataset: {explorationId: raceB.id}};
  element("explorationList").listeners.click({target: {closest: selector => selector === "button.trail-open[data-exploration-id]" ? trailButton : null}});
  assert.equal(run("live.following"), false, "opening a saved trail stops live following");
  assert.equal(element("liveFollow").checked, false);
  assert.equal(run("trailState.mode"), "history");
  assert.equal(run("trailState.id"), raceB.id);
  await settle();
  assert.equal(run("trailState.terrainTiles.find(tile => tile.x === 50).passable"), true,
    "history displays the terrain saved in the selected replay without merging newer live checks");
  assert.deepEqual(JSON.parse(run("JSON.stringify(trailState.terrainTiles.find(tile => tile.x === 50).connections)")), {east: true},
    "history displays the saved connection result without newer live checks");
  assert.equal(trailCallCounts.get(raceB.id), 4, "opening a replay refreshes cached trail data when its frame count advanced");
  assert.equal(run("trailState.points.length"), 4);
  assert.equal(run("trailState.points.find(point=>point.sequence===1).player_anchor.clear"), true,
    "saved history keeps its recorded anchor instead of replacing it with a newer local point");
  assert.ok(element("trailStatus").textContent.includes("历史回放"));
  assert.ok(JSON.parse(run("JSON.stringify(trailState.landmarks)")).some(item => item.prefab === "panflute" && item.x === 49),
    "saved history opens remembered target positions");
  const liveIdentityBeforeResume = run("trailState.live.identity");
  context.fetch = async url => {
    if (!url.startsWith("/api/live?")) throw new Error("unexpected fetch " + url);
    return apiResponse({status: "waiting"});
  };
  element("liveFollow").checked = true;
  element("liveFollow").listeners.change();
  assert.equal(run("live.following"), true);
  assert.equal(run("trailState.mode"), "live");
  assert.equal(run("trailState.identity"), liveIdentityBeforeResume, "checking live follow resumes the current live trail");
  await settle();
  run("stopLive()");

  const stoppedLive = replaySummary("7".repeat(64), {worldId: "stop-world", session: "stop-session"});
  let resolveStoppedLive;
  context.fetch = url => {
    if (url !== "/api/explorations/" + stoppedLive.id + "/trail") throw new Error("unexpected fetch " + url);
    return new Promise(resolve => { resolveStoppedLive = resolve; });
  };
  run('live.following=true;liveEl.follow.checked=true;live.key=null;live.sequence=0;trailState.mode="live";');
  context.reply = frame("stop-session", 1, stoppedLive, "stop-world", {x: 4, z: 0, capturedAt: 300});
  run("applyLiveResult(reply)");
  run("stopLive()");
  resolveStoppedLive(apiResponse(trailPayload(stoppedLive, [trailPoint(0, 299, 800, 0)])));
  await settle();
  assert.equal(run("trailState.id"), stoppedLive.id);
  assert.equal(run("trailState.points.length"), 1);
  assert.equal(run("trailState.points[0].x"), 4, "a pending live trail response is ignored after stopping");

  const historyA = replaySummary("4".repeat(64), {worldId: "history-a", session: "hist-a"});
  const historyB = replaySummary("5".repeat(64), {worldId: "history-b", session: "hist-b"});
  context.fetch = url => {
    const match = url.match(/^\/api\/explorations\/([a-f0-9]{64})\/trail$/);
    if (!match) throw new Error("unexpected fetch " + url);
    return new Promise(resolve => pendingTrails.set(match[1], resolve));
  };
  run(`openExplorationTrail(${JSON.stringify(historyA)})`);
  run(`openExplorationTrail(${JSON.stringify(historyB)})`);
  pendingTrails.get(historyA.id)(apiResponse(trailPayload(historyA, [trailPoint(1, 10, -10, 0)])));
  await settle();
  assert.equal(run("trailState.id"), historyB.id, "late saved-history responses are ignored after selection changes");
  assert.equal(run("trailState.points.length"), 0);
  pendingTrails.get(historyB.id)(apiResponse(trailPayload(historyB, [trailPoint(2, 10, 20, 30)])));
  await settle();
  assert.equal(run("trailState.points[0].x"), 20);
  const historyC = replaySummary("6".repeat(64), {worldId: "history-c", session: "hist-c"});
  run(`openExplorationTrail(${JSON.stringify(historyC)})`);
  run("stopLive()");
  pendingTrails.get(historyC.id)(apiResponse(trailPayload(historyC, [trailPoint(3, 10, 900, 0)])));
  await settle();
  assert.equal(run("trailState.points.length"), 0, "stopping invalidates a pending historical trail response");

  // Historical frame review requests server-projected prefixes by the recorded sequence.
  const playbackSummary = replaySummary("a".repeat(64), {
    worldId: "playback-world", session: "playback-session", frames: 3
  });
  const playbackPoints = [trailPoint(2, 1200, 0, 0, undefined, 10),
    trailPoint(5, 1500, 4, 0, undefined, 20), trailPoint(12, 2200, 8, 0, undefined, 30)];
  const playbackLandmarks = [remembered("panflute", 4, 0, 5, 5, 1500, 1500),
    remembered("panflute", 12, 0, 12, 12, 2200, 2200)];
  const playbackTerrain = [terrainCell(0, 0, "GRASS", 2, 1200, false),
    terrainCell(4, 0, "MARSH", 5, 1500, true), terrainCell(8, 0, "ROCKY", 12, 2200, true)];
  const playbackBaseUrl = "/api/explorations/" + playbackSummary.id + "/trail";
  context.playbackSummary = playbackSummary;
  context.playbackFuturePoint = trailPoint(20, 3000, 200, 0, undefined, 40);
  context.playbackFutureLandmark = remembered("panflute", 200, 0, 20, 20, 3000, 3000);
  context.playbackFutureTerrain = terrainCell(200, 0, "FOREST", 20, 3000, true);
  run(`trailState.live={identity:explorationReplayIdentity(playbackSummary),id:playbackSummary.id,
    localPoints:[playbackFuturePoint],storedPoints:[],trimmed:false,localLandmarks:[playbackFutureLandmark],
    storedLandmarks:[],landmarksTruncated:false,landmarkError:"",localTerrain:[playbackFutureTerrain],
    storedTerrain:[],localTerrainAvailable:true,storedTerrainAvailable:false,terrainTruncated:false,terrainError:""};`);
  const playbackUrls = [];
  const playbackAppendedPoints = [...playbackPoints, trailPoint(20, 3000, 12, 0)];
  const playbackAppendedTerrain = [...playbackTerrain, terrainCell(12, 0, "FOREST", 20, 3000, true)];
  context.fetch = async url => {
    playbackUrls.push(url);
    if (url === playbackBaseUrl) {
      return apiResponse(trailPayload(playbackSummary, playbackPoints, playbackLandmarks, false,
        {tile_size: 4, tiles: playbackTerrain, truncated: false}));
    }
    const match = url.match(/\?through_sequence=(\d+)$/);
    if (!match) throw new Error("unexpected playback request " + url);
    const sequence = Number(match[1]);
    const points = playbackPoints.filter(point => point.sequence <= sequence);
    const landmarks = playbackLandmarks.filter(item => item.last_sequence <= sequence);
    const tiles = playbackTerrain.filter(item => item.last_sequence <= sequence);
    return apiResponse(trailPlaybackPayload(playbackSummary, points, sequence, 4, landmarks,
      {tile_size: 4, tiles, truncated: false}));
  };
  run(`openExplorationTrail(${JSON.stringify(playbackSummary)})`);
  await settle();
  assert.deepEqual(JSON.parse(run("JSON.stringify(trailState.playback.timeline.map(frame=>frame.sequence))")), [2, 5, 12],
    "the full response keeps the sparse recorded frame index independently of the visible prefix");
  assert.equal(run("trailState.points.length"), 3, "opening history displays only the saved trail even when local live data is newer");
  assert.equal(run("trailState.points.at(-1).camera_heading"), 30,
    "opening history uses the latest saved frame heading and ignores a newer local live heading");
  assert.equal(run("trailState.landmarks.length"), 2, "opening history does not merge unsaved local sightings");
  assert.equal(run("trailState.terrainTiles.length"), 3, "opening history does not merge unsaved local terrain");
  assert.ok(playbackUrls.includes(playbackBaseUrl), "opening a replay still requests the unchanged full-trail URL");
  assert.equal(element("trailPlaybackControls").hidden, false);
  assert.equal(element("trailPlaybackRange").min, "0");
  assert.equal(element("trailPlaybackRange").max, "2");
  assert.equal(element("trailPlaybackRange").value, "2", "history opens at the latest recorded frame");
  assert.ok(element("trailPlaybackStatus").textContent.includes("第 3 / 3 帧 · 序号 12 ·"),
    "history status identifies the latest frame, its actual sequence, and capture time");

  run('checkedRouteSelection.identity=trailState.identity;checkedRouteSelection.destination={x:4,z:0};checkedRouteSelection.source={prefab:"panflute",x:4,z:0};');
  element("trailPlaybackRange").value = "1";
  element("trailPlaybackRange").listeners.change();
  await settle();
  assert.ok(playbackUrls.includes(playbackBaseUrl + "?through_sequence=5"),
    "the slider sends the selected sparse frame sequence in the cutoff URL");
  assert.deepEqual(JSON.parse(run("JSON.stringify(trailState.points.map(point=>point.sequence))")), [2, 5]);
  assert.equal(run("trailState.points.at(-1).camera_heading"), 20,
    "a cutoff history prefix uses its selected frame heading rather than a later saved or live heading");
  assert.deepEqual(JSON.parse(run("JSON.stringify(trailState.landmarks.map(item=>item.last_sequence))")), [5],
    "a prefix response shows only sightings known at the selected frame");
  assert.ok(JSON.parse(run("JSON.stringify(trailState.terrainTiles)")).every(tile => tile.last_sequence <= 5),
    "a prefix response shows no terrain checks from later frames");
  assert.equal(run("checkedRouteSelection.destination"), null,
    "changing the cursor clears a route endpoint that could reveal a later clue");
  assert.equal(run("checkedRouteSelection.source"), null, "changing the cursor also clears the route source");
  assert.ok(element("trailPlaybackStatus").textContent.includes("第 2 / 3 帧 · 序号 5"));

  element("trailPlaybackNextButton").listeners.click();
  await settle();
  assert.ok(playbackUrls.includes(playbackBaseUrl + "?through_sequence=12"),
    "next advances through the frame index and sends its actual sequence");
  assert.deepEqual(JSON.parse(run("JSON.stringify(trailState.points.map(point=>point.sequence))")), [2, 5, 12]);
  element("trailPlaybackPreviousButton").listeners.click();
  await settle();
  assert.equal(run("trailState.playback.appliedIndex"), 1, "previous returns to the earlier recorded frame");
  assert.deepEqual(JSON.parse(run("JSON.stringify(trailState.points.map(point=>point.sequence))")), [2, 5]);

  context.fetch = async url => {
    playbackUrls.push(url);
    if (url === playbackBaseUrl) return apiResponse(trailPayload(playbackSummary, playbackAppendedPoints,
      [...playbackLandmarks, context.playbackFutureLandmark], false,
      {tile_size: 4, tiles: playbackAppendedTerrain, truncated: false}));
    const match = url.match(/\?through_sequence=(\d+)$/);
    if (!match) throw new Error("unexpected appended-history request " + url);
    const sequence = Number(match[1]);
    const points = playbackAppendedPoints.filter(point => point.sequence <= sequence);
    const landmarks = [...playbackLandmarks, context.playbackFutureLandmark].filter(item => item.last_sequence <= sequence);
    const tiles = playbackAppendedTerrain.filter(item => item.last_sequence <= sequence);
    return apiResponse(trailPlaybackPayload(playbackSummary, points, sequence, 4, landmarks,
      {tile_size: 4, tiles, truncated: false}));
  };
  element("trailPlaybackLatestButton").listeners.click();
  await settle();
  assert.equal(playbackUrls.at(-1), playbackBaseUrl, "jump to latest refreshes the full trail to pick up appended frames");
  assert.deepEqual(JSON.parse(run("JSON.stringify(trailState.playback.timeline.map(frame=>frame.sequence))")), [2, 5, 12, 20]);
  assert.ok(element("trailPlaybackStatus").textContent.includes("第 4 / 4 帧 · 序号 20"));

  let resolveOlderPrefix;
  let resolveNewerPrefix;
  context.fetch = url => new Promise(resolve => {
    if (url.endsWith("through_sequence=2")) resolveOlderPrefix = resolve;
    else if (url.endsWith("through_sequence=5")) resolveNewerPrefix = resolve;
    else throw new Error("unexpected race request " + url);
  });
  element("trailPlaybackRange").value = "0";
  element("trailPlaybackRange").listeners.change();
  element("trailPlaybackRange").value = "1";
  element("trailPlaybackRange").listeners.change();
  resolveNewerPrefix(apiResponse(trailPlaybackPayload(playbackSummary, playbackPoints.slice(0, 2), 5, 4,
    playbackLandmarks.slice(0, 1), {tile_size: 4, tiles: playbackTerrain.slice(0, 2), truncated: false})));
  await settle();
  resolveOlderPrefix(apiResponse(trailPlaybackPayload(playbackSummary, playbackPoints.slice(0, 1), 2, 4, [],
    {tile_size: 4, tiles: playbackTerrain.slice(0, 1), truncated: false})));
  await settle();
  assert.equal(run("trailState.playback.appliedIndex"), 1,
    "a late response from an older cursor cannot replace the most recent selection");
  assert.deepEqual(JSON.parse(run("JSON.stringify(trailState.points.map(point=>point.sequence))")), [2, 5]);

  context.fetch = async () => { throw new Error("cutoff unavailable"); };
  element("trailPlaybackRange").value = "0";
  element("trailPlaybackRange").listeners.change();
  await settle();
  assert.ok(run("trailState.playback.error").includes("cutoff unavailable"), "cutoff failures are shown in replay status");
  assert.deepEqual(JSON.parse(run("JSON.stringify(trailState.points.map(point=>point.sequence))")), [2, 5],
    "a failed cutoff leaves the last successful prefix visible");
  context.fetch = async url => {
    assert.equal(url, playbackBaseUrl + "?through_sequence=2");
    return apiResponse(trailPlaybackPayload(playbackSummary, playbackPoints.slice(0, 1), 2, 4, [],
      {tile_size: 4, tiles: playbackTerrain.slice(0, 1), truncated: false}));
  };
  element("refreshTrailButton").listeners.click();
  await settle();
  assert.equal(run("trailState.playback.error"), "", "refresh retries the failed cutoff at the same selected frame");
  assert.deepEqual(JSON.parse(run("JSON.stringify(trailState.points.map(point=>point.sequence))")), [2]);

  let resolveStaleLivePrefix;
  context.fetch = () => new Promise(resolve => { resolveStaleLivePrefix = resolve; });
  element("trailPlaybackRange").value = "2";
  element("trailPlaybackRange").listeners.change();
  run("resumeLiveTrailView()");
  const livePointsBeforeStalePrefix = JSON.parse(run("JSON.stringify(trailState.points.map(point=>point.sequence))"));
  resolveStaleLivePrefix(apiResponse(trailPlaybackPayload(playbackSummary, playbackPoints, 12, 4,
    playbackLandmarks, {tile_size: 4, tiles: playbackTerrain, truncated: false})));
  await settle();
  assert.equal(run("trailState.mode"), "live");
  assert.deepEqual(JSON.parse(run("JSON.stringify(trailState.points.map(point=>point.sequence))")), livePointsBeforeStalePrefix,
    "a cutoff response cannot replace the live view after resuming collection");
  assert.equal(element("trailPlaybackControls").hidden, true, "replay controls hide after returning to live mode");

  const replaySwitch = replaySummary("b".repeat(64), {worldId: "switch-world", session: "switch-session"});
  let resolveStaleReplayPrefix;
  context.fetch = url => {
    if (url === playbackBaseUrl + "?through_sequence=2") return new Promise(resolve => { resolveStaleReplayPrefix = resolve; });
    if (url === "/api/explorations/" + replaySwitch.id + "/trail") {
      return Promise.resolve(apiResponse(trailPayload(replaySwitch, [trailPoint(40, 4000, 400, 0)])));
    }
    throw new Error("unexpected replay-switch request " + url);
  };
  run(`openExplorationTrail(${JSON.stringify(playbackSummary)})`);
  await settle();
  element("trailPlaybackRange").value = "0";
  element("trailPlaybackRange").listeners.change();
  run(`openExplorationTrail(${JSON.stringify(replaySwitch)})`);
  await settle();
  resolveStaleReplayPrefix(apiResponse(trailPlaybackPayload(playbackSummary, playbackPoints.slice(0, 1), 2, 4, [],
    {tile_size: 4, tiles: playbackTerrain.slice(0, 1), truncated: false})));
  await settle();
  assert.equal(run("trailState.id"), replaySwitch.id, "a stale cutoff cannot replace a different replay");
  assert.equal(run("trailState.points[0].sequence"), 40);

  const emptyPlayback = replaySummary("c".repeat(64), {worldId: "empty-playback", frames: 0});
  context.fetch = async url => {
    assert.equal(url, "/api/explorations/" + emptyPlayback.id + "/trail");
    return apiResponse(trailPayload(emptyPlayback, []));
  };
  run(`openExplorationTrail(${JSON.stringify(emptyPlayback)})`);
  await settle();
  assert.equal(element("trailPlaybackControls").hidden, true, "empty histories hide unusable frame controls");
  assert.ok(element("trailPlaybackStatus").textContent.includes("没有可回看的坐标帧"));
  const singlePlayback = replaySummary("d".repeat(64), {worldId: "single-playback", frames: 1});
  context.fetch = async url => {
    assert.equal(url, "/api/explorations/" + singlePlayback.id + "/trail");
    return apiResponse(trailPayload(singlePlayback, [trailPoint(7, 7000, 70, 0)]));
  };
  run(`openExplorationTrail(${JSON.stringify(singlePlayback)})`);
  await settle();
  assert.equal(element("trailPlaybackControls").hidden, true, "a one-frame history hides controls with no useful range");
  assert.ok(element("trailPlaybackStatus").textContent.includes("第 1 / 1 帧 · 序号 7"));

  const largePlayback = replaySummary("e".repeat(64), {worldId: "large-playback", frames: 520});
  const largePlaybackPoints = Array.from({length: 520}, (_, index) => trailPoint(index * 3 + 1, index + 1, index, 0));
  context.fetch = async url => {
    assert.equal(url, "/api/explorations/" + largePlayback.id + "/trail");
    return apiResponse(trailPayload(largePlayback, largePlaybackPoints));
  };
  run(`openExplorationTrail(${JSON.stringify(largePlayback)})`);
  await settle();
  assert.equal(run("trailState.playback.timeline.length"), 520,
    "the history index retains all available frames beyond the former 500-frame display limit");
  assert.equal(element("trailPlaybackRange").max, "519");

  run("resumeLiveTrailView()");
  assert.equal(element("trailPlaybackControls").hidden, true);
  assert.equal(element("trailPlaybackStatus").hidden, true, "playback status is hidden outside historical mode");

  run('trailState.mode="idle";trailState.live={identity:null,id:null,localPoints:[],storedPoints:[],trimmed:false,localLandmarks:[],storedLandmarks:[],landmarksTruncated:false,landmarkError:""};trailState.landmarks=[];trailState.landmarksTruncated=false;trailState.landmarkError="";state.liveRecording=null;');
  run(`for(let i=0;i<10002;i++){recordLiveTrailSnapshot({world_id:"bound-world",world_kind:"forest",session_id:"bound-session",sequence:i,captured_at:i,position:{x:i,z:0}});}`);
  assert.equal(run("trailState.live.localPoints.length"), 10000);
  assert.equal(run("trailState.live.localPoints[0].sequence"), 0, "trimming retains the original point");
  assert.equal(run("trailState.live.localPoints[9999].sequence"), 10001, "trimming retains the latest points");
  run('live.following=true;resumeLiveTrailView()');
  assert.equal(run("trailState.points.length"), 10000);
  assert.ok(element("trailStatus").textContent.includes("最近 9999 个位置"));
  run("stopLive()");
  assert.ok(run("trailState.requests.size") <= 4, "trail payload cache stays bounded");

  const initSummary = replaySummary("f".repeat(64), {worldId: "after-restart"});
  const initCalls = [];
  context.fetch = async url => {
    initCalls.push(url);
    if (url === "/api/options") return apiResponse({
      targets: ["panflute", "moonbase"], tile_types: ["GRASS"], prefabs: ["grass"], background_recording: true,
      directions: ["north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest"]
    });
    if (url === "/api/records") return apiResponse({records: []});
    if (url === "/api/explorations") return apiResponse({explorations: [initSummary]});
    throw new Error("unexpected fetch " + url);
  };
  await run("initialize()");
  assert.equal(element("backgroundRecordingNotice").hidden, false);
  assert.ok(element("backgroundRecordingNotice").textContent.includes("关闭网页") &&
    element("backgroundRecordingNotice").textContent.includes("Ctrl+C"),
    "startup explains the background recorder's lifetime separately from live display");
  assert.ok(initCalls.includes("/api/explorations"));
  assert.equal(run("state.explorations[0].id"), initSummary.id);
  assert.ok(element("explorationList").innerHTML.includes("/api/explorations/" + initSummary.id));

  assert.ok(!initCalls.includes("/api/live-check"), "connection diagnostics do not run automatically during initialization");

  run('live.following=true;liveEl.follow.checked=true;liveEl.status.textContent="保持实时指引";liveEl.position.textContent="洞穴 · X 1 / Z 2";liveEl.target.textContent="目标仍在附近";liveEl.recordingStatus.textContent="已自动记录";liveEl.replayLink.href="/api/explorations/"+"a".repeat(64);liveEl.replayLink.hidden=false;state.current={marker:"current"};state.result={directions:[{direction:"north",score:7}]};state.dirs.north.note="保持观测";state.activeRecordId="record-kept";state.activeRecordName="name-kept";state.liveRecording={id:"c".repeat(64),frame_count:4};el.recordName.value="记录名称";el.worldNote.value="世界备注";trailState.mode="history";trailState.id="b".repeat(64);trailState.identity="history-identity";trailState.points=[{sequence:1,captured_at:1,x:1,z:2}];');
  function liveStateForDiagnostics() {
    return JSON.parse(run('JSON.stringify({following:live.following,liveStatus:liveEl.status.textContent,position:liveEl.position.textContent,target:liveEl.target.textContent,recording:liveEl.recordingStatus.textContent,replayHref:liveEl.replayLink.href,replayHidden:liveEl.replayLink.hidden,current:state.current,result:state.result,directionNote:state.dirs.north.note,activeRecordId:state.activeRecordId,activeRecordName:state.activeRecordName,recordName:el.recordName.value,worldNote:el.worldNote.value,liveRecording:state.liveRecording,explorationIds:state.explorations.map(item=>item.id),trailMode:trailState.mode,trailId:trailState.id,trailIdentity:trailState.identity,trailPoints:trailState.points})'));
  }
  const diagnosticStateBefore = liveStateForDiagnostics();
  const diagnosticPath = 'C:\\游戏\\存档\\<img src=x onerror=boom>.txt';
  let diagnosticCalls = 0;
  context.fetch = async url => {
    assert.equal(url, "/api/live-check");
    diagnosticCalls += 1;
    return apiResponse({
      check_version: 1, status: "live", log_path: diagnosticPath, age_seconds: 0.8,
      position: {x: 4, y: 1, z: 9}, world_kind: "cave", sequence: 12
    });
  };
  await element("liveCheckButton").listeners.click();
  assert.equal(diagnosticCalls, 1, "the check button makes one explicit request");
  assert.ok(element("liveCheckStatus").textContent.includes("连接正常 · 洞穴世界"));
  assert.ok(element("liveCheckStatus").textContent.includes("日志路径：" + diagnosticPath));
  assert.ok(element("liveCheckStatus").textContent.includes("X 4.0 / Y 1.0 / Z 9.0"));
  assert.ok(!element("liveCheckStatus").textContent.includes("快照摘要"), "legacy live-check responses keep their original text without an observation summary");
  assert.equal(element("liveCheckStatus").innerHTML, "", "diagnostic paths render only as text, never as HTML");
  assert.deepEqual(liveStateForDiagnostics(), diagnosticStateBefore, "a diagnostic response does not mutate live, observation, plan, replay, or trail state");

  const validObservationSummary = {
    landmarks: 0, terrain_available: true, terrain_tiles: 3, passable_tiles: 1, blocked_tiles: 1,
    unknown_tiles: 1, clear_connections: 2, blocked_connections: 1, player_anchor: "clear"
  };
  context.fetch = async () => apiResponse({
    check_version: 1, status: "live", log_path: "D:\\summary.log", age_seconds: 0,
    position: {x: 4, y: 0, z: 9}, world_kind: "forest", sequence: 13, observation_summary: validObservationSummary
  });
  await element("liveCheckButton").listeners.click();
  assert.ok(element("liveCheckStatus").textContent.includes("最新快照摘要"));
  assert.ok(element("liveCheckStatus").textContent.includes("地标：0 个"), "zero landmarks are shown as a count, not treated as a failed connection");
  assert.ok(element("liveCheckStatus").textContent.includes("地皮：3 格（可通行 1 / 受阻 1 / 未知 1）"));
  assert.ok(element("liveCheckStatus").textContent.includes("邻格连接：通过 2 / 受阻 1"));
  assert.ok(element("liveCheckStatus").textContent.includes("玩家接入：通过"));
  assert.equal(element("liveCheckStatus").innerHTML, "", "summary content remains plain text");
  assert.deepEqual(liveStateForDiagnostics(), diagnosticStateBefore, "a live summary leaves live, form, replay, recording, and history state untouched");

  const unavailableTerrainSummary = {
    landmarks: 0, terrain_available: false, terrain_tiles: 0, passable_tiles: 0, blocked_tiles: 0,
    unknown_tiles: 0, clear_connections: 0, blocked_connections: 0, player_anchor: "unknown"
  };
  context.fetch = async () => apiResponse({
    check_version: 1, status: "live", log_path: "D:\\summary.log", age_seconds: 0,
    position: {x: 4, y: 0, z: 9}, world_kind: "forest", sequence: 14, observation_summary: unavailableTerrainSummary
  });
  await run("checkLiveConnection()");
  assert.ok(element("liveCheckStatus").textContent.includes("地皮：未提供"));
  assert.ok(element("liveCheckStatus").textContent.includes("玩家接入：未提供"));
  assert.ok(element("liveCheckStatus").textContent.includes("邻格连接：通过 0 / 受阻 0"));
  assert.deepEqual(liveStateForDiagnostics(), diagnosticStateBefore, "an unavailable-terrain summary leaves other UI state untouched");

  context.fetch = async () => apiResponse({
    check_version: 1, status: "stale", log_path: "D:\\summary.log", age_seconds: 11.25,
    position: {x: 4, y: 0, z: 9}, world_kind: "forest", sequence: 15, observation_summary: validObservationSummary
  });
  await run("checkLiveConnection()");
  assert.ok(element("liveCheckStatus").textContent.includes("最近快照已过期"));
  assert.ok(element("liveCheckStatus").textContent.includes("解除暂停"));
  assert.ok(element("liveCheckStatus").textContent.includes("11.3 秒前"));
  assert.ok(element("liveCheckStatus").textContent.includes("最后快照摘要（已过期）"));
  assert.ok(!element("liveCheckStatus").textContent.includes("最新快照摘要"), "stale summaries are labeled as the last snapshot");
  assert.deepEqual(liveStateForDiagnostics(), diagnosticStateBefore, "a stale summary leaves live, form, replay, recording, and history state untouched");

  const malformedSummaries = [
    {...validObservationSummary, landmarks: "0"},
    {...validObservationSummary, terrain_tiles: Infinity},
    {...validObservationSummary, terrain_tiles: Number.MAX_SAFE_INTEGER + 1},
    {...validObservationSummary, passable_tiles: 1.5},
    {...validObservationSummary, blocked_connections: -1},
    {...validObservationSummary, terrain_available: 1},
    {...validObservationSummary, player_anchor: "maybe"},
    {...validObservationSummary, unknown_tiles: 0},
    {...unavailableTerrainSummary, clear_connections: 1},
    {...unavailableTerrainSummary, player_anchor: "clear"},
    {...validObservationSummary, extra: "raw"}
  ];
  for (const summary of malformedSummaries) {
    context.fetch = async () => apiResponse({
      check_version: 1, status: "live", log_path: "D:\\invalid-summary.log", age_seconds: 0,
      position: {x: 4, y: 0, z: 9}, world_kind: "forest", sequence: 16, observation_summary: summary
    });
    await run("checkLiveConnection()");
    assert.ok(element("liveCheckStatus").textContent.includes("连接检查失败：连接检查结果中的观测摘要格式无效"),
      "malformed optional observation summaries use the existing diagnostic error display");
    assert.ok(element("liveCheckStatus").textContent.includes("日志路径：未能读取"));
    assert.deepEqual(liveStateForDiagnostics(), diagnosticStateBefore, "a rejected summary leaves other UI state untouched");
  }
  context.fetch = async () => apiResponse({check_version: 1, status: "waiting", log_path: "D:\\invalid-status.log", observation_summary: unavailableTerrainSummary});
  await run("checkLiveConnection()");
  assert.ok(element("liveCheckStatus").textContent.includes("连接检查失败：连接检查结果中的观测摘要格式无效"),
    "observation summaries are accepted only on live or stale results");
  assert.deepEqual(liveStateForDiagnostics(), diagnosticStateBefore, "a summary on a waiting response leaves other UI state untouched");

  const statusCases = [
    {status: "disabled", phrase: "--ui"},
    {status: "missing_log", phrase: "启动 DST"},
    {status: "waiting", phrase: "启用客户端采集器"},
    {status: "stale", phrase: "解除暂停", age_seconds: 8},
    {status: "error", phrase: "<svg onload=boom>", error: "<svg onload=boom>"}
  ];
  for (const item of statusCases) {
    context.fetch = async () => apiResponse({
      check_version: 1, status: item.status, log_path: "D:\\游戏\\Player.log",
      ...(item.age_seconds === undefined ? {} : {
        age_seconds: item.age_seconds, position: {x: 1, y: 0, z: 2}, world_kind: "forest", sequence: 3
      }),
      ...(item.error === undefined ? {} : {error: item.error})
    });
    await run("checkLiveConnection()");
    assert.ok(element("liveCheckStatus").textContent.includes(item.phrase), item.status + " explains its next step or error");
    assert.ok(element("liveCheckStatus").textContent.includes("日志路径：D:\\游戏\\Player.log"), item.status + " displays the selected path");
    assert.equal(element("liveCheckStatus").innerHTML, "", "all diagnostic text remains unparsed HTML");
    assert.deepEqual(liveStateForDiagnostics(), diagnosticStateBefore, "diagnostic status " + item.status + " leaves other UI state unchanged");
  }

  let resolveDiagnostic;
  let serializedCalls = 0;
  context.fetch = url => {
    assert.equal(url, "/api/live-check");
    serializedCalls += 1;
    return new Promise(resolve => { resolveDiagnostic = resolve; });
  };
  const pendingDiagnostic = run("checkLiveConnection()");
  assert.equal(element("liveCheckButton").disabled, true, "the button is disabled while a check runs");
  await run("checkLiveConnection()");
  assert.equal(serializedCalls, 1, "overlapping checks are serialized");
  resolveDiagnostic(apiResponse({check_version: 1, status: "waiting", log_path: "D:\\waiting.log"}));
  await pendingDiagnostic;
  assert.equal(element("liveCheckButton").disabled, false, "the button is re-enabled after a check");
  assert.ok(element("liveCheckStatus").textContent.includes("暂未收到快照"));

  context.fetch = async () => apiResponse({check_version: 2, status: "waiting", log_path: "D:\\invalid.log"});
  await run("checkLiveConnection()");
  assert.ok(element("liveCheckStatus").textContent.includes("格式无法识别"), "invalid response reports a readable format error");
  context.fetch = async () => { throw new Error("offline <b>"); };
  await run("checkLiveConnection()");
  assert.ok(element("liveCheckStatus").textContent.includes("offline <b>"), "network failure appears as plain text");
  assert.equal(element("liveCheckButton").disabled, false, "a failed check leaves retry enabled");
  context.fetch = async () => apiResponse({check_version: 1, status: "disabled", log_path: null});
  await run("checkLiveConnection()");
  assert.ok(element("liveCheckStatus").textContent.includes("重启工具并使用 --ui"), "retry succeeds after a network or validation failure");
  assert.ok(element("liveCheckStatus").textContent.includes("日志路径：未配置"));
  assert.deepEqual(liveStateForDiagnostics(), diagnosticStateBefore, "retries also preserve live, observation, plan, replay, and trail state");

  context.fetch = async () => { throw new Error("unexpected terrain-test fetch"); };
  run('trailState.mode="live";trailState.revision++;trailState.id=null;trailState.identity=null;trailState.summary=null;trailState.points=[];trailState.error="";trailState.loading=false;trailState.trimmed=false;trailState.requests.clear();trailState.live={identity:null,id:null,localPoints:[],storedPoints:[],trimmed:false,localLandmarks:[],storedLandmarks:[],landmarksTruncated:false,landmarkError:"",localTerrain:[],storedTerrain:[],localTerrainAvailable:false,storedTerrainAvailable:false,terrainTruncated:false,terrainError:""};trailState.landmarks=[];trailState.landmarksTruncated=false;trailState.landmarkError="";trailState.terrainTiles=[];trailState.terrainAvailable=false;trailState.terrainTruncated=false;trailState.terrainError="";state.liveRecording=null;state.result=null;state.explorations=[];live.following=true;liveEl.follow.checked=true;live.key=null;live.sequence=0;');
  context.reply = frame("forest-session", 1, null, "forest-world", {x: 4, z: 5, capturedAt: 100,
    terrain: {tile_size: 4, tiles: [{x: 4, z: 4, tile: "GRASS", passable: true, connections: {east: false, north: true}}]}});
  run("applyLiveResult(reply)");
  assert.equal(run("trailState.live.identity"), "forest-world\u0000forest\u0000forest-session");
  assert.equal(JSON.parse(run("JSON.stringify(trailState.live.localTerrain)")).find(tile => tile.tile === "GRASS").passable, true,
    "live snapshots preserve passable=true");
  assert.deepEqual(JSON.parse(run("JSON.stringify(trailState.live.localTerrain[0].connections)")), {east: false, north: true},
    "live snapshots preserve false connection checks");

  context.reply = frame("cave-session", 1, null, "cave-world", {worldKind: "cave", x: 21, z: 22, capturedAt: 101,
    terrain: {tile_size: 4, tiles: [{x: 20, z: 20, tile: "ROCKY", passable: false, connections: {north: false}}]}});
  context.reply.status = "unsupported_world";
  context.reply.age_seconds = 0.5;
  run("applyLiveResult(reply)");
  assert.equal(run("live.key"), "cave-world\u0000cave\u0000cave-session", "fresh unsupported snapshots advance the live identity");
  assert.equal(run("live.sequence"), 1);
  assert.equal(run("trailState.live.identity"), "cave-world\u0000cave\u0000cave-session");
  assert.equal(run("trailState.live.localPoints.length"), 1, "a world switch drops forest positions from the active trail");
  assert.deepEqual(JSON.parse(run("JSON.stringify(trailState.live.localTerrain)")), [terrainCell(20, 20, "ROCKY", 1, 101, false, {north: false})],
    "the cave becomes the active terrain identity and preserves passability and connections");
  assert.ok(element("livePosition").textContent.includes("洞穴 · 玩家坐标 X 21.0 / Z 22.0"));
  assert.equal(run("state.result"), null, "unsupported worlds still do not create direction suggestions");

  context.reply = frame("cave-session", 2, null, "cave-world", {worldKind: "cave", x: 99, z: 99, capturedAt: 102,
    terrain: {tile_size: 4, tiles: [{x: 24, z: 20, tile: "OCEAN"}]}});
  context.reply.status = "unsupported_world";
  context.reply.age_seconds = 8;
  run("applyLiveResult(reply)");
  assert.ok(element("liveStatus").textContent.includes("采集已暂停"));
  assert.ok(element("livePosition").textContent.includes("X 21.0 / Z 22.0"), "expired cave coordinates are not shown as current");
  assert.equal(run("live.sequence"), 1, "expired unsupported data does not advance the live sequence");
  assert.equal(run("trailState.live.localPoints.length"), 1);
  assert.deepEqual(JSON.parse(run("JSON.stringify(trailState.live.localTerrain)")), [terrainCell(20, 20, "ROCKY", 1, 101, false, {north: false})],
    "expired unsupported terrain is ignored");

  context.reply = frame("cave-session", 2, null, "cave-world", {worldKind: "cave", x: 22, z: 23, capturedAt: 1000,
    terrain: {tile_size: 4, tiles: [{x: 20, z: 20, tile: "MARSH", passable: true, connections: {north: true, east: false}}]}});
  context.reply.status = "unsupported_world";
  context.reply.age_seconds = 0.4;
  run("applyLiveResult(reply)");
  context.reply = frame("cave-session", 3, null, "cave-world", {worldKind: "cave", x: 23, z: 24, capturedAt: 50,
    terrain: {tile_size: 4, tiles: [{x: 20, z: 20, tile: "FOREST"}]}});
  context.reply.status = "unsupported_world";
  context.reply.age_seconds = 0.3;
  run("applyLiveResult(reply)");
  let caveTiles = JSON.parse(run("JSON.stringify(trailState.live.localTerrain)"));
  assert.deepEqual({tile: caveTiles[0].tile, sequence: caveTiles[0].last_sequence, seen: caveTiles[0].last_seen},
    {tile: "FOREST", sequence: 3, seen: 50}, "same-coordinate terrain follows sequence even when capture time moves backwards");
  assert.ok(!Object.hasOwn(caveTiles[0], "passable"), "a newer live tile without passability clears the prior true value");
  assert.ok(!Object.hasOwn(caveTiles[0], "connections"), "a newer live tile without connections clears the prior dictionary");
  assert.equal(run("live.sequence"), 3);

  context.reply = frame("cave-session", 4, null, "cave-world", {worldKind: "cave", x: 24, z: 25, capturedAt: 60,
    terrain: {tile_size: 4, tiles: [{x: 20, z: 20, tile: "GRASS", passable: false, connections: null}, {x: 20, z: 20, tile: "MARSH"}]}});
  run("applyLiveResult(reply)");
  caveTiles = JSON.parse(run("JSON.stringify(trailState.live.localTerrain)"));
  assert.equal(caveTiles[0].tile, "FOREST", "a malformed optional snapshot leaves previously observed terrain intact");
  assert.ok(run("trailState.terrainError").includes("地皮"));
  assert.equal(run("trailState.live.localPoints.length"), 4, "malformed terrain does not discard a valid player position");
  assert.equal(run("state.result.directions[0].direction"), "north", "malformed terrain does not discard current recommendations");
  assert.ok(element("terrainStatus").textContent.includes("地皮读取失败"));
  assert.ok(element("terrainStatus").textContent.includes("未知 1"), "terrain errors retain the current passability counts");
  assert.ok(element("liveTarget").textContent.includes("直线距离"), "invalid terrain does not remove a visible target");

  run(`trailState.mode="idle";trailState.live={identity:null,id:null,localPoints:[],storedPoints:[],trimmed:false,
    localLandmarks:[],storedLandmarks:[],landmarksTruncated:false,landmarkError:"",localTerrain:[],storedTerrain:[],
    localTerrainAvailable:false,storedTerrainAvailable:false,terrainTruncated:false,terrainError:""};
    recordLiveTrailSnapshot({world_id:"anchor-world",world_kind:"forest",session_id:"anchor-session",sequence:7,
      captured_at:7,position:{x:3,z:3},player_anchor:{x:2,z:2,clear:false}});`);
  assert.deepEqual(JSON.parse(run("JSON.stringify(trailState.live.localPoints[0].player_anchor)")),
    {x: 2, z: 2, clear: false}, "live point construction preserves a failed current-point anchor check");
  run(`recordLiveTrailSnapshot({world_id:"anchor-world",world_kind:"forest",session_id:"anchor-session",sequence:7,
    captured_at:8,position:{x:3.5,z:3}});`);
  assert.ok(!Object.hasOwn(JSON.parse(run("JSON.stringify(trailState.live.localPoints[0])")), "player_anchor"),
    "a same-sequence local point without an anchor replaces the whole prior point");
  run(`recordLiveTrailSnapshot({world_id:"anchor-world",world_kind:"forest",session_id:"anchor-session",sequence:7,
    captured_at:9,position:{x:3.5,z:3},player_anchor:{x:2,z:2,clear:"bad"}});`);
  assert.equal(run("trailState.live.localPoints[0].player_anchor"), null,
    "an invalid live anchor is retained as unknown and cannot revive an older value");
  run(`recordLiveTrailSnapshot({world_id:"anchor-world",world_kind:"forest",session_id:"anchor-session",sequence:8,
    captured_at:10,position:{x:3.5,z:3},camera_heading:270});`);
  assert.equal(run("trailState.live.localPoints.find(point=>point.sequence===8).camera_heading"), 270,
    "live trail recording copies the camera heading from its own snapshot");
  run(`recordLiveTrailSnapshot({world_id:"anchor-world",world_kind:"forest",session_id:"anchor-session",sequence:8,
    captured_at:11,position:{x:3.5,z:3}});`);
  assert.ok(!Object.hasOwn(JSON.parse(run("JSON.stringify(trailState.live.localPoints.find(point=>point.sequence===8))")), "camera_heading"),
    "a same-sequence replacement without a heading clears the previous heading");
  run(`recordLiveTrailSnapshot({world_id:"anchor-world",world_kind:"forest",session_id:"anchor-session",sequence:9,
    captured_at:12,position:{x:3.5,z:3},camera_heading:"invalid"});`);
  assert.equal(run("trailState.live.localPoints.some(point=>point.sequence===9)"), false,
    "an invalid optional heading rejects that live point instead of carrying camera data forward");
  run(`trailState.live={identity:null,id:null,localPoints:[],storedPoints:[],trimmed:false,localLandmarks:[],storedLandmarks:[],
    landmarksTruncated:false,landmarkError:"",localTerrain:[],storedTerrain:[],localTerrainAvailable:false,
    storedTerrainAvailable:false,terrainTruncated:false,terrainError:""};`);

  context.checkedRouteFixture = [
    {x: 2, z: 2, tile: "GRASS", passable: true, connections: {east: true, north: false}},
    {x: 6, z: 2, tile: "FOREST", passable: true, connections: {north: true}},
    {x: 6, z: 6, tile: "ROCKY", passable: true},
    {x: 2, z: 6, tile: "MARSH", passable: true, connections: {east: true}},
    {x: 10, z: 6, tile: "ROCKY", passable: false},
    {x: 14, z: 6, tile: "OTHER"}
  ];
  run('trailState.mode="history";trailState.identity="route-world\u0000forest\u0000route-session";trailState.points=[{sequence:1,captured_at:1,x:2,z:2}];trailState.terrainTiles=checkedRouteFixture;trailState.terrainAvailable=true;trailState.terrainError="";el.terrainToggle.checked=false;el.terrainConnectionToggle.checked=false;renderTrail()');
  assert.ok(appHtml.includes('id="routeDestinationSelect"') && appHtml.includes('id="clearRouteDestinationButton"') &&
    appHtml.includes('id="routeStatus"'), "the route selector, clear action, and status are accessible controls");
  assert.equal((routeDestinationElement.innerHTML.match(/<option /g) || []).length, 5,
    "the destination selector lists the four observed passable cells and its placeholder");
  assert.equal(element("routeStatus").textContent, "请选择路线终点。", "no destination is a normal empty route state");
  assert.equal((element("trailSvg").innerHTML.match(/class="terrain-cell/g) || []).length, 0,
    "the route map remains visible with the terrain layer hidden");
  element("terrainToggle").checked = true;
  element("terrainToggle").listeners.change();
  assert.ok(element("trailSvg").innerHTML.includes('data-terrain-x="2" data-terrain-z="2" tabindex="0" role="button"'),
    "passable terrain cells expose accessible coordinates for choosing a destination");
  assert.equal((element("trailSvg").innerHTML.match(/role="button"/g) || []).length, 4,
    "only currently passable terrain cells are interactive");
  const blockedRouteCell = element("trailSvg").innerHTML.match(/<rect class="terrain-cell terrain-rocky"[^>]+>/g).at(-1);
  const unknownRouteCell = element("trailSvg").innerHTML.match(/<rect class="terrain-cell terrain-other"[^>]+>/)[0];
  assert.ok(!blockedRouteCell.includes("data-terrain-x") && !unknownRouteCell.includes("data-terrain-x"),
    "blocked and unknown cells cannot be selected as new destinations");
  element("terrainToggle").checked = false;
  element("terrainToggle").listeners.change();
  routeDestinationElement.value = "2,6";
  routeDestinationElement.listeners.change();
  let routeSvg = element("trailSvg").innerHTML;
  assert.ok(element("routeStatus").textContent.includes("已找到格中心路线") &&
    element("routeStatus").textContent.includes("起点 X 2.0 / Z 2.0") &&
    element("routeStatus").textContent.includes("终点 X 2.0 / Z 6.0") &&
    element("routeStatus").textContent.includes("距离 12.0 世界单位 · 3 步") &&
    element("routeStatus").textContent.includes("下一格向东 · X 6.0 / Z 2.0"),
    "the checked-grid route reports endpoints, distance, steps, and next move");
  for (const [heading, label] of [[0, "屏幕下方"], [45, "屏幕左下方"], [90, "屏幕左侧"],
    [135, "屏幕左上方"], [180, "屏幕上方"], [225, "屏幕右上方"], [270, "屏幕右侧"], [315, "屏幕右下方"]]) {
    run(`trailState.points=[{sequence:1,captured_at:1,x:2,z:2,camera_heading:${heading}}];renderTrail()`);
    assert.ok(element("routeStatus").textContent.includes("按快照镜头朝向：" + label),
      "camera-relative next-step labels cover " + label);
    assert.ok(element("routeStatus").textContent.includes("下一格向东"),
      "camera-relative guidance keeps the world-coordinate bearing readable");
  }
  run('trailState.points=[{sequence:1,captured_at:1,x:2,z:2}];renderTrail()');
  assert.ok(element("routeStatus").textContent.includes("下一格向东") &&
    !element("routeStatus").textContent.includes("按快照镜头朝向"),
    "legacy route points keep world-coordinate direction without a camera hint");
  const realCameraDirection = context.CheckedRoutes.cameraRelativeDirection;
  context.CheckedRoutes.cameraRelativeDirection = undefined;
  run('trailState.points=[{sequence:1,captured_at:1,x:2,z:2,camera_heading:90}];renderTrail()');
  assert.ok(element("routeStatus").textContent.includes("下一格向东") &&
    !element("routeStatus").textContent.includes("按快照镜头朝向"),
    "a missing camera helper leaves the existing world-coordinate route guidance intact");
  context.CheckedRoutes.cameraRelativeDirection = realCameraDirection;
  run('trailState.points=[{sequence:1,captured_at:1,x:2,z:2,camera_heading:NaN}];renderTrail()');
  assert.ok(element("routeStatus").textContent.includes("下一格向东") &&
    !element("routeStatus").textContent.includes("按快照镜头朝向"),
    "an invalid in-memory heading cannot produce a camera hint");
  routeDestinationElement.value = "2,2";
  routeDestinationElement.listeners.change();
  run('trailState.points=[{sequence:1,captured_at:1,x:2,z:2,camera_heading:90}];renderTrail()');
  assert.equal(run("calculateCheckedRoute().status"), "arrived");
  assert.ok(!element("routeStatus").textContent.includes("按快照镜头朝向"),
    "an arrived route has no next-segment camera hint");
  routeDestinationElement.value = "2,6";
  routeDestinationElement.listeners.change();
  assert.ok(routeSvg.includes('class="checked-route"') && routeSvg.includes('class="checked-route-goal"'),
    "a found route and its goal render in the map even with both terrain overlays turned off");
  assert.ok(!routeSvg.includes('class="terrain-connection') && !routeSvg.includes('class="terrain-cell'),
    "route drawing is independent of the terrain and connection layer toggles");
  assert.equal(routeDestinationElement.value, "2,6", "a selected destination survives redraws for the same trail identity");
  const routeOptionWrites = routeDestinationElement.optionMarkupWrites;
  run("renderTrail()");
  assert.equal(routeDestinationElement.optionMarkupWrites, routeOptionWrites,
    "one-second trail redraws do not rebuild an unchanged destination menu");

  context.landmarkRouteRecords = [
    remembered("panflute", 1, 1, 1, 10, 1, 10),
    remembered("panflute", 3, 3, 1, 9, 1, 9),
    remembered("panflute", 11, 7, 1, 8, 1, 8),
    remembered("panflute", 15, 7, 1, 7, 1, 7),
    remembered("moonbase", 1, 1, 1, 6, 1, 6)
  ];
  run('state.target="panflute";trailState.landmarks=landmarkRouteRecords;renderTrail()');
  let landmarkButtons = [...element("seenLandmarksList").innerHTML.matchAll(/<button class="button seen-landmark-go"[\s\S]*?<\/button>/g)].map(match => match[0]);
  assert.equal(landmarkButtons.length, 4, "each of the four selected-target sightings gets a route action");
  assert.ok(!/\sdisabled>/.test(landmarkButtons[0]) && !/\sdisabled>/.test(landmarkButtons[1]),
    "two distinct sightings in one passable tile can both route to that tile");
  assert.ok(/\sdisabled>/.test(landmarkButtons[2]) && element("seenLandmarksList").innerHTML.includes("所在格不可通行"),
    "a target in a blocked tile is disabled with a clear reason");
  assert.ok(/\sdisabled>/.test(landmarkButtons[3]) && element("seenLandmarksList").innerHTML.includes("所在格未采集或通行状态未知"),
    "a target over unknown terrain is disabled instead of snapping to a neighbor");
  assert.ok(landmarkButtons[0].includes('aria-label="前往已见排箫第 1 处所在格 · X 1.0 / Z 1.0"'),
    "list actions have unique accessible names with the record coordinates");
  let landmarkSvg = element("trailSvg").innerHTML;
  assert.match(appHtml, /<svg class="trail-svg" id="trailSvg"[^>]*role="group" aria-label="[^"]+">/,
    "the named map is an accessible group so its interactive markers remain exposed to assistive technology");
  assert.equal((landmarkSvg.match(/class="trail-landmark-marker"[^>]*role="button"/g) || []).length, 2,
    "only sightings whose containing tile is checked passable are interactive map markers");
  assert.ok(landmarkSvg.includes("回车、空格或点击可前往所在格"), "interactive map markers explain their keyboard and pointer action");
  landmarkListSyntheticClick(0);
  assert.equal(routeDestinationElement.value, "2,2", "the list action selects the center of the sighting's containing tile");
  assert.equal(element("routeDestinationSource").textContent,
    "终点来自已见排箫：所记录位置 X 1.0 / Z 1.0 的格中心",
    "the route source identifies the exact remembered position even when another sighting shares its tile");
  landmarkButtons = [...element("seenLandmarksList").innerHTML.matchAll(/<button class="button seen-landmark-go"[\s\S]*?<\/button>/g)].map(match => match[0]);
  landmarkListSyntheticClick(1);
  assert.equal(element("routeDestinationSource").textContent,
    "终点来自已见排箫：所记录位置 X 3.0 / Z 3.0 的格中心",
    "a second record in the same cell keeps its own source coordinates");
  landmarkSvg = element("trailSvg").innerHTML;
  let markerIdentity = landmarkAttributes(landmarkSvg, 1);
  landmarkMapSyntheticEvent("click", markerIdentity);
  assert.equal(element("routeDestinationSource").textContent,
    "终点来自已见排箫：所记录位置 X 3.0 / Z 3.0 的格中心",
    "clicking an observed map marker uses the same checked-tile action");
  landmarkSvg = element("trailSvg").innerHTML;
  markerIdentity = landmarkAttributes(landmarkSvg, 0);
  let markerKeyPrevented = false;
  landmarkMapSyntheticEvent("keydown", markerIdentity, "Enter", () => { markerKeyPrevented = true; });
  assert.equal(markerKeyPrevented, true, "keyboard activation of an observed map marker prevents the default action");
  assert.equal(element("routeDestinationSource").textContent,
    "终点来自已见排箫：所记录位置 X 1.0 / Z 1.0 的格中心",
    "keyboard activation selects the exact sighting position");
  markerIdentity = landmarkAttributes(element("trailSvg").innerHTML, 1);
  let spacePrevented = false;
  landmarkMapSyntheticEvent("keydown", markerIdentity, " ", () => { spacePrevented = true; });
  assert.equal(spacePrevented, true, "Space activates an observed map marker for keyboard users");
  assert.equal(element("routeDestinationSource").textContent,
    "终点来自已见排箫：所记录位置 X 3.0 / Z 3.0 的格中心",
    "Space chooses the marker's exact sighting record");
  landmarkMapSyntheticEvent("click", landmarkAttributes(element("trailSvg").innerHTML, 0));
  const unknownLandmark = landmarkAttributes(landmarkListButton(3), 3);
  landmarkMapSyntheticEvent("click", unknownLandmark);
  assert.equal(element("routeDestinationSource").textContent,
    "终点来自已见排箫：所记录位置 X 1.0 / Z 1.0 的格中心",
    "unknown terrain cannot be selected even when a synthetic event supplies marker attributes");
  landmarkListSyntheticClick(2, true);
  assert.equal(element("routeDestinationSource").textContent,
    "终点来自已见排箫：所记录位置 X 1.0 / Z 1.0 的格中心",
    "disabled list actions cannot change the route");
  const blockedLandmark = landmarkAttributes(landmarkButtons[2], 2);
  landmarkMapSyntheticEvent("click", blockedLandmark);
  assert.equal(routeDestinationElement.value, "2,2", "even a forced stale map event rechecks the blocked cell and cannot select it");

  const staleLandmark = landmarkAttributes(element("trailSvg").innerHTML, 0);
  run("trailState.landmarks[1].last_sequence=30;renderTrail()");
  landmarkMapSyntheticEvent("click", staleLandmark);
  assert.equal(element("routeDestinationSource").textContent,
    "终点来自已见排箫：所记录位置 X 1.0 / Z 1.0 的格中心",
    "a late event after landmark ordering changes cannot select a different record at the same index");

  const landmarkListElement = element("seenLandmarksList");
  const landmarkSvgElement = element("trailSvg");
  const originalListQuery = landmarkListElement.querySelectorAll;
  const originalSvgQuery = landmarkSvgElement.querySelectorAll;
  const originalListContains = landmarkListElement.contains;
  const originalSvgContains = landmarkSvgElement.contains;
  let listFocusOptions = null, mapFocusOptions = null;
  const focusIdentity = run("landmarkIdentityToken()");
  const focusedListButton = {dataset: {landmarkPrefab: "panflute", landmarkX: "1", landmarkZ: "1", landmarkIdentity: focusIdentity},
    closest(selector) { return selector.startsWith(".seen-landmark-go") ? this : null; }};
  const nextListButton = {dataset: focusedListButton.dataset, disabled: false,
    focus(options) { listFocusOptions = options; }};
  landmarkListElement.contains = item => item === focusedListButton;
  landmarkListElement.querySelectorAll = selector => selector.startsWith(".seen-landmark-go") ? [nextListButton] : [];
  context.document.activeElement = focusedListButton;
  run("renderTrail()");
  assert.equal(listFocusOptions.preventScroll, true, "redrawing the sightings list restores keyboard focus to the same enabled record");
  const focusedMapMarker = {dataset: {landmarkPrefab: "panflute", landmarkX: "3", landmarkZ: "3", landmarkIdentity: focusIdentity},
    closest(selector) { return selector.startsWith(".trail-landmark-marker") ? this : null; }};
  const nextMapMarker = {dataset: focusedMapMarker.dataset, getAttribute(name) { return name === "role" ? "button" : null; },
    focus(options) { mapFocusOptions = options; }};
  landmarkSvgElement.contains = item => item === focusedMapMarker;
  landmarkSvgElement.querySelectorAll = selector => selector.startsWith(".trail-landmark-marker") ? [nextMapMarker] : [];
  context.document.activeElement = focusedMapMarker;
  run("renderTrail()");
  assert.equal(mapFocusOptions.preventScroll, true, "redrawing the SVG restores focus to the same enabled marker");
  let crossIdentityFocusCount = 0;
  landmarkListElement.querySelectorAll = () => [{dataset: {...focusedListButton.dataset,
    landmarkIdentity: JSON.stringify("focus-new-world")}, disabled: false, focus() { crossIdentityFocusCount += 1; }}];
  context.document.activeElement = focusedListButton;
  run('trailState.identity="focus-new-world";renderTrail()');
  assert.equal(crossIdentityFocusCount, 0, "focus is not restored onto a matching sighting in another world or session");
  delete context.document.activeElement;
  landmarkListElement.querySelectorAll = originalListQuery;
  landmarkSvgElement.querySelectorAll = originalSvgQuery;
  landmarkListElement.contains = originalListContains;
  landmarkSvgElement.contains = originalSvgContains;

  landmarkListSyntheticClick(0);
  routeDestinationElement.value = "6,2";
  routeDestinationElement.listeners.change();
  assert.equal(element("routeDestinationSource").hidden, true, "manual select changes clear the sighting source");
  landmarkListSyntheticClick(0);
  trailDestinationSyntheticEvent("click", 6, 6);
  assert.equal(routeDestinationElement.value, "6,6", "manual map-cell selection replaces a sighting-derived destination");
  assert.equal(element("routeDestinationSource").hidden, true, "manual map-cell selection clears the sighting source");
  landmarkListSyntheticClick(0);
  element("clearRouteDestinationButton").listeners.click();
  assert.equal(element("routeDestinationSource").hidden, true, "clearing the route removes its sighting source");

  landmarkListSyntheticClick(0);
  element("targetSelect").value = "moonbase";
  element("targetSelect").listeners.change();
  assert.equal(routeDestinationElement.value, "", "changing target type clears a sighting-derived route");
  assert.equal(element("routeDestinationSource").hidden, true, "changing target type clears the source explanation");
  routeDestinationElement.value = "6,6";
  routeDestinationElement.listeners.change();
  element("targetSelect").value = "panflute";
  element("targetSelect").listeners.change();
  assert.equal(routeDestinationElement.value, "6,6", "a manually selected cell route survives target-type changes");

  run('trailState.mode="history";trailState.identity="route-world\\u0000forest\\u0000landmark-history";trailState.points=[{sequence:1,captured_at:1,x:6,z:2}];trailState.terrainTiles=checkedRouteFixture;trailState.landmarks=landmarkRouteRecords;state.target="panflute";renderTrail()');
  landmarkListSyntheticClick(0);
  assert.equal(routeDestinationElement.value, "2,2", "historical sightings can choose their recorded passable tile");
  assert.ok(!element("routeDestinationSource").hidden, "historical sighting choices display their source");
  context.checkedRouteFixture[0].passable = false;
  run("renderTrail()");
  assert.equal(routeDestinationElement.value, "2,2", "a source-derived destination stays selected if its tile later becomes blocked");
  assert.ok(!element("routeDestinationSource").hidden && element("routeStatus").textContent.includes("终点格中心不可通行"),
    "blocked historical destinations keep their source and report their current route state");
  context.checkedRouteFixture[0].passable = true;
  run("trailState.terrainTiles=checkedRouteFixture.slice(1);renderTrail()");
  assert.equal(routeDestinationElement.value, "2,2", "a cropped source-derived destination is not silently replaced");
  assert.ok(!element("routeDestinationSource").hidden, "a cropped destination keeps its source explanation");
  run('trailState.terrainTiles=checkedRouteFixture;trailState.identity="route-world\\u0000forest\\u0000landmark-history-next";renderTrail()');
  assert.equal(routeDestinationElement.value, "", "changing history identity clears the sighting-derived destination");
  assert.ok(element("routeDestinationSource").hidden, "changing history identity clears the source explanation");

  context.injectedRoutePrefab = "<img src=x onerror=boom>";
  run('state.target=injectedRoutePrefab;trailState.landmarks=[{prefab:injectedRoutePrefab,x:1,z:1,first_seen:1,last_seen:1,first_sequence:1,last_sequence:1}];renderTrail();selectSeenLandmarkRoute(0,trailRenderRevision,injectedRoutePrefab,"1","1")');
  assert.ok(element("seenLandmarksList").innerHTML.includes("&lt;img src=x onerror=boom&gt;"),
    "untrusted prefab names are escaped in landmark action markup");
  assert.equal(element("routeDestinationSource").textContent,
    "终点来自已见<img src=x onerror=boom>：所记录位置 X 1.0 / Z 1.0 的格中心",
    "the selected source is written as text, never interpreted as HTML");
  assert.ok(!element("routeDestinationSource").innerHTML.includes("onerror"), "source content cannot inject markup");

  run('state.target="panflute";trailState.mode="live";trailState.identity="route-world\\u0000forest\\u0000route-session";trailState.points=[{sequence:2,captured_at:2,x:6,z:2}];trailState.landmarks=[];acceptRouteFreshness(trailState.identity,2,0);renderTrail()');
  assert.equal(routeDestinationElement.value, "", "switching back to the live identity starts without a historical destination");
  routeDestinationElement.value = "2,6";
  routeDestinationElement.listeners.change();
  run('trailState.points=[{sequence:2,captured_at:2,x:6,z:2}];renderTrail()');
  assert.ok(element("routeStatus").textContent.includes("起点 X 6.0 / Z 2.0") &&
    element("routeStatus").textContent.includes("距离 8.0 世界单位 · 2 步") &&
    element("routeStatus").textContent.includes("下一格向北 · X 6.0 / Z 6.0"),
    "moving the player to the middle tile recalculates the remaining route");
  context.checkedRouteFixture[1].connections.north = false;
  run("renderTrail()");
  assert.ok(element("routeStatus").textContent.includes("未连通") &&
    !element("trailSvg").innerHTML.includes('class="checked-route"'),
    "changing a checked edge to blocked removes the stale path and reports an unconnected route");
  context.checkedRouteFixture[1].connections.north = true;
  context.checkedRouteFixture[3].passable = false;
  run("renderTrail()");
  assert.ok(element("routeStatus").textContent.includes("终点格中心不可通行") &&
    routeDestinationElement.value === "2,6" && routeDestinationElement.innerHTML.includes("当前不可通行"),
    "a blocked destination stays selected and is reported instead of silently replaced");
  delete context.checkedRouteFixture[3].passable;
  run("renderTrail()");
  assert.ok(element("routeStatus").textContent.includes("终点格中心没有可用") &&
    routeDestinationElement.value === "2,6", "an unknown destination remains selected and is not treated as walkable");
  context.checkedRouteFixture[3].passable = true;
  run('trailState.mode="history";trailState.points=[{sequence:3,captured_at:3,x:3,z:3,player_anchor:{x:2,z:2,clear:true}}];renderTrail()');
  let playerRoute = JSON.parse(run("JSON.stringify(calculateCheckedRoute())"));
  assert.equal(playerRoute.origin, "player");
  assert.deepEqual(playerRoute.path, [{x:3,z:3},{x:2,z:2},{x:6,z:2},{x:6,z:6},{x:2,z:6}],
    "the projected player route begins at the actual location before the checked grid path");
  assert.equal(playerRoute.steps, 3);
  assert.equal(playerRoute.anchor_distance, Math.SQRT2);
  assert.equal(playerRoute.grid_distance, 12);
  assert.equal(playerRoute.distance, 12 + Math.SQRT2);
  assert.deepEqual(playerRoute.next, {kind:"anchor",direction:"southwest",x:2,z:2});
  routeSvg = element("trailSvg").innerHTML;
  assert.ok(element("routeStatus").textContent.includes("已找到玩家位置路线") &&
    element("routeStatus").textContent.includes("总距离 13.4 世界单位 · 格网步数 3") &&
    element("routeStatus").textContent.includes("先到所在格中心 · 向西南 · X 2.0 / Z 2.0"),
    "player-origin route status shows total distance, grid steps, and the center approach bearing");
  assert.ok(routeSvg.includes("玩家位置路线 · 玩家位置到所在格中心后接已检查格中心连接") &&
    appHtml.includes("采集到当前位置检查后，路线从玩家位置出发；终点为所选格中心。"), "the route layer and note identify the actual origin and center destination");

  run('trailState.points=[{sequence:4,captured_at:4,x:6.5,z:3,player_anchor:{x:6,z:2,clear:true}}];renderTrail()');
  playerRoute = JSON.parse(run("JSON.stringify(calculateCheckedRoute())"));
  assert.equal(playerRoute.steps, 2);
  assert.equal(playerRoute.distance, 8 + Math.hypot(0.5, 1), "movement to another cell recomputes the remaining total distance");
  assert.deepEqual(playerRoute.next, {kind:"anchor",direction:"southwest",x:6,z:2});

  routeDestinationElement.value = "2,2";
  routeDestinationElement.listeners.change();
  run('trailState.points=[{sequence:5,captured_at:5,x:3,z:3,player_anchor:{x:2,z:2,clear:true}}];renderTrail()');
  playerRoute = JSON.parse(run("JSON.stringify(calculateCheckedRoute())"));
  assert.equal(playerRoute.status, "found", "being inside the destination tile does not count as arrival before its center");
  assert.deepEqual(playerRoute.path, [{x:3,z:3},{x:2,z:2}]);
  assert.equal(playerRoute.steps, 0);
  assert.deepEqual(playerRoute.next, {kind:"anchor",direction:"southwest",x:2,z:2});
  assert.ok(element("routeStatus").textContent.includes("格网步数 0"));

  routeDestinationElement.value = "2,6";
  routeDestinationElement.listeners.change();
  run('trailState.points=[{sequence:6,captured_at:6,x:3,z:3,player_anchor:{x:2,z:2,clear:false}}];renderTrail()');
  assert.ok(element("routeStatus").textContent.includes("玩家位置路线 · 玩家当前位置到所在格中心的检查受阻") &&
    !element("trailSvg").innerHTML.includes('class="checked-route"'),
    "a failed player-anchor check never falls back to an unchecked line");
  run('trailState.points=[{sequence:7,captured_at:7,x:3,z:3,player_anchor:{x:6,z:2,clear:true}}];renderTrail()');
  assert.ok(element("routeStatus").textContent.includes("采集到的当前位置检查未知") &&
    !element("trailSvg").innerHTML.includes('class="checked-route"'),
    "an anchor that names a different tile is unknown and draws no route segment");
  run('trailState.points=[{sequence:8,captured_at:8,x:3,z:3}];renderTrail()');
  assert.ok(element("routeStatus").textContent.includes("已找到格中心路线") &&
    element("routeStatus").textContent.includes("起点 X 2.0 / Z 2.0") &&
    !element("routeStatus").textContent.includes("玩家位置路线"),
    "legacy points without an anchor retain the original grid-center route mode");

  trailDestinationSyntheticEvent("click", 6, 2);
  assert.equal(routeDestinationElement.value, "6,2", "one delegated SVG click selects a passable map tile");
  let keyPrevented = false;
  trailDestinationSyntheticEvent("keydown", 2, 6, "Enter", () => { keyPrevented = true; });
  assert.equal(routeDestinationElement.value, "2,6", "keyboard activation selects a terrain tile");
  assert.equal(keyPrevented, true, "keyboard activation prevents the browser's default key action");
  trailDestinationSyntheticEvent("click", 10, 6);
  trailDestinationSyntheticEvent("keydown", 14, 6, "Enter");
  assert.equal(routeDestinationElement.value, "2,6", "late events from blocked or unknown cells keep the current destination");
  assert.equal((element("trailSvg").listeners.click ? 1 : 0) + (element("trailSvg").listeners.keydown ? 1 : 0), 2,
    "map destination selection uses one delegated click and key listener");

  run('state.target="panflute";trailState.landmarks=[{prefab:"panflute",x:2,z:6,first_seen:1,last_seen:1,first_sequence:1,last_sequence:1}];trailState.mode="history";trailState.identity="route-world\u0000forest\u0000history-two";trailState.points=[{sequence:1,captured_at:1,x:2,z:2},{sequence:2,captured_at:2,x:6,z:2},{sequence:3,captured_at:3,x:2,z:2}];renderTrail()');
  assert.equal(routeDestinationElement.value, "", "switching trail identity clears the selected destination");
  assert.ok(element("routeStatus").textContent.includes("请选择路线终点"), "a new history identity starts without the previous goal");
  routeDestinationElement.value = "2,6";
  routeDestinationElement.listeners.change();
  assert.ok(element("routeStatus").textContent.includes("已找到格中心路线"), "historical points without anchors keep the legacy route mode");
  run('trailState.points[2]={sequence:3,captured_at:3,x:3,z:3,player_anchor:{x:2,z:2,clear:true}};renderTrail()');
  assert.ok(element("routeStatus").textContent.includes("已找到玩家位置路线"),
    "historical trail points with a checked player anchor use the actual-position route mode");
  routeSvg = element("trailSvg").innerHTML;
  assert.ok(routeSvg.indexOf('class="checked-route"') > routeSvg.indexOf('class="trail-route"') &&
    routeSvg.indexOf('class="checked-route-goal"') > routeSvg.lastIndexOf('class="trail-landmark-marker"'),
    "the purple checked route overlays the green history trail and the goal ring is drawn after observed landmarks");
  assert.ok(routeSvg.includes('class="checked-route-goal" cx="') && routeSvg.includes('r="10"'),
    "the goal uses a visible 10-unit hollow ring when it overlaps a landmark");
  run('trailState.mode="idle";renderTrail()');
  assert.ok(element("trailStatus").textContent.includes("实时跟随已暂停") &&
    !element("trailSvg").innerHTML.includes('class="checked-route"') &&
    element("trailSvg").innerHTML.includes('class="checked-route-goal"') &&
    element("routeStatus").textContent.includes("实时导航已暂停") &&
    element("routeStatus").textContent.includes("最后观测位置"),
    "a paused live trail keeps its goal and labels the retained location while suppressing route guidance");
  assert.ok(!element("routeStatus").textContent.includes("实时观测"), "route status does not label retained data as fresh");
  run('trailState.identity="another-world-session";renderTrail()');
  assert.equal(routeDestinationElement.value, "", "a session or world identity change clears the old destination");
  element("clearRouteDestinationButton").listeners.click();
  assert.equal(routeDestinationElement.value, "", "the clear button removes the route destination");

  routeDestinationElement.value = '2,6" onload="boom';
  routeDestinationElement.listeners.change();
  assert.equal(routeDestinationElement.value, "", "malformed select values cannot become SVG coordinates");
  assert.ok(!element("trailSvg").innerHTML.includes("onload=\"boom"), "route controls do not inject HTML from a destination value");
  routeDestinationElement.value = "1e308,-1e308";
  routeDestinationElement.listeners.change();
  routeSvg = element("trailSvg").innerHTML;
  assert.ok(!/NaN|Infinity/.test(routeSvg), "finite extreme route coordinates never serialize NaN or Infinity into SVG");
  assert.ok(routeSvg.includes("checked-route-goal"), "an off-map selected destination remains visible in the shared projection");

  run('checkedRouteSelection.destination=null;trailState.terrainTiles=Array.from({length:2501},(_,index)=>({x:2+index*4,z:2,passable:true}));updateCheckedRouteDestinations()');
  assert.equal((routeDestinationElement.innerHTML.match(/<option /g) || []).length, 2501,
    "the selector caps the passable destination list at 2500 plus its placeholder");
  assert.ok(routeDestinationElement.innerHTML.startsWith('<option value="">选择终点</option>'),
    "the placeholder stays at the top after a large map update");

  const liveRouteTerrain = [
    {x: 2, z: 2, tile: "GRASS", passable: true, connections: {east: true}},
    {x: 6, z: 2, tile: "FOREST", passable: true, connections: {north: true}},
    {x: 6, z: 6, tile: "ROCKY", passable: true},
    {x: 2, z: 6, tile: "MARSH", passable: true, connections: {east: true}}
  ];
  function liveRouteFrame(sequence, options = {}) {
    const reply = frame(options.session || "fresh-session", sequence, null, options.world || "fresh-world", {
      worldKind: options.worldKind || "forest", x: options.x ?? 2, z: options.z ?? 2,
      capturedAt: 100 + sequence, terrain: {tile_size: 4, tiles: liveRouteTerrain},
      ...(Object.prototype.hasOwnProperty.call(options, "cameraHeading") ? {camera_heading: options.cameraHeading} : {})
    });
    reply.status = options.status || "live";
    reply.age_seconds = options.age ?? 0.5;
    return reply;
  }
  context.routeTestNow = 10000;
  run(`pauseRouteNavigation("waiting",false);state.target="panflute";state.liveRecording=null;state.explorations=[];
    live.following=true;liveEl.follow.checked=true;live.key=null;live.sequence=0;
    trailState.mode="live";trailState.identity=null;trailState.id=null;trailState.summary=null;trailState.points=[];
    trailState.landmarks=[];trailState.terrainTiles=[];trailState.terrainAvailable=false;trailState.terrainError="";
    trailState.live={identity:null,id:null,localPoints:[],storedPoints:[],trimmed:false,localLandmarks:[],storedLandmarks:[],
      landmarksTruncated:false,landmarkError:"",localTerrain:[],storedTerrain:[],localTerrainAvailable:false,
      storedTerrainAvailable:false,terrainTruncated:false,terrainError:""};`);
  context.liveRouteReply = liveRouteFrame(1, {cameraHeading: 0});
  run("applyLiveResult(liveRouteReply)");
  run(`checkedRouteSelection.identity=trailState.identity;checkedRouteSelection.destination={x:2,z:6};
    checkedRouteSelection.source={prefab:"panflute",x:2,z:6};el.routeDestination.value="2,6";renderTrail()`);
  assert.ok(element("trailSvg").innerHTML.includes('class="checked-route"') &&
    element("routeStatus").textContent.includes("下一格向东") &&
    element("routeStatus").textContent.includes("按快照镜头朝向：屏幕下方"),
    "an accepted fresh live snapshot enables the route and its next-step hint");
  assert.equal(element("routeDestinationSource").textContent,
    "终点来自已见排箫：所记录位置 X 2.0 / Z 6.0 的格中心");
  context.liveRouteReply = liveRouteFrame(1, {cameraHeading: 90});
  run("applyLiveResult(liveRouteReply)");
  assert.deepEqual(JSON.parse(run("JSON.stringify(trailState.points.slice(-1).map(point=>({x:point.x,z:point.z,heading:point.camera_heading})))")),
    [{x: 2, z: 2, heading: 90}], "a same-sequence camera update replaces heading while the player stays still");
  assert.ok(element("routeStatus").textContent.includes("下一格向东") &&
    element("routeStatus").textContent.includes("按快照镜头朝向：屏幕左侧"),
    "a same-position live camera rotation redraws the next-step hint");

  context.fetch = async () => { throw new Error("offline"); };
  await run("pollLive()");
  assert.ok(!element("trailSvg").innerHTML.includes('class="checked-route"') &&
    element("trailSvg").innerHTML.includes('class="checked-route-goal"') &&
    element("routeStatus").textContent.includes("连接暂时中断") &&
    !element("routeStatus").textContent.includes("下一格") &&
    !element("routeStatus").textContent.includes("按快照镜头朝向") &&
    routeDestinationElement.value === "2,6" && !element("routeDestinationSource").hidden,
    "an error pauses the route while preserving its endpoint and source");
  run('unavailableLive("尚未连接日志","disabled")');
  assert.ok(element("routeStatus").textContent.includes("实时采集未启用") &&
    !element("trailSvg").innerHTML.includes('class="checked-route"') && routeDestinationElement.value === "2,6",
    "a disabled collector pauses guidance while keeping the selected endpoint");
  context.liveRouteReply = liveRouteFrame(2);
  run("applyLiveResult(liveRouteReply)");
  assert.ok(element("trailSvg").innerHTML.includes('class="checked-route"'),
    "a later fresh snapshot restores route guidance after an error");

  context.routeTestNow += 4900;
  context.liveRouteReply = liveRouteFrame(2, {age: 0.1});
  run("applyLiveResult(liveRouteReply)");
  assert.ok(element("routeStatus").textContent.includes("快照已超过五秒") &&
    !element("trailSvg").innerHTML.includes('class="checked-route"'),
    "a repeated sequence cannot reset freshness when its accepted age plus elapsed time exceeds five seconds");
  context.liveRouteReply = liveRouteFrame(3, {age: 0.2});
  run("applyLiveResult(liveRouteReply)");
  assert.ok(element("trailSvg").innerHTML.includes('class="checked-route"'),
    "a newer fresh sequence restores route guidance");

  let resolveHeldLive;
  context.fetch = () => new Promise(resolve => { resolveHeldLive = resolve; });
  const heldLivePoll = run("pollLive()");
  const firstExpiry = run("routeFreshness.timer");
  context.routeTestNow += 4700;
  fireScheduledTimer(firstExpiry);
  assert.ok(element("trailSvg").innerHTML.includes('class="checked-route"'),
    "the route remains active while the accepted snapshot is still within five seconds");
  const finalExpiry = run("routeFreshness.timer");
  context.routeTestNow += 200;
  fireScheduledTimer(finalExpiry);
  assert.ok(!element("trailSvg").innerHTML.includes('class="checked-route"') &&
    element("trailSvg").innerHTML.includes('class="checked-route-goal"') &&
    element("routeStatus").textContent.includes("快照已超过五秒") &&
    !element("routeStatus").textContent.includes("下一格") &&
    element("routeDestinationSource").textContent.includes("终点来自已见排箫") &&
    element("livePosition").textContent.includes("最后观测位置") &&
    run("state.result") === null,
    "a held live request expires locally, removes the purple route and next hint, and retains the goal, source, and last position");

  run('trailState.mode="history";renderTrail()');
  assert.ok(element("trailSvg").innerHTML.includes('class="checked-route"') &&
    element("routeStatus").textContent.includes("已找到格中心路线"),
    "history replay routes use their recorded last position even while live freshness is paused");
  run('state.result={directions:[{direction:"east",score:7}]};trailState.mode="live";live.following=true;stopLive()');
  assert.ok(element("routeStatus").textContent.includes("实时跟随已暂停") &&
    !element("trailSvg").innerHTML.includes('class="checked-route"') &&
    !element("routeStatus").textContent.includes("按快照镜头朝向") &&
    routeDestinationElement.value === "2,6" && !element("routeDestinationSource").hidden,
    "manually stopping live following pauses guidance and keeps the selected endpoint and source");
  resolveHeldLive(apiResponse(liveRouteFrame(4)));
  await heldLivePoll;

  let resolveResumeLive;
  context.fetch = () => new Promise(resolve => { resolveResumeLive = resolve; });
  element("liveFollow").checked = true;
  element("liveFollow").listeners.change();
  assert.ok(run("live.following") && run("state.result") === null &&
    element("resultsArea").innerHTML.includes("正在连接实时采集") &&
    element("routeStatus").textContent.includes("正在等待有效快照") &&
    !element("trailSvg").innerHTML.includes('class="checked-route"'),
    "resuming while the live request is pending clears old room and task directions until fresh data arrives");
  resolveResumeLive(apiResponse({status: "waiting"}));
  await new Promise(resolve => setImmediate(resolve));
  assert.ok(run("live.following") && element("routeStatus").textContent.includes("正在等待有效快照") &&
    !element("trailSvg").innerHTML.includes('class="checked-route"'),
    "resuming live following waits for a fresh snapshot before restoring the route");
  context.liveRouteReply = liveRouteFrame(4);
  run("applyLiveResult(liveRouteReply)");
  assert.ok(element("trailSvg").innerHTML.includes('class="checked-route"'),
    "a fresh snapshot after resuming restores live route guidance");
  context.liveRouteReply = liveRouteFrame(3);
  run("applyLiveResult(liveRouteReply)");
  assert.ok(element("routeStatus").textContent.includes("倒序观测") &&
    !element("trailSvg").innerHTML.includes('class="checked-route"') &&
    routeDestinationElement.value === "2,6" && !element("routeDestinationSource").hidden,
    "an out-of-order snapshot cannot clear the paused state or the selected endpoint source");
  run("stopLive()");

  run(`live.following=true;liveEl.follow.checked=true;live.key=null;live.sequence=0;trailState.mode="live";
    trailState.live={identity:null,id:null,localPoints:[],storedPoints:[],trimmed:false,localLandmarks:[],storedLandmarks:[],
      landmarksTruncated:false,landmarkError:"",localTerrain:[],storedTerrain:[],localTerrainAvailable:false,
      storedTerrainAvailable:false,terrainTruncated:false,terrainError:""};state.liveRecording=null;`);
  context.liveRouteReply = liveRouteFrame(1, {world: "fresh-cave", session: "cave-session", worldKind: "cave", status: "unsupported_world", age: 0.4});
  run("applyLiveResult(liveRouteReply)");
  run(`checkedRouteSelection.identity=trailState.identity;checkedRouteSelection.destination={x:2,z:6};
    checkedRouteSelection.source={prefab:"panflute",x:2,z:6};el.routeDestination.value="2,6";renderTrail()`);
  assert.ok(run('routeFreshness.status') === "fresh" &&
    element("trailSvg").innerHTML.includes('class="checked-route"') &&
    element("routeStatus").textContent.includes("下一格向东"),
    "a fresh unsupported-world cave position still supports the checked grid route");
  const caveExpiry = run("routeFreshness.timer");
  context.routeTestNow += 4700;
  fireScheduledTimer(caveExpiry);
  assert.ok(!element("trailSvg").innerHTML.includes('class="checked-route"') &&
    element("routeStatus").textContent.includes("快照已超过五秒") &&
    routeDestinationElement.value === "2,6" && !element("routeDestinationSource").hidden,
    "a cave route pauses when its last accepted position ages past five seconds");
  run("stopLive()");

  const deadlineWorld = "deadline-world";
  const deadlineSession = "deadline-session";
  run('state.target="panflute";state.seed="17";live.following=true;liveEl.follow.checked=true;live.key=null;live.sequence=0;trailState.mode="live";');
  context.liveRouteReply = liveRouteFrame(1, {world: deadlineWorld, session: deadlineSession});
  run("applyLiveResult(liveRouteReply)");
  run('checkedRouteSelection.identity=trailState.identity;checkedRouteSelection.destination={x:2,z:6};checkedRouteSelection.source={prefab:"panflute",x:2,z:6};el.routeDestination.value="2,6";renderTrail()');
  assert.ok(element("trailSvg").innerHTML.includes('class="checked-route"'), "the deadline cases start from an active live route");

  let resolveLateFetch;
  let resolveRetryFetch;
  const deadlineUrls = [];
  context.fetch = url => {
    deadlineUrls.push(url);
    if (deadlineUrls.length === 1) return new Promise(resolve => { resolveLateFetch = resolve; });
    if (deadlineUrls.length === 2) return new Promise(resolve => { resolveRetryFetch = resolve; });
    throw new Error("unexpected live request " + url);
  };
  const timedOutFetch = run("pollLive()");
  const fetchDeadline = run("live.requestTimeoutTimer");
  assert.equal(scheduledTimers.get(fetchDeadline).delay, 5000, "the live request deadline is five seconds");
  assert.ok(deadlineUrls[0].includes("target=panflute") && deadlineUrls[0].includes("seed=17"));
  fireScheduledTimer(fetchDeadline);
  await timedOutFetch;
  assert.ok(element("liveStatus").textContent.includes("实时请求超时，正在重试") &&
    !element("trailSvg").innerHTML.includes('class="checked-route"') &&
    element("trailSvg").innerHTML.includes('class="checked-route-goal"') &&
    routeDestinationElement.value === "2,6" && !element("routeDestinationSource").hidden,
    "a hung fetch pauses route guidance with a retry message while preserving its endpoint and source");
  assert.equal(run("live.requestTimeoutTimer"), null, "the request deadline is cleared after timeout");
  const fetchRetry = run("live.timer");
  assert.equal(scheduledTimers.get(fetchRetry).delay, 1000, "a timed-out request reuses the one-second poll cadence");
  fireScheduledTimer(fetchRetry);
  assert.equal(deadlineUrls.length, 2, "the collector request retries automatically");
  resolveLateFetch(apiResponse(liveRouteFrame(2, {world: deadlineWorld, session: deadlineSession})));
  await settle();
  assert.ok(element("liveStatus").textContent.includes("实时请求超时") &&
    !element("trailSvg").innerHTML.includes('class="checked-route"') && run("state.result") === null,
    "a late success from the timed-out fetch cannot replace the paused view");
  const retryDeadline = run("live.requestTimeoutTimer");
  resolveRetryFetch(apiResponse(liveRouteFrame(3, {world: deadlineWorld, session: deadlineSession})));
  await settle();
  assert.ok(element("trailSvg").innerHTML.includes('class="checked-route"') &&
    element("routeStatus").textContent.includes("下一格向东"),
    "a fresh response from the automatic retry restores the route");
  assert.equal(run("live.requestTimeoutTimer"), null);
  assert.equal(scheduledTimers.has(retryDeadline), false, "a successful response clears its deadline timer");

  let resolveLateBody;
  context.fetch = () => ({ok: true, json: () => new Promise(resolve => { resolveLateBody = resolve; })});
  const timedOutBody = run("pollLive()");
  await settle();
  const bodyDeadline = run("live.requestTimeoutTimer");
  assert.ok(resolveLateBody && scheduledTimers.get(bodyDeadline).delay === 5000,
    "the same deadline stays active while the JSON response body is being read");
  fireScheduledTimer(bodyDeadline);
  await timedOutBody;
  assert.ok(element("liveStatus").textContent.includes("实时请求超时") &&
    !element("trailSvg").innerHTML.includes('class="checked-route"'),
    "a hanging response body also pauses live guidance");
  resolveLateBody(liveRouteFrame(4, {world: deadlineWorld, session: deadlineSession}));
  await settle();
  assert.equal(run("state.result"), null, "a late JSON body cannot apply after its request timed out");
  run("stopLive()");
  assert.equal(run("live.timer"), null, "stopping clears the retry scheduled after a timeout");
  assert.equal(run("live.requestTimeoutTimer"), null);

  let resolveChangedInput;
  const changedInputUrls = [];
  context.fetch = url => {
    changedInputUrls.push(url);
    if (changedInputUrls.length === 1) return new Promise(resolve => { resolveChangedInput = resolve; });
    return Promise.resolve(apiResponse({status: "waiting"}));
  };
  element("liveFollow").checked = true;
  run('live.following=true;liveEl.follow.checked=true;resumeLiveTrailView();clearLiveRecommendations("正在连接实时采集…")');
  const changedInputPoll = run("pollLive()");
  const changedInputDeadline = run("live.requestTimeoutTimer");
  element("targetSelect").value = "moonbase";
  element("targetSelect").listeners.change();
  element("seedInput").value = "41";
  element("seedInput").listeners.input();
  fireScheduledTimer(changedInputDeadline);
  await changedInputPoll;
  assert.equal(element("liveStatus").textContent, "正在连接实时采集…",
    "a request for an old target or seed cannot pause the updated view when it times out");
  resolveChangedInput(apiResponse(liveRouteFrame(4, {world: deadlineWorld, session: deadlineSession})));
  await settle();
  assert.equal(element("liveStatus").textContent, "正在连接实时采集…",
    "a late response from the old target and seed remains ignored");
  const changedInputRetry = run("live.timer");
  fireScheduledTimer(changedInputRetry);
  assert.ok(changedInputUrls[1] && changedInputUrls[1].includes("target=moonbase") && changedInputUrls[1].includes("seed=41"),
    "the next poll uses the current target and seed: " + JSON.stringify(changedInputUrls));
  await settle();
  assert.equal(element("liveStatus").textContent, "正在等待采集器输出，请进入世界并启用客户端 mod。");
  run("stopLive()");

  let rejectObsoleteFetch;
  let resolveCurrentFetch;
  let generationCalls = 0;
  context.fetch = () => {
    generationCalls += 1;
    if (generationCalls === 1) return new Promise((resolve, reject) => { rejectObsoleteFetch = reject; });
    return new Promise(resolve => { resolveCurrentFetch = resolve; });
  };
  run('live.following=true;liveEl.follow.checked=true;resumeLiveTrailView();clearLiveRecommendations("正在连接实时采集…")');
  const obsoletePoll = run("pollLive()");
  const obsoleteDeadline = run("live.requestTimeoutTimer");
  fireScheduledTimer(obsoleteDeadline);
  const currentPoll = run("pollLive()");
  await obsoletePoll;
  assert.equal(element("liveStatus").textContent, "正在连接实时采集…",
    "an obsolete timeout cannot pause a newer live request");
  assert.equal(run("live.timer"), null, "an obsolete poll does not schedule a second retry");
  resolveCurrentFetch(apiResponse(liveRouteFrame(5, {world: deadlineWorld, session: deadlineSession})));
  await currentPoll;
  await settle();
  const freshGenerationStatus = element("liveStatus").textContent;
  const freshGenerationRetry = run("live.timer");
  assert.ok(freshGenerationStatus.includes("实时更新 · 观测 5") &&
    run("routeFreshness.status") === "fresh" && run("routeFreshness.sequence") === 5,
    "the current generation accepts its fresh response");
  rejectObsoleteFetch(new Error("late obsolete error"));
  await settle();
  assert.equal(element("liveStatus").textContent, freshGenerationStatus,
    "an obsolete error arriving after the fresh response cannot replace it");
  assert.equal(run("routeFreshness.status"), "fresh");
  assert.equal(run("routeFreshness.sequence"), 5);
  assert.equal(run("live.timer"), freshGenerationRetry,
    "an obsolete error cannot cancel the current poll cadence");

  let resolveStoppedFetch;
  context.fetch = () => new Promise(resolve => { resolveStoppedFetch = resolve; });
  const resultBeforeStop = run("JSON.stringify(state.result)");
  const stoppedPoll = run("pollLive()");
  run("stopLive()");
  await stoppedPoll;
  assert.equal(run("live.requestTimeoutTimer"), null, "manual stop cancels the deadline");
  assert.equal(run("live.timer"), null, "manual stop does not schedule another poll");
  resolveStoppedFetch(apiResponse(liveRouteFrame(6, {world: deadlineWorld, session: deadlineSession})));
  await settle();
  assert.equal(run("JSON.stringify(state.result)"), resultBeforeStop,
    "a late response after manual stop cannot update observations");

  const deadlineHistory = replaySummary("9".repeat(64), {worldId: "deadline-history", session: "deadline-history-session"});
  let resolveHistoryFetch;
  context.fetch = url => {
    if (url.startsWith("/api/live?")) return new Promise(resolve => { resolveHistoryFetch = resolve; });
    if (url === "/api/explorations/" + deadlineHistory.id + "/trail") {
      return Promise.resolve(apiResponse(trailPayload(deadlineHistory, [trailPoint(0, 50, 70, 80)])));
    }
    throw new Error("unexpected fetch " + url);
  };
  run('live.following=true;liveEl.follow.checked=true;resumeLiveTrailView()');
  const historyPendingPoll = run("pollLive()");
  run("openExplorationTrail(" + JSON.stringify(deadlineHistory) + ")");
  await historyPendingPoll;
  await settle();
  assert.equal(run("trailState.mode"), "history");
  assert.equal(run("live.requestTimeoutTimer"), null, "opening history cancels the live deadline");
  resolveHistoryFetch(apiResponse(liveRouteFrame(7, {world: deadlineWorld, session: deadlineSession})));
  await settle();
  assert.equal(run("trailState.mode"), "history");
  assert.equal(run("trailState.points[0].x"), 70,
    "a late live response cannot replace history after the user opens a replay");
  assert.equal(run("live.timer"), null, "history does not leave a live retry running");


  // Map follow/zoom keeps nearby navigation readable on long explorations.
  context.vpProjectionPoints = [trailPoint(1, 1, 0, 0), trailPoint(2, 2, 1000, 20)];
  const vpFull = run("projectTrailCoordinates(vpProjectionPoints)");
  const vpFollow = run("projectTrailCoordinates(vpProjectionPoints,[],[],null,null,{mode:'follow',span:64})");
  assert.equal(vpFull.viewport, null, "full map keeps its original automatic projection");
  assert.equal(vpFollow.viewport.center_x, 1000);
  assert.equal(vpFollow.viewport.center_z, 20);
  assert.equal(vpFollow.viewport.span_z, 64);
  assert.ok(Math.abs(vpFollow.viewport.span_x - 64 * 292 / 165) < 1e-9);
  assert.equal(vpFollow.points[1].x, 180);
  assert.equal(vpFollow.points[1].y, 107.5);
  assert.ok(vpFollow.scale > vpFull.scale * 5, "distant history does not shrink the local view");
  assert.deepEqual(JSON.parse(JSON.stringify(vpFollow.ranges)), JSON.parse(JSON.stringify(vpFull.ranges)),
    "local zoom preserves the recorded data bounds");
  assert.equal(run("projectTrailCoordinates(vpProjectionPoints,[],[],null,null,{mode:'follow',span:32}).scale"), vpFollow.scale * 2);
  assert.equal(run("projectTrailCoordinates([],[],[],null,null,{mode:'follow',span:64}).viewport"), null);
  assert.equal(run("projectTrailCoordinates([{x:-1e308,z:0},{x:1e308,z:0}],[],[],null,null,{mode:'follow',span:64}).error"), true);

  const vpHistory = replaySummary("e".repeat(64), {worldId: "viewport-world", session: "viewport-history", frames: 2});
  const vpPoints = [trailPoint(1, 1, 0.25, 0.25), trailPoint(2, 2, 1000.25, 20.25, {x:1000,z:20,clear:true})];
  const vpTiles = [terrainCell(0,0,"GRASS",1,1,true),
    terrainCell(1000,20,"GRASS",2,2,true,{east:true}), terrainCell(1004,20,"GRASS",2,2,true)];
  const vpLandmarks = [remembered("panflute",0.5,0.5,1,1), remembered("panflute",1004.5,20.5,2,2)];
  let vpHistoryPoints = vpPoints;
  context.vpHistory = vpHistory;
  context.fetch = async url => {
    assert.equal(url, "/api/explorations/" + vpHistory.id + "/trail");
    return apiResponse(trailPayload(vpHistory, vpHistoryPoints, vpLandmarks, false, {tile_size:4,tiles:vpTiles,truncated:false}));
  };
  run('stopLive();state.target="panflute";el.target.value="panflute";openExplorationTrail(vpHistory)');
  await settle();
  element("terrainToggle").checked = true;
  run("renderTrail()");
  assert.equal(run("trailViewport.mode"), "all");
  assert.equal(element("viewportFollowButton").disabled, false);
  assert.equal(element("viewportZoomInButton").disabled, false, "zoom is available directly from full map");
  assert.equal(run("setTrailViewportMode('invalid')"), false);
  assert.equal(run("zoomTrailViewport(0)"), false);
  element("viewportZoomInButton").listeners.click();
  assert.equal(run("trailViewport.mode"), "follow");
  assert.equal(run("trailViewport.span"), 32);
  assert.equal(element("viewportZoomInButton").disabled, true);
  let vpSvg = element("trailSvg").innerHTML;
  assert.ok(vpSvg.includes('<clipPath id="trailViewportClip">') &&
    (vpSvg.match(/clip-path="url\(#trailViewportClip\)"/g) || []).length === 2,
    "terrain/connections and trail/route layers are clipped while directions and legends stay fixed");
  assert.ok(!vpSvg.includes('data-terrain-x="0"') && !vpSvg.includes('data-landmark-x="0.5"'),
    "off-view terrain and target markers leave no hidden focusable controls");
  assert.ok(vpSvg.includes('data-terrain-x="1000"') && vpSvg.includes('data-landmark-x="1004.5"'));
  assert.ok(element("seenLandmarksList").innerHTML.includes('data-landmark-x="0.5"') &&
    routeDestinationElement.innerHTML.includes('value="0,0"'), "lists retain destinations outside the local view");
  routeDestinationElement.value = "1004,20";
  routeDestinationElement.listeners.change();
  assert.ok(element("trailSvg").innerHTML.includes('class="checked-route"'));
  run("refreshSelectedTrail()");
  await settle();
  assert.equal(run("trailViewport.span"), 32, "refreshing the same replay keeps the zoom");
  assert.equal(run("trailViewport.mode"), "follow");
  for (let i = 0; i < 4; i += 1) element("viewportZoomOutButton").listeners.click();
  assert.equal(run("trailViewport.span"), 512);
  assert.equal(element("viewportZoomOutButton").disabled, true);
  element("viewportAllButton").listeners.click();
  assert.equal(run("trailViewport.mode"), "all");
  assert.ok(element("trailSvg").innerHTML.includes('data-terrain-x="0"'));
  element("viewportZoomOutButton").listeners.click();
  assert.equal(run("trailViewport.span"), 128, "zooming from full map starts at the default local range");
  assert.equal(run("trailViewport.mode"), "follow");
  vpHistoryPoints = [];
  run("refreshSelectedTrail()");
  await settle();
  for (const id of ["viewportFollowButton","viewportZoomInButton","viewportZoomOutButton"]) {
    assert.equal(element(id).disabled, true, "missing player coordinates disable " + id);
  }
  assert.equal(run("setTrailViewportMode('follow')"), false);
  assert.equal(run("zoomTrailViewport(2)"), false);

  // Fresh, paused, and resumed live frames share the same local view; new identities do not.
  context.fetch = async () => { throw new Error("viewport live tests should not fetch"); };
  run('state.liveRecording=null;live.following=true;liveEl.follow.checked=true;live.key=null;live.sequence=0;resumeLiveTrailView()');
  context.vpLive = liveRouteFrame(1, {world:"viewport-live",session:"viewport-session",x:2.25,z:2.25});
  context.vpLive.snapshot.player_anchor = {x:2,z:2,clear:true};
  run("applyLiveResult(vpLive);setTrailViewportMode('follow');zoomTrailViewport(2)");
  routeDestinationElement.value = "2,6";
  routeDestinationElement.listeners.change();
  assert.ok(element("trailSvg").innerHTML.includes('class="checked-route"'));
  context.vpLive = liveRouteFrame(2, {world:"viewport-live",session:"viewport-session",x:6.25,z:2.25});
  context.vpLive.snapshot.player_anchor = {x:6,z:2,clear:true};
  run("applyLiveResult(vpLive)");
  assert.equal(run("trailViewport.mode"), "follow");
  assert.equal(run("trailViewport.span"), 32);
  assert.ok(element("viewportStatus").textContent.includes("X 6.3 / Z 2.3"), "new frames move the local center");
  run('unavailableLive("采集已暂停","paused")');
  assert.equal(run("trailViewport.span"), 32);
  assert.ok(!element("trailSvg").innerHTML.includes('class="checked-route"'));
  assert.equal(routeDestinationElement.value, "2,6");
  run("zoomTrailViewport(0.5)");
  assert.ok(!element("trailSvg").innerHTML.includes('class="checked-route"'), "zoom cannot reactivate paused navigation");
  run("stopLive();live.following=true;liveEl.follow.checked=true;resumeLiveTrailView()");
  assert.equal(run("trailViewport.span"), 64, "same-session stop/resume preserves the last view");
  assert.equal(run("trailViewport.mode"), "follow");
  const vpSameHistory = replaySummary("f".repeat(64), {worldId:"viewport-live",session:"viewport-session"});
  context.vpSameHistory = vpSameHistory;
  context.fetch = async () => apiResponse(trailPayload(vpSameHistory, [trailPoint(2,102,6.25,2.25)]));
  run("openExplorationTrail(vpSameHistory)");
  await settle();
  assert.equal(run("trailViewport.mode"), "all", "opening history resets the viewport");
  run("setTrailViewportMode('follow');zoomTrailViewport(2);live.following=true;liveEl.follow.checked=true;resumeLiveTrailView()");
  assert.equal(run("trailViewport.mode"), "all", "returning from same-identity history resets to full map");
  run("setTrailViewportMode('follow');zoomTrailViewport(2)");
  context.vpLive = liveRouteFrame(3, {world:"viewport-live",session:"viewport-new-session"});
  run("applyLiveResult(vpLive)");
  assert.equal(run("trailViewport.mode"), "all", "a new collector session resets to full map");
  assert.equal(run("trailViewport.span"), 64);
  run("setTrailViewportMode('follow');zoomTrailViewport(2)");
  context.vpLive = liveRouteFrame(4, {world:"viewport-new-world",session:"viewport-new-session"});
  run("applyLiveResult(vpLive)");
  assert.equal(run("trailViewport.mode"), "all", "a new world resets to full map");
  run("stopLive()");

  // This checks the stylesheet contract; browser hit testing is verified separately.
  const vpCssRules = [...appHtml.matchAll(/([^{}]+)\{([^{}]*)\}/g)];
  for (const name of ["trail-route","trail-route-halo","trail-grid","trail-first","trail-latest","trail-isolated"]) {
    assert.ok(vpCssRules.some(rule => rule[1].split(",").some(selector => selector.trim() === ".trail-svg ." + name) &&
      /pointer-events\s*:\s*none/.test(rule[2])), "decorative " + name + " lets clicks reach terrain");
  }

  run("updateBackgroundRecordingNotice(true)");
  const backgroundNotice = element("backgroundRecordingNotice").textContent;
  run("stopLive()");
  assert.equal(element("backgroundRecordingNotice").textContent, backgroundNotice,
    "stopping browser live following does not claim to stop server recording");
  run("updateBackgroundRecordingNotice(false)");
  assert.ok(element("backgroundRecordingNotice").textContent.includes("未启用后台录制"));
  run('updateBackgroundRecordingNotice("true")');
  assert.equal(element("backgroundRecordingNotice").hidden, true,
    "unknown and older option payloads cannot claim an active recorder");

  const nearestTerrain = [
    {x: 2, z: 2, tile: "GRASS", passable: true, connections: {east: true}},
    {x: 6, z: 2, tile: "FOREST", passable: true, connections: {north: true}},
    {x: 6, z: 6, tile: "ROCKY", passable: true},
    {x: 2, z: 6, tile: "MARSH", passable: true, connections: {east: true}}
  ];
  const realNearestTarget = context.CheckedRoutes.findNearestTarget;
  const nearestCalls = [];
  context.CheckedRoutes.findNearestTarget = (tiles, position, candidates, anchor) => {
    nearestCalls.push({position: JSON.parse(JSON.stringify(position)),
      anchor: anchor === undefined ? undefined : JSON.parse(JSON.stringify(anchor)),
      landmarks: JSON.parse(JSON.stringify(candidates))});
    return realNearestTarget(tiles, position, candidates, anchor);
  };
  context.nearestTerrain = nearestTerrain;
  context.noNearestSightings = [];
  run(`state.target="panflute";trailState.mode="history";trailState.id="nearest-history";
    trailState.identity="nearest-world-session";trailState.error="";trailState.loading=false;
    trailState.landmarkError="";trailState.terrainError="";trailState.points=[{sequence:1,captured_at:1,x:2,z:2}];
    trailState.terrainTiles=nearestTerrain;trailState.terrainAvailable=true;trailState.landmarks=noNearestSightings;
    trailState.playback={timeline:[{sequence:1,captured_at:1}],selectedIndex:0,appliedIndex:0,requestId:0,loading:false,error:""};
    checkedRouteSelection.destination=null;checkedRouteSelection.source=null;live.following=false;renderTrail()`);
  assert.equal(element("nearestSeenTargetButton").disabled, true, "the nearest-target action waits for a current-target sighting");
  assert.ok(element("nearestSeenTargetStatus").textContent.includes("暂未记录当前目标"));
  nearestTargetSyntheticClick();
  assert.equal(nearestCalls.length, 0, "a disabled no-sighting action is guarded by its click handler");

  const manyNearestSightings = Array.from({length: 10}, (_, index) =>
    remembered("panflute", 100 + index * 4, 100, 1, 30 - index, 1, 30 - index))
    .concat([remembered("panflute", 2, 6, 1, 20, 1, 20), remembered("panflute", 6, 6, 1, 19, 1, 19)]);
  context.manyNearestSightings = manyNearestSightings;
  run("trailState.landmarks=manyNearestSightings;renderTrail()");
  assert.equal((element("seenLandmarksList").innerHTML.match(/class="seen-landmark-item"/g) || []).length, 10,
    "the sightings panel keeps its ten-row display limit");
  assert.equal(element("nearestSeenTargetButton").disabled, false, "history can search recorded sightings");
  assert.equal(nearestCalls.length, 0, "rendering the panel does not search routes for all candidates");
  nearestTargetSyntheticClick();
  assert.equal(nearestCalls.length, 1, "the nearest-target action searches only after a click");
  assert.equal(nearestCalls[0].landmarks.length, 12, "the click includes retained sightings beyond the displayed ten");
  assert.deepEqual(nearestCalls[0].landmarks.slice(0, 10).map(item => item.x),
    [100, 104, 108, 112, 116, 120, 124, 128, 132, 136], "all candidates use deterministic newest-first order");
  assert.equal(routeDestinationElement.value, "6,6", "a farther sighting with a shorter checked detour route wins");
  assert.equal(element("routeDestinationSource").textContent,
    "终点来自已见排箫：所记录位置 X 6.0 / Z 6.0 的格中心");
  assert.ok(element("nearestSeenTargetStatus").textContent.includes("已知路线距离 8.0 世界单位"));
  assert.equal(JSON.parse(run("JSON.stringify(calculateCheckedRoute())")).distance, 8,
    "the selected route keeps the shortest known grid distance");

  const preservedDestination = routeDestinationElement.value;
  const preservedSource = element("routeDestinationSource").textContent;
  context.unreachableNearestSightings = [remembered("panflute", 1000, 1000, 1, 99, 1, 99)];
  run("trailState.landmarks=unreachableNearestSightings;renderTrail()");
  nearestTargetSyntheticClick();
  assert.equal(routeDestinationElement.value, preservedDestination, "no known route leaves the previous endpoint untouched");
  assert.equal(element("routeDestinationSource").textContent, preservedSource,
    "no known route leaves the previous endpoint source untouched");
  assert.ok(element("nearestSeenTargetStatus").textContent.includes("没有已知路线"));
  assert.ok(element("nearestSeenTargetStatus").textContent.includes("保持不变"));

  const helperCallsBeforeMissingTarget = nearestCalls.length;
  run('state.target="moonbase";renderTrail()');
  assert.equal(element("nearestSeenTargetButton").disabled, true, "the action is disabled when the current target has no sightings");
  assert.ok(element("nearestSeenTargetStatus").textContent.includes("暂未记录当前目标"));
  nearestTargetSyntheticClick();
  assert.equal(nearestCalls.length, helperCallsBeforeMissingTarget, "a missing-target handler call cannot invoke the route helper");

  context.prefixNearestPoint = trailPoint(1, 1, 3, 2, {x: 2, z: 2, clear: true});
  context.futureLiveNearestPoint = trailPoint(2, 2, 6, 2, {x: 6, z: 2, clear: false});
  context.prefixNearestSightings = [remembered("panflute", 2, 6, 1, 1, 1, 1)];
  run(`state.target="panflute";trailState.mode="history";trailState.id="nearest-prefix";
    trailState.identity="nearest-history-prefix";trailState.error="";trailState.loading=false;
    trailState.landmarkError="";trailState.terrainError="";trailState.terrainTiles=nearestTerrain;
    trailState.points=[prefixNearestPoint];trailState.live.localPoints=[futureLiveNearestPoint];
    trailState.landmarks=prefixNearestSightings;
    trailState.playback={timeline:[{sequence:1,captured_at:1},{sequence:2,captured_at:2}],selectedIndex:0,appliedIndex:0,requestId:0,loading:false,error:""};
    checkedRouteSelection.destination=null;checkedRouteSelection.source=null;renderTrail()`);
  const callsBeforeHistoryRender = nearestCalls.length;
  assert.equal(element("nearestSeenTargetButton").disabled, false, "historical playback remains eligible when its displayed frame is ready");
  assert.equal(nearestCalls.length, callsBeforeHistoryRender, "history rendering does not run nearest-route searches");
  nearestTargetSyntheticClick();
  assert.deepEqual(nearestCalls.at(-1).position, {x: 3, z: 2}, "history uses the latest player position in the displayed prefix");
  assert.deepEqual(nearestCalls.at(-1).anchor, {x: 2, z: 2, clear: true},
    "history passes the displayed point's own player anchor");
  assert.equal(routeDestinationElement.value, "2,6");
  run("trailState.playback.selectedIndex=1;renderTrail()");
  assert.ok(!element("nearestSeenTargetStatus").textContent.includes("已选择"),
    "changing the history cursor clears the transient nearest-target notice");

  run('trailState.playback.selectedIndex=0;renderTrail()');
  nearestTargetSyntheticClick();
  run('state.target="moonbase";renderTrail()');
  assert.ok(!element("nearestSeenTargetStatus").textContent.includes("已选择"),
    "changing the selected target clears the nearest-target notice");
  run('state.target="panflute";renderTrail()');
  nearestTargetSyntheticClick();
  run('trailState.identity="another-nearest-world-session";renderTrail()');
  assert.ok(!element("nearestSeenTargetStatus").textContent.includes("已选择"),
    "changing world or session identity clears the nearest-target notice");

  run('trailState.identity="nearest-history-prefix";trailState.id="nearest-prefix";renderTrail()');
  nearestTargetSyntheticClick();
  assert.ok(element("nearestSeenTargetStatus").textContent.includes("已选择"));
  routeDestinationElement.value = "6,2";
  routeDestinationElement.listeners.change();
  assert.ok(!element("nearestSeenTargetStatus").textContent.includes("已选择"),
    "a manual route-selector choice clears the nearest-target notice");
  nearestTargetSyntheticClick();
  assert.ok(element("nearestSeenTargetStatus").textContent.includes("已选择"));
  trailDestinationSyntheticEvent("click", 2, 2);
  assert.ok(!element("nearestSeenTargetStatus").textContent.includes("已选择"),
    "a manual map endpoint choice clears the nearest-target notice");

  const helperCallsBeforeBlockedUI = nearestCalls.length;
  run('trailState.loading=true;renderTrail()');
  assert.equal(element("nearestSeenTargetButton").disabled, true, "a trail refresh disables the nearest-target action");
  nearestTargetSyntheticClick();
  assert.equal(nearestCalls.length, helperCallsBeforeBlockedUI, "loading-state handler calls do not search routes");
  run('trailState.loading=false;trailState.error="history failed";renderTrail()');
  assert.equal(element("nearestSeenTargetButton").disabled, true, "a trail error disables the nearest-target action");
  nearestTargetSyntheticClick();
  assert.equal(nearestCalls.length, helperCallsBeforeBlockedUI, "error-state handler calls do not search routes");
  run('trailState.error="";renderTrail()');

  const priorRouteStatus = element("routeStatus").textContent;
  const priorSourceVisibility = element("routeDestinationSource").hidden;
  const helperWithError = context.CheckedRoutes.findNearestTarget;
  context.CheckedRoutes.findNearestTarget = () => { throw new Error("malformed helper result"); };
  nearestTargetSyntheticClick();
  assert.ok(element("nearestSeenTargetStatus").textContent.includes("路线计算失败"),
    "a malformed nearest-route helper is reported in the status line");
  assert.equal(element("routeDestinationSource").hidden, priorSourceVisibility, "a malformed helper keeps the prior source state");
  assert.equal(routeDestinationElement.value, "2,2", "a malformed helper keeps the prior endpoint");
  assert.ok(element("trailSvg").innerHTML.includes("<title"), "a malformed helper does not break map rendering");
  assert.equal(element("routeStatus").textContent, priorRouteStatus,
    "a malformed helper leaves the existing route display intact");
  context.CheckedRoutes.findNearestTarget = helperWithError;

  context.liveNearestSightings = [remembered("panflute", 2, 6, 1, 1, 1, 1)];
  context.liveNearestSightingsWithNew = context.liveNearestSightings.concat([remembered("panflute", 6, 2, 2, 2, 2, 2)]);
  run(`trailState.mode="live";trailState.id=null;trailState.identity="nearest-live-world-session";
    trailState.error="";trailState.loading=false;trailState.landmarkError="";trailState.terrainError="";
    trailState.points=[{sequence:1,captured_at:1,x:2,z:2}];trailState.landmarks=liveNearestSightings;
    trailState.terrainTiles=nearestTerrain;trailState.playback={timeline:[],selectedIndex:-1,appliedIndex:-1,requestId:0,loading:false,error:""};
    live.following=true;liveEl.follow.checked=true;acceptRouteFreshness(trailState.identity,1,0);renderTrail()`);
  assert.equal(element("nearestSeenTargetButton").disabled, false, "a fresh live route enables nearest-target search");
  nearestTargetSyntheticClick();
  const liveNearestDestination = routeDestinationElement.value;
  const liveNearestSource = element("routeDestinationSource").textContent;
  assert.equal(liveNearestDestination, "2,6");
  assert.ok(element("routeStatus").textContent.includes("距离 12.0 世界单位"));
  run(`acceptRouteFreshness(trailState.identity,2,0);trailState.points=[{sequence:2,captured_at:2,x:6,z:2}];
    trailState.landmarks=liveNearestSightingsWithNew;renderTrail()`);
  assert.equal(routeDestinationElement.value, liveNearestDestination,
    "movement and new sightings recalculate the route without switching its endpoint");
  assert.equal(element("routeDestinationSource").textContent, liveNearestSource,
    "movement keeps the exact selected sighting source");
  assert.ok(element("routeStatus").textContent.includes("距离 8.0 世界单位 · 2 步"));
  assert.ok(element("nearestSeenTargetStatus").textContent.includes("已知路线距离 8.0 世界单位"),
    "the selected-target status follows the recalculated route distance");

  const helperCallsBeforePause = nearestCalls.length;
  run('pauseRouteNavigation("stale",false);renderTrail()');
  assert.equal(element("nearestSeenTargetButton").disabled, true, "a stale live snapshot disables nearest-target search");
  nearestTargetSyntheticClick();
  assert.equal(nearestCalls.length, helperCallsBeforePause, "the click handler guards a stale live route even if invoked directly");
  assert.equal(routeDestinationElement.value, liveNearestDestination, "a paused click keeps the selected endpoint");
  run("stopLive()");
  assert.equal(element("nearestSeenTargetButton").disabled, true, "stopping live following disables nearest-target search");

  const rolloverPartOne = replaySummary("d".repeat(64), {worldId: "rollover-world", session: "rollover-session", frames: 1});
  const rolloverPartTwo = replaySummary("e".repeat(64), {worldId: "rollover-world", session: "rollover-session", frames: 2, segment: 2});
  const rolloverIdentity = run("explorationReplayIdentity(" + JSON.stringify(rolloverPartOne) + ")");
  const rolloverSnapshot = (sequence, x, z, prefab, tile) => ({
    world_id: "rollover-world", world_kind: "forest", session_id: "rollover-session", sequence,
    captured_at: sequence, position: {x, z}, landmarks: [{prefab, x: x + 20, z: z + 20}],
    terrain: {tile_size: 4, tiles: [{x, z, tile, passable: true}]}
  });
  const partOneSnapshot = rolloverSnapshot(1, 10, 10, "panflute", "GRASS");
  const partTwoSnapshot = rolloverSnapshot(2, 12, 12, "pigking", "FOREST");
  const partOneStored = trailPayload(rolloverPartOne, [trailPoint(1, 1, 10, 10)],
    [remembered("molehill", 30, 30, 1, 1)], false,
    {tile_size: 4, tiles: [terrainCell(2, 2, "GRASS", 1, 1, true)], truncated: false});
  const partTwoStored = trailPayload(rolloverPartTwo, [trailPoint(2, 2, 12, 12), trailPoint(3, 3, 14, 14)],
    [remembered("beequeenhive", 40, 40, 2, 2)], false,
    {tile_size: 4, tiles: [terrainCell(14, 14, "FOREST", 2, 2, true)], truncated: false});
  let partOneRequestCount = 0;
  let resolveLatePartOne;
  let resolveCurrentPartTwo;
  const rolloverTrailRequests = [];
  context.fetch = url => {
    rolloverTrailRequests.push(url);
    if (url === "/api/explorations/" + rolloverPartOne.id + "/trail") {
      partOneRequestCount += 1;
      return partOneRequestCount === 1
        ? Promise.resolve(apiResponse(partOneStored))
        : new Promise(resolve => { resolveLatePartOne = resolve; });
    }
    if (url === "/api/explorations/" + rolloverPartTwo.id + "/trail") {
      return new Promise(resolve => { resolveCurrentPartTwo = resolve; });
    }
    throw new Error("unexpected rollover trail request " + url);
  };
  run(`live.following=true;live.key=${JSON.stringify(rolloverIdentity)};live.sequence=0;liveEl.follow.checked=true;
    trailState.mode="live";trailState.revision++;trailState.id=null;trailState.identity=${JSON.stringify(rolloverIdentity)};trailState.summary=null;
    trailState.points=[];trailState.error="";trailState.loading=false;trailState.trimmed=false;trailState.requests.clear();
    trailState.live={identity:${JSON.stringify(rolloverIdentity)},id:null,localPoints:[],storedPoints:[],trimmed:false,
      localLandmarks:[],storedLandmarks:[],landmarksTruncated:false,landmarkError:"",localTerrain:[],storedTerrain:[],
      localTerrainAvailable:false,storedTerrainAvailable:false,terrainTruncated:false,terrainError:""};
    trailState.landmarks=[];trailState.landmarksTruncated=false;trailState.landmarkError="";trailState.terrainTiles=[];
    trailState.terrainAvailable=false;trailState.terrainTruncated=false;trailState.terrainError="";
    state.liveRecording=null;state.explorations=[${JSON.stringify(rolloverPartOne)},${JSON.stringify(rolloverPartTwo)}];
    state.explorationIdsSeen.add(${JSON.stringify(rolloverPartOne.id)});state.explorationIdsSeen.add(${JSON.stringify(rolloverPartTwo.id)});
    checkedRouteSelection.identity=null;checkedRouteSelection.destination=null;checkedRouteSelection.source=null;`);
  context.rolloverPartOne = rolloverPartOne;
  context.partOneSnapshot = partOneSnapshot;
  run("updateLiveRecording(rolloverPartOne, partOneSnapshot);recordLiveTrailSnapshot(partOneSnapshot)");
  await settle();
  assert.equal(run("trailState.id"), rolloverPartOne.id);
  assert.equal(run("trailState.live.localPoints.length"), 1);
  assert.equal(run("trailState.live.storedPoints.length"), 1);
  run(`checkedRouteSelection.identity=trailState.identity;checkedRouteSelection.destination={x:2,z:2};`);
  run("refreshSelectedTrail()");
  await settle();
  assert.equal(typeof resolveLatePartOne, "function", "the old-part refresh is pending before rollover");
  context.rolloverPartTwo = rolloverPartTwo;
  context.partTwoSnapshot = partTwoSnapshot;
  run("updateLiveRecording(rolloverPartTwo, partTwoSnapshot);recordLiveTrailSnapshot(partTwoSnapshot)");
  await settle();
  assert.equal(typeof resolveCurrentPartTwo, "function", "the new part requests its own stored trail");
  assert.equal(run("trailState.id"), rolloverPartTwo.id);
  assert.equal(run("trailState.identity"), rolloverIdentity, "segment IDs do not replace the world/session trail identity");
  assert.equal(run("trailState.live.identity"), rolloverIdentity);
  assert.deepEqual(JSON.parse(run("JSON.stringify(trailState.live.localPoints.map(point=>point.sequence))")), [1, 2],
    "local player positions continue across a same-session segment rollover");
  assert.equal(run('trailState.live.localLandmarks.some(item=>item.prefab==="panflute")'), true);
  assert.equal(run('trailState.live.localLandmarks.some(item=>item.prefab==="pigking")'), true,
    "local landmarks from both segments stay in the live trail");
  assert.equal(run('trailState.live.localTerrain.some(item=>item.tile==="GRASS")'), true);
  assert.equal(run('trailState.live.localTerrain.some(item=>item.tile==="FOREST")'), true,
    "local terrain from both segments stays in the live map");
  assert.equal(run("trailState.live.storedPoints.length"), 0, "stored points from part one are cleared while part two loads");
  assert.equal(run("trailState.live.storedLandmarks.length"), 0);
  assert.equal(run("trailState.live.storedTerrain.length"), 0);
  assert.deepEqual(JSON.parse(run("JSON.stringify(checkedRouteSelection.destination)")), {x: 2, z: 2},
    "route selection remains tied to the same world/session across parts");
  assert.equal(element("liveReplayLink").href, "/api/explorations/" + rolloverPartTwo.id);
  assert.ok(element("liveReplayLink").textContent.includes("第 2 段"));
  assert.ok(element("liveRecordingStatus").textContent.includes("第 2 段"));
  assert.ok(rolloverTrailRequests.includes("/api/explorations/" + rolloverPartTwo.id + "/trail"));
  resolveLatePartOne(apiResponse(partOneStored));
  await settle();
  assert.equal(run("trailState.id"), rolloverPartTwo.id);
  assert.equal(run("trailState.live.storedPoints.length"), 0, "a late old-part response cannot replace the active part");
  resolveCurrentPartTwo(apiResponse(partTwoStored));
  await settle();
  assert.equal(run("trailState.live.storedPoints.length"), 2);
  assert.deepEqual(JSON.parse(run("JSON.stringify(trailState.live.storedPoints.map(point=>point.sequence))")), [2, 3],
    "the active stored trail contains only its part's points");
  assert.equal(run("trailState.live.storedLandmarks[0].prefab"), "beequeenhive");
  assert.equal(run("trailState.live.storedTerrain[0].tile"), "FOREST");

  const savedActiveStatus = element("liveRecordingStatus").textContent;
  context.latePartOneSummary = {...rolloverPartOne, frame_count: 99};
  context.decreasedPartTwoSummary = {...rolloverPartTwo, frame_count: 1};
  context.equalCountLimitSummary = {...rolloverPartTwo, status: "limit_reached"};
  context.rolloverLaterSnapshot = rolloverSnapshot(3, 14, 14, "spiderden", "ROCKY");
  run("updateLiveRecording(latePartOneSummary, rolloverLaterSnapshot)");
  assert.equal(run("state.liveRecording.id"), rolloverPartTwo.id, "a delayed summary from a lower segment is rejected");
  assert.equal(element("liveReplayLink").href, "/api/explorations/" + rolloverPartTwo.id);
  assert.equal(element("liveRecordingStatus").textContent, savedActiveStatus);
  run("updateLiveRecording(decreasedPartTwoSummary, rolloverLaterSnapshot)");
  assert.equal(run("state.liveRecording.frame_count"), 2, "a decreasing frame count in the active segment is rejected");
  assert.equal(element("liveRecordingStatus").textContent, savedActiveStatus);
  run("updateLiveRecording(equalCountLimitSummary, rolloverLaterSnapshot)");
  assert.equal(run("state.liveRecording.status"), "limit_reached", "equal-count status changes remain accepted");
  assert.ok(element("liveRecordingStatus").textContent.includes("本段已满"));
  assert.ok(element("liveRecordingStatus").textContent.includes("下一帧将自动开始新段"));

  const historyTrailRequests = [];
  context.fetch = async url => {
    historyTrailRequests.push(url);
    if (url === "/api/explorations/" + rolloverPartOne.id + "/trail") return apiResponse(partOneStored);
    if (url === "/api/explorations/" + rolloverPartTwo.id + "/trail") return apiResponse(partTwoStored);
    if (url === "/api/explorations/" + rolloverPartTwo.id + "/trail?through_sequence=2") {
      return apiResponse(trailPlaybackPayload(rolloverPartTwo, [trailPoint(2, 2, 12, 12)], 2, 2));
    }
    throw new Error("unexpected history part request " + url);
  };
  run("trailState.requests.clear();openExplorationTrail(" + JSON.stringify(rolloverPartOne) + ")");
  await settle();
  assert.equal(run("trailState.id"), rolloverPartOne.id);
  assert.ok(element("trailPlaybackStatus").textContent.includes("第 1 段"));
  run("trailState.requests.clear();openExplorationTrail(" + JSON.stringify(rolloverPartTwo) + ")");
  await settle();
  assert.equal(run("trailState.id"), rolloverPartTwo.id, "history opens the selected sibling part by its exact ID");
  assert.ok(element("trailPlaybackStatus").textContent.includes("第 2 段"));
  await run("requestHistoryFrame(0, {force:true})");
  assert.ok(historyTrailRequests.includes("/api/explorations/" + rolloverPartTwo.id + "/trail?through_sequence=2"));
  assert.ok(!historyTrailRequests.includes("/api/explorations/" + rolloverPartOne.id + "/trail?through_sequence=2"));
  assert.deepEqual(JSON.parse(run("JSON.stringify(trailState.points.map(point=>point.sequence))")), [2],
    "history cutoffs include only the selected segment through the selected sequence");
  assert.ok(element("trailPlaybackStatus").textContent.includes("第 2 段"));

  console.log("Live UI: replay recording, freshness-gated live routes, request timeouts and retries, history isolation, map follow and zoom, trail rendering, checked-grid and landmark routes, races, and connection diagnostics passed");
})().catch(error => { console.error(error); process.exitCode = 1; });
