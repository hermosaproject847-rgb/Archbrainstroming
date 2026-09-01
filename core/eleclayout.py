"""Electrical and lighting layout.

Runs over a plan that already has its furniture, because the master prompt is
explicit that the layout follows the furniture: the fan centres on the bed
zone, the TV board sits behind the TV unit, bedside boards follow the pillow
end, the AC never blows on the pillow, the pendant centres on the dining TABLE
not the room.

Everything is computed. The standards are in electrical.py; nothing is read or
guessed.
"""

from __future__ import annotations

import math

from shapely.geometry import Point, box

from . import electrical as E
from . import engine
from . import furniture as F
from .model import Circuit, ElecPoint, Plan

M2_PER_SQFT = 0.092903

# the depth of the indoor unit's casing as elecsym draws it, so the layout can
# stand the point off the wall by exactly half of it and the back sits flush
AC_CASE_DEPTH_FT = 0.62

# any habitable room at least this large gets an AC even if its name does not
# classify as a living space (catches a mis-spelt "drawing hall")
AC_MIN_SQFT = 150.0

# a passage / lobby / foyer smaller than this is circulation only — light, no
# fan (nobody sits there long enough to need one)
FAN_MIN_PASSAGE_SQFT = 80.0

# a room this small takes no peripheral ring — just the calculated fittings
# spaced down its long axis (covers passages, dresses and small toilets)
SMALL_ROOM_NO_RING_SQFT = 55.0

# an open-to-sky area smaller than this (a planter strip) needs no light
OPEN_MIN_LIGHT_SQFT = 40.0


# --------------------------------------------------------------- helpers
def _clear(plan: Plan, room):
    b = box(room.x, room.y, room.x + room.w, room.y + room.h)
    solid = engine.wall_solid(plan)
    c = b.difference(solid) if not solid.is_empty else b
    if c.geom_type == "MultiPolygon":
        c = max(c.geoms, key=lambda g: g.area)
    return c


def _room_furniture(plan: Plan, room) -> list:
    """The pieces that stand in THIS room.

    A sketch can carry the same name twice — two rooms both written
    "BED ROOM" is normal — and matching on the name alone then hands each
    room the other's furniture as well, which doubles its boards and puts
    its fan over the wrong bed. Where the name repeats, fall back to where
    the piece actually sits.
    """
    n = (room.name or "").strip().lower()
    named = [f for f in plan.furniture if (f.room or "").strip().lower() == n]
    if sum(1 for r in plan.rooms
           if (r.name or "").strip().lower() == n) < 2:
        return named
    return [f for f in named
            if room.x <= f.x + f.w / 2 <= room.x + room.w
            and room.y <= f.y + f.h / 2 <= room.y + room.h]


def _find(items, *kinds):
    for f in items:
        if F.family(f.kind) in kinds or f.kind in kinds:
            return f
    return None


def snap_to_wall(clear, x: float, y: float, off: float = 0.18):
    """Put a point ON the nearest wall face of the room.

    A switchboard, a wall light and a socket are all fixed to a wall — none of
    them floats in the middle of a room. Everything that mounts on a wall goes
    through here, so it can never end up in the air.

    Returns (x, y, side) where side is the wall it sits on, N/S/E/W.
    """
    ring = clear.exterior
    d = ring.project(Point(x, y))
    p = ring.interpolate(d)
    x0, y0, x1, y1 = clear.bounds

    # which face it landed on, and the inward direction
    dl_, dr, db, dt = p.x - x0, x1 - p.x, p.y - y0, y1 - p.y
    m = min(dl_, dr, db, dt)
    if m == dl_:
        return p.x + off, p.y, "W"
    if m == dr:
        return p.x - off, p.y, "E"
    if m == db:
        return p.x, p.y + off, "S"
    return p.x, p.y - off, "N"


def wall_beside(clear, f, prefer=None, off: float = 0.18):
    """The point on a wall next to a piece of furniture.

    A board serving a bedside table sits on the wall the bed head is against,
    level with that table — not on top of the table.
    """
    cx, cy = f.centre
    side = prefer or getattr(f, "facing", None)
    x0, y0, x1, y1 = clear.bounds
    if side == "N":
        return cx, y1 - off, "N"
    if side == "S":
        return cx, y0 + off, "S"
    if side == "E":
        return x1 - off, cy, "E"
    if side == "W":
        return x0 + off, cy, "W"
    return snap_to_wall(clear, cx, cy, off)


def _door_of(plan: Plan, room):
    """(point, wall, opening) of the door serving this room.

    Matched by NAME and then by POSITION. Two rooms can share a name — two
    "BED ROOM"s each with their own door — and matching on the name alone
    returns the first room's door for both, so the second bedroom's board
    lands at the first bedroom's door. Among the doors that name this room,
    take the one whose mid-point actually sits on this room's boundary.
    """
    n = (room.name or "").strip().lower()
    pad = 0.75
    best = (None, None, None)
    best_d = 1e18
    for o in plan.openings:
        if not o.is_door or not o.swing or not o.swing.room:
            continue
        if o.swing.room.strip().lower() != n:
            continue
        w = plan.wall(o.wall_id)
        if not w:
            continue
        pt = w.point_at(o.pos + o.width / 2)
        # distance from the door mid-point to this room's box (0 if on it)
        dx = max(room.x - pt[0], 0, pt[0] - (room.x + room.w))
        dy = max(room.y - pt[1], 0, pt[1] - (room.y + room.h))
        d = dx * dx + dy * dy
        if d < best_d:
            best_d, best = d, (pt, w, o)
    if best_d <= pad * pad:
        return best
    return best if best[0] is not None else (None, None, None)


def _vent_of(plan: Plan, room):
    """(opening, wall, point) of the ventilator or window on a wall bounding
    this room — where a through-wall exhaust belongs. A real vent is preferred
    over a window."""
    best = None
    for o in plan.openings:
        if o.type not in ("vent", "window"):
            continue
        w = plan.wall(o.wall_id)
        if w is None:
            continue
        pt = w.point_at(o.pos + o.width / 2)
        dx = max(room.x - pt[0], 0, pt[0] - (room.x + room.w))
        dy = max(room.y - pt[1], 0, pt[1] - (room.y + room.h))
        if dx * dx + dy * dy > 0.6 * 0.6:            # not on this room's edge
            continue
        pref = 0 if o.type == "vent" else 1
        if best is None or pref < best[0]:
            best = (pref, o, w, pt)
    if best is None:
        return None
    return best[1], best[2], best[3]


# ------------------------------------------------------------ 1.3 fans
def place_fans(plan: Plan, room, clear, out: list, code: str,
               notes: list) -> list:
    """Default one fan at the room's geometric centre — the centre of the bed
    zone in a bedroom, of the seating zone in a living room. Two fans where a
    side is over 4.5 m or the area over 17 m²."""
    x0, y0, x1, y1 = clear.bounds
    w_m, h_m = (x1 - x0) * 0.3048, (y1 - y0) * 0.3048
    area_m2 = w_m * h_m
    n = E.fan_count(w_m, h_m)
    sweep = E.fan_sweep(area_m2 / n)

    items = _room_furniture(plan, room)
    anchor = _find(items, "bed") or _find(items, "sofa")

    centres = []
    if n == 1:
        if anchor is not None:
            cx, cy = anchor.centre
            # never directly over the pillow: pull back toward the room centre
            rc = ((x0 + x1) / 2, (y0 + y1) / 2)
            cx, cy = (cx + rc[0]) / 2, (cy + rc[1]) / 2
        else:
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        centres = [(cx, cy)]
    else:
        if (x1 - x0) >= (y1 - y0):
            centres = [(x0 + (x1 - x0) * 0.27, (y0 + y1) / 2),
                       (x0 + (x1 - x0) * 0.73, (y0 + y1) / 2)]
        else:
            centres = [((x0 + x1) / 2, y0 + (y1 - y0) * 0.27),
                       ((x0 + x1) / 2, y0 + (y1 - y0) * 0.73)]

    # keep the blade tip 600 off every wall
    r = E.ft(sweep) / 2
    fixed = []
    for cx, cy in centres:
        cx = min(max(cx, x0 + r + E.ft(E.FAN_BLADE_CLEAR_MM)),
                 x1 - r - E.ft(E.FAN_BLADE_CLEAR_MM))
        cy = min(max(cy, y0 + r + E.ft(E.FAN_BLADE_CLEAR_MM)),
                 y1 - r - E.ft(E.FAN_BLADE_CLEAR_MM))
        fixed.append((cx, cy))

    if len(fixed) == 2:
        d = math.dist(fixed[0], fixed[1])
        if d < E.ft(E.FAN_MIN_SPACING_MM):
            notes.append(f"{room.name}: two fans are only {d:.1f} ft apart; "
                         f"{E.FAN_MIN_SPACING_MM} mm is the minimum — check "
                         "the room can take both.")

    made = []
    for i, (cx, cy) in enumerate(fixed, start=1):
        p = ElecPoint(code="CF", x=cx, y=cy, room=room.name,
                      tag=f"{code}-CF-{i:02d}",
                      watts=E.FIXTURES["CF"][1], size=E.ft(sweep),
                      height_mm=E.FAN_HEIGHT_MM,
                      note=f"{sweep} mm sweep, regulator on the room's first "
                           "board")
        out.append(p)
        made.append(p)
    return made


def _peripheral(ax0, ay0, ax1, ay1, kind, need, notes, room_name):
    """The standard ceiling format of §1.3, laid out properly.

    A ring at the ceiling periphery: the inset rectangle is walked side by
    side, each side divided into equal steps so the END OFFSETS MATCH and the
    ring is symmetric about both room axes — that is what stops fixtures
    landing at arbitrary spots. The spacing is chosen inside its permitted
    900–1200 band (1200–1500 for panels) so the resulting count comes as close
    as it can to the lumen-method figure, rather than fixtures being dropped
    from a grid afterwards.
    """
    lo, hi = ((E.PANEL_SPACING_MM - 150, E.PANEL_SPACING_MM + 150)
              if kind == "PL" else (900, 1200))
    W, H = ax1 - ax0, ay1 - ay0

    def ring_for(space_mm):
        s = E.ft(space_mm)
        nx = max(1, int(round(W / s)))
        ny = max(1, int(round(H / s)))
        pts = []
        for i in range(nx):                       # bottom and top runs
            x = ax0 + W * (i + 0.5) / nx
            pts += [(x, ay0), (x, ay1)]
        for j in range(ny):                       # left and right runs
            y = ay0 + H * (j + 0.5) / ny
            pts += [(ax0, y), (ax1, y)]
        return pts

    best = None
    for mm in range(int(lo), int(hi) + 1, 25):
        pts = ring_for(mm)
        d = abs(len(pts) - need)
        if best is None or d < best[0]:
            best = (d, mm, pts)
    _d, mm, pts = best

    # the ring is used as it stands only when it BOTH meets the calculation
    # and does not run away from it. Accepting a ring that undershoots left
    # rooms dark, and left two rooms of the same size with different counts
    # because the spacing rounded differently in each.
    if need <= len(pts) <= need * 1.35:
        return pts

    # A full ring at the closest permitted spacing throws far more than a
    # low-lux space asks for. The calculation governs the COUNT, the format
    # governs the ARRANGEMENT — so the ring STAYS A RING, on all four sides,
    # and the count is shared between the sides in proportion to their length.
    # Laying the fixtures out in rows instead drops the two short runs and
    # leaves the middle of the side walls dark, which is not the peripheral
    # format at all.
    notes.append(f"{room_name}: a ring at {mm} mm c/c would be {len(pts)} "
                 f"{kind} where the calculation needs {need}; the ring is "
                 "opened out to that count instead.")
    # each pass of the loops below lays TWO fixtures, one on each opposite
    # wall, so the runs share half the count. A side may legitimately get
    # none — a 8' x 4' toilet wants two fixtures, not one per wall.
    # round the halves UP: rounding down quietly drops the room below the lux
    # it was calculated for, which is the one error the standard will not take
    half = max(1, math.ceil(need / 2))
    nx = int(round(half * W / max(W + H, 0.01)))
    ny = half - nx
    if nx + ny < 1:
        nx = 1
    nx, ny = max(0, nx), max(0, ny)
    out = []
    for i in range(nx):
        x = ax0 + W * (i + 0.5) / nx
        out += [(x, ay0), (x, ay1)]
    for j in range(ny):
        y = ay0 + H * (j + 0.5) / ny
        out += [(ax0, y), (ax1, y)]
    return out


def _clear_of_fans(pt, fans, ax0, ay0, ax1, ay1):
    """Slide a fixture along its own run of the ring until it clears the fans.

    The point keeps the wall it belongs to — only its position along that wall
    moves — so the ring survives and the room keeps the count it was
    calculated for. If the whole run is inside a fan's zone the point stays
    where it was; a fixture slightly close to a fan beats a dark room.
    """
    if not fans:
        return pt
    r = E.ft(E.FAN_CLEAR_ZONE_MM)

    def clear(p):
        return all(math.dist(p, (f.x, f.y)) >= r for f in fans)

    if clear(pt):
        return pt
    x, y = pt
    horiz = abs(y - ay0) < 1e-6 or abs(y - ay1) < 1e-6
    lo, hi = (ax0, ax1) if horiz else (ay0, ay1)
    here = x if horiz else y
    step = r / 6
    for k in range(1, int((hi - lo) / step) + 2):
        for cand in (here + step * k, here - step * k):
            if not lo <= cand <= hi:
                continue
            p = (cand, y) if horiz else (x, cand)
            if clear(p):
                return p
    return pt


# ---------------------------------------------------------- 1.3 lights
def place_lights(plan: Plan, room, clear, fans, out: list, code: str,
                 cat: str, notes: list) -> list:
    """The standard peripheral format: a ring of fixtures 300–450 from the
    finished wall face at 900–1200 c/c, count verified against the lumen
    method, and nothing within 600 of a fan centre."""
    x0, y0, x1, y1 = clear.bounds
    area_m2 = (x1 - x0) * (y1 - y0) * 0.3048 * 0.3048
    lux, task, cct, layers = E.LUX.get(cat, E.LUX["other"])

    kind = "PL" if cat in ("kitchen", "study") else "SL"
    watt = E.FIXTURES[kind][1]
    need = E.lumen_count(lux, area_m2, watt)

    edge = E.ft(E.PANEL_EDGE_MM if kind == "PL" else E.LIGHT_EDGE_MM)
    space = E.ft(E.PANEL_SPACING_MM if kind == "PL" else E.LIGHT_SPACING_MM)

    ax0, ay0 = x0 + edge, y0 + edge
    ax1, ay1 = x1 - edge, y1 - edge
    if clear.area < SMALL_ROOM_NO_RING_SQFT:
        # A passage, a dress, a small toilet takes NO RING — a peripheral ring
        # round a 3'-6" wide passage is fittings where one does the job. The
        # count is the lumen figure rounded to NEAREST here, not rounded up:
        # in a small room rounding up doubles the installed lux (a toilet came
        # out at 348 against a 175 target). Spaced down the long axis.
        exact = (lux * area_m2) / (watt * E.LUMEN_PER_W * E.UF * E.MF)
        n = max(1, int(round(exact)))
        # rounding to nearest must never leave the room meaningfully dark —
        # a bathroom at 76 % of its target is a fault, so take the extra
        # fitting whenever the shortfall would pass 10 %
        if n / max(exact, 1e-6) < 0.9:
            n += 1
        long_x = (x1 - x0) >= (y1 - y0)
        keep = []
        for i in range(n):
            t = (i + 0.5) / n
            if long_x:
                keep.append((x0 + (x1 - x0) * t, (y0 + y1) / 2))
            else:
                keep.append(((x0 + x1) / 2, y0 + (y1 - y0) * t))
        notes.append(f"{room.name}: {clear.area:.0f} sqft — {n} fitting(s) "
                     "down the room, no peripheral ring.")
    elif ax1 <= ax0 or ay1 <= ay0:
        keep = [((x0 + x1) / 2, (y0 + y1) / 2)]
    else:
        keep = _peripheral(ax0, ay0, ax1, ay1, kind, need, notes, room.name)

    # The fan's centre zone stays clear (flicker and shadow). In a narrow room
    # the zone reaches the side runs of the ring, and DELETING those points
    # left the room short of its calculated count — the kitchen came out at
    # 172 lux against 275. A fixture the zone rejects therefore SLIDES along
    # its own run until it is clear, which keeps both the count and the ring.
    keep = [_clear_of_fans(pt, fans, ax0, ay0, ax1, ay1) for pt in keep]
    made = []
    for i, (px, py) in enumerate(keep, start=1):
        p = ElecPoint(code=kind, x=px, y=py, room=room.name,
                      tag=f"{code}-{kind}-{i:02d}", watts=watt,
                      note=f"{watt} W, {cct}")
        out.append(p)
        made.append(p)

    lx = (x0 + x1) / 2
    achieved = (len(made) * watt * E.LUMEN_PER_W * E.UF * E.MF) / max(area_m2, 0.1)
    notes.append(f"{room.name}: {len(made)} x {kind} {watt} W gives about "
                 f"{achieved:.0f} lux against a {lux} lux target.")
    return made


def _walled_sides(plan: Plan, room, clear) -> dict:
    """Which sides of the room have a REAL wall, and the span it covers.
    Returns {side: (lo, hi)} in the along-wall coordinate."""
    x0, y0, x1, y1 = clear.bounds
    tol = 0.6
    out: dict = {}

    def note(side, lo, hi):
        if hi <= lo:
            return
        a, b = out.get(side, (lo, hi))
        out[side] = (min(a, lo), max(b, hi))

    for w in plan.walls:
        if abs(w.y2 - w.y1) < 1e-6:                      # horizontal
            lo, hi = sorted((w.x1, w.x2))
            lo, hi = max(lo, x0), min(hi, x1)
            if abs(w.y1 - room.y) <= tol:
                note("S", lo, hi)
            if abs(w.y1 - (room.y + room.h)) <= tol:
                note("N", lo, hi)
        elif abs(w.x2 - w.x1) < 1e-6:                    # vertical
            lo, hi = sorted((w.y1, w.y2))
            lo, hi = max(lo, y0), min(hi, y1)
            if abs(w.x1 - room.x) <= tol:
                note("W", lo, hi)
            if abs(w.x1 - (room.x + room.w)) <= tol:
                note("E", lo, hi)
    return out


def place_open_lights(plan: Plan, room, clear, out, code, notes):
    """An open terrace has NO SLAB overhead, so it gets no ceiling fitting —
    a ceiling light there has nothing to hang from. It takes wall lights on
    its own parapet / exterior wall instead, and a bare planter strip takes
    none at all."""
    area = clear.area
    if area < OPEN_MIN_LIGHT_SQFT:
        notes.append(f"{room.name}: open to sky and only {area:.0f} sqft — "
                     "no light needed.")
        return []

    sides = _walled_sides(plan, room, clear)
    if not sides:
        notes.append(f"{room.name}: open to sky with no wall to mount on — "
                     "no light placed.")
        return []
    side, (lo, hi) = max(sides.items(), key=lambda kv: kv[1][1] - kv[1][0])
    span = hi - lo
    n = max(1, min(3, int(span / 12) + 1))

    x0, y0, x1, y1 = clear.bounds
    off = 0.20
    made = []
    for i in range(n):
        t = lo + span * (i + 0.5) / n
        if side in ("N", "S"):
            px = t
            py = (y0 + off) if side == "S" else (y1 - off)
            ang = 90 if side == "S" else 270
        else:
            py = t
            px = (x0 + off) if side == "W" else (x1 - off)
            ang = 0 if side == "W" else 180
        p = ElecPoint(code="WL", x=px, y=py, room=room.name, angle=ang,
                      tag=f"{code}-WL-{i + 1:02d}",
                      watts=E.FIXTURES["WL"][1], height_mm=2100,
                      note="wall light on the terrace wall — open to sky, "
                           "no slab for a ceiling fitting; IP65")
        out.append(p)
        made.append(p)
    notes.append(f"{room.name}: open to sky — {n} wall light(s) on the "
                 f"{side} wall, no ceiling fitting.")
    return made


# ----------------------------------------------- room-specific fixtures
def place_room_extras(plan: Plan, room, clear, out, code, cat, notes):
    """The layers the standard makes mandatory for each kind of room."""
    items = _room_furniture(plan, room)
    x0, y0, x1, y1 = clear.bounds
    made = []

    def add(kind, x, y, tag_n=1, **kw):
        p = ElecPoint(code=kind, x=x, y=y, room=room.name,
                      tag=f"{code}-{kind}-{tag_n:02d}",
                      watts=E.FIXTURES[kind][1], **kw)
        out.append(p)
        made.append(p)
        return p

    def add_wall(kind, f, tag_n=1, prefer=None, **kw):
        """A fixture that mounts on a wall, put on that wall."""
        px, py, side = wall_beside(clear, f, prefer=prefer, off=0.10)
        p = add(kind, px, py, tag_n, **kw)
        p.angle = {"N": 270, "S": 90, "E": 180, "W": 0}[side]
        return p

    if cat == "wet":
        # ceiling light in the dry zone, mirror light over the basin, exhaust
        # over the wet zone
        basin = _find(items, "basin")
        shower = _find(items, "shower")
        if basin is not None:
            # the mirror light is ON the wall above the basin
            bx, by, side = wall_beside(clear, basin)
            p = add("ML", bx, by, note=f"over the mirror @ "
                                       f"{E.H_MIRROR_LIGHT} mm",
                    height_mm=E.H_MIRROR_LIGHT)
            p.angle = {"N": 270, "S": 90, "E": 180, "W": 0}[side]
        # the exhaust is a THROUGH-WALL fan at the ventilator / window, never a
        # ceiling unit — it has to vent to outside air. Put it on that wall,
        # high, flush.
        vent = _vent_of(plan, room)
        if vent is not None:
            _o, w, pt = vent
            L = w.length or 1e-9
            ux, uy = (w.x2 - w.x1) / L, (w.y2 - w.y1) / L
            nx, ny = -uy, ux
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            if (cx - pt[0]) * nx + (cy - pt[1]) * ny < 0:
                nx, ny = -nx, -ny
            ex, ey = pt[0] + nx * 0.24, pt[1] + ny * 0.24
            add("EF", ex, ey, height_mm=E.H_EXHAUST,
                note=f"wall exhaust at the ventilator @ {E.H_EXHAUST} mm, "
                     "vented to outside")
        else:
            wet = shower or _find(items, "wc")
            if wet is not None:
                ex, ey, _s = snap_to_wall(clear, *wet.centre, off=0.24)
                add("EF", ex, ey, height_mm=E.H_EXHAUST,
                    note=f"wall exhaust @ {E.H_EXHAUST} mm, on the wet-zone "
                         "wall, vented to outside")
        if shower is not None:
            sx, sy = shower.centre
            add("CSL", sx, sy, tag_n=2, note="IP44 rated, inside shower zone")

    elif cat == "kitchen":
        counter = _find(items, "counter")
        if counter is not None:
            cx0, cy0 = counter.x, counter.y
            n = max(2, int(max(counter.w, counter.h) / E.ft(900)))
            for i in range(n):
                t = (i + 0.5) / n
                if counter.w >= counter.h:
                    px, py = counter.x + counter.w * t, counter.y + counter.h / 2
                else:
                    px, py = counter.x + counter.w / 2, counter.y + counter.h * t
                add("TR", px, py, tag_n=i + 1,
                    note="under-cabinet task strip, mandatory over the counter")

    elif cat == "dining":
        table = _find(items, "dining")
        if table is not None:
            tx, ty = table.centre
            add("HL", tx, ty,
                note="pendant centred on the TABLE, 750-900 mm above the top")

    elif cat == "living":
        area_m2 = (x1 - x0) * (y1 - y0) * 0.3048 * 0.3048
        sofa = _find(items, "sofa")
        if area_m2 > 20 and sofa is not None:
            sx, sy = sofa.centre
            dia_in = ((x1 - x0) + (y1 - y0))
            add("CH", sx, sy,
                note=f"chandelier at the seating cluster, about {dia_in:.0f}\" "
                     "dia, bottom 2100 mm clear, on a dimmable circuit")
        tv = _find(items, "tv_unit")
        if tv is not None:
            tx, ty = tv.centre
            add("SL", tx, ty, tag_n=90, note="accent on the TV wall")

    elif cat == "master":
        # a bedside wall light over each side table, ON the head wall
        bed = _find(items, "bed")
        tables = [f for f in items if f.kind == "bedside"]
        if bed is not None:
            for i, tb in enumerate(tables, start=1):
                px, py, side = wall_beside(clear, tb, prefer=bed.facing,
                                           off=0.10)
                p = add("BWL", px, py, tag_n=i, height_mm=1350,
                        note="bedside wall light, 2-way with the entry board")
                p.angle = {"N": 270, "S": 90, "E": 180, "W": 0}[side]

    elif cat == "stair":
        add("STL", (x0 + x1) / 2, y0 + E.ft(300), height_mm=300,
            note="step light 300 mm above FFL; lights on 2-way switching")
    return made


# ------------------------------------------ 2.x switchboards and points
def place_boards(plan: Plan, room, clear, fixtures, out, code, cat, notes):
    """The first board at the entry door, lock side, 1200 above FFL, plus the
    boards the furniture calls for."""
    items = _room_furniture(plan, room)
    made = []
    n = 0

    def add(x, y, height, controls, note, rating=""):
        nonlocal n
        n += 1
        p = ElecPoint(code="SB", x=x, y=y, room=room.name,
                      tag=f"{code}-SB-{n:02d}", height_mm=height,
                      controls=list(controls), note=note)
        out.append(p)
        made.append(p)
        return p

    door_pt, door_wall, door_op = _door_of(plan, room)
    x0, y0, x1, y1 = clear.bounds

    if door_pt is not None and door_wall is not None:
        # lock side = the jamb away from the hinge, 200–300 from the frame
        L = door_wall.length or 1e-9
        ux, uy = ((door_wall.x2 - door_wall.x1) / L,
                  (door_wall.y2 - door_wall.y1) / L)
        hinge_at_start = not (door_op.swing and door_op.swing.hinge == "end")
        d = door_op.pos + (door_op.width + E.ft(E.BOARD_FROM_FRAME_MM)
                           if hinge_at_start else -E.ft(E.BOARD_FROM_FRAME_MM))
        d = max(0.2, min(d, door_wall.length - 0.2))
        bx, by = door_wall.point_at(d)
        # nudge inside the room
        nx, ny = -uy, ux
        if not clear.contains(Point(bx + nx * 0.4, by + ny * 0.4)):
            nx, ny = uy, -ux
        bx, by = bx + nx * 0.25, by + ny * 0.25
    else:
        bx, by = (x0 + x1) / 2, y0 + 0.3

    controls = [f.tag for f in fixtures]
    note = "entry board, lock side, 200-300 from the frame; main light + fan"
    if cat == "wet":
        note = "board OUTSIDE the toilet at the entry: light, exhaust, " \
               "mirror light, geyser indicator"
    add(bx, by, E.H_ENTRY_BOARD, controls, note)

    # One bedside board per bedside table, on the wall the bed head is
    # against, at 675 — two tables means two boards. This is why the layout
    # reads the furniture rather than assuming a bedroom has two of anything.
    bed = _find(items, "bed")
    tables = [f for f in items if f.kind == "bedside"]
    if bed is not None and cat in ("master", "bedroom"):
        for tb in tables:
            # ON THE WALL THE TABLE ITSELF STANDS AGAINST. Using the bed's
            # facing put every board on the head wall — with a rotated bed
            # both boards of one room landed on the same point on the wrong
            # wall, nowhere near their tables.
            bx, by, _s = snap_to_wall(clear, *tb.centre, 0.18)
            add(bx, by, E.H_BEDSIDE_BOARD, [],
                "bedside board: 2-way for the main light, lamp switch, "
                "6A x2, USB")
        if not tables:                       # a bed with no side tables
            bx, by, _s = wall_beside(clear, bed, prefer=bed.facing)
            add(bx, by, E.H_BEDSIDE_BOARD, [], "bedside board")

    # TV board on the wall the TV unit stands against
    tv = _find(items, "tv_unit")
    if tv is not None:
        tx, ty, _s = wall_beside(clear, tv)
        add(tx, ty, E.H_TV_BOARD, [],
            "TV board, concealed behind the panel: 16A x1 + 6A x3-4 + data")

    # sofa-side board, at skirting level on the wall behind the sofa
    sofa = _find(items, "sofa")
    if sofa is not None:
        sx, sy, _s = wall_beside(clear, sofa)
        add(sx, sy, E.H_SOFA_SIDE, [],
            "sofa-side board: 6A x2 for phone charging and a floor lamp")

    # kitchen appliance points, on the wall the counter runs along
    counter = _find(items, "counter")
    if counter is not None:
        along_x = counter.w >= counter.h
        length = counter.w if along_x else counter.h
        cn = max(2, int(length / E.ft(750)))
        for i in range(cn):
            t = (i + 0.5) / cn
            if along_x:
                px, py = counter.x + counter.w * t, counter.y + counter.h * 0.5
            else:
                px, py = counter.x + counter.w * 0.5, counter.y + counter.h * t
            wx, wy, _s = snap_to_wall(clear, px, py)
            add(wx, wy, E.H_KITCHEN_COUNTER, [],
                "counter appliance point, 6/16A, boards every 600-900 "
                "along the counter")
    fridge = _find(items, "fridge")
    if fridge is not None:
        fx, fy, _s = wall_beside(clear, fridge)
        add(fx, fy, E.H_FRIDGE, [], "fridge point, 16A dedicated")

    # geyser in a wet room, on the wall beside the shower
    if cat == "wet":
        shower = _find(items, "shower")
        if shower is not None:
            sx, sy, _s = snap_to_wall(clear, *shower.centre)
            add(sx, sy, E.H_GEYSER, [],
                "geyser point, 16/20A DP switch with neon, outside the "
                "splash zone")
    return made


def _internal_sides(plan: Plan, room, clear) -> set:
    """Which of the room's four sides border ANOTHER room (a partition), as
    opposed to an exterior wall. Used to route the AC onto the right wall."""
    x0, y0, x1, y1 = clear.bounds
    probe = 0.5
    mids = {"N": ((x0 + x1) / 2, y1 + probe), "S": ((x0 + x1) / 2, y0 - probe),
            "E": (x1 + probe, (y0 + y1) / 2), "W": (x0 - probe, (y0 + y1) / 2)}
    out = set()
    for s, (px, py) in mids.items():
        for r in plan.rooms:
            if r is room or r.void:
                continue
            if r.x <= px <= r.x + r.w and r.y <= py <= r.y + r.h:
                out.add(s)
                break
    return out


# ------------------------------------------------------------ 5. AC
def place_ac(plan: Plan, room, clear, out, code, cat, notes):
    """One indoor unit per habitable room, on the wall that makes it work.

    A high-wall split throws horizontally down the room, so it goes on a wall
    at the END of the room's LONG axis and blows along it. Which of the two
    end walls:

    * a bedroom takes the PARTITION (the shared internal wall). Two mirror
      bedrooms then carry their units back to back on the common wall, and the
      power and drain lines leave together instead of running to opposite
      outer walls;
    * a living / dining room takes the WINDOW (exterior) wall and blows inward
      across the room toward the circulation — a dining unit on the window
      wall throws over the table and on toward the stair, which is where the
      cooling is wanted, not into the outside wall.

    A bed's head is on a long wall, so an end-wall unit never blows on the
    pillow. Every choice is a starting point — the Faces column can turn it.
    """
    items = _room_furniture(plan, room)
    bed = _find(items, "bed")
    has_seating = any(F.family(f.kind) == "sofa" for f in items)

    x0, y0, x1, y1 = clear.bounds
    area_sqft = (x1 - x0) * (y1 - y0)

    is_bed = bed is not None and cat in ("master", "bedroom", "study")
    # provide an AC to the habitable rooms, and to any sizable room that is
    # clearly a sitting space (a hall with a sofa) even if its name does not
    # classify — the drawing hall was going without one purely on a typo.
    provide = (cat in ("living", "master", "bedroom", "study", "dining")
               or has_seating or area_sqft >= AC_MIN_SQFT)
    if not provide:
        return []

    tr = E.tonnage(area_sqft)

    long_x = (x1 - x0) >= (y1 - y0)
    ends = ("E", "W") if long_x else ("N", "S")
    internal = _internal_sides(plan, room, clear)
    want_internal = [s for s in ends if s in internal]
    want_external = [s for s in ends if s not in internal]
    if is_bed:
        side = (want_internal or want_external or list(ends))[0]
        why = "on the partition wall so the two bedroom units and their " \
              "lines run together"
    else:
        side = (want_external or want_internal or list(ends))[0]
        why = "on the window wall, blowing inward across the room toward the " \
              "circulation"

    d = AC_CASE_DEPTH_FT / 2
    (px, py), ang = {
        "N": (((x0 + x1) / 2, y1 - d), 0.0),
        "S": (((x0 + x1) / 2, y0 + d), 180.0),
        "E": ((x1 - d, (y0 + y1) / 2), 270.0),
        "W": ((x0 + d, (y0 + y1) / 2), 90.0),
    }[side]

    p = ElecPoint(code="AC", x=px, y=py, room=room.name, angle=ang,
                  tag=f"{code}-AC-01", height_mm=E.H_AC_POINT,
                  size=tr, watts=tr * 1200,
                  note=f"{tr} TR high-wall split, {why}; dedicated point "
                       "+ isolator")
    out.append(p)
    return [p]


# ------------------------------------------------ 3. circuits (IS 732)
def build_circuits(plan: Plan, points: list[ElecPoint],
                   notes: list) -> list[Circuit]:
    """Light circuits ≤ 800 W or 10 points; 16A power ≤ 2 points / 3000 W;
    a dedicated circuit for every AC and geyser."""
    from . import looping
    circuits: list[Circuit] = []

    def new(kind, n):
        prefix = {"light": "L", "power": "P", "ac": "AC",
                  "geyser": "GYS"}[kind]
        return Circuit(id=f"{prefix}{n}", kind=kind,
                       mcb=E.MCB[kind], wire=E.WIRE[kind])

    # Lights and fans are circuited SWITCH GROUP BY SWITCH GROUP, never split
    # through the middle of one: a switch's loop is a single run of cable, so a
    # group that straddled two circuits would be wired across two MCBs. The
    # groups are already capped at 800 W / 10 points, so each always fits.
    ln = 0
    cur = None
    for sw in looping.switches(plan):
        grp = list(sw.seq)
        gw = sum((p.watts or 0) for p in grp)
        if (cur is None
                or cur.points + len(grp) > E.CKT_LIGHT_MAX_PTS
                or cur.load_w + gw > E.CKT_LIGHT_MAX_W):
            ln += 1
            cur = new("light", ln)
            cur.description = "Lights + fans"
            circuits.append(cur)
        for p in grp:
            p.circuit = cur.id
            cur.points += 1
            cur.load_w += p.watts or 0
            if p.room not in cur.rooms:
                cur.rooms.append(p.room)

    # 16A power: two points a circuit
    pn = 0
    cur = None
    for p in points:
        if p.code != "SB" or p.height_mm in (E.H_ENTRY_BOARD,):
            continue
        if cur is None or cur.points + 1 > E.CKT_POWER_MAX_PTS:
            pn += 1
            cur = new("power", pn)
            cur.description = "16A power"
            circuits.append(cur)
        p.circuit = cur.id
        cur.points += 1
        cur.load_w += E.W_16A
        if p.room not in cur.rooms:
            cur.rooms.append(p.room)

    # a dedicated circuit for every AC and every geyser
    an = gn = 0
    for p in points:
        if p.code == "AC":
            an += 1
            c = new("ac", an)
            c.description = f"AC {p.room}"
            c.rooms = [p.room]
            c.points = 1
            c.load_w = p.watts
            circuits.append(c)
            p.circuit = c.id
        elif p.code == "SB" and "geyser" in (p.note or "").lower():
            gn += 1
            c = new("geyser", gn)
            c.description = f"Geyser {p.room}"
            c.rooms = [p.room]
            c.points = 1
            c.load_w = 2000
            circuits.append(c)
            p.circuit = c.id

    for c in circuits:
        if c.kind == "light" and c.load_w > E.CKT_LIGHT_MAX_W:
            notes.append(f"{c.id} carries {c.load_w:.0f} W; the limit is "
                         f"{E.CKT_LIGHT_MAX_W} W.")
    return circuits


def load_summary(points, circuits) -> dict:
    """Connected load, demand load with diversity, and the sanctioned
    recommendation."""
    conn = {"light": 0.0, "power": 0.0, "ac": 0.0}
    for c in circuits:
        k = "ac" if c.kind in ("ac", "geyser") else \
            ("power" if c.kind == "power" else "light")
        conn[k] += c.load_w
    total = sum(conn.values())
    demand = (conn["light"] * E.DIVERSITY["light"]
              + conn["power"] * E.DIVERSITY["power"]
              + conn["ac"] * E.DIVERSITY["ac"])
    sanction = max(1.0, round((demand / 1000.0) * 1.15 * 2) / 2)
    return {"connected_w": total, "demand_w": demand,
            "by_kind": conn, "sanctioned_kw": sanction}


# --------------------------------------------------------------- the run
def design(plan_dict: dict) -> tuple[dict, list[str]]:
    """Lay out the electrical and lighting over a plan that has furniture."""
    from dataclasses import asdict
    from . import autofix

    plan = Plan.from_dict(plan_dict)
    autofix.apply(plan)
    notes: list[str] = []

    if not plan.furniture:
        notes.append("There is no furniture yet. The layout follows the "
                     "furniture — fans centre on the bed or seating, the TV "
                     "board sits behind the TV — so run Furniture Layout "
                     "first for a proper result.")

    out: list[ElecPoint] = []
    seen: dict = {}
    rooms = sorted([r for r in plan.rooms if not r.void],
                   key=lambda r: (-round(r.y + r.h, 1), round(r.x, 1)))

    for room in rooms:
        if room.is_lawn:
            # a lawn / garden is soft landscape — grass only, no electrical
            continue
        clear = _clear(plan, room)
        if clear.is_empty or clear.area < 8:
            continue
        cat = E.classify(room.name)
        code = E.code_for(room.name, seen)

        # No fan in a wet room, an open area, a store or on a stair — and none
        # in a lobby / passage / foyer that is too small to need one: it is
        # circulation, not a place anyone sits, so it gets light only.
        no_fan = cat in ("wet", "open", "store", "stair")
        if (cat in ("passage", "other") and not no_fan
                and clear.area < FAN_MIN_PASSAGE_SQFT):
            # a lobby, a corridor, a dressing room — circulation or a walk-in,
            # too small for a fan and nobody sits there. Light only.
            no_fan = True
            notes.append(f"{room.name}: no fan — only {clear.area:.0f} sqft "
                         "of circulation / utility space; light only.")
        fans = [] if no_fan \
            else place_fans(plan, room, clear, out, code, notes)
        # open to sky = no ceiling to fix a fitting to
        lights = (place_open_lights(plan, room, clear, out, code, notes)
                  if room.open_area
                  else place_lights(plan, room, clear, fans, out, code, cat,
                                    notes))
        extras = place_room_extras(plan, room, clear, out, code, cat, notes)
        fixtures = fans + lights + extras
        if not room.open_area:
            place_boards(plan, room, clear, fixtures, out, code, cat, notes)
            place_ac(plan, room, clear, out, code, cat, notes)

    # the main DB, near the entrance foyer or passage
    db = _place_db(plan, out, notes)
    if db:
        out.append(db)

    # Boards, fans, ACs and exhausts are numbered ACROSS THE PLAN, not per
    # room — an electrician asks for "S.B.7", and two rooms each having their
    # own "S.B.1" is what made the drawing ambiguous.
    _renumber_globally(out)
    # Ceiling lights are numbered room by room so each board's lights are a
    # clean consecutive run in the lighting schedule.
    _number_lights(plan, out)
    # Boards are marked by TYPE, and the plan carries that same mark, so the
    # switchboard schedule and the drawing name every board identically.
    plan.elec = out
    from . import looping, sbsched
    sbsched.assign_type_tags(plan)
    notes.extend(looping.notes(plan))

    circuits = build_circuits(plan, out, notes)
    summary = load_summary(out, circuits)
    notes.append(
        f"Connected load {summary['connected_w'] / 1000:.2f} kW, demand "
        f"{summary['demand_w'] / 1000:.2f} kW with diversity; recommended "
        f"sanctioned load {summary['sanctioned_kw']:.1f} kW.")
    notes.append("Every AC and geyser is on its own circuit; RCCB 30 mA per "
                 "DB, separate lighting and power banks.")

    res = dict(plan_dict)
    res["openings"] = [asdict(o) for o in plan.openings]
    res["elec"] = [asdict(p) for p in out]
    res["circuits"] = [asdict(c) for c in circuits]
    res["elec_summary"] = summary
    # The LOOPING the drawing decided, handed to the 3D view as well. Without
    # this the 3D re-derived its own nearest-first chain from a board's whole
    # controls list, so a loop wandered out of the room and across the slab.
    # switches() is strictly per ROOM and per DUTY - one source of truth.
    res["elec_loops"] = [
        {"id": s.id, "duty": s.duty, "room": s.room,
         "board": (None if s.board is None else
                   {"x": s.board.x, "y": s.board.y,
                    "height_mm": s.board.height_mm}),
         "seq": [{"x": p.x, "y": p.y, "tag": p.tag, "code": p.code}
                 for p in s.seq]}
        for s in looping.switches(plan)]
    return res, notes


# every light, numbered together in one L-series so the plan, the lighting
# schedule and the switch-loop schedule can say "L7" and mean one fitting
CEILING_LIGHT_CODES = E.LIGHT_CODES


def _renumber_globally(points: list[ElecPoint]) -> None:
    """One running series per marked type, in reading order down the sheet.
    The ceiling lights share a single L-series so every one carries a number
    the schedule can name."""
    marked = ("SB", "CF", "AC", "EF", "DB")
    order = sorted([p for p in points if p.code in marked],
                   key=lambda p: (-round(p.y, 1), round(p.x, 1)))
    n: dict = {}
    for p in order:
        n[p.code] = n.get(p.code, 0) + 1
        room = p.tag.split("-")[0] if "-" in p.tag else ""
        p.tag = f"{room}-{p.code}-{n[p.code]:02d}" if room \
            else f"{p.code}-{n[p.code]:02d}"


def _number_lights(plan: Plan, points: list[ElecPoint]) -> None:
    """Number the ceiling lights ROOM BY ROOM so each board's lights come out
    consecutive — L1–L6 in the first bedroom, L7–L12 in the second — instead
    of interleaved across the floor, which made the schedule ranges a mess.
    Rooms are taken in reading order down the sheet, lights the same within a
    room."""
    def room_at(x, y):
        best, bd = None, 1e18
        for r in plan.rooms:
            if r.void:
                continue
            dx = max(r.x - x, 0, x - (r.x + r.w))
            dy = max(r.y - y, 0, y - (r.y + r.h))
            d = dx * dx + dy * dy
            if d < bd:
                best, bd = r, d
        return best

    from collections import defaultdict
    by_room = defaultdict(list)
    for p in points:
        if p.code in CEILING_LIGHT_CODES:
            by_room[id(room_at(p.x, p.y))].append(p)

    i = 0
    for r in sorted(plan.rooms,
                    key=lambda r: (-round(r.y + r.h, 1), round(r.x, 1))):
        pts = sorted(by_room.get(id(r), []),
                     key=lambda p: (-round(p.y, 1), round(p.x, 1)))
        for p in pts:
            i += 1
            room = p.tag.split("-")[0] if "-" in p.tag else ""
            p.tag = f"{room}-L-{i:02d}" if room else f"L-{i:02d}"


def _db_on_wall(plan, wall, opening, room):
    """A DB point sitting flush ON a real wall, to one side of a door, pushed
    just inside the room. The side is chosen so the board stays INSIDE this
    room — the jamb on one side of an entrance is often a partition into the
    next room, and putting the DB there drops it in the wrong room."""
    L = wall.length or 1e-9
    ux, uy = (wall.x2 - wall.x1) / L, (wall.y2 - wall.y1) / L
    nx, ny = -uy, ux                                  # wall normal
    cx, cy = room.x + room.w / 2, room.y + room.h / 2
    if (cx - wall.x1) * nx + (cy - wall.y1) * ny < 0:
        nx, ny = -nx, -ny                             # normal points inward

    def inside(px, py):
        return (room.x - 0.2 <= px <= room.x + room.w + 0.2
                and room.y - 0.2 <= py <= room.y + room.h + 0.2)

    if opening is not None:
        options = [opening.pos + opening.width + E.ft(500),   # past the door
                   opening.pos - E.ft(500)]                   # before it
    else:
        options = [L / 2]

    chosen = None
    for d in options:
        d = max(0.4, min(d, L - 0.4))
        bx, by = wall.point_at(d)
        bx, by = bx + nx * 0.28, by + ny * 0.28
        if inside(bx, by):
            chosen = (bx, by)
            break
    if chosen is None:                                # neither side fits
        d = max(0.4, min(options[0], L - 0.4))
        bx, by = wall.point_at(d)
        chosen = (bx + nx * 0.28, by + ny * 0.28)

    ang = 0.0 if abs(ux) >= abs(uy) else 90.0
    return chosen[0], chosen[1], ang


def _place_db(plan: Plan, out, notes):
    """Main DB flush on a REAL wall, beside the main entrance (the meter side),
    never mid-room. The earlier version snapped to the room's box edge, but
    that edge can be an OPEN side — the stair mouth has no wall — so the board
    still floated. This one puts it against an actual exterior entrance wall,
    which always exists, to one side of the door and pushed inside."""
    # the main entrance: the widest door on an exterior wall
    ent = None
    for o in plan.openings:
        if not o.is_door:
            continue
        w = plan.wall(o.wall_id)
        if w is None or not w.exterior:
            continue
        if ent is None or o.width > ent[0].width:
            ent = (o, w)

    if ent is not None:
        o, w = ent
        room = plan.room(o.swing.room) if o.swing and o.swing.room else None
        if room is None:
            # the room on the inside of that exterior wall
            room = min(plan.rooms,
                       key=lambda r: math.dist(
                           (r.x + r.w / 2, r.y + r.h / 2),
                           w.point_at(o.pos + o.width / 2)))
        placed = _db_on_wall(plan, w, o, room)
        if placed:
            bx, by, ang = placed
            notes.append(f"Main DB in {room.name}, flush beside the main "
                         "entrance; bottom 1500 / top 1800 above FFL, 750 "
                         "clear in front, circuit directory inside the door.")
            return ElecPoint(code="DB", x=bx, y=by, angle=ang, room=room.name,
                             tag="DB-01", height_mm=E.H_DB_BOTTOM,
                             note="Main DB: RCCB 30 mA, separate lighting / "
                                  "power / AC banks")

    # fallback: any interior door's wall in a passage / living room
    for cat in ("passage", "living"):
        for r in plan.rooms:
            if r.open_area or r.void or E.classify(r.name) != cat:
                continue
            dp, dw, do = _door_of(plan, r)
            if dw is not None:
                bx, by, ang = _db_on_wall(plan, dw, do, r)
                notes.append(f"Main DB in {r.name}, flush on the wall by its "
                             "door; bottom 1500 / top 1800 above FFL.")
                return ElecPoint(code="DB", x=bx, y=by, angle=ang,
                                 room=r.name, tag="DB-01",
                                 height_mm=E.H_DB_BOTTOM,
                                 note="Main DB: RCCB 30 mA, separate lighting "
                                      "/ power / AC banks")
    return None
