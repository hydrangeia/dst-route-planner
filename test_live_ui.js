const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync("dst_route_planner/static/app.html", "utf8").match(/<script>([\s\S]*?)<\/script>/)[1].replace("    initialize();", "");
const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, {
    value: "", checked: false, disabled: false, textContent: "", innerHTML: "",
    className: "", href: "", hidden: true,
    classList: {add() {}, remove() {}, toggle() {}, contains() { return false; }},
    querySelectorAll() { return []; }, addEventListener() {},
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
function frame(session = "one", sequence = 1, recording = null, worldId = "world-a") {
  const result = {
    status: "live", age_seconds: 0.5,
    snapshot: {
      world_id: worldId, world_kind: "forest", session_id: session, sequence,
      position: {x: 12, y: 0, z: 30},
      current: {prefab_counts: {observed_custom_prefab: 2}},
      directions: {north: {tile_types: ["CUSTOM_TILE"], prefab_counts: {panflute: 1}}}
    },
    plan: {directions: [{direction: "north", score: 4, p_dir: 1, p_task: 0, p_room: 0, explanation: []}], current_tasks: []},
    visible_target: {x: 12, z: 34, distance: 4}
  };
  if (recording) result.recording = recording;
  return result;
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

  console.log("Live UI: live updates, no-ID recording errors, replay identity, out-of-order frames, limits, persisted list counts, stale retention, world changes, and initialization checks passed");
})().catch(error => { console.error(error); process.exitCode = 1; });
