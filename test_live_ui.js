const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync("dst_route_planner/static/app.html", "utf8").match(/<script>([\s\S]*?)<\/script>/)[1].replace("    initialize();", "");
const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, {value:"", checked:false, disabled:false, textContent:"", innerHTML:"", className:"", classList:{add(){},remove(){},toggle(){},contains(){return false;}}, querySelectorAll(){return [];}, addEventListener(){}});
  return elements.get(id);
}
const context = vm.createContext({document:{getElementById:element}, AbortController,
  fetch:async()=>{throw new Error("unexpected fetch");},setTimeout:()=>1,clearTimeout(){}});
vm.runInContext(source, context);
function run(code) { return vm.runInContext(code, context); }
run('state.options={targets:["panflute","moonbase"],tile_types:["GRASS"],prefabs:["grass"],directions:DIRS.slice()}; live.following=true;');
function frame(session="one", sequence=1) {
  return {status:"live",age_seconds:0.5,snapshot:{world_id:"world-a",world_kind:"forest",session_id:session,sequence,position:{x:12,y:0,z:30},current:{prefab_counts:{observed_custom_prefab:2}},directions:{north:{tile_types:["CUSTOM_TILE"],prefab_counts:{panflute:1}}}},
    plan:{directions:[{direction:"north",score:4,p_dir:1,p_task:0,p_room:0,explanation:[]}],current_tasks:[]},visible_target:{x:12,z:34,distance:4}};
}
element("recordName").value="My world";element("worldNote").value="Exploration note";
run('state.activeRecordId="00000000-0000-4000-8000-000000000001";');
context.reply=frame();run("applyLiveResult(reply)");
assert.equal(run("state.activeRecordId"),"00000000-0000-4000-8000-000000000001");
assert.equal(element("recordName").value,"My world");
assert.ok(element("livePosition").textContent.includes("12.0"));
assert.ok(element("liveTarget").textContent.includes("4.0"));
assert.equal(element("diagonalToggle").disabled,true);
const saved=JSON.parse(run("JSON.stringify(createRecordPayload())"));
assert.equal(saved.observation.current.prefab_counts.observed_custom_prefab,2);
assert.equal(saved.observation.directions.north.tile_types[0],"CUSTOM_TILE");
context.reply={status:"stale",snapshot:frame().snapshot};run("applyLiveResult(reply)");
assert.equal(run("state.result"),null);
assert.equal(element("liveTarget").textContent,"");
assert.ok(element("resultsArea").innerHTML.includes("超过五秒"));
context.reply=frame("two",1);run("applyLiveResult(reply)");
assert.equal(run("state.activeRecordId"),null);
assert.equal(element("recordName").value,"");
context.reply=frame("two",3);run("applyLiveResult(reply)");
context.reply=frame("two",2);run("applyLiveResult(reply)");
assert.equal(run("state.result"),null);
assert.ok(element("liveStatus").textContent.includes("倒序"));
run('stopLive(); state.options.tile_types=["GRASS"]; state.options.prefabs=["grass"];');
context.loaded=saved.observation;
run('applyPayload(loaded,"saved live record",{id:"00000000-0000-4000-8000-000000000001",name:"Restored world",world_note:"saved note"})');
assert.equal(JSON.parse(run("JSON.stringify(createRecordPayload())")).observation.current.prefab_counts.observed_custom_prefab,2);
run('live.following=true;state.result=null;');
(async()=>{
  let resolve;
  context.fetch=()=>new Promise(done=>{resolve=done;});
  const pending=run("pollLive()");
  run("stopLive()");
  resolve({ok:true,json:async()=>frame("two",4)});
  await pending;
  assert.equal(run("state.result"),null);
  assert.equal(element("diagonalToggle").disabled,false);
  assert.equal(run("live.timer"),null);
  console.log("Live UI: metadata, observed IDs, stale data, session reset, sequence and cancelled-response checks passed");
})().catch(error=>{console.error(error);process.exitCode=1;});
