const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const appHtml = fs.readFileSync("dst_route_planner/static/app.html", "utf8");
const checkedRoutesSource = fs.readFileSync("dst_route_planner/static/checked_routes.js", "utf8");
const source = appHtml.match(/<script>([\s\S]*?)<\/script>/)[1].replace("    initialize();", "");
const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, {
    value: "", checked: false, disabled: false, textContent: "", innerHTML: "",
    className: "", href: "", hidden: true, listeners: Object.create(null),
    classList: {add() {}, remove() {}, toggle() {}, contains() { return false; }},
    querySelectorAll() { return []; }, addEventListener(name, handler) { this.listeners[name] = handler; },
    removeAttribute(name) { if (name === "href") this.href = ""; }
  });
  return elements.get(id);
}
const context = vm.createContext({
  document: {getElementById: element}, AbortController,
  fetch: async () => { throw new Error("unexpected fetch"); },
  setTimeout: () => 1, clearTimeout() {}
});
vm.runInContext(checkedRoutesSource, context);
vm.runInContext(source, context);
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
function trailPoint(sequence, capturedAt, x, z) { return {sequence, captured_at: capturedAt, x, z}; }
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
    frame_count: points.length, points,
    bounds: points.length ? {min_x: Math.min(...xs), max_x: Math.max(...xs), min_z: Math.min(...zs), max_z: Math.max(...zs)} : null,
    ...(landmarks === undefined ? {} : {landmarks, landmarks_truncated: landmarksTruncated}),
    ...(terrain === undefined ? {} : {terrain})
  };
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
  return result;
}
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
  assert.ok(element("liveRecordingStatus").textContent.includes("已自动记录"));
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
  assert.ok(element("liveRecordingStatus").textContent.includes("已达到记录上限"));
  assert.ok(element("liveRecordingStatus").textContent.includes(String(Number.MAX_SAFE_INTEGER)));

  const errorId = "c".repeat(64);
  const failed = replaySummary(errorId, {session: "two", status: "error", error: "disk full"});
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

  const persisted = Array.from({length: 12}, (_, index) => replaySummary(
    index.toString(16).padStart(64, "0"),
    {worldId: index === 0 ? '<img src=x onerror="x">' : "saved-world-" + index, frames: index + 1}
  ));
  persisted.push({...persisted[0], id: "../../bad"});
  context.fetch = async url => {
    if (url !== "/api/explorations") throw new Error("unexpected fetch " + url);
    return apiResponse({explorations: persisted});
  };
  await run('refreshExplorations({quiet:true})');
  assert.equal(run("state.explorations.length"), 10);
  assert.ok(element("explorationList").innerHTML.includes("/api/explorations/" + persisted[0].id));
  assert.ok(element("explorationList").innerHTML.includes("&lt;img"));
  assert.ok(!element("explorationList").innerHTML.includes("<img"));
  assert.ok(!element("explorationList").innerHTML.includes("../../bad"));
  assert.ok(element("explorationsStatus").textContent.includes("读取到 12 条有效回放，显示最近 10 条。"));
  assert.ok(element("explorationsStatus").textContent.includes("已忽略 1 条格式不完整的项目。"));

  context.fetch = async url => {
    if (url !== "/api/explorations") throw new Error("unexpected fetch " + url);
    return apiResponse({explorations: [{...persisted[0], id: "e".repeat(64), started_at: undefined, created_at: "2026-10-14T10:00:00.000Z"}]});
  };
  await run('refreshExplorations({quiet:true})');
  assert.equal(run("state.explorations.length"), 0, "created_at must not substitute for started_at");
  assert.ok(element("explorationsStatus").textContent.includes("格式不完整"));

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
    return apiResponse(trailPayload(raceB, [trailPoint(0, 199, 49, 0)], [remembered("panflute", 49, 0, 0, 0)], false,
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

  const newerRaceB = {...raceB, frame_count: 4};
  context.fetch = async url => {
    if (url !== "/api/explorations/" + raceB.id + "/trail") throw new Error("unexpected fetch " + url);
    trailCallCounts.set(raceB.id, trailCallCounts.get(raceB.id) + 1);
    return apiResponse(trailPayload(newerRaceB, [
      trailPoint(0, 199, 49, 0), trailPoint(1, 200, 50, 0),
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
  assert.equal(run("trailState.terrainTiles.find(tile => tile.x === 50).passable"), false,
    "historical trail merging preserves the newer local blocked check over saved terrain");
  assert.deepEqual(JSON.parse(run("JSON.stringify(trailState.terrainTiles.find(tile => tile.x === 50).connections)")), {east: false},
    "historical trail merging preserves the newer local connection results over saved terrain");
  assert.equal(trailCallCounts.get(raceB.id), 4, "opening a replay refreshes cached trail data when its frame count advanced");
  assert.equal(run("trailState.points.length"), 4);
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
      targets: ["panflute", "moonbase"], tile_types: ["GRASS"], prefabs: ["grass"],
      directions: ["north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest"]
    });
    if (url === "/api/records") return apiResponse({records: []});
    if (url === "/api/explorations") return apiResponse({explorations: [initSummary]});
    throw new Error("unexpected fetch " + url);
  };
  await run("initialize()");
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
  assert.equal(element("liveCheckStatus").innerHTML, "", "diagnostic paths render only as text, never as HTML");
  assert.deepEqual(liveStateForDiagnostics(), diagnosticStateBefore, "a diagnostic response does not mutate live, observation, plan, replay, or trail state");

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

  context.checkedRouteFixture = [
    {x: 2, z: 2, tile: "GRASS", passable: true, connections: {east: true, north: false}},
    {x: 6, z: 2, tile: "FOREST", passable: true, connections: {north: true}},
    {x: 6, z: 6, tile: "ROCKY", passable: true},
    {x: 2, z: 6, tile: "MARSH", passable: true, connections: {east: true}},
    {x: 10, z: 6, tile: "ROCKY", passable: false},
    {x: 14, z: 6, tile: "OTHER"}
  ];
  run('trailState.mode="live";trailState.identity="route-world\u0000forest\u0000route-session";trailState.points=[{sequence:1,captured_at:1,x:2,z:2}];trailState.terrainTiles=checkedRouteFixture;trailState.terrainAvailable=true;trailState.terrainError="";el.terrainToggle.checked=false;el.terrainConnectionToggle.checked=false;renderTrail()');
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
  assert.ok(routeSvg.includes('class="checked-route"') && routeSvg.includes('class="checked-route-goal"'),
    "a found route and its goal render in the map even with both terrain overlays turned off");
  assert.ok(!routeSvg.includes('class="terrain-connection') && !routeSvg.includes('class="terrain-cell'),
    "route drawing is independent of the terrain and connection layer toggles");
  assert.equal(routeDestinationElement.value, "2,6", "a selected destination survives redraws for the same trail identity");
  const routeOptionWrites = routeDestinationElement.optionMarkupWrites;
  run("renderTrail()");
  assert.equal(routeDestinationElement.optionMarkupWrites, routeOptionWrites,
    "one-second trail redraws do not rebuild an unchanged destination menu");

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
  assert.ok(element("routeStatus").textContent.includes("已找到格中心路线"), "historical tile connections support the same route finder");
  routeSvg = element("trailSvg").innerHTML;
  assert.ok(routeSvg.indexOf('class="checked-route"') > routeSvg.indexOf('class="trail-route"') &&
    routeSvg.indexOf('class="checked-route-goal"') > routeSvg.lastIndexOf('class="trail-landmark-marker"'),
    "the purple checked route overlays the green history trail and the goal ring is drawn after observed landmarks");
  assert.ok(routeSvg.includes('class="checked-route-goal" cx="') && routeSvg.includes('r="10"'),
    "the goal uses a visible 10-unit hollow ring when it overlaps a landmark");
  run('trailState.mode="idle";renderTrail()');
  assert.ok(element("trailStatus").textContent.includes("实时跟随已暂停") &&
    element("trailSvg").innerHTML.includes('class="checked-route"'),
    "a paused or stale trail keeps its static checked-grid route");
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

  console.log("Live UI: replay recording, trail rendering, checked-grid routes, races, and connection diagnostics passed");
})().catch(error => { console.error(error); process.exitCode = 1; });
