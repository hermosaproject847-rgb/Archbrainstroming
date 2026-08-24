/* 3D MODEL — builds the whole house in 3D from the live plan (walls with the
   doors/windows cut out, columns, beams, floor slabs, parapet, plinth, stairs)
   and shows it in an orbit viewer: drag = rotate, wheel = zoom, right-drag =
   pan, exactly like a normal 3D package. The "External walls" slider fades the
   outer shell so the internal structure reads through. */
(function () {
  "use strict";
  if (typeof THREE === "undefined") return;

  const MM = 1 / 304.8;
  let renderer = null, scene = null, camera = null, raf = 0, open = false;
  let extMats = [];                       // exterior shell materials (slider)
  const orbit = { az: -0.9, el: 0.55, dist: 90, tx: 0, ty: 6, tz: 0 };

  const $ = s => document.querySelector(s);

  /* ---------------- parameters (from the section questionnaire if stored) */
  function params() {
    const p = (S.plan && (S.plan.section_params || {})) || {};
    const mm = v => (+v || 0) * MM;
    const floors = Math.max(1, +(p.floors || (S.floors || []).filter(f => f.plan).length || 1));
    return {
      plinth: p.plinth_mm != null ? mm(p.plinth_mm) : mm(450),
      fh: mm(p.floor_height_mm) || mm(3000),
      slab: mm(p.slab_thk_mm) || mm(125),
      para: p.parapet_mm != null ? mm(p.parapet_mm) : mm(900),
      beamD: mm(300),
      sill: mm(900), lintel: mm(2100), doorH: mm(2100),
      floors
    };
  }

  /* model (x, y[plan], z[up]) → three (x, y=up, z=-planY) */
  function box(sx, sy, sz, cx, cy, cz, mat) {
    const m = new THREE.Mesh(new THREE.BoxGeometry(sx, sz, sy), mat);
    m.position.set(cx, cz, -cy);
    return m;
  }

  function mats() {
    const ext = new THREE.MeshLambertMaterial({ color: 0xd9cfbf, transparent: true, opacity: 1 });
    extMats.push(ext);
    return {
      ext,
      int_: new THREE.MeshLambertMaterial({ color: 0xece6da }),
      conc: new THREE.MeshLambertMaterial({ color: 0x99a0a8 }),
      slab: new THREE.MeshLambertMaterial({ color: 0xc7cbd1 }),
      glass: new THREE.MeshLambertMaterial({ color: 0x9ec8e8, transparent: true, opacity: 0.45 }),
      step: new THREE.MeshLambertMaterial({ color: 0xb9b2a4 }),
      door: new THREE.MeshLambertMaterial({ color: 0x8a5a34 }),
    };
  }

  /* one wall, its doors/windows CUT OUT (under-sill + over-lintel pieces) */
  function addWall(g, plan, w, z0, H, P, M) {
    const dx = w.x2 - w.x1, dy = w.y2 - w.y1;
    const L = Math.hypot(dx, dy); if (L < 0.05) return;
    const ux = dx / L, uy = dy / L;
    const t = ((+w.thickness_in || 5) / 12);
    const mat = w.exterior ? M.ext : M.int_;
    const ang = Math.atan2(-uy, ux);          // three-space yaw (z = -y)

    const ops = (plan.openings || [])
      .filter(o => o.wall_id === w.id)
      .map(o => {
        const door = /door|open|gate/.test(o.type || "");
        return {
          a: Math.max(0, +o.pos || 0),
          b: Math.min(L, (+o.pos || 0) + (+o.width || 3)),
          sill: door ? 0 : (o.sill_mm != null ? (+o.sill_mm) * MM : P.sill),
          head: (o.lintel_mm != null ? (+o.lintel_mm) * MM : (door ? P.doorH : P.lintel)),
          win: !door,
        };
      })
      .filter(o => o.b - o.a > 0.05)
      .sort((p1, p2) => p1.a - p2.a);

    const put = (a, b, zz0, zz1, m) => {
      if (b - a < 0.02 || zz1 - zz0 < 0.02) return;
      const mid = (a + b) / 2;
      const mesh = box(b - a, t, zz1 - zz0,
        w.x1 + ux * mid, w.y1 + uy * mid, z0 + (zz0 + zz1) / 2, m);
      mesh.rotation.y = ang;
      g.add(mesh);
    };

    let cur = 0;
    for (const o of ops) {
      put(cur, o.a, 0, H, mat);
      if (o.sill > 0.05) put(o.a, o.b, 0, Math.min(o.sill, H), mat);
      if (o.head < H - 0.05) put(o.a, o.b, Math.min(o.head, H), H, mat);
      if (o.win) {                         // glass pane in the hole
        const mid = (o.a + o.b) / 2;
        const gl = box(o.b - o.a, t * 0.25, Math.max(0.1, Math.min(o.head, H) - o.sill),
          w.x1 + ux * mid, w.y1 + uy * mid, z0 + (o.sill + Math.min(o.head, H)) / 2, M.glass);
        gl.rotation.y = ang;
        g.add(gl);
      }
      cur = o.b;
    }
    put(cur, L, 0, H, mat);
  }

  function addStairs(g, plan, z0, rise, M) {
    for (const s of (plan.stairs || [])) {
      const alongX = (s.run_axis || "x") === "x";
      const run = alongX ? s.w : s.h;
      const breadth = alongX ? s.h : s.w;
      const n = Math.max(8, (+s.steps_f1 || 0) + (+s.steps_f2 || 0) + (+s.steps_f3 || 0) || 15);
      const tread = run / n, riser = rise / n;
      for (let i = 0; i < n; i++) {
        const a = i * tread;
        const cx = alongX ? s.x + a + tread / 2 : s.x + s.w / 2;
        const cy = alongX ? s.y + s.h / 2 : s.y + a + tread / 2;
        g.add(box(alongX ? tread : breadth, alongX ? breadth : tread,
          (i + 1) * riser, cx, cy, z0 + (i + 1) * riser / 2, M.step));
      }
    }
  }

  function buildModel() {
    extMats = [];
    const M = mats();
    const P = params();
    const g = new THREE.Group();
    const base = S.plan; if (!base) return g;

    let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
    (base.walls || []).forEach(w => {
      x0 = Math.min(x0, w.x1, w.x2); y0 = Math.min(y0, w.y1, w.y2);
      x1 = Math.max(x1, w.x1, w.x2); y1 = Math.max(y1, w.y1, w.y2);
    });
    if (x1 <= x0) return g;
    const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;

    // plinth base
    g.add(box(x1 - x0 + 1, y1 - y0 + 1, Math.max(P.plinth, 0.1),
      cx, cy, Math.max(P.plinth, 0.1) / 2, M.conc));

    let topZ = P.plinth;
    for (let f = 0; f < P.floors; f++) {
      const plan = ((S.floors || [])[f] && S.floors[f].plan) || base;
      const z0 = P.plinth + f * P.fh;
      const H = P.fh;
      (plan.walls || []).forEach(w => { if (!w.railing) addWall(g, plan, w, z0, H, P, M); });
      // columns run floor to floor
      (plan.columns || []).forEach(c => {
        g.add(box(Math.max(+c.w || 0.8, 0.3), Math.max(+c.h || 0.8, 0.3), H,
          c.x, c.y, z0 + H / 2, M.conc));
      });
      // beams under the slab
      (plan.beams || []).forEach(b => {
        const L = Math.hypot(b.x2 - b.x1, b.y2 - b.y1); if (L < 0.1) return;
        const bw = ((+b.width_mm || 230) * MM), bd = ((+b.depth_mm || 300) * MM);
        const m = box(L, bw, bd, (b.x1 + b.x2) / 2, (b.y1 + b.y2) / 2,
          z0 + H - bd / 2, M.conc);
        m.rotation.y = Math.atan2(-(b.y2 - b.y1), (b.x2 - b.x1));
        g.add(m);
      });
      // floor / roof slab
      g.add(box(x1 - x0 + 0.8, y1 - y0 + 0.8, P.slab, cx, cy, z0 + H + P.slab / 2, M.slab));
      addStairs(g, plan, z0, H, M);
      topZ = z0 + H + P.slab;
    }

    // parapet on the exterior walls, above the roof slab
    if (P.para > 0.05) {
      (base.walls || []).forEach(w => {
        if (!w.exterior || w.railing) return;
        const L = Math.hypot(w.x2 - w.x1, w.y2 - w.y1); if (L < 0.05) return;
        const t = ((+w.thickness_in || 9) / 12) * 0.6;
        const m = box(L, t, P.para, (w.x1 + w.x2) / 2, (w.y1 + w.y2) / 2,
          topZ + P.para / 2, M.ext);
        m.rotation.y = Math.atan2(-(w.y2 - w.y1), (w.x2 - w.x1));
        g.add(m);
      });
    }

    g.position.set(-cx, 0, cy);            // centre the house on the origin
    return g;
  }

  /* ------------------------------------------------------------- viewer */
  function applyCam() {
    const { az, el, dist, tx, ty, tz } = orbit;
    camera.position.set(
      tx + dist * Math.cos(el) * Math.cos(az),
      ty + dist * Math.sin(el),
      tz + dist * Math.cos(el) * Math.sin(az));
    camera.lookAt(tx, ty, tz);
  }

  function openViewer() {
    if (!S.plan) { status("Pehle plan generate/khol karein"); return; }
    const holder = $("#view3d"); holder.classList.remove("hidden");
    const canvas = $("#v3canvas");
    if (!renderer) {
      renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
      renderer.setPixelRatio(window.devicePixelRatio || 1);
    }
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x1c2230);
    scene.add(new THREE.AmbientLight(0xffffff, 0.55));
    const sun = new THREE.DirectionalLight(0xffffff, 0.85);
    sun.position.set(60, 90, 40); scene.add(sun);
    const sun2 = new THREE.DirectionalLight(0xffffff, 0.25);
    sun2.position.set(-50, 40, -60); scene.add(sun2);
    const grid = new THREE.GridHelper(200, 40, 0x37415a, 0x2a3248);
    scene.add(grid);
    scene.add(buildModel());

    camera = new THREE.PerspectiveCamera(50, 1, 0.1, 2000);
    const p = params();
    orbit.ty = (p.plinth + p.floors * p.fh) / 2;
    orbit.dist = 90; orbit.az = -0.9; orbit.el = 0.55; orbit.tx = 0; orbit.tz = 0;
    open = true;
    const opInp = $("#v3op"); if (opInp) setOpacity(opInp.value / 100);
    resize(); loop();
  }

  function closeViewer() {
    open = false; cancelAnimationFrame(raf);
    $("#view3d").classList.add("hidden");
  }

  function resize() {
    if (!renderer || !open) return;
    const holder = $("#view3d");
    const w = holder.clientWidth, h = holder.clientHeight - 44;
    renderer.setSize(w, h, false);
    camera.aspect = w / h; camera.updateProjectionMatrix();
  }

  function loop() {
    if (!open) return;
    applyCam();
    renderer.render(scene, camera);
    raf = requestAnimationFrame(loop);
  }

  function setOpacity(v) {
    extMats.forEach(m => { m.opacity = v; m.transparent = true; m.needsUpdate = true; });
  }

  /* ------------------------------------------------ mouse / touch orbit */
  function wire() {
    const cv = $("#v3canvas"); if (!cv) return;
    let mode = 0, lx = 0, ly = 0, pinch = 0;
    cv.addEventListener("contextmenu", e => e.preventDefault());
    cv.addEventListener("mousedown", e => {
      mode = (e.button === 2 || e.shiftKey) ? 2 : 1; lx = e.clientX; ly = e.clientY;
    });
    addEventListener("mousemove", e => {
      if (!mode || !open) return;
      const dx = e.clientX - lx, dy = e.clientY - ly; lx = e.clientX; ly = e.clientY;
      if (mode === 1) {
        orbit.az += dx * 0.008;
        orbit.el = Math.min(1.5, Math.max(-0.2, orbit.el + dy * 0.006));
      } else {
        const k = orbit.dist * 0.0016;
        orbit.tx -= (Math.cos(orbit.az + Math.PI / 2)) * dx * k;
        orbit.tz -= (Math.sin(orbit.az + Math.PI / 2)) * dx * k;
        orbit.ty += dy * k;
      }
    });
    addEventListener("mouseup", () => mode = 0);
    cv.addEventListener("wheel", e => {
      if (!open) return;
      orbit.dist = Math.min(400, Math.max(10, orbit.dist * (e.deltaY > 0 ? 1.12 : 0.9)));
      e.preventDefault();
    }, { passive: false });
    cv.addEventListener("touchstart", e => {
      if (e.touches.length === 1) { mode = 1; lx = e.touches[0].clientX; ly = e.touches[0].clientY; }
      else if (e.touches.length === 2) {
        mode = 3;
        pinch = Math.hypot(e.touches[0].clientX - e.touches[1].clientX,
          e.touches[0].clientY - e.touches[1].clientY);
      }
    }, { passive: true });
    cv.addEventListener("touchmove", e => {
      if (!open) return;
      if (mode === 1 && e.touches.length === 1) {
        const dx = e.touches[0].clientX - lx, dy = e.touches[0].clientY - ly;
        lx = e.touches[0].clientX; ly = e.touches[0].clientY;
        orbit.az += dx * 0.008;
        orbit.el = Math.min(1.5, Math.max(-0.2, orbit.el + dy * 0.006));
      } else if (mode === 3 && e.touches.length === 2) {
        const d = Math.hypot(e.touches[0].clientX - e.touches[1].clientX,
          e.touches[0].clientY - e.touches[1].clientY);
        orbit.dist = Math.min(400, Math.max(10, orbit.dist * (pinch / (d || 1))));
        pinch = d;
      }
      e.preventDefault();
    }, { passive: false });
    addEventListener("touchend", () => mode = 0);
    addEventListener("resize", resize);

    const b = $("#btn3D"); if (b) b.onclick = openViewer;
    const c = $("#v3close"); if (c) c.onclick = closeViewer;
    const iso = $("#v3iso");
    if (iso) iso.onclick = () => { orbit.az = -Math.PI / 4; orbit.el = Math.atan(1 / Math.sqrt(2)); };
    const op = $("#v3op");
    if (op) op.oninput = () => setOpacity(op.value / 100);
    const rb = $("#v3rebuild");
    if (rb) rb.onclick = () => { if (open) { closeViewer(); openViewer(); } };
  }

  if (document.readyState === "loading") addEventListener("DOMContentLoaded", wire);
  else wire();
})();
