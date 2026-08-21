"""Opening marks — D1, W1, V1 …

Two jobs, both from what sketches actually look like:

  * A sketch usually letters its openings "D", "W", "V" and leaves the
    numbering to the draughtsman — every window simply says W. The rulebook
    (§2.4, §3.1, §4.1) requires a distinct mark on each one, so they are
    numbered here.

  * **A window in a toilet or bath is a ventilator.** It sits at high sill, it
    is there for ventilation rather than light, and it belongs in the schedule
    as V — with the ventilator's sill and lintel, not a window's. Sketches
    rarely make the distinction, so it is made from the room the opening
    serves.
"""

from __future__ import annotations

from . import standards as std

PREFIX = {"window": "W", "vent": "V", "gate": "G"}
DOOR_PREFIX = "D"


def _room_of(plan, o) -> str:
    """The room an opening serves — the door's own room, or the nearest."""
    if o.is_door and o.swing and o.swing.room:
        return o.swing.room
    w = plan.wall(o.wall_id)
    if w is None:
        return ""
    mid = w.point_at(o.pos + o.width / 2)
    best, best_d = "", 1e9
    for r in plan.rooms:
        cx, cy = r.centre
        d = (cx - mid[0]) ** 2 + (cy - mid[1]) ** 2
        if d < best_d:
            best, best_d = r.name, d
    return best


def _sort_key(plan, o):
    """Reading order on the sheet: top to bottom, then left to right."""
    w = plan.wall(o.wall_id)
    if w is None:
        return (0.0, 0.0)
    x, y = w.point_at(o.pos + o.width / 2)
    return (-round(y, 1), round(x, 1))


def wet_windows_to_vents(plan) -> list[str]:
    """A window serving a toilet or bath is a ventilator. Re-type it, and give
    it the ventilator's sill and lintel unless the sketch stated them."""
    notes: list[str] = []
    for o in plan.openings:
        if o.type != "window":
            continue
        room = _room_of(plan, o)
        if std.classify(room) != "wet":
            continue
        o.type = "vent"
        was = o.tag
        notes.append(f"{was or 'window'} in '{room}' is a ventilator — "
                     "a window serving a toilet or bath is marked V")
        # a ventilator sits high; a window's 900 sill would be wrong here
        if not o.sill_mm or abs(o.sill_mm - std.WINDOW_SILL_MM) < 1:
            o.sill_mm = std.VENT_SILL_MM
        if not o.lintel_mm or abs(o.lintel_mm - std.WINDOW_LINTEL_MM) < 1:
            o.lintel_mm = std.VENT_LINTEL_MM
        if not o.height_mm or o.height_mm > 900:
            o.height_mm = std.default_height("vent")
    return notes


def renumber(plan, force: bool = False) -> list[str]:
    """Give every opening a distinct mark: D1…, W1…, V1…

    `force` renumbers everything. Otherwise marks the sketch already made
    distinct are kept — a sketch that says D4 means D4 — and only the bare
    letters ("W", "D") and duplicates are numbered.
    """
    notes = wet_windows_to_vents(plan)

    groups: dict[str, list] = {}
    for o in plan.openings:
        if o.type in ("open",):
            continue
        key = DOOR_PREFIX if o.is_door else PREFIX.get(o.type)
        if key:
            groups.setdefault(key, []).append(o)

    for prefix, items in groups.items():
        items.sort(key=lambda o: _sort_key(plan, o))

        # a mark already numbered and unique is the designer's — leave it
        keep: dict[str, object] = {}
        if not force:
            counts: dict[str, int] = {}
            for o in items:
                t = (o.tag or "").strip().upper()
                if t and t != prefix and any(c.isdigit() for c in t):
                    counts[t] = counts.get(t, 0) + 1
            keep = {t for t, n in counts.items() if n == 1}

        used = set(keep)
        n = 0
        for o in items:
            t = (o.tag or "").strip().upper()
            if t in used and t in keep:
                continue                       # keep the sketch's own mark
            n += 1
            while f"{prefix}{n}" in used:
                n += 1
            new = f"{prefix}{n}"
            if new != o.tag:
                notes.append(f"{o.tag or o.type} → {new}")
            o.tag = new
            used.add(new)
    return notes
