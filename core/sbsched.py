"""The SWITCHBOARD SCHEDULE, in the practice's reference format.

One row per board: its number, its symbol, its mounting height, how many
modules the plate is, and — the point of the table — a DESCRIPTION of exactly
what each board switches: which numbered lights, the fan and its regulator,
the exhaust, the sockets. Built from the same board placement and light
numbering the plan carries, so the schedule and the drawing cannot disagree.

Columns match the reference sheet:  S. NO. | SYMBOL | HEIGHT | MODULE |
DESCRIPTION | QTY.
"""

from __future__ import annotations

from . import electrical as E
from .draw import DrawList, LINE_SP, fit_cell

COLS = [("S. NO.", 16), ("SYMBOL", 16), ("HEIGHT", 16), ("MODULE", 18),
        ("DESCRIPTION", 74), ("QTY", 10)]
TOTAL = sum(c[1] for c in COLS)

STD_MODULES = (1, 2, 3, 4, 6, 8, 12, 16, 18)

_CEILING = ("SL", "ASL", "PL", "CSL", "CV", "TR", "HL", "CH")
# how a ceiling code reads as a switch label
_LIGHT_LABEL = {"SL": "spot lights", "ASL": "spot lights", "PL": "panel lights",
                "CSL": "surface lights", "CV": "cove", "TR": "profile lights",
                "HL": "pendant", "CH": "chandelier"}


def _std(n: int) -> int:
    for s in STD_MODULES:
        if n <= s:
            return s
    return n


def _mark(b) -> str:
    """The mark exactly as elecsym prints it on the plan."""
    n = b.tag.rsplit("-", 1)[-1].lstrip("0") or "1"
    return ("D.B." if b.code == "DB" else "S.B.") + n


def _lno(p) -> int:
    try:
        return int(p.tag.rsplit("-", 1)[-1])
    except ValueError:
        return 0


def _ranges(nums) -> str:
    nums = sorted(set(nums))
    out, i = [], 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        out.append(f"L{nums[i]}" if i == j else f"L{nums[i]}-L{nums[j]}")
        i = j + 1
    return ", ".join(out)


def _lighting_desc(switches) -> tuple:
    """The duty of a lighting board, read straight off the switches that
    `core/looping.py` actually put on it — one module per switch, plus a
    module for each fan regulator. Deriving it any other way let the board's
    module count drift from the number of switches really wired to it."""
    from . import looping

    parts, mod = [], 0
    for s in switches:
        marks = _ranges([_lno(p) for p in s.seq if p.code in _CEILING]) \
            or ", ".join(looping.mark(p) for p in s.seq)
        if s.duty.startswith("Fan"):
            parts.append(f"{s.id}: switch + regulator, fan "
                         f"({', '.join(looping.mark(p) for p in s.seq)})")
            mod += 2                              # switch + regulator module
        else:
            parts.append(f"{s.id}: {s.duty.lower()} ({marks})")
            mod += 1
    if not parts:
        return "ADDITIONAL LIGHT / FAN SWITCHES", 2
    return "; ".join(parts).upper(), _std(mod)


# height -> (description, modules) for the socket boards
_SOCKET = {
    E.H_BEDSIDE_BOARD: ("2-way switch for main light & fan, 6A socket x2, USB",
                        4),
    E.H_TV_BOARD: ("16A socket x1, 6A socket x3, data point", 8),
    E.H_KITCHEN_COUNTER: ("6/16A appliance socket + switch", 3),
    E.H_SOFA_SIDE: ("6A socket x2 for charging & floor lamp", 2),
    E.H_FRIDGE: ("16A socket, dedicated, for the fridge", 2),
    E.H_GEYSER: ("20A DP switch with neon, for the geyser", 2),
}


def _reading_order(pts):
    """Down the sheet, then across — independent of any tag, so the duty a
    board is given never depends on the numbering it is about to receive."""
    return sorted(pts, key=lambda p: (-round(p.y, 1), round(p.x, 1)))


def duties(plan) -> dict:
    """id(board) -> (description, modules). One place decides what a board
    does, so the plan mark, the schedule and the totals can never disagree."""
    from . import looping

    by_board: dict = {}
    for s in looping.switches(plan):
        if s.board is not None:
            by_board.setdefault(id(s.board), []).append(s)

    out = {}
    for b in _reading_order([p for p in plan.elec if p.code in ("SB", "DB")]):
        if b.code == "DB":
            out[id(b)] = ("MAIN DISTRIBUTION BOARD - RCCB 30 mA, separate "
                          "lighting / power / AC banks", None)
        elif b.height_mm == E.H_ENTRY_BOARD:
            # a second board in the same room owns no switches, so it falls
            # through to the "additional switches" wording on its own
            out[id(b)] = _lighting_desc(by_board.get(id(b), []))
        else:
            d, m = _SOCKET.get(b.height_mm, ("switch / socket board", 3))
            out[id(b)] = (d.upper(), m)
    return out


def assign_type_tags(plan) -> None:
    """Mark every board with its TYPE, and mark it that way ON THE PLAN.

    This is the convention the practice's schedule follows: boards that are
    identical — same height, same plate, same duty — are one type, drawn with
    one mark wherever they occur, and the schedule describes that type once
    with a quantity. Numbering the boards by location instead (S.B.1 … S.B.21)
    left the drawing and the schedule naming the same board differently, which
    is what stopped them matching. A repeating type takes a letter, a one-off
    takes a number.
    """
    import string

    d = duties(plan)
    groups, order = {}, []
    for b in _reading_order([p for p in plan.elec if p.code == "SB"]):
        desc, mod = d[id(b)]
        key = (b.height_mm, mod, desc)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(b)

    repeats = sorted([k for k in order if len(groups[k]) > 1],
                     key=lambda k: -len(groups[k]))
    singles = [k for k in order if len(groups[k]) == 1]
    for i, k in enumerate(repeats):
        suf = string.ascii_uppercase[i] if i < 26 else f"R{i + 1}"
        for b in groups[k]:
            b.tag = f"SB-{suf}"
    for i, k in enumerate(singles, start=1):
        for b in groups[k]:
            b.tag = f"SB-{i}"
    for b in plan.elec:
        if b.code == "DB":
            b.tag = "DB-1"


def rows(plan) -> list[list]:
    """One row per board TYPE, with the quantity — the same marks the drawing
    carries. Each row keeps a representative point under [6] for the symbol
    and the module count under [7] for the totals."""
    d = duties(plan)
    seen: dict = {}
    sb_rows, db_rows = [], []
    for b in _reading_order([p for p in plan.elec if p.code in ("SB", "DB")]):
        if b.tag in seen:
            seen[b.tag][5] = str(int(seen[b.tag][5]) + 1)
            continue
        desc, mod = d[id(b)]
        row = [_mark(b), "", f"{b.height_mm:g} MM",
               "-" if mod is None else f"{mod} MODULE", desc, "1", b, mod]
        seen[b.tag] = row
        (db_rows if b.code == "DB" else sb_rows).append(row)

    # the repeating types first, then the one-offs, as the reference reads
    sb_rows.sort(key=lambda r: (r[0][-1].isdigit(), r[0]))

    from collections import defaultdict
    acs = defaultdict(list)
    for p in plan.elec:
        if p.code == "AC":
            acs[p.size].append(p)
    ac_rows = []
    for i, tr in enumerate(sorted(acs), start=1):
        ps = acs[tr]
        ac_rows.append([f"AC-POINT ({i})", "", f"{ps[0].height_mm:g} MM", "-",
                        f"{tr:g} TR HIGH-WALL SPLIT — DEDICATED POINT + "
                        "ISOLATOR", str(len(ps)), ps[0], None])
    return sb_rows + ac_rows + db_rows


def _unused_type_rows(plan) -> list[list]:
    """The reference's TYPE schedule: identical boards collapsed into ONE row
    carrying a quantity, so the table says how many of each board to order
    rather than repeating the same plate twenty times.

    Naming follows the reference — a board type that repeats takes a letter
    (SB-A, SB-B …), a one-off takes a number (SB-1, SB-2 …). AC points and the
    DB follow, as they do on the reference sheet.
    """
    import string
    from collections import defaultdict

    base = rows(plan)
    sbs = [r for r in base if r[6].code == "SB"]
    dbs = [r for r in base if r[6].code == "DB"]

    groups, order = {}, []
    for r in sbs:
        key = (r[2], r[3], r[4])                  # height + module + duty
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(r)

    repeats = sorted([k for k in order if len(groups[k]) > 1],
                     key=lambda k: -len(groups[k]))
    singles = [k for k in order if len(groups[k]) == 1]

    out = []
    for i, k in enumerate(repeats):
        g = groups[k]
        sno = f"SB-{string.ascii_uppercase[i]}" if i < 26 else f"SB-R{i + 1}"
        out.append([sno, "", k[0], k[1], k[2], str(len(g)), g[0][6], g[0][7]])
    for i, k in enumerate(singles, start=1):
        g = groups[k]
        out.append([f"SB-{i}", "", k[0], k[1], k[2], "1", g[0][6], g[0][7]])

    acs = defaultdict(list)
    for p in plan.elec:
        if p.code == "AC":
            acs[p.size].append(p)
    for i, tr in enumerate(sorted(acs), start=1):
        ps = acs[tr]
        out.append([f"AC-POINT ({i})", "", f"{ps[0].height_mm:g} MM", "-",
                    f"{tr:g} TR HIGH-WALL SPLIT — DEDICATED POINT + ISOLATOR",
                    str(len(ps)), ps[0], None])
    for r in dbs:
        out.append([r[0], "", r[2], r[3], r[4], "1", r[6], None])
    return out


def totals(plan) -> tuple[int, int]:
    """(boards, modules) — the order quantity the schedule adds up to."""
    boards = mods = 0
    for r in rows(plan):
        if r[6].code != "SB":
            continue
        q = int(r[5])
        boards += q
        if r[7]:
            mods += r[7] * q
    return boards, mods


def height_for(plan) -> float:
    return 24 + 6.0 * (len(rows(plan)) + 1) + 22


def draw(dl: DrawList, plan, x: float, top: float) -> float:
    """The switchboard schedule. Returns the y of the bottom edge."""
    y = _table(dl, rows(plan), x, top, "SWITCHBOARD SCHEDULE",
               "one row per board type — the marks are the marks on the plan")
    boards, mods = totals(plan)
    y -= 8
    dl.text(x, y, f"TOTAL   {boards} switchboards   ·   {mods} modules",
            h=2.6, layer="TITLE", halign="left", bold=True)
    return y - 6


def _table(dl: DrawList, data, x: float, top: float, title: str,
           sub: str = "") -> float:
    """One schedule table with its heading. Returns the y of its bottom edge."""
    n = len(data)
    rh = 7.6                # room for a three-line duty at proper leading

    dl.text(x, top + 2, title, h=3.4, layer="TITLE",
            halign="left", bold=True)
    if sub:
        dl.text(x, top - 2.6, sub, h=2.1, layer="TEXT-SUB", halign="left")
    y = top - 7
    dl.rect(x, y - rh * (n + 1), TOTAL, rh * (n + 1), layer="TITLE")
    cx = x
    for _nm, cw in COLS[:-1]:
        cx += cw
        dl.line(cx, y - rh * (n + 1), cx, y, layer="TITLE")

    def cell(text, cxx, yy, cw, bold=False, h=2.2, max_lines=1):
        """Always inside the column rule — see draw.fit_cell."""
        lines, hh = fit_cell(text, cw - 3, h, max_lines)
        step = hh * LINE_SP
        top_ = yy - rh * 0.5 + (len(lines) - 1) * step / 2
        for li, ln in enumerate(lines):
            dl.text(cxx + 1.5, top_ - li * step, ln, h=hh,
                    layer="TITLE" if bold else "TEXT-SUB",
                    halign="left", bold=bold)

    cxx = x
    for nm, cw in COLS:
        cell(nm, cxx, y, cw, bold=True)
        cxx += cw
    dl.line(x, y - rh, x + TOTAL, y - rh, layer="TITLE")

    for i, r in enumerate(data, start=1):
        yy = y - rh * i
        cxx = x
        for ci, (val, (_nm, cw)) in enumerate(zip(r[:6], COLS)):
            if ci == 1:                       # the SYMBOL cell
                _draw_symbol(dl, r[6], cxx + cw / 2, yy - rh / 2)
            elif ci == 4:                     # the DESCRIPTION cell
                cell(val, cxx, yy, cw, h=1.9, max_lines=3)
            else:
                cell(val, cxx, yy, cw, h=2.0)
            cxx += cw
    return y - rh * (n + 1)


def _draw_symbol(dl: DrawList, b, cx: float, cy: float) -> None:
    """Drop the board's own symbol into the schedule cell, scaled to fit."""
    from . import elecsym, eleclegend

    g = eleclegend._Ghost(b.code, angle=getattr(b, "angle", 0.0))
    g.controls = getattr(b, "controls", []) or [1, 2, 3]
    cell = DrawList()
    elecsym.draw(cell, g, tag=False)
    eleclegend._place(dl, cell, cx, cy, 2.4)

