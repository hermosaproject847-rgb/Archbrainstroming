"""Switch-wise light looping — the rules, in one place.

Everything the drawing and the Switch-Loop schedule show about looping comes
from here, so the two can never disagree. The rules encoded:

1. **Lights are grouped by FUNCTION, not by room.** General lighting sits on
   one switch; cove / profile, decorative, bedside, mirror, step and wall
   lights each take their own. A room is never switched as one lump.
2. **The PHASE loops in a chain** — switch to the nearest light, then on to
   the next nearest (S1 -> L1 -> L2 -> L3 …). The NEUTRAL is a common loop and
   NEVER passes through a switch; only the phase is broken by the switch, which
   is why the drawing shows the phase chain alone.
3. **Loop joints only at a ceiling rose or junction box** — that is, at the
   fittings themselves. The chain therefore runs fitting to fitting and never
   joints mid-conduit (IS 732).
4. **A lighting sub-circuit carries at most 800 W or 10 points** (IS 732).
   A group past either limit is split into further switches / circuits.
5. **Light loops are 1.5 sq.mm Cu FRLS.** 5A/16A power points are separate
   circuits and never share a lighting loop.
6. **General lighting is never all-or-nothing.** A room's ceiling lighting is
   split across TWO switches — a main bank and a smaller alternate bank — so
   the room can be run at part light. The alternate fittings are picked at
   EVEN SPACING round the loop, never as one half of the room, so switching
   just the small bank still lights the whole room evenly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import electrical as E

# IS 732 limits for a lighting sub-circuit
MAX_W = 800.0
MAX_PTS = 10
WIRE = "1.5 sq.mm Cu FRLS"

# Rule 6 — general lighting from this many fittings up is split into a main and
# an alternate bank, so a room can be run at part light
BANK_MIN = 4
GENERAL = "General lighting"

# Rule 1 — the functional groups, in the order a board's switches are laid out
GROUPS = [
    ("General lighting", ("SL", "ASL", "PL", "CSL")),
    ("Cove / profile",   ("CV", "TR")),
    ("Decorative",       ("HL", "CH")),
    ("Wall lights",      ("WL",)),
    ("Bedside lights",   ("BWL",)),
    ("Mirror light",     ("ML",)),
    ("Step / foot",      ("STL",)),
    ("Fan",              ("CF",)),
    ("Exhaust",          ("EF",)),
]


@dataclass
class Switch:
    """One switch on a board, and the chain of points it loops through."""
    id: str = ""
    duty: str = ""
    room: str = ""
    board: object = None
    seq: list = field(default_factory=list)

    @property
    def watts(self) -> float:
        return sum((p.watts or 0) for p in self.seq)

    @property
    def circuits(self) -> list:
        out = []
        for p in self.seq:
            if p.circuit and p.circuit not in out:
                out.append(p.circuit)
        return out


def mark(p) -> str:
    """A point as the plan letters it — L7, F1, E.F.1."""
    from . import elecsym
    n = p.tag.rsplit("-", 1)[-1].lstrip("0") or "1"
    return f"{elecsym._SHORT.get(p.code, '')}{n}"


def _chain(start, pts: list) -> list:
    """Rule 2 — nearest first, then nearest to that one, and so on. The loop
    follows the shortest walk between fittings rather than fanning out from
    the switch, which is both how it is wired and how it is drawn."""
    todo = list(pts)
    out: list = []
    if start is not None:
        cx, cy = start.x, start.y
    else:
        cx, cy = todo[0].x, todo[0].y
    while todo:
        nxt = min(todo, key=lambda p: (p.x - cx) ** 2 + (p.y - cy) ** 2)
        todo.remove(nxt)
        out.append(nxt)
        cx, cy = nxt.x, nxt.y
    return out


def _banks(duty: str, chain: list) -> list:
    """Rule 6 — split general lighting into a main bank and a smaller
    alternate bank.

    Six spots on one switch means all six or none; someone who wants the room
    dim has no option. The alternate bank takes about a third of the fittings,
    chosen at EVEN SPACING along the loop — for six that is two, opposite each
    other, giving a 4 + 2 split where the 2 still cover the whole room. Taking
    a contiguous half instead would leave one end of the room dark.
    """
    n = len(chain)
    if duty != GENERAL or n < BANK_MIN:
        return [(duty, chain)]
    m = max(2, int(round(n / 3.0)))          # the small bank
    if m >= n:
        return [(duty, chain)]
    picked = {id(p) for p in _spread_pick(chain, m)}
    alt = [p for p in chain if id(p) in picked]
    main = [p for p in chain if id(p) not in picked]
    if not alt or not main:
        return [(duty, chain)]
    return [(f"{duty} — main", main), (f"{duty} — alternate", alt)]


def _spread_pick(pts: list, m: int) -> list:
    """`m` fittings chosen to sit as far apart as they can (farthest-point
    sampling). Picking every other one ALONG THE CHAIN is not enough — a
    nearest-neighbour walk does not always run round the room, so two
    "alternate" fittings could come out side by side and light only one
    corner. Distance decides it instead."""
    if m >= len(pts):
        return list(pts)
    cx = sum(p.x for p in pts) / len(pts)
    cy = sum(p.y for p in pts) / len(pts)
    chosen = [max(pts, key=lambda p: (p.x - cx) ** 2 + (p.y - cy) ** 2)]
    taken = {id(chosen[0])}
    while len(chosen) < m:
        nxt = max((p for p in pts if id(p) not in taken),
                  key=lambda p: min((p.x - c.x) ** 2 + (p.y - c.y) ** 2
                                    for c in chosen))
        chosen.append(nxt)
        taken.add(id(nxt))
    return chosen


def _split(chain: list) -> list:
    """Rule 4 — break the chain wherever it would pass 800 W or 10 points.
    Split on the CHAIN so each sub-circuit stays spatially contiguous."""
    runs, cur, w = [], [], 0.0
    for p in chain:
        pw = p.watts or 0
        if cur and (len(cur) + 1 > MAX_PTS or w + pw > MAX_W):
            runs.append(cur)
            cur, w = [], 0.0
        cur.append(p)
        w += pw
    if cur:
        runs.append(cur)
    return runs


def switches(plan) -> list:
    """Every switch on the plan, numbered S1, S2 … in reading order."""
    from . import engine

    def visible(p):
        return getattr(p, "visible", True)

    out: list = []
    n = 0
    rooms = sorted([r for r in plan.rooms if not r.void],
                   key=lambda r: (-round(r.y + r.h, 1), round(r.x, 1)))
    for room in rooms:
        here = [p for p in plan.elec
                if visible(p) and engine._elec_room_at(plan, p) is room]
        if not here:
            continue
        board = next((p for p in here if p.code == "SB"
                      and p.height_mm == E.H_ENTRY_BOARD), None)
        for duty, codes in GROUPS:
            g = [p for p in here if p.code in codes]
            if not g:
                continue
            for label, bank in _banks(duty, _chain(board, g)):
                # each bank is re-chained: it is its own run of cable
                for run in _split(_chain(board, bank)):
                    n += 1
                    out.append(Switch(id=f"S{n}", duty=label, room=room.name,
                                      board=board, seq=run))
    return out


SHORT_DUTY = {
    "General lighting — main": "Gen. light (main)",
    "General lighting — alternate": "Gen. light (alt)",
    "General lighting": "General light",
    "Cove / profile": "Cove / profile",
    "Bedside lights": "Bedside",
    "Mirror light": "Mirror",
    "Step / foot": "Step light",
}


def rows(plan) -> list[list[str]]:
    """The Switch-Loop schedule:
    Switch | Room / duty | Lights controlled | Looping sequence | Wattage |
    Circuit | Wire.

    "Lights controlled" lists the FITTINGS — which is what the column says;
    the room and duty have their own column rather than being crammed in with
    them, which was making the cell too long to set at a readable size.
    """
    out = []
    for s in switches(plan):
        marks = [mark(p) for p in s.seq]
        duty = SHORT_DUTY.get(s.duty, s.duty)
        out.append([
            s.id,
            f"{s.room} — {duty}",
            ", ".join(marks),
            " > ".join([s.id] + marks),
            f"{s.watts:.0f} W",
            "/".join(s.circuits) or "—",
            WIRE,
        ])
    return out


def notes(plan) -> list[str]:
    """What the layout had to do to stay inside IS 732 — worth saying out
    loud rather than leaving in the geometry."""
    out = []
    sw = switches(plan)
    over = [s for s in sw if s.watts > MAX_W or len(s.seq) > MAX_PTS]
    for s in over:
        out.append(f"{s.id} carries {s.watts:.0f} W over {len(s.seq)} points "
                   f"— past the {MAX_W:.0f} W / {MAX_PTS} point limit.")
    out.append(f"{len(sw)} switches; phase looped switch to nearest fitting "
               "onward, neutral looped common and never through a switch; "
               f"joints at ceiling roses only; {WIRE} throughout.")
    return out
