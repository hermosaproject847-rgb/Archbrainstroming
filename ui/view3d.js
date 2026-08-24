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
  let extMats = [];
  let G = {};                                // named groups (toggle layers)
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
    return {
      ext,
      int_: new THREE.MeshLambertMaterial({ color: 0xece6da }),
      conc: new THREE.MeshLambertMaterial({ color: 0x99a0a8 }),
      slab: new THREE.MeshLambertMaterial({ color: 0xc7cbd1 }),
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
        // door split + handles on the FRONT (opposite the back)
        const fx = -back[0], fy = -back[1];
        const runW = Math.abs(fx) ? h : w;
        for (const s of [-1, 1])
          lb(Math.abs(fx) ? 0.06 : runW / 2 - 0.15,
            Math.abs(fx) ? runW / 2 - 0.15 : 0.06, hgt - 0.2,
            fx * (w / 2 + 0.03) + (Math.abs(fx) ? 0 : s * runW / 4),
            fy * (h / 2 + 0.03) + (Math.abs(fy) ? 0 : s * runW / 4),
            hgt / 2, panel);
        for (const s of [-1, 1])
          lc(0.05, 0.8, fx * (w / 2 + 0.1) + (Math.abs(fx) ? 0 : s * 0.35),
            fy * (h / 2 + 0.1) + (Math.abs(fy) ? 0 : s * 0.35),
            hgt * 0.5, lam(0x2e2e2e));
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
      g.add(grp);
    }
  }

  /* ---------------------------------------------- plumbing pipes in 3D */
  const PIPE3D = { CW: 0x0d47a1, HW: 0xd32f2f, SOIL: 0xe8590c, WASTE: 0x2e9e2e,
    VENT: 0x1b8a3a, STORM: 0x00acc1, ACD: 0xad1457 };
  const STACK3D = { SS: 0xe8590c, WS: 0x2e9e2e, VP: 0x1b8a3a, RWP: 0x00acc1,
    CWD: 0x0d47a1, HWD: 0xd32f2f };
  function addPipes(g, plan, z0, fh) {
    // wet rooms (toilet / bath) — supply there runs LOW, concealed in the
    // wall band at fixture level; nothing rises to the ceiling off a WC,
    // shower or wash-basin. Ceiling running + drops are for the DRY areas.
    const wet = (plan.rooms || []).filter(r =>
      /toilet|bath|w\.?c|wash/i.test(r.name || ""));
    const inWet = (x, y) => wet.some(r =>
      x >= r.x - 0.6 && x <= r.x + r.w + 0.6 &&
      y >= r.y - 0.6 && y <= r.y + r.h + 0.6);
    for (const r of (plan.pipes || [])) {
      const P = r.pts || []; if (P.length < 2) continue;
      const col = PIPE3D[r.system] || 0x888888;
      const mat = new THREE.MeshLambertMaterial({ color: col });
      const rad = Math.max(0.08, ((+r.dia_mm || 50) * MM) / 2);
      const supply = (r.system === "CW" || r.system === "HW" || r.system === "ACD");
      const allWet = supply && P.every(p => inWet(p[0], p[1]));
      // MEP levels: wet-room DRAINAGE lives INSIDE THE SUNK — below the
      // finished floor, it ends there and never shows above; outside the wet
      // zone it runs at ground level to the chambers. Wet-room supply is the
      // low concealed band; dry-area supply is at the ceiling with drops.
      const segZ = (a, b) => {
        if (supply) return allWet ? z0 + 1.5 : z0 + fh - 0.8;
        const midx = (a[0] + b[0]) / 2, midy = (a[1] + b[1]) / 2;
        return inWet(midx, midy) ? z0 - 0.25 : z0 + 0.2;
      };
      let prevZ = null;
      for (let i = 0; i < P.length - 1; i++) {
        const z = segZ(P[i], P[i + 1]);
        const c = cylBetween(P[i][0], P[i][1], z, P[i + 1][0], P[i + 1][1], z, rad, mat);
        if (c) g.add(c);
        if (prevZ !== null && Math.abs(prevZ - z) > 0.02) {
          const v = cylBetween(P[i][0], P[i][1], prevZ, P[i][0], P[i][1], z, rad, mat);
          if (v) g.add(v);                     // level change through the sunk edge
        }
        // joint ball at this segment's start vertex
        if (i > 0) {
          const j = new THREE.Mesh(new THREE.SphereGeometry(rad * 1.25, 10, 10), mat);
          j.position.set(P[i][0], z, -P[i][1]);
          g.add(j);
        }
        prevZ = z;
      }
      // PIPE DROPS: only where a CEILING-run supply arrives at a wet/fixture
      // point does it drop down — never a pipe rising out of a fixture
      if (supply && !allWet) {
        const zTop = z0 + fh - 0.8;
        for (const e of [P[0], P[P.length - 1]]) {
          if (!inWet(e[0], e[1])) continue;          // the source end stays up
          const d = cylBetween(e[0], e[1], zTop, e[0], e[1], z0 + 1.5, rad * 0.9, mat);
          if (d) g.add(d);
          const cap = new THREE.Mesh(new THREE.SphereGeometry(rad * 1.1, 10, 10), mat);
          cap.position.set(e[0], z0 + 1.5, -e[1]);
          g.add(cap);
        }
      }
    }
    // vertical STACKS / downtakes rise the full storey in their system colour
    for (const p of (plan.plumb || [])) {
      const sc = STACK3D[p.code];
      if (sc != null) {
        const mat = new THREE.MeshLambertMaterial({ color: sc });
        const st = cylBetween(p.x, p.y, z0, p.x, p.y, z0 + fh + 0.6, 0.19, mat);
        if (st) g.add(st);
        const clamp = new THREE.Mesh(new THREE.TorusGeometry(0.24, 0.05, 8, 14), mat);
        clamp.rotation.x = Math.PI / 2;
        clamp.position.set(p.x, z0 + fh / 2, -p.y);
        g.add(clamp);
      } else {                                     // traps / chambers markers
        g.add(box(0.8, 0.8, 0.35, p.x, p.y, z0 + 0.17,
          new THREE.MeshLambertMaterial({ color: 0x6d4c41 })));
      }
    }
  }

  /* ------------------------------------- electrical points + conduiting */
  function addElec(g, plan, z0, fh) {
    const ceil = z0 + fh - 0.15;
    const conduit = new THREE.MeshLambertMaterial({ color: 0xff8c1a });
    const byTag = {};
    (plan.elec || []).forEach(p => { if (p.tag) byTag[p.tag] = p; });
    for (const p of (plan.elec || [])) {
      if (p.visible === false) continue;
      const code = p.code || "SL";
      if (code === "SB" || code === "DB") {          // board plate at its height
        const hz = ((+p.height_mm || 1200) * MM);
        g.add(box(0.8, 0.25, 0.5, p.x, p.y, z0 + hz, new THREE.MeshLambertMaterial({ color: 0xf5f2ea })));
        // conduit: board → up to ceiling → along ceiling to each controlled fitting
        const up = cylBetween(p.x, p.y, z0 + hz, p.x, p.y, ceil, 0.05, conduit);
        if (up) g.add(up);
        (p.controls || []).forEach(tg => {
          const q = byTag[tg]; if (!q) return;
          const run = cylBetween(p.x, p.y, ceil, q.x, q.y, ceil, 0.05, conduit);
          if (run) g.add(run);
        });
      } else if (code === "CF") {                    // ceiling fan: rod + blades
        const rod = cylBetween(p.x, p.y, ceil, p.x, p.y, ceil - 1.0, 0.06,
          new THREE.MeshLambertMaterial({ color: 0x777d88 }));
        if (rod) g.add(rod);
        for (let k = 0; k < 3; k++) {
          const a = k * 2.094;
          const bl = box(1.8, 0.35, 0.06, p.x + Math.cos(a) * 0.95,
            p.y + Math.sin(a) * 0.95, ceil - 1.0,
            new THREE.MeshLambertMaterial({ color: 0x8a919c }));
          bl.rotation.y = -a;
          g.add(bl);
        }
      } else if (code === "AC") {                    // wall unit
        const m = box(3.2, 0.7, 0.9, p.x, p.y, z0 + ((+p.height_mm || 2175) * MM),
          new THREE.MeshLambertMaterial({ color: 0xf2f4f7 }));
        if (+p.angle) m.rotation.y = (+p.angle) * Math.PI / 180;
        g.add(m);
      } else {                                       // any light: warm disc
        const d = new THREE.Mesh(new THREE.CylinderGeometry(0.35, 0.35, 0.1, 14),
          new THREE.MeshLambertMaterial({ color: 0xffd76a }));
        d.position.set(p.x, ceil, -p.y);
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
      const mat = new THREE.MeshLambertMaterial({ map: t });
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
        strip(cutDoors(r.x + 0.2, r.x + r.w - 0.2, true, r.y), true, r.y, 0.2);
        strip(cutDoors(r.x + 0.2, r.x + r.w - 0.2, true, r.y + r.h), true, r.y + r.h, -0.2);
        strip(cutDoors(r.y + 0.2, r.y + r.h - 0.2, false, r.x), false, r.x, 0.2);
        strip(cutDoors(r.y + 0.2, r.y + r.h - 0.2, false, r.x + r.w), false, r.x + r.w, -0.2);
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
  function buildModel() {
    extMats = [];
    const M = mats();
    const P = params();
    const root = new THREE.Group();
    const base = S.plan; if (!base) return root;
    G = { walls: new THREE.Group(), roof: new THREE.Group(), struct: new THREE.Group(),
      stairs: new THREE.Group(), floor: new THREE.Group(), furn: new THREE.Group(),
      plumb: new THREE.Group(), elec: new THREE.Group(), top: new THREE.Group() };

    let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
    (base.walls || []).forEach(w => {
      x0 = Math.min(x0, w.x1, w.x2); y0 = Math.min(y0, w.y1, w.y2);
      x1 = Math.max(x1, w.x1, w.x2); y1 = Math.max(y1, w.y1, w.y2);
    });
    if (x1 <= x0) return root;
    const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;

    G.struct.add(box(x1 - x0 + 1, y1 - y0 + 1, Math.max(P.plinth, 0.1),
      cx, cy, Math.max(P.plinth, 0.1) / 2, M.conc));

    let topZ = P.plinth;
    for (let f = 0; f < P.floors; f++) {
      const plan = ((S.floors || [])[f] && S.floors[f].plan) || base;
      const z0 = P.plinth + f * P.fh;
      const H = P.fh;
      (plan.walls || []).forEach(w => { if (!w.railing) addWall(G.walls, plan, w, z0, H, P, M, cx, cy); });
      (plan.columns || []).forEach(c => {
        G.struct.add(box(Math.max(+c.w || 0.8, 0.3), Math.max(+c.h || 0.8, 0.3), H,
          c.x, c.y, z0 + H / 2, M.conc));
      });
      (plan.beams || []).forEach(b => {
        const L = Math.hypot(b.x2 - b.x1, b.y2 - b.y1); if (L < 0.1) return;
        const bw = ((+b.width_mm || 230) * MM), bd = ((+b.depth_mm || 300) * MM);
        const m = box(L, bw, bd, (b.x1 + b.x2) / 2, (b.y1 + b.y2) / 2,
          z0 + H - bd / 2, M.conc);
        m.rotation.y = Math.atan2(-(b.y2 - b.y1), (b.x2 - b.x1));
        G.struct.add(m);
      });
      // the slab is CUT OUT over every staircase (the stair well) — a slab
      // poured straight over the stair is exactly the amateur-model look
      const slabG = (f === P.floors - 1 ? G.roof : G.struct);
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
          const wallStrip = (wx0, wy0, wx1, wy1) => {
            const Lw = Math.hypot(wx1 - wx0, wy1 - wy0); if (Lw < 0.2) return;
            const m = box(Lw, mt, mh, (wx0 + wx1) / 2, (wy0 + wy1) / 2, mz + mh / 2, M.ext);
            m.rotation.y = Math.atan2(-(wy1 - wy0), (wx1 - wx0));
            G.roof.add(m);
          };
          // arrival side = where the return flight lands: the NEAR end, on the
          // half nearer the origin — leave a 3 ft door gap there
          const sx0 = st.x, sy0 = st.y, sx1 = st.x + st.w, sy1 = st.y + st.h;
          const doorW = 3;
          if (alongX) {
            const du = dirUp > 0 ? sx0 : sx1;         // near end x
            wallStrip(sx0, sy1, sx1, sy1);            // both long walls solid
            wallStrip(sx0, sy0, sx1, sy0);
            wallStrip(du, sy0, du, sy0 + (sy1 - sy0) / 2 - doorW / 2);
            wallStrip(du, sy0 + (sy1 - sy0) / 2 + doorW / 2, du, sy1);
            const far = dirUp > 0 ? sx1 : sx0;
            wallStrip(far, sy0, far, sy1);
          } else {
            const du = dirUp > 0 ? sy0 : sy1;
            wallStrip(sx0, sy0, sx0, sy1);
            wallStrip(sx1, sy0, sx1, sy1);
            wallStrip(sx0, du, sx0 + (sx1 - sx0) / 2 - doorW / 2, du);
            wallStrip(sx0 + (sx1 - sx0) / 2 + doorW / 2, du, sx1, du);
            const far = dirUp > 0 ? sy1 : sy0;
            wallStrip(sx0, far, sx1, far);
          }
          G.roof.add(box(st.w + 1.2, st.h + 1.2, P.slab,
            (sx0 + sx1) / 2, (sy0 + sy1) / 2, mz + mh + P.slab / 2, M.slab));
        }
      }
      addStairs(G.stairs, plan, z0, H, M);
      addFlooring(G.floor, plan, z0);
      addFurniture(G.furn, plan, z0);
      addPipes(G.plumb, plan, z0, H);
      addElec(G.elec, plan, z0, H);
      topZ = z0 + H + P.slab;
    }
    addTop(G.top, base, topZ, P, M, ($("#v3para") || {}).value || "parapet");

    Object.values(G).forEach(gr => root.add(gr));
    root.position.set(-cx, 0, cy);
    // apply the current layer checkboxes
    syncLayers();
    return root;
  }

  function syncLayers() {
    const on = id => { const e = $(id); return !e || e.checked; };
    if (!G.walls) return;
    G.roof.visible = on("#v3roof");
    G.top.visible = on("#v3roof");
    G.furn.visible = on("#v3furn");
    G.plumb.visible = on("#v3plumb");
    G.elec.visible = on("#v3elec");
    G.floor.visible = on("#v3floor");
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
    scene.add(new THREE.AmbientLight(0xffffff, 0.55));
    const hemi = new THREE.HemisphereLight(0xbcd2ff, 0x3a3126, 0.35);
    scene.add(hemi);
    const sun = new THREE.DirectionalLight(0xfff2dd, 0.85);
    sun.position.set(60, 90, 40);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.camera.left = -60; sun.shadow.camera.right = 60;
    sun.shadow.camera.top = 60; sun.shadow.camera.bottom = -60;
    scene.add(sun);
    const sun2 = new THREE.DirectionalLight(0xdde6ff, 0.22);
    sun2.position.set(-50, 40, -60); scene.add(sun2);
    scene.add(new THREE.GridHelper(200, 40, 0x37415a, 0x2a3248));
    // soft ground shadow catcher
    const ground = new THREE.Mesh(new THREE.PlaneGeometry(300, 300),
      new THREE.ShadowMaterial({ opacity: 0.28 }));
    ground.rotation.x = -Math.PI / 2;
    ground.receiveShadow = true;
    scene.add(ground);
    const model = buildModel();
    model.traverse(o => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
    scene.add(model);
    camera = new THREE.PerspectiveCamera(50, 1, 0.1, 2000);
    const p = params();
    orbit.ty = (p.plinth + p.floors * p.fh) / 2;
    orbit.dist = 90; orbit.az = -0.9; orbit.el = 0.55; orbit.tx = 0; orbit.tz = 0;
    open = true;
    const opInp = $("#v3op"); if (opInp) setOpacity(opInp.value / 100);
    resize(); loop();
  }
  function rebuild() { if (open) { closeViewer(); openViewer(); } }
  function closeViewer() { open = false; cancelAnimationFrame(raf); $("#view3d").classList.add("hidden"); }
  function resize() {
    if (!renderer || !open) return;
    const holder = $("#view3d");
    const w = holder.clientWidth, h = holder.clientHeight - 44;
    renderer.setSize(w, h, false);
    camera.aspect = w / h; camera.updateProjectionMatrix();
  }
  function loop() {
    if (!open) return;
    applyCam(); renderer.render(scene, camera);
    raf = requestAnimationFrame(loop);
  }
  function setOpacity(v) {
    extMats.forEach(m => { m.opacity = v; m.transparent = true; m.needsUpdate = true; });
  }

  /* --------------------------------------------------- controls wiring */
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
        orbit.el = Math.min(1.55, Math.max(-0.2, orbit.el + dy * 0.006));
      } else {
        const k = orbit.dist * 0.0016;
        orbit.tx -= Math.cos(orbit.az + Math.PI / 2) * dx * k;
        orbit.tz -= Math.sin(orbit.az + Math.PI / 2) * dx * k;
        orbit.ty += dy * k;
      }
    });
    addEventListener("mouseup", () => mode = 0);
    cv.addEventListener("wheel", e => {
      if (!open) return;
      orbit.dist = Math.min(400, Math.max(8, orbit.dist * (e.deltaY > 0 ? 1.12 : 0.9)));
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
        orbit.el = Math.min(1.55, Math.max(-0.2, orbit.el + dy * 0.006));
      } else if (mode === 3 && e.touches.length === 2) {
        const d = Math.hypot(e.touches[0].clientX - e.touches[1].clientX,
          e.touches[0].clientY - e.touches[1].clientY);
        orbit.dist = Math.min(400, Math.max(8, orbit.dist * (pinch / (d || 1))));
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
    on("#v3iso", () => { orbit.az = -Math.PI / 4; orbit.el = Math.atan(1 / Math.sqrt(2)); });
    // TOP-2D: straight down, roof off — the working 2D view inside the model
    on("#v3top", () => {
      const r = $("#v3roof"); if (r) r.checked = false;
      syncLayers();
      orbit.az = -Math.PI / 2; orbit.el = 1.55;
    });
    const op = $("#v3op");
    if (op) op.oninput = () => setOpacity(op.value / 100);
    ["#v3roof", "#v3furn", "#v3plumb", "#v3elec", "#v3floor"].forEach(id =>
      on(id, syncLayers, "onchange"));
    on("#v3para", rebuild, "onchange");
  }

  if (document.readyState === "loading") addEventListener("DOMContentLoaded", wire);
  else wire();
})();
