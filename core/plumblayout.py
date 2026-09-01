"""Plumbing, sanitary & drainage — the design pass.

Follows `Plumbing_Master_Prompt.docx` (NBC 2016 Part 9). Positions come from
the fixtures the plan already carries; every pipe is a polyline so its length
and fall are COMPUTED; every chamber invert is worked out from the run, never
typed; and the demand, tank, pump and RWP figures come from the formulae in
`plumbing.py` rather than being asserted.

Two-pipe system throughout: soil connects DIRECTLY to the chamber, only waste
passes a gully trap (§5).
"""

from __future__ import annotations

import math

from shapely.geometry import Point, box

from . import engine
from . import plumbing as P
from .model import Plan, PlumbPoint, PlumbRun

KEY_R = 0.42
KEY_GAP = 1.15


# ------------------------------------------------------------- geometry
def _clear(plan: Plan, room):
    b = box(room.x, room.y, room.x + room.w, room.y + room.h)
    solid = engine.wall_solid(plan)
    c = b.difference(solid) if not solid.is_empty else b
    if c.geom_type == "MultiPolygon":
        c = max(c.geoms, key=lambda g: g.area)
    return c


def _bounds(plan: Plan):
    xs = [w.x1 for w in plan.walls] + [w.x2 for w in plan.walls]
    ys = [w.y1 for w in plan.walls] + [w.y2 for w in plan.walls]
    return min(xs), max(xs), min(ys), max(ys)


def _snap_wall(clear, x, y, off=0.30):
    """A tap, valve or drop must land on solid wall (§15 cross-check)."""
    ring = clear.exterior
    p = ring.interpolate(ring.project(Point(x, y)))
    x0, y0, x1, y1 = clear.bounds
    dl_, dr, db, dt = p.x - x0, x1 - p.x, p.y - y0, y1 - p.y
    m = min(dl_, dr, db, dt)
    if m == dl_:
        return p.x + off, p.y, "W"
    if m == dr:
        return p.x - off, p.y, "E"
    if m == db:
        return p.x, p.y + off, "S"
    return p.x, p.y - off, "N"


def _in_opening(plan: Plan, x: float, y: float, tol=0.55) -> bool:
    for o in plan.openings:
        w = plan.wall(o.wall_id)
        if w is None:
            continue
        a, b = w.point_at(o.pos), w.point_at(o.pos + o.width)
        vx, vy = b[0] - a[0], b[1] - a[1]
        L2 = vx * vx + vy * vy or 1e-9
        t = max(0.0, min(1.0, ((x - a[0]) * vx + (y - a[1]) * vy) / L2))
        if math.hypot(x - (a[0] + vx * t), y - (a[1] + vy * t)) < tol:
            return True
    return False


def _slide_off_opening(plan, clear, x, y):
    if not _in_opening(plan, x, y):
        return x, y
    x0, y0, x1, y1 = clear.bounds
    horiz = min(abs(y - y0), abs(y - y1)) < min(abs(x - x0), abs(x - x1))
    for s in (0.4, -0.4, 0.8, -0.8, 1.3, -1.3, 1.9, -1.9, 2.6, -2.6):
        nx, ny = (x + s, y) if horiz else (x, y + s)
        if x0 <= nx <= x1 and y0 <= ny <= y1 and not _in_opening(plan, nx, ny):
            return nx, ny
    return x, y


def _nt_beside_wc(clear, wx, wy, side):
    """User rule: the nahani trap sits JUST BESIDE the WC on its own wall —
    about 1.5 ft to the WC's left along the wall (just past its body,
    flipped right when the wall ends) and 150 mm CLEAR OF THE WALL. Never
    on top of the WC, never in a far corner, never on another wall."""
    left = {"N": (-1, 0), "S": (1, 0), "E": (0, 1), "W": (0, -1)}[side]
    perp = {"N": (0, -1), "S": (0, 1), "E": (-1, 0), "W": (1, 0)}[side]
    off = 1.5                           # just past the WC body
    clr = 150.0 / 304.8 - 0.30          # wx/wy already sit 0.30 off the wall
    nx = wx + left[0] * off + perp[0] * clr
    ny = wy + left[1] * off + perp[1] * clr
    bx0, by0, bx1, by1 = clear.bounds
    if left[0]:
        if not (bx0 + 0.4 <= nx <= bx1 - 0.4):
            nx = wx - left[0] * off
        nx = min(max(nx, bx0 + 0.4), bx1 - 0.4)
    else:
        if not (by0 + 0.4 <= ny <= by1 - 0.4):
            ny = wy - left[1] * off
        ny = min(max(ny, by0 + 0.4), by1 - 0.4)
    return nx, ny


def _yard_side(plan: Plan, wet_xy: list) -> str:
    x0, x1, _y0, _y1 = _bounds(plan)
    mid = (x0 + x1) / 2
    left = sum(1 for x, _y in wet_xy if x <= mid)
    return "W" if left >= len(wet_xy) - left else "E"


def _yard(plan: Plan, y: float, side: str, out=2.6):
    x0, x1, _y0, _y1 = _bounds(plan)
    return (x0 - out if side == "W" else x1 + out), y


def _ortho(a, b):
    """An L-route between two points. Pipes run ALONG the building, never
    diagonally across it — a diagonal drain through a bedroom is not a run
    anyone can build, and it reads as a mistake on the sheet."""
    (ax, ay), (bx, by) = a, b
    if abs(ax - bx) < 1e-6 or abs(ay - by) < 1e-6:
        return [a, b]
    # turn on the longer leg first so the run hugs the wall it starts from
    if abs(bx - ax) >= abs(by - ay):
        return [a, (bx, ay), b]
    return [a, (ax, by), b]


# --------------------------------------------------------------- the run
def design(plan_dict: dict) -> tuple[dict, list[str]]:
    from dataclasses import asdict
    from . import autofix

    plan = Plan.from_dict(plan_dict)
    autofix.apply(plan)
    notes: list[str] = []

    if not plan.furniture:
        notes.append("There is no furniture yet. The plumbing follows the "
                     "fixtures — WC, basin, shower and kitchen counter — so "
                     "run Furniture Layout first for a proper result.")

    pts: list[PlumbPoint] = []
    runs: list[PlumbRun] = []
    n_key = {"n": 0}

    # Infrastructure carries its OWN tag on the plan (SS-1, IC-1, CO-2, KH-3),
    # so it needs no numbered key-note circle. Only the in-room fittings get a
    # circle — that is what keeps a small toilet from filling with circles.
    NO_KEY = {"SS", "WS", "VP", "RWP", "CWD", "HWD", "IC", "GT", "CO", "KH",
              "UGT", "OHT", "PUMP"}

    def add(code, x, y, room="", system="", dia=0.0, tag="", note=""):
        f = P.FIXTURES.get(code, (code, 0.0, ""))
        keyed = code not in NO_KEY
        if keyed:
            n_key["n"] += 1
        p = PlumbPoint(code=code, x=x, y=y, room=room,
                       key=n_key["n"] if keyed else 0,
                       system=system, dia_mm=dia, height_mm=f[1],
                       tag=tag or f"{code}{n_key['n']}",
                       note=note or P.KEYNOTES.get(code, f[0]))
        pts.append(p)
        return p

    def pipe(system, coords, dia, note=""):
        if len(coords) < 2:
            return
        # a two-point run is turned into an L — every pipe runs along the
        # building, never diagonally across it. Runs given with their own
        # corners are left alone.
        pts_ = _ortho(tuple(coords[0]), tuple(coords[1])) \
            if len(coords) == 2 else [tuple(c) for c in coords]
        runs.append(PlumbRun(system=system, pts=pts_, dia_mm=dia,
                             slope=P.slope_for(system, dia), note=note))

    # ---- 1. read the wet areas ----------------------------------------
    wet = []
    for room in sorted([r for r in plan.rooms if not r.void],
                       key=lambda r: (-round(r.y + r.h, 1), round(r.x, 1))):
        items = [f for f in plan.furniture
                 if P.is_plumb_fixture(f.kind)
                 and room.x <= f.x + f.w / 2 <= room.x + room.w
                 and room.y <= f.y + f.h / 2 <= room.y + room.h]
        if items:
            wet.append((room, items))
    if not wet:
        notes.append("No WC, basin, shower or kitchen counter found — nothing "
                     "to plumb.")
        res = dict(plan_dict)
        res["plumb"], res["pipes"], res["plumb_calc"] = [], [], {}
        return res, notes

    nts, soil_out, waste_out = [], [], []

    for room, items in wet:
        clear = _clear(plan, room)
        if clear.is_empty:
            continue
        rn = room.name

        def place(f, off=0.30):
            x, y, side = _snap_wall(clear, *f.centre, off)
            x, y = _slide_off_opening(plan, clear, x, y)
            return x, y, side

        shower = next((f for f in items if f.kind.startswith("shower")), None)
        wc = next((f for f in items if f.kind.startswith("wc")), None)
        basin = next((f for f in items if f.kind.startswith("basin")), None)
        counter = next((f for f in items if f.kind.startswith("counter")), None)
        wm = next((f for f in items if f.kind.startswith("washing")), None)

        # A toilet larger than 6 ft MUST have a shower (user rule / good
        # practice). If the sketch drew none, add a shower zone in the corner
        # farthest from the WC and the door, and note it.
        cx0, cy0, cx1, cy1 = clear.bounds
        long_dim = max(cx1 - cx0, cy1 - cy0)
        is_toilet = wc is not None or "toilet" in rn.lower() \
            or "bath" in rn.lower()
        shower_xy = None
        if shower is None and is_toilet and long_dim > 6.0:
            dp = _door_point(plan, room)
            wcc = wc.centre if wc else ((cx0 + cx1) / 2, (cy0 + cy1) / 2)
            corners = [(cx0 + 0.5, cy0 + 0.5), (cx1 - 0.5, cy0 + 0.5),
                       (cx1 - 0.5, cy1 - 0.5), (cx0 + 0.5, cy1 - 0.5)]

            def farness(c):
                dd = math.dist(c, wcc)
                if dp is not None:
                    dd += math.dist(c, dp)
                return dd
            shower_xy = max(corners, key=farness)
            notes.append(f"{rn}: {long_dim:.1f} ft long — a shower is "
                         "compulsory over 6 ft, so one has been added in the "
                         "dry corner. Confirm the layout.")

        # -- shower: arm / head / mixer on ONE line, NT at the low point
        if shower is not None or shower_xy is not None:
            if shower is not None:
                sx, sy, side = place(shower, 0.30)
                sctr = shower.centre
            else:
                sx, sy, side = _snap_wall(clear, *shower_xy, 0.30)
                sx, sy = _slide_off_opening(plan, clear, sx, sy)
                sctr = shower_xy
            add("SH", sx, sy, rn, "HW", P.D_HW_TAIL)
            add("SMX", sx, sy, rn, "CW", P.D_CW_TAIL)
            cx_, cy_ = sctr
            if wc is not None:
                # user rule: with a WC in the room the trap sits beside the
                # WC (1500 mm to its left along the wall); the shower waste
                # runs to it
                wxx, wyy, wside = place(wc, 0.30)
                nx, ny = _nt_beside_wc(clear, wxx, wyy, wside)
            else:
                nx, ny = (cx_, sy) if side in ("W", "E") else (sx, cy_)
            nt = add("NT", nx, ny, rn, "WASTE", P.D_WASTE_BRANCH)
            nts.append(nt)
            pipe("WASTE", [(sx, sy), (nx, ny)], P.D_WASTE_BRANCH,
                 "shower to nahani trap")
            notes.append(f"{rn}: shower head, mixer and nahani trap on one "
                         f"line; floor falls 1:{P.SLOPES[('BATH', 0)]:g} to "
                         "the trap.")

        # -- WC: 2-way angle cock + health faucet on the RIGHT-hand side
        if wc is not None:
            wx, wy, side = place(wc, 0.30)
            add("WCAC", wx, wy, rn, "CW", P.D_CW_TAIL)
            dxy = {"W": (0, -1), "E": (0, 1), "S": (1, 0), "N": (-1, 0)}[side]
            add("HF", wx + dxy[0] * 0.85, wy + dxy[1] * 0.85, rn, "CW",
                P.D_CW_TAIL)
            soil_out.append(((wc.centre), rn))
            # §5 + user rule — the nahani trap sits JUST BESIDE the WC on
            # the SAME wall: 1500 mm to the WC's left ALONG the wall, hugging
            # it — never on top of the WC, never shifted to another wall
            # (unless the shower already put one in this room)
            if shower is None and shower_xy is None:
                nx, ny = _nt_beside_wc(clear, wx, wy, side)
                nt = add("NT", nx, ny, rn, "WASTE", P.D_WASTE_BRANCH)
                nts.append(nt)

        if basin is not None:
            bx, by, _s = place(basin, 0.30)
            add("BAC", bx, by, rn, "CW", P.D_CW_TAIL)
            add("BBT", bx, by - 0.55, rn, "WASTE", 32)
            near = min(nts, key=lambda t: math.dist((t.x, t.y),
                                                    basin.centre)) if nts \
                else None
            # SHORTEST-ROUTE rule: join a trap only when it is genuinely
            # near (same room) — never run a basin waste across the house
            if near is not None and math.dist((near.x, near.y),
                                              basin.centre) <= 8.0:
                pipe("WASTE", [(bx, by - 0.55), (near.x, near.y)], 32,
                     "basin bottle trap to the nahani trap")
            else:
                nt = add("NT", *basin.centre, rn, "WASTE", P.D_WASTE_BRANCH)
                nts.append(nt)

        if counter is not None:
            cx, cy, _s = place(counter, 0.30)
            add("SKC", cx, cy, rn, "CW", P.D_CW_TAIL)
            add("BBT", cx, cy - 0.55, rn, "WASTE", 40)
            nt = add("NT", cx + 1.2, cy, rn, "WASTE", P.D_WASTE_BRANCH)
            nts.append(nt)
            pipe("WASTE", [(cx, cy - 0.55), (nt.x, nt.y)], 40,
                 "sink bottle trap to the nahani trap")

        if wm is not None:
            mx, my, _s = place(wm, 0.30)
            add("WMT", mx, my, rn, "CW", P.D_CW_TAIL)
            nt = add("NT", mx + 1.0, my, rn, "WASTE", P.D_WASTE_BRANCH)
            nts.append(nt)

        # every wet room takes an isolation valve at its entry (§12)
        dp = _door_point(plan, room)
        if dp is not None and (wc is not None or shower is not None
                               or counter is not None):
            add("SV", dp[0], dp[1], rn, "CW", P.D_CW_BRANCH)

    waste_out = list(nts)

    # ---- 2. stacks, cleanouts and vents (§8) ---------------------------
    side = _yard_side(plan, [xy for xy, _r in soil_out]
                      + [(t.x, t.y) for t in waste_out])
    notes.extend(_stacks(plan, pts, runs, soil_out, waste_out, add, pipe))

    # ---- 3. drainage at ground: GT, IC, the main (§5, §9) --------------
    chambers, dn = _drainage(plan, pts, runs, soil_out, waste_out, side,
                             add, pipe)
    notes.extend(dn)

    # ---- 4. supply: UG tank, pump, OHT, down-takes (§3, §10) -----------
    calc, sn = _supply(plan, pts, runs, side, add, pipe)
    notes.extend(sn)

    # ---- 5. storm water (§7) -------------------------------------------
    notes.extend(_storm(plan, pts, runs, side, calc, add, pipe))

    # ---- 6. AC condensate (§11) ----------------------------------------
    notes.extend(_ac_drains(plan, pts, runs, nts, add, pipe))

    # ---- 7. garden taps (§2) -------------------------------------------
    notes.extend(_garden(plan, pts, add))

    _space_keynotes(pts)
    notes.extend(validate(plan, pts, runs))

    res = dict(plan_dict)
    res["plumb"] = [asdict(p) for p in pts]
    res["pipes"] = [asdict(r) for r in runs]
    res["plumb_calc"] = calc
    return res, notes


def _door_point(plan: Plan, room):
    best, bd = None, 1e18
    for o in plan.openings:
        if not o.is_door:
            continue
        w = plan.wall(o.wall_id)
        if w is None:
            continue
        pt = w.point_at(o.pos + o.width / 2)
        dx = max(room.x - pt[0], 0, pt[0] - (room.x + room.w))
        dy = max(room.y - pt[1], 0, pt[1] - (room.y + room.h))
        d = dx * dx + dy * dy
        if d < bd:
            best, bd = pt, d
    return best if bd <= 0.8 * 0.8 else None


def _stacks(plan, pts, runs, soil_out, waste_out, add, pipe):
    """§8 — one soil stack, one waste stack, a vent and the down-takes, each
    tagged so vertical continuity is checkable plan to plan, each with a
    cleanout at its base. On a row-house plot the stacks sit at the FIXED
    site by the porch wall (`_stack_site`) — the same x,y on every floor, so
    the first floor's pipes drop exactly onto the ground floor's gully trap
    and chamber line."""
    notes = []
    site = _stack_site(plan)
    if soil_out:
        if site is not None:
            sx, sy = site["ss"]
            room0 = site["porch"].name
        else:
            (sx, sy), room0 = soil_out[0][0], soil_out[0][1]
        st = add("SS", sx, sy, room0, "SOIL", P.D_SOIL, tag="SS-1")
        add("CO", sx + 0.8, sy, room0, "SOIL", P.D_SOIL, tag="CO-1")
        _bx0, _bx1, _by0, _by1 = _bounds(plan)
        vp = add("VP", min(max(sx, _bx0 + 0.3), _bx1 - 0.3),
                 min(max(sy + 1.1, _by0 + 0.3), _by1 - 0.3),
                 room0, "VENT", P.D_VENT, tag="VP-1")
        pipe("VENT", [(st.x, st.y), (vp.x, vp.y)], P.D_VENT,
             "vent stack, 600 above terrace with a cowl")
        for (cx, cy), rn in (soil_out if site is not None else soil_out[1:]):
            pipe("SOIL", [(cx, cy), (st.x, st.y)], P.D_SOIL,
                 "WC branch to the soil stack")
        notes.append("Soil stack SS-1 110 with vent VP-1 75 taken 600 above "
                     "the terrace with a cowl; cleanout CO-1 at its base.")
    if waste_out:
        if site is not None:
            wx, wy = site["ws"]
            ws = add("WS", wx, wy, site["porch"].name, "WASTE",
                     P.D_WASTE_STACK, tag="WS-1")
        else:
            wx, wy = waste_out[0].x, waste_out[0].y
            ws = add("WS", wx, wy - 0.9, waste_out[0].room, "WASTE",
                     P.D_WASTE_STACK, tag="WS-1")
        add("CO", ws.x + 0.8, ws.y, ws.room, "WASTE",
            P.D_WASTE_STACK, tag="CO-2")
        # SHORTEST-ROUTE rule: each trap joins the NEAREST point already on
        # the waste line (a tee at that trap), not the stack directly — the
        # kitchen's waste tees into the adjacent toilet's line instead of
        # running the length of the house on its own pipe.
        nodes = [(ws.x, ws.y)]
        rem = list(waste_out)
        while rem:
            bt, bn, bd = None, None, 1e18
            for t in rem:
                for n in nodes:
                    # pipes run orthogonally, so the REAL run length is the
                    # Manhattan distance, not the crow-fly one
                    dd = abs(t.x - n[0]) + abs(t.y - n[1])
                    if dd < bd:
                        bt, bn, bd = t, n, dd
            pipe("WASTE", [(bt.x, bt.y), bn], P.D_WASTE_STACK,
                 "nahani trap tees into the nearest waste line")
            nodes.append((bt.x, bt.y))
            rem.remove(bt)
        notes.append("Waste stack WS-1 75 collects the nahani traps — each "
                     "trap tees into the nearest waste line (shortest "
                     "route); cleanout CO-2 at its base.")
    if site is not None and (soil_out or waste_out):
        notes.append("Row-house rule: both stacks drop AGAINST THE WALL by "
                     f"the {site['porch'].name}, to one side clear of the "
                     "entry — the same point on every floor, directly over "
                     "the gully trap / chamber line.")
    return notes


def _porch(plan: Plan):
    """The open forecourt. On a row-house plot the neighbours abut the side
    walls, so there IS no side yard — the porch is the only open ground and
    the drainage line belongs there. An upper floor has no porch: its OPEN
    TERRACE (over the porch) is the open ground instead, so the row-house
    rule still holds and nothing is drawn outside the plot line."""
    for key in ("porch", "parking", "court", "yard", "verandah", "terrace"):
        cands = [r for r in plan.rooms
                 if not getattr(r, "void", False)
                 and key in (r.name or "").lower()]
        if cands:
            return max(cands, key=lambda r: r.w * r.h)
    return None


def _porch_front(plan: Plan, porch) -> str:
    """The road-front edge. On a row-house plot the neighbours abut the LONG
    sides, so the road is on a SHORT side — pick the nearer short-side edge.
    The rule is pure plot geometry, so EVERY floor computes the same front
    (porch below, open terrace above) and the stacks line up plan over plan."""
    x0, x1, y0, y1 = _bounds(plan)
    px0, py0 = porch.x, porch.y
    px1, py1 = porch.x + porch.w, porch.y + porch.h
    d = {"S": abs(py0 - y0), "N": abs(y1 - py1),
         "W": abs(px0 - x0), "E": abs(x1 - px1)}
    cand = ("S", "N") if (y1 - y0) >= (x1 - x0) else ("W", "E")
    return min(cand, key=lambda k: d[k])


def _stack_site(plan: Plan):
    """The ONE place the house's stacks come down: against the wall where the
    building meets the porch, to ONE SIDE — clear of the entry — so every
    floor drops its pipes at the SAME x,y, straight over the gully trap and
    the chamber line below (user rule: 'pipe wall ke sahare utrenge')."""
    porch = _porch(plan)
    if porch is None:
        return None
    x0, x1, y0, y1 = _bounds(plan)
    px0, py0 = porch.x, porch.y
    px1, py1 = porch.x + porch.w, porch.y + porch.h
    front = _porch_front(plan, porch)
    horiz = front in ("S", "N")
    lo, hi = (px0, px1) if horiz else (py0, py1)
    # the entry: doors / gates ON THE HOUSE WALL or the ROAD EDGE of the
    # porch (a door in a side wall is not the entry path) — the stacks go to
    # the side FARTHER from them. No entry on this floor -> the near end
    # (lo + 1.3), the same deterministic end on every floor.
    wall_edges = ((py1, py0) if front == "S" else (py0, py1)) if horiz else \
                 ((px1, px0) if front == "W" else (px0, px1))
    mids = []
    for o in plan.openings:
        if not (getattr(o, "is_door", False) or o.type in ("gate", "open")):
            continue
        w = plan.wall(o.wall_id)
        if w is None:
            continue
        try:
            m = w.point_at(o.pos + o.width / 2)
        except Exception:
            continue
        if not (px0 - 0.5 <= m[0] <= px1 + 0.5
                and py0 - 0.5 <= m[1] <= py1 + 0.5):
            continue
        across = m[1] if horiz else m[0]
        if min(abs(across - wall_edges[0]), abs(across - wall_edges[1])) > 1.5:
            continue                       # a side-wall door, not the entry
        mids.append(m[0] if horiz else m[1])
    if mids:
        em = sum(mids) / len(mids)
        side_v = lo + 1.3 if abs(em - lo) >= abs(hi - em) else hi - 1.3
    else:
        side_v = lo + 1.3
    away = 1.8 if side_v < (lo + hi) / 2 else -1.8
    if horiz:
        sy = (py1 - 0.4) if front == "S" else (py0 + 0.4)
        ss, ws = (side_v, sy), (side_v + away, sy)
    else:
        sx_ = (px1 - 0.4) if front == "W" else (px0 + 0.4)
        ss, ws = (sx_, side_v), (sx_, side_v + away)
    return {"porch": porch, "front": front, "horiz": horiz,
            "ss": ss, "ws": ws, "side_v": side_v}


def _drainage_porch(plan, porch, pts, runs, add, pipe):
    """Row-house drainage (§5, §9): the stacks drop against the porch wall to
    one side (clear of the entry), the gully trap and the chambers sit right
    under them, and the external main runs straight down that side and out
    through the road front — the shortest possible route. An upper floor
    draws NO chambers: its stacks drop onto the ground floor's line."""
    notes = []
    x0, x1, y0, y1 = _bounds(plan)
    site = _stack_site(plan)
    front = site["front"]
    horiz = site["horiz"]
    ss = next((q for q in pts if q.code == "SS"), None)
    ws = next((q for q in pts if q.code == "WS"), None)
    if "terrace" in (porch.name or "").lower():
        if ss is not None or ws is not None:
            notes.append("Upper floor: the soil / waste stacks drop straight "
                         "down at this point — the gully trap and the "
                         "chambers sit on the GROUND-FLOOR plan directly "
                         "below (one house, one drainage).")
        return [], notes
    dvx, dvy = {"S": (0, -1), "N": (0, 1),
                "W": (-1, 0), "E": (1, 0)}[front]     # toward the road
    chambers = []
    if ss is not None:
        ic = add("IC", ss.x + dvx * 1.6, ss.y + dvy * 1.6, porch.name,
                 "SOIL", P.D_SOIL)
        chambers.append(ic)
        pipe("SOIL", [(ss.x, ss.y), (ic.x, ic.y)], P.D_SOIL,
             "soil stack drops by the wall, DIRECT to the chamber")
    if ws is not None:
        gt = add("GT", ws.x + dvx * 1.6, ws.y + dvy * 1.6, porch.name,
                 "WASTE", P.D_WASTE_STACK)
        pipe("WASTE", [(ws.x, ws.y), (gt.x, gt.y)], P.D_WASTE_STACK,
             "waste stack drops by the wall to the gully trap")
        base = ss if ss is not None else ws
        ic = add("IC", base.x + dvx * 3.4, base.y + dvy * 3.4, porch.name,
                 "WASTE", P.D_EXT_DRAIN)
        chambers.append(ic)
        pipe("WASTE", [(gt.x, gt.y), (ic.x, ic.y)], P.D_EXT_DRAIN,
             "gully trap to the chamber")
        notes.append("Two-pipe system: the soil stack enters the chamber "
                     "directly; only the waste stack passes a gully trap.")

    # the main runs down the chosen side of the porch — wall to road —
    # inverts computed, and leaves the plot through the road front
    chambers.sort(key={"S": (lambda c: -c.y), "N": (lambda c: c.y),
                       "W": (lambda c: -c.x), "E": (lambda c: c.x)}[front])
    prev = None
    for i, c in enumerate(chambers, start=1):
        c.tag = f"IC-{i}"
        c.cover_m = 0.0
        if prev is None:
            c.invert_m = -0.60
        else:
            dd = math.dist((prev.x, prev.y), (c.x, c.y))
            c.invert_m = P.invert_after(prev.invert_m, dd,
                                        P.SLOPES[("EXT", 160)])
            pipe("SOIL", [(prev.x, prev.y), (c.x, c.y)], P.D_EXT_DRAIN,
                 "external main along the porch")
        if (c.cover_m - c.invert_m) * 1000 < P.IC_MIN_DEPTH_MM:
            c.invert_m = c.cover_m - P.IC_MIN_DEPTH_MM / 1000.0
        depth = (c.cover_m - c.invert_m) * 1000
        c.note = (f"{P.chamber_size(depth)} chamber, cover {c.cover_m:+.3f}, "
                  f"invert {c.invert_m:+.3f}")
        prev = c
    if prev is not None:
        out_xy = {"S": (prev.x, y0 - 2.0), "N": (prev.x, y1 + 2.0),
                  "W": (x0 - 2.0, prev.y), "E": (x1 + 2.0, prev.y)}[front]
        pipe("SOIL", [(prev.x, prev.y), out_xy], P.D_EXT_DRAIN,
             "external main out through the road front")
        notes.append(f"Row-house plot: drainage line in the {porch.name} "
                     f"(no side yard — the neighbours abut the walls); "
                     f"external main {P.D_EXT_DRAIN} at "
                     f"1:{P.SLOPES[('EXT', 160)]:g} leaves through the road "
                     f"front; last chamber inverts at {prev.invert_m:+.3f} m "
                     "— the intercepting chamber. VERIFY against the sewer.")
    return chambers, notes


def _drainage(plan, pts, runs, soil_out, waste_out, side, add, pipe):
    """§5, §9 — soil DIRECT to the chamber, waste through a gully trap first.
    Chambers at every junction and at not more than 30 m, inverts computed.
    With a porch on the plan the whole line moves THERE (row-house rule)."""
    porch = _porch(plan)
    if porch is not None:
        return _drainage_porch(plan, porch, pts, runs, add, pipe)
    notes = []
    chambers = []

    ss = next((q for q in pts if q.code == "SS"), None)
    ws = next((q for q in pts if q.code == "WS"), None)

    if ss is not None:
        ox, oy = _yard(plan, ss.y, side)
        ic = add("IC", ox, oy, ss.room, "SOIL", P.D_SOIL)
        chambers.append(ic)
        pipe("SOIL", [(ss.x, ss.y), (ox, ss.y), (ox, oy)], P.D_SOIL,
             "soil stack DIRECT to the chamber — never through a gully trap")
    if ws is not None:
        # The gully trap sits BETWEEN the building and the chamber line, not
        # on it: the external main runs down the chamber line, and a GT left
        # on that line would have the soil main running straight through it.
        gx, gy = _yard(plan, ws.y, side, 1.4)
        gt = add("GT", gx, gy, ws.room, "WASTE", P.D_WASTE_STACK)
        pipe("WASTE", [(ws.x, ws.y), (gx, ws.y), (gx, gy)], P.D_WASTE_STACK,
             "waste stack to the gully trap")
        icx, icy = _yard(plan, gy - 3.0, side)
        ic = add("IC", icx, icy, ws.room, "WASTE", P.D_EXT_DRAIN)
        chambers.append(ic)
        pipe("WASTE", [(gt.x, gt.y), (gt.x, icy), (icx, icy)],
             P.D_EXT_DRAIN, "gully trap to the chamber")
        notes.append("Two-pipe system: the soil stack enters the chamber "
                     "directly; only the waste stack passes a gully trap.")

    # the external main down the yard — chambers ordered along the flow
    chambers.sort(key=lambda c: -round(c.y, 1))
    max_ft = P.IC_MAX_SPACING_M / 0.3048
    chain = []
    for c in chambers:
        if chain:
            prev = chain[-1]
            d = math.dist((prev.x, prev.y), (c.x, c.y))
            for k in range(1, int(d / max_ft) + 1):
                t = k / (int(d / max_ft) + 1)
                chain.append(add("IC", prev.x + (c.x - prev.x) * t,
                                 prev.y + (c.y - prev.y) * t, c.room, "SOIL",
                                 P.D_EXT_DRAIN))
        chain.append(c)
    chambers = chain

    prev = None
    for i, c in enumerate(chambers, start=1):
        c.tag = f"IC-{i}"
        c.cover_m = 0.0
        if prev is None:
            c.invert_m = -0.60
        else:
            d = math.dist((prev.x, prev.y), (c.x, c.y))
            c.invert_m = P.invert_after(prev.invert_m, d,
                                        P.SLOPES[("EXT", 160)])
            pipe("SOIL", [(prev.x, prev.y), (c.x, c.y)], P.D_EXT_DRAIN,
                 "external main to the sewer")
        if (c.cover_m - c.invert_m) * 1000 < P.IC_MIN_DEPTH_MM:
            c.invert_m = c.cover_m - P.IC_MIN_DEPTH_MM / 1000.0
        depth = (c.cover_m - c.invert_m) * 1000
        c.note = (f"{P.chamber_size(depth)} chamber, cover {c.cover_m:+.3f}, "
                  f"invert {c.invert_m:+.3f}")
        prev = c
    if prev is not None:
        notes.append(f"External main {P.D_EXT_DRAIN} at "
                     f"1:{P.SLOPES[('EXT', 160)]:g} down the "
                     f"{'west' if side == 'W' else 'east'} yard; the last "
                     f"chamber inverts at {prev.invert_m:+.3f} m against an "
                     f"assumed sewer invert of {P.SEWER_INVERT_M:+.2f} m — "
                     "the final chamber is the intercepting chamber. VERIFY.")
    return chambers, notes


def _room_of(plan: Plan, x: float, y: float):
    """The room a point physically sits in — by position, so duplicate room
    names (two 'TOILET's) group separately."""
    best, bd = None, 1e18
    for r in plan.rooms:
        if r.void:
            continue
        dx = max(r.x - x, 0, x - (r.x + r.w))
        dy = max(r.y - y, 0, y - (r.y + r.h))
        dd = dx * dx + dy * dy
        if dd < bd:
            best, bd = r, dd
    return best


def _entry_side(plan, cx, cy, water_side):
    """Which building edge a wet area sits nearest — where its supply riser
    goes, outside that wall. Prefers the water-yard side when it is close."""
    x0, x1, y0, y1 = _bounds(plan)
    dist = {"W": cx - x0, "E": x1 - cx, "S": cy - y0, "N": y1 - cy}
    s = min(dist, key=dist.get)
    if dist.get(water_side, 1e9) <= dist[s] + 2.5:
        s = water_side
    return s


def _riser_point(plan, side, cx, cy, d):
    """A riser just OUTSIDE the given building edge, level with the wet area."""
    x0, x1, y0, y1 = _bounds(plan)
    if side == "W":
        return x0 - d, cy
    if side == "E":
        return x1 + d, cy
    if side == "S":
        return cx, y0 - d
    return cx, y1 + d


def _supply(plan, pts, runs, side, add, pipe):
    """§3, §10 — UG tank outside the footprint, pump, OHT, down-takes. All
    figures computed, and the tank kept clear of the drainage line."""
    notes = []
    x0, x1, y0, y1 = _bounds(plan)
    floor_sqm = (x1 - x0) * (y1 - y0) * 0.3048 * 0.3048
    garden_sqm = max(0.0, floor_sqm * 0.25)

    demand = P.water_demand(P.OCCUPANTS_DEFAULT, garden_sqm)
    tk = P.tanks(demand)
    lift = 9.0                     # UG invert to OHT inlet, single storey + OHT
    pm = P.pump(tk["oht_l"], lift)

    porch = _porch(plan)
    tside = "E" if side == "W" else "W"
    if porch is not None:
        # ROW-HOUSE rule: nothing outside the plot line. The UG tank and the
        # pump sit IN THE PORCH on its house side (clear of the chamber line
        # at the road front); the OHT sits above the stair / mumty.
        px0, py0 = porch.x, porch.y
        px1, py1 = porch.x + porch.w, porch.y + porch.h
        front = _porch_front(plan, porch)
        # the potable tank goes on the OPPOSITE side of the porch to the
        # stack / chamber line — never beside the sewer
        _site = _stack_site(plan)
        sv = _site["side_v"] if _site else None
        if front in ("S", "N"):
            ty = (py1 - 1.5) if front == "S" else (py0 + 1.5)
            left = sv is None or sv > (px0 + px1) / 2
            tx = (px0 + 1.8) if left else (px1 - 1.8)
            px_ = min(px1 - 1.5, tx + 3.0) if left else max(px0 + 1.5,
                                                            tx - 3.0)
            py_ = ty
        else:
            tx = (px1 - 1.5) if front == "W" else (px0 + 1.5)
            low = sv is None or sv > (py0 + py1) / 2
            ty = (py0 + 1.8) if low else (py1 - 1.8)
            px_ = tx
            py_ = min(py1 - 1.5, ty + 3.0) if low else max(py0 + 1.5,
                                                           ty - 3.0)
        st = plan.stairs[0] if getattr(plan, "stairs", None) else None
        ohx = getattr(st, "x", None) if st is not None else None
        if ohx is not None:
            ohx = st.x + getattr(st, "w", 0) / 2
            ohy = st.y + getattr(st, "h", 0) / 2
        else:
            ohx, ohy = (x0 + x1) / 2, (y0 + y1) / 2
    else:
        # the UG tank goes in the OPPOSITE yard to the drainage — NBC keeps a
        # potable tank away from the sewer line
        tx, ty = _yard(plan, y0 + (y1 - y0) * 0.30, tside, 4.2)
        px_, py_ = _yard(plan, y0 + (y1 - y0) * 0.30 + 3.2, tside, 4.2)
        ohx, ohy = _yard(plan, y1 - 2.0, tside, 4.2)
    # an upper floor (open terrace, no porch) has NO UG tank or pump — they
    # exist once, in the ground; only the OHT and the risers show here
    upper = porch is not None and "terrace" in (porch.name or "").lower()
    if not upper:
        add("UGT", tx, ty, "", "CW", P.D_CW_MAIN)
        add("PUMP", px_, py_, "", "CW", P.D_CW_MAIN)
        pipe("CW", [(tx, ty), (px_, py_)], P.D_CW_MAIN, "UG tank to the pump")
    add("OHT", ohx, ohy, "", "CW", P.D_CW_MAIN)
    if not upper:
        pipe("CW", [(px_, py_), (px_, ohy), (ohx, ohy)], P.D_CW_MAIN,
             "pump delivery riser to the OHT, NRV at delivery"
             + (" — riser up in the porch, run at terrace level"
                if porch is not None else ""))

    # THE DOWN-TAKE RUNS OUTSIDE THE BUILDING, never through a bedroom. Each
    # wet room is fed by a riser (CWD-k) just outside its OWN nearest external
    # wall; the feed from the OHT reaches that riser OVER THE TOP of the
    # building (never across the interior), and only the short branch from the
    # riser to each fitting is inside — and it stays inside that wet room.
    from collections import defaultdict
    groups = defaultdict(list)
    for q in pts:
        if q.system in ("CW", "HW") and q.code not in ("UGT", "PUMP", "OHT"):
            groups[id(_room_of(plan, q.x, q.y))].append(q)

    top = y1 + 3.0                       # the outside feed runs above the roof
    # ROW-HOUSE rule: the neighbours abut the walls, so a riser 1 ft OUTSIDE
    # the wall is on their land — with a porch on the plan the risers sit
    # just INSIDE the wall and the OHT feed runs at TERRACE level instead of
    # looping outside the plot line.
    d = 1.0 if porch is None else -0.35
    hd = d + 0.7 if porch is None else d - 0.65
    ri = 0
    internal = 0
    for qs in groups.values():
        cwq = [q for q in qs if q.system == "CW"]
        hwq = [q for q in qs if q.system == "HW"]
        cx = sum(q.x for q in qs) / len(qs)
        cy = sum(q.y for q in qs) / len(qs)
        s = _entry_side(plan, cx, cy, tside)
        if s is None:
            internal += 1
        s = s or tside
        rx, ry = _riser_point(plan, s, cx, cy, d)
        ri += 1
        add("CWD", rx, ry, "", "CW", P.D_CW_DOWN, tag=f"CWD-{ri}")
        if porch is None:
            # OHT -> this riser, entirely outside: over the roof, across, down
            pipe("CW", [(ohx, ohy), (ohx, top), (rx, top), (rx, ry)],
                 P.D_CW_DOWN, "cold water down-take, outside the building")
        else:
            pipe("CW", [(ohx, ohy), (ohx, ry), (rx, ry)], P.D_CW_DOWN,
                 "cold water feed at TERRACE level to the down-take riser "
                 "— inside the plot line")

        def branch(system, riser_xy, q, dia):
            rxx, ryy = riser_xy
            if s in ("W", "E"):
                pipe(system, [(rxx, ryy), (rxx, q.y), (q.x, q.y)], dia,
                     f"branch to {q.code}")
            else:
                pipe(system, [(rxx, ryy), (q.x, ryy), (q.x, q.y)], dia,
                     f"branch to {q.code}")

        for q in cwq:
            branch("CW", (rx, ry), q, P.D_CW_TAIL)

        # hot water: a geyser in this room if it has a shower, its own HWD
        if hwq:
            sh = next((q for q in qs if q.code == "SH"), hwq[0])
            g = add("GY", sh.x, sh.y - 1.4, sh.room, "HW", P.D_HW_DOWN)
            hx, hy = _riser_point(plan, s, cx, cy, hd)
            add("HWD", hx, hy, "", "HW", P.D_HW_DOWN, tag=f"HWD-{ri}")
            branch("CW", (rx, ry), g, P.D_CW_BRANCH)   # cold feed to geyser
            pipe("HW", [(g.x, g.y), (hx, hy)], P.D_HW_DOWN,
                 "hot water down-take, insulated")
            for q in hwq:
                branch("HW", (hx, hy), q, P.D_HW_TAIL)

    if internal:
        notes.append(f"{internal} wet area has no external wall — it needs a "
                     "vertical plumbing shaft; supply shown to its nearest "
                     "wall, confirm the shaft on site.")
    notes.append("Cold and hot down-takes run OUTSIDE the building to a riser "
                 "at each wet area; no supply pipe crosses a bedroom.")

    gy_room = next((q.room for q in pts if q.code == "SH"), None)
    if gy_room:
        notes.append(f"Geyser in {gy_room}, bottom {P.FIXTURES['GY'][1]} mm; "
                     "hot runs under a 8-10 m dead leg, hot LEFT cold RIGHT.")

    notes.append(f"Demand {demand['total_l']:.0f} L/day for "
                 f"{demand['occupants']} persons at {P.LPCD_TOTAL} lpcd "
                 f"({P.LPCD_DOMESTIC} domestic + {P.LPCD_FLUSHING} flushing) "
                 f"plus {demand['garden_l']:.0f} L garden.")
    notes.append(f"UG tank {tk['ug_l']:.0f} L ({tk['days']} days) "
                 f"{tk['ug_dims'][0]}x{tk['ug_dims'][1]}x{tk['ug_dims'][2]} m; "
                 f"OHT {tk['oht_l']:.0f} L "
                 f"{tk['oht_dims'][0]}x{tk['oht_dims'][1]}x"
                 f"{tk['oht_dims'][2]} m, 300 mm freeboard.")
    notes.append(f"Pump {pm['q_lpm']:.0f} LPM @ {pm['head_m']:.0f} m — "
                 f"{pm['hp']} HP, float switches both ends, NRV at delivery.")
    if porch is not None:
        notes.append(f"Row-house plot: UG tank and pump IN THE {porch.name}, "
                     "on its house side clear of the chamber line; OHT above "
                     "the stair / mumty; every supply run stays inside the "
                     "plot line — a potable tank is never beside a sewer.")
    else:
        notes.append("UG tank set in the opposite yard to the drainage, clear "
                     "of the chamber line — a potable tank is never beside a "
                     "sewer.")

    return {"demand": demand, "tanks": tk, "pump": pm,
            "floor_sqm": round(floor_sqm, 1),
            "lift_m": lift}, notes


def _storm(plan, pts, runs, side, calc, add, pipe):
    """§7 — khurras and rain-water pipes go ONLY on an open terrace, terrace or
    balcony, never on a bedroom wall. A khurra is a spout in a parapet; there
    is no parapet along a bedroom, so an RWP there is wrong. If this floor has
    no such open area, the roof water drains on the terrace level above and
    none is shown here."""
    notes = []
    roof = calc["floor_sqm"]
    rw = P.rwp_count(roof)
    calc["rwp"] = rw

    OPEN = ("terrace", "balcony", "verandah", "veranda", "deck", "roof",
            "sit out", "sitout", "chajja", "open")
    opens = [r for r in plan.rooms
             if r.open_area and not r.void
             and any(w in (r.name or "").lower() for w in OPEN)
             and "planter" not in (r.name or "").lower()]
    if not opens:
        notes.append("No open terrace / balcony on this floor — rain-water "
                     "pipes and khurras are shown on the terrace-level plan, "
                     "not here.")
        calc["rwp"] = {**rw, "count": 0}
        return notes

    # spread the RWP count across the open areas, largest first
    opens.sort(key=lambda r: r.w * r.h, reverse=True)
    n = max(P.RWP_MIN, rw["count"])
    made = 0
    k = 0
    while made < n:
        r = opens[made % len(opens)]
        k += 1
        # a corner of the open area, hard against its parapet, offset in
        cxr = r.x + (0.9 if (made // len(opens)) % 2 == 0 else r.w - 0.9)
        cyr = r.y + 0.9
        add("KH", cxr, cyr, r.name, "STORM", P.D_RWP, tag=f"KH-{k}")
        rp = add("RWP", cxr, cyr + 0.9, r.name, "STORM", P.D_RWP,
                 tag=f"RWP-{k}")
        # drop to grade at the nearest outside edge — never into the sewer.
        # Row-house plot (porch present): the spout stays INSIDE the plot
        # line, discharging at the terrace edge to the front storm channel.
        if _porch(plan) is not None:
            ex = r.x + 0.35 if abs(r.x - _bounds(plan)[0]) < abs(
                _bounds(plan)[1] - (r.x + r.w)) else r.x + r.w - 0.35
            pipe("STORM", [(rp.x, rp.y), (ex, rp.y)], P.D_RWP,
                 "RWP over a grating inside the plot to the front storm "
                 "channel — never the sewer")
        else:
            ex = r.x - 1.4 if abs(r.x - _bounds(plan)[0]) < abs(
                _bounds(plan)[1] - (r.x + r.w)) else r.x + r.w + 1.4
            pipe("STORM", [(rp.x, rp.y), (ex, rp.y)], P.D_RWP,
                 "RWP over a grating to the storm channel — never the sewer")
        made += 1
    notes.append(f"{n} rain-water pipes {P.D_RWP}Ø on the "
                 f"{', '.join(sorted({r.name for r in opens[:2]}))} "
                 f"(one per {rw['per_rwp_sqm']:.0f} sq.m, minimum {P.RWP_MIN}); "
                 "the open area falls 1:100 to each khurra.")
    return notes


def _ac_drains(plan, pts, runs, nts, add, pipe):
    """§11 — 25/32 at 1:50 from each indoor unit to the nearest nahani trap,
    discharging over an air gap, never sealed into a soil or waste pipe."""
    notes = []
    acs = [q for q in plan.elec if q.code == "AC"]
    if not acs or not nts:
        return notes
    for i, ac in enumerate(acs, start=1):
        nt = min(nts, key=lambda t: math.dist((t.x, t.y), (ac.x, ac.y)))
        pipe("ACD", [(ac.x, ac.y), (ac.x, nt.y), (nt.x, nt.y)], P.D_ACD,
             f"AC-{i} condensate to the nahani trap, air gap")
    notes.append(f"{len(acs)} AC condensate drains {P.D_ACD}Ø at "
                 f"1:{P.SLOPES[('ACD', 32)]:g} to the nearest nahani trap, "
                 "discharging over an air gap — never sealed into soil/waste.")
    return notes


def _garden(plan, pts, add):
    """§2 — a bib cock every 15-20 m round the periphery. On a row-house plot
    (porch present) the periphery IS the porch, so both taps sit there."""
    notes = []
    x0, x1, y0, y1 = _bounds(plan)
    porch = _porch(plan)
    if porch is not None:
        px0, py0 = porch.x, porch.y
        px1, py1 = porch.x + porch.w, porch.y + porch.h
        front = _porch_front(plan, porch)
        if front in ("S", "N"):
            gy = (py0 + 0.8) if front == "S" else (py1 - 0.8)
            spots = [(px0 + 1.0, gy), (px1 - 1.0, gy)]
        else:
            gx = (px0 + 0.8) if front == "W" else (px1 - 0.8)
            spots = [(gx, py0 + 1.0), (gx, py1 - 1.0)]
        for i, (gx, gy) in enumerate(spots, start=1):
            add("GBC", gx, gy, porch.name, "CW", P.D_CW_TAIL, tag=f"GBC-{i}")
        notes.append(f"2 garden bib cocks at {P.FIXTURES['GBC'][1]} mm in the "
                     f"{porch.name} — the only open ground on a row-house "
                     "plot; both inside the plot line.")
        return notes
    per_m = 2 * ((x1 - x0) + (y1 - y0)) * 0.3048
    n = max(2, int(per_m / P.GARDEN_TAP_SPACING_M))
    spots = [(x0 - 1.2, y0 + (y1 - y0) * (i + 0.5) / max(1, n // 2))
             for i in range(max(1, n // 2))]
    spots += [(x1 + 1.2, y0 + (y1 - y0) * (i + 0.5) / max(1, n - n // 2))
              for i in range(max(1, n - n // 2))]
    for i, (gx, gy) in enumerate(spots, start=1):
        add("GBC", gx, gy, "", "CW", P.D_CW_TAIL, tag=f"GBC-{i}")
    notes.append(f"{len(spots)} garden bib cocks at "
                 f"{P.FIXTURES['GBC'][1]} mm, about every "
                 f"{P.GARDEN_TAP_SPACING_M:.0f} m round a {per_m:.0f} m "
                 "periphery.")
    return notes


def _space_keynotes(pts) -> None:
    placed: list[tuple[float, float]] = []
    ring = [(math.cos(math.radians(a)), math.sin(math.radians(a)))
            for a in range(0, 360, 30)]
    for p in sorted(pts, key=lambda q: q.key):
        cand = [(0.0, 1.05)]
        for rad in (1.05, 1.6, 2.2, 2.9, 3.7, 4.6):
            cand += [(dx * rad, dy * rad) for dx, dy in ring]
        for dx, dy in cand:
            cx, cy = p.x + dx, p.y + dy
            if all(math.dist((cx, cy), q) >= KEY_GAP for q in placed):
                p.key_dx, p.key_dy = dx, dy
                placed.append((cx, cy))
                break
        else:
            p.key_dx, p.key_dy = 0.0, 1.05
            placed.append((p.x, p.y + 1.05))


# --------------------------------------------------- §15 cross-checks
def validate(plan: Plan, pts, runs) -> list[str]:
    out = []
    bad = [q for q in pts if q.height_mm and _in_opening(plan, q.x, q.y)]
    out.append(f"Plumbing check — taps/valves inside a punched opening: "
               f"{len(bad)} ({'FAIL' if bad else 'PASS'}).")

    # every shower and every WC has a nahani trap near it (§5)
    nts = [q for q in pts if q.code == "NT"]
    miss = 0
    for q in pts:
        if q.code in ("SH", "WCAC"):
            if not nts or min(math.dist((q.x, q.y), (t.x, t.y))
                              for t in nts) > 12.0:
                miss += 1
    out.append(f"Plumbing check — nahani trap serving every shower and WC: "
               f"{'PASS' if not miss else 'FAIL'} ({len(nts)} traps, "
               f"{miss} unserved).")

    # two-pipe discipline: no soil run may pass through a gully trap
    gts = [q for q in pts if q.code == "GT"]
    thru = 0
    for r in runs:
        if r.system != "SOIL":
            continue
        for g in gts:
            if any(math.dist(p, (g.x, g.y)) < 0.5 for p in r.pts):
                thru += 1
    out.append(f"Plumbing check — soil connects DIRECT to the chamber "
               f"(no gully trap in a soil run): "
               f"{'PASS' if not thru else 'FAIL'}.")

    ics = sorted([q for q in pts if q.code == "IC"],
                 key=lambda q: int((q.tag or "IC-0").split("-")[-1] or 0))
    falling = all(a.invert_m > b.invert_m
                  for a, b in zip(ics, ics[1:])) if len(ics) > 1 else True
    gaps = [math.dist((a.x, a.y), (b.x, b.y)) * 0.3048
            for a, b in zip(ics, ics[1:])]
    over = [g for g in gaps if g > P.IC_MAX_SPACING_M + 0.05]
    out.append(f"Plumbing check — {len(ics)} chambers, inverts falling: "
               f"{'PASS' if falling else 'FAIL'}; spacing <= "
               f"{P.IC_MAX_SPACING_M:g} m: {'PASS' if not over else 'FAIL'} "
               f"(longest {max(gaps) if gaps else 0:.1f} m).")

    # RWPs never discharge to a soil/waste line (§7)
    storm_ends = [r.pts[-1] for r in runs if r.system == "STORM"]
    clash = sum(1 for e in storm_ends for q in pts
                if q.code in ("IC", "GT") and math.dist(e, (q.x, q.y)) < 0.6)
    out.append(f"Plumbing check — rain water kept out of the sewer: "
               f"{'PASS' if not clash else 'FAIL'}.")

    cs = [(q.x + q.key_dx, q.y + q.key_dy) for q in pts if q.key]
    over_k = sum(1 for i, a in enumerate(cs) for b in cs[i + 1:]
                 if math.dist(a, b) < KEY_GAP - 0.02)
    out.append(f"Plumbing check — keynote circles clear of each other: "
               f"{'PASS' if not over_k else 'FAIL'} ({over_k} overlapping).")
    return out
