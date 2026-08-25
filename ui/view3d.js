/* 3D MODEL — the whole house in 3D from the live plan, like a real 3D
   package: orbit / zoom / pan, an x-ray slider for the outer shell, a TOP-2D
   mode (roof off, looking straight down), and toggleable SERVICE layers —
   furniture models, plumbing pipes in their system colours, electrical
   conduiting from each board to its fittings, textured flooring + skirting
   (wood / tile / marble / granite), and a parapet that can turn into a
   railing on the front or on all four sides. */
(function () {
  "use strict";
  if (typeof THREE === "undefined") return;

  const MM = 1 / 304.8;
  let renderer = null, scene = null, camera = null, raf = 0, open = false;
  let extMats = [], intMats = [], floorMats = [];
  let G = {};                                // named groups (toggle layers)
  let modelRoot = null;                      // the built house (for rebuilds)
  let selObj = null, selHelper = null;       // 3D EDIT: current selection
  let homeCenter = null;                     // model bbox centre = orbit pivot
  let topMode = false, orthoH = 60;          // EXACT-2D top view (orthographic)
  let sunL = null, ambL = null, hemiL = null;   // lights (sun-glare slider)
  // LAYER LOCKS — a locked layer's things cannot be selected / moved / edited
  const locks = { struct: false, furn: false, plumb: false, elec: false,
    faces: false, bwall: false };
  // per-FLOOR state, kept across rebuilds: its own groups, eye, lock and the
  // XY offset you can nudge a floor by (to study a shifted upper storey)
  let FL = [];                                  // FL[f] = { layer: Group }
  const floorVis = [], floorLock = [], floorOff = [];
  const LOCKOF = { furn: "furn", elec: "elec", plumb: "plumb", pipe: "plumb",
    col: "struct", beam: "struct", face: "faces" };
  const orbit = { az: -0.9, el: 0.55, dist: 90, tx: 0, ty: 6, tz: 0 };
  const $ = s => document.querySelector(s);

  function params() {
    const p = (S.plan && (S.plan.section_params || {})) || {};
    const mm = v => (+v || 0) * MM;
    const floors = Math.max(1, +(p.floors || (S.floors || []).filter(f => f.plan).length || 1));
    return {
      plinth: p.plinth_mm != null ? mm(p.plinth_mm) : mm(450),
      fh: mm(p.floor_height_mm) || mm(3000),
      slab: mm(p.slab_thk_mm) || mm(125),
      para: p.parapet_mm != null ? mm(p.parapet_mm) : mm(900),
      sill: mm(900), lintel: mm(2100), doorH: mm(2100),
      floors
    };
  }

  function box(sx, sy, sz, cx, cy, cz, mat) {
    const m = new THREE.Mesh(new THREE.BoxGeometry(sx, sz, sy), mat);
    m.position.set(cx, cz, -cy);
    return m;
  }
  function cylBetween(ax, ay, az2, bx, by, bz, r, mat) {
    const a = new THREE.Vector3(ax, az2, -ay), b = new THREE.Vector3(bx, bz, -by);
    const d = b.clone().sub(a), L = d.length(); if (L < 0.02) return null;
    const m = new THREE.Mesh(new THREE.CylinderGeometry(r, r, L, 10), mat);
    m.position.copy(a.clone().add(b).multiplyScalar(0.5));
    m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), d.normalize());
    return m;
  }

  /* ---------------- procedural TEXTURES (no external files) ------------- */
  function texOf(drawFn) {
    const c = document.createElement("canvas"); c.width = c.height = 256;
    drawFn(c.getContext("2d"));
    const t = new THREE.CanvasTexture(c);
    t.wrapS = t.wrapT = THREE.RepeatWrapping;
    return t;
  }
  const TEX = {};
  function floorTex(material) {
    if (TEX[material]) return TEX[material];
    let t;
    if (material === "wood") t = texOf(g => {
      g.fillStyle = "#9a6b45"; g.fillRect(0, 0, 256, 256);
      for (let r = 0; r < 4; r++) {
        const sh = ["#8a5d3a", "#a4754d", "#916342", "#9d6f48"][r];
        g.fillStyle = sh; g.fillRect(0, r * 64, 256, 62);
        g.fillStyle = "rgba(60,35,18,.55)"; g.fillRect(0, r * 64 + 62, 256, 2);
        g.fillRect(((r * 97) % 256), r * 64, 2, 62);   // staggered end joints
        g.strokeStyle = "rgba(120,80,50,.35)";
        for (let k = 0; k < 5; k++) { g.beginPath(); g.moveTo(0, r * 64 + 8 + k * 11); g.lineTo(256, r * 64 + 6 + k * 12); g.stroke(); }
      }
    });
    else if (material === "marble") t = texOf(g => {
      g.fillStyle = "#e9e7e2"; g.fillRect(0, 0, 256, 256);
      g.strokeStyle = "rgba(150,150,160,.5)"; g.lineWidth = 2;
      for (let i = 0; i < 6; i++) {
        g.beginPath(); g.moveTo(0, 20 + i * 40);
        g.bezierCurveTo(80, i * 40, 150, 70 + i * 35, 256, 30 + i * 42); g.stroke();
      }
      g.strokeStyle = "rgba(90,90,100,.7)"; g.lineWidth = 3;
      g.strokeRect(1, 1, 254, 254);                    // slab joint
    });
    else if (material === "granite") t = texOf(g => {
      g.fillStyle = "#5c5f66"; g.fillRect(0, 0, 256, 256);
      for (let i = 0; i < 900; i++) {
        g.fillStyle = ["#7c7f88", "#3f4149", "#8f939c", "#2f3138"][i % 4];
        g.fillRect(Math.random() * 256, Math.random() * 256, 2.2, 2.2);
      }
      g.strokeStyle = "rgba(25,26,30,.8)"; g.lineWidth = 3;
      g.strokeRect(1, 1, 254, 254);
    });
    else t = texOf(g => {                              // vitrified TILE
      g.fillStyle = "#ddd9d2"; g.fillRect(0, 0, 256, 256);
      g.fillStyle = "rgba(255,255,255,.35)";
      for (let i = 0; i < 40; i++) g.fillRect(Math.random() * 256, Math.random() * 256, 8, 3);
      g.strokeStyle = "#a9a49c"; g.lineWidth = 4;
      g.strokeRect(1, 1, 254, 254);                    // grout square
    });
    TEX[material] = t;
    return t;
  }

  function mats() {
    const ext = new THREE.MeshLambertMaterial({ color: 0xd9cfbf, transparent: true, opacity: 1 });
    extMats.push(ext);
    const int_ = new THREE.MeshLambertMaterial({ color: 0xece6da, transparent: true, opacity: 1 });
    intMats.push(int_);
    return {
      ext,
      int_,
      conc: new THREE.MeshLambertMaterial({ color: 0x99a0a8 }),
      slab: new THREE.MeshLambertMaterial({ color: 0xc7cbd1, transparent: true, opacity: 1 }),
      glass: new THREE.MeshLambertMaterial({ color: 0x9ec8e8, transparent: true, opacity: 0.45 }),
      step: new THREE.MeshLambertMaterial({ color: 0xb9b2a4 }),
      door: new THREE.MeshLambertMaterial({ color: 0x8a5a34 }),
      frame: new THREE.MeshLambertMaterial({ color: 0x5f4630 }),
      chajja: new THREE.MeshLambertMaterial({ color: 0xb9bec6 }),
      rail: new THREE.MeshLambertMaterial({ color: 0x3d434d }),
    };
  }

  /* ---- one wall with detailed openings (frame, mullions, glass, chajja) */
  function addWall(g, plan, w, z0, H, P, M, cxAll, cyAll) {
    const dx = w.x2 - w.x1, dy = w.y2 - w.y1;
    const L = Math.hypot(dx, dy); if (L < 0.05) return;
    const ux = dx / L, uy = dy / L;
    const t = ((+w.thickness_in || 5) / 12);
    const mat = w.exterior ? M.ext : M.int_;
    const ang = Math.atan2(-uy, ux);
    let nx = -uy, ny = ux;
    const mxw = (w.x1 + w.x2) / 2, myw = (w.y1 + w.y2) / 2;
    if ((mxw + nx - cxAll) ** 2 + (myw + ny - cyAll) ** 2 <
        (mxw - nx - cxAll) ** 2 + (myw - ny - cyAll) ** 2) { nx = -nx; ny = -ny; }

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

    const wob = (a, b, zz0, zz1, ct, off, m) => {
      if (b - a < 0.015 || zz1 - zz0 < 0.015) return;
      const mid = (a + b) / 2;
      const mesh = box(b - a, ct, zz1 - zz0,
        w.x1 + ux * mid + nx * off, w.y1 + uy * mid + ny * off,
        z0 + (zz0 + zz1) / 2, m);
      mesh.rotation.y = ang;
      g.add(mesh);
    };
    const put = (a, b, zz0, zz1, m) => wob(a, b, zz0, zz1, t, 0, m);

    let cur = 0;
    for (const o of ops) {
      put(cur, o.a, 0, H, mat);
      const head = Math.min(o.head, H);
      if (o.sill > 0.05) put(o.a, o.b, 0, Math.min(o.sill, H), mat);
      if (head < H - 0.05) put(o.a, o.b, head, H, mat);
      const fw = 0.16, ft2 = t * 0.55;
      if (o.win) {
        wob(o.a, o.b, o.sill, o.sill + fw, ft2, 0, M.frame);
        wob(o.a, o.b, head - fw, head, ft2, 0, M.frame);
        wob(o.a, o.a + fw, o.sill, head, ft2, 0, M.frame);
        wob(o.b - fw, o.b, o.sill, head, ft2, 0, M.frame);
        wob(o.a + fw, o.b - fw, o.sill + fw, head - fw, t * 0.18, 0, M.glass);
        const wSpan = o.b - o.a - 2 * fw;
        const nMul = Math.max(0, Math.round(wSpan / 2.5) - 1);
        for (let k = 1; k <= nMul; k++) {
          const mx2 = o.a + fw + wSpan * k / (nMul + 1);
          wob(mx2 - 0.05, mx2 + 0.05, o.sill + fw, head - fw, ft2 * 0.8, 0, M.frame);
        }
        if (head - o.sill > 3.2)
          wob(o.a + fw, o.b - fw, (o.sill + head) / 2 - 0.05,
              (o.sill + head) / 2 + 0.05, ft2 * 0.8, 0, M.frame);
        if (w.exterior)
          wob(o.a - 0.2, o.b + 0.2, o.sill - 0.2, o.sill, 0.25, t / 2 + 0.125, M.chajja);
      } else {
        wob(o.a, o.a + fw, 0, head, ft2, 0, M.frame);
        wob(o.b - fw, o.b, 0, head, ft2, 0, M.frame);
        wob(o.a, o.b, head - fw, head, ft2, 0, M.frame);
        wob(o.a + fw, o.b - fw, 0.02, head - fw, t * 0.3, 0, M.door);
      }
      if (w.exterior) {
        const proj = 1.5, thk = 0.3;
        const mid = (o.a + o.b) / 2;
        const ch = box((o.b - o.a) + 0.8, proj, thk,
          w.x1 + ux * mid + nx * (t / 2 + proj / 2),
          w.y1 + uy * mid + ny * (t / 2 + proj / 2),
          z0 + head + thk / 2, M.chajja);
        ch.rotation.y = ang;
        g.add(ch);
      }
      cur = o.b;
    }
    put(cur, L, 0, H, mat);
  }

  /* ----------------------------------------------- staircase (true U/U3) */
  function addStairs(g, plan, z0, rise, M) {
    for (const s of (plan.stairs || [])) {
      const alongX = (s.run_axis || "x") === "x";
      const W = alongX ? s.w : s.h;
      const B = alongX ? s.h : s.w;
      const typ = s.type || "straight";
      const dirUp = (s.up_from === "left" || s.up_from === "bottom") ? 1 : -1;
      const stepBox = (u, v, du, dv, zTop, hZ) => {
        const cx = alongX ? s.x + u + du / 2 : s.x + v + dv / 2;
        const cy = alongX ? s.y + v + dv / 2 : s.y + u + du / 2;
        g.add(box(alongX ? du : dv, alongX ? dv : du, hZ, cx, cy, zTop - hZ / 2, M.step));
      };
      const flight = (u0, len, sign, v0, bw, zlo, zhi, n) => {
        n = Math.max(2, n | 0);
        const tr = len / n, rs = (zhi - zlo) / n;
        for (let i = 0; i < n; i++) {
          const zTop = zlo + (i + 1) * rs;
          const uu = sign > 0 ? u0 + i * tr : u0 - (i + 1) * tr;
          stepBox(uu, v0, tr, bw, zTop, Math.min(zTop - z0 + 0.01, rs * 2.2));
        }
      };
      const landing = (u0, len, v0, bw, zlv) =>
        stepBox(u0, v0, len, bw, zlv, 0.5);
      // HANDRAIL along the well side of a flight: posts + a sloped top rail
      const rail = (uA, uB, vEdge, zA, zB) => {
        const railH = 3.0;
        const P1 = alongX ? [s.x + uA, s.y + vEdge] : [s.x + vEdge, s.y + uA];
        const P2 = alongX ? [s.x + uB, s.y + vEdge] : [s.x + vEdge, s.y + uB];
        const top = cylBetween(P1[0], P1[1], zA + railH, P2[0], P2[1], zB + railH,
          0.07, M.rail || M.step);
        if (top) g.add(top);
        const nP = Math.max(2, Math.round(Math.hypot(uB - uA, 0) / 2.5) + 1);
        for (let i = 0; i < nP; i++) {
          const t2 = i / (nP - 1);
          const px = P1[0] + (P2[0] - P1[0]) * t2, py = P1[1] + (P2[1] - P1[1]) * t2;
          const pz = zA + (zB - zA) * t2;
          const p = cylBetween(px, py, pz, px, py, pz + railH, 0.045, M.rail || M.step);
          if (p) g.add(p);
        }
      };

      if (typ === "U" || typ === "U3" || typ === "L") {
        // EXACTLY the plan's arrangement: flight 1 in the TOP band, both
        // landings stacked at the FAR (landing) end, the U3's middle flight
        // running DOWN the landing column between them, the return flight in
        // the BOTTOM band — and an OPEN WELL in the middle, never solid.
        const land = Math.min(Math.max(+s.landing_size || 3, 2.5), W * 0.45);
        const runLen = W - land;
        const n1 = +s.steps_f1 || 8, n2 = +s.steps_f2 || n1;
        const nm = typ === "U3" ? Math.max(1, +s.steps_f3 || 2) : 0;
        const fw2 = nm > 0 ? Math.min(4.0, B * 0.34) : B / 2;   // band width
        const tot = Math.max(1, n1 + n2 + nm);
        const z1 = z0 + rise * n1 / tot;
        const z2 = z0 + rise * (n1 + nm) / tot;
        const vTop = B - fw2, vBot = 0;
        const uNear = dirUp > 0 ? 0 : W;
        const uFarL = dirUp > 0 ? runLen : 0;        // landing column start (u)
        // flight 1 — top band, near → far
        flight(uNear, runLen, dirUp, vTop, fw2, z0, z1, n1);
        rail(uNear, dirUp > 0 ? runLen : land, vTop + 0.08, z0, z1);
        // landing 1 — far end, TOP corner
        landing(uFarL, land, vTop, fw2, z1);
        if (nm > 0) {
          // middle flight: DOWN the landing column from the top landing to the
          // bottom landing (across the well span), exactly as drawn
          const span = vTop - fw2;                   // between the two landings
          for (let i = 0; i < nm; i++) {
            const zTop = z1 + (z2 - z1) * (i + 1) / nm;
            stepBox(uFarL, vTop - (i + 1) * (span / nm), land, span / nm,
              zTop, Math.min(zTop - z0 + 0.01, ((z2 - z1) / nm) * 2.2));
          }
          rail(dirUp > 0 ? W - 0.15 : 0.15, dirUp > 0 ? W - 0.15 : 0.15,
            vTop, z1, z2);
        }
        // landing 2 — far end, BOTTOM corner
        landing(uFarL, land, vBot, fw2, z2);
        // return flight — bottom band, far → near
        flight(dirUp > 0 ? runLen : land, runLen, -dirUp, vBot, fw2, z2, z0 + rise, n2);
        rail(dirUp > 0 ? runLen : land, uNear, fw2 - 0.08, z2, z0 + rise);
      } else {
        flight(dirUp > 0 ? 0 : W, W, dirUp, 0, B, z0, z0 + rise,
          Math.max(8, +s.steps_f1 || 15));
      }
    }
  }

  /* ------------------------- furniture: DETAILED little models, not boxes */
  const lam = c => new THREE.MeshLambertMaterial({ color: c });
  function addFurniture(g, plan, z0) {
    for (const f of (plan.furniture || [])) {
      const w = +f.w || 1, h = +f.h || 1;
      const cx = (+f.x || 0) + w / 2, cy = (+f.y || 0) + h / 2;
      const grp = new THREE.Group();
      // local frame: piece centred at origin, x = its w, y(plan) = its h.
      // `bk` = which local side its BACK is on (facing = the wall side).
      const bk = f.facing || "N";
      const back = { N: [0, 1], S: [0, -1], E: [1, 0], W: [-1, 0] }[bk] || [0, 1];
      const lb = (sx, sy, sz, ox, oy, oz, mat) => {
        const m = new THREE.Mesh(new THREE.BoxGeometry(sx, sz, sy), mat);
        m.position.set(ox, oz, -oy);
        grp.add(m); return m;
      };
      const lc = (r, hz, ox, oy, oz, mat) => {
        const m = new THREE.Mesh(new THREE.CylinderGeometry(r, r, hz, 14), mat);
        m.position.set(ox, oz, -oy);
        grp.add(m); return m;
      };
      const legs = (sw, sh, hz, mat) => {
        for (const p of [[-1, -1], [1, -1], [-1, 1], [1, 1]])
          lb(0.15, 0.15, hz, p[0] * (sw / 2 - 0.15), p[1] * (sh / 2 - 0.15), hz / 2, mat);
      };
      const k = f.kind || "";

      if (k.startsWith("bed_")) {
        const wood = lam(0x7a5c3e), matt = lam(0xdfe6ee), quilt = lam(0x6f9fd8),
          pil = lam(0xf5f0e6);
        lb(w, h, 1.1, 0, 0, 0.55, wood);                          // base
        lb(w - 0.25, h - 0.25, 0.55, 0, 0, 1.35, matt);           // mattress
        // quilt covers the FOOT two-thirds; pillows at the HEAD (back side)
        lb(w - 0.35, h * 0.62, 0.18, -back[0] * w * 0.17, -back[1] * h * 0.17, 1.72, quilt);
        const px = back[0], py = back[1];
        const across = Math.abs(px) > 0 ? h : w;
        for (const s of (across > 4 ? [-1, 1] : [0]))
          lb(px ? 0.5 : 1.5, px ? 1.5 : 0.5, 0.28,
            px * (w / 2 - 0.55) + (px ? 0 : s * 1.1),
            py * (h / 2 - 0.55) + (py ? 0 : s * 1.1), 1.78, pil);
        lb(px ? 0.18 : w, px ? h : 0.18, 2.9,                     // headboard
          px * (w / 2 - 0.09), py * (h / 2 - 0.09), 1.45, wood);
      } else if (k.startsWith("sofa") || k === "armchair") {
        const body = lam(0x3f8f6d), cush = lam(0x59a583), wood = lam(0x5a4632);
        lb(w, h, 1.05, 0, 0, 0.7, body);                          // seat base
        const px = back[0], py = back[1];
        lb(px ? 0.5 : w, px ? h : 0.5, 1.6,                       // back rest
          px * (w / 2 - 0.25), py * (h / 2 - 0.25), 1.6, body);
        const ax = py, ay = px;                                    // arms across
        for (const s of [-1, 1])
          lb(Math.abs(ax) ? 0.45 : w, Math.abs(ay) ? 0.45 : h, 0.75,
            s * ax * (w / 2 - 0.22), s * ay * (h / 2 - 0.22), 1.6, body);
        // seat cushions
        const n = k === "sofa_3" ? 3 : (k === "sofa_2" ? 2 : 1);
        const runW = Math.abs(px) ? h : w;
        for (let i = 0; i < n; i++) {
          const off = -runW / 2 + runW * (i + 0.5) / n;
          lb(Math.abs(px) ? w * 0.55 : runW / n - 0.2,
            Math.abs(px) ? runW / n - 0.2 : h * 0.55, 0.3,
            Math.abs(px) ? -px * w * 0.12 + 0 : off,
            Math.abs(px) ? off : -py * h * 0.12, 1.4, cush);
        }
        legs(w, h, 0.35, wood);
      } else if (k === "chair" || k === "stool") {
        const wood = lam(0x82603f);
        lb(w * 0.85, h * 0.85, 0.18, 0, 0, 1.45, wood);
        legs(w, h, 1.4, wood);
        if (k === "chair")
          lb(back[0] ? 0.15 : w * 0.85, back[0] ? h * 0.85 : 0.15, 1.5,
            back[0] * (w / 2 - 0.1), back[1] * (h / 2 - 0.1), 2.2, wood);
      } else if (k.startsWith("dining") || k === "coffee_table" ||
                 k === "study_table" || k === "dresser") {
        const wood = lam(k === "coffee_table" ? 0xa5824f : 0x8a6a42);
        const top = k === "coffee_table" ? 1.35 : 2.45;
        lb(w, h, 0.18, 0, 0, top, wood);
        legs(w, h, top - 0.09, lam(0x6b4f30));
        if (k === "dresser")                                       // mirror
          lb(back[0] ? 0.1 : w * 0.7, back[0] ? h * 0.7 : 0.1, 2.2,
            back[0] * (w / 2 - 0.06), back[1] * (h / 2 - 0.06), top + 1.2,
            lam(0xb8d4e8));
      } else if (k === "wardrobe" || k === "sideboard" || k === "shoe_rack") {
        const hgt = k === "wardrobe" ? 6.6 : (k === "sideboard" ? 2.8 : 3.2);
        const body = lam(0x77573a), panel = lam(0x8a6844);
        lb(w, h, hgt, 0, 0, hgt / 2, body);
        // SHUTTERS at the standard 450–500 mm module: an 8'-6" wardrobe gets
        // 5–6 doors, never just 2. Handles pair up at the meeting stiles.
        const fx = -back[0], fy = -back[1];
        const runW = Math.abs(fx) ? h : w;
        const nSh = Math.max(2, Math.round(runW / 1.55));   // ≈ 475 mm module
        const shW = runW / nSh;
        for (let i2 = 0; i2 < nSh; i2++) {
          const off = -runW / 2 + shW * (i2 + 0.5);
          lb(Math.abs(fx) ? 0.06 : shW - 0.12,
            Math.abs(fx) ? shW - 0.12 : 0.06, hgt - 0.2,
            fx * (w / 2 + 0.03) + (Math.abs(fx) ? 0 : off),
            fy * (h / 2 + 0.03) + (Math.abs(fy) ? 0 : off),
            hgt / 2, panel);
          // handle near the meeting edge, alternating so pairs face each other
          const hOff = off + (i2 % 2 === 0 ? 1 : -1) * (shW / 2 - 0.18);
          lc(0.045, 0.8, fx * (w / 2 + 0.1) + (Math.abs(fx) ? 0 : hOff),
            fy * (h / 2 + 0.1) + (Math.abs(fy) ? 0 : hOff),
            hgt * 0.5, lam(0x2e2e2e));
        }
      } else if (k === "tv_unit") {
        lb(w, h, 1.5, 0, 0, 0.75, lam(0x4a4f58));                 // cabinet
        lb(back[0] ? 0.15 : w * 0.8, back[0] ? h * 0.8 : 0.15, 2.4, // screen
          back[0] * (w / 2 - 0.2), back[1] * (h / 2 - 0.2), 2.8, lam(0x14161a));
      } else if (k === "fridge") {
        lb(w, h, 5.6, 0, 0, 2.8, lam(0xd6dade));
        const fx = -back[0], fy = -back[1];
        lb(Math.abs(fx) ? 0.06 : w, Math.abs(fx) ? h : 0.06, 0.06 + 0,
          fx * (w / 2 + 0.03), fy * (h / 2 + 0.03), 3.7, lam(0xb9bec4));
        lc(0.05, 1.4, fx * (w / 2 + 0.12), fy * (h / 2 + 0.12), 4.2, lam(0x7d838b));
      } else if (k === "counter") {
        lb(w, h, 2.7, 0, 0, 1.35, lam(0x9aa3ad));                 // carcass
        lb(w, h, 0.15, 0, 0, 2.82, lam(0x3c4046));                // granite top
        const alongX2 = w >= h;
        const runW = alongX2 ? w : h;
        if (runW > 4.5) {
          const sinkAt = -runW / 2 + runW * 0.25, hobAt = -runW / 2 + runW * 0.7;
          lb(alongX2 ? 1.6 : w * 0.6, alongX2 ? h * 0.6 : 1.6, 0.12,
            alongX2 ? sinkAt : 0, alongX2 ? 0 : sinkAt, 2.92, lam(0xc9d2da));
          for (const o of [[-0.45, -0.35], [0.45, -0.35], [-0.45, 0.35], [0.45, 0.35]])
            lc(0.22, 0.08, (alongX2 ? hobAt : 0) + o[0],
              (alongX2 ? 0 : hobAt) + o[1], 2.95, lam(0x1d1f24));
        }
      } else if (k === "wc") {
        lb(back[0] ? 0.6 : w, back[0] ? h : 0.6, 1.9,             // cistern
          back[0] * (w / 2 - 0.3), back[1] * (h / 2 - 0.3), 0.95, lam(0xf0f2f5));
        const m2 = new THREE.Mesh(new THREE.CylinderGeometry(0.62, 0.5, 1.3, 16),
          lam(0xf0f2f5));
        m2.scale.set(1, 1, 1.35);
        m2.position.set(-back[0] * (w / 4), 0.65, back[1] * (h / 4));
        grp.add(m2);
      } else if (k === "basin") {
        lc(0.16, 2.2, 0, 0, 1.1, lam(0xe6e9ed));                  // pedestal
        const bowl = lc(0.75, 0.4, 0, 0, 2.5, lam(0xf3f5f8));
        bowl.scale.set(Math.max(0.6, w / 1.6), 1, Math.max(0.6, h / 1.6));
      } else if (k === "shower") {
        const glass = new THREE.MeshLambertMaterial({
          color: 0xbfe0f2, transparent: true, opacity: 0.3 });
        lb(w, 0.06, 6.6, 0, -h / 2 + 0.03, 3.3, glass);
        lb(w, 0.06, 6.6, 0, h / 2 - 0.03, 3.3, glass);
        lb(0.06, h, 6.6, -w / 2 + 0.03, 0, 3.3, glass);
        lb(0.06, h, 6.6, w / 2 - 0.03, 0, 3.3, glass);
        lb(w, h, 0.12, 0, 0, 0.06, lam(0xcdd6dd));                // tray
        lc(0.06, 1.1, back[0] * (w / 2 - 0.3), back[1] * (h / 2 - 0.3), 6.0,
          lam(0x8f979f));
        lc(0.3, 0.08, back[0] * (w / 2 - 0.3) - back[0] * 0.4,
          back[1] * (h / 2 - 0.3) - back[1] * 0.4, 6.5, lam(0xaab2ba)); // rose
      } else if (k === "bedside") {
        lb(w, h, 1.7, 0, 0, 0.85, lam(0x846444));
        lc(0.14, 0.5, 0, 0, 2.05, lam(0xd9c27a));                 // little lamp
        lc(0.32, 0.4, 0, 0, 2.45, lam(0xf2e3b2));
      } else {
        lb(w, h, 2.2, 0, 0, 1.1, lam(0xb8a88f));
      }

      if (+f.angle) grp.rotation.y = (+f.angle) * Math.PI / 180;
      grp.position.set(cx, z0, -cy);
      grp.userData.edit = { kind: "furn", ref: f, plan };
      g.add(grp);
    }
  }

  /* ---------------------------------------------- plumbing pipes in 3D */
  const PIPE3D = { CW: 0x0d47a1, HW: 0xd32f2f, SOIL: 0xe8590c, WASTE: 0x2e9e2e,
    VENT: 0x1b8a3a, STORM: 0x00acc1, ACD: 0xad1457 };
  const STACK3D = { SS: 0xe8590c, WS: 0x2e9e2e, VP: 0x1b8a3a, RWP: 0x00acc1,
    CWD: 0x0d47a1, HWD: 0xd32f2f };
  function addPipes(g, plan, z0, fh) {
    // MEP: DRAINAGE is UNDERFLOOR (sunk / screed / underground, on its code
    // fall); WATER SUPPLY runs HIGH at ceiling level, concealed, dropping
    // down the wall only at tap points. X-ray sliders make both readable.
    const rooms = plan.rooms || [];
    const wet = rooms.filter(r =>
      /toilet|bath|w\.?c|wash/i.test(r.name || ""));
    const inWet = (x, y) => wet.some(r =>
      x >= r.x - 0.6 && x <= r.x + r.w + 0.6 &&
      y >= r.y - 0.6 && y <= r.y + r.h + 0.6);
    const inRoom = (x, y) => rooms.some(r => !r.void &&
      x >= r.x - 0.1 && x <= r.x + r.w + 0.1 &&
      y >= r.y - 0.1 && y <= r.y + r.h + 0.1);
    // MEP levels — DRAINAGE: wet rooms in the SUNK, dry rooms just under the
    // FFL screed, and OUTSIDE the footprint UNDERGROUND to the chambers.
    // WATER SUPPLY is the opposite: it runs HIGH at ceiling / lintel level,
    // concealed, and only DROPS DOWN THE WALL at the tap points.
    const baseAt = (x, y) =>
      inWet(x, y) ? z0 - 0.25 : (inRoom(x, y) ? z0 - 0.12 : -0.2);
    const tapRooms = rooms.filter(r =>
      /toilet|bath|w\.?c|wash|kitchen/i.test(r.name || ""));
    const inTap = (x, y) => tapRooms.some(r =>
      x >= r.x - 0.6 && x <= r.x + r.w + 0.6 &&
      y >= r.y - 0.6 && y <= r.y + r.h + 0.6);
    // code gradients (same 1:N the 2D writes on every run) — the pipes are
    // actually PLACED on that fall, dropping continuously toward the outfall
    const SLOPE3D = { SOIL: 40, WASTE: 40, STORM: 100, ACD: 50 };
    // each drainage SYSTEM owns its own LEVEL BAND — the deep soil main at
    // the bottom, waste above it, storm above that — so two crossing runs
    // NEVER pass through each other; branches step DOWN into the main via
    // the connector, exactly how the levels work on site
    // each drainage SYSTEM owns an EXCLUSIVE depth band with a clear gap
    // between bands: the deep soil main at the bottom, waste above it, storm
    // above that. A run is clamped INSIDE its own band, so two systems can
    // never end up sharing a level however long the fall runs.
    // dz is measured from the FLOOR of this storey, and the gap between two
    // bands (0.55 ft = 168 mm) is wider than the fattest pipe, so a crossing
    // always shows daylight between the two runs.
    const SYS_BAND = {                  // { top of band, max fall inside band }
      SOIL:  { dz: -2.24, drop: 0.20 },   // deepest: the soil main
      WASTE: { dz: -1.26, drop: 0.18 },   // above it: waste
      STORM: { dz: -0.30, drop: 0.16 },   // shallowest: rainwater
    };
    // turn angle at vertex i - a fitting belongs only on a real change of
    // direction; a straight continuation gets no ball
    const turnAt = (P, i) => {
      const ax = P[i][0] - P[i - 1][0], ay = P[i][1] - P[i - 1][1];
      const bx = P[i + 1][0] - P[i][0], by = P[i + 1][1] - P[i][1];
      const la = Math.hypot(ax, ay) || 1e-9, lb = Math.hypot(bx, by) || 1e-9;
      return Math.acos(Math.max(-1, Math.min(1, (ax * bx + ay * by) / (la * lb))));
    };
    const fitR = r => Math.min(r * 1.06, r + 0.022);   // slim fittings, no blobs
    // ONE fitting per physical point: an elbow, a socket and a joint ball all
    // landing on the same corner used to pile up into a big blob
    const fitSeen = new Set();
    const addFit = (gr, x, y, z, rr, mat) => {
      const k = Math.round(x * 12) + "|" + Math.round(y * 12) + "|" + Math.round(z * 12);
      if (fitSeen.has(k)) return;
      fitSeen.add(k);
      const j = new THREE.Mesh(new THREE.SphereGeometry(rr, 10, 10), mat);
      j.position.set(x, z, -y);
      gr.add(j);
    };
    // ---- LATERAL LANES: besides its depth band every system runs in its own
    // side lane, so parallel services sit SIDE BY SIDE like a real services
    // drawing instead of stacking one over the other. Corners are mitred so
    // an offset run stays continuous.
    const LANE = { SOIL: 0, WASTE: 0.62, STORM: 1.24,
      CW: 0, HW: 0.5, VENT: 1.0, ACD: 1.5 };
    const offsetPoly = (P, off) => {
      if (!off) return P.map(p => [p[0], p[1]]);
      const n = P.length, Q = [];
      const perp = (a, b) => {
        const dx = b[0] - a[0], dy = b[1] - a[1], L = Math.hypot(dx, dy) || 1e-9;
        return [-dy / L, dx / L];
      };
      for (let i = 0; i < n; i++) {
        let d;
        if (i === 0) d = perp(P[0], P[1]);
        else if (i === n - 1) d = perp(P[n - 2], P[n - 1]);
        else {
          const a = perp(P[i - 1], P[i]), b = perp(P[i], P[i + 1]);
          let mx = a[0] + b[0], my = a[1] + b[1];
          const L = Math.hypot(mx, my);
          if (L < 1e-6) d = a;
          else {
            const c = Math.abs((a[0] * mx + a[1] * my) / L);   // cos half-angle
            const sc = Math.max(0.4, c);
            d = [mx / L / sc, my / L / sc];                    // mitred corner
          }
        }
        Q.push([P[i][0] + d[0] * off, P[i][1] + d[1] * off]);
      }
      return Q;
    };
    const drains = [];             // drawn drainage runs, for the joins pass
    const supplies = [];           // drawn CW / HW runs, for their joins pass
    // A system band is not enough: two runs of the SAME system used to share
    // one lane, so parallel runs sat inside each other. Now every run that
    // would actually clash with an earlier one takes the next free SUB-LANE
    // (greedy colouring) — runs that do not clash stay exactly where they
    // belong, so the drawing stays tight instead of fanning out.
    const seg2d = (p1, q1, p2, q2) => {
      const ux = q1[0] - p1[0], uy = q1[1] - p1[1];
      const vx = q2[0] - p2[0], vy = q2[1] - p2[1];
      const wx = p1[0] - p2[0], wy = p1[1] - p2[1];
      const a = ux * ux + uy * uy, b = ux * vx + uy * vy, c = vx * vx + vy * vy;
      const d = ux * wx + uy * wy, e = vx * wx + vy * wy, D = a * c - b * b;
      let sc, tc;
      if (D < 1e-9) { sc = 0; tc = (b > c ? d / b : e / c); }
      else { sc = (b * e - c * d) / D; tc = (a * e - b * d) / D; }
      sc = Math.max(0, Math.min(1, sc)); tc = Math.max(0, Math.min(1, tc));
      return Math.hypot(wx + sc * ux - tc * vx, wy + sc * uy - tc * vy);
    };
    const runsClash = (A, B) => {
      for (let i = 0; i < A.length - 1; i++)
        for (let j = 0; j < B.length - 1; j++)
          if (seg2d(A[i], A[i + 1], B[j], B[j + 1]) < 1.3) return true;
      return false;
    };
    const laneIdx = new Map(), bySys = {};
    (plan.pipes || []).forEach(r => { (bySys[r.system] = bySys[r.system] || []).push(r); });
    for (const sys in bySys) {
      const list = bySys[sys];
      for (let i = 0; i < list.length; i++) {
        const used = new Set();
        for (let j = 0; j < i; j++)
          if (runsClash(list[i].pts || [], list[j].pts || []))
            used.add(laneIdx.get(list[j]));
        let k = 0; while (used.has(k)) k++;
        laneIdx.set(list[i], k);
      }
    }
    // 0, +0.42, -0.42, +0.84 … — alternating, so a group stays centred and the
    // spacing is always wider than the fattest pipe
    const subLane = k => (k ? (k % 2 ? 1 : -1) * Math.ceil(k / 2) * 0.55 : 0);
    for (const r of (plan.pipes || [])) {
      const P0 = r.pts || []; if (P0.length < 2) continue;
      const lk = laneIdx.get(r) || 0;      // clash colour: lane AND level
      const sub = subLane(lk);             // its own clash-free side lane
      const P = offsetPoly(P0, (LANE[r.system] || 0) + sub);
      const col = PIPE3D[r.system] || 0x888888;
      const mat = new THREE.MeshLambertMaterial({ color: col });
      const dia = +r.dia_mm || 50;
      const rad = Math.max(0.08, (dia * MM) / 2);
      let sN = SLOPE3D[r.system] || 0;
      if (r.system === "WASTE" && dia < 75) sN = 30;
      const fall = sN ? 1 / sN : 0;            // supply runs stay level
      const cum = [0];
      for (let i = 1; i < P.length; i++)
        cum[i] = cum[i - 1] + Math.hypot(P[i][0] - P[i - 1][0], P[i][1] - P[i - 1][1]);
      const rg = new THREE.Group();            // whole run = ONE editable thing
      rg.userData.edit = { kind: "pipe", ref: r, plan };
      const supply = (r.system === "CW" || r.system === "HW");
      const isACD = r.system === "ACD";
      if (supply || r.system === "VENT" || isACD) {
        // HIGH-LEVEL runs: supply + vent at ceiling / lintel height; the AC
        // CONDENSATE line also runs along the ceiling from the unit, on a
        // continuous 1:50 fall, and only drops down OUTSIDE to the drain
        // each high-level system gets its OWN band: cold lowest, hot above
        // it, vent above that — parallel runs never merge into one another
        const zBase = (isACD ? z0 + 7.1
          : r.system === "HW" ? z0 + fh - 1.05
          : r.system === "VENT" ? z0 + fh - 0.50
          : z0 + fh - 1.62) - lk * 0.17;    // clashing runs step clear too
        const fHi = isACD ? 1 / 50 : 0;
        for (let i = 0; i < P.length - 1; i++) {
          const zA = zBase - cum[i] * fHi, zB = zBase - cum[i + 1] * fHi;
          const c = cylBetween(P[i][0], P[i][1], zA, P[i + 1][0], P[i + 1][1], zB, rad, mat);
          if (c) rg.add(c);
          if (i > 0 && turnAt(P, i) > 0.26) {
            addFit(rg, P[i][0], P[i][1], zA, fitR(rad), mat);
          }
        }
        if (supply) {
          const ends = [P[0], P[P.length - 1]].filter(e => inTap(e[0], e[1]));
          for (const e of (ends.length ? ends : [P[P.length - 1]])) {
            const d = cylBetween(e[0], e[1], zBase, e[0], e[1], z0 + 1.5, rad * 0.9, mat);
            if (d) rg.add(d);                  // down the wall chase to the tap
          }
        }
        if (isACD) {
          const e = P[P.length - 1];
          const ze = zBase - cum[P.length - 1] * fHi;
          if (!inRoom(e[0], e[1])) {           // outfall: down the outer face
            const d = cylBetween(e[0], e[1], ze, e[0], e[1], 0.05, rad * 0.9, mat);
            if (d) rg.add(d);
          }
        }
        if (supply) supplies.push({ P, z: zBase, rad, mat, sys: r.system, dia });
        g.add(rg);
        continue;
      }
      const zs = [];                           // per-vertex levels (for joins)
      let prevZ = null;
      // within a system the SMALLER branch rides slightly higher than the
      // bigger main, so same-colour crossings clear each other too
      const band = SYS_BAND[r.system] || { dz: -1.26, drop: 0.18 };
      // inside its own band a SMALLER branch rides above the bigger main, so
      // two runs of the same system clear each other as well (max 0.10 ft,
      // which is what the band header leaves free)
      const sysDz = band.dz + (0.26 - Math.min(0.26, rad)) / 0.18 * 0.06
        + (lk % 4) * 0.34;              // clashing runs step clear too
      for (let i = 0; i < P.length - 1; i++) {
        const b = z0 + sysDz;
        // never deeper than just under the ground — long falls are capped
        const zA = Math.max(b - band.drop, b - cum[i] * fall);
        const zB = Math.max(b - band.drop, b - cum[i + 1] * fall);
        if (i === 0) zs[0] = zA;
        zs[i + 1] = zB;
        const c = cylBetween(P[i][0], P[i][1], zA, P[i + 1][0], P[i + 1][1], zB, rad, mat);
        if (c) rg.add(c);
        if (prevZ !== null && Math.abs(prevZ - zA) > 0.02) {
          const v = cylBetween(P[i][0], P[i][1], prevZ, P[i][0], P[i][1], zA, rad, mat);
          if (v) rg.add(v);                    // level change at the zone edge
        }
        // joint ball only where the run actually turns
        if (i > 0 && turnAt(P, i) > 0.26) {
          addFit(rg, P[i][0], P[i][1], zA, fitR(rad), mat);
        }
        prevZ = zB;
      }
      g.add(rg);
      drains.push({ P, zs, dia, rad, mat, sys: r.system });
    }
    // ------- DRAINAGE CONNECTIVITY: every smaller pipe TIES INTO the bigger
    // main (or the stack) with a proper TEE connector — no floating ends
    const closestOnSeg = (p, a, b) => {
      const vx = b[0] - a[0], vy = b[1] - a[1];
      const L2 = vx * vx + vy * vy || 1e-9;
      let t = ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / L2;
      t = Math.max(0, Math.min(1, t));
      return [a[0] + vx * t, a[1] + vy * t, t];
    };
    const stacksXY = (plan.plumb || []).filter(p =>
      p.code === "SS" || p.code === "WS" || p.code === "RWP");
    const tied = new Set();          // junctions already fitted, no doubling
    for (const a of drains) {
      const endIdx = [0, a.P.length - 1];
      for (const ei of endIdx) {
        const e = a.P[ei], ez = a.zs[ei];
        // nearest STACK first — a branch always prefers its stack
        let best = null;
        for (const s of stacksXY) {
          const d = Math.hypot(s.x - e[0], s.y - e[1]);
          if (d > 0.25 && d < 2.2 && (!best || d < best.d))
            best = { d, x: s.x, y: s.y, z: ez, stack: true };
        }
        if (!best) {
          // else the nearest BIGGER (or equal) main line
          for (const b of drains) {
            if (b === a || b.dia < a.dia) continue;
            for (let k = 0; k < b.P.length - 1; k++) {
              const cp = closestOnSeg(e, b.P[k], b.P[k + 1]);
              const d = Math.hypot(cp[0] - e[0], cp[1] - e[1]);
              if (d < 0.25 || d > 3.5) continue;
              const z = b.zs[k] + (b.zs[k + 1] - b.zs[k]) * cp[2];
              if (!best || d < best.d)
                best = { d, x: cp[0], y: cp[1], z, b, k };
            }
          }
        }
        if (!best) continue;
        // ONE connector per junction - if another branch already tied in at
        // (almost) this point, don't stack a second set of fittings on it
        const key = Math.round(e[0] * 4) + "|" + Math.round(e[1] * 4);
        if (tied.has(key)) continue;
        tied.add(key);
        // L-SHAPE, never a diagonal: run HORIZONTAL at the branch level up to
        // the main, then DROP VERTICALLY into the tee - the way it is actually
        // laid on site, and it keeps the crossings readable in 3D
        const h = cylBetween(e[0], e[1], ez, best.x, best.y, ez, a.rad, a.mat);
        if (h) g.add(h);
        if (Math.abs(ez - best.z) > 0.02) {
          const v = cylBetween(best.x, best.y, ez, best.x, best.y, best.z, a.rad, a.mat);
          if (v) g.add(v);
          addFit(g, best.x, best.y, ez, fitR(a.rad), a.mat);   // elbow at top of drop
        }
        // connector fittings: a socket on the branch, a TEE boss on the main
        addFit(g, e[0], e[1], ez, fitR(a.rad), a.mat);        // socket on the branch
        if (best.stack) {
          const ring = new THREE.Mesh(
            new THREE.TorusGeometry(a.rad + 0.05, 0.035, 8, 14), a.mat);
          ring.rotation.x = Math.PI / 2;
          ring.position.set(best.x, best.z, -best.y);
          g.add(ring);
        } else {
          const bb = best.b, k = best.k;
          const ux = bb.P[k + 1][0] - bb.P[k][0], uy = bb.P[k + 1][1] - bb.P[k][1];
          const L = Math.hypot(ux, uy) || 1;
          const tee = cylBetween(best.x - ux / L * 0.18, best.y - uy / L * 0.18, best.z,
            best.x + ux / L * 0.18, best.y + uy / L * 0.18, best.z,
            fitR(bb.rad), bb.mat);
          if (tee) g.add(tee);
        }
      }
    }
    // ------- WATER SUPPLY CONNECTIVITY. Only DRAINAGE had a joins pass, so a
    // CW / HW branch simply STOPPED IN MID AIR. Every supply run now ties
    // into its own DOWNTAKE STACK (CW -> CWD, HW -> HWD, never the other
    // one), or failing that into the nearest bigger main of the SAME system,
    // with an L-shape - horizontal at branch level, then the riser - and a
    // tee, exactly like the drainage side.
    const downtakes = (plan.plumb || []).filter(p =>
      p.code === "CWD" || p.code === "HWD");
    const WANT = { CW: "CWD", HW: "HWD" };
    for (const a of supplies) {
      for (const ei of [0, a.P.length - 1]) {
        const e = a.P[ei];
        if (inTap(e[0], e[1])) continue;     // that end already drops to a tap
        let best = null;
        for (const st of downtakes) {
          if (st.code !== WANT[a.sys]) continue;   // hot never joins the cold main
          const d = Math.hypot(st.x - e[0], st.y - e[1]);
          if (d > 0.2 && d < 3.0 && (!best || d < best.d))
            best = { d, x: st.x, y: st.y, stack: true };
        }
        if (!best) {
          for (const b of supplies) {
            if (b === a || b.sys !== a.sys || b.dia < a.dia) continue;
            for (let k = 0; k < b.P.length - 1; k++) {
              const cp = closestOnSeg(e, b.P[k], b.P[k + 1]);
              const d = Math.hypot(cp[0] - e[0], cp[1] - e[1]);
              if (d < 0.2 || d > 3.5) continue;
              if (!best || d < best.d) best = { d, x: cp[0], y: cp[1], b };
            }
          }
        }
        if (!best) continue;
        const h = cylBetween(e[0], e[1], a.z, best.x, best.y, a.z, a.rad, a.mat);
        if (h) g.add(h);                     // horizontal leg to the main
        if (best.stack) {                    // riser into the downtake band
          const v = cylBetween(best.x, best.y, a.z,
            best.x, best.y, z0 + fh - 0.9, a.rad, a.mat);
          if (v) g.add(v);
        } else if (Math.abs(a.z - best.b.z) > 0.02) {
          const v = cylBetween(best.x, best.y, a.z,
            best.x, best.y, best.b.z, a.rad, a.mat);
          if (v) g.add(v);
        }
        addFit(g, e[0], e[1], a.z, fitR(a.rad), a.mat);           // socket
        addFit(g, best.x, best.y, a.z, fitR(a.rad), a.mat);       // tee / elbow
      }
    }
    // vertical STACKS / downtakes: DOWN from the sunk to ground drainage —
    // a stack never rises above the floor it serves in this view
    for (const p of (plan.plumb || [])) {
      const sc = STACK3D[p.code];
      const sg = new THREE.Group();
      sg.userData.edit = { kind: "plumb", ref: p, plan };
      if (sc != null) {
        const mat = new THREE.MeshLambertMaterial({ color: sc });
        // each stack runs its OWN storey band: supply downtakes come from the
        // tank DOWN to the ceiling distribution; the vent rises above roof;
        // soil / waste / rain go from the sunk down to the drain — a water
        // pipe never dives into the drainage zone
        let zt, zb;
        if (p.code === "CWD" || p.code === "HWD") { zt = z0 + fh + 0.6; zb = z0 + fh - 0.9; }
        else if (p.code === "VP") { zt = z0 + fh + 1.0; zb = z0 - 0.25; }
        else if (p.code === "SS") { zt = z0 - 0.15; zb = -2.42; }
        else if (p.code === "WS") { zt = z0 - 0.15; zb = -1.52; }
        else { zt = z0 - 0.15; zb = -0.50; }
        const srad = Math.max(0.075,
          ((+p.dia_mm || (p.code === "SS" ? 110 : p.code === "VP" ? 75 : 63)) * MM) / 2);
        const st = cylBetween(p.x, p.y, zt, p.x, p.y, zb, srad, mat);
        if (st) sg.add(st);
        const clamp = new THREE.Mesh(new THREE.TorusGeometry(srad + 0.04, 0.03, 8, 14), mat);
        clamp.rotation.x = Math.PI / 2;
        clamp.position.set(p.x, (zt + zb) / 2, -p.y);
        sg.add(clamp);
      } else {
        // traps / chambers are FLUSH COVERS at floor (inside) or ground
        // (outside) level — never a raised box sitting in a doorway
        const mzTop = inRoom(p.x, p.y) ? z0 + 0.02 : 0.02;
        sg.add(box(0.9, 0.9, 0.08, p.x, p.y, mzTop,
          new THREE.MeshLambertMaterial({ color: 0x6d4c41 })));
        sg.add(box(0.62, 0.62, 0.03, p.x, p.y, mzTop + 0.05,
          new THREE.MeshLambertMaterial({ color: 0x4e372f })));
      }
      g.add(sg);
    }
  }

  /* ------------------------------------- electrical points + conduiting */
  function addElec(g, plan, z0, fh) {
    const ceil = z0 + fh - 0.15;
    const conduit = new THREE.MeshLambertMaterial({ color: 0xff8c1a });
    // a conduit can never drop THROUGH a window — if the vertical run at (x,y)
    // would cross a window on that wall, shift the drop beside the window
    // (0.5 ft clear of the jamb) and connect horizontally at the fitting level
    const windowDodge = (x, y, zLowAbs) => {
      for (const w of (plan.walls || [])) {
        const L = Math.hypot(w.x2 - w.x1, w.y2 - w.y1) || 1e-6;
        const ux = (w.x2 - w.x1) / L, uy = (w.y2 - w.y1) / L;
        const dx = x - w.x1, dy = y - w.y1;
        const t = dx * ux + dy * uy;
        const d = Math.abs(dx * -uy + dy * ux);
        if (d > 0.9 || t < -0.2 || t > L + 0.2) continue;
        for (const o of (plan.openings || [])) {
          if (o.wall_id !== w.id || !/win/i.test(o.type || "")) continue;
          const a = o.pos, b = o.pos + (o.width || 3);
          if (t < a - 0.3 || t > b + 0.3) continue;
          const sill = z0 + ((+o.sill_mm || 900) * MM);
          const head = sill + ((+o.height_mm || 1200) * MM);
          if (zLowAbs >= head) continue;        // run starts above the head — clear
          const tSide = (t - a < b - t) ? a - 0.5 : b + 0.5;
          const ts = Math.max(0.15, Math.min(L - 0.15, tSide));
          return { x: w.x1 + ux * ts, y: w.y1 + uy * ts };
        }
      }
      return null;
    };
    const byTag = {};
    (plan.elec || []).forEach(p => { if (p.tag) byTag[p.tag] = p; });
    // tags already wired through some board's controls list + tags a
    // room-fallback chain has claimed, so no fitting is looped twice
    const CTRL = new Set();
    (plan.elec || []).forEach(p =>
      (p.controls || []).forEach(t => CTRL.add(t)));
    const claimed = new Set();
    // ---- LOOPING COMES FROM THE DRAWING, not from a second guess here.
    // core/looping.py chains every switch inside ONE room (switch -> nearest
    // fitting -> next). The 3D used to re-chain a board's whole controls list
    // nearest-first, and the DB looped to EVERY board on the floor, so runs
    // wandered into the next room. Draw exactly what the 2D decided.
    // The conduit also runs IN THE SLAB now: `ceil` sits 0.15 under the slab,
    // which is INSIDE a 300 mm beam drop, so every ceiling run used to spear
    // straight through the beams. Cast-in conduit passes OVER them.
    const slab = z0 + fh + 0.10;
    const LOOPS = plan.elec_loops || [];
    // An older plan carries no elec_loops. Rather than fall back to the walk
    // that crossed rooms, derive the SAME rule here: per ROOM, per DUTY,
    // chained from the board nearest-first (core/looping.py GROUPS).
    const GROUPS3D = [
      ["General lighting", ["SL", "ASL", "PL", "CSL"]],
      ["Cove / profile", ["CV", "TR"]],
      ["Decorative", ["HL", "CH"]],
      ["Wall lights", ["WL"]],
      ["Bedside lights", ["BWL"]],
      ["Mirror light", ["ML"]],
      ["Step / foot", ["STL"]],
      ["Fan", ["CF"]],
      ["Exhaust", ["EF"]],
    ];
    const roomOf = (x, y) => (plan.rooms || []).find(r => !r.void &&
      x >= r.x - 0.1 && x <= r.x + r.w + 0.1 &&
      y >= r.y - 0.1 && y <= r.y + r.h + 0.1) || null;
    const GENERAL3D = "General lighting", BANK_MIN = 4, MAX_W = 800, MAX_PTS = 10;
    // farthest-point sampling: the alternate bank must still light the WHOLE
    // room, so its fittings are the ones furthest apart, not every other one
    function spreadPick(pts, m) {
      if (m >= pts.length) return pts.slice();
      const cx = pts.reduce((t, p) => t + p.x, 0) / pts.length;
      const cy = pts.reduce((t, p) => t + p.y, 0) / pts.length;
      const d2 = (p, q) => (p.x - q.x) * (p.x - q.x) + (p.y - q.y) * (p.y - q.y);
      let first = pts[0];
      for (const p of pts)
        if (d2(p, { x: cx, y: cy }) > d2(first, { x: cx, y: cy })) first = p;
      const chosen = [first], taken = new Set([pts.indexOf(first)]);
      while (chosen.length < m) {
        let bi = -1, bd = -1;
        pts.forEach((p, i) => {
          if (taken.has(i)) return;
          let near = Infinity;
          for (const ch of chosen) near = Math.min(near, d2(p, ch));
          if (near > bd) { bd = near; bi = i; }
        });
        if (bi < 0) break;
        chosen.push(pts[bi]); taken.add(bi);
      }
      return chosen;
    }
    function banks(duty, chain) {
      const n = chain.length;
      if (duty !== GENERAL3D || n < BANK_MIN) return [[duty, chain]];
      const m = Math.max(2, Math.round(n / 3));
      if (m >= n) return [[duty, chain]];
      const pick = new Set(spreadPick(chain, m));
      const alt = chain.filter(p => pick.has(p));
      const main = chain.filter(p => !pick.has(p));
      if (!alt.length || !main.length) return [[duty, chain]];
      return [[duty + " — main", main], [duty + " — alternate", alt]];
    }
    function splitRun(chain) {
      const runs = []; let cur = [], w = 0;
      for (const p of chain) {
        const pw = +p.watts || 0;
        if (cur.length && (cur.length + 1 > MAX_PTS || w + pw > MAX_W)) {
          runs.push(cur); cur = []; w = 0;
        }
        cur.push(p); w += pw;
      }
      if (cur.length) runs.push(cur);
      return runs;
    }
    function localLoops() {
      const byRoom = new Map();
      for (const q of (plan.elec || [])) {
        if (q.visible === false) continue;
        const rm = roomOf(q.x, q.y);
        if (!rm) continue;                 // nothing outside a room is looped
        if (!byRoom.has(rm)) byRoom.set(rm, []);
        byRoom.get(rm).push(q);
      }
      const out = [];
      for (const [rm, here] of byRoom) {
        const bd = here.find(q => q.code === "SB") || null;
        for (const [duty, codes] of GROUPS3D) {
          const todo = here.filter(q => codes.indexOf(q.code || "") >= 0);
          if (!todo.length) continue;
          const seq = [];
          let cur = bd || todo[0];
          while (todo.length) {            // nearest first, then nearest to that
            let bi = 0, bdist = 1e18;
            todo.forEach((q, k) => {
              const d = (q.x - cur.x) * (q.x - cur.x) + (q.y - cur.y) * (q.y - cur.y);
              if (d < bdist) { bdist = d; bi = k; }
            });
            const q = todo.splice(bi, 1)[0];
            seq.push({ x: q.x, y: q.y, tag: q.tag, code: q.code, watts: q.watts });
            cur = q;
          }
          // Rule 6 - general lighting splits into a MAIN and a smaller
          // ALTERNATE bank; Rule 4 - a run breaks at 800 W or 10 points. Each
          // resulting run is its OWN switch, its own loop, exactly as the
          // sheet draws it. Without this the whole room came out as one loop.
          for (const [label, bank] of banks(duty, seq))
            for (const run of splitRun(bank))
              out.push({ id: "", duty: label, room: rm.name, seq: run,
                board: bd ? { x: bd.x, y: bd.y, height_mm: bd.height_mm } : null });
        }
      }
      return out;
    }
    const CHAINS = LOOPS.length ? LOOPS : localLoops();
    // EVERY SWITCH IS ITS OWN LOOP. Drawn all at one level, in one colour, the
    // chains fused into a single web and the view read as "everything looped
    // together". The 2D sheet keeps them apart by bowing alternate chains
    // (engine.draw_elec_loops) and lettering S1, S2 - so do the same here:
    // each switch gets its OWN slab sub-level, its OWN bow direction and its
    // OWN shade, so you can trace one loop from its board to its last point.
    const LOOPTONE = [0xff8c1a, 0xffc247, 0xe0651a, 0xffa76b, 0xc4761f];
    const loopMat = LOOPTONE.map(c => new THREE.MeshLambertMaterial({ color: c }));
    CHAINS.forEach((s, ci) => {
      const seq = (s.seq || []).filter(q => q && isFinite(q.x) && isFinite(q.y));
      if (!seq.length) return;
      const zc = slab + (ci % 4) * 0.09;     // its own level inside the slab
      const bow = (ci % 2 === 0 ? 1 : -1) * (1 + (ci % 3) * 0.35);
      const mat = loopMat[ci % loopMat.length];
      const pts = [];
      if (s.board) {
        const hz = ((+s.board.height_mm || 1200) * MM);
        const dg = windowDodge(s.board.x, s.board.y, z0 + hz);
        const bx = dg ? dg.x : s.board.x, by = dg ? dg.y : s.board.y;
        if (dg) {
          const side = cylBetween(s.board.x, s.board.y, z0 + hz, bx, by, z0 + hz, 0.05, mat);
          if (side) g.add(side);
        }
        const up = cylBetween(bx, by, z0 + hz, bx, by, zc, 0.05, mat);
        if (up) g.add(up);                   // this switch's own riser
        pts.push([bx, by]);
      }
      seq.forEach(q => pts.push([q.x, q.y]));
      for (let i = 0; i < pts.length - 1; i++) {
        // one leg, bowed the way the 2D sheet bows it, so two chains sharing
        // a route stay traceable instead of lying on top of each other
        const A = pts[i], B = pts[i + 1];
        const L = Math.hypot(B[0] - A[0], B[1] - A[1]);
        if (L < 0.3) continue;
        const sag = Math.max(0.18, Math.min(0.9, L * 0.16)) * bow;
        const px = -(B[1] - A[1]) / L, py = (B[0] - A[0]) / L;
        const mx = (A[0] + B[0]) / 2 + px * sag, my = (A[1] + B[1]) / 2 + py * sag;
        let prev = A;
        for (let k = 1; k <= 6; k++) {       // quadratic bezier, same as the 2D
          const t = k / 6, u = 1 - t;
          const qx = u * u * A[0] + 2 * u * t * mx + t * t * B[0];
          const qy = u * u * A[1] + 2 * u * t * my + t * t * B[1];
          const c = cylBetween(prev[0], prev[1], zc, qx, qy, zc, 0.05, mat);
          if (c) g.add(c);
          prev = [qx, qy];
        }
      }
      for (const q of seq) {                 // drop out of the slab at the point
        const d = cylBetween(q.x, q.y, zc, q.x, q.y, ceil, 0.05, mat);
        if (d) g.add(d);
        const jb = new THREE.Mesh(new THREE.SphereGeometry(0.075, 8, 8), mat);
        jb.position.set(q.x, zc, -q.y);
        g.add(jb);                           // loop joint at the rose / box
      }
    });
    for (const p of (plan.elec || [])) {
      if (p.visible === false) continue;
      const code = p.code || "SL";
      if (code === "SB" || code === "DB") {          // board plate at its height
        const hz = ((+p.height_mm || 1200) * MM);
        const plate = box(0.8, 0.25, 0.5, p.x, p.y, z0 + hz, new THREE.MeshLambertMaterial({ color: 0xf5f2ea }));
        plate.userData.edit = { kind: "elec", ref: p, plan };
        g.add(plate);
        // the riser and the loop are drawn by the CHAINS pass above, which
        // follows the 2D drawing room by room. The DB is NOT looped to every
        // board any more - that was a lighting loop the drawing never had,
        // and it is what sent long runs across the whole floor.
      } else if (code === "CF") {                    // ceiling fan — one solid unit
        const fan = new THREE.Group();
        const grey = new THREE.MeshLambertMaterial({ color: 0x8a919c });
        const dark = new THREE.MeshLambertMaterial({ color: 0x6b727d });
        // FAN BOX: the 150 mm octagonal GI hook box cast into the slab. The
        // fan hangs off the hook bar in this box and the conduits land on it -
        // it is what the conduiting layout has to show, so it is modelled too.
        const gi = new THREE.MeshLambertMaterial({ color: 0xb0b6bd });
        const boxR = 0.25, boxD = 0.20;
        const fb = new THREE.Mesh(new THREE.CylinderGeometry(boxR, boxR, boxD, 8), gi);
        fb.rotation.y = Math.PI / 8;                 // flat face to the front
        fb.position.y = boxD / 2;                    // recessed up into the slab
        fan.add(fb);
        const lip = new THREE.Mesh(
          new THREE.TorusGeometry(boxR + 0.015, 0.022, 8, 16), gi);
        lip.rotation.x = Math.PI / 2;
        fan.add(lip);                                // rim flush with the ceiling
        const hook = new THREE.Mesh(
          new THREE.CylinderGeometry(0.028, 0.028, boxR * 2, 8), dark);
        hook.rotation.z = Math.PI / 2;
        hook.position.y = boxD * 0.72;
        fan.add(hook);                               // MS hook bar across the box
        const rod = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.06, 1.0, 10), dark);
        rod.position.y = -0.5;
        fan.add(rod);
        const hub = new THREE.Mesh(new THREE.CylinderGeometry(0.28, 0.28, 0.22, 14), dark);
        hub.position.y = -1.0;
        fan.add(hub);
        const sweep = Math.max(3.2, (+p.size || 4.6));
        for (let k = 0; k < 3; k++) {                // blades HELD BY the hub
          const arm = new THREE.Group();
          const bl = new THREE.Mesh(new THREE.BoxGeometry(sweep / 2 - 0.2, 0.05, 0.5), grey);
          bl.position.x = 0.25 + (sweep / 2 - 0.2) / 2;   // root at the hub
          arm.add(bl);
          arm.rotation.y = k * 2.0944;
          arm.position.y = -1.0;
          fan.add(arm);
        }
        fan.position.set(p.x, ceil, -p.y);
        fan.userData.edit = { kind: "elec", ref: p, plan };
        g.add(fan);
      } else if (code === "AC") {                    // high-wall SPLIT unit
        const ac = new THREE.Group();
        const body = new THREE.MeshLambertMaterial({ color: 0xf4f6f8 });
        const grill = new THREE.MeshLambertMaterial({ color: 0xc9ced4 });
        const shell = new THREE.Mesh(new THREE.BoxGeometry(3.0, 0.95, 0.72), body);
        ac.add(shell);
        for (let k = 0; k < 4; k++) {                // front grille slats
          const sl = new THREE.Mesh(new THREE.BoxGeometry(2.7, 0.05, 0.02), grill);
          sl.position.set(0, 0.25 - k * 0.16, 0.37);
          ac.add(sl);
        }
        const flap = new THREE.Mesh(new THREE.BoxGeometry(2.7, 0.12, 0.2), grill);
        flap.position.set(0, -0.46, 0.32);
        flap.rotation.x = 0.6;                       // open outlet flap
        ac.add(flap);
        const led = new THREE.Mesh(new THREE.BoxGeometry(0.25, 0.1, 0.02),
          new THREE.MeshLambertMaterial({ color: 0x2e7d32 }));
        led.position.set(1.1, 0.05, 0.37);
        ac.add(led);
        ac.position.set(p.x, z0 + ((+p.height_mm || 2175) * MM) + 0.45, -p.y);
        ac.rotation.y = ((+p.angle || 0)) * Math.PI / 180;
        ac.userData.edit = { kind: "elec", ref: p, plan };
        g.add(ac);
      } else {                                       // any light: warm disc
        const d = new THREE.Mesh(new THREE.CylinderGeometry(0.35, 0.35, 0.1, 14),
          new THREE.MeshLambertMaterial({ color: 0xffd76a }));
        d.position.set(p.x, ceil, -p.y);
        d.userData.edit = { kind: "elec", ref: p, plan };
        g.add(d);
      }
    }
  }

  /* ---------------------------------- flooring with REAL-looking texture */
  function addFlooring(g, plan, z0) {
    const rooms = plan.rooms || [];
    for (const r of rooms) {
      if (r.void) continue;
      const spec = (plan.flooring || []).find(f =>
        (f.room || "").trim().toLowerCase() === (r.name || "").trim().toLowerCase());
      const material = spec ? (spec.material || "tile") : "tile";
      const t = floorTex(material).clone();
      t.needsUpdate = true;
      const tileFt = spec && spec.tile_w ? Math.max(0.8, spec.tile_w * MM)
        : (material === "wood" ? 3.94 : 2.0);
      t.repeat.set(Math.max(1, r.w / tileFt), Math.max(1, r.h / tileFt));
      const mat = new THREE.MeshLambertMaterial({ map: t, transparent: true, opacity: 1 });
      floorMats.push(mat);
      g.add(box(r.w - 0.2, r.h - 0.2, 0.07, r.x + r.w / 2, r.y + r.h / 2,
        z0 + 0.045, mat));
      // SKIRTING: a darker strip round the room, 75 mm high — BROKEN at every
      // door (skirting never runs across an opening) and carried AROUND every
      // column standing in the room
      const skC = { wood: 0x6e4a2c, marble: 0xb9b5ae, granite: 0x3c3f45, tile: 0x9a958d }[material] || 0x9a958d;
      const sk = new THREE.MeshLambertMaterial({ color: skC });
      const hSk = (spec && spec.skirting_mm ? spec.skirting_mm : 75) * MM;
      if (hSk > 0.01) {
        const DOOR = o => /door|open|gate/.test(o.type || "");
        // door spans world-space, per opening on any wall
        const doorSpans = [];
        for (const o of (plan.openings || [])) {
          if (!DOOR(o)) continue;
          const w2 = (plan.walls || []).find(x => x.id === o.wall_id);
          if (!w2) continue;
          const L2 = Math.hypot(w2.x2 - w2.x1, w2.y2 - w2.y1) || 1e-6;
          const ux2 = (w2.x2 - w2.x1) / L2, uy2 = (w2.y2 - w2.y1) / L2;
          doorSpans.push({
            horiz: Math.abs(ux2) >= Math.abs(uy2),
            wy: (w2.y1 + w2.y2) / 2, wx: (w2.x1 + w2.x2) / 2,
            a: [w2.x1 + ux2 * o.pos, w2.y1 + uy2 * o.pos],
            b: [w2.x1 + ux2 * (o.pos + o.width), w2.y1 + uy2 * (o.pos + o.width)],
          });
        }
        const strip = (spans, horiz, edgeC, off) => {
          for (const [a, b] of spans) {
            if (b - a < 0.25) continue;
            if (horiz)
              g.add(box(b - a, 0.08, hSk, (a + b) / 2, edgeC + off, z0 + hSk / 2, sk));
            else
              g.add(box(0.08, b - a, hSk, edgeC + off, (a + b) / 2, z0 + hSk / 2, sk));
          }
        };
        const cutDoors = (a0, a1, horiz, edgeC) => {
          // skirting exists ONLY where an actual wall stands on this edge —
          // an open boundary (no wall: a stair mouth, an open-plan side) gets
          // no skirting at all — and then breaks at every door on it
          let spans = [];
          for (const w2 of (plan.walls || [])) {
            if (w2.railing) continue;
            const wHoriz = Math.abs(w2.x2 - w2.x1) >= Math.abs(w2.y2 - w2.y1);
            if (wHoriz !== horiz) continue;
            const wc = horiz ? (w2.y1 + w2.y2) / 2 : (w2.x1 + w2.x2) / 2;
            if (Math.abs(wc - edgeC) > 0.8) continue;
            const lo = Math.max(a0, Math.min(horiz ? w2.x1 : w2.y1, horiz ? w2.x2 : w2.y2));
            const hi = Math.min(a1, Math.max(horiz ? w2.x1 : w2.y1, horiz ? w2.x2 : w2.y2));
            if (hi - lo > 0.2) spans.push([lo, hi]);
          }
          spans.sort((p, q) => p[0] - q[0]);          // merge touching pieces
          const merged = [];
          for (const sp of spans) {
            if (merged.length && sp[0] <= merged[merged.length - 1][1] + 0.15)
              merged[merged.length - 1][1] = Math.max(merged[merged.length - 1][1], sp[1]);
            else merged.push(sp.slice());
          }
          spans = merged;
          for (const d of doorSpans) {
            if (d.horiz !== horiz) continue;
            const wc = horiz ? d.wy : d.wx;
            if (Math.abs(wc - edgeC) > 0.8) continue;      // not this edge's wall
            const da = Math.min(horiz ? d.a[0] : d.a[1], horiz ? d.b[0] : d.b[1]) - 0.1;
            const db = Math.max(horiz ? d.a[0] : d.a[1], horiz ? d.b[0] : d.b[1]) + 0.1;
            const ns = [];
            for (const [sa, sb] of spans) {
              if (db <= sa || da >= sb) { ns.push([sa, sb]); continue; }
              if (da > sa) ns.push([sa, da]);
              if (db < sb) ns.push([db, sb]);
            }
            spans = ns;
          }
          return spans;
        };
        // WET rooms get full wall TILE DADO up to 7 ft (doors cut out) instead
        // of a skirting strip — exactly how a toilet is actually finished
        const isWetRoom = /toilet|bath|w\.?c|wash/i.test(r.name || "");
        const dadoH = 2100 * MM;
        const dado = (spans, horiz, edgeC, off) => {
          for (const [a, b] of spans) {
            if (b - a < 0.3) continue;
            const dt = floorTex("tile").clone();
            dt.needsUpdate = true;
            dt.repeat.set(Math.max(1, (b - a) / 2), Math.max(1, dadoH / 2));
            const dm = new THREE.MeshLambertMaterial({ map: dt });
            if (horiz)
              g.add(box(b - a, 0.06, dadoH, (a + b) / 2, edgeC + off, z0 + dadoH / 2, dm));
            else
              g.add(box(0.06, b - a, dadoH, edgeC + off, (a + b) / 2, z0 + dadoH / 2, dm));
          }
        };
        const line = isWetRoom ? dado : strip;
        line(cutDoors(r.x + 0.2, r.x + r.w - 0.2, true, r.y), true, r.y, 0.2);
        line(cutDoors(r.x + 0.2, r.x + r.w - 0.2, true, r.y + r.h), true, r.y + r.h, -0.2);
        line(cutDoors(r.y + 0.2, r.y + r.h - 0.2, false, r.x), false, r.x, 0.2);
        line(cutDoors(r.y + 0.2, r.y + r.h - 0.2, false, r.x + r.w), false, r.x + r.w, -0.2);
        // skirting wraps AROUND every column standing in this room
        for (const c of (plan.columns || [])) {
          if (c.x < r.x - 0.2 || c.x > r.x + r.w + 0.2 ||
              c.y < r.y - 0.2 || c.y > r.y + r.h + 0.2) continue;
          const cw2 = (+c.w || 0.8) / 2 + 0.06, ch2 = (+c.h || 0.8) / 2 + 0.06;
          g.add(box(cw2 * 2, 0.08, hSk, c.x, c.y - ch2, z0 + hSk / 2, sk));
          g.add(box(cw2 * 2, 0.08, hSk, c.x, c.y + ch2, z0 + hSk / 2, sk));
          g.add(box(0.08, ch2 * 2, hSk, c.x - cw2, c.y, z0 + hSk / 2, sk));
          g.add(box(0.08, ch2 * 2, hSk, c.x + cw2, c.y, z0 + hSk / 2, sk));
        }
      }
    }
  }

  /* ------------------------------------------- parapet OR railing on top */
  function addTop(g, base, topZ, P, M, mode) {
    if (mode === "none") return;
    let y0 = 1e9;
    (base.walls || []).forEach(w => { y0 = Math.min(y0, w.y1, w.y2); });
    const isFront = w => Math.min(w.y1, w.y2) < y0 + 0.8 &&
      Math.abs(w.y1 - w.y2) < 0.5;                   // the lowest horizontal run
    (base.walls || []).forEach(w => {
      if (!w.exterior || w.railing) return;
      const L = Math.hypot(w.x2 - w.x1, w.y2 - w.y1); if (L < 0.05) return;
      const rail = mode === "rail-all" || (mode === "rail-front" && isFront(w));
      const ang = Math.atan2(-(w.y2 - w.y1), (w.x2 - w.x1));
      if (!rail) {                                    // solid parapet wall
        const t = ((+w.thickness_in || 9) / 12) * 0.6;
        const m = box(L, t, P.para, (w.x1 + w.x2) / 2, (w.y1 + w.y2) / 2,
          topZ + P.para / 2, M.ext);
        m.rotation.y = ang;
        g.add(m);
      } else {                                        // RAILING: posts + 2 rails
        const h = Math.max(P.para, 3.0);
        const ux = (w.x2 - w.x1) / L, uy = (w.y2 - w.y1) / L;
        const nPost = Math.max(2, Math.round(L / 3.5) + 1);
        for (let i = 0; i < nPost; i++) {
          const d = L * i / (nPost - 1);
          const p = cylBetween(w.x1 + ux * d, w.y1 + uy * d, topZ,
            w.x1 + ux * d, w.y1 + uy * d, topZ + h, 0.07, M.rail);
          if (p) g.add(p);
        }
        for (const frac of [1.0, 0.55]) {
          const r2 = cylBetween(w.x1, w.y1, topZ + h * frac,
            w.x2, w.y2, topZ + h * frac, frac === 1 ? 0.09 : 0.05, M.rail);
          if (r2) g.add(r2);
        }
      }
    });
  }

  /* --------------------------------------------------------- the model */
  // ---- COMPOUND WALL round the plot, with the MAIN GATE in the road face.
  // Its height comes from the panel slider, so you can study 4 ft vs 7 ft.
  function addBoundary(g, plan, M) {
    const pl = plan.plot; if (!pl || !(pl.w > 1) || !(pl.h > 1)) return;
    const H = +((($("#v3bwh") || {}).value)) || 6;
    const t = 0.75, pcH = H + 0.35;                 // wall thk, pillar height
    const bm = new THREE.MeshLambertMaterial({ color: 0xcfc6b4 });
    const cap = new THREE.MeshLambertMaterial({ color: 0x9aa0a8 });
    const gm = new THREE.MeshLambertMaterial({ color: 0x37506b });
    const x0 = pl.x, y0 = pl.y, x1 = pl.x + pl.w, y1 = pl.y + pl.h;
    const gateW = Math.min(12, pl.w * 0.45);        // main gate, road side
    const gx = (x0 + x1) / 2;
    const strip = (ax0, ay0, ax1, ay1) => {
      const L = Math.hypot(ax1 - ax0, ay1 - ay0); if (L < 0.2) return;
      const m = box(L, t, H, (ax0 + ax1) / 2, (ay0 + ay1) / 2, H / 2, bm);
      m.rotation.y = Math.atan2(-(ay1 - ay0), (ax1 - ax0));
      g.add(m);
      const c = box(L, t + 0.18, 0.22, (ax0 + ax1) / 2, (ay0 + ay1) / 2, H + 0.11, cap);
      c.rotation.y = m.rotation.y;
      g.add(c);                                     // coping over the wall
    };
    strip(x0, y1, x1, y1);                          // rear
    strip(x0, y0, x0, y1);                          // left
    strip(x1, y0, x1, y1);                          // right
    strip(x0, y0, gx - gateW / 2, y0);              // front, either side of gate
    strip(gx + gateW / 2, y0, x1, y0);
    // gate pillars + a twin-leaf sliding gate with vertical bars
    for (const px of [gx - gateW / 2, gx + gateW / 2]) {
      g.add(box(1.1, 1.1, pcH, px, y0, pcH / 2, bm));
      g.add(box(1.3, 1.3, 0.28, px, y0, pcH + 0.14, cap));
    }
    const gH = Math.min(H, 6.5);
    for (const side of [-1, 1]) {
      const cxg = gx + side * gateW / 4;
      g.add(box(gateW / 2 - 0.1, 0.16, 0.28, cxg, y0, 0.35, gm));   // bottom rail
      g.add(box(gateW / 2 - 0.1, 0.16, 0.28, cxg, y0, gH - 0.2, gm)); // top rail
      const n = Math.max(5, Math.round((gateW / 2) / 0.55));
      for (let i = 0; i <= n; i++) {
        const bx = cxg - (gateW / 4 - 0.1) + (i * (gateW / 2 - 0.2)) / n;
        g.add(box(0.11, 0.11, gH - 0.55, bx, y0, gH / 2 + 0.2, gm));
      }
    }
  }

  // ---- free FACES you draw for facade study: a rectangle or a disc placed
  // in the model, movable / resizable / deletable like any other object
  function addFaces(g, plan) {
    for (const fc of (plan.faces3d || [])) {
      const mat = new THREE.MeshLambertMaterial({
        color: parseInt((fc.color || "#8fa3bf").slice(1), 16),
        side: THREE.DoubleSide, transparent: true,
        opacity: fc.opacity == null ? 1 : +fc.opacity });
      const geo = fc.shape === "circle"
        ? new THREE.CircleGeometry(Math.max(0.2, +fc.r || 2), 40)
        : new THREE.PlaneGeometry(Math.max(0.2, +fc.w || 4),
                                  Math.max(0.2, +fc.h || 4));
      const m = new THREE.Mesh(geo, mat);
      m.position.set(+fc.x || 0, +fc.z || 4, -(+fc.y || 0));
      m.rotation.y = ((+fc.angle || 0)) * Math.PI / 180;
      if (fc.flat) m.rotation.x = -Math.PI / 2;      // lying flat, not upright
      m.userData.edit = { kind: "face", ref: fc, plan };
      g.add(m);
    }
  }

  function buildModel() {
    extMats = []; intMats = []; floorMats = [];
    const M = mats();
    floorMats.push(M.slab);
    const P = params();
    const root = new THREE.Group();
    const base = S.plan; if (!base) return root;
    G = { walls: new THREE.Group(), roof: new THREE.Group(), struct: new THREE.Group(),
      stairs: new THREE.Group(), floor: new THREE.Group(), furn: new THREE.Group(),
      plumb: new THREE.Group(), elec: new THREE.Group(), top: new THREE.Group(),
      mumty: new THREE.Group(), bwall: new THREE.Group(),
      faces: new THREE.Group() };

    let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
    (base.walls || []).forEach(w => {
      x0 = Math.min(x0, w.x1, w.x2); y0 = Math.min(y0, w.y1, w.y2);
      x1 = Math.max(x1, w.x1, w.x2); y1 = Math.max(y1, w.y1, w.y2);
    });
    if (x1 <= x0) return root;
    const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;

    // the plinth gets its OWN material so the floor x-ray can see through it
    // to the underfloor piping without fading every column in the model
    const plinthM = new THREE.MeshLambertMaterial({ color: 0x99a0a8, transparent: true, opacity: 1 });
    floorMats.push(plinthM);
    G.struct.add(box(x1 - x0 + 1, y1 - y0 + 1, Math.max(P.plinth, 0.1),
      cx, cy, Math.max(P.plinth, 0.1) / 2, plinthM));

    // every layer holds one sub-group PER FLOOR, so a floor can be hidden,
    // locked or nudged as a whole while the layer toggles still work
    FL = [];
    const LKEYS = ["walls", "struct", "stairs", "floor", "furn", "plumb",
      "elec", "roof", "mumty"];
    const floorSet = fi => {
      if (FL[fi]) return FL[fi];
      const set = {};
      for (const k of LKEYS) {
        const gg = new THREE.Group();
        gg.userData.floor = fi;
        (G[k] || G.walls).add(gg);
        set[k] = gg;
      }
      FL[fi] = set;
      return set;
    };
    let topZ = P.plinth;
    for (let f = 0; f < P.floors; f++) {
      const plan = ((S.floors || [])[f] && S.floors[f].plan) || base;
      const L = floorSet(f);
      const z0 = P.plinth + f * P.fh;
      const H = P.fh;
      (plan.walls || []).forEach(w => { if (!w.railing) addWall(L.walls, plan, w, z0, H, P, M, cx, cy); });
      (plan.columns || []).forEach(c => {
        const cm = box(Math.max(+c.w || 0.8, 0.3), Math.max(+c.h || 0.8, 0.3), H,
          c.x, c.y, z0 + H / 2, M.conc);
        cm.userData.edit = { kind: "col", ref: c, plan };
        L.struct.add(cm);
      });
      (plan.beams || []).forEach(b => {
        const L = Math.hypot(b.x2 - b.x1, b.y2 - b.y1); if (L < 0.1) return;
        const bw = ((+b.width_mm || 230) * MM), bd = ((+b.depth_mm || 300) * MM);
        const m = box(L, bw, bd, (b.x1 + b.x2) / 2, (b.y1 + b.y2) / 2,
          z0 + H - bd / 2, M.conc);
        m.rotation.y = Math.atan2(-(b.y2 - b.y1), (b.x2 - b.x1));
        m.userData.edit = { kind: "beam", ref: b, plan };
        L.struct.add(m);
      });
      // the slab is CUT OUT over every staircase (the stair well) — a slab
      // poured straight over the stair is exactly the amateur-model look
      const slabG = (f === P.floors - 1 ? L.roof : L.struct);
      let rects = [[x0 - 0.4, y0 - 0.4, x1 + 0.4, y1 + 0.4]];
      for (const st of (plan.stairs || [])) {
        const hole = [st.x, st.y, st.x + st.w, st.y + st.h];
        const nr = [];
        for (const r of rects) {
          if (hole[2] <= r[0] || hole[0] >= r[2] || hole[3] <= r[1] || hole[1] >= r[3]) { nr.push(r); continue; }
          if (hole[0] > r[0]) nr.push([r[0], r[1], hole[0], r[3]]);
          if (hole[2] < r[2]) nr.push([hole[2], r[1], r[2], r[3]]);
          const ix0 = Math.max(r[0], hole[0]), ix1 = Math.min(r[2], hole[2]);
          if (hole[1] > r[1]) nr.push([ix0, r[1], ix1, hole[1]]);
          if (hole[3] < r[3]) nr.push([ix0, hole[3], ix1, r[3]]);
        }
        rects = nr;
      }
      for (const r of rects) {
        if (r[2] - r[0] < 0.1 || r[3] - r[1] < 0.1) continue;
        slabG.add(box(r[2] - r[0], r[3] - r[1], P.slab,
          (r[0] + r[2]) / 2, (r[1] + r[3]) / 2, z0 + H + P.slab / 2, M.slab));
      }
      // MUMTY over the top-floor staircase: its own little room on the roof —
      // walls round the stair well, a door gap where the flight arrives, and
      // its own flat slab. This is how the stair actually comes out on top.
      if (f === P.floors - 1) {
        for (const st of (plan.stairs || [])) {
          const mz = z0 + H + P.slab, mh = 2450 * MM, mt = 0.4;
          const alongX = (st.run_axis || "x") === "x";
          const dirUp = (st.up_from === "left" || st.up_from === "bottom") ? 1 : -1;
          const Bst = alongX ? st.h : st.w;
          const fwM = (st.type === "U3") ? Math.min(4.0, Bst * 0.34) : Bst / 2;
          const doorC = fwM / 2;                     // door centred on the
          const doorW = 3;                           // ARRIVAL (bottom) band
          const wallStrip = (wx0, wy0, wx1, wy1) => {
            const Lw = Math.hypot(wx1 - wx0, wy1 - wy0); if (Lw < 0.2) return;
            const m = box(Lw, mt, mh, (wx0 + wx1) / 2, (wy0 + wy1) / 2, mz + mh / 2, M.ext);
            m.rotation.y = Math.atan2(-(wy1 - wy0), (wx1 - wx0));
            L.mumty.add(m);
          };
          const sx0 = st.x, sy0 = st.y, sx1 = st.x + st.w, sy1 = st.y + st.h;
          if (alongX) {
            const du = dirUp > 0 ? sx0 : sx1;        // near end x (arrival side)
            wallStrip(sx0, sy1, sx1, sy1);
            wallStrip(sx0, sy0, sx1, sy0);
            wallStrip(du, sy0, du, sy0 + Math.max(0, doorC - doorW / 2));
            wallStrip(du, sy0 + doorC + doorW / 2, du, sy1);
            const far = dirUp > 0 ? sx1 : sx0;
            wallStrip(far, sy0, far, sy1);
          } else {
            const du = dirUp > 0 ? sy0 : sy1;
            wallStrip(sx0, sy0, sx0, sy1);
            wallStrip(sx1, sy0, sx1, sy1);
            wallStrip(sx0, du, sx0 + Math.max(0, doorC - doorW / 2), du);
            wallStrip(sx0 + doorC + doorW / 2, du, sx1, du);
            const far = dirUp > 0 ? sy1 : sy0;
            wallStrip(sx0, far, sx1, far);
          }
          L.mumty.add(box(st.w + 1.2, st.h + 1.2, P.slab,
            (sx0 + sx1) / 2, (sy0 + sy1) / 2, mz + mh + P.slab / 2, M.slab));
        }
      }
      addStairs(L.stairs, plan, z0, H, M);
      addFlooring(L.floor, plan, z0);
      addFurniture(L.furn, plan, z0);
      addPipes(L.plumb, plan, z0, H);
      addElec(L.elec, plan, z0, H);
      topZ = z0 + H + P.slab;
    }
    addTop(G.top, base, topZ, P, M, ($("#v3para") || {}).value || "parapet");
    addBoundary(G.bwall, base, M);        // compound wall + main gate
    addFaces(G.faces, base);              // facade study faces

    Object.values(G).forEach(gr => root.add(gr));
    root.position.set(-cx, 0, cy);
    // apply the current layer checkboxes
    buildFloorPanel();
    syncLayers();
    return root;
  }

  function syncLayers() {
    const on = id => { const e = $(id); return !e || e.checked; };
    if (!G.walls) return;
    G.walls.visible = on("#v3walls");
    G.struct.visible = on("#v3struct");
    G.stairs.visible = on("#v3stairs");
    G.roof.visible = on("#v3roof");
    G.top.visible = on("#v3roof");
    if (G.mumty) G.mumty.visible = on("#v3roof") && on("#v3mumty");
    G.furn.visible = on("#v3furn");
    const plumbOn = on("#v3plumb");
    G.plumb.visible = plumbOn;
    // piping is UNDERFLOOR — with the plumbing layer on, the floor/plinth
    // fades (floor x-ray slider) so the concealed runs read below the FFL
    const fOp = plumbOn ? (+((($("#v3flop") || {}).value)) || 0.35) : 1;
    floorMats.forEach(m => { m.opacity = fOp; m.needsUpdate = true; });
    const elecOn = on("#v3elec");
    G.elec.visible = elecOn;
    // conduits are CONCEALED in the walls — turning the electrical layer on
    // fades the internal walls (wall x-ray slider) so the runs read INSIDE
    const wOp = elecOn ? (+((($("#v3intop") || {}).value)) || 0.3) : 1;
    intMats.forEach(m => { m.opacity = wOp; m.needsUpdate = true; });
    G.floor.visible = on("#v3floor");
    if (G.bwall) G.bwall.visible = on("#v3bwall");
    if (G.faces) G.faces.visible = on("#v3faces");
    // per-FLOOR eye and nudge: hide or shift a whole storey without touching
    // the layer switches
    FL.forEach((set, fi) => {
      const vis = floorVis[fi] !== false;
      const o = floorOff[fi] || { x: 0, y: 0 };
      for (const k in set) {
        set[k].visible = vis;
        set[k].position.set(o.x || 0, 0, -(o.y || 0));
      }
    });
  }

  /* ------------------------------------------------------------- viewer */
  function applyCam() {
    if (topMode) {                     // EXACT 2D: straight-down orthographic
      camera.position.set(orbit.tx, 300, orbit.tz);
      camera.up.set(0, 0, -1);
      camera.lookAt(orbit.tx, 0, orbit.tz);
      return;
    }
    const { az, el, dist, tx, ty, tz } = orbit;
    camera.position.set(
      tx + dist * Math.cos(el) * Math.cos(az),
      ty + dist * Math.sin(el),
      tz + dist * Math.cos(el) * Math.sin(az));
    camera.up.set(0, 1, 0);
    camera.lookAt(tx, ty, tz);
  }
  // ENTER the exact-2D top view: a real ORTHOGRAPHIC camera looking straight
  // down — zero perspective, walls dead-flat, exactly the 2D plan
  function enterTop() {
    const holder = $("#view3d");
    const w = holder.clientWidth, h = holder.clientHeight - 44, asp = w / Math.max(1, h);
    if (modelRoot) {
      const bb = new THREE.Box3().setFromObject(modelRoot);
      const sz = bb.getSize(new THREE.Vector3());
      const c = bb.getCenter(new THREE.Vector3());
      orthoH = Math.max(sz.z * 0.62, sz.x * 0.62 / asp, 10);
      orbit.tx = c.x; orbit.tz = c.z;
    }
    camera = new THREE.OrthographicCamera(-orthoH * asp, orthoH * asp,
      orthoH, -orthoH, 0.1, 1000);
    topMode = true;
  }
  function exitTop() {
    if (!topMode) return;
    topMode = false;
    camera = new THREE.PerspectiveCamera(50, 1, 0.1, 4000);
    resize();
  }
  function orthoFrustum() {
    const holder = $("#view3d");
    const w = holder.clientWidth, h = holder.clientHeight - 44, asp = w / Math.max(1, h);
    camera.left = -orthoH * asp; camera.right = orthoH * asp;
    camera.top = orthoH; camera.bottom = -orthoH;
    camera.updateProjectionMatrix();
  }

  function openViewer() {
    if (!S.plan) { status("Pehle plan generate/khol karein"); return; }
    $("#view3d").classList.remove("hidden");
    const canvas = $("#v3canvas");
    if (!renderer) {
      renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
      renderer.setPixelRatio(window.devicePixelRatio || 1);
    }
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x1c2230);
    ambL = new THREE.AmbientLight(0xffffff, 0.55);
    scene.add(ambL);
    hemiL = new THREE.HemisphereLight(0xbcd2ff, 0x3a3126, 0.35);
    scene.add(hemiL);
    const sun = new THREE.DirectionalLight(0xfff2dd, 0.85);
    sun.position.set(60, 90, 40);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.camera.left = -60; sun.shadow.camera.right = 60;
    sun.shadow.camera.top = 60; sun.shadow.camera.bottom = -60;
    scene.add(sun);
    sunL = sun;
    applySun();                            // honour the Sun / brightness slider
    const sun2 = new THREE.DirectionalLight(0xdde6ff, 0.22);
    sun2.position.set(-50, 40, -60); scene.add(sun2);
    scene.add(new THREE.GridHelper(200, 40, 0x37415a, 0x2a3248));
    // soft ground shadow catcher
    const ground = new THREE.Mesh(new THREE.PlaneGeometry(300, 300),
      new THREE.ShadowMaterial({ opacity: 0.28 }));
    ground.rotation.x = -Math.PI / 2;
    ground.receiveShadow = true;
    scene.add(ground);
    modelRoot = buildModel();
    modelRoot.traverse(o => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
    scene.add(modelRoot);
    camera = new THREE.PerspectiveCamera(50, 1, 0.1, 4000);
    topMode = false;
    // the orbit HOME pivot = the model's bounding-box centre (Revit-style)
    homeCenter = new THREE.Box3().setFromObject(modelRoot)
      .getCenter(new THREE.Vector3());
    orbit.tx = homeCenter.x; orbit.ty = homeCenter.y; orbit.tz = homeCenter.z;
    orbit.dist = 90; orbit.az = -0.9; orbit.el = 0.55;
    open = true;
    const opInp = $("#v3op"); if (opInp) setOpacity(opInp.value / 100);
    resize(); loop();
  }
  // rebuild keeps the CAMERA where you left it — only the model is re-derived
  function rebuild() {
    if (!open || !scene) return;
    clearSel();
    if (modelRoot) scene.remove(modelRoot);
    modelRoot = buildModel();
    modelRoot.traverse(o => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
    scene.add(modelRoot);
    homeCenter = new THREE.Box3().setFromObject(modelRoot)
      .getCenter(new THREE.Vector3());
    const opInp = $("#v3op"); if (opInp) setOpacity(opInp.value / 100);
  }
  function closeViewer() { clearSel(); open = false; cancelAnimationFrame(raf); $("#view3d").classList.add("hidden"); }
  function resize() {
    if (!renderer || !open) return;
    const holder = $("#view3d");
    const w = holder.clientWidth, h = holder.clientHeight - 44;
    renderer.setSize(w, h, false);
    if (camera.isOrthographicCamera) { orthoFrustum(); return; }
    camera.aspect = w / h; camera.updateProjectionMatrix();
  }
  /* -------- game-style FLY keys: W/S ahead-back, A/D strafe, Q/E down-up */
  const flyKeys = {};
  function flyStep() {
    const sp = Math.max(0.15, orbit.dist * 0.014);
    const fnx = -Math.cos(orbit.az), fnz = -Math.sin(orbit.az);  // level forward
    let dx = 0, dy = 0, dz = 0;
    if (flyKeys.w) { dx += fnx * sp; dz += fnz * sp; }
    if (flyKeys.s) { dx -= fnx * sp; dz -= fnz * sp; }
    if (flyKeys.d) { dx += -fnz * sp; dz += fnx * sp; }
    if (flyKeys.a) { dx -= -fnz * sp; dz -= fnx * sp; }
    if (flyKeys.e) dy += sp;
    if (flyKeys.q) dy -= sp;
    if (dx || dy || dz) { orbit.tx += dx; orbit.ty += dy; orbit.tz += dz; }
  }
  function loop() {
    if (!open) return;
    flyStep();
    applyCam(); renderer.render(scene, camera);
    raf = requestAnimationFrame(loop);
  }
  function setOpacity(v) {
    extMats.forEach(m => { m.opacity = v; m.transparent = true; m.needsUpdate = true; });
  }
  // SUN / brightness — one slider tames the glare instead of washing the
  // model out: it scales the sun, the ambient and the sky fill together
  // LAYERS panel gets a FLOORS block: eye, lock and an X / Y nudge per storey
  function buildFloorPanel() {
    const host = $("#v3floors"); if (!host) return;
    const P = params();
    host.innerHTML = "";
    for (let i = 0; i < P.floors; i++) {
      const nm = ((S.floors || [])[i] || {}).name || ("Floor " + (i + 1));
      const row = document.createElement("div");
      row.className = "v3f-row";
      const eye = document.createElement("input");
      eye.type = "checkbox"; eye.checked = floorVis[i] !== false;
      eye.title = "show / hide this floor";
      eye.onchange = () => { floorVis[i] = eye.checked; syncLayers(); };
      const lab = document.createElement("span");
      lab.className = "v3f-name"; lab.textContent = nm;
      const lk = document.createElement("button");
      lk.className = "v3lock" + (floorLock[i] ? " locked" : "");
      lk.textContent = floorLock[i] ? "🔒" : "🔓";
      lk.title = "lock this floor — nothing in it can be selected or edited";
      lk.onclick = e => {
        e.preventDefault();
        floorLock[i] = !floorLock[i];
        lk.textContent = floorLock[i] ? "🔒" : "🔓";
        lk.classList.toggle("locked", floorLock[i]);
        if (floorLock[i] && selObj) clearSel();
      };
      row.appendChild(eye); row.appendChild(lab); row.appendChild(lk);
      host.appendChild(row);
      if (i > 0) {                       // the ground floor stays put
        const nud = document.createElement("div");
        nud.className = "v3f-nudge";
        for (const ax of ["x", "y"]) {
          const inp = document.createElement("input");
          inp.type = "number"; inp.step = 0.25; inp.value = 0;
          inp.title = "shift this floor along " + ax.toUpperCase() + " (ft)";
          inp.onchange = () => {
            floorOff[i] = floorOff[i] || { x: 0, y: 0 };
            floorOff[i][ax] = +inp.value || 0;
            syncLayers();
          };
          nud.appendChild(inp);
        }
        host.appendChild(nud);
      }
    }
  }

  function applySun() {
    const v = +((($("#v3sun") || {}).value)) || 0.6;
    if (sunL) sunL.intensity = v * 0.9;
    if (ambL) ambL.intensity = 0.30 + v * 0.30;
    if (hemiL) hemiL.intensity = v * 0.4;
  }

  /* ------------------------------------------- 3D EDIT: select + move */
  const raycaster = new THREE.Raycaster();
  // re-pivot the orbit onto a world point WITHOUT the camera jumping:
  // keep the camera where it is, recompute az/el/dist about the new target
  function retarget(pt) {
    if (!pt || !camera) return;
    const d = camera.position.clone().sub(pt);
    orbit.tx = pt.x; orbit.ty = pt.y; orbit.tz = pt.z;
    orbit.dist = Math.max(1.5, d.length());
    orbit.el = Math.asin(Math.min(1, Math.max(-1, d.y / orbit.dist)));
    orbit.az = Math.atan2(d.z, d.x);
  }
  function clearSel() {
    if (selHelper && scene) scene.remove(selHelper);
    selHelper = null; selObj = null;
    const chip = $("#v3selname"); if (chip) chip.textContent = "";
    showProps(null);
  }
  function setSel(obj) {
    clearSel();
    selObj = obj;
    selHelper = new THREE.BoxHelper(obj, 0x27e0a3);
    scene.add(selHelper);
    const ed = obj.userData.edit, r = ed.ref;
    const chip = $("#v3selname");
    if (chip) chip.textContent =
      (r.tag || r.name || r.kind || r.system || ed.kind) + "  ·  drag = move, Del = delete";
    // REVIT-style: with a selection, the orbit pivots around the SELECTION
    const bc = new THREE.Box3().setFromObject(obj).getCenter(new THREE.Vector3());
    retarget(bc);
    showProps(obj);
  }
  /* ---------- PROPERTIES panel: click a product, edit its specification */
  const PROP_FIELDS = {
    furn:  [["Tag", "tag", "t"], ["X (ft)", "x", 0.25], ["Y (ft)", "y", 0.25],
            ["Width (ft)", "w", 0.25], ["Depth (ft)", "h", 0.25], ["Angle °", "angle", 15]],
    elec:  [["Tag", "tag", "t"], ["X (ft)", "x", 0.25], ["Y (ft)", "y", 0.25],
            ["Height (mm)", "height_mm", 25], ["Fan sweep (ft)", "size", 0.2], ["Angle °", "angle", 15]],
    plumb: [["Code", "code", "t"], ["X (ft)", "x", 0.25], ["Y (ft)", "y", 0.25]],
    pipe:  [["Dia (mm)", "dia_mm", 5]],
    col:   [["X (ft)", "x", 0.25], ["Y (ft)", "y", 0.25],
            ["Width (ft)", "w", 0.05], ["Depth (ft)", "h", 0.05]],
    beam:  [["Length (ft)", "__len", 0.25], ["Width (mm)", "width_mm", 10],
            ["Depth (mm)", "depth_mm", 25]],
    face:  [["X (ft)", "x", 0.25], ["Y (ft)", "y", 0.25], ["Height Z (ft)", "z", 0.25],
            ["Width (ft)", "w", 0.25], ["Height (ft)", "h", 0.25],
            ["Radius (ft)", "r", 0.25], ["Angle °", "angle", 15],
            ["Colour", "color", "t"], ["Opacity", "opacity", 0.05]],
  };
  const PROP_TITLE = { face: "◻ FACE", furn: "🛋 FURNITURE", elec: "⚡ ELECTRICAL",
    plumb: "🚿 PLUMBING", pipe: "🚰 PIPE RUN",
    col: "🏗 COLUMN", beam: "🏗 BEAM" };
  function showProps(obj) {
    const el = $("#v3props"); if (!el) return;
    el.innerHTML = "";
    if (!obj) return;
    const ed = obj.userData.edit, r = ed.ref;
    const head = document.createElement("div");
    head.className = "v3p-head";
    head.textContent = (PROP_TITLE[ed.kind] || ed.kind.toUpperCase()) +
      (r.tag || r.name ? "  ·  " + (r.tag || r.name) : "") +
      (r.kind ? "  ·  " + r.kind : "") + (r.system ? "  ·  " + r.system : "");
    el.appendChild(head);
    for (const [label, key, step] of (PROP_FIELDS[ed.kind] || [])) {
      if (r[key] === undefined && step !== "t" &&
          !(key === "x" || key === "y" || key === "__len")) continue;
      const row = document.createElement("label");
      row.className = "v3p-row";
      const sp = document.createElement("span"); sp.textContent = label;
      const inp = document.createElement("input");
      if (step === "t") { inp.type = "text"; inp.value = r[key] || ""; }
      else if (key === "__len") {        // beam LENGTH — derived, edits both ends
        inp.type = "number"; inp.step = step;
        inp.value = +Math.hypot(r.x2 - r.x1, r.y2 - r.y1).toFixed(2);
      }
      else { inp.type = "number"; inp.step = step; inp.value = +(+r[key] || 0).toFixed(2); }
      inp.onchange = () => {
        if (typeof pushUndo === "function") pushUndo();
        if (key === "__len") {
          // stretch / shrink about the beam's midpoint, along its own axis
          const L = Math.hypot(r.x2 - r.x1, r.y2 - r.y1) || 1e-6;
          const ux = (r.x2 - r.x1) / L, uy = (r.y2 - r.y1) / L;
          const mx = (r.x1 + r.x2) / 2, my = (r.y1 + r.y2) / 2;
          const nl = Math.max(0.5, +inp.value || L);
          const rd = v => Math.round(v * 20) / 20;
          r.x1 = rd(mx - ux * nl / 2); r.y1 = rd(my - uy * nl / 2);
          r.x2 = rd(mx + ux * nl / 2); r.y2 = rd(my + uy * nl / 2);
        } else {
          r[key] = step === "t" ? inp.value : (+inp.value || 0);
        }
        if (typeof redraw === "function") redraw();  // 2D follows the spec edit
        rebuild();
        reselectRef(r);
      };
      row.appendChild(sp); row.appendChild(inp);
      el.appendChild(row);
    }
    const del = document.createElement("button");
    del.className = "v3btn v3x"; del.textContent = "🗑 Delete";
    del.onclick = deleteSel;
    el.appendChild(del);
  }
  // after a rebuild the meshes are new — find the one for the same plan ref
  function reselectRef(ref) {
    if (!modelRoot) return;
    let f = null;
    modelRoot.traverse(o => {
      if (!f && o.userData && o.userData.edit && o.userData.edit.ref === ref) f = o;
    });
    if (f) setSel(f);
  }
  // pick the closest EDITABLE thing under the cursor (skips hidden layers)
  function pick(e) {
    if (!modelRoot || !camera) return null;
    const cv = $("#v3canvas"), rc = cv.getBoundingClientRect();
    const nd = new THREE.Vector2(
      ((e.clientX - rc.left) / rc.width) * 2 - 1,
      -((e.clientY - rc.top) / rc.height) * 2 + 1);
    raycaster.setFromCamera(nd, camera);
    for (const hit of raycaster.intersectObjects(modelRoot.children, true)) {
      let o = hit.object, vis = true, ed = null;
      for (let a = hit.object; a; a = a.parent) {
        if (a.visible === false) vis = false;
        if (!ed && a.userData && a.userData.edit) { ed = a.userData.edit; o = a; }
      }
      if (!vis) continue;
      if (ed && locks[LOCKOF[ed.kind]]) ed = null;    // locked layer = untouchable
      if (ed) {                                       // locked FLOOR likewise
        for (let a = o; a; a = a.parent)
          if (a.userData && a.userData.floor !== undefined
              && floorLock[a.userData.floor]) { ed = null; break; }
      }
      if (ed) return { obj: o, pt: hit.point };
      // a SOLID surface blocks the pick; an x-rayed (faded) one lets the
      // click pass through to the concealed services behind it
      const m = Array.isArray(hit.object.material) ? hit.object.material[0] : hit.object.material;
      if (!m || !m.transparent || m.opacity >= 0.9) return null;
    }
    return null;
  }
  // move the ref by (dx, dy) in PLAN feet — every editable kind knows its shape
  function applyMove(ed, dx, dy) {
    const rnd = v => Math.round(v * 20) / 20, r = ed.ref;
    dx = rnd(dx); dy = rnd(dy);
    if (ed.kind === "face") { r.x = rnd((+r.x || 0) + dx); r.y = rnd((+r.y || 0) + dy); }
    else if (ed.kind === "pipe") (r.pts || []).forEach(pt => { pt[0] = rnd(pt[0] + dx); pt[1] = rnd(pt[1] + dy); });
    else if (ed.kind === "beam") { r.x1 = rnd(r.x1 + dx); r.x2 = rnd(r.x2 + dx); r.y1 = rnd(r.y1 + dy); r.y2 = rnd(r.y2 + dy); }
    else { r.x = rnd((+r.x || 0) + dx); r.y = rnd((+r.y || 0) + dy); }
  }
  function deleteSel() {
    if (!selObj) return;
    const ed = selObj.userData.edit;
    const pool = { furn: "furniture", elec: "elec", plumb: "plumb", pipe: "pipes",
      col: "columns", beam: "beams", face: "faces3d" }[ed.kind];
    const arr = (ed.plan && ed.plan[pool]) || [];
    const i = arr.indexOf(ed.ref); if (i < 0) return;
    if (typeof pushUndo === "function") pushUndo();
    arr.splice(i, 1);
    clearSel();
    if (typeof redraw === "function") redraw();   // 2D follows the 3D edit
    rebuild();
  }

  /* --------------------------------------------------- controls wiring */
  function wire() {
    const cv = $("#v3canvas"); if (!cv) return;
    // modes: 1 = orbit (L-drag empty), 2 = pan (middle / right / shift),
    // 3 = pinch, 4 = drag-move a selected object
    let mode = 0, lx = 0, ly = 0, pinch = 0;
    let dragEd = null, dragPlane = null, dragStart = null, dragDelta = null, downXY = null;
    cv.addEventListener("contextmenu", e => e.preventDefault());
    // the model-surface point under the cursor (ground plane as fallback) —
    // SketchUp pivots its orbit and its zoom on exactly this point
    function surfPoint(e) {
      const rc = cv.getBoundingClientRect();
      const nd = new THREE.Vector2(
        ((e.clientX - rc.left) / rc.width) * 2 - 1,
        -((e.clientY - rc.top) / rc.height) * 2 + 1);
      raycaster.setFromCamera(nd, camera);
      if (modelRoot) {
        for (const h of raycaster.intersectObjects(modelRoot.children, true)) {
          let vis = true;
          for (let a = h.object; a; a = a.parent) if (a.visible === false) vis = false;
          if (vis) return h.point;
        }
      }
      const p = new THREE.Vector3();
      return raycaster.ray.intersectPlane(
        new THREE.Plane(new THREE.Vector3(0, 1, 0), -orbit.ty), p) ? p : null;
    }
    cv.addEventListener("mousedown", e => {
      lx = e.clientX; ly = e.clientY; downXY = [e.clientX, e.clientY];
      // SKETCHUP scheme: middle-drag = ORBIT, Shift+drag / right-drag = PAN
      if (e.shiftKey || e.button === 2) { mode = 2; e.preventDefault(); return; }
      if (e.button === 1) {
        if (topMode) { mode = 2; e.preventDefault(); return; }
        const sp = surfPoint(e);
        if (sp) retarget(sp);                  // orbit about the cursor point
        mode = 1; e.preventDefault(); return;
      }
      const hit = pick(e);                       // L-down on a thing = grab it
      if (hit) {
        setSel(hit.obj);
        dragEd = hit.obj.userData.edit;
        dragPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -hit.pt.y);
        dragStart = { pt: hit.pt.clone(), pos: hit.obj.position.clone() };
        dragDelta = null;
        mode = 4;
      } else {
        clearSel();
        if (topMode) { mode = 2; return; }   // in exact-2D, L-drag pans
        const sp = surfPoint(e);             // SketchUp: orbit about the point
        if (sp) retarget(sp);                // the cursor is ON
        else if (homeCenter) retarget(homeCenter);
        mode = 1;
      }
    });
    addEventListener("mousemove", e => {
      if (!mode || !open) return;
      const dx = e.clientX - lx, dy = e.clientY - ly; lx = e.clientX; ly = e.clientY;
      if (mode === 1) {          // ORBIT about the grabbed point, SketchUp-style
        orbit.az -= dx * 0.008;
        orbit.el = Math.min(1.55, Math.max(-1.35, orbit.el + dy * 0.006));
      } else if (mode === 2) {
        if (topMode) {                       // exact-2D pan, pixel-true
          const rc = cv.getBoundingClientRect();
          const k2 = (orthoH * 2) / Math.max(1, rc.height);
          orbit.tx -= dx * k2; orbit.tz -= dy * k2;
        } else {
          const k = orbit.dist * 0.0016;
          orbit.tx += Math.cos(orbit.az + Math.PI / 2) * dx * k;
          orbit.tz += Math.sin(orbit.az + Math.PI / 2) * dx * k;
          orbit.ty += dy * k;
        }
      } else if (mode === 4 && dragEd) {         // slide along the floor plane
        const cvr = cv.getBoundingClientRect();
        const nd = new THREE.Vector2(
          ((e.clientX - cvr.left) / cvr.width) * 2 - 1,
          -((e.clientY - cvr.top) / cvr.height) * 2 + 1);
        raycaster.setFromCamera(nd, camera);
        const p = new THREE.Vector3();
        if (raycaster.ray.intersectPlane(dragPlane, p)) {
          dragDelta = { x: p.x - dragStart.pt.x, z: p.z - dragStart.pt.z };
          selObj.position.set(dragStart.pos.x + dragDelta.x, dragStart.pos.y,
            dragStart.pos.z + dragDelta.z);
          if (selHelper) selHelper.update();
        }
      }
    });
    addEventListener("mouseup", e => {
      if (mode === 4 && dragEd && dragDelta &&
          (Math.abs(dragDelta.x) > 0.05 || Math.abs(dragDelta.z) > 0.05)) {
        if (typeof pushUndo === "function") pushUndo();
        applyMove(dragEd, dragDelta.x, -dragDelta.z);   // three z = −plan y
        if (typeof redraw === "function") redraw();     // 2D follows
        const ref = dragEd.ref;
        rebuild();
        reselectRef(ref);          // keep the piece selected, props refreshed
      }
      mode = 0; dragEd = null; dragDelta = null;
    });
    addEventListener("keydown", e => {
      if (!open) return;
      const t = (document.activeElement || {}).tagName;
      if (t === "INPUT" || t === "TEXTAREA" || t === "SELECT") return;
      const k = (e.key || "").toLowerCase();
      if ("wasdqe".includes(k) && k.length === 1) { flyKeys[k] = true; e.preventDefault(); return; }
      if (selObj && (e.key === "Delete" || e.key === "Backspace")) { e.preventDefault(); deleteSel(); }
    });
    addEventListener("keyup", e => { flyKeys[(e.key || "").toLowerCase()] = false; });
    // Ctrl+Z / Ctrl+Y / Ctrl+S work INSIDE the 3D view too — app.js already
    // performs the undo/redo/save on the plan; here the model re-derives so
    // the 3D (and through redraw, every drawing) follows the same history
    addEventListener("keydown", e => {
      if (!open || !(e.ctrlKey || e.metaKey)) return;
      const k = (e.key || "").toLowerCase();
      if (k === "z" || k === "y")
        setTimeout(() => { clearSel(); rebuild(); }, 60);
    });
    cv.addEventListener("wheel", e => {
      if (!open) return;
      // no zoom while a drag (pan / move) is in progress — one thing at a time
      if (mode) { e.preventDefault(); return; }
      const f = e.deltaY > 0 ? 1.12 : 0.9;
      const rc = cv.getBoundingClientRect();
      if (topMode) {                 // 2D zoom, SketchUp-style: onto the cursor
        const relx = ((e.clientX - rc.left) / rc.width) * 2 - 1;
        const rely = ((e.clientY - rc.top) / rc.height) * 2 - 1;
        const asp = rc.width / Math.max(1, rc.height);
        const wx = orbit.tx + relx * orthoH * asp;
        const wz = orbit.tz + rely * orthoH;
        orbit.tx += (wx - orbit.tx) * (1 - f);
        orbit.tz += (wz - orbit.tz) * (1 - f);
        orthoH = Math.min(2000, Math.max(2, orthoH * f));
        orthoFrustum();
        e.preventDefault(); return;
      }
      // SKETCHUP zoom: dolly straight along the ray to the point the cursor
      // is ON (model surface, else the ground) — you fly INTO what you point
      const hp = surfPoint(e);
      if (hp) {
        const cp = camera.position, k = 1 - f;      // camera slides toward hp,
        orbit.tx += (hp.x - cp.x) * k;              // the pivot rides with it
        orbit.ty += (hp.y - cp.y) * k;
        orbit.tz += (hp.z - cp.z) * k;
      }
      orbit.dist = Math.min(1500, Math.max(1.5, orbit.dist * f));
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
        orbit.az -= dx * 0.008;
        orbit.el = Math.min(1.55, Math.max(-0.2, orbit.el + dy * 0.006));
      } else if (mode === 3 && e.touches.length === 2) {
        const d = Math.hypot(e.touches[0].clientX - e.touches[1].clientX,
          e.touches[0].clientY - e.touches[1].clientY);
        orbit.dist = Math.min(1500, Math.max(1.5, orbit.dist * (pinch / (d || 1))));
        pinch = d;
      }
      e.preventDefault();
    }, { passive: false });
    addEventListener("touchend", () => mode = 0);
    addEventListener("resize", resize);

    const on = (id, fn, ev) => { const e = $(id); if (e) e[ev || "onclick"] = fn; };
    on("#btn3D", openViewer);
    on("#v3close", closeViewer);
    on("#v3rebuild", rebuild);
    on("#v3iso", () => {
      exitTop();
      if (homeCenter) { orbit.tx = homeCenter.x; orbit.ty = homeCenter.y; orbit.tz = homeCenter.z; }
      orbit.az = -Math.PI / 4; orbit.el = Math.atan(1 / Math.sqrt(2));
    });
    // TOP-2D: true ORTHOGRAPHIC straight-down view, roof off — the EXACT
    // 2D plan, no perspective lean on the walls
    on("#v3top", () => {
      const r = $("#v3roof"); if (r) r.checked = false;
      syncLayers();
      enterTop();
    });
    const op = $("#v3op");
    if (op) op.oninput = () => setOpacity(op.value / 100);
    ["#v3walls", "#v3struct", "#v3stairs", "#v3roof", "#v3mumty", "#v3furn",
     "#v3plumb", "#v3elec", "#v3floor"].forEach(id =>
      on(id, syncLayers, "onchange"));
    on("#v3intop", syncLayers, "oninput");   // wall x-ray (electrical)
    on("#v3flop", syncLayers, "oninput");    // floor x-ray (plumbing)
    on("#v3sun", applySun, "oninput");       // sun / glare control
    on("#v3bwh", rebuild, "onchange");       // boundary-wall height
    // FACADE tools — drop a rectangle / disc into the model and edit it
    const addFace = shape => () => {
      if (!S.plan) return;
      if (!Array.isArray(S.plan.faces3d)) S.plan.faces3d = [];
      const c = homeCenter || { x: 0, z: 0 };
      if (typeof pushUndo === "function") pushUndo();
      const fc = { shape, x: Math.round((c.x + 0) * 4) / 4, y: 0, z: 5,
        w: 6, h: 4, r: 3, angle: 0, color: "#8fa3bf", opacity: 1 };
      S.plan.faces3d.push(fc);
      const fb = $("#v3faces"); if (fb) fb.checked = true;
      rebuild();
      reselectRef(fc);
      status("face added — drag it, or set its size in the panel");
    };
    on("#v3rect", addFace("rect"));
    on("#v3circ", addFace("circle"));
    ["#v3bwall", "#v3faces"].forEach(id => on(id, syncLayers, "onchange"));
    // LOCK buttons cover the new layers too (data-lock="faces")
    on("#v3para", rebuild, "onchange");
    // LAYER LOCK buttons — lock a layer and nothing in it can be edited
    document.querySelectorAll(".v3lock").forEach(b => {
      b.onclick = e => {
        e.preventDefault(); e.stopPropagation();
        const k = b.dataset.lock;
        locks[k] = !locks[k];
        b.textContent = locks[k] ? "🔒" : "🔓";
        b.classList.toggle("locked", locks[k]);
        if (locks[k] && selObj && LOCKOF[selObj.userData.edit.kind] === k) clearSel();
      };
    });
  }

  if (document.readyState === "loading") addEventListener("DOMContentLoaded", wire);
  else wire();
})();
