"""Outer building ELEVATIONS — the four faces (front / rear / left / right)
developed the way an architect draws them: the facade silhouette, the plinth,
floor and roof lines, every door / window on that face at its true position and
sill / lintel height (with a sunshade over each window), a parapet with coping,
and full dimensioning — a vertical height chain, a horizontal width chain and
level marks down the side.

Heights come from the SAME questionnaire the section uses (plinth, floor
height, slab, floors, parapet). Everything else is derived from the plan.
"""

from __future__ import annotations

import math

from .draw import DrawList
from . import section as S

MM = 304.8


def _mm(v):
    return (v or 0) / MM


FACES = [
    {"name": "FRONT ELEVATION", "axis": "x", "ndir": -1, "mirror": False},
    {"name": "REAR ELEVATION", "axis": "x", "ndir": 1, "mirror": True},
    {"name": "LEFT SIDE ELEVATION", "axis": "y", "ndir": -1, "mirror": True},
    {"name": "RIGHT SIDE ELEVATION", "axis": "y", "ndir": 1, "mirror": False},
]


def _heights(params):
    p = params or {}
    is_gf = bool(p.get("is_ground", True))
    plinth = _mm(p.get("plinth_mm", 0)) if is_gf else 0.0
    fh = _mm(p.get("floor_height_mm", 0)) or _mm(3000)
    slab = _mm(p.get("slab_thk_mm", 0)) or _mm(125)
    floors = max(1, int(p.get("floors", 1) or 1))
    para = _mm(p.get("parapet_mm", 0))
    return plinth, fh, slab, floors, para


def build_one(plan, params, face, floor_plans=None):
    dl = DrawList()
    L_CUT, L_SLAB, L_TXT, L_DIM = "SEC-CUT", "SEC-SLAB", "SEC-TEXT", "SEC-DIM"
    plinth, fh, slab, floors, para = _heights(params)
    ffl0 = plinth
    tops = [ffl0 + k * fh for k in range(floors + 1)]
    roof = tops[floors]
    top = roof + para
    coping = _mm(150) if para > 0 else 0.0

    axis, ndir, mirror = face["axis"], face["ndir"], face["mirror"]
    ext = [w for w in plan.walls
           if getattr(w, "exterior", False) and not getattr(w, "railing", False)]
    if not ext:
        return dl
    allc = [(w.x1 if axis == "x" else w.y1) for w in ext] + \
           [(w.x2 if axis == "x" else w.y2) for w in ext]
    lo, hi = min(allc), max(allc)
    width = hi - lo
    if width < 1e-3:
        return dl
    cx = sum((w.x1 + w.x2) / 2 for w in ext) / len(ext)
    cy = sum((w.y1 + w.y2) / 2 for w in ext) / len(ext)

    def U(coord):
        return (hi - coord) if mirror else (coord - lo)

    # the SOLID (roofed / enclosed) extent along this axis comes from the
    # enclosed rooms; an open verandah / terrace is NOT a full-height wall — it
    # shows only its floor + railing, exactly as the plan draws it.
    solid_rooms = [r for r in getattr(plan, "rooms", [])
                   if not getattr(r, "open_area", False)
                   and not getattr(r, "is_lawn", False)]
    if solid_rooms:
        if axis == "x":
            s0 = min(r.x for r in solid_rooms)
            s1 = max(r.x + r.w for r in solid_rooms)
            sp_lo = min(r.y for r in solid_rooms)     # perpendicular (depth)
            sp_hi = max(r.y + r.h for r in solid_rooms)
        else:
            s0 = min(r.y for r in solid_rooms)
            s1 = max(r.y + r.h for r in solid_rooms)
            sp_lo = min(r.x for r in solid_rooms)
            sp_hi = max(r.x + r.w for r in solid_rooms)
    else:
        s0, s1 = lo, hi
        sp_lo, sp_hi = -1e9, 1e9
    wall_t = 0.75                                     # 9" exterior wall
    s0 = max(lo, s0 - wall_t)                          # out to the wall faces
    s1 = min(hi, s1 + wall_t)
    su0, su1 = sorted((U(s0), U(s1)))

    # ---- facade silhouette (plan-accurate) --------------------------------
    dl.line(-1.6, 0, width + 1.6, 0, layer=L_SLAB)               # ground line
    for gx in _frange(-1.4, width + 1.4, 0.6):                   # earth ticks
        dl.line(gx, 0, gx - 0.28, -0.42, layer="SEC-EARTH")
    proj = 0.12
    # plinth runs the full width (the verandah floor sits on it too)
    S._fill_band(dl, -proj, 0, width + proj, ffl0, L_SLAB)
    # SOLID wall body only over the enclosed span
    dl.rect(su0, ffl0, su1 - su0, roof - ffl0, layer=L_CUT)
    for k in range(1, floors):                                   # floor lines
        dl.line(su0, tops[k], su1, tops[k], layer=L_SLAB, dashed=True)
    # the ROOF (+ parapet + coping) runs the FULL width — the verandah is
    # COVERED (roof above), open below on columns, exactly what the plan shows
    S._fill_band(dl, -proj, roof, width + proj, roof + slab, L_SLAB)
    if para > 0:
        dl.rect(0, roof + slab, width, para - slab, layer=L_CUT)
        S._fill_band(dl, -proj, roof + para, width + proj,
                     roof + para + coping, L_SLAB)
    # COLUMNS carrying the roof over the OPEN verandah — a pier ONLY at the
    # verandah's outer corner (no wall there). The solid block's own corners are
    # plain silhouette edges — an architect does NOT draw a wall-thickness line
    # at a corner that has no reveal, so none is added there.
    col_w = 0.75
    open_left = su0 > 0.1                  # open verandah bay to the left in U
    open_right = su1 < width - 0.1         # open verandah bay to the right in U
    # VERANDAH edge walls (the corner piers that flank the railing) — real
    # exterior walls that run along this face but sit OUT in the verandah,
    # beyond the enclosed block. Drawn as full-height piers carrying the roof.
    for w in plan.walls:
        if getattr(w, "railing", False) or not getattr(w, "exterior", False):
            continue
        horiz = abs(w.x2 - w.x1) > abs(w.y2 - w.y1)
        if (axis == "x") != horiz:         # need the wall's FACE (runs along U)
            continue
        mx, my = (w.x1 + w.x2) / 2, (w.y1 + w.y2) / 2
        pcoord = my if axis == "x" else mx
        ref = cy if axis == "x" else cx
        if (1 if pcoord > ref else -1) != ndir:       # not on the viewer's side
            continue
        if sp_lo - 0.6 <= pcoord <= sp_hi + 0.6:       # part of the main block
            continue
        a = w.x1 if axis == "x" else w.y1
        b = w.x2 if axis == "x" else w.y2
        pu0, pu1 = sorted((U(a), U(b)))
        if pu1 - pu0 > 0.05:
            S._fill_band(dl, pu0, ffl0, pu1, roof, L_CUT)   # verandah pier
    if open_left:
        _column(dl, 0, ffl0, roof, col_w, L_CUT)
        dl.line(su0, ffl0, su0, roof, layer=L_CUT)      # solid/verandah edge
    if open_right:
        _column(dl, width - col_w, ffl0, roof, col_w, L_CUT)
        dl.line(su1, ffl0, su1, roof, layer=L_CUT)      # solid/verandah edge

    # ---- openings on this face, at each floor -----------------------------
    # In a MULTI-FLOOR elevation each storey shows its OWN doors / windows,
    # read from that floor's own plan; otherwise every storey repeats the one
    # plan we were given.
    def _gather(src):
        res = []
        wid = {w.id: w for w in src.walls if getattr(w, "id", None)}
        for o in getattr(src, "openings", []):
            if getattr(o, "type", "") in ("gate", "open"):
                continue
            w = wid.get(o.wall_id)
            if not w or not getattr(w, "exterior", False):
                continue
            horiz = abs(w.x2 - w.x1) > abs(w.y2 - w.y1)
            if (axis == "x") != horiz:
                continue
            mx, my = (w.x1 + w.x2) / 2, (w.y1 + w.y2) / 2
            sign = (1 if (my if axis == "x" else mx) >
                    (cy if axis == "x" else cx) else -1)
            if sign != ndir:
                continue
            a = w.point_at(o.pos)
            b = w.point_at(o.pos + o.width)
            ca = a[0] if axis == "x" else a[1]
            cb = b[0] if axis == "x" else b[1]
            u0, u1 = sorted((U(ca), U(cb)))
            sill, lintel = S._open_levels(o)
            kind = "door" if getattr(o, "is_door", False) else (
                "vent" if o.type == "vent" else "window")
            res.append((u0, u1, sill, lintel, kind, o.tag or ""))
        return res

    if floor_plans and len(floor_plans) == floors:
        ops_by_floor = [_gather(fp) for fp in floor_plans]
    else:
        base_ops = _gather(plan)
        ops_by_floor = [base_ops for _ in range(floors)]
    ops = ops_by_floor[0]           # ground floor — drives the hdim / leaders

    for k in range(floors):
        base = tops[k]
        head_cap = tops[k + 1] - slab - 0.1
        for (u0, u1, sill, lintel, kind, tag) in ops_by_floor[k]:
            y0 = base + sill
            y1 = min(base + lintel, head_cap)
            if y1 - y0 < 0.3:
                continue
            S._elev_opening(dl, u0, u1, y0, y1, kind, tag, L_CUT, L_TXT)
            if kind != "door":                          # sunshade over windows
                S._fill_band(dl, u0 - 0.3, y1 + 0.02, u1 + 0.3, y1 + 0.14,
                             L_SLAB)

    # ---- railings on this face (open verandah / terrace edge) -------------
    rail_h = _mm(params.get("railing_mm", 0)) or _mm(1000)
    for w in plan.walls:
        if not getattr(w, "railing", False):
            continue
        horiz = abs(w.x2 - w.x1) > abs(w.y2 - w.y1)
        if (axis == "x") != horiz:
            continue
        # a railing that runs ALONG this elevation's axis spans the open bay and
        # is SEEN across it from either side. Whether it reads in the FOREGROUND
        # or BEHIND depends on which side of the building it sits: a rail on the
        # FAR side (opposite the viewer) is a background element, drawn light.
        mx, my = (w.x1 + w.x2) / 2, (w.y1 + w.y2) / 2
        perp = my if axis == "x" else mx
        ref = cy if axis == "x" else cx
        near = (1 if perp > ref else -1) == ndir
        ca = w.x1 if axis == "x" else w.y1
        cb = w.x2 if axis == "x" else w.y2
        u0, u1 = sorted((U(ca), U(cb)))
        # OPEN verandah bays (in U): the parts NOT covered by the solid block
        bays = []
        if open_left:
            bays.append((0.0, su0))
        if open_right:
            bays.append((su1, width))
        bay = None
        for b0, b1 in bays:
            if min(u1, b1) - max(u0, b0) > 0.3:
                bay = (b0, b1)
                break
        if bay:
            # side elevation: the rail sits in the open verandah bay — draw it
            # as a clean horizontal panel BETWEEN the wall and the column
            b0, b1 = bay
            r0 = max(u0, b0 + (col_w if b0 < 0.1 else 0.0))
            r1 = min(u1, b1 - (col_w if b1 > width - 0.1 else 0.0))
            if r1 - r0 > 0.3:
                _railing(dl, r0, r1, ffl0, rail_h,
                         L_CUT if near else "BEAM-WALL")
        elif near:
            # front / rear: the verandah runs the full width IN FRONT of the
            # building — the near rail shows across; a FAR rail here is hidden
            # behind the solid building, so it is NOT drawn.
            _railing(dl, u0, u1, ffl0, rail_h, L_CUT)

    # ---- entrance STEPS — shown ONLY on the elevation you APPROACH them from
    # (the face at the bottom of the flight), never on the perpendicular faces
    for st in getattr(plan, "steps", []):
        sx, sy = getattr(st, "x", 0), getattr(st, "y", 0)
        sw, sh = getattr(st, "w", 0), getattr(st, "h", 0)
        n = max(1, int(getattr(st, "count", 1) or 1))
        run_axis = getattr(st, "run_axis", "x")
        up_from = str(getattr(st, "up_from", "left")).lower()
        low = up_from in ("left", "start", "bottom", "down", "west", "south")
        # the flight climbs along run_axis; you face it from the perpendicular
        # elevation whose view direction is along the run, on the bottom side
        want_axis = "y" if run_axis == "x" else "x"
        want_ndir = -1 if low else 1
        if axis != want_axis or ndir != want_ndir:
            continue
        if run_axis == "x":
            u0, u1 = sorted((U(sy), U(sy + sh)))       # stair WIDTH across face
        else:
            u0, u1 = sorted((U(sx), U(sx + sw)))
        if u1 - u0 < 0.05:
            continue
        # front view of the flight: its full width, with the tread nosing lines
        dl.rect(u0, 0, u1 - u0, ffl0, layer=L_CUT)
        for i in range(1, n):
            yy = ffl0 * i / n
            dl.line(u0, yy, u1, yy, layer=L_CUT)

    # ---- dimensions -------------------------------------------------------
    segs = []
    if plinth > 0:
        segs.append((0, ffl0, round(plinth * MM)))
    for k in range(floors):
        segs.append((tops[k], tops[k + 1], round(fh * MM)))
    if para > 0:
        segs.append((roof, top, round(para * MM)))
    S._dim_stack(dl, -2.2, segs, L_DIM)

    ticks = [0.0, width]
    for (u0, u1, *_r) in ops:
        ticks += [u0, u1]
    ybot = S._hdim_chain(dl, -1.4, ticks, 0, width, 0, L_DIM)

    ax = width + 1.8
    # level datums down the right — reference names (INTERNAL RD / PLINTH / SILL
    # / LINTEL / ROOF SLAB / PARAPET), drawn as dashed datum lines + half-filled
    # level bubbles + 'LVL. +X'-Y"' (see section._level_marks).
    ents = [(0.0, width, "INTERNAL RD")]
    if ffl0 > 0.02:
        ents.append((ffl0, width, "PLINTH"))
    for k in range(1, floors):
        ents.append((tops[k], width, "FLOOR"))
    ents.append((roof, width, "ROOF SLAB"))
    if para > 0:
        ents.append((top + coping, width, "PARAPET"))
    # one representative sill / lintel level for the ground floor
    grd = [(sill, lintel) for (_a, _b, sill, lintel, kind, _t) in ops
           if kind != "door"]
    if grd:
        sill, lintel = grd[0]
        ents.append((ffl0 + sill, width * 0.5, "SILL"))
        ents.append((ffl0 + lintel, width * 0.5, "LINTEL"))
    S._level_marks(dl, ax, ents, L_DIM)

    ty = (ybot if ybot is not None else -1.4) - 1.2
    dl.text(width / 2, ty, face["name"], h=0.55, layer=L_TXT, bold=True)
    dl.text(width / 2, ty - 0.75, f"OVERALL {round(width * MM)} WIDE  ·  "
            f"SCALE AS NOTED", h=0.26, layer="TEXT-SUB")
    return dl


def build_all(plan, params, floor_plans=None):
    """The four elevations in a 2 x 2 block, each in its own titled frame.

    Pass `floor_plans` (ground first) for a MULTI-FLOOR elevation: every
    storey then carries its own floor's doors / windows."""
    out = DrawList()
    parts = []
    for f in FACES:
        d = build_one(plan, params, f, floor_plans=floor_plans)
        if d.items:
            parts.append(d)
    if not parts:
        return out
    # bounds of each, then arrange in a 2-column grid
    gap = 6.0
    boxes = [p.bounds() for p in parts]
    ws = [b[2] - b[0] for b in boxes]
    hs = [b[3] - b[1] for b in boxes]
    colw = max(ws) + gap
    rowh = max(hs) + gap + 3.0
    for i, (p, b) in enumerate(zip(parts, boxes)):
        r, c = divmod(i, 2)
        dx = c * colw - b[0]
        dy = -r * rowh - b[1]
        out.extend(p.translated(dx, dy))
    return out


def build_project(floor_plans, params):
    """A MULTI-FLOOR elevation set: the building's four faces developed to its
    full height, every storey carrying its OWN floor's openings. `floor_plans`
    is ground-first; the outer silhouette comes from the ground plan (same
    footprint) and the storey count is taken from the list."""
    n = max(1, len(floor_plans or []))
    base = floor_plans[0] if floor_plans else None
    prm = dict(params or {})
    prm["floors"] = n
    return build_all(base, prm, floor_plans=floor_plans if n > 1 else None)


def _column(dl, u0, base, top, w, layer):
    """A verandah pier / column carrying the roof — a solid vertical member with
    a small capital, so the open bay reads with a proper support (the wall
    thickness shown as a column)."""
    if top <= base:
        return
    S._fill_band(dl, u0, base, u0 + w, top, layer)         # column shaft
    dl.rect(u0 - 0.1, top - 0.15, w + 0.2, 0.18, layer=layer)   # capital


def _step_profile(dl, u0, u1, base, top, n, layer):
    """A flight of `n` steps rising from (u0, base) to (u1, top), drawn as the
    classic stepped riser/tread profile closed back to the ground."""
    if top <= base or u1 <= u0:
        return
    rise = (top - base) / n
    run = (u1 - u0) / n
    pts = [(u0, base)]
    xx = u0
    for i in range(n):
        yy = base + (i + 1) * rise
        pts.append((xx, yy))                 # riser up
        xx = u0 + (i + 1) * run
        pts.append((xx, yy))                 # tread across
    pts.append((xx, base))                    # close down to the ground
    for a, b in zip(pts, pts[1:]):
        dl.line(a[0], a[1], b[0], b[1], layer=layer)


def _railing(dl, u0, u1, base, h, layer):
    """A balustrade in elevation: top & bottom rails, end posts and evenly
    spaced vertical balusters between them."""
    if u1 - u0 < 0.2 or h <= 0:
        return
    top = base + h
    bot = base + 0.12
    # end posts
    for x in (u0, u1):
        dl.rect(x - 0.05, base, 0.1, h, layer=layer)
    # top hand-rail (two lines) and a bottom rail — all in the given layer so a
    # BACKGROUND rail (light layer) reads as behind, a foreground one as solid
    dl.line(u0, top, u1, top, layer=layer)
    dl.line(u0, top - 0.1, u1, top - 0.1, layer=layer)
    dl.line(u0, bot, u1, bot, layer=layer)
    # vertical balusters ~150 mm c/c
    step = 0.5
    x = u0 + step
    while x < u1 - 0.05:
        dl.line(x, bot, x, top - 0.1, layer=layer)
        x += step


def _frange(a, b, step):
    x = a
    while x <= b:
        yield x
        x += step
