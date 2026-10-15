const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync("dst_route_planner/static/app.html", "utf8").match(/<script>([\s\S]*?)<\/script>/)[1].replace("    initialize();", "");
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
vm.runInContext(source, context);
function run(code) { return vm.runInContext(code, context); }
function apiResponse(payload) { return {ok: true, json: async () => payload}; }
function trailPoint(sequence, capturedAt, x, z) { return {sequence, captured_at: capturedAt, x, z}; }
function trailPayload(summary, points) {
  const xs = points.map(point => point.x), zs = points.map(point => point.z);
  return {
    trail_version: 1, id: summary.id, world_id: summary.world_id,
    world_kind: summary.world_kind, session_id: summary.session_id,
    frame_count: points.length, points,
    bounds: points.length ? {min_x: Math.min(...xs), max_x: Math.max(...xs), min_z: Math.min(...zs), max_z: Math.max(...zs)} : null
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
const stationaryProjection = run("projectTrailCoordinates([{sequence:1,captured_at:1,x:7,z:-4},{sequence:2,captured_at:2,x:7,z:-4}])");
assert.deepEqual(
  {x: stationaryProjection.points[0].x, y: stationaryProjection.points[0].y},
  {x: stationaryProjection.points[1].x, y: stationaryProjection.points[1].y}
);
run('trailState.points=[];trailState.error="";renderTrail()');
assert.ok(element("trailSvg").innerHTML.includes("还没有可绘制的坐标"));
run('trailState.points=[{sequence:1,captured_at:1,x:7,z:-4},{sequence:2,captured_at:2,x:7,z:-4}];renderTrail()');
assert.ok(element("trailSvg").innerHTML.includes('class="trail-route"'));
assert.ok(element("trailSvg").innerHTML.includes('class="trail-first"'));
assert.ok(element("trailSvg").innerHTML.includes('class="trail-latest"'));
assert.ok(element("trailSvg").innerHTML.includes("起点") && element("trailSvg").innerHTML.includes("最新位置"));
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
const validationSummary = replaySummary("9".repeat(64), {worldId: "validate-world", session: "validate-session"});
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
  run(`trailState.mode="idle";trailState.revision++;trailState.id=null;trailState.identity=null;trailState.summary=null;trailState.points=[];trailState.error="";trailState.loading=false;trailState.trimmed=false;trailState.requests.clear();trailState.live={identity:null,id:null,localPoints:[],storedPoints:[],trimmed:false};state.liveRecording=null;state.explorations=[${JSON.stringify(liveTrailSummary)}];state.explorationIdsSeen.add("${liveTrailId}");live.following=true;liveEl.follow.checked=true;live.key=null;live.sequence=0;resumeLiveTrailView();`);
  let resolveLiveTrail;
  let trailCalls = 0;
  context.fetch = url => {
    if (url !== "/api/explorations/" + liveTrailId + "/trail") throw new Error("unexpected fetch " + url);
    trailCalls += 1;
    return new Promise(resolve => { resolveLiveTrail = resolve; });
  };
  context.reply = frame("trail-session", 1, liveTrailSummary, "trail-world", {x: 1, z: 1, capturedAt: 100});
  run("applyLiveResult(reply)");
  context.reply = frame("trail-session", 2, {...liveTrailSummary, frame_count: 2}, "trail-world", {x: 2, z: 1, capturedAt: 101});
  run("applyLiveResult(reply)");
  context.reply = frame("trail-session", 3, liveTrailSummary, "trail-world", {x: 3, z: 1, capturedAt: 102});
  run("applyLiveResult(reply)");
  assert.equal(trailCalls, 1, "live updates append locally without a journal request per frame");
  assert.equal(run("trailState.live.localPoints.length"), 3);
  resolveLiveTrail(apiResponse(trailPayload(liveTrailSummary, [
    trailPoint(0, 99, 0, 0), trailPoint(2, 101, 222, 222)
  ])));
  await settle();
  const mergedLivePoints = JSON.parse(run("JSON.stringify(trailState.points)"));
  assert.deepEqual(mergedLivePoints.map(point => point.sequence), [0, 1, 2, 3]);
  assert.deepEqual({x: mergedLivePoints[2].x, z: mergedLivePoints[2].z}, {x: 2, z: 1}, "accepted local points win duplicate sequences");
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
  context.reply = frame("same-session", 1, raceA, "race-a", {x: 500, z: 0, capturedAt: 200});
  run("applyLiveResult(reply)");
  context.reply = frame("same-session", 1, raceB, "race-b", {x: 50, z: 0, capturedAt: 200});
  run("applyLiveResult(reply)");
  assert.equal(run("trailState.identity"), "race-b\u0000forest\u0000same-session");
  pendingTrails.get(raceA.id)(apiResponse(trailPayload(raceA, [trailPoint(0, 1, 500, 0)])));
  await settle();
  assert.equal(run("trailState.id"), raceB.id, "late world trail responses cannot replace the active world");
  assert.ok(JSON.parse(run("JSON.stringify(trailState.points)")).every(point => point.x !== 500));
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
    return apiResponse(trailPayload(raceB, [trailPoint(0, 199, 49, 0)]));
  };
  run("refreshSelectedTrail()");
  await settle();
  assert.equal(trailCallCounts.get(raceB.id), 3);
  assert.equal(run("trailState.error"), "");

  const newerRaceB = {...raceB, frame_count: 4};
  context.fetch = async url => {
    if (url !== "/api/explorations/" + raceB.id + "/trail") throw new Error("unexpected fetch " + url);
    trailCallCounts.set(raceB.id, trailCallCounts.get(raceB.id) + 1);
    return apiResponse(trailPayload(newerRaceB, [
      trailPoint(0, 199, 49, 0), trailPoint(1, 200, 50, 0),
      trailPoint(2, 201, 51, 0), trailPoint(3, 202, 52, 0)
    ]));
  };
  run(`state.explorations=[${JSON.stringify(newerRaceB)}];renderExplorations();live.following=true;liveEl.follow.checked=true;`);
  const trailButton = {dataset: {explorationId: raceB.id}};
  element("explorationList").listeners.click({target: {closest: selector => selector === "button.trail-open[data-exploration-id]" ? trailButton : null}});
  assert.equal(run("live.following"), false, "opening a saved trail stops live following");
  assert.equal(element("liveFollow").checked, false);
  assert.equal(run("trailState.mode"), "history");
  assert.equal(run("trailState.id"), raceB.id);
  await settle();
  assert.equal(trailCallCounts.get(raceB.id), 4, "opening a replay refreshes cached trail data when its frame count advanced");
  assert.equal(run("trailState.points.length"), 4);
  assert.ok(element("trailStatus").textContent.includes("历史回放"));
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

  run('trailState.mode="idle";trailState.live={identity:null,id:null,localPoints:[],storedPoints:[],trimmed:false};state.liveRecording=null;');
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

  console.log("Live UI: replay recording plus trail projection, segmentation, merging, races, retries, retention bounds, map independence, history opening, and initialization checks passed");
})().catch(error => { console.error(error); process.exitCode = 1; });
