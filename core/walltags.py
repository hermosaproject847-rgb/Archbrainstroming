"""Wall numbering — split by room, tagged on the drawing.

Two jobs, both about being able to say *which* wall:

  split_by_rooms()  A single long partition often runs past several rooms. As
                    one wall it cannot be edited per room: shortening it for
                    the kitchen also moves it for the bedroom. Splitting it at
                    the room boundaries it crosses gives each room its own
                    piece — and every opening is carried over to the piece it
                    actually sits in.

  renumber()        Every wall then gets a number, ordered so the numbers make
                    sense on the sheet: the external envelope first, then the
                    internal walls room by room. The number is drawn on the
                    plan, so the table and the drawing agree.
"""

from __future__ import annotations

from shapely.geometry import box

TOL = 0.02          # feet; two coordinates closer than this are the same line
MIN_PIECE = 0.4     # do not create slivers


def _is_h(w) -> bool:
    return abs(w.y2 - w.y1) < 1e-6


def _is_v(w) -> bool:
    return abs(w.x2 - w.x1) < 1e-6


def _room_edges(plan, horizontal: bool) -> list[tuple[float, float, float]]:
    """(line, lo, hi) for every room edge that could cut a wall of that run."""
    out = []
    for r in plan.rooms:
        if horizontal:
            # a horizontal wall is cut by the rooms' vertical edges
            for x in (r.x, r.x + r.w):
                out.append((x, r.y, r.y + r.h))
        else:
            for y in (r.y, r.y + r.h):
                out.append((y, r.x, r.x + r.w))
    return out


def split_by_rooms(plan) -> list[str]:
    """Cut every wall where a room boundary meets it. Returns what changed."""
    notes: list[str] = []
    new_walls = []
    remap: dict[str, list] = {}

    for w in plan.walls:
        if w.railing or not (_is_h(w) or _is_v(w)):
            new_walls.append(w)
            continue

        horiz = _is_h(w)
        a, b = (sorted((w.x1, w.x2)) if horiz else sorted((w.y1, w.y2)))
        line = w.y1 if horiz else w.x1

        cuts = {a, b}
        for pos, lo, hi in _room_edges(plan, horiz):
            if a + MIN_PIECE < pos < b - MIN_PIECE and lo - TOL <= line <= hi + TOL:
                cuts.add(round(pos, 4))

        stations = sorted(cuts)
        if len(stations) <= 2:
            new_walls.append(w)
            continue

        pieces = []
        for s, e in zip(stations, stations[1:]):
            if e - s < MIN_PIECE:
                continue
            p = _clone(w)
            if horiz:
                p.x1, p.x2, p.y1, p.y2 = s, e, line, line
            else:
                p.y1, p.y2, p.x1, p.x2 = s, e, line, line
            pieces.append(p)

        if len(pieces) <= 1:
            new_walls.append(w)
            continue

        remap[w.id] = pieces
        new_walls.extend(pieces)
        notes.append(f"wall {w.id} split into {len(pieces)} pieces at the room "
                     "boundaries it crosses")

    if not remap:
        return notes

    # give the pieces temporary unique ids, then move each opening onto the
    # piece it physically sits in
    for old, pieces in remap.items():
        for i, p in enumerate(pieces, start=1):
            p.id = f"{old}.{i}"

    for o in plan.openings:
        pieces = remap.get(o.wall_id)
        if not pieces:
            continue
        src = next((w for w in plan.walls if w.id == o.wall_id), None)
        if src is None:
            continue
        mid = src.point_at(o.pos + o.width / 2)
        best, best_d = None, 1e9
        for p in pieces:
            d = _dist_to(p, mid)
            if d < best_d:
                best, best_d = p, d
        if best is None:
            continue
        start = (min(best.x1, best.x2) if _is_h(best)
                 else min(best.y1, best.y2))
        along = (mid[0] if _is_h(best) else mid[1]) - start
        o.wall_id = best.id
        o.pos = max(0.0, min(along - o.width / 2, best.length - o.width))

    plan.walls = new_walls
    return notes


def _dist_to(w, pt) -> float:
    """Distance from a point to a wall segment (axis-aligned)."""
    if _is_h(w):
        lo, hi = sorted((w.x1, w.x2))
        dx = 0.0 if lo <= pt[0] <= hi else min(abs(pt[0] - lo), abs(pt[0] - hi))
        return (dx ** 2 + (pt[1] - w.y1) ** 2) ** 0.5
    lo, hi = sorted((w.y1, w.y2))
    dy = 0.0 if lo <= pt[1] <= hi else min(abs(pt[1] - lo), abs(pt[1] - hi))
    return (dy ** 2 + (pt[0] - w.x1) ** 2) ** 0.5


def _clone(w):
    from .model import Wall
    return Wall(id=w.id, x1=w.x1, y1=w.y1, x2=w.x2, y2=w.y2,
                thickness_in=w.thickness_in, exterior=w.exterior,
                railing=w.railing)


# ------------------------------------------------------------- numbering
def owner_of(plan, w) -> str:
    """The room a wall belongs to: the one it borders along its whole length.
    Exterior walls belong to the envelope, not to a room."""
    if w.exterior:
        return ""
    mid = w.point_at(w.length / 2)
    off = w.th / 2 + 0.3
    if _is_h(w):
        probes = [(mid[0], mid[1] + off), (mid[0], mid[1] - off)]
    else:
        probes = [(mid[0] + off, mid[1]), (mid[0] - off, mid[1])]

    names = []
    for px, py in probes:
        for r in plan.rooms:
            if r.x <= px <= r.x + r.w and r.y <= py <= r.y + r.h:
                names.append(r.name)
                break
    if not names:
        return ""
    # the smaller room owns the wall — that is the one it defines
    areas = {r.name: r.w * r.h for r in plan.rooms}
    return min(names, key=lambda n: areas.get(n, 1e9))


def renumber(plan, start: int = 1) -> list[str]:
    """W1, W2, … — the envelope first, then internal walls grouped by room.
    `start` lets a multi-floor project continue the numbering across floors
    (ground floor W1–W45, first floor W46 …)."""
    ext = [w for w in plan.walls if w.exterior and not w.railing]
    rail = [w for w in plan.walls if w.railing]
    inner = [w for w in plan.walls if not w.exterior and not w.railing]

    def clockwise(w):
        """Envelope in reading order: south, east, north, west."""
        if _is_h(w):
            return (0, w.x1) if w.y1 <= _mid_y(plan) else (2, -w.x1)
        return (1, w.y1) if w.x1 > _mid_x(plan) else (3, -w.y1)

    ext.sort(key=clockwise)

    groups: dict[str, list] = {}
    for w in inner:
        groups.setdefault(owner_of(plan, w) or "~", []).append(w)
    for g in groups.values():
        g.sort(key=lambda w: (0 if _is_h(w) else 1, w.y1, w.x1))

    order = list(ext)
    for name in sorted(groups, key=lambda n: (n == "~", n.lower())):
        order.extend(groups[name])
    order.extend(rail)

    old = {id(w): w.id for w in order}
    for i, w in enumerate(order, start=start):
        w.id = ("R" if w.railing else "W") + str(i)
    plan.walls = order

    # Every opening refers to its wall by id, so the ids must move together —
    # renaming walls alone would orphan every door and window on the plan.
    rename = {old[id(w)]: w.id for w in order}
    for o in plan.openings:
        if o.wall_id in rename:
            o.wall_id = rename[o.wall_id]

    changed = sum(1 for w in order if old[id(w)] != w.id)
    return [f"{changed} wall(s) renumbered W1–W{len(order)}, "
            "envelope first then by room"] if changed else []


def _mid_x(plan) -> float:
    xs = [v for w in plan.walls for v in (w.x1, w.x2)]
    return (min(xs) + max(xs)) / 2 if xs else 0.0


def _mid_y(plan) -> float:
    ys = [v for w in plan.walls for v in (w.y1, w.y2)]
    return (min(ys) + max(ys)) / 2 if ys else 0.0
