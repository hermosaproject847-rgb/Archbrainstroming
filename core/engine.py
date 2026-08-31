"""Geometry engine: Plan -> DrawList.

Method (STEP 2/3 of the master prompt):
  1. every wall is a thin rectangle about its centre-line, extended half a
     thickness at each end so junctions close cleanly;
  2. union them  ->  one wall solid;
  3. subtract the opening rectangles  ->  openings are punched by construction;
  4. draw the boundary of the result  ->  hollow double-line walls, correct
     junctions, no overshoots, no wall across any door.
Open areas contribute no walls at all, so two adjacent open areas are one
continuous space with nothing between them.
"""

from __future__ import annotations

import math

from shapely.geometry import Polygon, MultiPolygon, box, Point
from shapely.ops import unary_union

from . import furniture as furn
from . import stairs
from .draw import Arc, DrawList
from .model import Plan, Wall, Opening, Stair, IN

EPS = 1e-6


# ---------------------------------------------------------------- helpers
def wall_rect(w: Wall, extend_ends: bool = True) -> Polygon:
    """Rectangle of a wall about its centre-line."""
    h = w.th / 2.0
    e = h if extend_ends else 0.0
    if w.horizontal:
        x1, x2 = sorted((w.x1, w.x2))
        return box(x1 - e, w.y1 - h, x2 + e, w.y1 + h)
    if abs(w.x2 - w.x1) < 1e-9:
        y1, y2 = sorted((w.y1, w.y2))
        return box(w.x1 - h, y1 - e, w.x1 + h, y2 + e)
    # skew wall -> buffer the segment
    from shapely.geometry import LineString
    return LineString([(w.x1, w.y1), (w.x2, w.y2)]).buffer(h, cap_style=2, join_style=2)


def opening_rect(w: Wall, o: Opening) -> Polygon:
    """Cut box for an opening: full wall depth (plus slop) x opening width."""
    h = w.th / 2.0 + 0.05
    p1 = w.point_at(o.pos)
    p2 = w.point_at(o.pos + o.width)
    if w.horizontal:
        x1, x2 = sorted((p1[0], p2[0]))
        return box(x1, w.y1 - h, x2, w.y1 + h)
    if abs(w.x2 - w.x1) < 1e-9:
        y1, y2 = sorted((p1[1], p2[1]))
        return box(w.x1 - h, y1, w.x1 + h, y2)
    from shapely.geometry import LineString
    return LineString([p1, p2]).buffer(h, cap_style=2, join_style=2)


def _polys(geom) -> list[Polygon]:
    if geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    return [g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon)]


def solid_walls(plan: Plan) -> list[Wall]:
    """The walls that are actually built. A railing is drawn but encloses
    nothing, so it must not take part in the wall solid or an opening would be
    punched through it and a verandah would read as an enclosed room."""
    return [w for w in plan.walls if not w.railing]


def wall_solid(plan: Plan):
    """Union of every wall rectangle (before openings are punched)."""
    rects = [wall_rect(w) for w in solid_walls(plan)]
    return unary_union(rects) if rects else Polygon()


def cut_solid(plan: Plan):
    """Wall solid with every opening punched out."""
    solid = wall_solid(plan)
    cuts = []
    for o in plan.openings:
        w = plan.wall(o.wall_id)
        if w is not None and not w.railing:
            cuts.append(opening_rect(w, o))
    if cuts:
        solid = solid.difference(unary_union(cuts))
    return solid


def room_clear(plan: Plan, room) -> Polygon:
    """A room's clear floor = its centre-line box minus every wall."""
    b = box(room.x, room.y, room.x + room.w, room.y + room.h)
    solid = wall_solid(plan)
    return b.difference(solid) if not solid.is_empty else b


# ---------------------------------------------------------------- drawing
def draw_walls(plan: Plan, dl: DrawList) -> None:
    """Hollow double-line walls: just stroke the boundary of the cut solid."""
    ext = {w.id for w in plan.walls if w.exterior}
    solid = cut_solid(plan)
    for poly in _polys(solid):
        # exterior ring slightly heavier, holes (courtyards) lighter
        dl.poly(list(poly.exterior.coords)[:-1], layer="WALL-EXT" if ext else "WALL-INT")
        for ring in poly.interiors:
            dl.poly(list(ring.coords)[:-1], layer="WALL-INT")

    # railings: a thin double line with posts, drawn on top of nothing
    for w in plan.walls:
        if not w.railing:
            continue
        L = w.length or 1e-9
        ux, uy = (w.x2 - w.x1) / L, (w.y2 - w.y1) / L
        nx, ny = -uy, ux
        g = 0.12                                   # rail spacing on the sheet
        for s in (-1, 1):
            dl.line(w.x1 + nx * g * s, w.y1 + ny * g * s,
                    w.x2 + nx * g * s, w.y2 + ny * g * s, layer="RAILING")
        step = 1.5                                 # posts every 1'-6"
        n = max(1, int(L / step))
        for i in range(n + 1):
            t = min(L, i * step)
            px, py = w.x1 + ux * t, w.y1 + uy * t
            dl.line(px + nx * g, py + ny * g, px - nx * g, py - ny * g,
                    layer="RAILING")
        # named on the drawing, as the sketch names it
        mx, my = (w.x1 + w.x2) / 2, (w.y1 + w.y2) / 2
        ang = 0 if abs(ux) >= abs(uy) else 90
        dl.text(mx - nx * 0.75, my - ny * 0.75, "RAILING", h=0.4,
                layer="TEXT-SUB", angle=ang)

    # jambs: close each opening's cut with two short lines across the wall depth
    for o in plan.openings:
        w = plan.wall(o.wall_id)
        if w is None or w.railing or o.type in ("gate", "open"):
            continue
        h = w.th / 2.0
        for d in (o.pos, o.pos + o.width):
            px, py = w.point_at(d)
            if w.horizontal:
                dl.line(px, py - h, px, py + h, layer="OPENING")
            else:
                dl.line(px - h, py, px + h, py, layer="OPENING")


def draw_sections(plan: Plan, dl: DrawList) -> None:
    """The section cut lines on the plan — a dashed line with the mark (A-A)
    and an ARROW at each end pointing the way the section is viewed. The arrow
    follows the section's own direction (flippable), so the plan and the cut
    always agree on which way you are looking."""
    from . import section as SEC
    for s in getattr(plan, "sections", []):
        dl.line(s.x1, s.y1, s.x2, s.y2, layer="SEC-LINE", dashed=True)
        L = math.hypot(s.x2 - s.x1, s.y2 - s.y1) or 1e-9
        ux, uy = (s.x2 - s.x1) / L, (s.y2 - s.y1) / L
        nx, ny = SEC.view_dir(plan, s)                 # true view direction
        alen = 1.9
        for (ex, ey, sgn) in ((s.x1, s.y1, 1), (s.x2, s.y2, -1)):
            tx, ty = ex + nx * alen, ey + ny * alen
            dl.line(ex, ey, tx, ty, layer="SEC-LINE")          # arrow stem
            # arrowhead
            bx, by = tx - nx * 0.5, ty - ny * 0.5
            px, py = -ny * 0.22, nx * 0.22
            dl.line(bx + px, by + py, tx, ty, layer="SEC-LINE")
            dl.line(bx - px, by - py, tx, ty, layer="SEC-LINE")
            # tag at the end, set back opposite the arrow so they don't clash
            dl.text(ex - nx * 0.9 - ux * 0.3 * sgn,
                    ey - ny * 0.9 - uy * 0.3 * sgn,
                    s.tag, h=0.7, layer="SEC-LINE", bold=True)


def draw_beams(plan: Plan, dl: DrawList, prefix: str = "", inch: bool = False,
               tags: bool = True) -> None:
    """Beams over the walls, drawn as ONE joined outline (like the wall network)
    so corners and T-junctions meet cleanly instead of each beam ending in a
    box. A dashed centre-line and the number + size sit on each beam.

    prefix / inch let a framing plan tag them like the reference — e.g. prefix
    'PB' with inch sizes gives  PB-1 (9"X9"); the default keeps the mm labels."""
    beams = [b for b in (getattr(plan, "beams", None) or [])
             if math.hypot(b.x2 - b.x1, b.y2 - b.y1) > 1e-6]
    if not beams:
        return
    try:
        from shapely.geometry import LineString
        from shapely.ops import unary_union
        parts = []
        for b in beams:
            L = math.hypot(b.x2 - b.x1, b.y2 - b.y1) or 1e-9
            ux, uy = (b.x2 - b.x1) / L, (b.y2 - b.y1) / L
            hw = (b.width_mm / 304.8) / 2.0
            # extend each beam by half its width at BOTH ends so that at a
            # corner / T-junction the rectangles overlap and the joint fills in
            # smoothly instead of leaving an L-shaped notch
            ax, ay = b.x1 - ux * hw, b.y1 - uy * hw
            bx, by = b.x2 + ux * hw, b.y2 + uy * hw
            parts.append(LineString([(ax, ay), (bx, by)]).buffer(
                hw, cap_style=2, join_style=2))
        u = unary_union(parts)
        # a light close only removes hairline nicks — it must stay SMALL so an
        # intentional flush offset of a beam (~0.19 ft on a 4.5" wall) is not
        # healed away and still shows
        u = u.buffer(0.03, join_style=2).buffer(-0.03, join_style=2)
        geoms = list(u.geoms) if hasattr(u, "geoms") else [u]
        for g in geoms:
            if getattr(g, "geom_type", "") != "Polygon":
                continue
            _ring(dl, list(g.exterior.coords), "BEAM")
            for r in g.interiors:
                _ring(dl, list(r.coords), "BEAM")
    except Exception:
        for b in beams:                                    # fallback: plain edges
            L = math.hypot(b.x2 - b.x1, b.y2 - b.y1) or 1e-9
            nx, ny = -(b.y2 - b.y1) / L, (b.x2 - b.x1) / L
            hw = (b.width_mm / 304.8) / 2.0
            for s in (1, -1):
                dl.line(b.x1 + nx * hw * s, b.y1 + ny * hw * s,
                        b.x2 + nx * hw * s, b.y2 + ny * hw * s, layer="BEAM")
    # centre-lines and the number / size label, with collision avoidance so
    # labels at T-junctions / corners never print on top of each other
    placed = []                       # (cx, cy, half_w, half_h) axis-aligned

    def _clear(cx, cy, hwid, hht):
        for px, py, pw, ph in placed:
            if abs(cx - px) < (hwid + pw) and abs(cy - py) < (hht + ph):
                return False
        return True

    h = 0.32
    for i, b in enumerate(beams, start=1):
        L = math.hypot(b.x2 - b.x1, b.y2 - b.y1) or 1e-9
        ux, uy = (b.x2 - b.x1) / L, (b.y2 - b.y1) / L
        nx, ny = -uy, ux
        hw = (b.width_mm / 304.8) / 2.0
        dl.line(b.x1, b.y1, b.x2, b.y2, layer="BEAM-CL", dashed=True)
        if not tags:
            continue
        mx, my = (b.x1 + b.x2) / 2, (b.y1 + b.y2) / 2
        ang = math.degrees(math.atan2(uy, ux))
        if ang > 90 or ang < -90:
            ang += 180
        if inch:
            tag = f"{prefix}-{b.tag.lstrip('B') or i}" if prefix else b.tag
            label = f'{tag} ({round(b.width_mm / 25.4)}"X{round(b.depth_mm / 25.4)}")'
        else:
            label = f"{b.tag}  {round(b.width_mm)}x{round(b.depth_mm)}"
        vertical = abs(uy) > abs(ux)               # text runs up the sheet
        tw = len(label) * h * 0.6                  # rough text length
        hwid, hht = (h * 0.7, tw / 2) if vertical else (tw / 2, h * 0.7)
        off = hw + 0.35
        # candidate anchors: default side, flipped side, then nudged along beam
        cands = []
        for side in (1, -1):
            for slide in (0.0, 0.30 * L, -0.30 * L, 0.45 * L, -0.45 * L):
                ax = mx + ux * slide - ny * off * side
                ay = my + uy * slide + nx * off * side
                cands.append((ax, ay))
        ax, ay = cands[0]
        for cx, cy in cands:
            if _clear(cx, cy, hwid, hht):
                ax, ay = cx, cy
                break
        placed.append((ax, ay, hwid, hht))
        dl.text(ax, ay, label, h=h, layer="BEAM-TAG", angle=ang)


def _ring(dl: DrawList, coords, layer: str) -> None:
    for a, b in zip(coords, coords[1:]):
        dl.line(a[0], a[1], b[0], b[1], layer=layer)


def draw_lawn(plan: Plan, dl: DrawList) -> None:
    """A lawn / garden is soft landscape — fill it with a grass hatch and
    NOTHING else. It is open (no floor tiles, no ceiling, no electrical)."""
    for r in plan.rooms:
        if not r.is_lawn:
            continue
        clear = room_clear(plan, r)
        if clear.is_empty:
            x0, y0, x1, y1 = r.x, r.y, r.x + r.w, r.y + r.h
            polys = [None]
        else:
            polys = _polys(clear)
        step = 1.15
        for poly in polys:
            bx0, by0, bx1, by1 = (clear.bounds if poly is not None
                                  else (r.x, r.y, r.x + r.w, r.y + r.h))
            j = 0
            y = by0 + 0.5
            while y < by1 - 0.2:
                x = bx0 + 0.5 + (0.55 if j % 2 else 0.0)
                while x < bx1 - 0.2:
                    if poly is None or poly.contains(Point(x, y)):
                        _grass_tuft(dl, x, y)
                    x += step
                y += step * 0.85
                j += 1


def _grass_tuft(dl: DrawList, x: float, y: float, s: float = 0.32) -> None:
    dl.line(x, y, x - 0.4 * s, y + s, layer="GRASS")
    dl.line(x, y, x, y + 1.25 * s, layer="GRASS")
    dl.line(x, y, x + 0.4 * s, y + s, layer="GRASS")


def draw_columns(plan: Plan, dl: DrawList) -> None:
    """Structural columns, drawn solid the way they read on the sketch — a
    filled square, rectangle or circle at the column's centre, hatched so it
    stands out from the walls, with its C-number beside it."""
    import math as _m
    for c in getattr(plan, "columns", []):
        shape = (getattr(c, "shape", "square") or "square").lower()
        if shape.startswith("round") or shape in ("circle", "circular"):
            r = max(c.w, 0.2) / 2.0
            pts = [(c.x + r * _m.cos(t), c.y + r * _m.sin(t))
                   for t in [i * _m.pi / 16 for i in range(32)]]
            dl.fill(pts, color="#3a3a3a", layer="COLUMN")
            dl.poly(pts, layer="COLUMN", closed=True)
            rad = r
        else:
            w = max(c.w, 0.2)
            h = max(c.h if shape.startswith("rect") else c.w, 0.2)
            x0, y0 = c.x - w / 2, c.y - h / 2
            dl.fill_rect(x0, y0, w, h, color="#3a3a3a", layer="COLUMN")
            dl.rect(x0, y0, w, h, layer="COLUMN")
            # the two diagonals that mark a column on a structural plan
            dl.line(x0, y0, x0 + w, y0 + h, layer="COLUMN")
            dl.line(x0, y0 + h, x0 + w, y0, layer="COLUMN")
            rad = max(w, h) / 2
        if c.tag:
            dl.text(c.x + rad + 0.25, c.y + rad + 0.15, c.tag, h=0.28,
                    layer="COLUMNTAG", halign="left")


def draw_wall_tags(plan: Plan, dl: DrawList) -> None:
    """The wall's number, on the wall. Without it the table and the drawing
    cannot be talked about together — you can see that a wall is wrong but not
    which row to edit."""
    for w in plan.walls:
        if w.length < 1.2:                     # too short to letter
            continue
        num = "".join(ch for ch in w.id if ch.isdigit())
        if not num:
            continue
        cx, cy = w.point_at(w.length / 2)
        r = 0.42
        dl.items.append(Arc(cx, cy, r, 0, 360, "WALLTAG"))
        dl.text(cx, cy, num, h=0.42, layer="WALLTAG")


def draw_windows(plan: Plan, dl: DrawList) -> None:
    for o in plan.openings:
        w = plan.wall(o.wall_id)
        if w is None or o.type not in ("window", "vent"):
            continue
        h = w.th / 2.0
        a = w.point_at(o.pos)
        b = w.point_at(o.pos + o.width)
        if w.horizontal:
            for dy in (-h, -h / 3, h / 3, h):
                dl.line(a[0], w.y1 + dy, b[0], w.y1 + dy, layer="WINDOW")
        else:
            for dx in (-h, -h / 3, h / 3, h):
                dl.line(w.x1 + dx, a[1], w.x1 + dx, b[1], layer="WINDOW")
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        off = h + 0.55
        tag = o.tag or ("V" if o.type == "vent" else "W")
        if w.horizontal:
            dl.text(mid[0], w.y1 + off, tag, h=0.42, layer="TEXT-SUB")
        else:
            dl.text(w.x1 + off, mid[1], tag, h=0.42, layer="TEXT-SUB", angle=90)


def _door_frame(plan: Plan, o: Opening):
    """Return (hinge_pt, leaf_dir_unit, swing_normal_unit, width).

    `side` is measured against the WALL's own start→end direction, so it means
    the same thing whichever jamb the door is hinged at. Deriving it from the
    hinge instead would silently invert the swing every time the hinge moved.
    """
    w = plan.wall(o.wall_id)
    a = w.point_at(o.pos)
    b = w.point_at(o.pos + o.width)
    hinge = a if (o.swing and o.swing.hinge == "start") else b
    other = b if hinge is a else a
    L = o.width or 1e-9
    u = ((other[0] - hinge[0]) / L, (other[1] - hinge[1]) / L)   # jamb to jamb
    WL = w.length or 1e-9
    wx, wy = (w.x2 - w.x1) / WL, (w.y2 - w.y1) / WL              # wall direction
    n = (-wy, wx)                                                # its left normal
    if o.swing and o.swing.side == "right":
        n = (wy, -wx)
    return hinge, u, n, o.width


def draw_doors(plan: Plan, dl: DrawList) -> None:
    for o in plan.openings:
        w = plan.wall(o.wall_id)
        if w is None or not (o.is_door or o.type == "gate"):
            continue
        if o.type == "gate":                      # gate: two leaf ticks, no arc
            a = w.point_at(o.pos); b = w.point_at(o.pos + o.width)
            dl.line(a[0], a[1], b[0], b[1], layer="DOOR", dashed=True)
            mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            dl.text(mid[0], mid[1] + 0.8, o.tag or "GATE", h=0.45, layer="TEXT-SUB")
            continue

        hinge, u, n, wd = _door_frame(plan, o)

        if o.is_sliding:
            _draw_sliding(dl, plan, o)
        elif o.leaf_count >= 2:
            # Double door: each leaf is half the opening, hinged at its own
            # jamb, both swinging the same way — the two arcs meet at the
            # centre line of the opening.
            far = (hinge[0] + u[0] * wd, hinge[1] + u[1] * wd)
            half = wd / 2.0
            for pivot, along in ((hinge, u), (far, (-u[0], -u[1]))):
                _leaf(dl, pivot, along, n, half)
        else:
            _leaf(dl, hinge, u, n, wd)

        if o.tag:
            lx = hinge[0] + (u[0] * wd * 0.5) - n[0] * 0.6
            ly = hinge[1] + (u[1] * wd * 0.5) - n[1] * 0.6
            dl.text(lx, ly, o.tag, h=0.42, layer="TEXT-SUB")


LEAF_MM = 40.0          # a door panel is ~40 mm thick


def _leaf(dl: DrawList, pivot, along, normal, width: float) -> None:
    """One door leaf, open at 90°.

    The leaf is drawn as the PANEL it is — a narrow rectangle standing off the
    jamb — not a bare line, and the swing arc runs from the panel's outer face
    to the closed position. That is the standard symbol.
    """
    t = LEAF_MM / 304.8                        # panel thickness in feet
    tip = (pivot[0] + normal[0] * width, pivot[1] + normal[1] * width)

    # the panel: a thin rectangle from the jamb outwards, its thickness lying
    # along the wall
    ax, ay = along[0] * t, along[1] * t
    dl.poly([pivot, (pivot[0] + ax, pivot[1] + ay),
             (tip[0] + ax, tip[1] + ay), tip], layer="DOOR", closed=True)

    a1 = math.degrees(math.atan2(along[1], along[0]))
    a2 = math.degrees(math.atan2(normal[1], normal[0]))
    if (a2 - a1) % 360 > 180:                  # sweep the short way, 90°
        a1, a2 = a2, a1
    dl.arc(pivot[0], pivot[1], width, a1, a2, layer="DOOR")


def _draw_sliding(dl: DrawList, plan: Plan, o: Opening) -> None:
    """A sliding leaf: the panel drawn in the opening, offset to one side,
    with the track it runs on."""
    w = plan.wall(o.wall_id)
    a = w.point_at(o.pos)
    b = w.point_at(o.pos + o.width)
    L = w.length or 1e-9
    ux, uy = (w.x2 - w.x1) / L, (w.y2 - w.y1) / L
    nx, ny = -uy, ux
    if o.swing and o.swing.side == "right":
        nx, ny = uy, -ux
    off = w.th / 2 + 0.12
    dl.line(a[0] + nx * off, a[1] + ny * off,
            b[0] + nx * off, b[1] + ny * off, layer="DOOR")          # panel
    dl.line(a[0], a[1], b[0], b[1], layer="DOOR", dashed=True)       # track


def draw_stairs(plan: Plan, dl: DrawList) -> None:
    """Straight / L / U stairs, with the landing, winders, well and UP-DN
    arrows all derived from the typology by core.stairs."""
    for s in plan.stairs:
        g = stairs.build(s)

        # a three-flight stair has two landings; the others have one
        # the office sheets draw NO landing box when the turn is winders —
        # the diagonals and the well-line strip ARE the turn
        for (lx, ly, lw, lh) in ([] if g.get("winder_polys")
                                 else (g.get("landings")
                                 or ([g["landing"]] if g["landing"] else []))):
            dl.rect(lx, ly, lw, lh, layer="STAIR")
            if g.get("landings"):
                # name them: a landing is not a step, and its size is its own
                dl.text(lx + lw / 2, ly + lh / 2, "LANDING", h=0.34,
                        layer="TEXT-SUB",
                        angle=0 if lw >= lh else 90)

        for f in g["flights"]:
            fx, fy, fw, fh = f["rect"]
            dl.rect(fx, fy, fw, fh, layer="STAIR")
            n = max(2, int(f["steps"]))
            if f["axis"] == "x":
                step = fw / n
                for i in range(1, n):
                    dl.line(fx + i * step, fy, fx + i * step, fy + fh, layer="STAIR")
            else:
                step = fh / n
                for i in range(1, n):
                    dl.line(fx, fy + i * step, fx + fw, fy + i * step, layer="STAIR")
            _number_steps(dl, f)

        for (x1, y1, x2, y2) in g["winders"]:
            dl.line(x1, y1, x2, y2, layer="STAIR")

        if g["well"]:
            wx, wy, ww, wh = g["well"]
            dl.rect(wx, wy, ww, wh, layer="STAIR")
            dl.line(wx, wy, wx + ww, wy + wh, layer="STAIR")   # the void's X
            dl.line(wx, wy + wh, wx + ww, wy, layer="STAIR")

        for a in g["arrows"]:
            dl.arrow(a["from"][0], a["from"][1], a["to"][0], a["to"][1])
            lx, ly = a["from"]
            dl.text(lx, ly + 0.55, a["label"], h=0.45, layer="TEXT-SUB")

        # only label the stair if no room already carries that name
        if s.label and plan.room(s.label) is None:
            dl.text(s.x + s.w / 2, s.y - 0.8, s.label, h=0.5, layer="TEXT-SUB")


def draw_steps(plan: Plan, dl: DrawList) -> None:
    """Entry steps: a run of treads with the sketch's level marks and an arrow
    up. Deliberately not the stair engine — these have no flights or landing."""
    for s in plan.steps:
        n = max(1, int(s.count or 1))
        along_x = s.run_axis == "x"
        dl.rect(s.x, s.y, s.w, s.h, layer="STAIR")

        # treads run square to the walk
        for i in range(1, n):
            t = i / n
            if along_x:
                x = s.x + s.w * t
                dl.line(x, s.y, x, s.y + s.h, layer="STAIR")
            else:
                y = s.y + s.h * t
                dl.line(s.x, y, s.x + s.w, y, layer="STAIR")

        # the level written on each tread, reading in the direction of ascent
        rising = s.up_from in ("left", "bottom")
        from . import units as _u          # level marks follow the unit too
        for i, lvl in enumerate(s.levels[:n]):
            lvl = _u.relabel(lvl)
            k = i if rising else (n - 1 - i)
            if along_x:
                cx, cy = s.x + s.w * (k + 0.5) / n, s.y + s.h / 2
                dl.text(cx, cy, lvl, h=0.34, layer="TEXT-SUB", angle=90)
            else:
                cx, cy = s.x + s.w / 2, s.y + s.h * (k + 0.5) / n
                dl.text(cx, cy, lvl, h=0.34, layer="TEXT-SUB")

        vec = {"left": (1, 0), "right": (-1, 0),
               "bottom": (0, 1), "top": (0, -1)}.get(s.up_from, (1, 0))
        cx, cy = s.x + s.w / 2, s.y + s.h / 2
        ax, ay = (s.w / 2 * 0.8, s.h / 2 * 0.8)
        dl.arrow(cx - vec[0] * ax, cy - vec[1] * ay,
                 cx + vec[0] * ax, cy + vec[1] * ay, head=0.3)
        if s.label:
            dl.text(cx, s.y - 0.6, s.label, h=0.4, layer="TEXT-SUB")


def _number_steps(dl: DrawList, f: dict) -> None:
    """Write the sketch's own step numbers at each end of a flight."""
    first = int(f.get("first") or 0)
    if first <= 0:
        return
    x, y, w, h = f["rect"]
    last = first + int(f["steps"]) - 1
    if f["axis"] == "x":
        lo, hi = (x + 0.35, y + h / 2), (x + w - 0.35, y + h / 2)
    else:
        lo, hi = (x + w / 2, y + 0.35), (x + w / 2, y + h - 0.35)
    a, b = (lo, hi) if f["dir"] > 0 else (hi, lo)
    dl.text(a[0], a[1], str(first), h=0.34, layer="TEXT-SUB")
    dl.text(b[0], b[1], str(last), h=0.34, layer="TEXT-SUB")


def draw_rooms(plan: Plan, dl: DrawList) -> None:
    for r in plan.rooms:
        cx, cy = r.centre
        # A stair that fills its own room would sit under that room's label, so
        # the label moves clear. Only when the stair really does fill the room:
        # a stair merely overlapping a corner of a large room must not push
        # that room's label off the plan.
        rb = box(r.x, r.y, r.x + r.w, r.y + r.h)
        covered = sum(rb.intersection(box(s.x, s.y, s.x + s.w,
                                          s.y + s.h)).area
                      for s in plan.stairs)
        if rb.area > 0 and covered / rb.area > 0.5:
            cy = r.y - 1.0
        # the user can drag the label off the centre (stored offset, feet)
        cx += getattr(r, "label_dx", 0.0) or 0.0
        cy += getattr(r, "label_dy", 0.0) or 0.0
        gap = 0.42 if r.size_label else 0.0
        dl.text(cx, cy + gap, r.name.upper(), h=0.62, layer="TEXT", bold=True)
        if r.size_label:
            from . import units
            # keep the recorded dimensions, just convert their unit (mm / m) so
            # the numbers stay correct instead of being recomputed from w × h
            dl.text(cx, cy - 0.55, units.relabel(r.size_label),
                    h=0.46, layer="TEXT-SUB")


def _fmt_ft(v: float) -> str:      # noqa: F811 — one formatter for the sheet
    from . import units           # feet-inch / mm / m per the chosen drawing unit
    return units.fmt_len(v)


def _fmt_dim(v: float) -> str:
    """Dimension text the way the civil layout writes it: under a foot it is
    inches only (9\", 4\"), otherwise feet-inches — short text crowds less.
    In mm / m mode EVERY figure follows the chosen unit — a drawing must
    never mix 356-mm chains with leftover 5\" fragments."""
    from . import units
    if units.current() != "ft":
        return units.fmt_len(v)
    if v < 1.0 - 1e-6:
        inch = v * 12.0
        whole = int(inch + 1e-6)
        frac = inch - whole
        if frac >= 0.75:
            whole += 1
            frac = 0.0
        half = "½" if 0.25 <= frac < 0.75 else ""
        return f"{whole}{half}\""
    return _fmt_ft(v)


def _slash(dl: DrawList, x: float, y: float, horiz: bool) -> None:
    """The architectural tick: a short 45-degree slash across the dim line."""
    s = 0.18
    dl.line(x - s, y - s, x + s, y + s, layer="DIM")


def _dim_chain(dl: DrawList, ticks: list[float], base: float, horiz: bool) -> None:
    """One dimension string, drawn the way the civil layout draws it: a thin
    line with a 45-degree slash tick at every station and the bay length over
    each bay. A bay too narrow for its text lifts the text clear of the line
    (staggered rows) so adjacent small figures never print over each other."""
    ticks = sorted(set(round(t, 4) for t in ticks))
    # a hairline bay reads as noise — merge it into its neighbour
    ticks = [t for i, t in enumerate(ticks) if i == 0 or t - ticks[i - 1] > 0.18]
    if len(ticks) < 2:
        return
    H = 0.40                                 # text height, feet
    if horiz:
        dl.line(ticks[0], base, ticks[-1], base, layer="DIM")
        for t in ticks:
            _slash(dl, t, base, True)
        row = 0
        for a, b in zip(ticks, ticks[1:]):
            txt = _fmt_dim(b - a)
            need = len(txt) * H * 0.62       # rough text width
            if b - a >= need:
                dl.text((a + b) / 2, base + 0.55, txt, h=H, layer="DIM")
                row = 0
            else:                            # narrow bay: lift the text clear,
                row += 1                     # alternating rows so pairs never touch
                ty = base + 0.55 + row * (H * 1.5)
                dl.text((a + b) / 2, ty, txt, h=H * 0.9, layer="DIM")
                dl.line((a + b) / 2, base + 0.18, (a + b) / 2, ty - 0.32, layer="DIM")
                if row >= 2:
                    row = 0
    else:
        dl.line(base, ticks[0], base, ticks[-1], layer="DIM")
        for t in ticks:
            _slash(dl, base, t, False)
        row = 0
        for a, b in zip(ticks, ticks[1:]):
            txt = _fmt_dim(b - a)
            need = len(txt) * H * 0.62
            if b - a >= need:
                dl.text(base - 0.55, (a + b) / 2, txt, h=H, layer="DIM", angle=90)
                row = 0
            else:
                row += 1
                tx = base - 0.55 - row * (H * 1.5)
                dl.text(tx, (a + b) / 2, txt, h=H * 0.9, layer="DIM", angle=90)
                dl.line(base - 0.18, (a + b) / 2, tx + 0.32, (a + b) / 2, layer="DIM")
                if row >= 2:
                    row = 0


def draw_dims(plan: Plan, dl: DrawList) -> None:
    x0, y0, x1, y1 = plan.extents()
    for chain in plan.dims:
        horiz = chain.axis in ("top", "bottom")
        if getattr(chain, "base", None) is not None:
            base = chain.base          # dimension line placed beside a wall
        elif chain.axis == "top":
            base = y1 + chain.at
        elif chain.axis == "bottom":
            base = y0 - chain.at
        elif chain.axis == "left":
            base = x0 - chain.at
        else:
            base = x1 + chain.at
        _dim_chain(dl, list(chain.ticks), base, horiz)


def draw_auto_dims(plan: Plan, dl: DrawList) -> None:
    """Automatic civil-layout dimensioning, done the way a working drawing is
    actually dimensioned: all COLLINEAR walls on one line share ONE continuous
    chain beside that line. The chain runs internal-face to internal-face and
    breaks ONLY at (a) column faces and (b) every door / window edge on any
    wall of the line. A crossing internal wall does NOT break the chain — the
    figure runs continuous wall-to-window across it (its thickness reads on its
    own line inside). Collinear walls are never split at their own joints."""
    OFF = 1.0
    x0, y0, x1, y1 = plan.extents()
    mx, my = (x0 + x1) / 2.0, (y0 + y1) / 2.0

    def half_ft(w):
        return (getattr(w, "thickness_in", 0) or 0) / 24.0   # half thickness, feet

    # ---- group the walls into straight LINES (same orientation + centre-line)
    lines: dict = {}
    for w in plan.walls:
        if getattr(w, "railing", False):
            continue
        horiz = abs(w.x2 - w.x1) >= abs(w.y2 - w.y1)
        cross = (w.y1 + w.y2) / 2.0 if horiz else (w.x1 + w.x2) / 2.0
        key = (horiz, round(cross * 4) / 4.0)     # collinear within 3"
        lines.setdefault(key, []).append(w)

    for (horiz, _), ws in lines.items():
        cross = sum(((w.y1 + w.y2) if horiz else (w.x1 + w.x2)) / 2.0
                    for w in ws) / len(ws)
        runs = [(min(a, b), max(a, b)) for a, b in
                (((w.x1, w.x2) if horiz else (w.y1, w.y2)) for w in ws)]
        lo, hi = min(r[0] for r in runs), max(r[1] for r in runs)
        if hi - lo < 1.0:
            continue
        exterior = any(getattr(w, "exterior", False) for w in ws)

        # 1) crossing walls at the ENDS only: pull each end IN to that wall's
        #    inner face. A wall crossing MID-run does not break the chain.
        span0, span1 = lo, hi
        for o in plan.walls:
            if o in ws or getattr(o, "railing", False):
                continue
            o_horiz = abs(o.x2 - o.x1) >= abs(o.y2 - o.y1)
            if o_horiz == horiz:
                continue
            oc = (o.x1 + o.x2) / 2.0 if horiz else (o.y1 + o.y2) / 2.0
            plo, phi = (min(o.y1, o.y2), max(o.y1, o.y2)) if horiz \
                else (min(o.x1, o.x2), max(o.x1, o.x2))
            if not (plo - 0.4 <= cross <= phi + 0.4):
                continue                              # does not touch this line
            if abs(oc - lo) < 0.6:
                span0 = max(span0, oc + half_ft(o))
            elif abs(oc - hi) < 0.6:
                span1 = min(span1, oc - half_ft(o))
        ticks = [span0, span1]

        # 2) columns on the line — their faces break the chain
        for c in plan.columns:
            ccross = c.y if horiz else c.x
            calong = c.x if horiz else c.y
            if abs(ccross - cross) > 0.7:
                continue
            if not (lo - 0.6 <= calong <= hi + 0.6):
                continue
            chw = ((getattr(c, "w", 0) if horiz else getattr(c, "h", 0)) or 0) / 2.0
            for t in (calong - chw, calong + chw):
                if span0 - 0.05 <= t <= span1 + 0.05:
                    ticks.append(min(max(t, span0), span1))

        # 3) door / window edges on ANY wall of this line
        for w in ws:
            L = math.hypot(w.x2 - w.x1, w.y2 - w.y1) or 1e-6
            ux, uy = (w.x2 - w.x1) / L, (w.y2 - w.y1) / L
            for o in plan.openings:
                if o.wall_id != w.id:
                    continue
                for d in (o.pos, o.pos + o.width):
                    t = (w.x1 + ux * d) if horiz else (w.y1 + uy * d)
                    if span0 - 0.05 <= t <= span1 + 0.05:
                        ticks.append(min(max(t, span0), span1))

        # merge near-coincident ticks so hairline segments never print
        ticks = sorted(set(round(t, 3) for t in ticks))
        merged = []
        for t in ticks:
            if not merged or t - merged[-1] > 0.12:
                merged.append(t)
        if len(merged) < 2:
            continue
        # 4) the chain sits just OFF the line — exterior lines on the OUTSIDE
        #    of the building, internal lines on the side away from plan centre
        if horiz:
            base = cross + OFF if cross >= my else cross - OFF
        else:
            base = cross + OFF if cross >= mx else cross - OFF
        _dim_chain(dl, merged, base, horiz)

    # overall size on the top & right
    _dim_chain(dl, [x0, x1], y1 + 2.4, True)
    _dim_chain(dl, [y0, y1], x1 + 2.4, False)


def draw_north(plan: Plan, dl: DrawList) -> None:
    x0, y0, x1, y1 = plan.extents()
    r = max(1.6, (x1 - x0) * 0.045)
    # The opening schedule occupies the sheet's top-right corner, so the north
    # point sits clear of it rather than under it.
    cx, cy = x1 + r * 3.0, y0 + (y1 - y0) * 0.5
    a = math.radians(plan.north_deg)
    tip = (cx + r * math.cos(a), cy + r * math.sin(a))
    tail = (cx - r * math.cos(a), cy - r * math.sin(a))
    perp = (a + math.pi / 2)
    l = (cx + r * 0.42 * math.cos(perp), cy + r * 0.42 * math.sin(perp))
    rr = (cx - r * 0.42 * math.cos(perp), cy - r * 0.42 * math.sin(perp))
    dl.poly([tip, l, tail, rr], layer="NORTH", closed=True)
    dl.line(tip[0], tip[1], tail[0], tail[1], layer="NORTH")
    dl.text(tip[0] + r * 0.35 * math.cos(a), tip[1] + r * 0.55 * math.sin(a) + 0.5,
            "N", h=0.7, layer="NORTH", bold=True)


def draw_plot(plan: Plan, dl: DrawList) -> None:
    if plan.plot:
        p = plan.plot
        dl.rect(p["x"], p["y"], p["w"], p["h"], layer="PLOT", dashed=True)


def draw_furniture(plan: Plan, dl: DrawList) -> None:
    """Furniture, each piece tagged with its mark and size.

    The sanitary and kitchen fixtures go on the SANITARY layer instead of
    FURNITURE, because the plumbing drawing keeps exactly those and drops
    every other piece. Splitting them by layer is what lets one view do that
    without deleting anything.
    """
    from . import furnsym, plumbing as P
    for f in plan.furniture:
        san = P.is_plumb_fixture(f.kind)
        furnsym.draw(dl, f, layer="SANITARY" if san else None)
        if san:
            continue                  # no size text — the plumbing sheet is
            # annotated by keyed notes, not by furniture labels
        cx, cy = f.centre
        label = furn.LABEL.get(f.kind, f.kind.upper())
        dl.text(cx, cy + 0.25, f.tag or label, h=0.34, layer="FURNTAG")
        dl.text(cx, cy - 0.28,
                f"{_fmt_ft(f.w)} x {_fmt_ft(f.h)}", h=0.26, layer="FURNTAG")


def draw_plumbing(plan: Plan, dl: DrawList) -> None:
    """The five plumbing systems, then the fittings and their keynote
    circles on top so a pipe never runs through a number."""
    from . import plumbsym
    for r in plan.pipes:
        if getattr(r, "visible", True):
            plumbsym.draw_run(dl, r)
    # No numbered key-note circles on the routing layout — the reference sheet
    # keeps it clean with pipe tags + the legend, not numbers piled on fittings
    # (that was the overlap / clutter). Traps, stacks and valves still draw.
    for p in plan.plumb:
        if getattr(p, "visible", True):
            plumbsym.draw(dl, p, keynotes=False)


def draw_elec(plan: Plan, dl: DrawList) -> None:
    """Electrical points, each with its legend symbol and number."""
    from . import elecsym
    for p in plan.elec:
        if getattr(p, "visible", True):
            elecsym.draw(dl, p)


def _elec_room_at(plan: Plan, p):
    """The room a fitting physically sits in — NOT its name. Two rooms can
    share a name ("BED ROOM"), and grouping loops by name then wires one
    board to both rooms' lights, crossing the partition. Points sit on walls,
    so the room whose box is nearest (0 inside) wins."""
    best, bd = None, 1e18
    for r in plan.rooms:
        if r.void:
            continue
        dx = max(r.x - p.x, 0, p.x - (r.x + r.w))
        dy = max(r.y - p.y, 0, p.y - (r.y + r.h))
        d = dx * dx + dy * dy
        if d < bd:
            best, bd = r, d
    return best


def draw_elec_loops(plan: Plan, dl: DrawList) -> None:
    """The switch loops, drawn the way they are wired.

    `core/looping.py` owns the rules; this only draws what it decides. Each
    switch loops in a CHAIN — switch to the nearest fitting, then on to the
    next (S1 > L1 > L2 …) — because the phase is looped fitting to fitting at
    the ceiling roses, not fanned out from the board. Only the phase is drawn:
    the neutral is a common loop and never passes through a switch, so it
    would say nothing here. Everything sits on the ELEC-LOOP layer so the set
    hides in one click.

    The fan keeps its TWO-WAY leg back to a bedside board.
    """
    from . import electrical as E
    from . import looping

    def _loop_arc(ax, ay, bx, by, bow):
        """One wiring leg as a CURVED arc (a shallow bow), the way looping is
        drawn on an electrical sheet — straight legs pile onto each other in a
        lit row and become unreadable; the bows keep every chain traceable."""
        L = math.hypot(bx - ax, by - ay)
        if L < 0.3:
            dl.line(ax, ay, bx, by, layer="ELEC-LOOP")
            return
        sag = max(0.18, min(0.9, L * 0.16)) * bow
        px, py = -(by - ay) / L, (bx - ax) / L        # unit perpendicular
        mx_, my_ = (ax + bx) / 2 + px * sag, (ay + by) / 2 + py * sag
        pts = []
        for i in range(9):                            # quadratic bezier, 8 legs
            t = i / 8.0
            u = 1 - t
            pts.append((u * u * ax + 2 * u * t * mx_ + t * t * bx,
                        u * u * ay + 2 * u * t * my_ + t * t * by))
        dl.poly(pts, layer="ELEC-LOOP", closed=False)

    for k, s in enumerate(looping.switches(plan)):
        if not s.seq:
            continue
        bow = 1 if k % 2 == 0 else -1            # alternate chains bow apart
        pts = ([(s.board.x, s.board.y)] if s.board is not None else []) \
            + [(p.x, p.y) for p in s.seq]
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            _loop_arc(ax, ay, bx, by, bow)
        # the switch number, set on its first leg so each chain is traceable
        if len(pts) >= 2:
            (ax, ay), (bx, by) = pts[0], pts[1]
            dl.text(ax + (bx - ax) * 0.32, ay + (by - ay) * 0.32,
                    s.id, h=0.19, layer="ELEC-LOOP")

    # two-way for the fan: a second leg from the bedside board (the one highest
    # up the room, at the bed head) so the fan switches from the bed too
    def visible(p):
        return getattr(p, "visible", True)

    buckets: dict[int, list] = {}
    for p in plan.elec:
        if visible(p):
            r = _elec_room_at(plan, p)
            if r is not None:
                buckets.setdefault(id(r), []).append(p)
    for pts_r in buckets.values():
        fans = [p for p in pts_r if p.code == "CF"]
        bedside = [p for p in pts_r if p.code == "SB"
                   and p.height_mm == E.H_BEDSIDE_BOARD]
        if fans and bedside:
            bb = max(bedside, key=lambda p: p.y)
            for f in fans:
                _loop_arc(bb.x, bb.y + (0.18 if bb.y < f.y else -0.18),
                          f.x, f.y, -1)


def draw_flooring(plan: Plan, dl: DrawList) -> None:
    """The tile grid, spacers, start point, skirting and level for each room."""
    from . import floorlayout
    floorlayout.draw(plan, dl)


def draw_raw(plan: Plan, dl: DrawList) -> None:
    """Reproduce an imported DXF EXACTLY — the lines, polylines, arcs and text
    the user drew, on their own layers, with no re-thickening. This is what
    makes a DXF with drawn wall thickness come out as-is instead of doubled."""
    for it in plan.raw:
        t = it.get("t")
        ly = it.get("layer", "WALL-EXT")
        try:
            if t == "line":
                dl.line(it["x1"], it["y1"], it["x2"], it["y2"], layer=ly)
            elif t == "poly":
                dl.poly([tuple(p) for p in it["pts"]], layer=ly,
                        closed=bool(it.get("closed")))
            elif t == "arc":
                dl.arc(it["cx"], it["cy"], it["r"], it["a1"], it["a2"],
                       layer=ly)
            elif t == "text":
                dl.text(it["x"], it["y"], it["s"], h=it.get("h", 0.5),
                        layer=ly, angle=it.get("angle", 0.0))
        except Exception:
            pass


def build(plan: Plan, wall_tags: bool = True, furniture: bool = True,
          elec: bool = True, plumb: bool = True, floor: bool = True,
          sections: bool = True) -> DrawList:
    dl = DrawList()

    # an imported DXF is drawn verbatim; the walls/rooms/dims it carries are
    # already IN the raw geometry, so we do not regenerate (and re-thicken)
    # them. The overlay stages still draw on top.
    raw = bool(getattr(plan, "raw", None))
    if raw:
        draw_raw(plan, dl)

    draw_plot(plan, dl)
    draw_lawn(plan, dl)               # grass under a lawn / garden, always shown
    if floor and plan.flooring:
        draw_flooring(plan, dl)       # under everything — it is the floor
    if not raw:
        draw_walls(plan, dl)
    if getattr(plan, "columns", None):
        draw_columns(plan, dl)
    if sections and getattr(plan, "sections", None):
        draw_sections(plan, dl)          # section line lives on the FLOOR PLAN only
    if wall_tags:
        draw_wall_tags(plan, dl)
    if furniture and plan.furniture:
        draw_furniture(plan, dl)
    if elec and plan.elec:
        draw_elec_loops(plan, dl)     # under the symbols, so it reads behind
        draw_elec(plan, dl)
    if plumb and (plan.plumb or plan.pipes):
        draw_plumbing(plan, dl)
    if not raw:
        # an imported DXF already draws its own openings, stairs, room names
        # and dimensions in the raw geometry — regenerating them would double
        # the lines and re-print the labels
        draw_windows(plan, dl)
        draw_doors(plan, dl)
        draw_stairs(plan, dl)
        draw_steps(plan, dl)
        draw_rooms(plan, dl)
        draw_dims(plan, dl)
        if getattr(plan, "autodim", False):
            draw_auto_dims(plan, dl)
    # No north point in the drawing area — the sheet's title strip carries it,
    # and a second one both duplicates it and pushes the plan's extents out,
    # costing a scale step.
    return dl
