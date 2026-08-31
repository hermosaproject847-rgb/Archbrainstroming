"""Flooring layout — build the per-room specs, and draw the tile grid.

`design()` gives every floored room a default FloorSpec (material, size,
spacer, skirting, drop) which the user then edits room by room. `draw()`
regenerates the tile grid, the spacer joints, the start-point hatch, the
skirting run and the level box for each room from its spec — so any edit
redraws that room and the quantities re-total.
"""

from __future__ import annotations

import math

from shapely.ops import unary_union
from shapely.geometry import box, Point

from . import engine
from . import electrical as E          # reuse its room classifier
from . import flooring as F
from .draw import DrawList, CHAR_W
from .model import Plan, FloorSpec

FT_MM = 304.8


def _footprint(plan: Plan):
    """The building outline the floor lives inside."""
    plot = getattr(plan, "plot", None)
    if plot is not None and getattr(plot, "w", 0) and getattr(plot, "h", 0):
        return box(plot.x, plot.y, plot.x + plot.w, plot.y + plot.h)
    xs, ys = [], []
    for r in plan.rooms:
        xs += [r.x, r.x + r.w]
        ys += [r.y, r.y + r.h]
    if not xs:
        return box(0, 0, 1, 1)
    return box(min(xs), min(ys), max(xs), max(ys))


def _clear(plan: Plan, room):
    """The room's TRUE floor: the connected area inside the real walls that
    holds the room's centre — so an L-shape or a notch is tiled to its actual
    shape, not just the labelled rectangle. Door thresholds are added so the
    floor runs to the wall centre-line at every door, and steps are cut out."""
    solid = engine.wall_solid(plan)          # doors NOT punched → rooms stay apart
    interior = _footprint(plan)
    if not solid.is_empty:
        interior = interior.difference(solid)
    pieces = (list(interior.geoms)
              if interior.geom_type == "MultiPolygon" else [interior])
    cx, cy = room.x + room.w / 2, room.y + room.h / 2
    pt = Point(cx, cy)
    piece = next((g for g in pieces if g.contains(pt)), None)
    if piece is None and pieces:                 # centre landed on a wall/notch
        rb = box(room.x, room.y, room.x + room.w, room.y + room.h)
        piece = max(pieces, key=lambda g: g.intersection(rb).area)
    if piece is None:
        return interior
    # NOTE: the floor STOPS at the wall face on each side of a doorway — it is no
    # longer extended into the door threshold. Extending it made BOTH adjacent
    # rooms tile the same doorway (a doubled hatch) and pushed the skirting out
    # into the opening. Tiles meeting the door line reads correctly.
    # steps carry their own finish — cut them out so tiles start AFTER the step
    for st in getattr(plan, "steps", []):
        try:
            piece = piece.difference(box(st.x, st.y, st.x + st.w, st.y + st.h))
        except Exception:
            pass
    if piece.geom_type == "MultiPolygon":
        piece = max(piece.geoms, key=lambda g: g.distance(pt) if not g.contains(pt) else -1) \
            if not any(g.contains(pt) for g in piece.geoms) \
            else next(g for g in piece.geoms if g.contains(pt))
    return piece


def _cat(room) -> str:
    return E.classify(room.name)


# --------------------------------------------------------------- the run
def design(plan_dict: dict) -> tuple[dict, list[str]]:
    """Give every room a default flooring spec (SECTION 7). The table then
    lets the user change material, size, spacer, start, skirting and drop."""
    from dataclasses import asdict

    plan = Plan.from_dict(plan_dict)
    notes: list[str] = []

    floorable = [r for r in plan.rooms if not r.void and not r.is_lawn
                 and "stair" not in r.name.lower()      # counted as treads/risers
                 and not _clear(plan, r).is_empty
                 and _clear(plan, r).area >= 4]
    floorable.sort(key=lambda r: (-round(r.y + r.h, 1), round(r.x, 1)))

    # rooms that open into one another (no partition) share ONE flooring —
    # same material, tile and code — so the floor reads as one continuous area.
    regions = _room_regions(plan, floorable)

    specs: list[FloorSpec] = []
    codes: dict = {}
    for region in regions:
        rep = max(region, key=lambda r: r.w * r.h)      # the region's spec-setter
        d = F.default_spec(_cat(rep))
        pref = F.MATERIALS[d["material"]]["code"]
        codes[pref] = codes.get(pref, 0) + 1
        code = f"{pref}-{codes[pref]:02d}"
        for room in region:
            cx, cy = room.x + room.w / 2, room.y + room.h / 2
            specs.append(FloorSpec(room=room.name, rx=cx, ry=cy, code=code,
                                   **d, start="symmetry"))
    # keep the drawing order sensible (top-left first)
    specs.sort(key=lambda s: (-round(s.ry, 1), round(s.rx, 1)))

    res = dict(plan_dict)
    res["flooring"] = [asdict(s) for s in specs]
    notes.append(f"Flooring set for {len(specs)} rooms — edit material, size, "
                 "spacer, start point, skirting and drop room by room in the "
                 "table.")
    notes.extend(_report(plan, specs))
    return res, notes


def _report(plan: Plan, specs) -> list[str]:
    """The setting-out line for each room (SECTION 15 item 3)."""
    out = []
    for s in specs:
        room = _room_at(plan, s.rx, s.ry)
        if room is None:
            continue
        clear = _clear(plan, room)
        if clear.is_empty:
            continue
        x0, y0, x1, y1 = clear.bounds
        ax = F.cut_pieces(x1 - x0, s.tile_w, s.spacer_mm)
        ay = F.cut_pieces(y1 - y0, s.tile_h, s.spacer_mm)
        out.append(f"{s.room}: {F.MATERIALS[s.material]['label']} "
                   f"{s.tile_w:g}x{s.tile_h:g}, {s.spacer_mm:g} mm joint — "
                   f"{ax['full']} full + {ax['cut_mm']:.0f} cut each end (x), "
                   f"{ay['full']} full + {ay['cut_mm']:.0f} cut each end (y); "
                   f"start {s.start}.")
    return out


def _room_at(plan: Plan, x: float, y: float):
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


# ------------------------------------------------------------- drawing
def _entry_point(plan: Plan, room):
    """Midpoint of the door / gate that opens into `room`, and which way its
    wall runs. Returns (px, py, along) where along = 'x' (door on a top/bottom
    wall) or 'y' (door on a left/right wall), or None if the room has no door.
    'Start from entry' begins the tiling here, so the cut tiles fall away from
    the doorway a fitter actually walks in through."""
    door_types = ("gate", "open", "door", "single_door", "double_door",
                  "sliding_door")
    cx, cy = room.x + room.w / 2.0, room.y + room.h / 2.0
    best, bd = None, 1e18
    for o in getattr(plan, "openings", []):
        if not (getattr(o, "is_door", False) or o.type in door_types):
            continue
        w = plan.wall(o.wall_id)
        if w is None:
            continue
        try:
            mx, my = w.point_at(o.pos + o.width / 2.0)
        except Exception:
            continue
        # the door's midpoint must sit on THIS room's boundary band
        if not (room.x - 0.6 <= mx <= room.x + room.w + 0.6
                and room.y - 0.6 <= my <= room.y + room.h + 0.6):
            continue
        d = (mx - cx) ** 2 + (my - cy) ** 2
        if d < bd:
            along = "x" if abs(w.x2 - w.x1) >= abs(w.y2 - w.y1) else "y"
            best, bd = (mx, my, along), d
    return best


def _origin(x0, y0, x1, y1, s, ax, ay, entry=None):
    """Where the first joint line sits on each axis, from the start rule."""
    p = F.PERIM_JOINT_MM / FT_MM
    cx = ax["cut_mm"] / FT_MM
    cy = ay["cut_mm"] / FT_MM
    # symmetry / default: equal cut at both ends -> first full tile at p+cut
    ox = x0 + p + cx
    oy = y0 + p + cy
    rule = s.start or "symmetry"
    if rule == "corner-sw":
        ox, oy = x0 + p, y0 + p
    elif rule == "corner-se":
        ox, oy = x1 - p, y0 + p
    elif rule == "corner-nw":
        ox, oy = x0 + p, y1 - p
    elif rule == "corner-ne":
        ox, oy = x1 - p, y1 - p
    elif rule == "entry" and entry is not None:
        px, py, along = entry
        if along == "x":                 # door on a top / bottom wall
            ox = px                       # first full tile begins AT the doorway
            oy = (y0 + p) if abs(py - y0) <= abs(py - y1) else (y1 - p)
        else:                            # door on a left / right wall
            oy = py
            ox = (x0 + p) if abs(px - x0) <= abs(px - x1) else (x1 - p)
    return ox + s.start_dx, oy + s.start_dy


def draw(plan: Plan, dl: DrawList) -> None:
    """Draw the flooring for every room from its spec.

    Rooms that open into one another with NO partition wall between them (a
    bedroom flowing into a foyer, say) are tiled as ONE continuous floor: they
    share a single grid origin, so the joints line up straight across the open
    boundary instead of restarting in each room.
    """
    entries = []                                   # (spec, room, clear)
    for s in plan.flooring:
        if not getattr(s, "visible", True):
            continue
        room = _room_at(plan, s.rx, s.ry)
        if room is None:
            continue
        clear = _clear(plan, room)
        if clear.is_empty:
            continue
        entries.append((s, room, clear))

    groups = _regions(plan, entries)
    for grp in groups:
        # one shared origin for the whole region, from its combined extent
        gx0 = min(c.bounds[0] for _s, _r, c in grp)
        gy0 = min(c.bounds[1] for _s, _r, c in grp)
        gx1 = max(c.bounds[2] for _s, _r, c in grp)
        gy1 = max(c.bounds[3] for _s, _r, c in grp)
        rep = grp[0][0]                            # representative spec
        ax = F.cut_pieces(gx1 - gx0, rep.tile_w, rep.spacer_mm)
        ay = F.cut_pieces(gy1 - gy0, rep.tile_h, rep.spacer_mm)
        entry = _entry_point(plan, grp[0][1]) if (rep.start or "") == "entry" else None
        origin = _origin(gx0, gy0, gx1, gy1, rep, ax, ay, entry)
        if len(grp) > 1:
            # a CONTINUOUS region: one grid and one skirting run over the
            # union of the floors PLUS the open-archway reveals, so the joints
            # and the skirting line run THROUGH the opening — never broken
            # into per-room pieces that stop dead at the jamb
            from shapely.ops import unary_union
            reveals = [rv for rv in _open_reveals(plan)
                       if sum(1 for *_x, c in grp if rv.intersects(c)) >= 2]
            region = unary_union([c for *_x, c in grp] + reveals)
            area = region.buffer(-0.02)
            if area.is_empty:
                area = region
            Tx = max(rep.tile_w, 1.0) / FT_MM
            Ty = max(rep.tile_h, 1.0) / FT_MM
            Mx, My = Tx + rep.spacer_mm / FT_MM, Ty + rep.spacer_mm / FT_MM
            for loops in _area_loops(area):
                dl.hatch(loops, kind="vlines", step=Mx, layer="FLR-GRID",
                         phase=origin[0])
                dl.hatch(loops, kind="hlines", step=My, layer="FLR-GRID",
                         phase=origin[1])
            if rep.skirting_mm > 0:
                _skirting(dl, plan, region, cut_open=False)
            for i, (s, room, clear) in enumerate(grp):
                _draw_room(plan, room, clear, s, dl, origin=origin,
                           draw_start=(i == 0), draw_skirt=False,
                           draw_grid=False)
        else:
            s, room, clear = grp[0]
            _draw_room(plan, room, clear, s, dl, origin=origin,
                       draw_start=True, draw_skirt=(s.skirting_mm > 0))


def _union_find(n, connected):
    """Group 0..n-1 by a `connected(i, j)` predicate. Returns list of groups."""
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for i in range(n):
        for j in range(i + 1, n):
            if connected(i, j):
                parent[find(i)] = find(j)
    buckets: dict = {}
    for i in range(n):
        buckets.setdefault(find(i), []).append(i)
    return list(buckets.values())


def _room_regions(plan, rooms):
    """Groups of rooms that open into each other with no partition between."""
    groups = _union_find(len(rooms),
                         lambda i, j: _open_between(plan, rooms[i], rooms[j]))
    return [[rooms[i] for i in g] for g in groups]


def _regions(plan, entries):
    """Group entries whose rooms open into each other AND share a tile module
    (so the joints can actually line up) into one continuous grid."""
    def connected(i, j):
        si, ri, _ci = entries[i]
        sj, rj, _cj = entries[j]
        if (round(si.tile_w, 1), round(si.tile_h, 1), round(si.spacer_mm, 1)) \
           != (round(sj.tile_w, 1), round(sj.tile_h, 1), round(sj.spacer_mm, 1)):
            return False
        return _open_between(plan, ri, rj)

    groups = _union_find(len(entries), connected)
    return [[entries[i] for i in g] for g in groups]


def _open_between(plan, A, B) -> bool:
    """True if room boxes A and B meet (touch OR overlap) and NO wall runs
    along most of their shared boundary — i.e. they are open to each other."""
    face = _interface(A, B)
    if face is None:
        return False
    axis, coord, lo, hi = face
    span = hi - lo
    if span < 1.5:                         # only a sliver in common — ignore
        return False
    covered = 0.0
    for w in plan.walls:
        if axis == "v" and abs(w.x1 - w.x2) < 0.06 and abs(w.x1 - coord) < 0.6:
            covered += max(0.0, min(max(w.y1, w.y2), hi)
                           - max(min(w.y1, w.y2), lo))
        elif axis == "h" and abs(w.y1 - w.y2) < 0.06 and abs(w.y1 - coord) < 0.6:
            covered += max(0.0, min(max(w.x1, w.x2), hi)
                           - max(min(w.x1, w.x2), lo))
    # an OPEN opening (archway, no shutter) in a wall along the boundary is a
    # connection too — the floor runs straight through it, so subtract its span
    open_len = 0.0
    for o in plan.openings:
        if getattr(o, "type", "") != "open":
            continue
        w = plan.wall(o.wall_id)
        if w is None:
            continue
        try:
            a = w.point_at(o.pos)
            b = w.point_at(o.pos + o.width)
        except Exception:
            continue
        if axis == "v" and abs(a[0] - coord) < 0.6 and abs(b[0] - coord) < 0.6:
            open_len += max(0.0, min(max(a[1], b[1]), hi)
                            - max(min(a[1], b[1]), lo))
        elif axis == "h" and abs(a[1] - coord) < 0.6 and abs(b[1] - coord) < 0.6:
            open_len += max(0.0, min(max(a[0], b[0]), hi)
                            - max(min(a[0], b[0]), lo))
    covered = max(0.0, covered - open_len)
    # open when mostly unwalled, OR when a real archway (>= 3 ft) joins them
    return covered < 0.4 * span or open_len >= 3.0


def _interface(A, B):
    """Where two room boxes meet, whether they touch along an edge or overlap.

    Returns (axis, coord, lo, hi): the boundary runs along `axis` at `coord`,
    over the span [lo, hi] the two rooms share. None if the boxes are neither
    adjacent nor overlapping.
    """
    ax0, ay0, ax1, ay1 = A.x, A.y, A.x + A.w, A.y + A.h
    bx0, by0, bx1, by1 = B.x, B.y, B.x + B.w, B.y + B.h
    ox = min(ax1, bx1) - max(ax0, bx0)     # x overlap (negative = a gap)
    oy = min(ay1, by1) - max(ay0, by0)     # y overlap
    if ox < -0.5 or oy < -0.5:             # too far apart to be connected
        return None
    if ox >= oy:
        # rooms stacked in Y — the boundary is a horizontal line between them
        coord = (min(ay1, by1) + max(ay0, by0)) / 2
        return ("h", coord, max(ax0, bx0), min(ax1, bx1))
    # rooms side by side in X — the boundary is a vertical line between them
    coord = (min(ax1, bx1) + max(ax0, bx0)) / 2
    return ("v", coord, max(ay0, by0), min(ay1, by1))


def _open_reveals(plan):
    """The wall-thickness rectangles of the OPEN (archway) openings — the floor
    runs straight through these, so a continuous region includes them."""
    from shapely.geometry import LineString
    out = []
    for o in plan.openings:
        if getattr(o, "type", "") != "open":
            continue
        w = plan.wall(o.wall_id)
        if w is None:
            continue
        try:
            a = w.point_at(o.pos)
            b = w.point_at(o.pos + o.width)
        except Exception:
            continue
        half = (float(w.thickness_in or 4.5) / 12.0) / 2.0
        out.append(LineString([a, b]).buffer(half + 0.1, cap_style=2))
    return out


def _door_gaps(plan, cut_open=True):
    """A buffered shape covering every DOOR/gate/open opening — the skirting is
    cut wherever it would cross a doorway (skirting never runs across a door).
    With cut_open=False the archways are left alone (a continuous region's
    skirting WRAPS through them instead of stopping dead)."""
    from shapely.geometry import LineString
    from shapely.ops import unary_union
    spans = []
    for o in plan.openings:
        kinds = ("gate", "open") if cut_open else ("gate",)
        if not (getattr(o, "is_door", False) or o.type in kinds):
            continue                              # windows keep skirting (sill above)
        w = plan.wall(o.wall_id)
        if w is None:
            continue
        try:
            a = w.point_at(o.pos)
            b = w.point_at(o.pos + o.width)
        except Exception:
            continue
        # flat cap → the gap spans the door WIDTH only (not beyond), while the
        # 0.6 ft reach cuts through the wall thickness to the skirting line
        spans.append(LineString([a, b]).buffer(0.6, cap_style=2))
    return unary_union(spans) if spans else None


def _skirting(dl, plan, clear, cut_open=True) -> None:
    """Skirting round THIS room's floor (room-wise), BROKEN at every doorway."""
    inner = clear.buffer(-0.12)
    if inner.is_empty:
        return
    gaps = _door_gaps(plan, cut_open=cut_open)
    geoms = inner.geoms if inner.geom_type == "MultiPolygon" else [inner]
    for g in geoms:
        line = g.exterior
        if gaps is not None:
            line = line.difference(gaps)          # cut the door openings out
        parts = (line.geoms if getattr(line, "geom_type", "") == "MultiLineString"
                 else [line])
        for p in parts:
            if getattr(p, "geom_type", "") != "LineString":
                continue
            cs = [(round(x, 3), round(y, 3)) for x, y in p.coords]
            for a, b in zip(cs, cs[1:]):
                dl.line(a[0], a[1], b[0], b[1], layer="FLR-SKIRT")


def _draw_room(plan, room, clear, s, dl, origin=None, draw_start=True,
               draw_skirt=True, draw_grid=True) -> None:
    x0, y0, x1, y1 = clear.bounds
    Tx = max(s.tile_w, 1.0) / FT_MM
    Ty = max(s.tile_h, 1.0) / FT_MM
    jx = jy = s.spacer_mm / FT_MM
    Mx, My = Tx + jx, Ty + jy
    if origin is not None:
        ox, oy = origin                     # shared grid across the open region
    else:
        ax = F.cut_pieces(x1 - x0, s.tile_w, s.spacer_mm)
        ay = F.cut_pieces(y1 - y0, s.tile_h, s.spacer_mm)
        entry = _entry_point(plan, room) if (s.start or "") == "entry" else None
        ox, oy = _origin(x0, y0, x1, y1, s, ax, ay, entry)

    # every joint and hatch line is CLIPPED to the real floor polygon, so the
    # tiling follows the true room shape (L-shapes, notches and all) and never
    # runs over a wall or into a doorway. Kept a hair inside so lines never sit
    # exactly on the wall face.
    area = clear.buffer(-0.02)
    if area.is_empty:
        area = clear

    # NOTE: no full-room diagonal "material wash" hatch — at drawing scale its
    # fine lines merge into a solid grey block (worst in a CAD's dark view). The
    # real, readable flooring indication is the TILE-JOINT GRID below, drawn at
    # the actual tile module (e.g. 600 mm) so the tiles read one-by-one.

    # tile joints (spacer grid) as GROUPED hatch objects (one vertical + one
    # horizontal per floor polygon), never hundreds of loose lines
    if draw_grid:
        for loops in _area_loops(area):
            dl.hatch(loops, kind="vlines", step=Mx, layer="FLR-GRID",
                     phase=ox)
            dl.hatch(loops, kind="hlines", step=My, layer="FLR-GRID",
                     phase=oy)

    # the START POINT marker — anchored at the DOORWAY (you tile from where you
    # walk in). No door → the start corner from the rule. Always snapped to the
    # tile grid and kept fully inside the room, so it never floats mid-room.
    if draw_start:
        xs = _lines_from(ox, Mx, x0, x1)
        ys = _lines_from(oy, My, y0, y1)
        # the marker FOLLOWS the start rule: entry -> doorway, corner-* ->
        # that corner, symmetry -> the grid origin (first full tile). The old
        # code anchored to the doorway whenever a door existed, so changing
        # the start never moved the hatch.
        rule = s.start or "symmetry"
        ep = _entry_point(plan, room) if rule in ("entry", "symmetry") else None
        if rule == "entry" and ep is not None:
            ax, ay = ep[0], ep[1]
        elif rule.startswith("corner"):
            ax = (x1 - Tx) if rule in ("corner-se", "corner-ne") else x0
            ay = (y1 - Ty) if rule in ("corner-nw", "corner-ne") else y0
        elif ep is not None:                 # symmetry with a door: walk-in tile
            ax, ay = ep[0], ep[1]
        else:
            ax, ay = ox, oy
        # the marker must sit ON the drawn grid: mark the ACTUAL CELL of the
        # lattice (between joint lines / room edges — a cut tile in a room
        # smaller than the module) nearest the anchor and inside the floor —
        # never a nominal full-size rect straddling the lines
        from shapely.geometry import box as _box
        bx = sorted(set([round(x0, 4), round(x1, 4)]
                        + [v for v in xs if x0 - 1e-6 <= v <= x1 + 1e-6]))
        by = sorted(set([round(y0, 4), round(y1, 4)]
                        + [v for v in ys if y0 - 1e-6 <= v <= y1 + 1e-6]))
        cells_x = [(a, b) for a, b in zip(bx, bx[1:]) if b - a > 0.25]
        cells_y = [(a, b) for a, b in zip(by, by[1:]) if b - a > 0.25]
        pairs = sorted(((cx2, cy2) for cx2 in cells_x for cy2 in cells_y),
                       key=lambda p: ((p[0][0] + p[0][1]) / 2 - ax) ** 2
                                     + ((p[1][0] + p[1][1]) / 2 - ay) ** 2)
        ok = clear.buffer(0.05)
        best = next(((cx2, cy2) for cx2, cy2 in pairs
                     if ok.contains(_box(cx2[0], cy2[0], cx2[1], cy2[1]))),
                    pairs[0] if pairs else None)
        if best is not None:
            (sx, ex), (sy, ey) = best
            _start_tile(dl, sx, sy, ex, ey)

    # skirting run round the room's own floor (skip 0 = dado; a merged region
    # draws its skirting once, round the whole outline, instead)
    if draw_skirt and s.skirting_mm > 0:
        _skirting(dl, plan, clear)

    # the room's flooring label, on a clean white panel so no line runs through
    _label(dl, room, clear, s)


def _clip_line(dl, area, x1, y1, x2, y2, layer) -> None:
    """Draw a line only where it lies inside the floor polygon."""
    from shapely.geometry import LineString
    inter = LineString([(x1, y1), (x2, y2)]).intersection(area)
    if inter.is_empty:
        return
    parts = inter.geoms if inter.geom_type == "MultiLineString" else [inter]
    for p in parts:
        if getattr(p, "geom_type", "") != "LineString":
            continue
        cs = list(p.coords)
        for a, b in zip(cs, cs[1:]):
            dl.line(a[0], a[1], b[0], b[1], layer=layer)


def _lines_from(o, M, lo, hi):
    """Joint positions from origin o, spacing M, within [lo, hi]."""
    out = []
    k = 0
    while o - k * M >= lo - 1e-6:
        out.append(o - k * M)
        k += 1
    k = 1
    while o + k * M <= hi + 1e-6:
        out.append(o + k * M)
        k += 1
    return sorted(set(round(v, 4) for v in out))


def _area_loops(area):
    """[exterior, *holes] coordinate loops for each Polygon in `area` — the
    boundary(ies) a grouped HATCH object is built on."""
    geoms = area.geoms if getattr(area, "geom_type", "") == "MultiPolygon" \
        else [area]
    out = []
    for g in geoms:
        if g is None or g.is_empty or getattr(g, "geom_type", "") != "Polygon":
            continue
        loops = [[(round(x, 4), round(y, 4))
                  for x, y in list(g.exterior.coords)[:-1]]]
        for ring in g.interiors:
            loops.append([(round(x, 4), round(y, 4))
                          for x, y in list(ring.coords)[:-1]])
        if len(loops[0]) >= 3:
            out.append(loops)
    return out


def _hatch(dl, area, x0, y0, x1, y1, s):
    """A light material hatch as ONE grouped HATCH object per floor polygon
    (never loose lines): wood as horizontal planks, the rest at 45°."""
    step = {"tile": 1.6, "marble": 2.6, "wood": 1.0, "granite": 2.0}.get(
        s.material, 1.6)
    kind = "hlines" if s.material == "wood" else "diag45"
    for loops in _area_loops(area):
        dl.hatch(loops, kind=kind, step=step, layer="FLR-HATCH")


def _start_tile(dl, x0, y0, x1, y1):
    """A clean START marker on the first full tile: just the tile outline and a
    small corner tick — no fill, so it reads as a marker, not a solid block."""
    dl.rect(x0, y0, x1 - x0, y1 - y0, layer="FLR-START")
    # one short diagonal in the corner nearest the start, as the 'begin here' tick
    d = min(x1 - x0, y1 - y0) * 0.5
    dl.line(x0, y0, x0 + d, y0 + d, layer="FLR-START")


def _label(dl, room, clear, s):
    x0, y0, x1, y1 = clear.bounds
    cx = (x0 + x1) / 2
    cy = y0 + 0.95
    mat = F.MATERIALS[s.material]["label"]
    lvl = "FFL +/-0.000" if abs(s.drop_mm) < 1e-6 else f"FFL {s.drop_mm:+.0f}"
    sk = f"SK {s.skirting_mm:g}" if s.skirting_mm > 0 else "dado"
    line1 = f"{s.code}  {mat} {s.tile_w:g}x{s.tile_h:g}"
    line2 = f"{lvl}  ·  joint {s.spacer_mm:g}  ·  {sk}"
    # one white panel behind BOTH lines, so the grid never runs through the text
    w = max(len(line1) * 0.28, len(line2) * 0.24) * CHAR_W + 0.3
    top, bot = cy + 0.28, cy - 0.42 - 0.24
    dl.fill_rect(cx - w / 2, bot - 0.06, w, (top - bot) + 0.12,
                 color="#ffffff", layer="FLR-TEXT")
    dl.text(cx, cy, line1, h=0.28, layer="FLR-TEXT")
    dl.text(cx, cy - 0.42, line2, h=0.24, layer="FLR-LEVEL")
