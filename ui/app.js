/* Sketch → Floor Plan — UI logic */

const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];

/* ── drawing unit for EDITING ─────────────────────────────────
   The model stores lengths in FEET. The user can edit in Feet-Inch / mm / Meter;
   these helpers convert to the chosen unit for display and back to feet on save,
   so every coordinate / size / the gizmo / the step read & accept that unit.
   (Defined up here so the gizmo wiring below can use them at load.)            */
let DUNIT = "ft";
const UNIT_F = { ft: 1, mm: 304.8, m: 0.3048 };   // feet → unit
const unitFactor = () => UNIT_F[DUNIT] || 1;
const unitStepAttr = () => ({ ft: "0.02", mm: "1", m: "0.005" }[DUNIT] || "0.02");
const FEET_LEN = new Set(["x", "y", "w", "h", "x1", "y1", "x2", "y2", "pos",
  "width", "size", "rx", "ry", "landing_size", "landing_depth", "well_gap",
  "__len"]);
const isFeetLen = path => FEET_LEN.has(String(path || ""));
const toDisp = f => {
  const v = (+f || 0) * unitFactor();
  return DUNIT === "mm" ? Math.round(v)
    : DUNIT === "m" ? Math.round(v * 1000) / 1000
      : Math.round(v * 10000) / 10000;
};
const fromDisp = d => (parseFloat(d) || 0) / unitFactor();
const STEP_PRESETS = {
  ft: [["1\"", 0.0833], ["3\"", 0.25], ["6\"", 0.5], ["1'", 1], ["2'", 2]],
  mm: [["10", 10], ["25", 25], ["50", 50], ["100", 100], ["300", 300]],
  m:  [["0.05", 0.05], ["0.1", 0.1], ["0.25", 0.25], ["0.5", 0.5], ["1", 1]],
};
const STEP_DEFAULT = { ft: "0.5", mm: "100", m: "0.1" };

const S = {
  pages: [],
  page: 0,
  sk: { z: 1, x: 0, y: 0, w: 0, h: 0 },
  pl: { z: 1, x: 0, y: 0, w: 0, h: 0 },
  dirty: false,
  undo: [],
  redo: [],
  savePath: "",
  saveName: "",
  layerState: null,
  lastFolder: "",
  // multi-floor: a project is a list of floors; every tool works on the ACTIVE
  // floor. S.plan is an alias for the active floor's plan, so all existing code
  // keeps working unchanged.
  floors: [{ name: "Ground Floor", plan: null }],
  active: 0,
};
Object.defineProperty(S, "plan", {
  get() { const f = S.floors[S.active]; return f ? f.plan : null; },
  set(v) {
    if (!S.floors.length) S.floors = [{ name: "Ground Floor", plan: null }];
    if (S.active >= S.floors.length) S.active = 0;
    S.floors[S.active].plan = v;
  },
  enumerable: true, configurable: true,
});

/* Bridge. The desktop build talks to the pywebview `api` object; the WEB build
   (no pywebview) talks to the server over HTTP — every api().method(...args)
   becomes POST /rpc/method with [args], returning the same JSON. */
function isWeb() { return !(window.pywebview && window.pywebview.api); }
const _sleep = ms => new Promise(r => setTimeout(r, ms));
// One RPC call. The free host can be waking up or mid-redeploy, when its proxy
// answers with an HTML 502/503/504 page instead of our JSON — so we retry those
// a few times, and if a reply still isn't JSON we surface a clear message rather
// than the cryptic "Unexpected token '<'".
async function _rpc(method, args, _try) {
  _try = _try || 0;
  let r;
  try {
    r = await fetch("/rpc/" + method, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(args || []),
    });
  } catch (e) {
    if (_try < 4) { await _sleep(1500); return _rpc(method, args, _try + 1); }
    return { ok: false, error: "Server not reachable: " + e };
  }
  // 502/503/504 = proxy up but app waking / restarting / busy → wait & retry
  if ((r.status === 502 || r.status === 503 || r.status === 504) && _try < 5) {
    await _sleep(2000);
    return _rpc(method, args, _try + 1);
  }
  const text = await r.text();
  try {
    const j = JSON.parse(text);
    // session expired or the admin blocked this login → back to the sign-in page
    if (j && j.auth === false) { location.href = "/"; return j; }
    return j;
  } catch (e) {
    if (_try < 4) { await _sleep(1500); return _rpc(method, args, _try + 1); }
    return { ok: false, error:
      `Server returned ${r.status} (not JSON). The free host may be waking up `
      + `or busy — wait ~30 s and try again. If it keeps failing on this sheet, `
      + `the free 512 MB tier may be too small for it.` };
  }
}
const _webApi = new Proxy({}, { get: (_t, m) => (...a) => _rpc(m, a) });
const api = () => (window.pywebview && window.pywebview.api)
  ? window.pywebview.api : _webApi;

/* WEB file open: read JSON in the browser, upload DXF to the server. Returns
   {json} for a JSON plan, {path,name} for an uploaded file, or null. */
function webPickFile(accept) {
  return new Promise(resolve => {
    let inp = document.getElementById("_webfile");
    if (!inp) {
      inp = document.createElement("input");
      inp.type = "file"; inp.id = "_webfile"; inp.style.display = "none";
      document.body.appendChild(inp);
    }
    inp.accept = accept || "";
    inp.onchange = async () => {
      const f = inp.files && inp.files[0]; inp.value = "";
      if (!f) return resolve(null);
      if (/\.json$/i.test(f.name)) {
        try { resolve({ json: JSON.parse(await f.text()), name: f.name }); }
        catch (e) { resolve({ error: "bad JSON: " + e }); }
        return;
      }
      const fd = new FormData(); fd.append("file", f);
      const r = await fetch("/upload", { method: "POST", body: fd })
        .then(x => x.json()).catch(e => ({ ok: false, error: String(e) }));
      resolve(r.ok ? { path: r.path, name: r.name } : { error: r.error });
    };
    inp.click();
  });
}

/* WEB: pick SEVERAL files at once (one per floor) through the browser picker */
function webPickFiles(accept) {
  return new Promise(resolve => {
    let inp = document.getElementById("_webfiles");
    if (!inp) {
      inp = document.createElement("input");
      inp.type = "file"; inp.id = "_webfiles"; inp.multiple = true;
      inp.style.display = "none";
      document.body.appendChild(inp);
    }
    inp.accept = accept || "";
    inp.onchange = async () => {
      const files = Array.from(inp.files || []); inp.value = "";
      if (!files.length) return resolve(null);
      const paths = [], names = [];
      for (const fl of files) {                 // upload each, keep the order
        const fd = new FormData(); fd.append("file", fl);
        const r = await fetch("/upload", { method: "POST", body: fd })
          .then(x => x.json()).catch(e => ({ ok: false, error: String(e) }));
        if (!r.ok) return resolve({ error: r.error });
        paths.push(r.path); names.push(r.name);
      }
      resolve({ paths, names });
    };
    inp.click();
  });
}

/* WEB: pull the exported combined file(s) from the server as browser downloads */
function webDownloadCombined(paths) {
  const wanted = ["combined_dxf", "combined_pdf"];
  const list = [];
  for (const [k, v] of Object.entries(paths || {})) {
    if (k === "folder" || !v) continue;
    if (wanted.includes(k) || /_COMBINED\.(dxf|pdf)$/i.test(v)
        || /ALL-FLOORS\.(dxf|pdf)$/i.test(v)) list.push(v);
  }
  // fallback — if nothing matched the combined naming, offer any dxf/pdf found
  if (!list.length) {
    for (const [k, v] of Object.entries(paths || {}))
      if (k !== "folder" && v && /\.(dxf|pdf)$/i.test(v)) list.push(v);
  }
  // 1) try the automatic download (works on most desktop browsers)
  list.forEach((p, i) => setTimeout(() => {
    const a = document.createElement("a");
    a.href = "/download?path=" + encodeURIComponent(p);
    a.download = (p.split(/[\\/]/).pop()) || "";
    document.body.appendChild(a); a.click(); a.remove();
  }, i * 700));
  // 2) ALWAYS show visible, clickable links — browsers block programmatic
  //    downloads (multiple files / on mobile), so this guarantees a way to grab
  //    the file even when the auto-download is silently ignored.
  webShowDownloads(list);
}

function webShowDownloads(list) {
  let box = document.getElementById("dlPanel");
  if (!box) {
    box = document.createElement("div");
    box.id = "dlPanel";
    box.style.cssText =
      "position:fixed;right:16px;bottom:16px;z-index:99999;background:#141821;"
      + "color:#fff;border:1px solid #3a4152;border-radius:12px;"
      + "padding:14px 16px;box-shadow:0 10px 34px rgba(0,0,0,.55);"
      + "max-width:360px;font:14px system-ui,Segoe UI,Arial";
    document.body.appendChild(box);
  }
  const links = (list || []).map(p => {
    const name = (p.split(/[\\/]/).pop()) || "file";
    return `<a href="/download?path=${encodeURIComponent(p)}" download="${name}"`
      + ` style="display:block;margin:6px 0;color:#7cc4ff;`
      + `text-decoration:underline;word-break:break-all">⬇ ${name}</a>`;
  }).join("");
  box.innerHTML =
    `<div style="font-weight:600;margin-bottom:6px">✅ Export ready — download</div>`
    + (links || "<div>no file produced</div>")
    + `<div style="opacity:.65;font-size:12px;margin-top:8px">Tap a file to save.`
    + ` If it opens in a new tab, use the browser's Save/Download.</div>`
    + `<button onclick="this.parentNode.remove()" style="margin-top:10px;`
    + `background:#2b3040;color:#fff;border:0;border-radius:7px;`
    + `padding:6px 14px;cursor:pointer">Close</button>`;
}

/* ── chrome ──────────────────────────────────────────────── */
function busy(on, msg, cancellable) {
  $("#busyMsg").textContent = msg || "Working…";
  $("#busy").classList.toggle("hidden", !on);
  $("#btnCancel").classList.toggle("hidden", !(on && cancellable));
}
$("#btnCancel").onclick = async () => {
  $("#btnCancel").textContent = "Stopping…";
  await api().cancel_read();
};
function status(s) { $("#status").textContent = s || ""; }
window.pushLog = s => {
  window.lastLog = s;
  const b = $("#logBox");
  b.textContent += (b.textContent ? "\n" : "") + s;
  b.scrollTop = b.scrollHeight;
};
function fail(r) {
  if (r && r.error) {
    pushLog("ERROR: " + r.error);
    if (r.trace) pushLog(r.trace);
    tab("log");
    status("failed — see Log");
    banner(r.error);
  }
}

/* a dismissable message for problems the user has to act on */
function banner(msg) {
  let el = $("#banner");
  if (!el) {
    el = document.createElement("div");
    el.id = "banner";
    el.className = "banner";
    document.body.appendChild(el);
  }
  const needsLogin = /sign-in|login/i.test(msg);
  el.innerHTML = `<pre>${esc(msg)}</pre>`
    + (needsLogin ? '<button class="btn accent" data-act="login">Open sign-in</button>' : "")
    + '<button class="btn ghost" data-act="close">Dismiss</button>';
  el.querySelector('[data-act="close"]').onclick = () => el.remove();
  const lg = el.querySelector('[data-act="login"]');
  if (lg) lg.onclick = async () => {
    // on the web build there is no terminal here — the CLI signs in on the
    // machine that runs the server, so just say so instead of erroring
    if (isWeb()) status("Sign in to Claude on the machine running the server, "
      + "then press Re-check.");
    else await api().open_login();
    status("sign in in the terminal, then press Re-check");
    lg.textContent = "Re-check";
    lg.onclick = async () => {
      const st = await api().cli_status();
      if (st && st.error) { pushLog("still not signed in"); return; }
      el.remove();
      status("signed in — press Read Sketch (AI)");
    };
  };
}

// rail tool → open its flyout side-window; click the active tool again to close
$$(".tab").forEach(t => t.onclick = () => {
  const fo = $("#flyout");
  const wasSec = editingSections();
  if (fo && fo.classList.contains("open") && t.classList.contains("on")) {
    closeFlyout();
  } else {
    tab(t.dataset.tab);
  }
  // opening/leaving the Sections tool toggles the cut lines on the plan
  if (wasSec !== editingSections() && S.plan && !S.beamView && !S.sectionView) redraw();
  // canvas edit follows the open tab — drop a selection that isn't this type
  // (the Plumbing tab edits BOTH pipes and fittings, so keep either)
  const _aek = activeEditKey();
  if (_sel && _sel.key !== _aek && !(_aek === "pipes" && _sel.key === "plumb")) {
    _sel = null;
    $$("tr.selrow,.litem.on").forEach(x => x.classList.remove("selrow", "on"));
  }
  if (typeof buildHandles === "function") buildHandles(S.plInfo);
});
function tab(name) {
  $$(".tab").forEach(t => t.classList.toggle("on", t.dataset.tab === name));
  $$(".panel").forEach(p => p.classList.toggle("on", p.id === "p-" + name));
  const fo = $("#flyout");
  if (fo) {
    fo.classList.add("open");
    const t = $$(".tab").find(x => x.dataset.tab === name);
    const ft = $("#flyoutTitle");
    if (ft && t) ft.textContent = t.dataset.label || t.textContent.trim();
  }
  applyTabView(name);          // open the layout that belongs to this tool
}
/* opening a stage tool shows its own layer view: Electrical tab → electrical
   layout, Furniture → furniture, Plumbing → plumbing, Flooring → flooring. */
/* switch to a plumbing layer view (its pipes/fittings become the editable set) */
async function setPlumbView(v) {
  if (!S.plan) return;
  await loadLayers();
  if (!LAYERS.views || !LAYERS.views[v] || !LAYERS.groups) return;
  S.curView = v;
  const want = new Set(LAYERS.views[v] || []);
  LAYERS.groups.forEach(g => S.layerState[g.key] = want.has(g.key));
  if (_sel && (_sel.key === "pipes" || _sel.key === "plumb")) { _sel = null; }  // drop hidden selection
  buildTable("pipes"); redraw();
  status(v === "watersupply" ? "Water supply layout — edit its pipes & valves"
    : "Plumbing routing (drainage) — edit its pipes & fittings");
}
/* the two-layout switcher shown at the top of the Plumbing tab */
function plumbViewSwitcher(host) {
  const bar = document.createElement("div");
  bar.className = "row"; bar.style.cssText = "gap:6px;margin:0 0 10px";
  const cur = S.curView;
  [["drainage", "Plumbing routing"], ["watersupply", "Water supply"]].forEach(([v, lbl]) => {
    const b = document.createElement("button");
    b.className = "btn" + (cur === v ? " accent" : "");
    b.textContent = lbl;
    b.onclick = () => setPlumbView(v);
    bar.appendChild(b);
  });
  host.appendChild(bar);
}
const TAB_VIEW = { furniture: "furniture", elec: "electrical", flooring: "flooring" };
async function applyTabView(name) {
  let v = TAB_VIEW[name];
  // the Plumbing (pipes) tab keeps the current plumbing layout if one is open
  // (water supply / drainage), else drops into drainage so pipes are visible
  if (name === "pipes") {
    if (["watersupply", "drainage", "plumbing"].includes(S.curView)) return;
    v = "drainage";
  }
  if (!v || !S.plan || S.beamView || S.sectionView || S.structView || S.elevView) return;
  await loadLayers();
  if (!LAYERS.views || !LAYERS.views[v] || !LAYERS.groups) return;
  if (S.curView === v) return;                 // already showing it
  S.curView = v;
  const want = new Set(LAYERS.views[v] || []);
  LAYERS.groups.forEach(g => S.layerState[g.key] = want.has(g.key));
  redraw();
}
function closeFlyout() {
  const wasSec = editingSections();
  const fo = $("#flyout");
  if (fo) fo.classList.remove("open");
  $$(".tab").forEach(t => t.classList.remove("on"));
  if (wasSec && S.plan && !S.beamView && !S.sectionView) redraw();
}
if ($("#flyoutClose")) $("#flyoutClose").onclick = closeFlyout;

/* section cut lines are their own layer — draw them ONLY while the Sections tool
   is open or a section is selected, so they never clutter the floor plan /
   furniture / other views. */
function editingSections() {
  const fo = $("#flyout"), active = $(".tab.on");
  if (fo && fo.classList.contains("open") && active && active.dataset.tab === "sections") return true;
  return !!(_sel && _sel.key === "sections");
}

/* ── move gizmo — pick an item, see its coordinates, nudge with a D-pad
   (click = one step, hold = keep moving). Like moving objects in CAD.        */
const POSCFG = {
  furniture:{coord:"xy", rot:"angle", full:true},
  elec:     {coord:"xy", rot:"angle", full:true},   // AC / fan / board rotate
  columns:  {coord:"xy", full:true},
  walls:    {coord:"seg", full:true},          // move both ends together
  openings: {coord:"pos", full:true},          // slides along its wall (1-D)
  rooms:    {coord:"xy", full:true},
  stairs:   {coord:"xy", full:true},
  steps:    {coord:"xy", rot:"__rot90", full:true},   // 90° rotate (swap run axis)
  sections: {coord:"seg", full:true},
  beams:    {coord:"seg", full:true},
  flooring: {coord:"none", full:true},         // no move — just its settings
  pipes:    {coord:"poly", full:true},         // plumbing pipe runs: drag whole / per vertex
  plumb:    {coord:"xy", full:true},           // plumbing fittings: gully/manhole/traps/stacks
};
let _sel = null;                 // {key, ri}
const round2 = v => Math.round((+v || 0) * 100) / 100;
function selItem(){ return _sel ? ((S.plan && S.plan[_sel.key]) || [])[_sel.ri] : null; }
function selectItem(key, ri){
  if (!POSCFG[key]) return;
  _sel = { key, ri };
  $$("tr.selrow").forEach(t => t.classList.remove("selrow"));
  $$(".litem.on").forEach(t => t.classList.remove("on"));
  const row = $('#p-' + key + ' tr[data-ri="' + ri + '"]')
           || $('#p-' + key + ' .litem[data-ri="' + ri + '"]');
  if (row) row.classList.add(row.classList.contains("litem") ? "on" : "selrow");
  showGizmo();
  if (typeof buildHandles === "function") buildHandles(S.plInfo);   // canvas grips
}
/* nearest wall on one axis to a model point — signed offset (point - wall).
   axis "x" looks at vertical walls (controls the ↔ gap), "y" at horizontal. */
function nearestWallAxis(px, py, axis) {
  let best = null, bd = 1e9;
  ((S.plan && S.plan.walls) || []).forEach(w => {
    const vert = Math.abs(w.x1 - w.x2) <= Math.abs(w.y1 - w.y2);
    if (axis === "x" && !vert) return;
    if (axis === "y" && vert) return;
    if (axis === "x") {
      const lo = Math.min(w.y1, w.y2) - 0.5, hi = Math.max(w.y1, w.y2) + 0.5;
      if (py < lo || py > hi) return;
      const wx = (w.x1 + w.x2) / 2, d = Math.abs(px - wx);
      if (d < bd) { bd = d; best = { coord: wx, dist: px - wx }; }
    } else {
      const lo = Math.min(w.x1, w.x2) - 0.5, hi = Math.max(w.x1, w.x2) + 0.5;
      if (px < lo || px > hi) return;
      const wy = (w.y1 + w.y2) / 2, d = Math.abs(py - wy);
      if (d < bd) { bd = d; best = { coord: wy, dist: py - wy }; }
    }
  });
  return best;
}
/* move the selected light/furniture so its gap to that nearest wall = absVal (ft) */
function setWallDist(axis, absVal) {
  const it = selItem(); if (!it || !_sel) return;
  const key = _sel.key, w = +it.w || 0, h = +it.h || 0;
  const cx = key === "furniture" ? it.x + w / 2 : it.x;
  const cy = key === "furniture" ? it.y + h / 2 : it.y;
  const nw = nearestWallAxis(cx, cy, axis); if (!nw) return;
  const sign = nw.dist >= 0 ? 1 : -1;
  const target = nw.coord + sign * Math.max(0, absVal);
  pushUndo();
  if (axis === "x") it.x = r4(key === "furniture" ? target - w / 2 : target);
  else it.y = r4(key === "furniture" ? target - h / 2 : target);
  markDirty(); updateGizmoCoords(); redraw(); showGizmo();
}
function showGizmo(){
  const g = $("#gizmo"); if (!g) return;
  const it = selItem();
  if (!it || !_sel){ g.classList.add("hidden"); return; }
  const cfg = POSCFG[_sel.key];
  g.classList.remove("hidden");
  g.classList.toggle("oneD", cfg.coord === "pos");
  g.classList.toggle("nomove", cfg.coord === "none");
  const extra = it.kind ? " · " + it.kind : (it.code ? " · " + it.code : "");
  $("#gizName").textContent = _sel.key === "pipes"
    ? `${it.system || "PIPE"} ${it.dia_mm ? it.dia_mm + "Ø" : ""}`.trim()
    : (it.tag || it.name || it.id || it.room || _sel.key) + extra;
  const xy = cfg.coord === "xy", pos = cfg.coord === "pos";
  $("#gizXWrap").classList.toggle("hidden", !xy);
  $("#gizYWrap").classList.toggle("hidden", !xy);
  $("#gizPosWrap").classList.toggle("hidden", !pos);
  if (xy){ $("#gizX").value = toDisp(it.x); $("#gizY").value = toDisp(it.y); }
  if (pos){ $("#gizPos").value = toDisp(it.pos); }
  $("#gizRotL").classList.toggle("hidden", !cfg.rot);
  $("#gizRotR").classList.toggle("hidden", !cfg.rot);
  // snap-to-wall: columns get the precise directional face-flush (⇤/⇥/⤒/⤓ at
  // T- and L-junctions, as before); other free x/y items (furniture, lights,
  // rooms, stairs, steps) get the simple 'nearest wall' snap.
  const isCol = _sel.key === "columns";
  $("#gizSnap").classList.toggle("hidden", cfg.coord !== "xy" || isCol);
  $("#gizColSnap").classList.toggle("hidden", !isCol);
  // openings (doors/windows) can be centred on their wall in one tap
  $("#gizCenter").classList.toggle("hidden", _sel.key !== "openings");
  // full field editor — every editable property (swing, sill, lintel, width …)
  const box = $("#gizFields"); box.innerHTML = "";
  if (cfg.full) {
    const skip = new Set(pos ? ["pos"] : xy ? ["x", "y"] : []);
    (COLS[_sel.key] || []).forEach(c => {
      if (skip.has(c[0])) return;
      const el = makeFieldEl(_sel.key, it, c);
      const lab = document.createElement("label");
      lab.className = "giz-field";
      const s = document.createElement("span"); s.textContent = c[1];
      lab.appendChild(s); lab.appendChild(el);
      box.appendChild(lab);
    });
  }
  // distance-from-wall — for lights & furniture: shows the gap to the nearest
  // wall on each axis; type a number to move the piece to that exact gap.
  if (_sel.key === "furniture" || _sel.key === "elec") {
    const w = +it.w || 0, h = +it.h || 0;
    const cx = _sel.key === "furniture" ? it.x + w / 2 : it.x;
    const cy = _sel.key === "furniture" ? it.y + h / 2 : it.y;
    [["x", "From wall ↔"], ["y", "From wall ↕"]].forEach(([ax, lbl]) => {
      const nw = nearestWallAxis(cx, cy, ax);
      const lab = document.createElement("label"); lab.className = "giz-field";
      const s = document.createElement("span"); s.textContent = lbl + " (" + DUNIT + ")";
      const inp = document.createElement("input");
      inp.type = "number"; inp.step = unitStepAttr();
      if (nw) inp.value = toDisp(Math.abs(nw.dist));
      else { inp.placeholder = "no wall"; inp.disabled = true; }
      inp.onchange = () => { const v = fromDisp(inp.value); if (!isNaN(v)) setWallDist(ax, v); };
      lab.appendChild(s); lab.appendChild(inp);
      box.appendChild(lab);
    });
  }
  // Duplicate: any free x/y piece or a pipe run copies cleanly
  if ($("#gizDup")) $("#gizDup").classList.toggle(
    "hidden", !(cfg.coord === "xy" || cfg.coord === "poly"));
  $("#gizDelete").classList.remove("hidden");
}
function updateGizmoCoords(){
  const it = selItem(); if (!it || !_sel) return;
  const c = POSCFG[_sel.key].coord;
  if (c === "xy"){ $("#gizX").value = toDisp(it.x); $("#gizY").value = toDisp(it.y); }
  else if (c === "pos"){ $("#gizPos").value = toDisp(it.pos); }
}
function gizStep(){                     // returns the step in FEET (model unit)
  const d = parseFloat(($("#gizStep") || {}).value);
  return Math.max(0.001, isNaN(d) ? 0.5 : d / unitFactor());
}
function moveSel(dx, dy){
  const it = selItem(); if (!it) return;
  const c = POSCFG[_sel.key].coord, s = gizStep();
  if (c === "xy"){ if (dx) it.x = r4((+it.x || 0) + dx * s); if (dy) it.y = r4((+it.y || 0) + dy * s); }
  else if (c === "poly"){ const P = it.pts || []; for (let k = 0; k < P.length; k++) P[k] = [r4(P[k][0] + dx * s), r4(P[k][1] + dy * s)]; }
  else if (c === "pos"){ if (dx) it.pos = r4(Math.max(0, (+it.pos || 0) + dx * s)); }
  else if (c === "seg"){
    it.x1 = r4((+it.x1 || 0) + dx * s); it.x2 = r4((+it.x2 || 0) + dx * s);
    it.y1 = r4((+it.y1 || 0) + dy * s); it.y2 = r4((+it.y2 || 0) + dy * s);
  }
  markDirty(); updateGizmoCoords(); redraw();
}
const _ROT90_CCW = { left: "bottom", bottom: "right", right: "top", top: "left" };
const _ROT90_CW = { left: "top", top: "right", right: "bottom", bottom: "left" };
function rotSel(dir){
  const it = selItem(); if (!it) return;
  const f = POSCFG[_sel.key] && POSCFG[_sel.key].rot; if (!f) return;
  if (f === "__rot90") {                    // steps: rotate the whole run 90°
    const cx = it.x + (+it.w || 0) / 2, cy = it.y + (+it.h || 0) / 2;
    const nw = +it.h || 0, nh = +it.w || 0;      // swap footprint
    it.w = r4(nw); it.h = r4(nh);
    it.x = r4(cx - nw / 2); it.y = r4(cy - nh / 2);
    it.run_axis = it.run_axis === "x" ? "y" : "x";
    const map = dir > 0 ? _ROT90_CCW : _ROT90_CW;
    it.up_from = map[it.up_from] || it.up_from;
    markDirty(); updateGizmoCoords(); redraw(); return;
  }
  it[f] = r4(((+it[f] || 0) + dir * 15 + 360) % 360);
  markDirty(); redraw();
}
function holdRepeat(el, fn){
  if (!el) return;
  let iv = null;
  const start = e => { e.preventDefault(); fn(); clearInterval(iv); iv = setInterval(fn, 110); };
  const stop = () => { clearInterval(iv); iv = null; };
  el.addEventListener("mousedown", start);
  el.addEventListener("touchstart", start, { passive: false });
  ["mouseup", "mouseleave", "touchend", "touchcancel"]
    .forEach(ev => el.addEventListener(ev, stop));
}
holdRepeat($("#gizmo .up"),    () => moveSel(0, +1));
holdRepeat($("#gizmo .down"),  () => moveSel(0, -1));
holdRepeat($("#gizmo .left"),  () => moveSel(-1, 0));
holdRepeat($("#gizmo .right"), () => moveSel(+1, 0));
if ($("#gizX")) $("#gizX").onchange = () => { const it = selItem(); if (it){ it.x = r4(fromDisp($("#gizX").value)); markDirty(); redraw(); } };
if ($("#gizY")) $("#gizY").onchange = () => { const it = selItem(); if (it){ it.y = r4(fromDisp($("#gizY").value)); markDirty(); redraw(); } };
if ($("#gizPos")) $("#gizPos").onchange = () => { const it = selItem(); if (it){ it.pos = r4(Math.max(0, fromDisp($("#gizPos").value))); markDirty(); redraw(); } };
if ($("#gizRotL")) $("#gizRotL").onclick = () => rotSel(+1);
if ($("#gizRotR")) $("#gizRotR").onclick = () => rotSel(-1);
function rebuildStepPresets(){
  const box = $("#gizmo .giz-presets"); if (!box) return;
  box.innerHTML = (STEP_PRESETS[DUNIT] || STEP_PRESETS.ft)
    .map(([lb, val]) => `<button data-step="${val}">${lb}</button>`).join("");
  box.querySelectorAll("button").forEach(b =>
    b.onclick = () => { $("#gizStep").value = b.dataset.step; });
  const lbl = $("#gizmo .giz-step");
  if (lbl && lbl.childNodes[0]) lbl.childNodes[0].nodeValue = "Step (" + DUNIT + ") ";
}
rebuildStepPresets();
if ($("#selUnit")) $("#selUnit").onchange = () => {
  DUNIT = $("#selUnit").value;
  if ($("#gizStep")) $("#gizStep").value = STEP_DEFAULT[DUNIT];
  rebuildStepPresets();
  buildTables();                       // re-show every table in the new unit
  if (_sel) showGizmo();               // and the gizmo
  if (S.plan) redraw();                // and the DRAWING's dims / labels, live
  status("editing unit set to " + ({ ft: "Feet-Inch", mm: "Millimeter", m: "Meter" }[DUNIT]));
};
function snapSel(){
  const it = selItem(); if (!it || !_sel) return;
  if (POSCFG[_sel.key].coord !== "xy") return;
  const box = ("w" in it && "h" in it);   // a piece with size vs a point fitting
  pushUndo();
  if (flushToWall(it, box)) { markDirty(); updateGizmoCoords(); redraw();
    status("snapped to the nearest wall"); }
  else status("no wall to snap to");
}
if ($("#gizSnap")) $("#gizSnap").onclick = snapSel;
if ($("#gizCenter")) $("#gizCenter").onclick = () => {
  const it = selItem(); if (!it || !_sel || _sel.key !== "openings") return;
  const w = (S.plan.walls || []).find(x => x.id === it.wall_id);
  if (!w) { status("set this opening's Wall first"); return; }
  const L = Math.hypot(w.x2 - w.x1, w.y2 - w.y1);
  pushUndo();
  it.pos = r4(Math.max(0, (L - (+it.width || 0)) / 2));   // centred on the wall
  markDirty(); showGizmo(); redraw();
  status("centered on wall " + it.wall_id);
};
$$("#gizColSnap button").forEach(b => b.onclick = () => {
  const it = selItem(); if (!it || !_sel || _sel.key !== "columns") return;
  pushUndo(); flushColumnSide(it, b.dataset.side);
  markDirty(); updateGizmoCoords(); redraw();
  status("column flushed " + b.dataset.side + " to the wall");
});
if ($("#gizDelete")) $("#gizDelete").onclick = () => {
  if (!_sel) return;
  const key = _sel.key, ri = _sel.ri;
  pushUndo(); (S.plan[key] || []).splice(ri, 1);
  _sel = null; $("#gizmo").classList.add("hidden");
  markDirty(); buildTables(); redraw();
};
/* Duplicate: an exact copy of the selected piece, dropped a step aside and
   immediately selected — drag it to where it goes. */
if ($("#gizDup")) $("#gizDup").onclick = () => {
  const it = selItem(); if (!it || !_sel) return;
  const key = _sel.key;
  pushUndo();
  const cp = structuredClone(it);
  const OFF2 = 1.5;                              // feet, so the copy is visible
  if (Array.isArray(cp.pts)) cp.pts = cp.pts.map(p => [r4(p[0] + OFF2), r4(p[1] - OFF2)]);
  else { if ("x" in cp) cp.x = r4((+cp.x || 0) + OFF2); if ("y" in cp) cp.y = r4((+cp.y || 0) - OFF2); }
  if (key === "furniture") {                     // next free F-number
    const used = new Set((S.plan.furniture || []).map(f => f.tag));
    let n = (S.plan.furniture || []).length + 1;
    while (used.has("F" + n)) n++;
    cp.tag = "F" + n;
  } else if (cp.tag) {
    // the copy takes the series' HIGHEST number + 1 (PAS-L-09 in a set that
    // reaches PAS-L-12 → PAS-L-13). A legacy suffix after the number ("-C")
    // is ignored for parsing and dropped from the new tag.
    const list = S.plan[key] || [];
    const m = String(cp.tag).match(/^(.*?)(\d+)\D*$/);
    if (m) {
      const pre = m[1], width = m[2].length;
      let mx = 0;
      list.forEach(o => {
        const mm = String(o.tag || "").match(/^(.*?)(\d+)\D*$/);
        if (mm && mm[1] === pre) mx = Math.max(mx, parseInt(mm[2], 10));
      });
      cp.tag = pre + String(mx + 1).padStart(width, "0");
    } else {                                     // no number anywhere: TAG → TAG2
      let mx = 1;
      list.forEach(o => {
        const mm = String(o.tag || "").match(new RegExp("^" + cp.tag + "(\\d+)$"));
        if (mm) mx = Math.max(mx, parseInt(mm[1], 10));
      });
      cp.tag = cp.tag + (mx + 1);
    }
  } else if (cp.id) cp.id = String(cp.id) + "C";
  (S.plan[key] || (S.plan[key] = [])).push(cp);
  markDirty(); buildTables(); redraw();
  selectItem(key, S.plan[key].length - 1);
  status((cp.tag || cp.id || "copy") + " — duplicate ban gaya, drag karke jagah pe rakho");
};
if ($("#gizClose")) $("#gizClose").onclick = () => { _sel = null; $("#gizmo").classList.add("hidden"); clearHandles(); $$("tr.selrow,.litem.on").forEach(t => t.classList.remove("selrow", "on")); };
/* drag the gizmo by its header so it never has to overlap anything */
(function dragGizmo(){
  const g = $("#gizmo"); if (!g) return;
  const h = g.querySelector(".giz-head"); if (!h) return;
  let ox = 0, oy = 0, on = false;
  h.addEventListener("mousedown", e => {
    if (e.target.closest(".giz-x")) return;    // the × still closes
    const r = g.getBoundingClientRect();
    ox = e.clientX - r.left; oy = e.clientY - r.top; on = true;
    g.style.right = "auto"; g.style.bottom = "auto";
    g.style.left = r.left + "px"; g.style.top = r.top + "px";
    e.preventDefault();
  });
  addEventListener("mousemove", e => {
    if (!on) return;
    const x = Math.max(4, Math.min(e.clientX - ox, innerWidth - g.offsetWidth - 4));
    const y = Math.max(4, Math.min(e.clientY - oy, innerHeight - g.offsetHeight - 4));
    g.style.left = x + "px"; g.style.top = y + "px";
  });
  addEventListener("mouseup", () => { on = false; });
})();

/* keyboard: move the selected item with the ARROW keys (same step as the gizmo).
   Ignored while typing in a field. Openings only move left/right (along wall).  */
addEventListener("keydown", e => {
  if (!_sel || !POSCFG[_sel.key]) return;
  const t = e.target;
  if (t && /^(INPUT|SELECT|TEXTAREA)$/.test(t.tagName)) return;
  let dx = 0, dy = 0;
  if (e.key === "ArrowLeft") dx = -1;
  else if (e.key === "ArrowRight") dx = 1;
  else if (e.key === "ArrowUp") dy = 1;
  else if (e.key === "ArrowDown") dy = -1;
  else return;
  if (POSCFG[_sel.key].coord === "pos" && dy) return;   // openings: 1-D only
  e.preventDefault();
  moveSel(dx, dy);
});

/* ── zoom / pan ──────────────────────────────────────────── */
function viewOf(k) { return k === "sk" ? $("#skView") : $("#plView"); }
function nodeOf(k) { return k === "sk" ? $("#skImg") : $("#plHolder"); }

function apply(k) {
  const s = S[k];
  nodeOf(k).style.transform = `translate(${s.x}px,${s.y}px) scale(${s.z})`;
}

/* the sketch-under-drawing overlay was removed; keep no-op stubs so callers
   don't need guarding */
const OV = { on: false };
function applyOverlay() {}
function mixOverlay() {}
function fit(k) {
  const s = S[k], v = viewOf(k);
  if (!s.w || !s.h) return;
  const z = Math.min((v.clientWidth - 28) / s.w, (v.clientHeight - 28) / s.h);
  s.z = z > 0 ? z : 1;
  s.x = (v.clientWidth - s.w * s.z) / 2;
  s.y = (v.clientHeight - s.h * s.z) / 2;
  apply(k);
}
function zoomAt(k, factor, cx, cy) {
  const s = S[k];
  const nz = Math.min(24, Math.max(0.04, s.z * factor));
  s.x = cx - (cx - s.x) * (nz / s.z);
  s.y = cy - (cy - s.y) * (nz / s.z);
  s.z = nz;
  apply(k);
}
["sk", "pl"].forEach(k => {
  const v = viewOf(k);
  v.addEventListener("wheel", e => {
    e.preventDefault();
    const r = v.getBoundingClientRect();
    zoomAt(k, e.deltaY < 0 ? 1.14 : 1 / 1.14, e.clientX - r.left, e.clientY - r.top);
  }, { passive: false });
  let drag = null;
  v.addEventListener("mousedown", e => {
    drag = { x: e.clientX, y: e.clientY, ox: S[k].x, oy: S[k].y };
    v.classList.add("grabbing");
  });
  addEventListener("mousemove", e => {
    if (!drag) return;
    S[k].x = drag.ox + e.clientX - drag.x;
    S[k].y = drag.oy + e.clientY - drag.y;
    apply(k);
  });
  addEventListener("mouseup", () => { drag = null; v.classList.remove("grabbing"); });
});
$$("[data-zoom]").forEach(b => b.onclick = () => {
  const k = b.dataset.zoom, d = +b.dataset.d, v = viewOf(k);
  if (d === 0) return fit(k);
  zoomAt(k, d > 0 ? 1.25 : 1 / 1.25, v.clientWidth / 2, v.clientHeight / 2);
});
addEventListener("resize", () => { fit("sk"); fit("pl"); });

/* ── pane splitter ───────────────────────────────────────── */
(() => {
  let on = false;
  $("#gutter").addEventListener("mousedown", () => on = true);
  addEventListener("mousemove", e => {
    if (!on) return;
    const split = $(".split");
    const f = (e.clientX - split.getBoundingClientRect().left) / split.clientWidth;
    if (f > .15 && f < .85) {
      split.children[0].style.flex = f;
      split.children[2].style.flex = 1 - f;
      fit("sk"); fit("pl");
    }
  });
  addEventListener("mouseup", () => on = false);
})();

/* ── sketch preview ──────────────────────────────────────── */
function showPages(pages, name) {
  S.pages = pages; S.page = 0;
  $("#sketchName").textContent = name || "";
  const tabs = $("#pageTabs");
  tabs.innerHTML = "";
  if (pages.length > 1) {
    pages.forEach((_, i) => {
      const b = document.createElement("button");
      b.textContent = i + 1;
      b.className = i === 0 ? "on" : "";
      b.onclick = () => { S.page = i; paintPage(); };
      tabs.appendChild(b);
    });
  }
  paintPage();
}
function paintPage() {
  $$("#pageTabs button").forEach((b, i) => b.classList.toggle("on", i === S.page));
  const img = $("#skImg");
  img.onload = () => { S.sk.w = img.naturalWidth; S.sk.h = img.naturalHeight; fit("sk"); };
  img.src = S.pages[S.page];
  $("#skEmpty").classList.add("hidden");
  if (OV.on) $("#ovImg").src = S.pages[S.page];
}

/* ── drawing preview ─────────────────────────────────────── */
function clearPlanView() {
  const h = $("#plHolder");
  if (h) h.innerHTML = "";
  const e = $("#plEmpty");
  if (e) e.classList.remove("hidden");
  const pi = $("#planInfo");
  if (pi) pi.textContent = "";
}
function showSvg(svg, info) {
  const h = $("#plHolder");
  h.innerHTML = svg;
  const el = h.querySelector("svg");
  const mm2px = 3.7795;
  const nw = info.w_mm * mm2px, nh = info.h_mm * mm2px;
  // keep the current zoom / pan across an edit — only refit for a brand-new
  // plan (S.forceFit) or when the sheet size itself changes. Editing one
  // corner should not throw the whole view back to fit.
  const sameSize = Math.abs((S.pl.w || 0) - nw) < 0.5
                && Math.abs((S.pl.h || 0) - nh) < 0.5;
  S.pl.w = nw; S.pl.h = nh;
  el.setAttribute("width", nw); el.setAttribute("height", nh);
  $("#plEmpty").classList.add("hidden");
  $("#planInfo").textContent =
    `${info.sheet} ${info.orientation} · ${info.scale}`;
  mixOverlay();
  if (S.forceFit || !sameSize || !S.pl.z) fit("pl");
  else apply("pl");
  S.forceFit = false;
  S.plInfo = info;
  buildHandles(info);          // draggable handles on top of the drawing
  drawRefs(info);              // persistent reference / guide lines
}

/* ── canvas direct-manipulation ───────────────────────────────────────
   Click an element on the plan to SELECT it; only the selected element shows a
   clean highlight with small SQUARE grips (no clutter). Drag a wall end to
   stretch it, its body to move it, a piece / its corner to move / resize, a
   door along its wall. Snapping: a grid + orthogonal (90°) + alignment to other
   walls — essential for clean drawings. Mouse and touch.                       */
const NS_SVG = "http://www.w3.org/2000/svg";
let _hdrag = null;
function clearHandles() { const o = document.getElementById("plHandles"); if (o) o.remove(); }
function wallById(id) { return (S.plan && S.plan.walls || []).find(w => w.id === id); }
/* a pipe run is editable only while its system's layer is shown — so in the
   Water-supply view you drag supply pipes, in the Drainage view drainage pipes */
const PIPE_GRP = { CW: "plumbcw", HW: "plumbhw", SOIL: "plumbsoil", WASTE: "plumbwaste",
  VENT: "plumbvent", STORM: "plumbstorm", ACD: "plumbacd" };
function pipeVisible(r) {
  const g = PIPE_GRP[r && r.system];
  return !S.layerState || g == null || S.layerState[g] !== false;
}

/* --- snapping ------------------------------------------------------- */
const GRID = 0.25, ORTHO = 7, ALIGN = 0.4;      // ft grid, ° ortho, ft align
const snapG = v => Math.round(v / GRID) * GRID;
let _guides = [];                                // alignment guide lines during a drag
/* candidate coords to align to — walls, columns, box edges/centres, lights,
   reference lines — excluding the element being dragged (so it can leave home). */
function _cand(axis) {
  const skip = _hdrag && _hdrag.it, s = [];
  const dk = _hdrag && _sel && _sel.key;
  if (dk === "elec") {                 // lights align to OTHER LIGHTS only
    (S.plan.elec || []).forEach(e => { if (e === skip) return; s.push(axis === "x" ? e.x : e.y); });
    ((S.plan && S.plan.refs) || []).forEach(r => { if (r.axis === (axis === "x" ? "v" : "h")) s.push(r.at); });
    return s;
  }
  (S.plan.walls || []).forEach(w => { if (w === skip) return; axis === "x" ? s.push(w.x1, w.x2) : s.push(w.y1, w.y2); });
  (S.plan.columns || []).forEach(c => { if (c === skip) return; s.push(axis === "x" ? c.x : c.y); });
  ["furniture", "rooms", "stairs", "steps"].forEach(arr => (S.plan[arr] || []).forEach(it => {
    if (it === skip) return; const w = +it.w || 0, h = +it.h || 0;
    if (axis === "x") s.push(it.x, it.x + w / 2, it.x + w); else s.push(it.y, it.y + h / 2, it.y + h);
  }));
  (S.plan.elec || []).forEach(e => { if (e === skip) return; s.push(axis === "x" ? e.x : e.y); });
  ((S.plan && S.plan.refs) || []).forEach(r => { if (r.axis === (axis === "x" ? "v" : "h")) s.push(r.at); });
  return s;
}
/* snap to the NEAREST aligned candidate (not the first found) — dragging a
   light must line it dead straight with the closest light on that axis, both
   horizontally and vertically. Lights get a wider catch (their rows run long). */
function _snapTol() {
  return (_hdrag && _sel && _sel.key === "elec") ? 0.9 : ALIGN;
}
function snapX(x) {
  let best = null, bd = _snapTol();
  for (const v of _cand("x")) { const d = Math.abs(x - v); if (d < bd) { bd = d; best = v; } }
  if (best !== null) { _guides.push({ axis: "v", at: best }); return best; }
  return snapG(x);
}
function snapY(y) {
  let best = null, bd = _snapTol();
  for (const v of _cand("y")) { const d = Math.abs(y - v); if (d < bd) { bd = d; best = v; } }
  if (best !== null) { _guides.push({ axis: "h", at: best }); return best; }
  return snapG(y);
}
function orthoEnd(mx, my, ox, oy) {              // snap a wall end to H/V + grid
  const a = ((Math.atan2(my - oy, mx - ox) * 180 / Math.PI) % 180 + 180) % 180;
  if (a < ORTHO || a > 180 - ORTHO) return [snapX(mx), oy];      // horizontal
  if (Math.abs(a - 90) < ORTHO) return [ox, snapY(my)];         // vertical
  return [snapX(mx), snapY(my)];
}

/* --- coordinate maps ----------------------------------------------- */
function m2s(info, mx, my) { return [mx * info.k + info.ox, info.h_mm - (my * info.k + info.oy)]; }
function screenToModel(cx, cy) {
  const draw = $("#plHolder").querySelector("svg"); if (!draw || !S.plInfo) return null;
  const r = draw.getBoundingClientRect(), ppu = r.width / S.plInfo.w_mm;
  const sx = (cx - r.left) / ppu, sy = (cy - r.top) / ppu;
  return [(sx - S.plInfo.ox) / S.plInfo.k, (S.plInfo.h_mm - sy - S.plInfo.oy) / S.plInfo.k];
}
/* rotate a model point about (cx,cy) by deg anticlockwise — the same convention
   the server uses to draw rotated furniture (about the piece's own centre) */
function rotPt(px, py, cx, cy, deg) {
  const r = deg * Math.PI / 180, c = Math.cos(r), s = Math.sin(r);
  const dx = px - cx, dy = py - cy;
  return [cx + dx * c - dy * s, cy + dx * s + dy * c];
}
function _distSeg(px, py, x1, y1, x2, y2) {
  const vx = x2 - x1, vy = y2 - y1, L2 = vx * vx + vy * vy || 1e-9;
  let t = ((px - x1) * vx + (py - y1) * vy) / L2; t = Math.max(0, Math.min(1, t));
  return Math.hypot(px - (x1 + vx * t), py - (y1 + vy * t));
}
/* the element type you can edit on the canvas RIGHT NOW = the open tool's tab
   (Walls tab → only walls, Furniture tab → only furniture, …). No tool open →
   the canvas only pans. */
function activeEditKey() {
  const fo = $("#flyout"), t = $(".tab.on");
  if (!fo || !fo.classList.contains("open") || !t) return null;
  const k = t.dataset.tab;
  return POSCFG[k] ? k : null;      // only editable element types
}
/* which element of ONE type is under a model point (closest within tolerance) */
function hitTest(mx, my, key) {
  if (!key) return null;
  let best = null, bd = 0.7;
  if (key === "walls" || key === "beams" || key === "sections") {
    (S.plan[key] || []).forEach((w, i) => {
      const d = _distSeg(mx, my, w.x1, w.y1, w.x2, w.y2);
      if (d < bd) { bd = d; best = { key, ri: i }; }
    });
  } else if (key === "openings") {
    (S.plan.openings || []).forEach((o, i) => {
      const w = wallById(o.wall_id); if (!w) return;
      const L = Math.hypot(w.x2 - w.x1, w.y2 - w.y1) || 1e-6, ux = (w.x2 - w.x1) / L, uy = (w.y2 - w.y1) / L;
      const cx = w.x1 + ux * (o.pos + o.width / 2), cy = w.y1 + uy * (o.pos + o.width / 2);
      const d = Math.hypot(mx - cx, my - cy); if (d < bd) { bd = d; best = { key: "openings", ri: i }; }
    });
  } else if (key === "flooring") {
    const room = (S.plan.rooms || []).find(r => mx >= r.x && mx <= r.x + r.w && my >= r.y && my <= r.y + r.h);
    if (room) { const i = (S.plan.flooring || []).findIndex(f => f.room === room.name); if (i >= 0) best = { key: "flooring", ri: i }; }
  } else if (key === "elec") {        // point fixtures: light / AC / switchboard / fan …
    bd = 1.0;                         // generous click radius for tiny symbols
    (S.plan.elec || []).forEach((e, i) => {
      const d = Math.hypot(mx - e.x, my - e.y);
      if (d < bd) { bd = d; best = { key: "elec", ri: i }; }
    });
  } else if (key === "pipes") {       // plumbing pipe runs + fittings (VISIBLE only)
    (S.plan.pipes || []).forEach((r, i) => {
      if (!pipeVisible(r)) return;
      const P = r.pts || [];
      for (let k = 0; k < P.length - 1; k++) {
        const d = _distSeg(mx, my, P[k][0], P[k][1], P[k + 1][0], P[k + 1][1]);
        if (d < bd) { bd = d; best = { key: "pipes", ri: i }; }
      }
    });
    // gully trap / manhole / nahani / stacks etc. — drag these too
    (S.plan.plumb || []).forEach((p, i) => {
      if (!pipeVisible(p)) return;
      const d = Math.hypot(mx - p.x, my - p.y);
      if (d < Math.max(bd, 1.0) && d < 1.0) { bd = d; best = { key: "plumb", ri: i }; }
    });
  } else {                            // boxes: furniture / columns / rooms / stairs / steps
    const centred = key === "columns";
    (S.plan[key] || []).forEach((it, i) => {
      const w = +it.w || 0, h = +it.h || 0, x0 = centred ? it.x - w / 2 : it.x, y0 = centred ? it.y - h / 2 : it.y;
      let tx = mx, ty = my;
      const ang = +it.angle || 0;
      if (ang) {                      // a rotated piece: test in ITS frame
        const p = rotPt(mx, my, x0 + w / 2, y0 + h / 2, -ang); tx = p[0]; ty = p[1];
      }
      if (tx >= x0 && tx <= x0 + w && ty >= y0 && ty <= y0 + h) { best = { key, ri: i }; bd = 0; }
    });
  }
  return best;
}

function buildHandles(info) {
  clearHandles();
  if (!S.plan || !info || !_sel) return;
  // beam layout is editable in the beam view (drag / move / snap the beams);
  // section / structural / elevation views stay read-only.
  const beamEdit = S.beamView && !S.structView && _sel.key === "beams";
  if ((S.sectionView || S.structView || S.elevView || (S.beamView && !beamEdit))) return;
  if (allFloorsView() || !POSCFG[_sel.key]) return;
  const _ae = activeEditKey();                        // Plumbing tab edits pipes + fittings
  if (_sel.key !== _ae && !(_ae === "pipes" && _sel.key === "plumb")) return;
  if (POSCFG[_sel.key].coord === "none") return;     // flooring: settings only, no drag
  const it = selItem(); if (!it) return;
  const holder = $("#plHolder"), draw = holder.querySelector("svg"); if (!draw) return;
  const ov = document.createElementNS(NS_SVG, "svg");
  ov.id = "plHandles";
  ov.setAttribute("viewBox", `0 0 ${info.w_mm} ${info.h_mm}`);
  ov.setAttribute("width", draw.getAttribute("width"));
  ov.setAttribute("height", draw.getAttribute("height"));
  ov.style.cssText = "position:absolute;left:0;top:0;pointer-events:none;overflow:visible";
  holder.appendChild(ov);
  const G = Math.max(1.7, info.w_mm * 0.009);

  const grip = (mx, my, cls, spec) => {
    const [sx, sy] = m2s(info, mx, my);
    const r = document.createElementNS(NS_SVG, "rect");
    r.setAttribute("x", sx - G / 2); r.setAttribute("y", sy - G / 2);
    r.setAttribute("width", G); r.setAttribute("height", G);
    r.setAttribute("class", "grip " + cls); r.style.pointerEvents = "auto";
    const dn = e => startDrag(e, spec);
    r.addEventListener("mousedown", dn); r.addEventListener("touchstart", dn, { passive: false });
    ov.appendChild(r);
  };
  const moveLine = (x1, y1, x2, y2, spec) => {
    const [ax, ay] = m2s(info, x1, y1), [bx, by] = m2s(info, x2, y2);
    const l = document.createElementNS(NS_SVG, "line");
    l.setAttribute("x1", ax); l.setAttribute("y1", ay); l.setAttribute("x2", bx); l.setAttribute("y2", by);
    l.setAttribute("class", "selhi"); l.style.pointerEvents = "auto";
    const dn = e => startDrag(e, spec);
    l.addEventListener("mousedown", dn); l.addEventListener("touchstart", dn, { passive: false });
    ov.appendChild(l);
  };
  const moveRect = (x0, y0, w, h, spec) => {
    const [ax, ay] = m2s(info, x0, y0 + h);       // svg top-left (y is flipped)
    const r = document.createElementNS(NS_SVG, "rect");
    r.setAttribute("x", ax); r.setAttribute("y", ay);
    r.setAttribute("width", w * info.k); r.setAttribute("height", h * info.k);
    r.setAttribute("class", "selhi"); r.style.pointerEvents = "auto";
    const dn = e => startDrag(e, spec);
    r.addEventListener("mousedown", dn); r.addEventListener("touchstart", dn, { passive: false });
    ov.appendChild(r);
  };
  const movePoly = (pts, spec) => {               // rotated footprint highlight
    const p = document.createElementNS(NS_SVG, "polygon");
    p.setAttribute("points", pts.map(q => m2s(info, q[0], q[1]).join(",")).join(" "));
    p.setAttribute("class", "selhi"); p.style.pointerEvents = "auto";
    const dn = e => startDrag(e, spec);
    p.addEventListener("mousedown", dn); p.addEventListener("touchstart", dn, { passive: false });
    ov.appendChild(p);
  };

  const key = _sel.key;
  if (key === "walls" || key === "beams" || key === "sections") {
    moveLine(it.x1, it.y1, it.x2, it.y2, { role: "seg-move" });
    grip(it.x1, it.y1, "g-end", { role: "seg-a" });
    grip(it.x2, it.y2, "g-end", { role: "seg-b" });
  } else if (key === "openings") {
    const w = wallById(it.wall_id);
    if (w) {
      const L = Math.hypot(w.x2 - w.x1, w.y2 - w.y1) || 1e-6, ux = (w.x2 - w.x1) / L, uy = (w.y2 - w.y1) / L;
      const ax = w.x1 + ux * it.pos, ay = w.y1 + uy * it.pos;
      const bx = w.x1 + ux * (it.pos + it.width), by = w.y1 + uy * (it.pos + it.width);
      moveLine(ax, ay, bx, by, { role: "open-move" });
      grip((ax + bx) / 2, (ay + by) / 2, "g-move", { role: "open-move" });
    }
  } else if (key === "elec") {                 // point fixture — one move grip (+size for fans/AC)
    grip(it.x, it.y, "g-move", { role: "pt-move" });
    if ((+it.size || 0) > 0) grip(it.x + (+it.size) / 2, it.y, "g-size", { role: "elec-size" });
    const eang = +it.angle || 0;               // rotate stalk (AC / boards / fans)
    const rp2 = rotPt(it.x, it.y + 1.5, it.x, it.y, eang);
    grip(rp2[0], rp2[1], "g-rot", { role: "rotate" });
  } else if (key === "pipes") {                 // pipe run: whole-run move + per-vertex drag
    const P = it.pts || [];
    for (let k = 0; k < P.length - 1; k++)
      moveLine(P[k][0], P[k][1], P[k + 1][0], P[k + 1][1], { role: "pipe-move" });
    P.forEach((p, vi) => grip(p[0], p[1], "g-end", { role: "pipe-vertex", vi }));
  } else if (key === "plumb") {                 // fitting (gully / manhole / trap / stack)
    grip(it.x, it.y, "g-move", { role: "pt-move" });
  } else {
    const centred = key === "columns", w = +it.w || 0, h = +it.h || 0;
    const x0 = centred ? it.x - w / 2 : it.x, y0 = centred ? it.y - h / 2 : it.y;
    const ang = +it.angle || 0;
    const corners = [[x0, y0], [x0 + w, y0], [x0, y0 + h], [x0 + w, y0 + h]];
    const ccx = x0 + w / 2, ccy = y0 + h / 2;
    if (ang) {                       // the box + grips TURN with the piece
      const rc = corners.map(c => rotPt(c[0], c[1], ccx, ccy, ang));
      movePoly([rc[0], rc[1], rc[3], rc[2]], { role: "box-move" });
      rc.forEach((c, i) => grip(c[0], c[1], "g-size", { role: "box-size", corner: i, centred }));
    } else {
      moveRect(x0, y0, w, h, { role: "box-move" });
      corners.forEach((c, i) => grip(c[0], c[1], "g-size", { role: "box-size", corner: i, centred }));
    }
    // room LABEL grip: drag the name + size text anywhere (offset stored)
    if (key === "rooms") {
      const lx = ccx + (+it.label_dx || 0), ly = ccy + (+it.label_dy || 0);
      grip(lx, ly, "g-move", { role: "label-move" });
    }
    // ROTATE handle on the piece itself (furniture): a stalk off the top edge —
    // drag it round to turn the piece, snapping every 15°
    if (POSCFG[key] && POSCFG[key].rot === "angle") {
      const stalk = h / 2 + 1.1;
      const [hx, hy] = rotPt(ccx, ccy + stalk, ccx, ccy, ang);
      const [ex, ey] = rotPt(ccx, ccy + h / 2, ccx, ccy, ang);
      const l = document.createElementNS(NS_SVG, "line");
      const [ax, ay] = m2s(info, ex, ey), [bx2, by2] = m2s(info, hx, hy);
      l.setAttribute("x1", ax); l.setAttribute("y1", ay);
      l.setAttribute("x2", bx2); l.setAttribute("y2", by2);
      l.setAttribute("class", "selhi");
      ov.appendChild(l);
      grip(hx, hy, "g-rot", { role: "rotate" });
    }
  }
}

function startDrag(e, spec) {
  e.preventDefault(); e.stopPropagation();
  const p = e.touches ? e.touches[0] : e;
  const g = screenToModel(p.clientX, p.clientY);
  const it = selItem(); if (!it || !g) return;
  _hdrag = { spec, it, gx: g[0], gy: g[1], init: JSON.parse(JSON.stringify(it)) };
  pushUndo();
}
function applyDrag(d, mx, my) {
  const it = d.it, sp = d.spec, I = d.init;
  _guides = [];                                  // rebuilt by snapX/snapY this move
  if (sp.role === "pt-move") { it.x = r4(snapX(mx)); it.y = r4(snapY(my)); }
  else if (sp.role === "rotate") {
    // drag the stalk round the piece's centre; the handle rests at the top
    // (90°) when angle = 0, and the angle snaps every 15°
    const rcx = ("w" in it) ? (+it.x + (+it.w || 0) / 2) : +it.x;
    const rcy = ("h" in it) ? (+it.y + (+it.h || 0) / 2) : +it.y;
    let a = Math.atan2(my - rcy, mx - rcx) * 180 / Math.PI - 90;
    a = ((Math.round(a / 15) * 15) % 360 + 360) % 360;
    it.angle = r4(a);
  }
  else if (sp.role === "elec-size") { it.size = r4(Math.max(0.5, 2 * Math.abs(mx - it.x))); }
  else if (sp.role === "label-move") {           // room name/size text offset
    it.label_dx = r4(mx - ((+it.x || 0) + (+it.w || 0) / 2));
    it.label_dy = r4(my - ((+it.y || 0) + (+it.h || 0) / 2));
  }
  else if (sp.role === "pipe-vertex") { const P = it.pts; if (P && P[sp.vi]) P[sp.vi] = [r4(snapX(mx)), r4(snapY(my))]; }
  else if (sp.role === "pipe-move") {
    const P = it.pts, IP = (I.pts || []); const dx = snapG(mx - d.gx), dy = snapG(my - d.gy);
    for (let k = 0; k < P.length && k < IP.length; k++) P[k] = [r4(IP[k][0] + dx), r4(IP[k][1] + dy)];
  }
  else if (sp.role === "seg-a") { const [x, y] = orthoEnd(mx, my, it.x2, it.y2); it.x1 = r4(x); it.y1 = r4(y); }
  else if (sp.role === "seg-b") { const [x, y] = orthoEnd(mx, my, it.x1, it.y1); it.x2 = r4(x); it.y2 = r4(y); }
  else if (sp.role === "seg-move") {
    const dx = snapG(mx - d.gx), dy = snapG(my - d.gy);
    it.x1 = r4(I.x1 + dx); it.x2 = r4(I.x2 + dx); it.y1 = r4(I.y1 + dy); it.y2 = r4(I.y2 + dy);
  } else if (sp.role === "open-move") {
    const w = wallById(it.wall_id); if (!w) return;
    const L = Math.hypot(w.x2 - w.x1, w.y2 - w.y1) || 1e-6, ux = (w.x2 - w.x1) / L, uy = (w.y2 - w.y1) / L;
    const proj = (mx - w.x1) * ux + (my - w.y1) * uy - it.width / 2;
    it.pos = r4(Math.min(Math.max(0, snapG(proj)), Math.max(0, L - it.width)));
  } else if (sp.role === "box-move") {
    it.x = r4(snapX(I.x + (mx - d.gx))); it.y = r4(snapY(I.y + (my - d.gy)));
  } else if (sp.role === "box-size") {
    const _ang = +I.angle || 0;
    if (sp.centred) {
      it.w = r4(Math.max(0.3, 2 * Math.abs(mx - I.x)));
      it.h = r4(Math.max(0.3, 2 * Math.abs(my - I.y)));
    } else if (_ang) {
      // a ROTATED piece resizes in its own frame: un-rotate the mouse about the
      // original centre, size against the fixed opposite corner, then carry the
      // new centre back through the rotation so the piece grows in place.
      const w0 = +I.w || 0, h0 = +I.h || 0, cx = I.x + w0 / 2, cy = I.y + h0 / 2;
      const lp = rotPt(mx, my, cx, cy, -_ang);
      const corners = [[I.x, I.y], [I.x + w0, I.y], [I.x, I.y + h0], [I.x + w0, I.y + h0]];
      const opp = { 0: 3, 1: 2, 2: 1, 3: 0 }[sp.corner];
      const fx = corners[opp][0], fy = corners[opp][1];
      const nw = Math.max(0.3, Math.abs(lp[0] - fx)), nh = Math.max(0.3, Math.abs(lp[1] - fy));
      const nx = Math.min(fx, lp[0]), ny = Math.min(fy, lp[1]);
      const nc = rotPt(nx + nw / 2, ny + nh / 2, cx, cy, _ang);
      it.w = r4(nw); it.h = r4(nh);
      it.x = r4(nc[0] - nw / 2); it.y = r4(nc[1] - nh / 2);
    } else {
      const w = +I.w || 0, h = +I.h || 0;
      const corners = [[I.x, I.y], [I.x + w, I.y], [I.x, I.y + h], [I.x + w, I.y + h]];
      const opp = { 0: 3, 1: 2, 2: 1, 3: 0 }[sp.corner];
      const fx = corners[opp][0], fy = corners[opp][1];
      const nx = snapX(mx), ny = snapY(my);
      it.x = r4(Math.min(fx, nx)); it.y = r4(Math.min(fy, ny));
      it.w = r4(Math.max(0.3, Math.abs(nx - fx))); it.h = r4(Math.max(0.3, Math.abs(ny - fy)));
    }
    // a hand-resized piece prints the size you gave it — drop the stale
    // label cap so the printed size follows the handles (furniture only)
    if ("size_w" in it || "size_h" in it) { delete it.size_w; delete it.size_h; }
  }
}
function clearGuides() { const g = document.getElementById("plGuides"); if (g) g.remove(); }
function drawGuides(info) {                       // temporary dashed alignment lines
  clearGuides();
  if (!_guides.length || !info) return;
  const holder = $("#plHolder"), draw = holder.querySelector("svg"); if (!draw) return;
  const ov = document.createElementNS(NS_SVG, "svg");
  ov.id = "plGuides";
  ov.setAttribute("viewBox", `0 0 ${info.w_mm} ${info.h_mm}`);
  ov.setAttribute("width", draw.getAttribute("width"));
  ov.setAttribute("height", draw.getAttribute("height"));
  ov.style.cssText = "position:absolute;left:0;top:0;pointer-events:none;overflow:visible";
  holder.appendChild(ov);
  const seen = new Set();
  _guides.forEach(gd => {
    const kk = gd.axis + gd.at.toFixed(3); if (seen.has(kk)) return; seen.add(kk);
    const l = document.createElementNS(NS_SVG, "line");
    if (gd.axis === "v") { const sx = gd.at * info.k + info.ox; l.setAttribute("x1", sx); l.setAttribute("x2", sx); l.setAttribute("y1", 0); l.setAttribute("y2", info.h_mm); }
    else { const sy = info.h_mm - (gd.at * info.k + info.oy); l.setAttribute("y1", sy); l.setAttribute("y2", sy); l.setAttribute("x1", 0); l.setAttribute("x2", info.w_mm); }
    l.setAttribute("class", "aguide");
    ov.appendChild(l);
  });
}
/* ── reference / guide lines (user-placed, vertical or horizontal) ──── */
function _planBounds() {
  const xs = [], ys = [];
  ((S.plan && S.plan.rooms) || []).forEach(r => { xs.push(r.x, r.x + (+r.w || 0)); ys.push(r.y, r.y + (+r.h || 0)); });
  ((S.plan && S.plan.walls) || []).forEach(w => { xs.push(w.x1, w.x2); ys.push(w.y1, w.y2); });
  if (!xs.length) return { x0: 0, y0: 0, x1: 20, y1: 20 };
  return { x0: Math.min(...xs), y0: Math.min(...ys), x1: Math.max(...xs), y1: Math.max(...ys) };
}
function addRef(axis) {                           // axis "v" (vertical) | "h" (horizontal)
  if (!S.plan) { toast && toast("Pehle plan generate karein"); return; }
  if (!Array.isArray(S.plan.refs)) S.plan.refs = [];
  const b = _planBounds();
  const at = axis === "v" ? r4((b.x0 + b.x1) / 2) : r4((b.y0 + b.y1) / 2);
  S.plan.refs.push({ axis, at });
  S.refSel = S.plan.refs.length - 1;
  markDirty && markDirty(); drawRefs(S.plInfo);
}
function deleteRef(i) {
  if (!S.plan || !S.plan.refs || i == null || i < 0) return;
  S.plan.refs.splice(i, 1); S.refSel = null;
  markDirty && markDirty(); drawRefs(S.plInfo);
}
function clearRefs() {
  if (S.plan && S.plan.refs) S.plan.refs = [];
  S.refSel = null; markDirty && markDirty(); drawRefs(S.plInfo);
}
/* Architectural dimensions — toggle automatic INTERNAL (clear, inner-face to
   inner-face) dimensions. The server (draw_auto_dims) measures each room's CLEAR
   size from its wall faces (the 9'-7" the drawing prints, not the centre-line
   10'-0"), places the width below the room and the height to its left, and
   breaks the chain at every door/window. Drawn on the DIM layer. */
function autoDims() {
  if (!S.plan || !((S.plan.walls) || []).length) { status("Pehle plan generate/khol karein"); return; }
  if (S.plan.autodim) {                        // toggle OFF
    S.plan.autodim = false; markDirty(); redraw(); status("dimensions off");
    return;
  }
  S.plan.autodim = true;
  S.plan.dims = [];                            // use the auto internal dims, not old chains
  if (S.layerState) Object.keys(S.layerState).forEach(k => { if (/dim/i.test(k)) S.layerState[k] = true; });
  markDirty(); redraw();
  status("internal (clear) dimensions added — click Dimensions again to remove");
}
let _refDrag = null;
function drawRefs(info) {
  const old = document.getElementById("plRefs"); if (old) old.remove();
  if (!S.plan || !info || !S.plan.refs || !S.plan.refs.length) return;
  const holder = $("#plHolder"), draw = holder.querySelector("svg"); if (!draw) return;
  const ov = document.createElementNS(NS_SVG, "svg");
  ov.id = "plRefs";
  ov.setAttribute("viewBox", `0 0 ${info.w_mm} ${info.h_mm}`);
  ov.setAttribute("width", draw.getAttribute("width"));
  ov.setAttribute("height", draw.getAttribute("height"));
  ov.style.cssText = "position:absolute;left:0;top:0;pointer-events:none;overflow:visible";
  holder.appendChild(ov);
  const G = Math.max(1.7, info.w_mm * 0.009);
  S.plan.refs.forEach((r, i) => {
    let x1, y1, x2, y2;
    if (r.axis === "v") { const sx = r.at * info.k + info.ox; x1 = x2 = sx; y1 = 0; y2 = info.h_mm; }
    else { const sy = info.h_mm - (r.at * info.k + info.oy); y1 = y2 = sy; x1 = 0; x2 = info.w_mm; }
    const line = document.createElementNS(NS_SVG, "line");
    line.setAttribute("x1", x1); line.setAttribute("y1", y1); line.setAttribute("x2", x2); line.setAttribute("y2", y2);
    line.setAttribute("class", "refline");
    if (i === S.refSel) line.style.strokeWidth = "2";
    ov.appendChild(line);
    const hit = document.createElementNS(NS_SVG, "line");
    hit.setAttribute("x1", x1); hit.setAttribute("y1", y1); hit.setAttribute("x2", x2); hit.setAttribute("y2", y2);
    hit.setAttribute("class", "refhit");
    const dn = e => startRefDrag(e, i);
    hit.addEventListener("mousedown", dn); hit.addEventListener("touchstart", dn, { passive: false });
    ov.appendChild(hit);
    if (i === S.refSel) {          // delete handle at the near end
      const [bx, by] = r.axis === "v" ? [x1, 14] : [14, y1];
      const del = document.createElementNS(NS_SVG, "rect");
      del.setAttribute("x", bx - G / 2); del.setAttribute("y", by - G / 2);
      del.setAttribute("width", G); del.setAttribute("height", G);
      del.setAttribute("class", "grip"); del.setAttribute("fill", "#f43f5e"); del.setAttribute("stroke", "#fff");
      del.style.pointerEvents = "auto"; del.style.cursor = "pointer";
      const rm = e => { e.preventDefault(); e.stopPropagation(); deleteRef(i); };
      del.addEventListener("mousedown", rm); del.addEventListener("touchstart", rm, { passive: false });
      ov.appendChild(del);
    }
  });
}
function startRefDrag(e, i) {
  e.preventDefault(); e.stopPropagation();
  S.refSel = i; _refDrag = i; drawRefs(S.plInfo);
}
function _refMove(e) {
  if (_refDrag == null) return;
  const p = e.touches ? e.touches[0] : e;
  const m = screenToModel(p.clientX, p.clientY); if (!m) return;
  const r = S.plan.refs[_refDrag]; if (!r) return;
  _guides = [];
  r.at = r4(r.axis === "v" ? snapX(m[0]) : snapY(m[1]));
  drawRefs(S.plInfo); drawGuides(S.plInfo);
  if (e.cancelable) e.preventDefault();
}
function _refEnd() { if (_refDrag == null) return; _refDrag = null; _guides = []; clearGuides(); markDirty && markDirty(); }
addEventListener("mousemove", _refMove);
addEventListener("touchmove", _refMove, { passive: false });
addEventListener("mouseup", _refEnd);
addEventListener("touchend", _refEnd);
addEventListener("touchcancel", _refEnd);
let _lastDragRender = 0;
function _dragMove(e) {
  if (!_hdrag) return;
  const p = e.touches ? e.touches[0] : e;
  const m = screenToModel(p.clientX, p.clientY); if (!m) return;
  applyDrag(_hdrag, m[0], m[1]);
  markDirty();
  // The grips + guides follow the finger every frame (cheap, client-side). The
  // heavy plan redraw (server round-trip — the real source of lag, esp. on the
  // electrical sheet) is throttled to ~11/s; the final one lands on release.
  buildHandles(S.plInfo);
  drawGuides(S.plInfo);
  if (typeof updateGizmoCoords === "function") updateGizmoCoords();
  const now = Date.now();
  if (now - _lastDragRender > 90) { _lastDragRender = now; redraw(); }
  if (e.cancelable) e.preventDefault();
}
function _dragEnd() {
  if (!_hdrag) return;
  _hdrag = null; clearGuides(); redraw(); buildHandles(S.plInfo);
  if (_sel && typeof showGizmo === "function") showGizmo();   // W/H fields refresh
}
addEventListener("mousemove", _dragMove);
addEventListener("touchmove", _dragMove, { passive: false });
addEventListener("mouseup", _dragEnd);
addEventListener("touchend", _dragEnd);
addEventListener("touchcancel", _dragEnd);

/* click an element on the plan to select it (vs a pan / handle drag) */
(() => {
  const pv = $("#plView"); if (!pv) return;
  let dn = null;
  const down = e => { const p = e.touches ? e.touches[0] : e; dn = { x: p.clientX, y: p.clientY, t: e.target }; };
  const up = e => {
    if (!dn) return;
    const p = e.changedTouches ? e.changedTouches[0] : e;
    const moved = Math.hypot(p.clientX - dn.x, p.clientY - dn.y);
    const onHandle = dn.t && dn.t.closest && dn.t.closest("#plHandles");
    const wasDn = dn; dn = null;
    if (moved > 5 || onHandle || _hdrag) return;      // a pan or a handle drag
    const beamEdit = S.beamView && !S.structView && activeEditKey() === "beams";
    if (S.sectionView || S.structView || S.elevView || (S.beamView && !beamEdit)) return;
    const ek = activeEditKey(); if (!ek) return;       // no tool open → canvas just pans
    const m = screenToModel(p.clientX, p.clientY); if (!m) return;
    const hit = hitTest(m[0], m[1], ek);               // only the open tool's type
    if (hit) selectItem(hit.key, hit.ri);
    else { _sel = null; clearHandles(); showGizmo();
      $$("tr.selrow,.litem.on").forEach(t => t.classList.remove("selrow", "on")); }
  };
  pv.addEventListener("mousedown", down);
  pv.addEventListener("mouseup", up);
  pv.addEventListener("touchstart", down, { passive: true });
  pv.addEventListener("touchend", up);
})();

/* ── stage buttons ───────────────────────────────────────────
   A stage that is already in the file cannot be run again by accident: the
   button turns into a "done" state and says how to redo it deliberately.
   Loading a JSON that already carries a furniture or electrical layout locks
   those stages the same way.                                                */
function refreshStageButtons() {
  const has = k => ((S.plan && S.plan[k]) || []).length;
  const set = (id, done, label, n, what) => {
    const b = $("#" + id);
    if (!b) return;
    b.disabled = !S.plan;
    b.classList.toggle("done", !!done);
    b.textContent = done ? `✓ ${label} (${n})` : label;
    b.title = done
      ? `${n} ${what} already in this plan. Click to lay them out again — `
        + `that replaces what is there.`
      : `Lay out the ${what}`;
  };
  set("btnFurn", has("furniture"), "Furniture Layout",
      has("furniture"), "furniture");
  set("btnElec", has("elec"), "Electrical Layout",
      has("elec"), "electrical points");
  set("btnPlumb", has("plumb"), "Plumbing Layout",
      has("plumb"), "plumbing points");
  set("btnFloor", has("flooring"), "Flooring Drawing",
      has("flooring"), "floored rooms");
  // action buttons: enabled whenever there is a plan
  ["btnBoq", "btnSection", "btnBeam", "btnElev"].forEach(id => {
    const b = $("#" + id);
    if (b) b.disabled = !S.plan;
  });
  if (typeof updateSecToggle === "function") updateSecToggle();
}

/* ── layers ──────────────────────────────────────────────────
   Everything the software draws sits on a layer, and every layer can be
   turned off — on screen and in the exports. That is what lets you look at
   the electrical with the furniture hidden, or the bare shell on its own.
   The three view buttons are starting points; any group can still be toggled
   by hand afterwards.                                                       */
async function loadLayers() {
  if (LAYERS.groups) return;
  const r = await api().layer_groups();
  if (!r.ok) return fail(r);
  LAYERS.groups = r.groups;
  LAYERS.views = r.views;
  if (!S.layerState) {
    S.layerState = {};
    r.groups.forEach(g => S.layerState[g.key] = g.default);
  }
}

const LAYERS = { groups: null, views: null };

async function showLayers() {
  await loadLayers();
  const host = $("#p-layerspanel");
  if (!LAYERS.groups) return;
  const views = [["floor", "Floor plan"], ["furniture", "Furniture"],
                 ["electrical", "Electrical"], ["watersupply", "Water supply"],
                 ["drainage", "Drainage"], ["flooring", "Flooring"],
                 ["all", "Everything"]];
  host.innerHTML =
    '<div class="row" style="margin:0 0 10px">'
    + views.map(([k, l]) =>
        `<button class="btn" data-view="${k}">${l}</button>`).join("")
    + '</div><div class="sub" style="margin-bottom:8px">A view is a starting '
    + 'point — tick anything on or off afterwards. This applies to the drawing '
    + 'on screen and to every export.</div>'
    + '<div class="lay">' + LAYERS.groups.map(g =>
        `<label class="layrow"><input type="checkbox" data-lay="${g.key}"`
        + `${S.layerState[g.key] ? " checked" : ""}> ${esc(g.label)}`
        + `<span class="sub">${g.layers.join(" ")}</span></label>`).join("")
    + '</div>';

  $$("#p-layerspanel [data-view]").forEach(b => b.onclick = () => {
    const want = new Set(LAYERS.views[b.dataset.view] || []);
    LAYERS.groups.forEach(g => S.layerState[g.key] = want.has(g.key));
    S.curView = b.dataset.view;
    showLayers(); redraw();
    status(b.textContent + " view");
  });
  $$("#p-layerspanel [data-lay]").forEach(c => c.onchange = () => {
    S.layerState[c.dataset.lay] = c.checked;
    redraw();
  });
}

/* ── electrical ──────────────────────────────────────────────*/
function showCircuits() {
  const host = $("#p-circuits");
  if (!host) return;                 // the Circuits tab was removed
  const cks = (S.plan && S.plan.circuits) || [];
  if (!cks.length) {
    host.innerHTML = '<div class="sub">Press <b>Electrical Layout</b> — the '
      + 'circuit division, the load calculation and the DB schedule appear '
      + 'here.</div>';
    return;
  }
  const s = (S.plan && S.plan.elec_summary) || {};
  const rows = cks.map(c => `<tr>
      <td>${esc(c.id)}</td><td>${esc(c.description || "")}</td>
      <td>${esc((c.rooms || []).join(", "))}</td>
      <td class="num">${c.points}</td>
      <td class="num">${Math.round(c.load_w)}</td>
      <td>${esc(c.mcb || "")}</td><td>${esc(c.wire || "")}</td></tr>`).join("");
  host.innerHTML =
    `<div class="sub" style="margin-bottom:8px">Connected `
    + `<b>${((s.connected_w || 0) / 1000).toFixed(2)} kW</b> · demand with `
    + `diversity <b>${((s.demand_w || 0) / 1000).toFixed(2)} kW</b> · `
    + `recommended sanctioned load <b>${s.sanctioned_kw || "—"} kW</b>. `
    + `RCCB 30 mA per DB, lighting and power on separate banks.</div>`
    + `<table><thead><tr><th>Ckt</th><th>Description</th><th>Rooms</th>`
    + `<th>Pts</th><th>Load W</th><th>MCB</th><th>Wire mm²</th></tr></thead>`
    + `<tbody>${rows}</tbody></table>`;
}

/* ── Vaastu compliance table ─────────────────────────────────
   Every piece is listed, complying or not. A deviation is never hidden and
   never silently corrected — Vaastu ranks below safety and ergonomics, so a
   piece that had to move says so.                                          */
function showVaastu() {
  const host = $("#p-vaastu");
  const items = (S.plan && S.plan.furniture) || [];
  if (!items.length) {
    host.innerHTML = '<div class="sub">Press <b>Furniture Layout</b> to lay '
      + 'out the furniture; every piece is then checked against Vaastu here.'
      + '</div>';
    return;
  }
  const dev = items.filter(f => f.verdict === "DEVIATES");
  const ok = items.filter(f => f.verdict === "COMPLIES");
  const rows = items.map(f => `<tr>
      <td>${esc(f.tag || "")}</td>
      <td>${esc((f.kind || "").replace(/_/g, " "))}</td>
      <td>${esc(f.room || "")}</td>
      <td>${esc(f.zone || "")}</td>
      <td class="${f.verdict === "DEVIATES" ? "bad" : ""}">${esc(f.verdict || "n/a")}</td>
      <td>${esc(f.reason || f.note || "")}</td></tr>`).join("");
  host.innerHTML =
    `<div class="sub" style="margin-bottom:8px">${ok.length} comply · `
    + `<b>${dev.length} deviate</b> — Vaastu is traditional practice, not `
    + `building code. It never overrides safety, egress or ergonomics.</div>`
    + `<table><thead><tr><th>Tag</th><th>Piece</th><th>Room</th><th>Zone</th>`
    + `<th>Verdict</th><th>Note</th></tr></thead><tbody>${rows}</tbody></table>`;
}

/* ── auto-fix log ────────────────────────────────────────── */
function showFixes(fixes) {
  const p = $("#p-fixes"), b = $("#fixBadge");
  if (!p) return;                    // the Auto-fixes tab was removed
  fixes = fixes || [];
  p.innerHTML = fixes.length
    ? '<div class="sub" style="margin-bottom:8px">Corrections the software '
      + 'derived from the geometry rather than from the reading — swing sides, '
      + 'hinge jambs, and walls that only bounded open areas.</div>'
      + fixes.map(f => `<div class="issue warn"><span class="dot"></span>`
        + `<div>${esc(f)}</div></div>`).join("")
    : '<div class="good">Nothing needed correcting — the reading was already '
      + 'geometrically consistent.</div>';
  b.className = "badge show ok";
  b.textContent = fixes.length || "0";
}

/* ── validation panel ────────────────────────────────────── */
function showIssues(issues, sum) {
  const p = $("#p-issues");
  const badge = $("#badge");
  p.innerHTML = "";
  if (!issues.length) {
    p.innerHTML = '<div class="good">✓ All geometric checks passed — every '
      + 'opening lands on a wall, every door swings into its own room, no wall '
      + 'crosses a door, open areas carry no walls, the stair is a dog-leg.</div>';
  } else {
    issues.forEach(i => {
      const d = document.createElement("div");
      d.className = "issue " + (i.severity === "error" ? "error" : "warn");
      d.innerHTML = `<span class="dot"></span><div>${esc(i.message)}
        <div><code>${esc(i.code)}${i.ref ? " · " + esc(i.ref) : ""}</code>`
        + (i.rule ? ` <span class="rule">rulebook ${esc(i.rule)}</span>` : "")
        + `</div></div>`;
      p.appendChild(d);
    });
  }
  badge.className = "badge show " + (sum.errors ? "" : "ok");
  badge.textContent = sum.errors ? sum.errors + " ✕"
    : (sum.warnings ? sum.warnings + " !" : "OK");
}
const esc = s => String(s ?? "").replace(/[&<>"]/g,
  c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/* ── editable tables ─────────────────────────────────────── */
/* Which wall a point hangs on, as an angle. The symbols are drawn with the
   unit's back at the top and its throw running down, so 0° is a unit on the
   north wall blowing south, and the rest follow round. */
const FACE_COL = {
  opts: [["0", "N wall → blows S"], ["180", "S wall → blows N"],
         ["270", "E wall → blows W"], ["90", "W wall → blows E"]],
  get: r => String(Math.round((((+r.angle || 0) % 360) + 360) % 360)),
  set: (r, v) => { r.angle = parseFloat(v) || 0; },
};

/* Snap an item hard against the wall it is nearest to, so it sits perfectly
   flush without nudging coordinates by hand. Works for a furniture piece
   (x,y is its corner) or an electrical point / switchboard (x,y is its
   centre). It keeps the item on whichever side of the wall it is already on. */
/* Align a COLUMN to the nearest wall at 90°, sitting flush against ONE face of
   the wall (its outer face on the room side coincides with the wall face) — not
   centred on the wall / the T- or L-junction. */
function flushColumnFace(col) {
  const walls = (S.plan && S.plan.walls) || [];
  if (!walls.length) return false;
  const cx = +col.x, cy = +col.y;
  let best = null, bd = Infinity;
  for (const w of walls) {
    const ax = w.x1, ay = w.y1, vx = w.x2 - w.x1, vy = w.y2 - w.y1;
    const L2 = vx * vx + vy * vy || 1e-9;
    let t = Math.max(0, Math.min(1, ((cx - ax) * vx + (cy - ay) * vy) / L2));
    const px = ax + vx * t, py = ay + vy * t;
    const d = Math.hypot(cx - px, cy - py);
    if (d < bd) { bd = d; best = { w, px, py, horiz: Math.abs(vy) <= Math.abs(vx) }; }
  }
  if (!best) return false;
  const thk = (+best.w.thickness_in || 9) / 12;
  if (best.horiz) {                         // wall runs along X → offset in Y
    const cp = +col.h || 0.75;
    const side = (cy - best.py) >= 0 ? 1 : -1;
    col.x = r4(best.px);                     // centre it along the wall run
    col.y = r4(best.py + side * (thk / 2 - cp / 2));   // face flush with wall face
  } else {                                  // wall runs along Y → offset in X
    const cp = +col.w || 0.75;
    const side = (cx - best.px) >= 0 ? 1 : -1;
    col.y = r4(best.py);
    col.x = r4(best.px + side * (thk / 2 - cp / 2));
  }
  return true;
}

/* Flush a COLUMN against a wall of a CHOSEN orientation on a CHOSEN side, so at
   a T- or L-junction you decide which wall and which face:
     left / right  → nearest VERTICAL wall, column's L/R face on the wall face
     top  / bottom → nearest HORIZONTAL wall, column's T/B face on the wall face
   This is exact (no grid), so it always lands flush. */
function flushColumnSide(col, side) {
  const walls = (S.plan && S.plan.walls) || [];
  if (!walls.length) return false;
  const cx = +col.x, cy = +col.y;
  const wantV = (side === "left" || side === "right");
  let best = null, bd = Infinity;
  for (const w of walls) {
    const dx = w.x2 - w.x1, dy = w.y2 - w.y1;
    const isV = Math.abs(dx) < Math.abs(dy);
    if (isV !== wantV) continue;                 // only the needed orientation
    const L2 = dx * dx + dy * dy || 1e-9;
    const t = Math.max(0, Math.min(1, ((cx - w.x1) * dx + (cy - w.y1) * dy) / L2));
    const px = w.x1 + dx * t, py = w.y1 + dy * t, d = Math.hypot(cx - px, cy - py);
    if (d < bd) { bd = d; best = { px, py, thk: (+w.thickness_in || 9) / 12 }; }
  }
  if (!best) return false;
  if (wantV) {
    const cw = +col.w || 0.75, sign = side === "right" ? 1 : -1;
    col.y = r4(best.py);                          // sit on the wall line
    col.x = r4(best.px + sign * best.thk / 2 - sign * cw / 2);   // face flush
  } else {
    const ch = +col.h || 0.75, sign = side === "top" ? 1 : -1;
    col.x = r4(best.px);
    col.y = r4(best.py + sign * best.thk / 2 - sign * ch / 2);
  }
  return true;
}

/* Shift a BEAM sideways so ONE of its faces sits flush with the nearest wall's
   face on that side (instead of the beam being centred on the wall centre-line).
   side = "left"/"right" for a beam that runs vertically, "top"/"bottom" for one
   that runs horizontally. */
function flushBeam(beam, side) {
  const walls = (S.plan && S.plan.walls) || [];
  if (!walls.length) return;
  const mx = (beam.x1 + beam.x2) / 2, my = (beam.y1 + beam.y2) / 2;
  let best = null, bd = Infinity;
  for (const w of walls) {
    const ax = w.x1, ay = w.y1, vx = w.x2 - w.x1, vy = w.y2 - w.y1;
    const L2 = vx * vx + vy * vy || 1e-9;
    const t = Math.max(0, Math.min(1, ((mx - ax) * vx + (my - ay) * vy) / L2));
    const px = ax + vx * t, py = ay + vy * t, d = Math.hypot(mx - px, my - py);
    if (d < bd) { bd = d; best = { px, py, thk: (+w.thickness_in || 9) / 12 }; }
  }
  if (!best) return;
  const bw = (+beam.width_mm || 230) / 304.8;
  const vert = Math.abs(beam.y2 - beam.y1) >= Math.abs(beam.x2 - beam.x1);
  if (vert) {
    const sign = side === "right" ? 1 : -1;         // wall face on that side…
    const cx = best.px + sign * best.thk / 2 - sign * bw / 2;   // …= beam face
    beam.x1 = r4(cx); beam.x2 = r4(cx);
  } else {
    const sign = side === "top" ? 1 : -1;
    const cy = best.py + sign * best.thk / 2 - sign * bw / 2;
    beam.y1 = r4(cy); beam.y2 = r4(cy);
  }
}

function flushToWall(row, isFurn) {
  const walls = (S.plan && S.plan.walls) || [];
  if (!walls.length) return false;
  const cx = isFurn ? row.x + (+row.w || 0) / 2 : row.x;
  const cy = isFurn ? row.y + (+row.h || 0) / 2 : row.y;
  let best = null, bd = Infinity;
  for (const w of walls) {
    const ax = w.x1, ay = w.y1, bx = w.x2, by = w.y2;
    const vx = bx - ax, vy = by - ay, L2 = vx * vx + vy * vy || 1e-9;
    let t = ((cx - ax) * vx + (cy - ay) * vy) / L2;
    t = Math.max(0, Math.min(1, t));
    const px = ax + vx * t, py = ay + vy * t;
    const d = Math.hypot(cx - px, cy - py);
    if (d < bd) {
      bd = d;
      best = { w, px, py, horiz: Math.abs(vy) <= Math.abs(vx) };
    }
  }
  if (!best) return false;
  const thk = (+best.w.thickness_in || 4) / 12;
  if (best.horiz) {
    const half = isFurn ? (+row.h || 0) / 2 : 0.13;
    const side = cy >= best.py ? 1 : -1;
    const newCy = best.py + side * (thk / 2 + half);
    if (isFurn) row.y = r4(newCy - (+row.h || 0) / 2); else row.y = r4(newCy);
  } else {
    const half = isFurn ? (+row.w || 0) / 2 : 0.13;
    const side = cx >= best.px ? 1 : -1;
    const newCx = best.px + side * (thk / 2 + half);
    if (isFurn) row.x = r4(newCx - (+row.w || 0) / 2); else row.x = r4(newCx);
  }
  return true;
}
const COLS = {
  rooms: [
    ["name", "Room", "text", 1.6],
    ["x", "X", "num"], ["y", "Y", "num"], ["w", "W", "num"], ["h", "H", "num"],
    ["size_label", "Size label", "text", 1.5],
    ["open_area", "Open", "bool"],
    ["void", "Shaft", "bool"],
  ],
  walls: [
    ["id", "No.", "text"],
    ["room", "Room", "text", 1.3],
    ["x1", "X1", "num"], ["y1", "Y1", "num"], ["x2", "X2", "num"], ["y2", "Y2", "num"],
    // Length is derived, not stored: setting it holds the wall's midpoint and
    // moves BOTH ends, so the wall grows or shrinks evenly at each side.
    ["__len", "Length (ft)", { get: wallLength, set: setWallLength }],
    ["thickness_in", "Thk (in)", "num"],
    // its own height (blank = full storey) — same as clicking it in 3D
    ["height_ft", "Height (ft)", "num"],
    ["exterior", "Ext", "bool"],
    ["railing", "Railing", "bool"],
  ],
  openings: [
    ["type", "Type", ["single_door", "double_door", "sliding_door",
                      "window", "vent", "gate", "open"], 1.5],
    ["tag", "Tag", "text"],
    ["wall_id", "Wall", "wall"],
    ["pos", "Pos (ft)", "num"], ["width", "Width", "num"],
    ["swing.room", "Swings into", "room", 1.4],
    ["swing.hinge", "Hinge", ["start", "end"]],
    ["swing.side", "Side", ["left", "right"]],
    ["swing.manual", "Kept", "bool"],
    // Rulebook §2.5 / §3.2 / §4.2 — mandatory on every opening, in mm above FFL
    ["height_mm", "Height mm", "num"],
    ["sill_mm", "Sill mm", "num"],
    ["lintel_mm", "Lintel mm", "num"],
    ["count", "Nos", "num"],
  ],
  columns: [
    ["tag", "Tag", "text", 1.2],
    ["shape", "Shape", ["square", "rectangular", "round"], 1.4],
    ["x", "Xc", "num"], ["y", "Yc", "num"],
    ["w", "W/Dia ft", "num"], ["h", "H ft", "num"],
    ["room", "Room", "text", 1.3],
  ],
  sections: [
    ["tag", "Mark", "text", 1.2],
    ["x1", "X1", "num"], ["y1", "Y1", "num"],
    ["x2", "X2", "num"], ["y2", "Y2", "num"],
  ],
  beams: [
    ["tag", "No.", "text", 1.0],
    ["width_mm", "Width mm", "num"], ["depth_mm", "Depth mm", "num"],
    ["x1", "X1", "num"], ["y1", "Y1", "num"],
    ["x2", "X2", "num"], ["y2", "Y2", "num"],
  ],
  stairs: [
    ["type", "Type", ["U", "U3", "L", "straight"], 1.2],
    ["x", "X", "num"], ["y", "Y", "num"], ["w", "W", "num"], ["h", "H", "num"],
    ["run_axis", "Treads run", ["x", "y"]],
    ["up_from", "UP starts at", ["bottom", "top", "left", "right"]],
    ["turn_side", "Turn side", ["right", "left", "top", "bottom"]],
    ["steps_f1", "Steps 1", "num"], ["steps_f2", "Steps 2", "num"],
    ["steps_f3", "Steps mid", "num"],
    ["landing_size", "Landing (ft)", "num"],
    ["winders", "Turn steps", "num"],
    ["winder_style", "Turn style", ["straight", "fan"]],
    ["start_step", "First step no.", "num"],
    ["landing_depth", "Landing", "num"], ["well_gap", "Well", "num"],
    ["well", "Well?", "bool"], ["show_dn", "DN?", "bool"],
  ],
  elec: [
    ["tag", "Tag", "text", 1.4],
    ["code", "Type", ["SL", "ASL", "PL", "CSL", "CV", "WL", "BWL", "HL",
                      "CH", "ML", "STL", "TR", "CF", "EF", "AC", "SB", "DB"]],
    ["room", "Room", "text", 1.2],
    ["x", "X", "num"], ["y", "Y", "num"],
    ["watts", "W", "num"],
    ["height_mm", "Ht mm", "num"],
    ["size", "Size", "num"],
    // which wall the unit hangs on. An AC, a wall light or an adjustable
    // spot has to face into the room; the angle alone reads as nothing on a
    // table, so the choice is offered as the wall itself.
    ["__face", "Faces", FACE_COL, 1.7],
    ["circuit", "Circuit", "text"],
    ["visible", "Show", "bool"],
  ],
  pipes: [
    ["system", "System", ["CW", "HW", "SOIL", "WASTE", "VENT", "STORM", "ACD"]],
    ["dia_mm", "Ø mm", "num"],
    ["visible", "Show", "bool"],
  ],
  flooring: [
    ["room", "Room", "text", 1.4],
    ["material", "Material", ["tile", "marble", "wood", "granite"]],
    ["tile_w", "W mm", "num"], ["tile_h", "H mm", "num"],
    ["spacer_mm", "Spacer mm", "num"],
    ["start", "Start", ["symmetry", "entry", "corner-sw", "corner-se",
                        "corner-nw", "corner-ne", "feature"]],
    ["skirting_mm", "Skirt mm", "num"],
    ["skirting_type", "Skirt type", ["surface", "flush", "groove",
                                     "recessed", "wooden beading"]],
    ["drop_mm", "Drop mm", "num"],
    ["junction_drop", "Door drop", "bool"],
  ],
  furniture: [
    ["tag", "Tag", "text"],
    ["kind", "Piece", "text", 1.4],
    ["room", "Room", "text", 1.3],
    ["x", "X", "num"], ["y", "Y", "num"], ["w", "W", "num"], ["h", "H", "num"],
    ["angle", "Angle°", "num"],
    ["facing", "Faces", ["N", "S", "E", "W"]],
    ["zone", "Zone", "text"],
  ],
  steps: [
    ["x", "X", "num"], ["y", "Y", "num"], ["w", "W", "num"], ["h", "H", "num"],
    ["count", "Treads", "num"],
    ["run_axis", "Treads run", ["x", "y"]],
    ["up_from", "UP starts at", ["left", "right", "bottom", "top"]],
    ["levels", "Levels (comma)", "list", 1.6],
    ["label", "Label", "text"],
  ],
};
const BLANK = {
  rooms: { name: "New room", x: 0, y: 0, w: 10, h: 10, size_label: "", open_area: false, void: false, label_dx: 0, label_dy: 0 },
  walls: { id: "W-N", x1: 0, y1: 0, x2: 10, y2: 0, thickness_in: 4, exterior: false, railing: false },
  openings: { type: "single_door", tag: "D", wall_id: "", pos: 1, width: 3, swing: { room: "", hinge: "start", side: "left" }, height_mm: 2100, sill_mm: 0, lintel_mm: 2100, count: 1 },
  columns: { tag: "C", shape: "square", x: 5, y: 5, w: 0.75, h: 0.75, room: "" },
  sections: { tag: "A", x1: 0, y1: 0, x2: 10, y2: 0 },
  beams: { tag: "B", x1: 0, y1: 0, x2: 10, y2: 0, width_mm: 230, depth_mm: 300 },
  stairs: { type: "U", x: 0, y: 0, w: 9, h: 8, run_axis: "y", up_from: "bottom", turn_side: "right", steps_f1: 9, steps_f2: 9, steps_f3: 2, landing_size: 3, winders: 0, start_step: 0, landing_depth: 0, well_gap: 0, well: true, show_dn: true },
  steps: { x: 0, y: 0, w: 2, h: 6, count: 2, run_axis: "x", up_from: "left", levels: [], label: "" },
  furniture: { kind: "wardrobe", tag: "F", room: "", x: 0, y: 0, w: 2, h: 6, angle: 0, facing: "N", chairs: 0, zone: "" },
  elec: { code: "SL", tag: "SL", room: "", x: 0, y: 0, watts: 9, height_mm: 0, size: 0, angle: 0, circuit: "", visible: true, controls: [] },
  pipes: { system: "SOIL", dia_mm: 110, pts: [], length_ft: 0, tag: "", visible: true },
  flooring: { room: "", rx: 0, ry: 0, material: "tile", finish: "Matt", tile_w: 600, tile_h: 600, spacer_mm: 2, start: "symmetry", start_dx: 0, start_dy: 0, skirting_mm: 75, skirting_type: "surface", drop_mm: 0, junction_drop: true, code: "VT-01", visible: true },
};

/* ── wall length ─────────────────────────────────────────────
   A wall is stored as its two centre-line ends. Editing those one at a time to
   lengthen a wall is fiddly and easy to get wrong, so length is offered
   directly: the midpoint stays put and both ends move out (or in) equally.   */
const r4 = v => Math.round(v * 10000) / 10000;

/* Spinner step for a numeric field: mm fields nudge 1 mm, inch fields ¼", whole-
   count fields 1, and everything measured in feet nudges on the 0.05 ft grid —
   so the up/down arrows fine-tune instead of jumping a whole foot. */
const stepFor = path => {
  const p = String(path || "");
  if (/_mm$/.test(p)) return "1";
  if (/_in$/.test(p)) return "0.25";
  if (/^(count|leaves|points|watts|winders|start_step)$/.test(p)
      || /^steps_/.test(p)) return "1";
  return "0.02";                    // feet fields nudge on a fine 0.02 ft grid
};

function wallLength(w) {
  return r4(Math.hypot((w.x2 || 0) - (w.x1 || 0), (w.y2 || 0) - (w.y1 || 0)));
}

function wallUnit(w) {
  const L = wallLength(w);
  if (L < 1e-9) return { ux: 1, uy: 0 };          // degenerate: assume along x
  return { ux: ((w.x2 - w.x1) / L), uy: ((w.y2 - w.y1) / L) };
}

function setWallLength(w, L) {
  L = Math.max(0.05, +L || 0);
  const { ux, uy } = wallUnit(w);
  const mx = ((w.x1 || 0) + (w.x2 || 0)) / 2, my = ((w.y1 || 0) + (w.y2 || 0)) / 2;
  w.x1 = r4(mx - ux * L / 2); w.y1 = r4(my - uy * L / 2);
  w.x2 = r4(mx + ux * L / 2); w.y2 = r4(my + uy * L / 2);
}

/** Move one end along the wall's own direction: + extends, − trims. */
function extendWallEnd(w, which, d) {
  const { ux, uy } = wallUnit(w);
  if (which === "start") { w.x1 = r4(w.x1 - ux * d); w.y1 = r4(w.y1 - uy * d); }
  else                   { w.x2 = r4(w.x2 + ux * d); w.y2 = r4(w.y2 + uy * d); }
}

/* Wider than this and a door is a double — one leaf that big is neither built
   nor drawn. Kept in step with model.DOUBLE_DOOR_MM. */
const DOUBLE_MM = 1200;

const dig = (o, path) => path.split(".").reduce((a, k) => (a == null ? a : a[k]), o);
function put(o, path, v) {
  const ks = path.split(".");
  let t = o;
  for (const k of ks.slice(0, -1)) t = (t[k] = t[k] || {});
  t[ks.at(-1)] = v;
}

function buildTables() {
  for (const key of Object.keys(COLS)) buildTable(key);
  buildTitle();
  showVaastu();
  showCircuits();
  showLayers();
  refreshStageButtons();
}

/* The electrical table gets sub-categories. A whole floor's electrical runs to
   a hundred points, and hunting for one AC in that list is what made moving
   things painful. The FILTER ONLY NARROWS THE EDIT TABLE — the drawing keeps
   showing every layer, so nothing disappears from the plan. */
/* the sensible defaults each flooring material snaps to when picked */
const FLOOR_DEFAULTS = {
  tile:    { tile_w: 600, tile_h: 600, spacer_mm: 2, finish: "Matt",
             skirting_mm: 75, skirting_type: "surface" },
  marble:  { tile_w: 1200, tile_h: 800, spacer_mm: 1.5, finish: "Polished",
             skirting_mm: 100, skirting_type: "surface" },
  wood:    { tile_w: 1200, tile_h: 190, spacer_mm: 0, finish: "Matt lacquer",
             skirting_mm: 75, skirting_type: "wooden beading" },
  granite: { tile_w: 1200, tile_h: 600, spacer_mm: 3, finish: "Polished",
             skirting_mm: 75, skirting_type: "surface" },
};

const ELEC_CATS = [
  ["all", "All", null],
  ["light", "Lights", ["SL", "ASL", "PL", "CSL", "CV", "WL", "BWL", "HL",
                       "CH", "ML", "STL", "TR"]],
  ["fan", "Fans", ["CF", "EF"]],
  ["ac", "AC", ["AC"]],
  ["board", "Switchboards", ["SB", "DB"]],
];

function elecCatOf(code) {
  for (const [, label, codes] of ELEC_CATS) {
    if (codes && codes.includes(code)) return label;
  }
  return "Other";
}

/* The furniture categories come from the SAME catalogue the add dialog uses,
   so the chips can never drift from what the software can actually draw. */
const FURN = { map: null };

async function ensureFurnCats() {
  if (FURN.map) return;
  if (!AF.groups) {
    const r = await api().furniture_catalogue();
    if (!r.ok) return;
    AF.groups = r.groups;
  }
  const m = {};
  AF.groups.forEach(g => g.items.forEach(it => { m[it.kind] = g.category; }));
  FURN.map = m;
  buildTable("furniture");            // now the chips can be drawn
}

/* One chip bar, shared. `catOf` names a row's category, `order` is the order
   the chips appear in; only categories that actually have rows get a chip. */
function chipBar(host, rows, all, catOf, order, cur, onPick, what) {
  const present = order.filter(c => rows.some(r => catOf(r) === c));
  const bar = document.createElement("div");
  bar.className = "filters";
  const mk = (k, label, n) => {
    const b = document.createElement("button");
    b.className = "chip" + (k === cur ? " on" : "");
    b.innerHTML = `${esc(label)}<span class="n">${n}</span>`;
    b.title = k === "all" ? `every ${what}`
      : `edit only the ${label.toLowerCase()} — the drawing still shows all`;
    b.onclick = () => onPick(k);
    bar.appendChild(b);
  };
  mk("all", "All", rows.length);
  present.forEach(c => mk(c, c, rows.filter(r => catOf(r) === c).length));
  host.appendChild(bar);
  return cur === "all" ? all : all.filter(e => catOf(e.row) === cur);
}

function buildFilters(host, key, rows) {
  const all = rows.map((row, ri) => ({ row, ri }));

  if (key === "elec") {
    const order = ELEC_CATS.filter(c => c[2]).map(c => c[1]).concat("Other");
    return chipBar(host, rows, all, r => elecCatOf(r.code), order,
                   S.elecFilter || "all",
                   k => { S.elecFilter = k; buildTable(key); },
                   "electrical point");
  }

  if (key === "furniture") {
    if (!FURN.map) { ensureFurnCats(); return all; }
    const catOf = r => FURN.map[r.kind] || "Other";
    const order = AF.groups.map(g => g.category).concat("Other");
    return chipBar(host, rows, all, catOf, order,
                   S.furnFilter || "all",
                   k => { S.furnFilter = k; buildTable(key); },
                   "piece");
  }

  if (key === "flooring") {
    // room-wise: one chip per room, click a room to edit only its flooring
    const order = rows.map(r => r.room);
    return chipBar(host, rows, all, r => r.room, order,
                   S.floorFilter || "all",
                   k => { S.floorFilter = k; buildTable(key); },
                   "room's flooring");
  }
  if (key === "sections") {
    const bar = document.createElement("div");
    bar.className = "filters";
    const mk = (label, fn) => {
      const b = document.createElement("button");
      b.className = "chip"; b.textContent = label; b.onclick = fn;
      bar.appendChild(b);
    };
    mk("+ Horizontal cut", () => addSection("H"));
    mk("+ Vertical cut", () => addSection("V"));
    const hint = document.createElement("span");
    hint.className = "sub"; hint.style.marginLeft = "8px";
    hint.textContent = "add a cut line, drag its X/Y to place it, then press "
      + "Section in the top bar";
    bar.appendChild(hint);
    host.appendChild(bar);
    return all;
  }
  if (key === "columns") {
    const bar = document.createElement("div");
    bar.className = "filters";
    const b = document.createElement("button");
    b.className = "chip";
    b.textContent = "🧲 Snap all to wall face";
    b.title = "align every column 90° and flush against its nearest wall face "
      + "(off the junction centre)";
    b.onclick = () => {
      if (!(S.plan.columns || []).length) return;
      pushUndo();
      S.plan.columns.forEach(c => flushColumnFace(c));
      markDirty(); buildTable("columns"); redraw();
      status("columns snapped flush to the nearest wall face");
    };
    bar.appendChild(b);
    const hint = document.createElement("span");
    hint.className = "sub"; hint.style.marginLeft = "8px";
    hint.textContent = "or use the row buttons to move / rotate / flush each one";
    bar.appendChild(hint);
    host.appendChild(bar);
    return all;
  }
  if (key === "beams") {
    const bar = document.createElement("div");
    bar.className = "filters";
    const mk = (label, fn) => {
      const b = document.createElement("button");
      b.className = "chip"; b.textContent = label; b.onclick = fn;
      bar.appendChild(b);
    };
    mk("⟳ Regenerate (auto)", () => beamAction("regen"));
    mk("Set all widths…", () => beamAction("width"));
    mk("Set all depths…", () => beamAction("depth"));
    mk("Renumber", () => beamAction("renumber"));
    mk("Rebar / grades…", () => openStruct());
    const hint = document.createElement("span");
    hint.className = "sub"; hint.style.marginLeft = "8px";
    hint.textContent = "default width 230 mm; edit width/depth per beam, "
      + "rotate/move with the row buttons, then press Beam Layout";
    bar.appendChild(hint);
    host.appendChild(bar);
    return all;
  }
  return all;
}

function planExtents() {
  const xs = [], ys = [];
  (S.plan.walls || []).forEach(w => { xs.push(w.x1, w.x2); ys.push(w.y1, w.y2); });
  (S.plan.rooms || []).forEach(r => {
    xs.push(r.x, r.x + r.w); ys.push(r.y, r.y + r.h);
  });
  if (!xs.length) return [0, 0, 10, 10];
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

function addSection(dir) {
  if (!S.plan) return;
  pushUndo();
  const e = planExtents();
  const secs = S.plan.sections || (S.plan.sections = []);
  const tag = String.fromCharCode(65 + secs.length);   // A, B, C …
  if (dir === "H") {
    const y = r4((e[1] + e[3]) / 2);
    secs.push({ tag, x1: r4(e[0] - 1), y1: y, x2: r4(e[2] + 1), y2: y });
  } else {
    const x = r4((e[0] + e[2]) / 2);
    secs.push({ tag, x1: x, y1: r4(e[1] - 1), x2: x, y2: r4(e[3] + 1) });
  }
  syncSections(S.plan);          // the same cut sits on every floor
  markDirty(); buildTable("sections"); redraw(); updateSecToggle();
  status(`section line ${tag}-${tag} added — same position on every floor. `
    + `Drag it, then press Section`);
}

/* how many floors actually carry a plan (multi-floor set vs single) */
function floorsWithPlans() {
  return (S.floors || []).filter(f => f && f.plan).length;
}

/* Show ALL floors on one sheet? That view is a read-only composite. Editing
   always happens on the ACTIVE floor, so this is off unless asked for — a
   multi-floor project is otherwise fully editable, like a single plan. */
function allFloorsView() {
  const c = $("#chkAllFloors");
  return !!(c && c.checked) && floorsWithPlans() >= 2;
}

/* the section line(s) are SHARED by every floor at the same position — a cut
   added or moved on any floor shows on all of them, and the multi-floor
   section / elevation reads the same line through each floor's own plan */
function syncSections(srcPlan) {
  if (!srcPlan) return;
  const secs = srcPlan.sections || [];
  const clone = () => JSON.parse(JSON.stringify(secs));
  (S.floors || []).forEach(f => {
    if (f.plan && f.plan !== srcPlan) f.plan.sections = clone();
  });
}

/* run a stage (furniture / electrical / plumbing / flooring) on EVERY floor
   that has a plan and store each result back, so one click lays the stage over
   the whole project. Returns [{floor, r}] — check every r.ok. */
async function forEachFloorPlan(fn) {
  const out = [];
  const list = (S.floors || []).filter(f => f && f.plan);
  const targets = list.length ? list : (S.plan ? [S.floors[S.active]] : []);
  for (const f of targets) {
    const r = await fn(f.plan);
    if (r && r.ok && r.plan) f.plan = r.plan;
    out.push({ floor: f, r });
  }
  return out;
}
function stageTotal(res, key) {
  return res.reduce((s, x) => s + ((x.r && x.r[key]) || 0), 0);
}
function stageFailed(res) {
  return (res.find(x => !x.r || !x.r.ok) || {}).r;
}

/* the "Editing:" floor selector in the dock — which floor the tables edit,
   while the canvas keeps showing every floor together */
function renderEditFloor() {
  const wrap = $("#editFloorWrap"), sel = $("#editFloor");
  if (!wrap || !sel) return;
  const multi = allFloorsView();
  wrap.classList.toggle("hidden", !multi);
  if (!multi) return;
  sel.innerHTML = "";
  S.floors.forEach((f, i) => {
    if (!f.plan) return;
    const o = document.createElement("option");
    o.value = String(i);
    o.textContent = f.name || `Floor ${i + 1}`;
    if (i === S.active) o.selected = true;
    sel.appendChild(o);
  });
}
if ($("#editFloor")) $("#editFloor").onchange = e => {
  const i = parseInt(e.target.value, 10);
  if (isNaN(i) || i === S.active || !S.floors[i]) return;
  S.active = i;                       // the tables now edit this floor…
  S.undo = []; S.redo = [];
  buildTables();                      // …but the canvas keeps showing all floors
  renderFloorBar();
  status(`editing ${S.floors[i].name || "Floor " + (i + 1)} — `
    + `the canvas still shows every floor`);
};

/* keys whose flyout shows only a MINIMAL identity list (click a row → the gizmo
   opens with every editable field). Keeps the side panel clean. */
const LIST_COLS = {
  openings: ["type", "tag", "wall_id"],
  furniture: ["tag", "kind", "room"],
  elec: ["tag", "code", "room"],
  pipes: ["system", "dia_mm"],
  columns: ["tag", "shape", "room"],
  walls: ["id", "room", "thickness_in"],
  rooms: ["name", "size_label"],
  sections: ["tag"],
  beams: ["tag", "width_mm", "depth_mm"],
  stairs: ["type"],
  steps: ["label", "count"],
  flooring: ["room", "material"],
};
function listCell(row, col) {
  const v = dig(row, col[0]);
  if (v == null || v === "") return "—";
  return String(v).replace(/_/g, " ");
}

/* ONE editable control for a column (select / number / bool / wall / room /
   computed) with all the special-case wiring — shared by the table AND the
   gizmo so a door's swing, sill, lintel, width, retype … behave the same. */
function makeFieldEl(key, row, col) {
  const [path, , kind] = col;
  const calc = (kind && typeof kind === "object" && !Array.isArray(kind))
    ? kind : null;
  let el;
  if (calc && calc.opts) {
    el = document.createElement("select");
    el.innerHTML = calc.opts
      .map(o => `<option value="${o[0]}">${esc(o[1])}</option>`).join("");
    el.value = String(calc.get(row));
  } else if (calc) {
    el = document.createElement("input");
    el.type = "number";
    el.step = isFeetLen(path) ? unitStepAttr() : "0.05";
    el.value = isFeetLen(path) ? toDisp(calc.get(row)) : calc.get(row);
    el._isNum = true;
  } else if (Array.isArray(kind)) {
    el = document.createElement("select");
    el.innerHTML = '<option value=""></option>'
      + kind.map(o => `<option>${o}</option>`).join("");
    el.value = dig(row, path) ?? "";
  } else if (kind === "wall" || kind === "room") {
    el = document.createElement("select");
    const list = kind === "wall"
      ? (S.plan.walls || []).map(w => w.id)
      : (S.plan.rooms || []).map(r => r.name);
    el.innerHTML = '<option value=""></option>'
      + list.map(o => `<option>${esc(o)}</option>`).join("");
    el.value = dig(row, path) ?? "";
  } else if (kind === "bool") {
    el = document.createElement("select");
    el.innerHTML = "<option value='false'>no</option><option value='true'>yes</option>";
    el.value = String(!!dig(row, path));
  } else if (kind === "list") {
    el = document.createElement("input");
    el.value = (dig(row, path) || []).join(", ");
    el.placeholder = "+0'-6\", +1'-0\"";
  } else {
    el = document.createElement("input");
    if (kind === "num") {
      el.type = "number"; el._isNum = true;
      el.step = isFeetLen(path) ? unitStepAttr() : stepFor(path);
      // furniture shows its PRINTED size (drawn ÷ room scale) — the drawn
      // box carries the sketch's own stretch, the number is the truth
      let dv = dig(row, path);
      if (key === "furniture" && (path === "w" || path === "h")) {
        const k = furnScale(S.plan, row);
        dv = (+dv || 0) / (path === "w" ? k.kw : k.kh);
      }
      el.value = isFeetLen(path) ? toDisp(dv) : (dv ?? "");
    } else {
      el.value = dig(row, path) ?? "";
    }
  }
  el.onchange = () => {
    let v = el.value;
    if ((kind === "num" || (calc && !calc.opts)) && isFeetLen(path)) v = fromDisp(el.value);
    else if (kind === "num" || (calc && !calc.opts)) v = v === "" ? 0 : parseFloat(v);
    else if (kind === "bool") v = v === "true";
    else if (kind === "list") v = v.split(",").map(s => s.trim()).filter(Boolean);
    pushUndo();
    if (calc) { calc.set(row, v); markDirty(); refreshKey(key); redraw(); return; }
    if (key === "furniture" && (path === "w" || path === "h")) {
      // the typed number is the PRINTED size — draw it at the room's own
      // stretch so the box and the number stay linked
      const k = furnScale(S.plan, row);
      v = (+v || 0) * (path === "w" ? k.kw : k.kh);
      delete row.size_w; delete row.size_h;    // legacy cache, now derived
    }
    put(row, path, v);
    if (key === "flooring" && path === "material") {
      const dfl = FLOOR_DEFAULTS[v]; if (dfl) Object.assign(row, dfl); refreshKey(key);
    }
    if (path === "swing.hinge" || path === "swing.side") put(row, "swing.manual", true);
    let retype = false;
    if (key === "openings" && path === "width") {
      const mm = (+v || 0) * 304.8;
      if (row.type === "single_door" && mm > DOUBLE_MM) { row.type = "double_door"; retype = true; }
      else if (row.type === "double_door" && mm <= DOUBLE_MM) { row.type = "single_door"; retype = true; }
    }
    markDirty();
    if (retype) status(`${row.tag || "door"} is now a ${row.type.replace("_", " ")} `
      + `(${Math.round((+v || 0) * 304.8)} mm wide)`);
    if (retype || path.startsWith("swing.")) refreshKey(key);
    redraw();
  };
  return el;
}
/* rebuild the list/table AND (if it is showing) the gizmo for a key */
function refreshKey(key) {
  buildTable(key);
  if (_sel && _sel.key === key) showGizmo();
}

function buildTable(key) {
  const host = $("#p-" + key);
  if (!host || !COLS[key]) return;          // no panel for this key — skip safely
  const rows = S.plan[key] || (S.plan[key] = []);
  const listMode = !!LIST_COLS[key];
  const cols = listMode
    ? LIST_COLS[key].map(p => COLS[key].find(c => c[0] === p)).filter(Boolean)
    : COLS[key];

  host.innerHTML = "";
  if (key === "pipes") plumbViewSwitcher(host);   // Water supply / Drainage toggle
  const view = buildFilters(host, key, rows);

  const tbl = document.createElement("table");
  tbl.innerHTML = "<thead><tr>" + cols.map(c => `<th>${c[1]}</th>`).join("")
    + "<th></th></tr></thead>";
  const tb = document.createElement("tbody");

  view.forEach(({ row, ri }) => {
    const tr = document.createElement("tr");
    // positionable rows: click to pick the item up with the move gizmo
    if (POSCFG[key]) {
      tr.dataset.ri = ri;
      tr.style.cursor = "pointer";
      tr.addEventListener("click", () => selectItem(key, ri));
      if (_sel && _sel.key === key && _sel.ri === ri) tr.classList.add("selrow");
    }
    cols.forEach(c => {
      if (listMode) {                       // minimal read-only identity cell
        const td = document.createElement("td");
        td.className = "licell";
        td.textContent = listCell(row, c);
        tr.appendChild(td);
        return;
      }
      const [path, , kind] = c;
      // a computed column: not stored on the row, derived from it
      const calc = (kind && typeof kind === "object" && !Array.isArray(kind))
        ? kind : null;
      const td = document.createElement("td");
      let el;
      if (calc && calc.opts) {
        // a computed column with a fixed set of choices, e.g. which wall a
        // unit hangs on — the label is plain English, the value is the angle
        el = document.createElement("select");
        el.innerHTML = calc.opts
          .map(o => `<option value="${o[0]}">${esc(o[1])}</option>`).join("");
        el.value = String(calc.get(row));
      } else if (calc) {
        el = document.createElement("input");
        el.type = "number"; el.step = "0.05";
        el.value = calc.get(row);
        td.className = "num";
      } else if (Array.isArray(kind)) {
        el = document.createElement("select");
        el.innerHTML = '<option value=""></option>'
          + kind.map(o => `<option>${o}</option>`).join("");
        el.value = dig(row, path) ?? "";
      } else if (kind === "wall" || kind === "room") {
        el = document.createElement("select");
        const list = kind === "wall"
          ? (S.plan.walls || []).map(w => w.id)
          : (S.plan.rooms || []).map(r => r.name);
        el.innerHTML = '<option value=""></option>'
          + list.map(o => `<option>${esc(o)}</option>`).join("");
        el.value = dig(row, path) ?? "";
      } else if (kind === "bool") {
        el = document.createElement("select");
        el.innerHTML = "<option value='false'>no</option><option value='true'>yes</option>";
        el.value = String(!!dig(row, path));
      } else if (kind === "list") {
        el = document.createElement("input");
        el.value = (dig(row, path) || []).join(", ");
        el.placeholder = "+0'-6\", +1'-0\"";
      } else {
        el = document.createElement("input");
        el.value = dig(row, path) ?? "";
        if (kind === "num") { el.type = "number"; el.step = stepFor(path); td.className = "num"; }
      }
      el.onchange = () => {
        let v = el.value;
        if (kind === "num" || (calc && !calc.opts)) v = v === "" ? 0 : parseFloat(v);
        else if (kind === "bool") v = v === "true";
        else if (kind === "list") {
          v = v.split(",").map(s => s.trim()).filter(Boolean);
        }
        pushUndo();
        if (calc) { calc.set(row, v); markDirty(); buildTable(key); redraw(); return; }
        put(row, path, v);
        // Picking a flooring material resets the size, spacer and skirting to
        // that material's sensible defaults, which the user can then tweak.
        if (key === "flooring" && path === "material") {
          const dfl = FLOOR_DEFAULTS[v];
          if (dfl) Object.assign(row, dfl);
          buildTable(key);
        }
        // Editing a swing by hand means keep it: otherwise the auto-fix pass
        // recomputes it on the next redraw and the edit appears to do nothing.
        if (path === "swing.hinge" || path === "swing.side") {
          put(row, "swing.manual", true);
        }
        // A single leaf wider than 1200 mm is not built or drawn — widening a
        // door past that makes it a double door, and narrowing it back makes
        // it single again.
        let retype = false;
        if (key === "openings" && path === "width") {
          const mm = (+v || 0) * 304.8;
          if (row.type === "single_door" && mm > DOUBLE_MM) {
            row.type = "double_door"; retype = true;
          } else if (row.type === "double_door" && mm <= DOUBLE_MM) {
            row.type = "single_door"; retype = true;
          }
        }
        markDirty();
        if (retype) {
          status(`${row.tag || "door"} is now a ${row.type.replace("_", " ")} `
                 + `(${Math.round((+v || 0) * 304.8)} mm wide)`);
        }
        if (retype || path.startsWith("swing.")) buildTable(key);
        redraw();
      };
      td.appendChild(el);
      tr.appendChild(td);
    });
    const td = document.createElement("td");
    if (!listMode && key === "elec") {
      // move each light, fan, AC or board, and turn it on or off, without
      // typing coordinates. Shift = fine 3", Ctrl = coarse 1'-0".
      const btn = (label, title, fn) => {
        const b = document.createElement("button");
        b.className = "del"; b.textContent = label; b.title = title;
        b.onclick = e => {
          const d = e.shiftKey ? 0.25 : (e.ctrlKey ? 1 : 0.5);
          pushUndo(); fn(d, e); markDirty(); buildTable(key); redraw();
        };
        td.appendChild(b);
      };
      btn("←", "move left (Shift 3\", Ctrl 1')", d => row.x = r4(row.x - d));
      btn("→", "move right", d => row.x = r4(row.x + d));
      btn("↓", "move down", d => row.y = r4(row.y - d));
      btn("↑", "move up", d => row.y = r4(row.y + d));
      if (row.code === "CF" || row.code === "AC" || row.code === "TR"
          || row.code === "CV") {
        btn("+", "larger (fan sweep / unit length)",
            d => row.size = r4(Math.max(0.5, (+row.size || 3) + d)));
        btn("−", "smaller",
            d => row.size = r4(Math.max(0.5, (+row.size || 3) - d)));
      }
      // switchboards and the DB can be turned to sit flush on any wall
      if (row.code === "SB" || row.code === "DB") {
        btn("⟲", "turn anticlockwise (Shift 15°, else 90°)",
            (_d, e) => row.angle = r4(((+row.angle || 0)
                        + (e.shiftKey ? 15 : 90)) % 360));
        btn("⟳", "turn clockwise",
            (_d, e) => row.angle = r4(((+row.angle || 0)
                        - (e.shiftKey ? 15 : 90) + 360) % 360));
      }
      btn("🧲", "flush against the nearest wall", () => flushToWall(row, false));
      const eye = document.createElement("button");
      eye.className = "del";
      eye.textContent = row.visible === false ? "◌" : "◉";
      eye.title = row.visible === false ? "hidden — click to show"
                                        : "shown — click to hide";
      eye.onclick = () => {
        pushUndo(); row.visible = row.visible === false;
        markDirty(); buildTable(key); redraw();
      };
      td.appendChild(eye);
    }
    if (!listMode && key === "furniture") {
      // move, turn and resize the piece without typing coordinates.
      // Shift = fine (3"), Ctrl = coarse (1'-0"); rotation Shift = 15°.
      const btn = (label, title, fn) => {
        const b = document.createElement("button");
        b.className = "del"; b.textContent = label; b.title = title;
        b.onclick = e => {
          const d = e.shiftKey ? 0.25 : (e.ctrlKey ? 1 : 0.5);
          pushUndo(); fn(d, e); markDirty(); buildTable(key); redraw();
        };
        td.appendChild(b);
      };
      btn("←", "move left (Shift 3\", Ctrl 1')", d => row.x = r4(row.x - d));
      btn("→", "move right", d => row.x = r4(row.x + d));
      btn("↓", "move down", d => row.y = r4(row.y - d));
      btn("↑", "move up", d => row.y = r4(row.y + d));
      btn("⟲", "turn anticlockwise (Shift 15°, else 90°)",
          (_d, e) => row.angle = r4(((+row.angle || 0) + (e.shiftKey ? 15 : 90)) % 360));
      btn("⟳", "turn clockwise",
          (_d, e) => row.angle = r4(((+row.angle || 0) - (e.shiftKey ? 15 : 90) + 360) % 360));
      btn("+", "larger (both ways, about the centre)", d => {
        row.x = r4(row.x - d / 2); row.y = r4(row.y - d / 2);
        row.w = r4(Math.max(0.5, row.w + d)); row.h = r4(Math.max(0.5, row.h + d));
      });
      btn("−", "smaller", d => {
        row.x = r4(row.x + d / 2); row.y = r4(row.y + d / 2);
        row.w = r4(Math.max(0.5, row.w - d)); row.h = r4(Math.max(0.5, row.h - d));
      });
      btn("⇄", "swap width and height", () => {
        const w = row.w; row.w = row.h; row.h = w;
      });
      btn("🧲", "flush against the nearest wall", () => flushToWall(row, true));
    }
    if (!listMode && key === "sections") {
      // move the whole cut line, and rotate it about its centre
      const btn = (label, title, fn) => {
        const b = document.createElement("button");
        b.className = "del"; b.textContent = label; b.title = title;
        b.onclick = e => {
          const d = e.shiftKey ? 0.25 : (e.ctrlKey ? 1 : 0.5);
          pushUndo(); fn(d, e); markDirty(); buildTable(key); redraw();
        };
        td.appendChild(b);
      };
      const mv = (dx, dy) => {
        row.x1 = r4(row.x1 + dx); row.x2 = r4(row.x2 + dx);
        row.y1 = r4(row.y1 + dy); row.y2 = r4(row.y2 + dy);
      };
      btn("←", "move left (Shift 3\", Ctrl 1')", d => mv(-d, 0));
      btn("→", "move right", d => mv(d, 0));
      btn("↓", "move down", d => mv(0, -d));
      btn("↑", "move up", d => mv(0, d));
      const rot = deg => {
        const cx = (row.x1 + row.x2) / 2, cy = (row.y1 + row.y2) / 2;
        const a = deg * Math.PI / 180, c = Math.cos(a), s = Math.sin(a);
        const rp = (x, y) => [r4(cx + (x - cx) * c - (y - cy) * s),
                              r4(cy + (x - cx) * s + (y - cy) * c)];
        [row.x1, row.y1] = rp(row.x1, row.y1);
        [row.x2, row.y2] = rp(row.x2, row.y2);
      };
      btn("⟲", "turn anticlockwise (Shift 15°, else 90°)",
          (_d, e) => rot(e.shiftKey ? 15 : 90));
      btn("⟳", "turn clockwise", (_d, e) => rot(e.shiftKey ? -15 : -90));
      // flip which way the section looks (the arrow direction on the plan)
      const fb = document.createElement("button");
      fb.className = "del"; fb.textContent = "⇄";
      fb.title = "flip view direction (which side's first wall shows)";
      fb.onclick = async () => {
        pushUndo(); row.flip = !row.flip; markDirty(); buildTable(key);
        if (S.sectionView) { await regenSection(); } else { redraw(); }
        status(`section ${row.tag}: view flipped — arrow now points the other way`);
      };
      td.appendChild(fb);
    }
    if (!listMode && key === "columns") {
      // move in every direction, rotate (swap W/H at 90°), and snap flush to a
      // wall face at the junction (not centred on the intersection)
      const btn = (label, title, fn) => {
        const b = document.createElement("button");
        b.className = "del"; b.textContent = label; b.title = title;
        b.onclick = e => {
          const d = e.shiftKey ? 0.25 : (e.ctrlKey ? 1 : 0.5);
          pushUndo(); fn(d, e); markDirty(); buildTable(key); redraw();
        };
        td.appendChild(b);
      };
      btn("←", "move left (Shift 3\", Ctrl 1')", d => row.x = r4(row.x - d));
      btn("→", "move right", d => row.x = r4(row.x + d));
      btn("↓", "move down", d => row.y = r4(row.y - d));
      btn("↑", "move up", d => row.y = r4(row.y + d));
      btn("⟲", "rotate 90° (swap width / height)", () => {
        const w = row.w; row.w = row.h; row.h = w;
      });
      // directional flush — pick the wall (vertical → L/R, horizontal → T/B) and
      // the face; exact, so it always lands flush at a T- or L-junction
      btn("⇤L", "flush LEFT face to the nearest vertical wall",
          () => flushColumnSide(row, "left"));
      btn("⇥R", "flush RIGHT face to the nearest vertical wall",
          () => flushColumnSide(row, "right"));
      btn("⤒T", "flush TOP face to the nearest horizontal wall",
          () => flushColumnSide(row, "top"));
      btn("⤓B", "flush BOTTOM face to the nearest horizontal wall",
          () => flushColumnSide(row, "bottom"));
    }
    if (!listMode && key === "beams") {
      // move / rotate a beam, and quick width/depth steps. Always re-draw the
      // BEAM layout (switching to it if needed) so the change is visible.
      const btn = (label, title, fn) => {
        const b = document.createElement("button");
        b.className = "del"; b.textContent = label; b.title = title;
        b.onclick = e => {
          const d = e.shiftKey ? 0.25 : (e.ctrlKey ? 1 : 0.5);
          pushUndo(); fn(d, e); markDirty(); buildTable(key); regenBeam();
        };
        td.appendChild(b);
      };
      const mv = (dx, dy) => {
        row.x1 = r4(row.x1 + dx); row.x2 = r4(row.x2 + dx);
        row.y1 = r4(row.y1 + dy); row.y2 = r4(row.y2 + dy);
      };
      btn("←", "move left (Shift 3\", Ctrl 1')", d => mv(-d, 0));
      btn("→", "move right", d => mv(d, 0));
      btn("↓", "move down", d => mv(0, -d));
      btn("↑", "move up", d => mv(0, d));
      btn("⟲", "rotate about centre (Shift 15°, else 90°)", (_d, e) => {
        const cx = (row.x1 + row.x2) / 2, cy = (row.y1 + row.y2) / 2;
        const a = (e.shiftKey ? 15 : 90) * Math.PI / 180,
          c = Math.cos(a), s = Math.sin(a);
        const rp = (x, y) => [r4(cx + (x - cx) * c - (y - cy) * s),
                              r4(cy + (x - cx) * s + (y - cy) * c)];
        [row.x1, row.y1] = rp(row.x1, row.y1);
        [row.x2, row.y2] = rp(row.x2, row.y2);
      });
      btn("D+", "deepen 25 mm", () => row.depth_mm = (row.depth_mm || 300) + 25);
      btn("D−", "shallower 25 mm",
          () => row.depth_mm = Math.max(150, (row.depth_mm || 300) - 25));
      // flush ONE face of the beam to the wall — sides depend on the beam's run
      const vert = Math.abs(row.y2 - row.y1) >= Math.abs(row.x2 - row.x1);
      if (vert) {
        btn("⇤L", "flush the beam's LEFT face to the wall",
            () => flushBeam(row, "left"));
        btn("⇥R", "flush the beam's RIGHT face to the wall",
            () => flushBeam(row, "right"));
      } else {
        btn("⤒T", "flush the beam's TOP face to the wall",
            () => flushBeam(row, "top"));
        btn("⤓B", "flush the beam's BOTTOM face to the wall",
            () => flushBeam(row, "bottom"));
      }
    }
    if (!listMode && key === "walls") {
      // step is in feet; hold Shift for 3", Ctrl for 1'-0"
      const nudge = (label, title, fn) => {
        const b = document.createElement("button");
        b.className = "del"; b.textContent = label; b.title = title;
        b.onclick = e => {
          const d = e.shiftKey ? 0.25 : (e.ctrlKey ? 1 : 0.5);
          pushUndo(); fn(d); markDirty(); buildTable(key); redraw();
        };
        td.appendChild(b);
      };
      nudge("⇤", "extend the start end (Shift 3\", Ctrl 1')",
            d => extendWallEnd(row, "start", d));
      nudge("⇥", "extend the end end (Shift 3\", Ctrl 1')",
            d => extendWallEnd(row, "end", d));
      nudge("↔", "extend BOTH ends (Shift 3\", Ctrl 1')",
            d => setWallLength(row, wallLength(row) + 2 * d));
      nudge("→←", "trim both ends (Shift 3\", Ctrl 1')",
            d => setWallLength(row, wallLength(row) - 2 * d));
    }
    if (!listMode && key === "openings" && String(row.type || "").endsWith("door")) {
      const flip = document.createElement("button");
      flip.className = "del"; flip.textContent = "⇄";
      flip.title = "flip this door's swing";
      flip.onclick = () => {
        pushUndo();
        const s = row.swing || (row.swing = {});
        s.side = s.side === "right" ? "left" : "right";
        s.manual = true;
        markDirty(); buildTable(key); redraw();
      };
      td.appendChild(flip);
    }
    const b = document.createElement("button");
    b.className = "del"; b.textContent = "×"; b.title = "delete";
    b.onclick = () => {
      pushUndo(); rows.splice(ri, 1); markDirty(); buildTables(); redraw();
    };
    td.appendChild(b); tr.appendChild(td);
    tb.appendChild(tr);
  });

  tbl.appendChild(tb);
  host.appendChild(tbl);          // host was cleared before the filter bar

  const bar = document.createElement("div");
  bar.className = "row";
  if (key === "walls") {
    const num = document.createElement("button");
    num.className = "btn";
    num.textContent = "Number walls";
    num.title = "Split walls where rooms divide them, then number every wall "
      + "W1, W2 … — the numbers show on the drawing";
    num.onclick = async () => {
      pushUndo();
      const r = await api().number_walls(S.plan, true);
      if (!r.ok) return fail(r);
      S.plan = r.plan;
      markDirty(); buildTables(); redraw();
      status(r.notes.length ? r.notes[r.notes.length - 1] : "walls numbered");
    };
    bar.appendChild(num);
  }
  if (key === "openings") {
    const mk = (label, force, title) => {
      const b = document.createElement("button");
      b.className = "btn"; b.textContent = label; b.title = title;
      b.onclick = async () => {
        pushUndo();
        const r = await api().number_openings(S.plan, force);
        if (!r.ok) return fail(r);
        S.plan = r.plan;
        markDirty(); buildTables(); redraw();
        status(r.notes.length
          ? `${r.notes.length} mark(s) set — see Log`
          : "every opening already has a distinct mark");
      };
      bar.appendChild(b);
    };
    mk("Mark openings", false,
       "Number the openings that only carry a bare letter, and mark any "
       + "window serving a toilet or bath as a ventilator");
    mk("Renumber all", true,
       "Renumber every opening from 1, in reading order");
  }
  const add = document.createElement("button");
  add.className = "btn";
  add.textContent = key === "walls" ? "+ Add wall…"
    : (key === "furniture" ? "+ Add furniture…" : "+ Add");
  add.onclick = () => {
    if (key === "walls") return openWallDialog();   // placed, not dropped at 0,0
    if (key === "furniture") return openFurnDialog();
    if (key === "pipes") {                           // add a pipe run at plan centre
      pushUndo();
      const b = _planBounds(), cx = r4((b.x0 + b.x1) / 2), cy = r4((b.y0 + b.y1) / 2);
      const fresh = structuredClone(BLANK.pipes);
      fresh.pts = [[cx, cy], [r4(cx + 4), cy]];      // a short run to start; drag to route
      fresh.length_ft = 4;
      rows.push(fresh);
      markDirty(); buildTables(); redraw();
      selectItem("pipes", rows.length - 1);          // open it in the gizmo (set system/Ø)
      status("pipe added — set System & Ø mm in the gizmo, then drag its ends to route");
      return;
    }
    pushUndo();
    const fresh = structuredClone(BLANK[key]);
    rows.push(fresh);
    // a new point must be visible to be edited — show the category it lands in
    if (key === "elec") S.elecFilter = elecCatOf(fresh.code);
    markDirty(); buildTables(); redraw();
  };
  bar.appendChild(add);
  host.appendChild(bar);
}

const TITLE_FIELDS = [
  ["client", "Client"], ["project", "Project"], ["plan_name", "Plan name"],
  ["plot_size", "Plot size"], ["wall_note", "Wall note"],
  ["drawing_no", "Drawing no."], ["revision", "Revision"], ["date", "Date"],
  ["drawn_by", "Drawn by"],
];
function buildTitle() {
  const host = $("#p-title");
  const t = S.plan.title || (S.plan.title = {});
  const tbl = document.createElement("table");
  const tb = document.createElement("tbody");
  TITLE_FIELDS.forEach(([k, lbl]) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<th style="width:130px">${lbl}</th>`;
    const td = document.createElement("td");
    const inp = document.createElement("input");
    inp.value = t[k] ?? "";
    inp.onchange = () => { pushUndo(); t[k] = inp.value; markDirty(); redraw(); };
    td.appendChild(inp); tr.appendChild(td); tb.appendChild(tr);
  });
  const tr = document.createElement("tr");
  tr.innerHTML = `<th>North (deg)</th>`;
  const td = document.createElement("td");
  const inp = document.createElement("input");
  inp.type = "number"; inp.step = "any"; inp.value = S.plan.north_deg ?? 90;
  inp.onchange = () => {
    pushUndo(); S.plan.north_deg = parseFloat(inp.value) || 0;
    markDirty(); redraw();
  };
  td.appendChild(inp); tr.appendChild(td); tb.appendChild(tr);
  tbl.appendChild(tb);
  host.innerHTML = ""; host.appendChild(tbl);
}

let _autosaveT = null;
function markDirty() {
  S.dirty = true;
  showSaved();
  clearTimeout(_autosaveT);
  _autosaveT = setTimeout(autosaveProject, 1500);   // crash-safe, debounced
}

/* ── saving ──────────────────────────────────────────────────
   Ctrl+S writes the whole plan — walls, openings, stairs, furniture, the lot
   — back to one JSON file. The first save asks where; every save after that
   goes to the same place without asking, so working through the floor plan
   and then the furniture layout keeps building up one file.              */
function showSaved() {
  const el = $("#savedAs");
  if (!el) return;
  if (!S.savePath) { el.textContent = "not saved"; el.className = "sub dirty"; }
  else {
    el.textContent = (S.dirty ? "● " : "") + S.saveName;
    el.className = S.dirty ? "sub dirty" : "sub";
    el.title = S.savePath;
  }
}

async function savePlan(saveAs = false) {
  if (!S.plan) return status("nothing to save yet");
  // WEB: no native save dialog — download the plan as a .json the browser can
  // re-open later with Open Plan (a direct download from this click gesture).
  if (isWeb()) {
    let base = (S.saveName || "plan").replace(/\.[^.]+$/, "") || "plan";
    if (saveAs) {
      const nm = prompt("Save as — file name:", base);
      if (nm === null) return;                 // cancelled
      base = (nm.trim().replace(/\.[^.]+$/, "")) || base;
    }
    const name = base + ".json";
    // more than one floor => save the WHOLE project in this one file
    const multi = S.floors.filter(fl => fl.plan).length > 1;
    const blob = new Blob([JSON.stringify(multi ? projectFile() : S.plan, null, 2)],
                          { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    S.saveName = name; S.dirty = false; showSaved();
    status((multi ? "project (" + S.floors.filter(fl => fl.plan).length
        + " floors) downloaded — " : "plan downloaded — ")
      + name + " (re-open it with Open Plan)");
    return;
  }
  const multiD = S.floors.filter(fl => fl.plan).length > 1;
  const payload = multiD ? projectFile() : S.plan;
  const r = saveAs ? await api().save_as(payload)
                   : await api().save_plan_json(payload, S.savePath || "");
  if (!r.ok) return fail(r);
  if (r.cancelled) return;
  S.savePath = r.path;
  S.saveName = r.name;
  S.dirty = false;
  showSaved();
  status("saved to " + r.name);
}

addEventListener("keydown", e => {
  if (!(e.ctrlKey || e.metaKey)) return;
  if (e.key.toLowerCase() !== "s") return;
  e.preventDefault();
  savePlan(e.shiftKey);              // Ctrl+Shift+S = save as
});

/* ── add furniture ───────────────────────────────────────────
   A blank row is no use for furniture: a piece has a standard size, a symbol
   and a wall it belongs on. So the category is asked first, and the catalogue
   supplies the rest.                                                        */
const AF = { groups: null, cat: 0, kind: "", label: "" };

async function openFurnDialog() {
  if (!S.plan) return status("read or load a plan first");
  if (!AF.groups) {
    const r = await api().furniture_catalogue();
    if (!r.ok) return fail(r);
    AF.groups = r.groups;
  }
  const rooms = (S.plan.rooms || []).filter(r => !r.open_area && !r.void);
  $("#furnRoom").innerHTML =
    '<option value="">the largest room</option>'
    + rooms.map(r => `<option>${esc(r.name)}</option>`).join("");
  $("#furnCats").innerHTML = AF.groups.map((g, i) =>
    `<button class="${i === AF.cat ? "on" : ""}" data-cat="${i}">`
    + `${esc(g.category)}</button>`).join("");
  $$("#furnCats button").forEach(b => b.onclick = () => {
    AF.cat = +b.dataset.cat;
    $$("#furnCats button").forEach(x => x.classList.toggle("on", x === b));
    furnItems();
  });
  AF.kind = "";
  furnItems();
  $("#furnPick").textContent = "";
  $("#furnAdd").disabled = true;
  $("#furnWrap").classList.remove("hidden");
}

function furnItems() {
  const g = AF.groups[AF.cat];
  $("#furnItems").innerHTML = g.items.map(it =>
    `<button class="pick${it.kind === AF.kind ? " on" : ""}" `
    + `data-kind="${esc(it.kind)}"><b>${esc(it.label)}</b>`
    + `<span>${Math.round(it.length_mm)} × ${Math.round(it.depth_mm)}</span>`
    + `</button>`).join("");
  $$("#furnItems .pick").forEach(b => b.onclick = () => {
    AF.kind = b.dataset.kind;
    const it = g.items.find(x => x.kind === AF.kind);
    AF.label = it.label;
    $$("#furnItems .pick").forEach(x => x.classList.toggle("on", x === b));
    $("#furnPick").textContent = it.vaastu
      ? `${it.label} — ${it.vaastu}.`
      : `${it.label} — no Vaastu rule; it goes where it fits.`;
    $("#furnAdd").disabled = false;
  });
}

$("#furnCancel").onclick = () => $("#furnWrap").classList.add("hidden");
$("#furnAdd").onclick = async () => {
  if (!AF.kind) return;
  pushUndo();
  const r = await api().add_furniture(S.plan, AF.kind,
                                      $("#furnRoom").value,
                                      $("#furnWall").value);
  if (!r.ok) return fail(r);
  if (!r.placed) {
    $("#furnPick").innerHTML = `<span style="color:var(--err)">`
      + `${esc(r.message)}</span>`;
    return;
  }
  S.plan = r.plan;
  $("#furnWrap").classList.add("hidden");
  // show the category the new piece landed in, or it is filtered out of sight
  S.furnFilter = (FURN.map && FURN.map[AF.kind]) || "all";
  markDirty(); buildTables(); redraw();
  tab("furniture");
  status(r.message);
};

/* ── the code library ────────────────────────────────────────
   The books in NBC/ are ~290 MB — far too much to hand a model on every read.
   They are indexed once and then consulted: a question returns the handful of
   passages that bear on it, with book and page, so a rule can be checked
   against its source rather than recalled.                                  */
async function refSearch() {
  const q = $("#refQ").value.trim();
  if (!q) return;
  const out = $("#refOut");
  out.textContent = "searching…";
  const r = await api().library_search(q, 5);
  if (!r.ok) { out.innerHTML = `<div class="issue error"><span class="dot">`
    + `</span><div>${esc(r.error)}</div></div>`; return; }
  if (!r.hits.length) {
    out.textContent = `Nothing in the library matches “${q}”.`;
    return;
  }
  out.innerHTML = r.hits.map(h =>
    `<div class="ref"><b>${esc(h.book)}</b> <span class="sub">p.${h.page}</span>`
    + `<div>${esc(h.text)}</div></div>`).join("");
}
/* the Code library tab was removed; its handlers only bind if present */
if ($("#refGo")) {
  $("#refGo").onclick = refSearch;
  $("#refQ").onkeydown = e => { if (e.key === "Enter") refSearch(); };
  $("#refBuild").onclick = async () => {
    const r = await api().library_build();
    if (!r.ok) return fail(r);
    $("#refOut").textContent = r.already ? "Already indexing — watch the Log."
      : "Indexing the books. The Log reports when it is done.";
    tab("log");
  };
}

/* ── add a wall ──────────────────────────────────────────────
   A blank row at the origin is no use: a wall has to land where the plan needs
   it. The three modes cover how a draughtsman actually places one — by
   dimension, on the line two rooms share, or carrying on from an existing
   wall's end so the junction closes.                                        */
const AW = { mode: "dir", thk: 9, ext: true };

function openWallDialog() {
  if (!S.plan) return status("load or read a plan first");
  const rooms = (S.plan.rooms || []).map(r => esc(r.name));
  const walls = (S.plan.walls || []).map(w => esc(w.id));
  $("#wRoomA").innerHTML = rooms.map(n => `<option>${n}</option>`).join("");
  $("#wRoomB").innerHTML = rooms.map(n => `<option>${n}</option>`).join("");
  if (rooms.length > 1) $("#wRoomB").selectedIndex = 1;
  $("#wFromWall").innerHTML = walls.map(n => `<option>${n}</option>`).join("");
  $("#wallWrap").classList.remove("hidden");
  wallPreview();
}

$$("#wallMode button").forEach(b => b.onclick = () => {
  AW.mode = b.dataset.mode;
  $$("#wallMode button").forEach(x => x.classList.toggle("on", x === b));
  ["dir", "rooms", "cont"].forEach(m =>
    $("#wf-" + m).classList.toggle("hidden", m !== AW.mode));
  wallPreview();
});

$$("#wThk button").forEach(b => b.onclick = () => {
  $$("#wThk button").forEach(x => x.classList.toggle("on", x === b));
  const custom = b.dataset.thk === "";
  $("#wThkVal").classList.toggle("hidden", !custom);
  if (!custom) { AW.thk = +b.dataset.thk; AW.ext = b.dataset.ext === "1"; }
  else { AW.thk = +$("#wThkVal").value || 4.5; AW.ext = false; }
  wallPreview();
});
$("#wThkVal").oninput = () => { AW.thk = +$("#wThkVal").value || 4.5; wallPreview(); };

$("#wDir").onchange = () => {
  const h = $("#wDir").value === "h";
  $("#wLineLbl").firstChild.textContent = h ? "On line Y " : "On line X ";
  $("#wStartLbl").firstChild.textContent = h ? "Starting at X " : "Starting at Y ";
  wallPreview();
};
["wLine", "wStart", "wLen", "wLen2", "wRoomA", "wRoomB", "wFromWall",
 "wFromEnd", "wGo"].forEach(id => {
  const el = $("#" + id);
  el.oninput = wallPreview; el.onchange = wallPreview;
});

/** The wall the current settings describe, or {error} if they describe none. */
function proposedWall() {
  if (AW.mode === "dir") {
    const h = $("#wDir").value === "h";
    const line = +$("#wLine").value || 0;
    const from = +$("#wStart").value || 0;
    const L = +$("#wLen").value || 0;
    if (L <= 0) return { error: "Length must be more than zero." };
    return h ? { x1: from, y1: line, x2: from + L, y2: line }
             : { x1: line, y1: from, x2: line, y2: from + L };
  }

  if (AW.mode === "rooms") {
    const a = (S.plan.rooms || []).find(r => r.name === $("#wRoomA").value);
    const b = (S.plan.rooms || []).find(r => r.name === $("#wRoomB").value);
    if (!a || !b || a === b) return { error: "Pick two different rooms." };
    const T = 0.05;
    // a vertical line they share
    for (const [p, q] of [[a, b], [b, a]]) {
      if (Math.abs((p.x + p.w) - q.x) < T) {
        const lo = Math.max(p.y, q.y), hi = Math.min(p.y + p.h, q.y + q.h);
        if (hi - lo > T) return { x1: q.x, y1: lo, x2: q.x, y2: hi };
      }
    }
    // a horizontal line they share
    for (const [p, q] of [[a, b], [b, a]]) {
      if (Math.abs((p.y + p.h) - q.y) < T) {
        const lo = Math.max(p.x, q.x), hi = Math.min(p.x + p.w, q.x + q.w);
        if (hi - lo > T) return { x1: lo, y1: q.y, x2: hi, y2: q.y };
      }
    }
    return { error: `${a.name} and ${b.name} do not share an edge.` };
  }

  const w = (S.plan.walls || []).find(x => x.id === $("#wFromWall").value);
  if (!w) return { error: "Pick a wall to start from." };
  const at = $("#wFromEnd").value === "start"
    ? { x: w.x1, y: w.y1 } : { x: w.x2, y: w.y2 };
  const L = +$("#wLen2").value || 0;
  if (L <= 0) return { error: "Length must be more than zero." };
  const d = { e: [L, 0], w: [-L, 0], n: [0, L], s: [0, -L] }[$("#wGo").value];
  return { x1: at.x, y1: at.y, x2: at.x + d[0], y2: at.y + d[1] };
}

function wallPreview() {
  const p = $("#wPreview"), w = proposedWall();
  if (w.error) {
    p.className = "sub bad"; p.textContent = w.error;
    $("#wallAdd").disabled = true;
    return;
  }
  p.className = "sub";
  p.textContent = `(${r4(w.x1)}, ${r4(w.y1)}) → (${r4(w.x2)}, ${r4(w.y2)})  ·  `
    + `${wallLength(w)} ft  ·  ${AW.thk}" ${AW.ext ? "external" : "partition"}`;
  $("#wallAdd").disabled = false;
}

function nextWallId() {
  // continue the plan's OWN series: with P-1..P-10 on the drawing the next
  // wall is P-11, so its number is fresh and the tag on the drawing is unique
  const walls = S.plan.walls || [];
  const counts = {};
  let maxN = 0;
  for (const w of walls) {
    const m = String(w.id || "").match(/^(.*?)(\d+)$/);
    if (!m) continue;
    counts[m[1]] = (counts[m[1]] || 0) + 1;
    maxN = Math.max(maxN, +m[2]);
  }
  const prefix = Object.keys(counts)
    .sort((a, b) => counts[b] - counts[a])[0];
  if (prefix !== undefined) return prefix + (maxN + 1);
  const used = new Set(walls.map(w => w.id));
  for (let i = 1; i < 9999; i++) if (!used.has("W-" + i)) return "W-" + i;
  return "W-" + Date.now();
}

$("#wallCancel").onclick = () => $("#wallWrap").classList.add("hidden");
$("#wallAdd").onclick = () => {
  const w = proposedWall();
  if (w.error) return;
  pushUndo();
  (S.plan.walls || (S.plan.walls = [])).push({
    id: nextWallId(), x1: r4(w.x1), y1: r4(w.y1), x2: r4(w.x2), y2: r4(w.y2),
    thickness_in: AW.thk, exterior: AW.ext,
  });
  $("#wallWrap").classList.add("hidden");
  markDirty(); buildTables(); redraw();
  tab("walls");
  status("wall added — Ctrl+Z if it is not what you wanted");
};

/* ── undo / redo ─────────────────────────────────────────── */
const HISTORY = 80;

/** Call BEFORE changing the plan, so the state being replaced is the one kept. */
function pushUndo() {
  if (!S.plan) return;
  S.undo.push(JSON.stringify(S.plan));
  if (S.undo.length > HISTORY) S.undo.shift();
  S.redo.length = 0;                 // a new edit ends the redo branch
  refreshUndo();
}

function refreshUndo() {
  $("#btnUndo").disabled = !S.undo.length;
  $("#btnRedo").disabled = !S.redo.length;
  $("#btnUndo").title = S.undo.length ? `Undo (${S.undo.length})` : "Nothing to undo";
  $("#btnRedo").title = S.redo.length ? `Redo (${S.redo.length})` : "Nothing to redo";
}

function undo() {
  if (!S.undo.length) return status("nothing to undo");
  S.redo.push(JSON.stringify(S.plan));
  S.plan = JSON.parse(S.undo.pop());
  refreshUndo(); buildTables(); redraw();
  if (typeof rebuild3D === "function") rebuild3D();   // the 3D view follows too
  status(`undone — ${S.undo.length} step(s) left`);
}

function redo() {
  if (!S.redo.length) return status("nothing to redo");
  S.undo.push(JSON.stringify(S.plan));
  S.plan = JSON.parse(S.redo.pop());
  refreshUndo(); buildTables(); redraw();
  if (typeof rebuild3D === "function") rebuild3D();
  status("redone");
}

$("#btnUndo").onclick = undo;
$("#btnRedo").onclick = redo;

addEventListener("keydown", e => {
  if (!(e.ctrlKey || e.metaKey)) return;
  // inside the JSON box, leave Ctrl+Z to the browser's own text undo
  if (e.target && e.target.id === "jsonBox") return;
  const k = e.key.toLowerCase();
  if (k === "z" && !e.shiftKey) { e.preventDefault(); undo(); }
  else if (k === "y" || (k === "z" && e.shiftKey)) { e.preventDefault(); redo(); }
});

/* ── actions ─────────────────────────────────────────────── */
let redrawTimer = null;
function redraw() {
  clearTimeout(redrawTimer);
  redrawTimer = setTimeout(() => {
    // re-render whatever view is on screen, so editing beams updates the beam
    // layout (not the plan) and keeps the current zoom / pan
    if (S.beamView) regenBeam();
    else if (S.sectionView) regenSection();
    else doRenderFast();               // live edits: draw-only (~2 ms), no checks
  }, 0);   // ~immediate — the render-coalescing guard prevents any flooding
}

// LIVE draw for interactive edits — uses render_fast (no validation, ~2 ms) so
// dragging a door / nudging furniture is smooth; the checks panel is refreshed a
// beat after the user stops (scheduleCheck). The FULL doRender (with validation)
// is kept for the initial load and the Re-draw button.
let _fastBusy = false, _fastPending = false, _checkTimer = null;
async function doRenderFast() {
  if (!S.plan) return;
  if (allFloorsView()) return doRender();      // the composite needs the full path
  if (_fastBusy) { _fastPending = true; return; }
  _fastBusy = true;
  try {
    do {
      _fastPending = false;
      const r = await api().render_fast(S.plan, $("#selSheet").value,
        $("#selOrient").value, $("#chkTags").checked, S.layerState || null,
        editingSections(), DUNIT);
      if (!r.ok) { fail(r); break; }
      S.sectionView = false; S.beamView = false;
      updateSecToggle();
      showSvg(r.svg, r.info);
    } while (_fastPending);
  } finally { _fastBusy = false; }
  scheduleCheck();
}

function scheduleCheck() {
  clearTimeout(_checkTimer);
  _checkTimer = setTimeout(async () => {
    if (!S.plan || S.beamView || S.sectionView || allFloorsView()) return;
    const c = await api().check_plan(S.plan);
    if (c && c.ok) {
      showIssues(c.issues, c.summary);
      showFixes(c.fixes);
      status(c.summary.clean ? "drawing is clean"
        : c.summary.errors + " issue(s) to fix");
    }
  }, 450);
}

let _renderBusy = false, _renderPending = false;
async function doRender() {
  if (!S.plan) return;
  // COALESCE — while one render is in flight, a new edit just flags 'pending'
  // and we redraw ONCE more when it lands, instead of stacking many round-trips
  // (over the tunnel that stacking is what makes fast door nudges feel laggy).
  if (_renderBusy) { _renderPending = true; return; }
  _renderBusy = true;
  try {
    do {
      _renderPending = false;
      const multi = allFloorsView();
      const r = multi
        ? await api().render_project(S.floors, $("#selSheet").value,
            $("#selOrient").value, $("#chkTags").checked, S.layerState || null)
        : await api().render(S.plan, $("#selSheet").value,
            $("#selOrient").value, $("#chkTags").checked, S.layerState || null,
            editingSections(), DUNIT);
      if (!r.ok) { fail(r); break; }
      S.sectionView = false;
      S.beamView = false;
      updateSecToggle();
      showSvg(r.svg, r.info);
      if (multi) {
        status(`${r.floors} floors shown together — click a stage to apply it to `
          + `every floor; pick a floor in “Editing” to edit its tables`);
      } else {
        showIssues(r.issues, r.summary);
        showFixes(r.fixes);
        status(r.summary.clean ? "drawing is clean"
          : r.summary.errors + " issue(s) to fix");
      }
    } while (_renderPending);           // a newer edit arrived mid-render → redo
  } finally {
    _renderBusy = false;
  }
}

/* Give a fresh plan four default section lines — two vertical, two horizontal —
   spread across the building at the 1/3 and 2/3 lines. The user can move / add /
   delete them like anything else. A plan that already has section lines is left
   as-is (their own choices win). */
function ensureDefaultSections(plan) {
  if (!plan || (plan.sections && plan.sections.length)) return;
  const xs = [], ys = [];
  (plan.rooms || []).forEach(r => { xs.push(r.x, r.x + (+r.w || 0)); ys.push(r.y, r.y + (+r.h || 0)); });
  (plan.walls || []).forEach(w => { xs.push(w.x1, w.x2); ys.push(w.y1, w.y2); });
  if (!xs.length) return;
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  const y0 = Math.min(...ys), y1 = Math.max(...ys);
  const W = x1 - x0, H = y1 - y0, m = Math.max(2, Math.min(W, H) * 0.15);
  const vx1 = r4(x0 + W / 3), vx2 = r4(x0 + 2 * W / 3);
  const hy1 = r4(y0 + H / 3), hy2 = r4(y0 + 2 * H / 3);
  plan.sections = [
    { tag: "A", x1: vx1, y1: r4(y0 - m), x2: vx1, y2: r4(y1 + m) },  // vertical
    { tag: "B", x1: vx2, y1: r4(y0 - m), x2: vx2, y2: r4(y1 + m) },  // vertical
    { tag: "C", x1: r4(x0 - m), y1: hy1, x2: r4(x1 + m), y2: hy1 },  // horizontal
    { tag: "D", x1: r4(x0 - m), y1: hy2, x2: r4(x1 + m), y2: hy2 },  // horizontal
  ];
}

/* A PROJECT FILE holds every floor in one .json:
     { "archbrain_project": 1, "floors": [ {name, plan}, ... ], "active": 0 }
   Saving a multi-floor project writes this; a single floor still writes the
   plain plan, and both open through loadAnyJson(). */
function isProjectFile(j) {
  return !!(j && Array.isArray(j.floors) && j.floors.length
            && j.floors.some(f => f && f.plan));
}
function projectFile() {
  return {
    archbrain_project: 1,
    saved: new Date().toISOString(),
    active: S.active || 0,
    floors: S.floors.map(f => ({ name: f.name, plan: f.plan })),
  };
}
const AUTOSAVE_KEY = "abs_autosave_project";
function autosaveProject() {
  try {
    localStorage.setItem(AUTOSAVE_KEY, JSON.stringify(projectFile()));
  } catch (e) { /* storage full — the session copy still stands */ }
}
function takeAutosave() {
  try {
    const t = localStorage.getItem(AUTOSAVE_KEY);
    return t ? JSON.parse(t) : null;
  } catch (e) { return null; }
}
/* THE ROOM LABEL IS THE DIMENSION (user rule): where the read walls give a
   room a different clear size than its own printed label, the room is
   snapped to the label — and the bounding wall moves with it when that wall
   belongs to this room alone (a shared wall stays, so the neighbour's own
   label is not broken). Runs once at load, in the client's data. */
function _lblFtV(s) {
  if (!s) return null; s = String(s).trim();
  let m = s.match(/^(\d+)\s*'\s*-?\s*(\d+(?:\.\d+)?)?/);
  if (m) return (+m[1]) + ((+m[2] || 0) / 12);
  m = s.match(/^(\d+(?:\.\d+)?)/);
  if (m) { const v = +m[1]; return v > 50 ? v / 304.8 : v; }
  return null;
}
/* Room GEOMETRY is never auto-edited to match the size label: the read
   sketch is a single glued network (walls + rects + doors + columns), and
   moving any of it programmatically detached fills from walls and left the
   plan visibly corrupted. The label stays the TRUTH for every NUMBER —
   the printed size, the furniture clamp below, unit conversions — while a
   genuinely misread wall is fixed by hand or by re-reading the sheet. */

/* room-local drawn/label scale for a piece, per STORED axis — the sketch
   reads a room a touch bigger than its printed label, so everything drawn
   inside carries the same stretch. drawn ÷ this = the PRINTED size; a typed
   size × this = the drawn box. Mirrors core/furniture.room_scale(). */
function furnScale(plan, f) {
  const w = +f.w || 0, h = +f.h || 0;
  const rot = Math.abs(((+f.angle || 0) % 180 + 180) % 180 - 90) < 45;
  const dw = rot ? h : w, dh = rot ? w : h;
  const cx = (+f.x || 0) + w / 2, cy = (+f.y || 0) + h / 2;
  const rm = ((plan && plan.rooms) || []).find(r => !r.void &&
    cx - dw / 2 >= r.x - 0.6 && cx + dw / 2 <= r.x + r.w + 0.6 &&
    cy - dh / 2 >= r.y - 0.6 && cy + dh / 2 <= r.y + r.h + 0.6);
  if (!rm) return { kw: 1, kh: 1 };
  const parts = String(rm.size_label || "").split(/[xX×]/);
  const lw = _lblFtV(parts[0]), lh = _lblFtV(parts[1]);
  let sx = (lw && lw < rm.w) ? rm.w / lw : 1;
  let sy = (lh && lh < rm.h) ? rm.h / lh : 1;
  if (!(sx >= 1 && sx <= 1.6)) sx = 1;   // a misparsed label must not warp
  if (!(sy >= 1 && sy <= 1.6)) sy = 1;
  return rot ? { kw: sy, kh: sx } : { kw: sx, kh: sy };
}

/* a piece can never be bigger than its room or hang outside it — clamp in
   the CLIENT's own data (once, at load / after the furniture stage), so the
   drawn sheet, the size labels and the gizmo all read the same numbers */
function clampFurniture(plan) {
  if (!plan) return;
  for (const f of (plan.furniture || [])) {
    const w = +f.w || 1, h = +f.h || 1;
    const cx = (+f.x || 0) + w / 2, cy = (+f.y || 0) + h / 2;
    let rm = (plan.rooms || []).find(r =>
      cx >= r.x - 0.6 && cx <= r.x + r.w + 0.6 &&
      cy >= r.y - 0.6 && cy <= r.y + r.h + 0.6);
    if (!rm) rm = (plan.rooms || []).find(r =>
      (f.room || "").trim().toLowerCase() ===
      (r.name || "").trim().toLowerCase());
    if (!rm || rm.void) continue;
    // the room's SIZE LABEL is the sheet's own truth — when the read walls
    // sit wider than the label says, a piece still respects the label, so
    // a 4'-6" deep dress never grows a 5'-2" wardrobe
    const lblFt = s => {
      if (!s) return null; s = String(s).trim();
      let m = s.match(/^(\d+)\s*'\s*-?\s*(\d+(?:\.\d+)?)?/);
      if (m) return (+m[1]) + ((+m[2] || 0) / 12);
      m = s.match(/^(\d+(?:\.\d+)?)/);
      if (m) { const v = +m[1]; return v > 50 ? v / 304.8 : v; }
      return null;
    };
    const parts = String(rm.size_label || "").split(/[xX×]/);
    const lw = lblFt(parts[0]), lh = lblFt(parts[1]);
    const effW = (lw && lw < rm.w) ? lw : rm.w;
    const effH = (lh && lh < rm.h) ? lh : rm.h;
    // a 90/270 piece is DRAWN rotated about its centre — its footprint is
    // h wide and w TALL, so work in DRAWN extents, not the stored fields
    const rot = Math.abs(((+f.angle || 0) % 180 + 180) % 180 - 90) < 45;
    let dw = rot ? (+f.h || 1) : (+f.w || 1);   // drawn x-extent
    let dh = rot ? (+f.w || 1) : (+f.h || 1);   // drawn y-extent
    // the DRAWN box works like the room itself: the sketch geometry is
    // proportional, so a piece meant to span the room spans the DRAWN room
    // flush to its walls — no dead gap where the sketch reads a little big
    if (dw >= effW - 0.3) dw = rm.w;
    if (dh >= effH - 0.3) dh = rm.h;
    if (rot) { f.h = dw; f.w = dh; } else { f.w = dw; f.h = dh; }
    // printed size is DERIVED live (drawn ÷ room scale) — drop stale caches
    delete f.size_w; delete f.size_h;
    // keep the DRAWN box inside the room (rotation is about the centre);
    // a full-span axis sits flush, a loose one keeps a small clearance
    const padX = dw >= rm.w - 0.01 ? 0 : 0.08;
    const padY = dh >= rm.h - 0.01 ? 0 : 0.08;
    let ccx = (+f.x || 0) + (+f.w || 1) / 2;
    let ccy = (+f.y || 0) + (+f.h || 1) / 2;
    ccx = Math.min(Math.max(ccx, rm.x + padX + dw / 2),
                   rm.x + rm.w - padX - dw / 2);
    ccy = Math.min(Math.max(ccy, rm.y + padY + dh / 2),
                   rm.y + rm.h - padY - dh / 2);
    f.x = ccx - (+f.w || 1) / 2;
    f.y = ccy - (+f.h || 1) / 2;
  }
}

function loadAnyJson(j, name) {
  if (!isProjectFile(j)) { setPlan(j); return 1; }
  S.floors = j.floors.map((f, i) => ({
    name: (f && f.name) || _nextFloorNameAt(i),
    plan: (f && f.plan) || null,
  }));
  S.floors.forEach(f => clampFurniture(f.plan));
  S.active = Math.min(Math.max(0, +j.active || 0), S.floors.length - 1);
  if (!S.floors[S.active].plan)                 // land on a floor that has one
    S.active = Math.max(0, S.floors.findIndex(f => f.plan));
  S.undo = []; S.redo = [];
  S.forceFit = true;
  ["btnRender", "btnExport"].forEach(i => $("#" + i).disabled = false);
  refreshStageButtons();
  buildTables();
  if (S.plan) doRender(); else clearPlanView();
  renderFloorBar();
  return S.floors.filter(f => f.plan).length;
}

function setPlan(plan) {
  pushUndo();               // no-op on the first plan; makes a reload undoable
  _sel = null;              // drop any gizmo selection from the old plan
  if ($("#gizmo")) $("#gizmo").classList.add("hidden");
  S.forceFit = true;        // a fresh plan starts fitted to the pane
  ensureDefaultSections(plan);   // 2 vertical + 2 horizontal cut lines by default
  clampFurniture(plan);          // pieces respect the room LABEL, data-level
  if (!Array.isArray(plan.refs)) plan.refs = [];   // user-placed reference guides
  S.refSel = null;
  S.plan = plan;
  ["btnRender", "btnExport"].forEach(i => $("#" + i).disabled = false);
  refreshStageButtons();
  buildTables();
  doRender();
  renderFloorBar();
}

/* ── multi-floor: a project = list of floors, each a full plan ───────── */
function renderFloorBar() {
  renderEditFloor();
  // the composite view is only offered when there IS more than one floor
  const afw = $("#allFloorsWrap");
  if (afw) afw.style.display = floorsWithPlans() >= 2 ? "" : "none";
  const bar = $("#floorBar");
  if (!bar) return;
  // only show the bar once there is more than one floor (or a plan exists)
  const multi = S.floors.length > 1;
  if (!S.plan && !multi) { bar.innerHTML = ""; return; }
  bar.innerHTML = "";
  S.floors.forEach((f, i) => {
    const t = document.createElement("div");
    t.className = "ftab" + (i === S.active ? " on" : "");
    t.textContent = f.name || `Floor ${i + 1}`;
    t.title = "Click to edit this floor · double-click to rename";
    t.onclick = () => switchFloor(i);
    t.ondblclick = () => renameFloor(i);
    if (S.floors.length > 1) {
      const x = document.createElement("span");
      x.className = "x"; x.textContent = "✕";
      x.title = "Remove this floor";
      x.onclick = ev => { ev.stopPropagation(); deleteFloor(i); };
      t.appendChild(x);
    }
    bar.appendChild(t);
  });
  const add = document.createElement("button");
  add.className = "fadd"; add.textContent = "+ Add floor";
  add.title = "Add another floor (First / Second …) — edit each separately, "
    + "export gives every floor its own sheets";
  add.onclick = addFloor;
  bar.appendChild(add);
}

function switchFloor(i) {
  if (i < 0 || i >= S.floors.length || i === S.active) return;
  S.active = i;
  S.undo = []; S.redo = [];            // undo history is per-floor
  S.sectionView = S.beamView = S.structView = S.elevView = false;
  S.forceFit = true;
  refreshStageButtons();
  buildTables();
  if (S.plan) doRender(); else clearPlanView();
  renderFloorBar();
  status(`editing ${S.floors[S.active].name}`);
}

function _nextFloorName() {
  const ord = ["Ground Floor", "First Floor", "Second Floor", "Third Floor",
               "Fourth Floor", "Fifth Floor"];
  return ord[S.floors.length] || `Floor ${S.floors.length + 1}`;
}

function addFloor() {
  S.floors.push({ name: _nextFloorName(), plan: null });
  S.active = S.floors.length - 1;
  S.undo = []; S.redo = [];
  buildTables();
  clearPlanView();
  renderFloorBar();
  status(`added ${S.floors[S.active].name} — read a sketch, run the `
    + `Questionnaire, or Open Plan to fill it`);
}

function renameFloor(i) {
  const nm = prompt("Floor name:", S.floors[i].name);
  if (nm === null) return;
  S.floors[i].name = nm.trim() || S.floors[i].name;
  renderFloorBar();
}

function deleteFloor(i) {
  if (S.floors.length <= 1) return;
  if (!confirm(`Remove “${S.floors[i].name}” and its plan?`)) return;
  S.floors.splice(i, 1);
  if (S.active >= S.floors.length) S.active = S.floors.length - 1;
  S.undo = []; S.redo = [];
  buildTables();
  if (S.plan) doRender(); else clearPlanView();
  renderFloorBar();
}

$("#btnOpen").onclick = async () => {
  // WEB build: use the browser's file picker. A JSON plan loads instantly; a
  // DXF is uploaded and imported from its layers. (Photos/PDF need the AI read,
  // which the free web build does not have.)
  if (isWeb()) {
    // when the server has the Claude CLI (your own PC), also allow photos / PDF
    // sketches — they are read by the AI into an editable plan, just like desktop
    const accept = window.WEB_AI ? ".json,.dxf,.png,.jpg,.jpeg,.pdf" : ".json,.dxf";
    const f = await webPickFile(accept);
    if (!f) return;
    if (f.error) return fail({ error: f.error });
    if (f.json) {
      const n = loadAnyJson(f.json, f.name);
      status(n > 1 ? `project loaded — ${n} floors (switch them on the floor bar)`
                   : "plan loaded from JSON — edit any row and it redraws");
      return;
    }
    const isImg = /\.(png|jpe?g|pdf)$/i.test(f.name || "");
    let rr;
    if (isImg) {
      // AI read takes ~1-2 min — run it as a background JOB and poll, so the
      // Cloudflare tunnel never times the single request out (502).
      busy(true, "Reading the drawing with AI — this can take 1-3 minutes…", true);
      const st = await api().read_async_start(f.path, "", false);
      if (!st.ok) { busy(false); return fail(st); }
      rr = { ok: false, error: "The AI read is taking unusually long — it may "
        + "still finish in the background. Try Open Drawing again in a moment." };
      const t0 = Date.now();
      let miss = 0;
      for (let i = 0; i < 400; i++) {          // poll for up to ~20 min
        await _sleep(3000);
        const s = await api().read_async_status(st.job);
        if (s && s.ok && s.done) { rr = s.result; break; }
        if (s && !s.ok) {                       // e.g. transient 'unknown job'
          if (++miss > 5) { rr = s; break; }
          continue;
        }
        miss = 0;
        const secs = Math.round((Date.now() - t0) / 1000);
        busy(true, `Reading the drawing with AI…  (${Math.floor(secs / 60)}m `
          + `${String(secs % 60).padStart(2, "0")}s)`, true);
      }
      busy(false);
    } else {
      busy(true, "Importing the DXF…");
      rr = await api().read_path(f.path, "", false);
      busy(false);
    }
    if (!rr.ok) return fail(rr);
    if (rr.plan) {
      setPlan(rr.plan);
      status(isImg
        ? "AI read the drawing into an editable plan — edit any row, it redraws"
        : "DXF imported from its layers — walls, doors, windows & rooms");
    } else {
      banner("This is an image/PDF and the AI read is not available on this "
        + "server (no Claude CLI). Run the app on your PC (START-ONLINE) for AI "
        + "read, or open a DXF / saved JSON plan.");
    }
    return;
  }
  busy(true, "Opening the drawing…");
  const r = await api().pick_sketch();
  busy(false);
  if (!r.ok) return fail(r);
  if (r.cancelled) return;
  // a DXF with proper CAD layers is converted straight to an editable plan
  if (r.dxf && r.plan) {
    setPlan(r.plan);
    $("#btnRead").disabled = true;
    status("DXF imported from its layers — walls, doors, windows & rooms; "
           + "edit any row and it redraws");
    return;
  }
  // photos, PDFs (and layer-less DXFs) open as a page image that the AI reader
  // turns into an editable plan when you press Read Drawing
  showPages(r.pages, r.name);
  $("#btnRead").disabled = false;
  status("drawing opened — press Read Drawing");
};

// Open several drawings at once — one per floor — and read each into its floor
if ($("#btnOpenFloors")) $("#btnOpenFloors").onclick = async () => {
  // the WEB build has no desktop file dialog — use the browser's multi-picker
  let r;
  if (isWeb()) {
    const acc = window.WEB_AI ? ".dxf,.png,.jpg,.jpeg,.pdf" : ".dxf";
    const w = await webPickFiles(acc);
    if (!w) return;
    if (w.error) return fail({ error: w.error });
    r = { ok: true, paths: w.paths, names: w.names };
  } else r = await api().pick_sketches();
  if (!r.ok) return fail(r);
  if (r.cancelled) return;
  const paths = r.paths || [], names = r.names || [];
  if (!paths.length) return;
  if (paths.length === 1) { status("only one file picked — use Open Drawing"); }
  // one floor per file
  S.floors = paths.map((p, i) => ({ name: _nextFloorNameAt(i), plan: null }));
  S.active = 0; S.undo = []; S.redo = [];
  let okCount = 0;
  for (let i = 0; i < paths.length; i++) {
    const lbl = `${names[i]} — floor ${i + 1} of ${paths.length}`;
    busy(true, `Reading ${lbl}…`, true);
    // An AI read can run for minutes. A single sync request dies on the
    // Cloudflare tunnel (502) even though the server finished and cached the
    // read — that is why floors used to "read" but never load. Images / PDFs
    // therefore go through the same background JOB + poll the single Open
    // Drawing uses; a DXF is instant so it stays a direct call.
    const isImg = /[.](png|jpe?g|pdf)$/i.test(names[i] || paths[i] || "");
    let rr = null;
    // one RESTART if the job/polling dies: the server caches a finished read,
    // so a restarted job answers instantly instead of reading again
    for (let attempt = 0; attempt < 2 && !(rr && rr.ok); attempt++) {
      if (attempt) pushLog(`Retrying ${names[i]} (the finished read is cached — this is quick)…`);
      if (isImg) {
        let st = null;
        try { st = await api().read_async_start(paths[i], "", false); } catch (e) { st = { ok: false, error: String(e) }; }
        if (!st || !st.ok) { rr = st || { ok: false, error: "could not start" }; continue; }
        rr = { ok: false, error: "read timed out" };
        const t0 = Date.now();
        let miss = 0;
        for (let k = 0; k < 400; k++) {            // up to ~20 min per floor
          await _sleep(3000);
          let sres = null;
          try { sres = await api().read_async_status(st.job); } catch (e) { sres = null; }
          if (sres && sres.ok && sres.done) { rr = sres.result; break; }
          if (!sres || !sres.ok) { if (++miss > 5) { rr = sres || rr; break; } continue; }
          miss = 0;
          const secs = Math.round((Date.now() - t0) / 1000);
          busy(true, `Reading ${lbl}…  (${Math.floor(secs / 60)}m `
            + `${String(secs % 60).padStart(2, "0")}s)`, true);
        }
      } else {
        try { rr = await api().read_path(paths[i], "", false); } catch (e) { rr = { ok: false, error: String(e) }; }
      }
    }
    if (rr && rr.ok && rr.plan) {
      S.floors[i].plan = rr.plan; okCount++;
      // LOAD AS YOU GO: this floor is usable right now, and the whole
      // project is autosaved so nothing finished can be lost any more
      S.active = i;
      ["btnRender", "btnExport"].forEach(x => $("#" + x).disabled = false);
      refreshStageButtons();
      buildTables(); renderFloorBar();
      if (S.plan) doRender();
      autosaveProject();
      status(`${names[i]} loaded (${okCount} of ${paths.length}) — baaki padh raha hoon…`);
    }
    else { pushLog(`Could not read ${names[i]}: ${(rr && rr.error) || "no plan"}`); }
  }
  S.active = 0;
  autosaveProject();
  busy(false);
  S.active = 0;
  ["btnRender", "btnExport"].forEach(i => $("#" + i).disabled = false);
  refreshStageButtons();
  S.forceFit = true;
  buildTables();
  if (S.plan) doRender(); else clearPlanView();
  renderFloorBar();
  status(`read ${okCount} of ${paths.length} floors — switch floors on the `
    + `floor bar; Export gives each its own sheets (continuous wall numbers)`);
};
function _nextFloorNameAt(i) {
  const ord = ["Ground Floor", "First Floor", "Second Floor", "Third Floor",
               "Fourth Floor", "Fifth Floor"];
  return ord[i] || `Floor ${i + 1}`;
}

$("#btnRead").onclick = () => $("#notesWrap").classList.remove("hidden");

// ── Questionnaire → offline plan ──────────────────────────────
function fillQuizFloors() {
  const sel = $("#qFloor");
  if (!sel) return;
  const cur = S.active;
  sel.innerHTML = "";
  S.floors.forEach((f, i) => {
    const o = document.createElement("option");
    o.value = String(i);
    o.textContent = f.name + (f.plan ? " (has a plan — will replace)" : "");
    sel.appendChild(o);
  });
  const on = document.createElement("option");
  on.value = "new"; on.textContent = "➕ New floor…";
  sel.appendChild(on);
  sel.value = String(cur);
}
$("#btnQuiz").onclick = () => {
  if (!S.plan && S.floors.length === 1) S.floors[0].plan = S.floors[0].plan;
  fillQuizFloors();
  $("#quizWrap").classList.remove("hidden");
};
if ($("#quizCancel")) $("#quizCancel").onclick = () =>
  $("#quizWrap").classList.add("hidden");
if ($("#quizGo")) $("#quizGo").onclick = async () => {
  const val = id => $("#" + id) ? $("#" + id).value : "";
  const num = id => parseFloat(val(id)) || 0;
  const ck  = id => $("#" + id) && $("#" + id).checked;
  const answers = {
    project: val("qProject"),
    plot_w: num("qPlotW"), plot_d: num("qPlotD"),
    setback_front: num("qSbF"), setback_rear: num("qSbR"),
    setback_left: num("qSbL"), setback_right: num("qSbRt"),
    floors: Math.max(1, parseInt(val("qFloors")) || 1),
    entry: val("qEntry"),
    bedrooms: Math.max(0, parseInt(val("qBeds")) || 0),
    attached: val("qAttach"),
    master: ck("qMaster"),
    living_dining_combined: ck("qLDcombine"),
    dining: ck("qDining"), powder: ck("qPowder"),
    common_bath: ck("qCommonBath"), pooja: ck("qPooja"),
    store: ck("qStore"), utility: ck("qUtility"), staircase: ck("qStair"),
  };
  if (!(answers.plot_w > 3 && answers.plot_d > 3))
    return status("enter a valid plot size");
  // which floor does this design go into?
  const fv = val("qFloor");
  let target = fv === "new" ? -1 : (parseInt(fv) || 0);
  if (target >= 0 && S.floors[target] && S.floors[target].plan &&
      !confirm(`Replace the existing plan on ${S.floors[target].name}?`)) return;
  const which = target === "new" || target < 0 ? "a new floor"
    : S.floors[target].name;
  busy(true, `Claude is designing ${which} from the brief — this can take a `
           + `minute…`);
  const r = await api().questionnaire(answers);
  busy(false);
  if (!r.ok) return fail(r);
  $("#quizWrap").classList.add("hidden");
  if (target < 0) {                       // create a new floor and design into it
    S.floors.push({ name: _nextFloorNameAt(S.floors.length), plan: null });
    target = S.floors.length - 1;
  }
  S.active = target;
  S.undo = []; S.redo = [];
  setPlan(r.plan);
  status(`AI designed ${S.floors[target].name} — ${(r.plan.rooms || []).length} `
    + `rooms. Add another floor & run again for the next floor; Export gives `
    + `each floor its own sheets`);
};

// Save the current plan into the template library
$("#btnElec").onclick = async () => {
  if (!S.plan) return status("read or load a plan first");
  if (!(S.plan.furniture || []).length && !confirm(
      "The electrical layout follows the furniture — fans centre on the bed "
      + "or the seating, the TV board sits behind the TV, the AC never blows "
      + "on the pillow.\n\nThere is no furniture yet. Carry on anyway?"))
    return;
  const had = (S.plan.elec || []).length;
  if (had && !confirm(
      `This plan already has an electrical layout — ${had} point(s), `
      + `${(S.plan.circuits || []).length} circuit(s).\n\nLaying it out again `
      + `replaces all of it, losing anything you moved or switched off.\n\n`
      + `Ctrl+Z undoes it. Lay out again?`)) return;
  pushUndo();
  const multi = allFloorsView();
  busy(true, multi
    ? "Laying out electrical on EVERY floor — fans, boards, circuits, load…"
    : "Laying out the electrical — lux targets, fans, boards, circuits and load…");
  const res = await forEachFloorPlan(p => api().electrify(p));
  busy(false);
  const bad = stageFailed(res); if (bad) return fail(bad);
  await loadLayers();
  const want = new Set(LAYERS.views.electrical || []);
  LAYERS.groups.forEach(g => S.layerState[g.key] = want.has(g.key));
  markDirty(); buildTables(); redraw();
  tab("elec");
  const total = stageTotal(res, "count"), circ = stageTotal(res, "circuits");
  status((multi ? `across ${res.length} floors — ` : "")
    + `${total} point(s), ${circ} circuit(s) · furniture hidden — `
    + `turn it back on in the Layers tab`);
};

$("#btnFloor").onclick = async () => {
  if (!S.plan) return status("read or load a plan first");
  const had = (S.plan.flooring || []).length;
  if (had && !confirm(
      `This plan already has flooring set for ${had} room(s).\n\nSetting it `
      + `again resets every room to defaults.\n\nCtrl+Z undoes it. Reset?`))
    return;
  pushUndo();
  const multi = allFloorsView();
  busy(true, multi
    ? "Setting flooring on EVERY floor — tile grid, spacers, start, skirting…"
    : "Setting the flooring — tile grid, spacers, start points, skirting and levels…");
  const res = await forEachFloorPlan(p => api().floor(p));
  busy(false);
  const bad = stageFailed(res); if (bad) return fail(bad);
  await loadLayers();
  const want = new Set(LAYERS.views.flooring || []);
  LAYERS.groups.forEach(g => S.layerState[g.key] = want.has(g.key));
  markDirty(); buildTables(); redraw();
  tab("flooring");
  const total = stageTotal(res, "count");
  status((multi ? `across ${res.length} floors — ` : "")
    + `${total} room(s) floored · edit material, size, spacer, start, skirting `
    + `and drop per room — furniture, plumbing and electrical hidden`);
};

/* show / hide + highlight the Plan | Section | Beam toggles in the plan pane */
function updateSecToggle() {
  const onView = S.sectionView || S.beamView;
  const hasS = !!(S.plan && (S.plan.sections || []).length);
  const hasB = !!(S.plan && (S.plan.beams || []).length);
  const bp = $("#btnBackPlan"), bs = $("#btnShowSection"), bb = $("#btnShowBeam");
  const bx = $("#btnShowStruct");
  if (bp) { bp.classList.toggle("hidden", !(hasS || hasB)); bp.classList.toggle("on", !onView); }
  if (bs) { bs.classList.toggle("hidden", !hasS); bs.classList.toggle("on", !!S.sectionView); }
  if (bb) { bb.classList.toggle("hidden", !hasB); bb.classList.toggle("on", !!S.beamView && !S.structView); }
  if (bx) { bx.classList.toggle("hidden", !hasB); bx.classList.toggle("on", !!S.structView); }
}

// show ALL structural sheets on one canvas (beam · plinth · roof · section)
let _structBusy = false;
async function showStructSheets(fit) {
  if (!S.plan || !(S.plan.beams || []).length)
    return status("no beams yet — press Beam Layout first");
  if (_structBusy) return;
  _structBusy = true;
  busy(true, "Composing all structural sheets…");
  try {
    const r = await api().struct_sheets(S.plan);
    if (!r.ok) return fail(r);
    if (fit) S.forceFit = true;
    S.beamView = true; S.sectionView = false; S.structView = true;
    showSvg(r.svg, r.info);
    updateSecToggle();
    status("all structural sheets — beam · plinth framing · roof framing · typical section");
  } finally { busy(false); _structBusy = false; }
}
if ($("#btnShowStruct")) $("#btnShowStruct").onclick = () => showStructSheets(true);

if ($("#btnBackPlan")) $("#btnBackPlan").onclick = () => {
  S.sectionView = false;
  S.beamView = false;
  S.structView = false;
  S.elevView = false;
  doRender();                       // shows the plan; clears section/beam view
  status("floor plan");
};

// re-render the beam layout from the stored beams (after edits). Zoom / pan are
// PRESERVED — the caller sets S.forceFit only when first opening the view.
let _beamBusy = false, _beamPending = false;
async function regenBeam() {
  if (_beamBusy) { _beamPending = true; return; }   // coalesce, never stack
  _beamBusy = true;
  try {
    do {
      _beamPending = false;
      // do NOT overwrite S.plan.beams here — the table rows point into it and
      // the edits already live there; replacing it would freeze the buttons
      const r = await api().beams(S.plan, 230, 300, false, false);
      if (!r.ok) { fail(r); break; }
      S.beamView = true; S.sectionView = false; S.structView = false;
      showSvg(r.svg, r.info);        // zoom / pan preserved (no forceFit)
      updateSecToggle();
    } while (_beamPending);           // a new edit arrived mid-render → redo
  } finally {
    _beamBusy = false;
  }
}

if ($("#btnShowBeam")) $("#btnShowBeam").onclick = async () => {
  if (!S.plan) return status("read or load a plan first");
  if (!(S.plan.beams || []).length) return $("#btnBeam").click();
  S.forceFit = true; S.structView = false;   // fit once on entering the beam view
  await regenBeam();
  status("beam layout only — press ‘All structural’ to see every sheet");
};

// the top-bar Beam Layout button: auto-generate beams (once) then show them
$("#btnBeam").onclick = async () => {
  if (!S.plan) return status("read or load a plan first");
  const regen = !(S.plan.beams || []).length;
  pushUndo();
  busy(true, regen ? "Placing beams on every wall (230 mm)…"
                   : "Drawing the beam layout…");
  const r = await api().beams(S.plan, 230, 300, regen);
  busy(false);
  if (!r.ok) return fail(r);
  if (r.beams) S.plan.beams = r.beams;
  markDirty();
  S.forceFit = true; S.beamView = true; S.sectionView = false;
  showSvg(r.svg, r.info);
  buildTable("beams"); updateSecToggle();
  // On the DESKTOP (in-process, fast) go straight to the WHOLE structural set.
  // On the WEB, composing all 14 sheets + shipping a ~0.5 MB SVG every time is
  // the slow part — so show just the beam layout (snappy) and let the user open
  // the full set on demand with the ‘All structural’ toggle. The EXPORT still
  // always contains every sheet regardless.
  if (!isWeb()) {
    showStructSheets(true);
  } else {
    status("beam layout ready — press ‘All structural’ for the full set "
           + "(Export always includes every sheet)");
  }
};

// Elevation — develop the four outer faces professionally
$("#btnElev").onclick = async () => {
  if (!S.plan) return status("read or load a plan first");
  const prm = S.plan.section_params || null;   // reuse section heights if set
  const multi = allFloorsView();
  busy(true, multi
    ? "Developing the MULTI-FLOOR elevations — every storey to full height…"
    : "Developing the four elevations…");
  const r = multi
    ? await api().elevation_project(S.floors, prm)
    : await api().elevations(S.plan, prm);
  busy(false);
  if (!r.ok) return fail(r);
  if (r.plan && !multi) S.plan = r.plan;
  S.forceFit = true; S.beamView = false; S.sectionView = false;
  S.structView = false; S.elevView = true;
  showSvg(r.svg, r.info);
  updateSecToggle();
  status((multi ? "multi-floor elevations — every storey's own openings. "
                : "")
    + (prm ? "elevations — front / rear / left / right, fully dimensioned"
           : "elevations (default heights) — set exact heights via the "
             + "Section questionnaire, then press Elevation again"));
};

// Regenerate / bulk width / bulk depth / renumber from the Beams tab
async function beamAction(kind) {
  if (!S.plan) return;
  if (kind === "regen") {
    if ((S.plan.beams || []).length &&
        !confirm("Regenerate beams on every wall? This replaces the current "
          + "beams (Ctrl+Z undoes it).")) return;
    pushUndo();
    const r = await api().beams(S.plan, 230, 300, true);
    if (!r.ok) return fail(r);
    if (r.beams) S.plan.beams = r.beams;
    markDirty(); buildTable("beams");
    if (S.beamView) showSvg(r.svg, r.info);      // keep current zoom / pan
    return status(`${r.count} beams regenerated`);
  }
  const beams = S.plan.beams || [];
  if (!beams.length) return status("no beams yet — press Beam Layout first");
  if (kind === "width" || kind === "depth") {
    const cur = kind === "width" ? 230 : 300;
    const v = parseFloat(prompt(`Set ${kind} (mm) for ALL beams:`, cur));
    if (!v || v <= 0) return;
    pushUndo();
    beams.forEach(b => b[kind + "_mm"] = Math.round(v));
  } else if (kind === "renumber") {
    pushUndo();
    beams.slice().sort((a, b) =>
      ((b.y1 + b.y2) - (a.y1 + a.y2)) || ((a.x1 + a.x2) - (b.x1 + b.x2)))
      .forEach((b, i) => b.tag = "B" + (i + 1));
  }
  markDirty(); buildTable("beams");
  if (S.beamView) await regenBeam();
}

// re-cut and show the section using the stored heights (no questionnaire)
let _secBusy = false;
async function regenSection() {
  if (!S.plan.section_params) return $("#btnSection").click();
  if (_secBusy) return;
  _secBusy = true;
  try {
    syncSections(S.plan);
    const multi = allFloorsView();
    const r = multi
      ? await api().section_project(S.floors, S.plan.section_params)
      : await api().section(S.plan, S.plan.section_params);
    if (!r.ok) return fail(r);
    if (r.plan && !multi) S.plan = r.plan;   // keep flips / params in sync
    S.sectionView = true;             // zoom / pan preserved across edits
    showSvg(r.svg, r.info);
    updateSecToggle();
  } finally {
    _secBusy = false;
  }
}

if ($("#btnShowSection")) $("#btnShowSection").onclick = async () => {
  if (!S.plan || !(S.plan.sections || []).length)
    return status("add a section line first (Sections tab)");
  if (!S.plan.section_params)       // first time → ask the heights once
    return $("#btnSection").click();
  S.forceFit = true;                // fit once on entering the section view
  await regenSection();
  status("section view — press Plan to go back");
};

// structural rebar / grades editor → S.plan.struct (used by the framing sheets)
const STRUCT_FIELDS = {
  stBeamTop: "beam_top", stBeamBot: "beam_bot", stStirrup: "stirrup",
  stSlabD: "slab_depth", stSlabMain: "slab_main", stSlabDist: "slab_dist",
  stConc: "conc", stSteel: "steel",
};
function openStruct() {
  if (!S.plan) return status("read or load a plan first");
  const s = S.plan.struct || {};
  for (const [id, key] of Object.entries(STRUCT_FIELDS))
    if ($("#" + id) && s[key] != null) $("#" + id).value = s[key];
  $("#structWrap").classList.remove("hidden");
}
if ($("#structCancel")) $("#structCancel").onclick = () =>
  $("#structWrap").classList.add("hidden");
if ($("#structGo")) $("#structGo").onclick = () => {
  const s = S.plan.struct || (S.plan.struct = {});
  for (const [id, key] of Object.entries(STRUCT_FIELDS)) {
    const el = $("#" + id);
    if (el && el.value.trim()) s[key] = el.value.trim();
  }
  markDirty();
  $("#structWrap").classList.add("hidden");
  status("structural rebar / grades saved — used on the framing sheets on Export");
};

$("#btnSection").onclick = () => {
  if (!S.plan) return status("read or load a plan first");
  if (!(S.plan.sections || []).length)
    return status("add a section line first — open the Sections tab and press "
      + "“+ Horizontal cut” or “+ Vertical cut”");
  $("#secInfo").textContent = (S.plan.sections.length)
    + " section line(s) will be cut";
  $("#secWrap").classList.remove("hidden");
};
if ($("#secFoundSkip")) {
  $("#secFoundSkip").onchange = e => {
    $("#secFound").disabled = e.target.checked;
  };
  $("#secGF").onchange = e => {
    const gf = e.target.checked;
    ["secPlinth", "secPBT", "secPBH"].forEach(id => {
      const el = $("#" + id); if (el) el.disabled = !gf;
    });
  };
}
if ($("#secCancel")) $("#secCancel").onclick = () =>
  $("#secWrap").classList.add("hidden");
if ($("#secGo")) $("#secGo").onclick = async () => {
  const num = id => parseFloat($("#" + id).value) || 0;
  const params = {
    is_ground: $("#secGF").checked,
    plinth_mm: num("secPlinth"),
    floor_height_mm: num("secFloor"),
    slab_thk_mm: num("secSlab"),
    beam_depth_mm: num("secBeam"),
    floors: Math.max(1, num("secFloors")),
    parapet_mm: num("secPara"),
    foundation_mm: $("#secFoundSkip").checked ? 0 : num("secFound"),
    plinth_beam_thk_mm: $("#secGF").checked ? num("secPBT") : 0,
    plinth_beam_ht_mm: $("#secGF").checked ? num("secPBH") : 0,
  };
  if (params.floor_height_mm <= 0)
    return status("enter the floor-to-floor height");
  $("#secWrap").classList.add("hidden");
  syncSections(S.plan);                       // one cut line for every floor
  const multi = allFloorsView();
  busy(true, multi
    ? "Cutting the MULTI-FLOOR section — every storey stacked, one dim stack…"
    : "Cutting the section — walls, slabs, plinth, openings, levels…");
  const r = multi
    ? await api().section_project(S.floors, params)
    : await api().section(S.plan, params);
  busy(false);
  if (!r.ok) return fail(r);
  S.plan.section_params = params;            // remembered for Export
  markDirty();
  // show the section(s) on screen — the plan is hidden until Re-draw
  S.forceFit = true;
  showSvg(r.svg, r.info);
  S.sectionView = true;
  updateSecToggle();
  status((multi
      ? r.count + " multi-floor section(s) — every storey stacked. "
      : r.count + " section(s) shown. ")
    + "Press “Plan” to go back. Saved to the output folder"
    + (multi ? "" : " and added to the combined DXF on Export"));
};

$("#btnBoq").onclick = async () => {
  if (!S.plan) return status("read or load a plan first");
  const h = prompt(
    "Floor height (finished floor to slab bottom) in FEET.\n\n"
    + "A 2D plan carries no height, so masonry / plaster / paint volumes "
    + "need this one figure. Everything else is measured from the drawing.",
    "10");
  if (h === null) return;
  busy(true, "Generating the BOQ workbook — masonry, plaster, flooring, "
           + "skirting, doors/windows, painting, columns…");
  const r = await api().boq(S.plan, parseFloat(h) || 10);
  busy(false);
  if (!r.ok) return fail(r);
  pushLog("BOQ written:\n  " + r.path);
  status("BOQ Excel generated → " + (r.name || r.path)
    + "  ·  " + (r.items || 0) + " items, " + (r.blocked || 0) + " blocked");
};

$("#btnPlumb").onclick = async () => {
  if (!S.plan) return status("read or load a plan first");
  if (!(S.plan.furniture || []).length && !confirm(
      "The plumbing follows the fixtures — the WC, basin, shower and kitchen "
      + "counter tell it where the water and drainage go.\n\nThere is no "
      + "furniture yet. Carry on anyway?"))
    return;
  const had = (S.plan.plumb || []).length;
  if (had && !confirm(
      `This plan already has a plumbing layout — ${had} point(s), `
      + `${(S.plan.pipes || []).length} pipe run(s).\n\nLaying it out again `
      + `replaces all of it.\n\nCtrl+Z undoes it. Lay out again?`)) return;
  pushUndo();
  const multi = allFloorsView();
  busy(true, multi
    ? "Laying out plumbing on EVERY floor — water, soil, waste, rain, chambers…"
    : "Laying out the plumbing — water, soil, waste, rain water and the chambers…");
  const res = await forEachFloorPlan(p => api().plumb(p));
  busy(false);
  const bad = stageFailed(res); if (bad) return fail(bad);
  await loadLayers();
  const want = new Set(LAYERS.views.plumbing || []);
  LAYERS.groups.forEach(g => S.layerState[g.key] = want.has(g.key));
  markDirty(); buildTables(); redraw();
  const total = stageTotal(res, "count"), pipes = stageTotal(res, "pipes");
  status((multi ? `across ${res.length} floors — ` : "")
    + `${total} plumbing point(s), ${pipes} pipe run(s) · only sanitary and `
    + `kitchen fixtures shown — the rest is off in the Layers tab`);
};

$("#btnFurn").onclick = async () => {
  if (!S.plan) return status("read or load a plan first");
  const had = (S.plan.furniture || []).length;
  if (had && !confirm(
      `This plan already has a furniture layout — ${had} piece(s).\n\n`
      + `Laying it out again replaces all of it, losing any moves, turns or `
      + `resizes you made.\n\nCtrl+Z undoes it. Lay out again?`)) return;
  pushUndo();
  const multi = allFloorsView();
  busy(true, multi
    ? "Laying out furniture on EVERY floor — sizes, clearances and Vaastu…"
    : "Laying out the furniture — sizes, clearances and Vaastu…");
  const res = await forEachFloorPlan(p => api().furnish(p));
  busy(false);
  const bad = stageFailed(res); if (bad) return fail(bad);
  if (S.floors && S.floors.length) S.floors.forEach(f => clampFurniture(f.plan));
  else clampFurniture(S.plan);
  markDirty(); buildTables(); redraw();
  tab("furniture");
  const total = stageTotal(res, "count");
  status(multi
    ? `${total} piece(s) placed across ${res.length} floors — see the Vaastu tab`
    : `${total} piece(s) placed — see the Vaastu tab for compliance`);
};
$("#notesCancel").onclick = () => $("#notesWrap").classList.add("hidden");
$("#notesGo").onclick = async () => {
  $("#notesWrap").classList.add("hidden");
  const t0 = Date.now();
  tab("log");                       // the read reports its progress there
  $("#btnCancel").textContent = "Cancel";
  busy(true, "Reading the drawing — forensic examination…", true);
  const tick = setInterval(() => {
    const s = Math.round((Date.now() - t0) / 1000);
    const last = (window.lastLog || "").slice(0, 90);
    $("#busyMsg").innerHTML =
      `Reading the drawing… ${Math.floor(s / 60)}m ${s % 60}s`
      + (last ? `<div class="sub" style="margin-top:6px">${esc(last)}</div>` : "");
  }, 1000);
  const r = await api().read_sketch($("#notesBox").value || "",
                                    $("#chkFresh").checked);
  clearInterval(tick);
  busy(false);
  pushLog(`read took ${Math.round((Date.now() - t0) / 1000)}s`);
  if (r.log) pushLog(r.log);
  if (!r.ok) return fail(r);
  setPlan(r.plan);
  status("drawing read — check every row, fix what is wrong, the drawing updates live");
};

$("#btnSave").onclick = () => savePlan(false);
if ($("#btnSaveAs")) $("#btnSaveAs").onclick = () => savePlan(true);

if ($("#btnLoad")) $("#btnLoad").onclick = async () => {
  // WEB: the native file dialog does not exist — read the saved .json in the
  // browser with the file picker (same as Open Drawing's JSON branch).
  if (isWeb()) {
    const f = await webPickFile(".json");
    if (!f) return;
    if (f.error) return fail({ error: f.error });
    if (!f.json) return status("please pick a saved .json plan file");
    const nF = loadAnyJson(f.json, f.name);
    S.saveName = f.name || "";
    S.dirty = false;
    showSaved();
    status(nF > 1 ? `project loaded — ${nF} floors (switch them on the floor bar)`
                  : "plan loaded — " + (f.name || "saved file"));
    return;
  }
  const r = await api().load_plan_json();
  if (!r.ok) return fail(r);
  if (r.cancelled) return;
  const nFd = loadAnyJson(r.plan, r.name);
  S.savePath = r.path || "";        // Ctrl+S returns to the file it came from
  S.saveName = r.name || "";
  S.dirty = false;
  showSaved();
  status(nFd > 1 ? `project loaded — ${nFd} floors (switch them on the floor bar)`
                : "plan loaded — " + (r.name || "saved file"));
};
$("#btnSample").onclick = async () => {
  const r = await api().load_sample();
  if (!r.ok) return fail(r);
  setPlan(r.plan);
};
$("#btnRender").onclick = doRender;
$("#selSheet").onchange = doRender;
$("#selOrient").onchange = doRender;
$("#chkTags").onchange = doRender;

$("#btnExport").onclick = async () => {
  // multi-floor: export EVERY floor, each to its own sheets, wall numbers
  // running continuously across floors
  const withPlan = S.floors.filter(f => f.plan
    && (f.plan.walls || []).length && (f.plan.rooms || []).length);
  if (withPlan.length > 1) {
    busy(true, `Exporting ${withPlan.length} floors into ONE combined file — `
             + `every floor's sheets in a single DXF + PDF…`);
    const base = (S.saveName || "project").replace(/\.[^.]+$/, "");
    const r = await api().export_project(S.floors, $("#selSheet").value,
                                         $("#selOrient").value, base, DUNIT);
    busy(false);
    if (!r.ok) return fail(r);
    S.lastFolder = r.folder || "";
    if (isWeb()) webDownloadCombined(r.paths);
    const files = Object.entries(r.paths || {})
      .filter(([k]) => k !== "folder")
      .map(([k, v]) => "  " + (v || "").split("\\").pop()).join("\n");
    pushLog(`Exported ${r.floors} floors into ONE combined file (continuous `
      + `wall numbers, plus the multi-floor section & elevation):\n` + files
      + `\n\nFolder:\n  ${r.folder}`);
    return status(`exported ${r.floors} floors — ONE combined DXF + PDF in `
      + `${r.folder}`);
  }
  busy(true, "Exporting one combined DXF — architecture + full structural set…");
  const r = await api().export(S.plan, $("#selSheet").value,
                               $("#selOrient").value, "", false, DUNIT);
  busy(false);
  if (!r.ok) return fail(r);
  S.lastFolder = r.folder || "";
  if (isWeb()) webDownloadCombined(r.paths);
  const combined = (r.paths.combined_dxf || "").split("\\").pop();
  pushLog("Exported to " + r.folder
    + "\n\n★ ONE COMBINED FILE holds EVERY sheet (floor plan, furniture, "
    + "electrical, plumbing, flooring, beam layout & framing, beam details, "
    + "BBS, column schedule/layout, footing layout/details, slab / staircase "
    + "/ terrace sections, foundation) side by side:"
    + "\n  " + combined
    + "\n\n(also written as .pdf / .png / .svg of the same combined drawing — "
    + "no separate per-sheet files)");
  status("exported — one combined DXF with everything: " + combined);
};
$("#btnFolder").onclick = () => {
  // on the web build the output lives on the server — Export downloads it
  if (isWeb()) return status("Web build: Export downloads the file straight to "
    + "your browser — there is no folder to open.");
  api().open_folder(S.lastFolder || "");
};
if ($("#btnDims")) $("#btnDims").onclick = () => autoDims();
if ($("#btnRefV")) $("#btnRefV").onclick = () => addRef("v");
if ($("#btnRefH")) $("#btnRefH").onclick = () => addRef("h");
if ($("#btnRefClr")) $("#btnRefClr").onclick = () => clearRefs();

/* PDF → DXF — a direct geometric conversion (no AI, offline) */
if ($("#btnPdf2Dxf")) $("#btnPdf2Dxf").onclick = async () => {
  const report = (r) => {
    const e = r.entities || {};
    pushLog(`PDF → DXF: ${r.pages} page(s) → ${e.lines || 0} lines, `
      + `${e.rects || 0} rects, ${e.curves || 0} curves, ${e.text || 0} text\n`
      + `  ${(r.path || "").split("\\").pop()}`);
  };
  if (isWeb()) {
    const f = await webPickFile(".pdf");
    if (!f) return;
    if (f.error || !f.path) return fail({ error: f.error || "upload failed" });
    busy(true, "Converting PDF → DXF (geometry only, offline)…");
    const r = await api().pdf_to_dxf(f.path);
    busy(false);
    if (!r.ok) return fail(r);
    report(r);
    const a = document.createElement("a");
    a.href = "/download?path=" + encodeURIComponent(r.path);
    a.download = ""; document.body.appendChild(a); a.click(); a.remove();
    return status("PDF converted to DXF — downloaded");
  }
  busy(true, "Converting PDF → DXF (geometry only, offline)…");
  const r = await api().pdf_to_dxf("");
  busy(false);
  if (!r.ok) return fail(r);
  if (r.cancelled) return;
  report(r);
  status("PDF → DXF done: " + (r.name || "") + " — in the output folder");
};


/* drag & drop is handled by the shell; keep the hint honest */
["dragover", "drop"].forEach(t =>
  $("#skView").addEventListener(t, e => e.preventDefault()));

/* ── login gate (disabled) ───────────────────────────────────
   Login was removed at the user's request — the app opens straight to the
   workspace. The #login overlay is hidden the moment the page loads.        */
if ($("#login")) $("#login").classList.add("hidden");

/* The bridge may be injected before or after this script runs, so poll for it
   instead of relying on the pywebviewready event alone. */
function addLogoutButton() {
  if (document.getElementById("btnLogout")) return;
  const b = document.createElement("button");
  b.id = "btnLogout";
  b.className = "btn";
  b.textContent = "Log out";
  b.title = "Sign out and return to the login page";
  b.style.marginLeft = "auto";        // push to the right end of the top bar
  b.onclick = async () => {
    try { await fetch("/logout", { method: "POST" }); } catch (e) {}
    location.href = "/";
  };
  const bar = document.querySelector("header.bar") || document.body;
  bar.appendChild(b);
}

async function boot() {
  status("ready");
  // RECOVERY: a refresh / crash / tunnel drop no longer loses finished work —
  // the last autosaved project is offered back before anything else
  try {
    const back = takeAutosave();
    if (back && !S.dirty && !(S.plan)) {
      const nf = (back.floors || []).filter(fl => fl && fl.plan).length;
      if (nf && confirm(`Pichhla kaam mila — ${nf} floor(s) ka autosave. `
          + `Wapas load karein?`)) {
        loadAnyJson(back, "autosave");
        status(`recovered — ${nf} floor(s) from the last session (Save karke `
          + `file bana lo)`);
      }
    }
  } catch (e) { /* recovery must never block boot */ }
  if (isWeb()) {
    document.body.classList.add("web");  // single display — hide the input pane
    addLogoutButton();                  // a Log out control on the web build
    // The AI 'Read Drawing' runs on the SERVER via the Claude CLI. A cloud host
    // has no CLI (off), but when the server runs on your OWN PC (localhost /
    // Cloudflare tunnel) the CLI is right there — so ask the server if it has it.
    let ai = false;
    try {
      const st = await api().cli_status();
      ai = !!(st && st.exe && !st.error);
      window.WEB_AI = ai;
      if (!ai && st && st.error) pushLog(st.error);
    } catch (e) { window.WEB_AI = false; }
    // btnRead/btnQuiz are the desktop's two-step flow; on the web the AI read is
    // driven straight from Open Drawing, so keep those two hidden either way.
    ["btnRead", "btnQuiz"].forEach(id => {
      const b = $("#" + id); if (b) b.style.display = "none";
    });
    if (ai) {
      pushLog("This server has the Claude CLI — AI 'Read Drawing' is ON. "
        + "Open Drawing → pick a photo / PDF / sketch and it is read into an "
        + "editable plan (or open a DXF / saved JSON plan).");
      status("ready — Open Drawing (photo/PDF read is ON) or a DXF/JSON plan");
    } else {
      pushLog("WEB build — the AI 'Read Drawing' is OFF (no Claude CLI on this "
        + "server). Open a DXF or a saved JSON plan, then Furniture / Structural "
        + "/ Export (one combined DXF) — all offline.");
      status("web build ready — Open a DXF or JSON plan");
    }
    return;
  }
  try {
    const st = await api().cli_status();        // preflight the AI read
    if (st && st.error) {
      banner(st.error);
      pushLog(st.error);
      status("the AI read is unavailable — see the message");
    } else if (st && st.exe) {
      pushLog("Claude CLI: " + st.exe + "  (" + (st.auth || "?") + ")");
      status("ready — open a sketch");
    }
  } catch (e) {
    pushLog("preflight failed: " + e);
  }
}
(function waitForBridge(n = 0) {
  // desktop: wait for the REAL pywebview bridge (its methods land a moment after
  // the object). web: pywebview never appears, so after a short wait, boot in
  // web mode (boot() detects isWeb()).
  if (window.pywebview && window.pywebview.api &&
      typeof window.pywebview.api.cli_status === "function") return boot();
  if (n < 15) return setTimeout(() => waitForBridge(n + 1), 100);
  return boot();
})();


if ($("#chkAllFloors")) $("#chkAllFloors").onchange = () => {
  _sel = null;
  if ($("#gizmo")) $("#gizmo").classList.add("hidden");
  S.forceFit = true;
  doRender();
};
