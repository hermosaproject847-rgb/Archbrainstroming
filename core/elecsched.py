"""Sheet 3 — the circuit / switchboard schedule.

PART 3 of the electrical prompt: every final circuit on the DB, the fixtures
it feeds, its connected load and its protection. It answers the one question
an electrician asks the drawing — "which points are on which board" — from the
same circuit assignment the plan is numbered with, so the two cannot disagree.
"""

from __future__ import annotations

from . import electrical as E
from .draw import DrawList, LINE_SP, fit_cell
from .model import Plan

COLS = [("CKT", 12), ("BOARD / ROOM", 40), ("CONTROLS", 62),
        ("PTS", 10), ("LOAD W", 16), ("MCB", 14), ("WIRE", 20)]
TOTAL = sum(c[1] for c in COLS)

# the lighting-point schedule: which numbered light is which model, on which
# board, on which circuit
LCOLS = [("LIGHT No.", 34), ("MODEL", 46), ("BOARD", 16), ("CIRCUIT", 16)]
LTOTAL = sum(c[1] for c in LCOLS)

# the switch-loop schedule (IS 732) — see core/looping.py for the rules
SCOLS = [("SWITCH", 13), ("ROOM / DUTY", 42), ("LIGHTS CONTROLLED", 34),
         ("LOOPING SEQUENCE", 44), ("WATTAGE", 14), ("CIRCUIT", 13),
         ("WIRE", 28)]
STOTAL = sum(c[1] for c in SCOLS)

# how each fixture code reads in the CONTROLS column
_NAME = {
    "SL": "spot", "ASL": "adj. spot", "PL": "panel", "CSL": "surface light",
    "CV": "cove", "WL": "wall light", "BWL": "bedside light",
    "HL": "pendant", "CH": "chandelier", "ML": "mirror light",
    "STL": "step light", "TR": "track", "CF": "fan", "EF": "exhaust",
    "AC": "AC", "SB": "power point", "DB": "DB",
}


def _controls(pts) -> str:
    """A compact 'which fixtures' string: '4 spot, 1 fan'."""
    order, seen = [], {}
    for p in pts:
        nm = _NAME.get(p.code, p.code)
        if nm not in seen:
            seen[nm] = 0
            order.append(nm)
        seen[nm] += 1
    return ", ".join(f"{seen[n]} {n}" for n in order) or "—"


def rows(plan: Plan) -> list[list[str]]:
    out = []
    for c in plan.circuits:
        pts = [p for p in plan.elec if p.circuit == c.id]
        out.append([
            c.id,
            (c.description or ", ".join(c.rooms) or "—")[:30],
            _controls(pts),
            str(c.points),
            f"{c.load_w:.0f}",
            c.mcb or "—",
            c.wire or "—",
        ])
    return out


def _board_mark(b) -> str:
    """The board's plan mark — the same one sbsched and the drawing use."""
    if b is None:
        return "—"
    from . import sbsched
    return sbsched._mark(b)


def _ranges(nums) -> str:
    """[1,2,3,5] -> 'L1-L3, L5'."""
    nums = sorted(set(nums))
    out, i = [], 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        out.append(f"L{nums[i]}" if i == j else f"L{nums[i]}-L{nums[j]}")
        i = j + 1
    return ", ".join(out)


def lighting_rows(plan: Plan) -> list[list[str]]:
    """Every ceiling light grouped by the board and model it shares, so the
    table reads 'L1-L6 | 9 W COB spot | S.B.5 | L1'."""
    from . import engine
    from collections import defaultdict

    # each room's lighting board, by room identity
    board_of = {}
    for r in plan.rooms:
        board_of[id(r)] = next(
            (b for b in plan.elec if b.code == "SB"
             and b.height_mm == E.H_ENTRY_BOARD
             and engine._elec_room_at(plan, b) is r), None)

    groups = defaultdict(list)
    for p in plan.elec:
        if p.code not in E.LIGHT_CODES:
            continue
        r = engine._elec_room_at(plan, p)
        board = board_of.get(id(r)) if r else None
        desc, watt, _cct, _key = E.FIXTURES.get(p.code, ("light", 0, "", ""))
        try:
            no = int(p.tag.rsplit("-", 1)[-1])
        except ValueError:
            continue
        groups[(_board_mark(board), f"{watt} W {desc}",
                p.circuit or "—")].append(no)

    rows = []
    for (board, model, ckt), nos in groups.items():
        rows.append([_ranges(nos), model, board, ckt])
    rows.sort(key=lambda r: (r[2], r[0]))
    return rows


def height_for(plan: Plan) -> float:
    """Mirrors `build()` block for block. It has to: when this came out short
    the last rows ran outside the sheet border and the caption printed over
    them."""
    from . import looping, sbsched
    nb = len(sbsched.rows(plan))
    nc = len(plan.circuits)
    ln = len(lighting_rows(plan))
    sn = len(looping.rows(plan))
    return (10 + 32                          # margin + the sheet's heading
            + 7 + 7.6 * (nb + 1) + 8 + 6     # switchboard schedule + total
            + 12 + 6 + 6.2 * (nc + 1)        # circuit schedule
            + 12 + 6 + 6.2 * (ln + 1)        # lighting schedule
            + 12 + 8 + 6.2 * (sn + 1)        # switch-loop schedule
            + 10 + 5.5 + 6                   # load summary
            + 16)                            # bottom margin


def build(plan: Plan, w_mm: float, h_mm: float) -> DrawList:
    """The circuit schedule as its own sheet, matching furnsched's format."""
    dl = DrawList()
    m = 10.0
    dl.rect(m / 2, m / 2, w_mm - m, h_mm - m, layer="TITLE")
    dl.rect(m, m, w_mm - 2 * m, h_mm - 2 * m, layer="TITLE")

    t = plan.title
    dl.text(m + 4, h_mm - m - 8, (t.project or "PROJECT").upper(), h=5.0,
            layer="TITLE", halign="left", bold=True)
    dl.text(m + 4, h_mm - m - 16, "ELECTRICAL SCHEDULES  —  SHEET 3",
            h=3.6, layer="TITLE", halign="left", bold=True)
    dl.text(m + 4, h_mm - m - 23,
            "WHICH BOARD, HOW MANY MODULES, AND WHAT EACH ONE SWITCHES. "
            "RCCB 30 mA PER DB; SEPARATE LIGHTING AND POWER BANKS.", h=2.4,
            layer="TEXT-SUB", halign="left")

    x = m + 4

    # ---- the switchboard schedule, in the reference format (primary) -----
    from . import sbsched
    y = sbsched.draw(dl, plan, x, h_mm - m - 32) - 12

    dl.text(x, y + 2, "CIRCUIT SCHEDULE  —  protection", h=3.0,
            layer="TITLE", halign="left", bold=True)
    y -= 6
    rh = 6.2                # two lines of 2.4 at 1.25 leading need 5.4

    def cells(vals, cols, yy, bold=False, h=2.4, max_lines=2):
        """Every cell clipped to its own column — see draw.fit_cell. Letting a
        long value run on was what wrote one column over the next. Two lines
        are allowed before the type is stepped down, so a long control list
        stays readable instead of shrinking to nothing."""
        cx = x
        for v, (_n, cw) in zip(vals, cols):
            lines, hh = fit_cell(v, cw - 3, h, max_lines)
            step = hh * LINE_SP
            top_ = yy - rh * 0.5 + (len(lines) - 1) * step / 2
            for li, ln in enumerate(lines):
                dl.text(cx + 1.5, top_ - li * step, ln, h=hh,
                        layer="TITLE" if bold else "TEXT-SUB",
                        halign="left", bold=bold)
            cx += cw

    def row(vals, yy, bold=False):
        cells(vals, COLS, yy, bold)

    data = rows(plan)
    n = len(data)
    dl.rect(x, y - rh * (n + 1), TOTAL, rh * (n + 1), layer="TITLE")
    cx = x
    for _nm, cw in COLS[:-1]:
        cx += cw
        dl.line(cx, y - rh * (n + 1), cx, y, layer="TITLE")
    row([c[0] for c in COLS], y, bold=True)
    dl.line(x, y - rh, x + TOTAL, y - rh, layer="TITLE")
    for i, r in enumerate(data, start=1):
        row(r, y - rh * i)

    # ---- the lighting-point schedule: number -> model -> board -----------
    ldata = lighting_rows(plan)
    yy = y - rh * (n + 1) - 12
    dl.text(x, yy, "LIGHTING SCHEDULE  —  which light is on which board",
            h=3.0, layer="TITLE", halign="left", bold=True)
    ly = yy - 6
    ln = len(ldata)

    def lrow(vals, yr, bold=False):
        cells(vals, LCOLS, yr, bold)

    dl.rect(x, ly - rh * (ln + 1), LTOTAL, rh * (ln + 1), layer="TITLE")
    cx = x
    for _nm, cw in LCOLS[:-1]:
        cx += cw
        dl.line(cx, ly - rh * (ln + 1), cx, ly, layer="TITLE")
    lrow([c[0] for c in LCOLS], ly, bold=True)
    dl.line(x, ly - rh, x + LTOTAL, ly - rh, layer="TITLE")
    for i, r in enumerate(ldata, start=1):
        lrow(r, ly - rh * i)

    # ---- the switch-loop schedule (IS 732) ------------------------------
    from . import looping
    sdata = looping.rows(plan)
    sy = ly - rh * (ln + 1) - 12
    dl.text(x, sy, "SWITCH-LOOP SCHEDULE  —  phase looped switch to nearest "
                   "fitting onward", h=3.0, layer="TITLE", halign="left",
            bold=True)
    dl.text(x, sy - 4.4,
            "NEUTRAL LOOPED COMMON, NEVER THROUGH A SWITCH. JOINTS AT CEILING "
            "ROSE / JUNCTION BOX ONLY. MAX 800 W OR 10 POINTS PER SUB-CIRCUIT "
            "(IS 732).", h=2.0, layer="TEXT-SUB", halign="left")
    sy -= 8
    sn = len(sdata)

    def srow(vals, yr, bold=False):
        cells(vals, SCOLS, yr, bold, h=2.2)

    dl.rect(x, sy - rh * (sn + 1), STOTAL, rh * (sn + 1), layer="TITLE")
    cx = x
    for _nm, cw in SCOLS[:-1]:
        cx += cw
        dl.line(cx, sy - rh * (sn + 1), cx, sy, layer="TITLE")
    srow([c[0] for c in SCOLS], sy, bold=True)
    dl.line(x, sy - rh, x + STOTAL, sy - rh, layer="TITLE")
    for i, r in enumerate(sdata, start=1):
        srow(r, sy - rh * i)

    # the load summary underneath, if it was computed
    s = getattr(plan, "elec_summary", None) or {}
    yy = sy - rh * (sn + 1) - 10
    if s:
        dl.text(x, yy, "LOAD SUMMARY", h=3.0, layer="TITLE",
                halign="left", bold=True)
        yy -= 5.5
        line = (f"Connected {s.get('connected_w', 0) / 1000:.2f} kW   ·   "
                f"Demand {s.get('demand_w', 0) / 1000:.2f} kW (with diversity)"
                f"   ·   Recommended sanctioned load "
                f"{s.get('sanctioned_kw', 0):.1f} kW")
        dl.text(x, yy, line, h=2.4, layer="TEXT-SUB", halign="left")
    return dl

