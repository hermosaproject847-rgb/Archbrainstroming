"""Furniture placement.

Given a finished floor plan, work out where each piece goes. The rules come
from furniture.py; the geometry — clear floor, door swings, the stair — comes
from the plan itself, so nothing has to be read or guessed.

Order of priority, from the master prompt STEP 3D:
    1. door swings and safety
    2. circulation and ergonomics
    3. Vaastu
    4. aesthetics

So a piece is placed on the best Vaastu wall that also leaves its clearances
and misses every swing. Where Vaastu has to give way, the piece still gets
placed and the compromise is recorded as a deviation — never silently.
"""

from __future__ import annotations

import math

from shapely.geometry import Polygon, Point, box
from shapely.ops import unary_union

from . import engine
from . import furniture as F
from .model import Furniture, Plan

GAP = F.ft(F.WALL_GAP)

# a clear walk-through kept across every doorway, on BOTH sides, so nothing is
# ever placed in a door's approach — you can always walk in and out
DOOR_APPROACH_FT = F.ft(600)         # 600 mm clear passage each side of a door
DOOR_JAMB_PAD_FT = F.ft(120)         # widen a little past the jambs


# ------------------------------------------------------------- obstacles
def door_approach(plan: Plan) -> list:
    """A clear rectangle across every doorway AND every open pass-through, on
    BOTH sides, so furniture is never placed in a door's swing / walk-through or
    across a servery / opening. This is the single biggest cause of a 'furniture
    in front of the door' or 'fridge blocking the kitchen opening' layout —
    not reserving the passage."""
    rects = []
    for o in plan.openings:
        passable = getattr(o, "is_door", False) or \
            getattr(o, "type", "") == "open"
        if not passable:
            continue
        w = plan.wall(o.wall_id)
        if w is None:
            continue
        try:
            a = w.point_at(o.pos)
            b = w.point_at(o.pos + o.width)
        except Exception:
            continue
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1e-9
        ux, uy = dx / L, dy / L               # along the wall
        px, py = -uy, ux                       # its normal (across the opening)
        d = DOOR_APPROACH_FT
        pad = DOOR_JAMB_PAD_FT
        a1 = (a[0] - ux * pad, a[1] - uy * pad)
        b1 = (b[0] + ux * pad, b[1] + uy * pad)
        pts = [(a1[0] - px * d, a1[1] - py * d),
               (b1[0] - px * d, b1[1] - py * d),
               (b1[0] + px * d, b1[1] + py * d),
               (a1[0] + px * d, a1[1] + py * d)]
        try:
            poly = Polygon(pts)
            if poly.is_valid and not poly.is_empty:
                rects.append(poly)
        except Exception:
            pass
    return rects


def blocked(plan: Plan) -> Polygon:
    """Everything furniture must stay out of: walls, door swings + approaches,
    stairs."""
    parts = [engine.wall_solid(plan)]
    parts.extend(door_approach(plan))          # keep every doorway walkable

    for o in plan.openings:
        if not o.is_door or o.is_sliding:
            continue
        w = plan.wall(o.wall_id)
        if w is None:
            continue
        try:
            hinge, u, n, wd = engine._door_frame(plan, o)
        except Exception:
            continue
        # the quarter-circle the leaf sweeps
        pts = [hinge]
        a1 = math.atan2(u[1], u[0])
        a2 = math.atan2(n[1], n[0])
        d = (a2 - a1)
        while d > math.pi:
            d -= 2 * math.pi
        while d < -math.pi:
            d += 2 * math.pi
        for i in range(13):
            a = a1 + d * i / 12
            pts.append((hinge[0] + wd * math.cos(a), hinge[1] + wd * math.sin(a)))
        try:
            parts.append(Polygon(pts))
        except Exception:
            pass

    for s in plan.stairs:
        parts.append(box(s.x, s.y, s.x + s.w, s.y + s.h))
    for s in plan.steps:
        parts.append(box(s.x, s.y, s.x + s.w, s.y + s.h))

    parts = [p for p in parts if p and not p.is_empty]
    return unary_union(parts) if parts else Polygon()


def footprint(f) -> Polygon:
    """The area a piece really occupies, turned by its own angle."""
    fp = box(f.x, f.y, f.x + f.w, f.y + f.h)
    a = float(getattr(f, "angle", 0.0) or 0.0)
    if abs(a) < 1e-9:
        return fp
    from shapely import affinity
    cx, cy = f.centre
    return affinity.rotate(fp, a, origin=(cx, cy))


def clear_floor(plan: Plan, room) -> Polygon:
    """A room's usable floor: its box less the walls."""
    b = box(room.x, room.y, room.x + room.w, room.y + room.h)
    solid = engine.wall_solid(plan)
    return b.difference(solid) if not solid.is_empty else b


# --------------------------------------------------------------- helpers
SIDES = ("N", "S", "E", "W")


def wall_slots(clear: Polygon, side: str, depth: float, length: float,
               step: float = 0.25):
    """Candidate footprints standing against one wall of a room, offered from
    the middle outwards so a piece lands centred when nothing forces it."""
    x0, y0, x1, y1 = clear.bounds
    out = []
    if side in ("N", "S"):
        span = x1 - x0 - length
        if span < -1e-6:
            return out
        y = (y1 - depth - GAP) if side == "N" else (y0 + GAP)
        n = max(1, int(span / step) + 1)
        idx = sorted(range(n), key=lambda i: abs(i - (n - 1) / 2))
        for i in idx:
            x = x0 + min(span, i * step)
            out.append(box(x, y, x + length, y + depth))
    else:
        span = y1 - y0 - length
        if span < -1e-6:
            return out
        x = (x1 - depth - GAP) if side == "E" else (x0 + GAP)
        n = max(1, int(span / step) + 1)
        idx = sorted(range(n), key=lambda i: abs(i - (n - 1) / 2))
        for i in idx:
            y = y0 + min(span, i * step)
            out.append(box(x, y, x + depth, y + length))
    return out


def _side_zone(plan: Plan, room, side: str) -> str:
    """The compass zone a wall of this room faces."""
    d = {"N": (0, 1), "S": (0, -1), "E": (1, 0), "W": (-1, 0)}[side]
    return F.zone_of(d[0], d[1], plan.north_deg)


# a full-height piece must not stand across a window (it blocks the light and
# the opening); low pieces (bed, counter, desk) may sit under one
TALL = {"wardrobe", "fridge", "tv_unit", "bookshelf", "cupboard", "almirah"}


def _window_zones(plan: Plan) -> list:
    """A shallow rectangle over every window, projecting a foot into the room
    on both faces — the area a TALL piece must not cover. Memoised per plan
    (it is asked for on every tall-piece placement)."""
    cache = getattr(plan, "_wz_cache", None)
    if cache is not None:
        return cache
    zones = []
    for o in plan.openings:
        if getattr(o, "type", "") not in ("window", "vent"):
            continue
        w = plan.wall(o.wall_id)
        if w is None:
            continue
        try:
            a = w.point_at(o.pos)
            b = w.point_at(o.pos + o.width)
        except Exception:
            continue
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1e-9
        ux, uy = dx / L, dy / L
        px, py = -uy, ux
        d = 1.0
        pts = [(a[0] - px * d, a[1] - py * d), (b[0] - px * d, b[1] - py * d),
               (b[0] + px * d, b[1] + py * d), (a[0] + px * d, a[1] + py * d)]
        try:
            poly = Polygon(pts)
            if poly.is_valid and not poly.is_empty:
                zones.append(poly)
        except Exception:
            pass
    try:
        plan._wz_cache = zones
    except Exception:
        pass
    return zones


def _fits(fp: Polygon, clear: Polygon, bad: Polygon, taken: list) -> bool:
    if not clear.contains(fp.buffer(-0.02)):
        return False
    if not bad.is_empty and fp.intersects(bad.buffer(-0.02)):
        return False
    return all(not fp.intersects(t.buffer(-0.02)) for t in taken)


def _front(fp: Polygon, side: str, depth: float) -> Polygon:
    """The clearance strip a piece needs in front of it."""
    x0, y0, x1, y1 = fp.bounds
    if side == "N":
        return box(x0, y0 - depth, x1, y0)
    if side == "S":
        return box(x0, y1, x1, y1 + depth)
    if side == "E":
        return box(x0 - depth, y0, x0, y1)
    return box(x1, y0, x1 + depth, y1)


# --------------------------------------------------------------- placing
def place_piece(plan, room, kind, clear, bad, taken, prefer=None,
                front_clear=0.0, tag="", strict=False):
    """Put one piece on the best wall that works. Returns a Furniture or None.

    Walls are tried in Vaastu order first; if none of those leaves the piece
    its clearances, the rest are tried and the compromise is recorded. With
    `strict=True` the walls are tried in the EXACT `prefer` order (Vaastu is
    still recorded but does not reorder) — used when circulation must win, e.g.
    a bed head that has to go on a short wall for side access.
    """
    dep_mm, len_mm = F.CATALOGUE.get(kind, (600, 900))
    depth, length = F.ft(dep_mm), F.ft(len_mm)
    fam = F.family(kind)
    good, badzones, _note = F.VAASTU.get(fam, ((), (), ""))
    windows = _window_zones(plan) if kind in TALL else []

    order = []
    for i, side in enumerate(prefer or SIDES):
        z = _side_zone(plan, room, side)
        rank = 0 if z in good else (2 if z in badzones else 1)
        order.append((i if strict else rank, side, z))
    order.sort(key=lambda t: t[0])

    for rank, side, z in order:
        for fp in wall_slots(clear, side, depth, length):
            if not _fits(fp, clear, bad, taken):
                continue
            # a full-height piece must not stand across a window
            if windows and any(fp.intersection(wz).area > 0.15
                               for wz in windows):
                continue
            if front_clear > 0:
                # the strip in front must be real floor, and empty. Measured
                # by AREA, not by touching: a hairline contact at a corner is
                # not a blocked approach, but a piece standing in it is.
                strip = _front(fp, side, front_clear)
                if strip.difference(clear).area > 0.2:
                    continue
                if any(strip.intersection(t).area > 0.2 for t in taken):
                    continue
                if not bad.is_empty and strip.intersection(bad).area > 0.2:
                    continue
            x0, y0, x1, y1 = fp.bounds
            verdict, reason = F.vaastu_check(fam, z)
            return Furniture(kind=kind, x=x0, y=y0, w=x1 - x0, h=y1 - y0,
                             room=room.name, tag=tag, facing=side, zone=z,
                             verdict=verdict, reason=reason)
    return None


def _entry_wall(plan, room):
    """Which wall (N/S/E/W) of THIS room the entrance opening sits on — a door
    OR an open pass-through — found by geometry (the opening's midpoint on the
    room's boundary), so it is right even when many rooms share the name
    'BEDROOM' / 'KITCHEN'."""
    tol = 0.6
    for o in plan.openings:
        if not (getattr(o, "is_door", False)
                or getattr(o, "type", "") == "open"):
            continue
        w = plan.wall(o.wall_id)
        if w is None:
            continue
        try:
            px, py = w.point_at(o.pos + o.width / 2)
        except Exception:
            continue
        in_x = room.x - tol <= px <= room.x + room.w + tol
        in_y = room.y - tol <= py <= room.y + room.h + tol
        if in_x and abs(py - room.y) < tol:
            return "S"
        if in_x and abs(py - (room.y + room.h)) < tol:
            return "N"
        if in_y and abs(px - room.x) < tol:
            return "W"
        if in_y and abs(px - (room.x + room.w)) < tol:
            return "E"
    return None


def _bedroom(plan, room, clear, bad, taken, out, notes, master: bool):
    """Bed first — it decides everything else in the room."""
    area = room.w * room.h
    bed = "bed_queen" if (master or area >= 140) else "bed_double"
    if area < 90:
        bed = "bed_single"

    # Circulation beats the Vaastu wall. The proven compact-bedroom layout is:
    # bed head on a SHORT wall (never the entry wall), pushed to ONE side wall,
    # and the WARDROBE on the OPPOSITE side wall — you walk in down the aisle
    # between them and reach both. We search corners for the arrangement that
    # leaves the widest bed↔wardrobe walkway (≥ ~600 mm), shrinking the bed if
    # the big one will not leave a walk.
    entry = _entry_wall(plan, room)
    short = ["N", "S"] if room.w <= room.h else ["E", "W"]
    long_ = ["E", "W"] if room.w <= room.h else ["N", "S"]
    heads = ([s for s in short if s != entry] + [s for s in long_ if s != entry]
             + ([entry] if entry else []))
    OPP = {"N": "S", "S": "N", "E": "W", "W": "E"}
    cx0, cy0, cx1, cy1 = clear.bounds
    walk_min = F.ft(600)
    wd_dep = F.ft(F.CATALOGUE["wardrobe"][0])

    def corner_bed(kind, head, push):
        """The bed in the (head × push) corner — head against `head`, one long
        side against the `push` wall."""
        dep = F.ft(F.CATALOGUE[kind][0])       # perpendicular (bed length)
        wid = F.ft(F.CATALOGUE[kind][1])       # along the head wall (bed width)
        if head in ("N", "S"):
            by1, by0 = ((cy1 - GAP, cy1 - GAP - dep) if head == "N"
                        else (cy0 + GAP + dep, cy0 + GAP))
            bx0, bx1 = ((cx1 - GAP - wid, cx1 - GAP) if push == "E"
                        else (cx0 + GAP, cx0 + GAP + wid))
        else:
            bx1, bx0 = ((cx1 - GAP, cx1 - GAP - dep) if head == "E"
                        else (cx0 + GAP + dep, cx0 + GAP))
            by0, by1 = ((cy1 - GAP - wid, cy1 - GAP) if push == "N"
                        else (cy0 + GAP, cy0 + GAP + wid))
        fp = box(bx0, by0, bx1, by1)
        if not _fits(fp, clear, bad, taken):
            return None
        z = _side_zone(plan, room, head)
        v, r = F.vaastu_check(F.family(kind), z)
        return Furniture(kind=kind, x=bx0, y=by0, w=bx1 - bx0, h=by1 - by0,
                         room=room.name, facing=head, zone=z, verdict=v,
                         reason=r)

    best = None                                  # (walk, bed, wardrobe)
    for kind in (bed, "bed_double", "bed_single"):
        for head in heads:
            for push in (["E", "W"] if head in ("N", "S") else ["N", "S"]):
                p = corner_bed(kind, head, push)
                if p is None:
                    continue
                taken2 = taken + [box(p.x, p.y, p.x + p.w, p.y + p.h)]
                other = OPP[push]                # wardrobe on the far side wall
                wd = place_piece(plan, room, "wardrobe", clear, bad, taken2,
                                 prefer=[other], strict=True,
                                 front_clear=F.ft(F.CLEAR["wardrobe_front"]))
                # the walkway = room span minus bed width minus wardrobe depth
                if head in ("N", "S"):
                    walk = (cx1 - cx0) - p.w - (wd_dep if wd else 0)
                else:
                    walk = (cy1 - cy0) - p.h - (wd_dep if wd else 0)
                if wd is None:
                    continue
                if best is None or walk > best[0]:
                    best = (walk, p, wd)
            if best and best[0] >= walk_min:
                break
        if best and best[0] >= walk_min:
            break

    if best is None:
        # could not pair bed + wardrobe with a walk — place the bed alone on the
        # best wall so the room is at least usable
        piece = place_piece(plan, room, bed, clear, bad, taken, prefer=heads,
                            strict=True) or \
            place_piece(plan, room, "bed_single", clear, bad, taken)
        if piece is None:
            notes.append(f"{room.name}: no wall takes a bed")
            return
        out.append(piece)
        taken.append(box(piece.x, piece.y, piece.x + piece.w, piece.y + piece.h))
        wd = None
        notes.append(f"{room.name}: too tight for a bed AND a wardrobe with a "
                     "walk between — wardrobe left out")
    else:
        walk, piece, wd = best
        out.append(piece)
        taken.append(box(piece.x, piece.y, piece.x + piece.w, piece.y + piece.h))
        out.append(wd)
        taken.append(box(wd.x, wd.y, wd.x + wd.w, wd.y + wd.h))
        if walk < walk_min:
            notes.append(f"{room.name}: only {walk*12:.0f}\" walk between bed "
                         "and wardrobe — a sliding-door unit is advised")

    # one bedside at the pillow end, on the aisle side (never crushed to a wall)
    bs_d, bs_l = (F.ft(v) for v in F.CATALOGUE["bedside"])
    for sign in (1, -1):
        if piece.facing in ("N", "S"):
            bx = piece.x + (piece.w if sign > 0 else -bs_l)
            by = (piece.y + piece.h - bs_d) if piece.facing == "N" else piece.y
            fp = box(bx, by, bx + bs_l, by + bs_d)
        else:
            by = piece.y + (piece.h if sign > 0 else -bs_l)
            bx = (piece.x + piece.w - bs_d) if piece.facing == "E" else piece.x
            fp = box(bx, by, bx + bs_d, by + bs_l)
        if _fits(fp, clear, bad, taken):
            x0, y0, x1, y1 = fp.bounds
            out.append(Furniture(kind="bedside", x=x0, y=y0, w=x1 - x0,
                                 h=y1 - y0, room=room.name, zone=piece.zone,
                                 verdict="n/a"))
            taken.append(fp)
            break                                # one is enough in these rooms

    # ONE workstation per bedroom (REV 2): the master keeps the dresser,
    # other bedrooms get the study table — never both. It goes on a wall the
    # bed and wardrobe do NOT use, so the chair has real floor to pull into; if
    # no such wall leaves the chair its pull-back, the workstation is LEFT OUT
    # rather than jammed against the bed with nowhere to sit or walk.
    work = "dresser" if master else "study_table"
    avoid = {getattr(piece, "facing", None), getattr(wd, "facing", None)}
    pref = [s for s in SIDES if s not in avoid] + \
           [s for s in SIDES if s in avoid]
    wk = place_piece(plan, room, work, clear, bad, taken, prefer=pref,
                     front_clear=F.ft(F.CLEAR["chair_pullback"]))
    if wk:
        out.append(wk)
        taken.append(box(wk.x, wk.y, wk.x + wk.w, wk.y + wk.h))
        notes.append(f"{room.name}: {F.LABEL[work].lower()} is the one "
                     "workstation in this room (REV 2 rule)")
    else:
        notes.append(f"{room.name}: no wall leaves a {F.LABEL[work].lower()} "
                     "its chair pull-back — left out to keep the room walkable")


def _door_centroid(plan, room):
    """The average position of the doors / openings on this room's boundary —
    the 'busy' side. Seating is kept AWAY from it so you can walk in and reach
    the other rooms without stepping over the sofa."""
    tol = 1.0
    pts = []
    for o in plan.openings:
        if not (getattr(o, "is_door", False)
                or getattr(o, "type", "") == "open"):
            continue
        w = plan.wall(o.wall_id)
        if w is None:
            continue
        try:
            px, py = w.point_at(o.pos + o.width / 2)
        except Exception:
            continue
        inx = room.x - tol <= px <= room.x + room.w + tol
        iny = room.y - tol <= py <= room.y + room.h + tol
        onb = ((abs(py - room.y) < tol or abs(py - (room.y + room.h)) < tol)
               and inx) or \
              ((abs(px - room.x) < tol or abs(px - (room.x + room.w)) < tol)
               and iny)
        if inx and iny and onb:
            pts.append((px, py))
    if not pts:
        return None
    return (sum(p[0] for p in pts) / len(pts),
            sum(p[1] for p in pts) / len(pts))


def _wall_behind(plan, room, side, fp, cover=0.6) -> bool:
    """A seat's BACK must stand against a real wall — never an open edge (a
    stair mouth, an open-plan boundary). True when actual wall segments cover
    at least `cover` of the footprint's run on that side of the room."""
    x0, y0, x1, y1 = fp.bounds
    tol = 1.2
    span = 0.0
    if side in ("N", "S"):
        line_y = room.y + room.h if side == "N" else room.y
        for w in plan.walls:
            if getattr(w, "railing", False) or abs(w.y1 - w.y2) > 0.5:
                continue
            if abs((w.y1 + w.y2) / 2 - line_y) > tol:
                continue
            lo, hi = sorted((w.x1, w.x2))
            span += max(0.0, min(hi, x1) - max(lo, x0))
        return span >= (x1 - x0) * cover
    line_x = room.x + room.w if side == "E" else room.x
    for w in plan.walls:
        if getattr(w, "railing", False) or abs(w.x1 - w.x2) > 0.5:
            continue
        if abs((w.x1 + w.x2) / 2 - line_x) > tol:
            continue
        lo, hi = sorted((w.y1, w.y2))
        span += max(0.0, min(hi, y1) - max(lo, y0))
    return span >= (y1 - y0) * cover


def _sofa_walls(clear, dc):
    """Candidate sofa walls, farthest from the doors first."""
    cx0, cy0, cx1, cy1 = clear.bounds
    mids = {"N": ((cx0 + cx1) / 2, cy1), "S": ((cx0 + cx1) / 2, cy0),
            "E": (cx1, (cy0 + cy1) / 2), "W": (cx0, (cy0 + cy1) / 2)}

    def far(pt):
        return 0.0 if dc is None else (pt[0] - dc[0]) ** 2 + (pt[1] - dc[1]) ** 2
    return sorted(SIDES, key=lambda s: -far(mids[s])), far


def _sofa_on_side(plan, room, clear, bad, taken, side, far):
    """The best sofa footprint on ONE given wall (back against real wall)."""
    for kind in ("sofa_3", "sofa_2"):
        dep, length = F.ft(F.CATALOGUE[kind][0]), F.ft(F.CATALOGUE[kind][1])
        slots = wall_slots(clear, side, dep, length)
        slots.sort(key=lambda fp: -far((fp.centroid.x, fp.centroid.y)))
        for fp in slots:
            if not _fits(fp, clear, bad, taken):
                continue
            if not _wall_behind(plan, room, side, fp):
                continue                       # open edge — nothing to back onto
            strip = _front(fp, side, F.ft(750))   # room to sit + a walkway
            if strip.difference(clear).area > 0.4:
                continue
            bx0, by0, bx1, by1 = fp.bounds
            z = _side_zone(plan, room, side)
            v, r = F.vaastu_check(F.family(kind), z)
            return Furniture(kind=kind, x=bx0, y=by0, w=bx1 - bx0,
                             h=by1 - by0, room=room.name, facing=side,
                             zone=z, verdict=v, reason=r)
    return None


def _place_sofa(plan, room, clear, bad, taken, dc):
    """Sofa on the wall FARTHEST from the doors, pushed to the far corner, so
    the seating sits out of the circulation and the entry stays clear."""
    walls, far = _sofa_walls(clear, dc)
    for side in walls:
        p = _sofa_on_side(plan, room, clear, bad, taken, side, far)
        if p:
            return p
    return None


def _tv_for(plan, room, clear, bad, taken, sofa):
    """The TV unit on the wall the sofa LOOKS AT, lined up in front of it — or
    None when that wall has no clear run (doors / openings)."""
    opp = {"N": "S", "S": "N", "E": "W", "W": "E"}[sofa.facing]
    td, tl = F.ft(F.CATALOGUE["tv_unit"][0]), F.ft(F.CATALOGUE["tv_unit"][1])
    sb = box(sofa.x, sofa.y, sofa.x + sofa.w, sofa.y + sofa.h).bounds
    for fp in wall_slots(clear, opp, td, tl):
        if not _fits(fp, clear, bad, taken):
            continue
        fb = fp.bounds
        if sofa.facing in ("W", "E"):            # sofa/TV face along x → align y
            overlap = min(sb[3], fb[3]) - max(sb[1], fb[1])
        else:                                     # face along y → align x
            overlap = min(sb[2], fb[2]) - max(sb[0], fb[0])
        if overlap > 1.5:                         # genuinely in front of the sofa
            z = _side_zone(plan, room, opp)
            v, r = F.vaastu_check(F.family("tv_unit"), z)
            return Furniture(kind="tv_unit", x=fb[0], y=fb[1], w=fb[2] - fb[0],
                             h=fb[3] - fb[1], room=room.name, facing=opp,
                             zone=z, verdict=v, reason=r)
    return None


def _living(plan, room, clear, bad, taken, out, notes):
    dc = _door_centroid(plan, room)
    # SEATING GROUP as a pair: the sofa AND the TV it faces are chosen together.
    # Walk the candidate sofa walls (farthest from the doors first); the first
    # wall whose OPPOSITE wall also takes the TV wins. Only if no wall pairs do
    # we keep the best lone sofa and say 'wall-mount the TV'.
    walls, far = _sofa_walls(clear, dc)
    sofa = tv = first = None
    for side in walls:
        s = _sofa_on_side(plan, room, clear, bad, taken, side, far)
        if s is None:
            continue
        first = first or s
        t = _tv_for(plan, room, clear, bad,
                    taken + [box(s.x, s.y, s.x + s.w, s.y + s.h)], s)
        if t:
            sofa, tv = s, t
            break
    if sofa is None:
        sofa = first or place_piece(plan, room, "sofa_2", clear, bad, taken)
    if sofa:
        out.append(sofa)
        taken.append(box(sofa.x, sofa.y, sofa.x + sofa.w, sofa.y + sofa.h))
    if tv:
        out.append(tv)
        taken.append(box(tv.x, tv.y, tv.x + tv.w, tv.y + tv.h))
    elif sofa:
        notes.append(f"{room.name}: the wall facing the sofa is taken by "
                     "doors/openings — wall-mount the TV there")

    # centre table squarely IN FRONT of the sofa, centred on the sofa's length,
    # with a 1.5 ft (≈450 mm) gap between the sofa front and the table
    if sofa and sofa.facing in SIDES:
        g = 1.5                                    # feet, the gap the user asked
        cw, cl = F.ft(600), F.ft(1100)             # table depth, length
        sx, sy = sofa.centre
        ct = None
        if sofa.facing in ("W", "E"):
            dx = 1 if sofa.facing == "W" else -1
            front = sx + dx * (sofa.w / 2)
            near = front + dx * g
            cx0 = near if dx > 0 else near - cw
            fp = box(cx0, sy - cl / 2, cx0 + cw, sy + cl / 2)   # long side ∥ sofa
        else:
            dy = -1 if sofa.facing == "N" else 1
            front = sy + dy * (sofa.h / 2)
            near = front + dy * g
            cy0 = near if dy > 0 else near - cw
            fp = box(sx - cl / 2, cy0, sx + cl / 2, cy0 + cw)
        if _fits(fp, clear, bad, taken):
            bx0, by0, bx1, by1 = fp.bounds
            ct = Furniture(kind="coffee_table", x=bx0, y=by0, w=bx1 - bx0,
                           h=by1 - by0, room=room.name, verdict="n/a")
        if ct is None:                             # tight spot — best effort
            d = {"N": (0, -1), "S": (0, 1), "E": (-1, 0), "W": (1, 0)}[sofa.facing]
            near_pt = (sx + d[0] * (sofa.w / 2 + g + cw / 2),
                       sy + d[1] * (sofa.h / 2 + g + cw / 2))
            ct = place_free(plan, room, "coffee_table", clear, bad, taken, near_pt)
        if ct:
            out.append(ct)
            taken.append(box(ct.x, ct.y, ct.x + ct.w, ct.y + ct.h))
    return sofa


def _open_ring(fp, wall_side, pad):
    """The chair zone round a table standing against `wall_side` — the pad ring
    on the THREE open sides only (no chair against the wall)."""
    x0, y0, x1, y1 = fp.bounds
    full = box(x0 - pad, y0 - pad, x1 + pad, y1 + pad)
    cut = {"N": box(x0 - pad, y1, x1 + pad, y1 + pad),
           "S": box(x0 - pad, y0 - pad, x1 + pad, y0),
           "E": box(x1, y0 - pad, x1 + pad, y1 + pad),
           "W": box(x0 - pad, y0 - pad, x0, y1 + pad)}.get(wall_side)
    ring = full.difference(fp)
    return ring.difference(cut) if cut is not None else ring


def _dining_on_wall(plan, room, clear, bad, taken, kind, prefer):
    """Place the dining table AGAINST a wall — chairs on the three open sides,
    none against the wall — trying the preferred walls in order. Returns a
    Furniture with `facing` = the wall it sits on, or None."""
    dep, length = F.ft(F.CATALOGUE[kind][0]), F.ft(F.CATALOGUE[kind][1])
    chair = F.ft(480)
    for side in prefer:
        for fp in wall_slots(clear, side, dep, length):
            if not _fits(fp, clear, bad, taken):
                continue
            ring = _open_ring(fp, side, chair)          # the 3-side chair zone
            if ring.is_empty:
                continue
            # a chair may overhang the room edge a little or tuck near a door
            # path, but it must NOT sit on another piece
            if ring.difference(clear).area > 0.6:
                continue                                 # chairs well off the floor
            if any(ring.intersection(t).area > 0.15 for t in taken):
                continue                                 # a chair would hit a piece
            bx0, by0, bx1, by1 = fp.bounds
            z = _side_zone(plan, room, side)
            return Furniture(kind=kind, x=bx0, y=by0, w=bx1 - bx0, h=by1 - by0,
                             room=room.name, facing=side, zone=z, verdict="n/a")
    return None


def _dining(plan, room, clear, bad, taken, out, notes, anchor=None,
            sizes=("dining_6", "dining_4"), prefer_walls=None):
    """Place the dining table (largest that keeps a route round every open
    side). In a shared living/dining room `prefer_walls` puts the table AGAINST
    a wall (chairs on three sides, the wall-side chair dropped) away from the
    sofa; otherwise it free-stands. `sizes` tries the smaller table first in a
    shared room so the walk between the two zones survives."""
    chair = F.ft(480)
    for kind in sizes:
        # 1) against a wall, tidy, wall-side chair dropped
        if prefer_walls:
            t = _dining_on_wall(plan, room, clear, bad, taken, kind,
                                prefer_walls)
            if t:
                out.append(t)
                taken.append(box(t.x - chair, t.y - chair,
                                 t.x + t.w + chair, t.y + t.h + chair))
                return
        # 2) free-standing fallback — table + chair ring clear of everything;
        # try the anchor then the room centre (two probes keeps it fast)
        t = place_free(plan, room, kind, clear, bad, taken, near=anchor,
                       pad=chair)
        if t is None and anchor is not None:
            t = place_free(plan, room, kind, clear, bad, taken, near=None,
                           pad=chair)
        if t is None:
            continue
        fp = box(t.x, t.y, t.x + t.w, t.y + t.h)
        ring = fp.buffer(F.ft(F.CLEAR["chair_pullback"]))
        if not clear.buffer(0.05).contains(ring.buffer(-0.1)):
            ring = fp.buffer(F.ft(F.CLEAR["route_spur"]))
            if not clear.buffer(0.05).contains(ring.buffer(-0.1)):
                notes.append(f"{room.name}: a {kind.split('_')[1]}-seat table "
                             "leaves under 600 clear — trying smaller "
                             "(REV 2 resize protocol)")
                continue
            notes.append(f"{room.name}: perimeter is between 600 and 750 — "
                         "kept at the hard minimum rather than reducing seats")
        out.append(t)
        taken.append(box(t.x - chair, t.y - chair,
                         t.x + t.w + chair, t.y + t.h + chair))
        return

    # No properly-placed dining fits. Do NOT cram a table into a leftover gap —
    # that is what reads as 'random furniture'. Leave it out and say why.
    notes.append(f"{room.name}: no dining table fits with a real chair pull-back "
                 "— the hall is ringed by doors; put the dining in/near the "
                 "kitchen or use a wall drop-leaf")


def _kitchen(plan, room, clear, bad, taken, out, notes):
    """An L of counter along the two longest usable walls — never the
    entry/opening wall (that has to stay a clear passage) — then the fridge at
    a free end, off the opening and off any window."""
    x0, y0, x1, y1 = clear.bounds
    W, H = x1 - x0, y1 - y0
    depth = F.ft(600)
    entry = _entry_wall(plan, room)

    def wall_len(s):
        return W if s in ("N", "S") else H

    # the counter walls: longest first, and NEVER the entry/opening wall (a
    # counter across the opening is what boxes the kitchen in)
    walls = sorted([s for s in SIDES if s != entry], key=lambda s: -wall_len(s))
    walls = walls or list(SIDES)

    counter_side = None
    for side in walls:                       # run 1 — the main counter
        length = wall_len(side)
        placed = False
        for fp in wall_slots(clear, side, depth, length - 0.1):
            if _fits(fp, clear, bad, taken):
                bx0, by0, bx1, by1 = fp.bounds
                z = _side_zone(plan, room, side)
                out.append(Furniture(kind="counter", x=bx0, y=by0, w=bx1 - bx0,
                                     h=by1 - by0, room=room.name, facing=side,
                                     zone=z, verdict="n/a",
                                     note="hob SE, sink NE"))
                taken.append(fp)
                counter_side = side
                placed = True
                break
        if placed:
            break

    # run 2 — the L return on a wall perpendicular to run 1 (skip the entry
    # wall), only if it is long enough to be useful; run 1 already holds the
    # shared corner, so _fits keeps the two from overlapping
    if counter_side:
        perp = (["E", "W"] if counter_side in ("N", "S") else ["N", "S"])
        perp = [s for s in perp if s != entry] + [s for s in perp if s == entry]
        for side in perp:
            if wall_len(side) - depth < F.ft(1200):
                continue
            for fp in wall_slots(clear, side, depth, wall_len(side) - depth):
                if _fits(fp, clear, bad, taken):
                    bx0, by0, bx1, by1 = fp.bounds
                    z = _side_zone(plan, room, side)
                    out.append(Furniture(kind="counter", x=bx0, y=by0,
                                         w=bx1 - bx0, h=by1 - by0,
                                         room=room.name, facing=side, zone=z,
                                         verdict="n/a", note="return run"))
                    taken.append(fp)
                    break
            else:
                continue
            break

    # the fridge lives in a CORNER next to the counter's end — never floated
    # mid-wall. Try the four corners, nearest to the counter first.
    fd = F.ft(700)
    counters = [f for f in out if f.kind == "counter" and f.room == room.name]
    cpolys = [box(f.x, f.y, f.x + f.w, f.y + f.h) for f in counters]
    corners = [(x0 + GAP, y0 + GAP), (x1 - fd - GAP, y0 + GAP),
               (x0 + GAP, y1 - fd - GAP), (x1 - fd - GAP, y1 - fd - GAP)]
    best = None
    for cx, cy in corners:
        fp = box(cx, cy, cx + fd, cy + fd)
        if not _fits(fp, clear, bad, taken):
            continue
        d = min((fp.distance(cp) for cp in cpolys), default=0.0)
        if best is None or d < best[0]:
            best = (d, fp)
    fr = None
    if best:
        bx0, by0, bx1, by1 = best[1].bounds
        zx = "E" if (bx0 + bx1) / 2 > (x0 + x1) / 2 else "W"
        z = _side_zone(plan, room, zx)
        v, r = F.vaastu_check("fridge", z)
        fr = Furniture(kind="fridge", x=bx0, y=by0, w=bx1 - bx0, h=by1 - by0,
                       room=room.name, facing=zx, zone=z, verdict=v, reason=r)
    if fr is None:
        fr = place_piece(plan, room, "fridge", clear, bad, taken)
    if fr:
        out.append(fr)
        taken.append(box(fr.x, fr.y, fr.x + fr.w, fr.y + fr.h))


def _wet(plan, room, clear, bad, taken, out, notes):
    """Every fixture in ONE straight row against a single wet wall — basin, WC,
    then a shower ONLY if the room is big enough. The opposite side is left
    open as walking space; a small toilet gets just basin + WC, never crammed
    to the point there is nowhere to stand."""
    door = None
    for o in plan.openings:
        if o.is_door and o.swing and o.swing.room \
                and o.swing.room.strip().lower() == room.name.strip().lower():
            w = plan.wall(o.wall_id)
            if w:
                door = w.point_at(o.pos + o.width / 2)
            break

    x0, y0, x1, y1 = clear.bounds
    W, H = x1 - x0, y1 - y0
    area = W * H

    def wall_len(s):
        return W if s in ("N", "S") else H

    # the door's own wall is kept as the approach; the wet wall is the longest
    # of the others so the fixtures line up along it
    door_side = None
    if door is not None:
        dside = {"N": y1 - door[1], "S": door[1] - y0,
                 "E": x1 - door[0], "W": door[0] - x0}
        door_side = min(dside, key=lambda s: dside[s])
    cand = [s for s in SIDES if s != door_side] or list(SIDES)
    wet_wall = max(cand, key=wall_len)
    horiz = wet_wall in ("N", "S")
    run = wall_len(wet_wall)

    # EVERY toilet gets a shower — common or attached. As you enter it reads
    # basin → WC → shower, so along the wall the SHOWER sits FARTHEST from the
    # door (its wet zone away from the entry) and the basin nearest. The row is
    # laid from the far end first, so the far-end item is listed first here.
    row = []
    for kind in ("shower", "wc", "basin"):
        dmm, lmm = F.CATALOGUE.get(kind, (450, 550))
        row.append([kind, F.ft(dmm), F.ft(lmm)])

    # lay the row against the wet wall, starting from the end FARTHEST from the
    # door so the entry stays open, every fixture aligned on the one wall
    lo = (x0 + GAP) if horiz else (y0 + GAP)
    hi = (x1 - GAP) if horiz else (y1 - GAP)
    start_hi = True
    if door is not None:
        dpos = door[0] if horiz else door[1]
        start_hi = dpos < (lo + hi) / 2      # door low → start from the high end
    cursor = hi if start_hi else lo

    for kind, dep, length in row:
        if horiz:
            yy = (y1 - dep - GAP) if wet_wall == "N" else (y0 + GAP)
            if start_hi:
                bx0, bx1 = cursor - length, cursor
            else:
                bx0, bx1 = cursor, cursor + length
            fp = box(bx0, yy, bx1, yy + dep)
        else:
            xx = (x1 - dep - GAP) if wet_wall == "E" else (x0 + GAP)
            if start_hi:
                by0, by1 = cursor - length, cursor
            else:
                by0, by1 = cursor, cursor + length
            fp = box(xx, by0, xx + dep, by1)
        if _fits(fp, clear, bad, taken):
            bx0, by0, bx1, by1 = fp.bounds
            z = _side_zone(plan, room, wet_wall)
            out.append(Furniture(kind=kind, x=bx0, y=by0, w=bx1 - bx0,
                                 h=by1 - by0, room=room.name, facing=wet_wall,
                                 zone=z, verdict="n/a"))
            taken.append(fp)
            cursor = (cursor - length - GAP) if start_hi else \
                (cursor + length + GAP)
            continue
        # it will not sit in the row (a short wall, the door's approach): put it
        # tidily on an ADJACENT wall instead of dropping it — the shower + WC
        # stay in their line, the basin steps round the corner
        fc = {"basin": F.ft(F.CLEAR["basin_front"]),
              "wc": F.ft(F.CLEAR["wc_front"])}.get(kind, 0.0)
        pc = place_piece(plan, room, kind, clear, bad, taken,
                         prefer=[w for w in SIDES if w != wet_wall] + [wet_wall],
                         front_clear=fc)
        if pc is None and fc:
            pc = place_piece(plan, room, kind, clear, bad, taken,
                             prefer=[w for w in SIDES if w != wet_wall])
        if pc:
            out.append(pc)
            taken.append(box(pc.x, pc.y, pc.x + pc.w, pc.y + pc.h))

    # the BASIN must appear in every toilet — as you enter you wash your hands.
    # If neither the row nor the clearance fallback took it, place it on ANY
    # wall with the clearance waived (a tight toilet still gets its basin).
    rb0 = box(room.x, room.y, room.x + room.w, room.y + room.h)
    if not any(f.kind == "basin" and rb0.contains(footprint(f).centroid)
               for f in out):
        pc = place_piece(plan, room, "basin", clear, bad, taken)
        if pc is None:
            pc = place_piece(plan, room, "basin", clear, Polygon(), taken)
        if pc:
            out.append(pc)
            taken.append(box(pc.x, pc.y, pc.x + pc.w, pc.y + pc.h))
            notes.append(f"{room.name}: basin squeezed in with reduced "
                         "clearance — the room is tight")
        else:
            notes.append(f"{room.name}: NO basin fits — the room is too small")

    # the shower must appear in EVERY toilet — if the row could not take it,
    # drop it into the free corner farthest from the door, shrinking a compact
    # cubicle (900 → 800 → 750 → 700 mm) until one fits rather than skipping it
    rb = box(room.x, room.y, room.x + room.w, room.y + room.h)
    placed = {f.kind for f in out if rb.contains(footprint(f).centroid)}
    if "shower" not in placed:
        best = None
        for s in (F.ft(900), F.ft(800), F.ft(750), F.ft(700)):
            for cx, cy in ((x0 + GAP, y0 + GAP), (x1 - s - GAP, y0 + GAP),
                           (x0 + GAP, y1 - s - GAP), (x1 - s - GAP, y1 - s - GAP)):
                fp = box(cx, cy, cx + s, cy + s)
                if not _fits(fp, clear, bad, taken):
                    continue
                d = 1e9 if door is None else \
                    (cx + s / 2 - door[0]) ** 2 + (cy + s / 2 - door[1]) ** 2
                if best is None or d > best[0]:
                    best = (d, fp)
            if best:
                break                          # keep the largest size that fits
        if best:
            bx0, by0, bx1, by1 = best[1].bounds
            out.append(Furniture(kind="shower", x=bx0, y=by0, w=bx1 - bx0,
                                 h=by1 - by0, room=room.name, verdict="n/a",
                                 note="corner shower"))
            taken.append(best[1])
        else:
            notes.append(f"{room.name}: no room for a shower — too small even "
                         "for a corner cubicle")


def place_free(plan, room, kind, clear, bad, taken, near=None, tag="",
               pad=0.0):
    """A piece that stands away from the walls — a coffee or dining table.

    `pad` is the space the piece's own CHAIRS occupy beyond the table box: a
    dining table's chairs stick out ~480 mm all round, so the table plus that
    ring must be clear of the other furniture, otherwise the chairs overlap a
    neighbour (the classic 'dining chairs on the centre table' clash)."""
    from shapely.prepared import prep
    dep_mm, len_mm = F.CATALOGUE.get(kind, (600, 900))
    depth, length = F.ft(dep_mm), F.ft(len_mm)
    x0, y0, x1, y1 = clear.bounds
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    if near is not None:
        cx, cy = near

    # prepared geometry makes the grid search an order of magnitude faster: the
    # clear floor and the union of every obstacle are each prepared ONCE, then
    # contains / intersects on each candidate is a cheap test
    inner = clear.buffer(-0.02)
    pinner = prep(inner)
    obst = unary_union([b for b in ([bad] if not bad.is_empty else []) + taken])
    pobst = prep(obst) if not obst.is_empty else None
    tk = [t for t in taken]

    def _ok(fp):
        if not pinner.contains(fp):
            return False
        if pobst is not None and pobst.intersects(fp.buffer(-0.02)):
            return False
        if pad > 0:
            ring = fp.buffer(pad)
            if any(ring.intersection(t).area > 0.15 for t in tk):
                return False
        return True

    step = 0.25
    best = None
    for wr, hr in ((length, depth), (depth, length)):     # try both ways round
        for dx in [i * step for i in range(-14, 15)]:
            for dy in [i * step for i in range(-14, 15)]:
                fp = box(cx + dx - wr / 2, cy + dy - hr / 2,
                         cx + dx + wr / 2, cy + dy + hr / 2)
                if not _ok(fp):
                    continue
                d = dx * dx + dy * dy
                if best is None or d < best[0]:
                    best = (d, fp)
        if best:
            break
    if not best:
        return None
    x0, y0, x1, y1 = best[1].bounds
    z = F.zone_of(((x0 + x1) / 2) - ((clear.bounds[0] + clear.bounds[2]) / 2),
                  ((y0 + y1) / 2) - ((clear.bounds[1] + clear.bounds[3]) / 2),
                  plan.north_deg)
    verdict, reason = F.vaastu_check(F.family(kind), z)
    return Furniture(kind=kind, x=x0, y=y0, w=x1 - x0, h=y1 - y0,
                     room=room.name, tag=tag, zone=z,
                     verdict=verdict, reason=reason)


def add_piece(plan_dict: dict, kind: str, room_name: str = "",
              wall: str = "") -> tuple[dict, str]:
    """Add ONE piece of a chosen kind, placed properly.

    The catalogue gives its standard size, the Vaastu table its preferred
    wall, and the same fitting rules keep it clear of swings and of what is
    already there. Placed, not dropped at the origin.
    """
    from dataclasses import asdict
    from . import autofix

    plan = Plan.from_dict(plan_dict)
    autofix.apply(plan)
    bad = blocked(plan)

    room = plan.room(room_name) if room_name else None
    if room is None:
        rooms = [r for r in plan.rooms if not r.open_area and not r.void]
        if not rooms:
            return plan_dict, "There is no enclosed room to put it in."
        room = max(rooms, key=lambda r: r.w * r.h)

    clear = clear_floor(plan, room)
    if clear.geom_type == "MultiPolygon":
        clear = max(clear.geoms, key=lambda g: g.area)
    taken = [footprint(f) for f in plan.furniture
             if (f.room or "").strip().lower() == room.name.strip().lower()]

    prefer = [wall] if wall in SIDES else None
    piece = place_piece(plan, room, kind, clear, bad, taken, prefer=prefer)
    if piece is None:
        piece = place_free(plan, room, kind, clear, bad, taken)
    if piece is None:
        return plan_dict, (f"No room on any wall of '{room.name}' for a "
                           f"{F.LABEL.get(kind, kind)}.")

    used = {f.tag for f in plan.furniture}
    n = len(plan.furniture) + 1
    while f"F{n}" in used:
        n += 1
    piece.tag = f"F{n}"
    plan.furniture.append(piece)

    out = dict(plan_dict)
    out["furniture"] = [asdict(f) for f in plan.furniture]
    return out, (f"{piece.tag} {F.LABEL.get(kind, kind)} placed on the "
                 f"{piece.facing} wall of {room.name} ({piece.zone}, "
                 f"{piece.verdict.lower()})")


# --------------------------------------------------------------- the run
# lower = more essential (removed LAST); >=2 may be dropped for circulation
_PRIORITY = {
    "bed_single": 0, "bed_double": 0, "bed_queen": 0, "bed_king": 0, "cot": 0,
    "wc": 0, "basin": 0, "shower": 0, "counter": 0, "sofa_3": 0, "sofa_2": 0,
    "dining_2": 0, "dining_4": 0, "dining_6": 0, "dining_8": 0,
    "wardrobe": 1, "fridge": 1, "bedside": 1,
    "tv_unit": 2, "dresser": 2, "study_table": 2, "coffee_table": 2,
    "armchair": 2, "shoe_rack": 3, "stool": 3, "side_table": 3,
}


def _circulation(plan, room, clear, out, notes):
    """Keep a real walking movement in the room. Every piece needs clear floor
    to reach and stand at it — in front of a wall piece, all round a free-
    standing table. A bed against a wall is walkable on its open sides; a piece
    that leaves no room to move around it is REMOVED (least essential first),
    exactly as a designer would thin a crowded room."""
    # how much clear floor a piece needs to be usable — a workstation needs the
    # chair pull-back AND room to stand, so it is judged harder than a shelf
    MINK = {"study_table": F.ft(750), "dresser": F.ft(700),
            "coffee_table": F.ft(400), "armchair": F.ft(450)}
    # by GEOMETRY, not by name — many rooms share the name 'HALL' / 'BEDROOM' in
    # an apartment, so a name filter would drag another unit's pieces in here
    rb = box(room.x, room.y, room.x + room.w, room.y + room.h)
    mine = [f for f in out if rb.contains(footprint(f).centroid)]
    if len(mine) < 2:
        return
    # try to remove the least essential pieces first
    order = sorted(mine, key=lambda f: -_PRIORITY.get(f.kind, 2))
    mineset = set(id(f) for f in mine)
    for f in order:
        if f not in out:
            continue
        if _PRIORITY.get(f.kind, 2) < 2:      # never drop an essential piece
            continue
        MIN = MINK.get(f.kind, F.ft(500))
        fp = footprint(f)
        rest = [footprint(g) for g in out
                if g is not f and id(g) in mineset]
        others = unary_union(rest) if rest else Polygon()
        if getattr(f, "facing", "") in SIDES:
            acc = _front(fp, f.facing, MIN).intersection(clear)
            need = 0.6
        else:
            acc = fp.buffer(MIN).difference(fp).intersection(clear)
            need = 0.5
        if acc.area < 1e-6:
            free = 0.0
        elif others.is_empty:
            free = 1.0
        else:
            free = acc.difference(others).area / acc.area
        if free < need:
            out.remove(f)
            notes.append(f"{room.name}: {f.kind} removed — it left no walking "
                         "space around it")


def furnish(plan_dict: dict) -> tuple[dict, list[str]]:
    """Lay out furniture across a finished floor plan.

    Returns the plan with a `furniture` list, and the notes — every assumption,
    every compromise and every room that could not take a piece.
    """
    from dataclasses import asdict
    from . import autofix

    plan = Plan.from_dict(plan_dict)
    # Lay out against the geometry that will actually be DRAWN. The auto-fix
    # pass flips door swings and punches open-area walls, so running it first
    # is what stops a piece being placed clear of a swing that then moves.
    autofix.apply(plan)
    notes: list[str] = []
    if plan.north_deg == 90:
        notes.append("No compass was given, so the top of the sheet is taken "
                     "as North. Every Vaastu call must be re-checked if the "
                     "actual north differs.")

    bad = blocked(plan)
    out: list[Furniture] = []

    rooms = sorted([r for r in plan.rooms if not r.open_area and not r.void],
                   key=lambda r: -(r.w * r.h))
    master_done = False

    for room in rooms:
        area = room.w * room.h
        clear = clear_floor(plan, room)
        if clear.is_empty or clear.area < 12:
            continue
        # a room whose floor is in pieces (a stair through it) — use the
        # largest piece
        if clear.geom_type == "MultiPolygon":
            clear = max(clear.geoms, key=lambda g: g.area)

        kit = F.kit_for(room.name, area)
        if not kit:
            continue
        taken: list = []
        n = (room.name or "").lower()

        is_dining = "dining" in n
        is_living = any(w in n for w in ("living", "drawing", "hall",
                                         "lounge", "family"))
        if any(w in n for w in ("toilet", "bath", "w.c", "wc", "washroom")):
            _wet(plan, room, clear, bad, taken, out, notes)
        elif any(w in n for w in ("kitchen", "pantry")):
            _kitchen(plan, room, clear, bad, taken, out, notes)
        elif is_living:
            # a LIVING room / apartment HALL seats the family: sofa, centre
            # table and TV — and it is ALSO the dining, so a compact (folding)
            # dining set is added whenever the room can take both. The seating
            # goes first; the dining table is then pushed to the wall AWAY from
            # the sofa (never in front of it) and tried SMALL first, so the walk
            # between the two zones survives.
            sofa = _living(plan, room, clear, bad, taken, out, notes)
            # a hall doubles as the dining ONLY when the house has no dining
            # room of its own — two dining sets in one home is the 'mess' look
            has_dining_room = any("dining" in (r.name or "").lower()
                                  for r in plan.rooms if r is not room)
            if is_dining or (area >= 130 and not has_dining_room):
                anchor, prefer_walls = None, None
                if sofa and sofa.facing in SIDES:
                    bx0, by0, bx1, by1 = clear.bounds
                    cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
                    far = 0.28
                    anchor = {
                        "W": (bx1 - (bx1 - bx0) * far, cy),
                        "E": (bx0 + (bx1 - bx0) * far, cy),
                        "N": (cx, by0 + (by1 - by0) * far),
                        "S": (cx, by1 - (by1 - by0) * far),
                    }[sofa.facing]
                    opp = {"N": "S", "S": "N", "E": "W", "W": "E"}[sofa.facing]
                    prefer_walls = [opp] + [s for s in SIDES
                                            if s not in (opp, sofa.facing)]
                # a hall dines compact — a 4-seat, or a folding 2-seat where the
                # room is tight; a room that is explicitly a DINING room seats six
                sizes = ("dining_6", "dining_4") if is_dining else \
                    ("dining_4", "dining_2")
                _dining(plan, room, clear, bad, taken, out, notes, anchor=anchor,
                        sizes=sizes, prefer_walls=prefer_walls)
        elif is_dining:
            _dining(plan, room, clear, bad, taken, out, notes)
        elif "bed" in n:
            master = ("master" in n) or (not master_done and area >= 140)
            master_done = master_done or master
            _bedroom(plan, room, clear, bad, taken, out, notes, master)
        else:
            for kind in kit:
                p = place_piece(plan, room, kind, clear, bad, taken)
                if p:
                    out.append(p)
                    taken.append(box(p.x, p.y, p.x + p.w, p.y + p.h))

        # thin the room to keep a real walking movement
        _circulation(plan, room, clear, out, notes)

    # tag in reading order so the schedule follows the sheet
    out.sort(key=lambda f: (-round(f.y, 1), round(f.x, 1)))
    for i, f in enumerate(out, start=1):
        f.tag = f"F{i}"

    notes.append("Furniture sizes are indicative — confirm actual pieces "
                 "before ordering.")

    res = dict(plan_dict)
    # carry the auto-fixed openings back too, so what was laid out against is
    # what gets saved
    res["openings"] = [asdict(o) for o in plan.openings]
    res["furniture"] = [asdict(f) for f in out]
    return res, notes
