"""Deterministic corrections applied before drawing.

These are the rules that do NOT need to be read off the sketch, because they
follow from the geometry itself. Solving them here removes a whole class of
reading mistakes: the reader only has to say WHICH room a door serves, and the
swing side, the hinge jamb and the spurious open-area walls are then computed.

Every change is reported, so nothing is corrected silently.
"""

from __future__ import annotations

from shapely.geometry import Point, box

from .model import Plan, Opening, Swing

STEP = 0.25          # sampling step along a wall, feet


def _rooms_at(plan: Plan, pt) -> list:
    # plain arithmetic — building a shapely box per room per sample summed to
    # 40,000+ boxes per validation pass and was the whole reason every edit
    # felt stuck on the small server
    x, y = pt
    return [r for r in plan.rooms
            if r.x <= x <= r.x + r.w and r.y <= y <= r.y + r.h]


def _sides_of(plan: Plan, w, d: float):
    """The rooms immediately either side of a wall, `d` feet along it."""
    px, py = w.point_at(d)
    off = w.th / 2 + 0.35
    if w.horizontal:
        a, b = (px, py + off), (px, py - off)
    elif abs(w.x2 - w.x1) < 1e-9:
        a, b = (px - off, py), (px + off, py)
    else:
        L = w.length or 1e-9
        ux, uy = (w.x2 - w.x1) / L, (w.y2 - w.y1) / L
        a, b = (px - uy * off, py + ux * off), (px + uy * off, py - ux * off)
    return _rooms_at(plan, a), _rooms_at(plan, b), a, b


# ------------------------------------------------------------- door swings
_SERVICE_WORDS = ("toilet", "bath", "wc", "w.c", "powder", "washroom",
                  "lavatory", "store", "dress", "utility", "pooja", "puja")


def _is_service(name: str) -> bool:
    n = (name or "").lower()
    return any(k in n for k in _SERVICE_WORDS)


def _flanking_rooms(plan: Plan, w, mid: float):
    """The two rooms on either side of a door opening — used to make a small
    service room's door open INTO the service room."""
    px, py = w.point_at(mid)
    off = w.th / 2 + 0.35
    L = w.length or 1e-9
    ux, uy = (w.x2 - w.x1) / L, (w.y2 - w.y1) / L

    def at(pt):
        for r in plan.rooms:
            if r.x <= pt[0] <= r.x + r.w and r.y <= pt[1] <= r.y + r.h:
                return r
        return None
    return (at((px - uy * off, py + ux * off)),
            at((px + uy * off, py - ux * off)))


def fix_swings(plan: Plan) -> list[str]:
    """Point every door into the room it serves, hinged so the leaf folds flat
    against the nearest perpendicular wall."""
    notes: list[str] = []
    for o in plan.openings:
        if not o.is_door or not o.swing or not o.swing.room:
            continue
        if o.swing.manual:
            # Someone flipped this by hand. Recomputing it would silently undo
            # their edit on the very next redraw, which is why flipping a door
            # appeared not to work at all.
            continue
        w = plan.wall(o.wall_id)
        if w is None:
            continue

        # a door between a small service room (toilet / bath / store / dress)
        # and any other space opens INTO the service room — that is the room it
        # serves, and its leaf must not swing out into circulation
        ra, rb = _flanking_rooms(plan, w, o.pos + o.width / 2)
        svc = [r for r in (ra, rb) if r and _is_service(r.name)]
        non = [r for r in (ra, rb) if r and not _is_service(r.name)]
        if len(svc) == 1 and non and o.swing.room != svc[0].name:
            notes.append(f"{o.tag or 'door'}: set to open into {svc[0].name} "
                         "(a service room opens inward, not into circulation)")
            o.swing.room = svc[0].name

        room = plan.room(o.swing.room)
        if room is None:
            continue

        mid = o.pos + o.width / 2
        px, py = w.point_at(mid)
        off = w.th / 2 + 0.35
        L = w.length or 1e-9
        ux, uy = (w.x2 - w.x1) / L, (w.y2 - w.y1) / L
        left = (px - uy * off, py + ux * off)     # left of the walking direction
        rb = box(room.x, room.y, room.x + room.w, room.y + room.h)

        side = "left" if rb.contains(Point(left)) else "right"
        if side != o.swing.side:
            notes.append(f"{o.tag or 'door'}: swing side set to {side} so it "
                         f"opens into {room.name}")
            o.swing.side = side

        # hinge at the jamb nearer the end of the wall, so the leaf lies along
        # the perpendicular wall there rather than floating mid-room
        hinge = "start" if (o.pos < (w.length - (o.pos + o.width))) else "end"
        if hinge != o.swing.hinge:
            notes.append(f"{o.tag or 'door'}: hinged at the {hinge} jamb so the "
                         "leaf folds along the adjacent wall")
            o.swing.hinge = hinge
    return notes


# --------------------------------------------------- walls in open areas
def strip_open_area_walls(plan: Plan) -> list[str]:
    """A wall span with an OPEN AREA on both sides is not a wall — two adjacent
    open areas are one continuous space. Such spans are punched out (recorded as
    `open` openings) rather than deleted, so wall ids and every other opening on
    the same wall stay valid."""
    notes: list[str] = []
    for w in plan.walls:
        if w.railing:
            continue                  # a railing is drawn, never stripped
        spans, run = [], None
        d = 0.0
        while d <= w.length + 1e-9:
            a, b, _, _ = _sides_of(plan, w, min(d, w.length))
            # A shaft (O.T.S, duct, light well) is open to the sky but walled
            # all round, so a wall touching one is real and must stay.
            spurious = (bool(a) and bool(b)
                        and all(r.open_area and not r.void for r in a)
                        and all(r.open_area and not r.void for r in b))
            if spurious and run is None:
                run = d
            elif not spurious and run is not None:
                spans.append((run, d))
                run = None
            d += STEP
        if run is not None:
            spans.append((run, w.length))

        for (s0, s1) in spans:
            if s1 - s0 < 0.6:                 # ignore sampling noise at corners
                continue
            # grow by one sampling step so the punch reaches the true edge of
            # the span rather than the first sample inside it
            a = max(0.0, s0 - STEP)
            b = min(w.length, s1 + STEP)
            plan.openings.append(Opening(
                type="open", wall_id=w.id, pos=a, width=b - a, tag="OPEN"))
            notes.append(f"wall {w.id}: {s1 - s0:.1f} ft removed — open area on "
                         "both sides, so there is no wall there")
    return notes


def apply(plan: Plan) -> list[str]:
    return fix_swings(plan) + strip_open_area_walls(plan)
