"""Sheet composition: fit the plan on a titled, bordered sheet.

Takes the model-space DrawList (feet, y-up) and returns a sheet-space
DrawList in MILLIMETRES, y-up, plus the scale actually used.
"""

from __future__ import annotations

import math

from . import sheetformat
from .draw import DrawList, Line, Arc, Poly, Text, Fill, Hatch
from .model import Plan


def _drawing_title(plan: Plan, schedule: str) -> str:
    """What this sheet is called, on the strip."""
    base = (plan.title.plan_name or "FLOOR PLAN").upper()
    if schedule == "electrical":
        return "ELECTRICAL LAYOUT"
    if schedule == "furniture":
        return "FURNITURE LAYOUT"
    return base

SHEETS = {           # width x height in mm, landscape
    "A4": (297, 210),
    "A3": (420, 297),
    "A2": (594, 420),
    "A1": (841, 594),
}
MARGIN = 10.0
TB_H = 34.0          # title block height, mm
TB_W = 165.0         # title block width, mm
FT_MM = 304.8


def _nice_scale(raw: float) -> float:
    """Snap to a conventional architectural scale denominator."""
    for s in (20, 25, 50, 75, 100, 125, 150, 200, 250, 300, 400, 500, 750, 1000):
        if raw <= s:
            return float(s)
    return math.ceil(raw / 500.0) * 500.0


def compose(plan: Plan, dl: DrawList, sheet: str = "A3",
            orientation: str = "auto",
            schedule: str = "openings") -> tuple[DrawList, dict]:
    """`schedule` picks the table printed on this sheet:
    "openings" (the floor plan), "furniture", "electrical", or "" for none.
    Each drawing carries only the schedule that belongs to it."""
    W, H = SHEETS.get(sheet.upper(), SHEETS["A3"])

    x0, y0, x1, y1 = dl.bounds()
    pad = 0.6                                  # feet of breathing room
    x0 -= pad; y0 -= pad; x1 += pad; y1 += pad
    pw, ph = max(x1 - x0, 1e-6), max(y1 - y0, 1e-6)

    if orientation == "auto":
        orientation = "portrait" if ph > pw else "landscape"
    if orientation == "portrait":
        W, H = H, W

    # The drawing window sits above the title block and BELOW whatever table
    # this sheet carries — reserving the band is what stops the plan running
    # underneath the schedule.
    # The practice sheet puts a full-height title strip down the right, so the
    # drawing window is the area left of it. The strip carries the key plan,
    # the issue status, the legend, the revisions, the notes and the north
    # point, which is why no band has to be reserved above or below.
    band = _schedule_band(plan, schedule)      # the table above the drawing
    ax0, ay0 = MARGIN, MARGIN
    ax1, ay1 = sheetformat.drawing_right(W) - 4, H - MARGIN - band
    aw, ah = ax1 - ax0, ay1 - ay0

    raw = max(pw * FT_MM / aw, ph * FT_MM / ah)
    denom = _nice_scale(raw)
    k = FT_MM / denom                          # feet -> mm on paper

    # centre the plan in the window
    ox = ax0 + (aw - pw * k) / 2 - x0 * k
    oy = ay0 + (ah - ph * k) / 2 - y0 * k

    out = DrawList()
    for it in dl.items:
        if isinstance(it, Fill):
            out.fill([(p[0] * k + ox, p[1] * k + oy) for p in it.pts],
                     it.color, it.layer)
        elif isinstance(it, Line):
            out.line(it.x1 * k + ox, it.y1 * k + oy,
                     it.x2 * k + ox, it.y2 * k + oy, it.layer, it.dashed)
        elif isinstance(it, Poly):
            out.poly([(p[0] * k + ox, p[1] * k + oy) for p in it.pts],
                     it.layer, it.closed, it.dashed)
        elif isinstance(it, Arc):
            out.arc(it.cx * k + ox, it.cy * k + oy, it.r * k,
                    it.a1, it.a2, it.layer, it.dashed)
        elif isinstance(it, Text):
            h = max(1.6, min(4.0, it.h * k))   # keep text legible at any scale
            out.text(it.x * k + ox, it.y * k + oy, it.s, h, it.layer,
                     it.angle, it.halign, it.valign, it.bold)
        elif isinstance(it, Hatch):
            # scale the boundary AND the pattern step together so the pattern
            # keeps its density at any sheet scale — and carry the lattice
            # anchor through the same transform so the grid stays aligned
            ph = getattr(it, "phase", None)
            if ph is not None:
                ph = ph * k + (ox if it.kind == "vlines" else oy)
            out.hatch([[(p[0] * k + ox, p[1] * k + oy) for p in lp]
                       for lp in it.loops], it.kind, it.step * k, it.layer,
                      phase=ph)

    sheetformat.draw(out, plan, W, H, f"1:{int(denom)}",
                     sheet.upper(), _drawing_title(plan, schedule))
    if schedule == "openings":
        _schedule(out, plan, W, H)
        from . import wallsched
        wallsched.draw(out, plan, W, H)        # wall no · length · thickness
    elif schedule == "electrical":
        from . import eleclegend
        eleclegend.draw(out, plan, W, H)
    elif schedule == "plumbing":
        from . import plumblegend
        plumblegend.draw(out, plan, W, H)
    elif schedule == "flooring":
        from . import floorlegend
        floorlegend.draw(out, plan, W, H)

    info = {"sheet": sheet.upper(), "orientation": orientation,
            "w_mm": W, "h_mm": H, "scale": f"1:{int(denom)}", "k": k,
            # model→sheet mapping (sheet_x = model_x*k + ox, y likewise) so the
            # web UI can place interactive drag-handles exactly on each element
            "ox": ox, "oy": oy}
    return out, info


SCHED_COLS = [("MARK", 13), ("SIZE  W x H", 30), ("SILL", 13),
              ("LINTEL", 15), ("NOS", 9)]
SCHED_W = sum(c[1] for c in SCHED_COLS)


def _schedule_band(plan, schedule: str) -> float:
    """How much of the sheet's height this sheet's table takes."""
    if schedule == "openings":
        n = len(_schedule_rows(plan))
        return (4.4 * (n + 1) + 12) if n else 0.0
    return 0.0


def _legend_band(plan, schedule: str) -> float:
    """Nothing: the electrical legend lives inside the title strip's LEGEND
    panel, so it costs the drawing no space at all."""
    return 0.0


def _schedule(dl: DrawList, plan, W: float, H: float) -> None:
    """§10.5 — the door/window/ventilator schedule the rulebook requires on
    the sheet: Mark, Size W x H, Sill, Lintel, Nos."""
    rows = _schedule_rows(plan)
    if not rows:
        return

    rh = 4.4
    # inside the DRAWING window, not the sheet — the title strip owns the
    # right-hand column and nothing may run into it
    x = sheetformat.drawing_right(W) - 8 - SCHED_W
    top = H - MARGIN - 8
    dl.text(x, top + 2.0, "DOOR / WINDOW / VENTILATOR SCHEDULE", h=2.8,
            layer="TITLE", halign="left", bold=True)

    y = top
    dl.rect(x, y - rh * (len(rows) + 1), SCHED_W, rh * (len(rows) + 1),
            layer="TITLE")
    cx = x
    for _, w in SCHED_COLS[:-1]:
        cx += w
        dl.line(cx, y - rh * (len(rows) + 1), cx, y, layer="TITLE")

    def row(vals, yy, bold=False, h=2.3):
        cx = x
        for (txt, (_, w)) in zip(vals, SCHED_COLS):
            dl.text(cx + 2, yy - rh * 0.62, str(txt), h=h,
                    layer="TITLE" if bold else "TEXT-SUB",
                    halign="left", bold=bold)
            cx += w

    row([c[0] for c in SCHED_COLS], y, bold=True, h=2.2)
    dl.line(x, y - rh, x + SCHED_W, y - rh, layer="TITLE")
    for i, r in enumerate(rows, start=1):
        row(r, y - rh * i)


def _schedule_rows(plan) -> list[list[str]]:
    from . import standards as std

    order = {"single_door": 0, "double_door": 0, "sliding_door": 0,
             "door": 0, "window": 1, "vent": 2}
    seen: dict[str, list] = {}
    for o in plan.openings:
        if o.type not in order:
            continue
        tag = o.tag or o.type[0].upper()
        if tag in seen:                       # identical marks are one row
            seen[tag][4] = str(int(seen[tag][4]) + max(1, o.count))
            continue
        h = o.height_mm or std.default_height(o.type)
        kind = ""
        if o.is_door:
            if o.is_sliding:
                kind = " SLD"
            elif o.leaf_count >= 2:
                kind = " DBL"          # two leaves
        seen[tag] = [tag,
                     f"{o.width_mm:.0f} x {h:.0f}{kind}",
                     std.fmt_mm(o.sill_mm),
                     std.fmt_mm(o.lintel_mm),
                     str(max(1, o.count)),
                     order[o.type]]
    rows = sorted(seen.values(), key=lambda r: (r[5], r[0]))
    return [r[:5] for r in rows]


def _border(dl: DrawList, W: float, H: float) -> None:
    dl.rect(MARGIN / 2, MARGIN / 2, W - MARGIN, H - MARGIN, layer="TITLE")
    dl.rect(MARGIN, MARGIN, W - 2 * MARGIN, H - 2 * MARGIN, layer="TITLE")


def _title_block(dl: DrawList, plan: Plan, W: float, H: float, denom: float,
                 legend: bool = False) -> None:
    t = plan.title
    x = W - MARGIN - TB_W
    y = MARGIN
    dl.rect(x, y, TB_W, TB_H, layer="TITLE")

    rows = [
        (t.project or "PROJECT", 5.0, True),
        (t.plan_name or "FLOOR PLAN", 3.6, True),
    ]
    cy = y + TB_H - 6
    for s, h, bold in rows:
        dl.text(x + 4, cy, s.upper(), h=h, layer="TITLE",
                halign="left", bold=bold)
        cy -= h + 3.0

    dl.line(x, cy + 1.5, x + TB_W, cy + 1.5, layer="TITLE")

    cells = [
        ("PLOT", t.plot_size or "-"),
        ("SCALE", f"1:{int(denom)}"),
        ("REV", t.revision or "R0"),
        ("DATE", t.date or "-"),
    ]
    cw = TB_W / len(cells)
    for i, (k, v) in enumerate(cells):
        cx = x + i * cw
        if i:
            dl.line(cx, y, cx, cy + 1.5, layer="TITLE")
        dl.text(cx + 3, cy - 4.0, k, h=2.2, layer="TEXT-SUB", halign="left")
        dl.text(cx + 3, cy - 9.5, v, h=2.8, layer="TITLE", halign="left")

    # Notes sit outside the block, on the free strip to its left — wrapped to
    # that strip's width so they can never run under the title block. On a
    # sheet that carries the electrical legend the strip is taken, so the
    # notes shrink to the one line that matters.
    strip = x - MARGIN - 6
    from . import units as _u
    lines = _wrap(_u.relabel(t.wall_note or ""), strip, 2.6)
    lines.append("ALL DIMENSIONS IN FEET-INCHES. DO NOT SCALE THE DRAWING.")
    ty = y + TB_H - 5
    for ln in lines[:5]:
        dl.text(MARGIN + 3, ty, ln, h=2.6, layer="TEXT-SUB", halign="left")
        ty -= 4.2


def _wrap(text: str, width_mm: float, h: float) -> list[str]:
    """Greedy wrap using an average glyph width of 0.55 * cap height."""
    per = max(8, int(width_mm / (h * 0.55)))
    out, line = [], ""
    for word in (text or "").split():
        trial = (line + " " + word).strip()
        if len(trial) <= per:
            line = trial
        else:
            if line:
                out.append(line)
            line = word
    if line:
        out.append(line)
    return out
