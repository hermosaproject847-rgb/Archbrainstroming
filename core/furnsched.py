"""Sheet 2 — the furniture schedule.

STEP 5 of the master prompt: every piece, its size, and its clear distance from
ALL FOUR wall faces, computed from the same footprints the drawing uses so the
two can never disagree.
"""

from __future__ import annotations

from shapely.geometry import box

from . import furniture as F
from .draw import DrawList, fit_cell
from .model import Plan

COLS = [("TAG", 12), ("PIECE", 34), ("ROOM", 26), ("SIZE", 26),
        ("N", 15), ("S", 15), ("E", 15), ("W", 15), ("VAASTU", 22)]


def _ft(v: float) -> str:
    """Feet-inches, to the nearest half inch (REV 2)."""
    if v is None:
        return "—"
    neg = v < 0
    v = abs(v)
    ft = int(v)
    inch = (v - ft) * 12
    half = round(inch * 2) / 2
    if half >= 12:
        ft, half = ft + 1, 0
    s = f"{ft}'-{half:g}\""
    return ("-" + s) if neg else s


def distances(plan: Plan, f) -> dict:
    """Clear distance from the piece to each of its room's wall faces."""
    room = plan.room(f.room)
    if room is None:
        return {}
    from . import engine
    solid = engine.wall_solid(plan)
    rb = box(room.x, room.y, room.x + room.w, room.y + room.h)
    clear = rb.difference(solid) if not solid.is_empty else rb
    if clear.is_empty:
        return {}
    if clear.geom_type == "MultiPolygon":
        clear = max(clear.geoms, key=lambda g: g.area)
    x0, y0, x1, y1 = clear.bounds
    return {"W": f.x - x0, "S": f.y - y0,
            "E": x1 - (f.x + f.w), "N": y1 - (f.y + f.h)}


def rows(plan: Plan) -> list[list[str]]:
    out = []
    for f in plan.furniture:
        d = distances(plan, f)
        out.append([
            f.tag or "",
            F.LABEL.get(f.kind, f.kind.replace("_", " ").upper()),
            f.room or "",
            f"{_ft(f.w)} x {_ft(f.h)}",
            _ft(d.get("N")), _ft(d.get("S")),
            _ft(d.get("E")), _ft(d.get("W")),
            f.verdict or "n/a",
        ])
    return out


def height_for(plan: Plan) -> float:
    """How tall the schedule sheet needs to be — no more. A fixed A3 leaves
    two thirds of the sheet blank beside the drawings."""
    n = len(plan.furniture)
    dev = sum(1 for f in plan.furniture if f.verdict == "DEVIATES")
    return 32 + 5.0 * (n + 1) + 10 + 5.5 + max(1, dev) * 4.5 + 14 + 20


def build(plan: Plan, w_mm: float, h_mm: float) -> DrawList:
    """The schedule as its own sheet."""
    dl = DrawList()
    m = 10.0
    dl.rect(m / 2, m / 2, w_mm - m, h_mm - m, layer="TITLE")
    dl.rect(m, m, w_mm - 2 * m, h_mm - 2 * m, layer="TITLE")

    t = plan.title
    dl.text(m + 4, h_mm - m - 8, (t.project or "PROJECT").upper(), h=5.0,
            layer="TITLE", halign="left", bold=True)
    dl.text(m + 4, h_mm - m - 16, "FURNITURE SCHEDULE  —  SHEET 2", h=3.6,
            layer="TITLE", halign="left", bold=True)
    dl.text(m + 4, h_mm - m - 23,
            "CLEAR DISTANCE TO EACH WALL FACE OF THE ROOM. "
            "FURNITURE SIZES ARE INDICATIVE — CONFIRM ACTUAL PIECES BEFORE "
            "ORDERING.", h=2.4, layer="TEXT-SUB", halign="left")

    total = sum(c[1] for c in COLS)
    x = m + 4
    y = h_mm - m - 32
    rh = 5.0

    def row(vals, yy, bold=False):
        cx = x
        for v, (_n, cw) in zip(vals, COLS):
            # clipped to its own column — a long piece name used to run over
            # the next heading
            lines, hh = fit_cell(v, cw - 3, 2.4, 1)
            dl.text(cx + 1.5, yy - rh * 0.62, lines[0], h=hh,
                    layer="TITLE" if bold else "TEXT-SUB",
                    halign="left", bold=bold)
            cx += cw

    data = rows(plan)
    n = len(data)
    dl.rect(x, y - rh * (n + 1), total, rh * (n + 1), layer="TITLE")
    cx = x
    for _nm, cw in COLS[:-1]:
        cx += cw
        dl.line(cx, y - rh * (n + 1), cx, y, layer="TITLE")
    row([c[0] for c in COLS], y, bold=True)
    dl.line(x, y - rh, x + total, y - rh, layer="TITLE")
    for i, r in enumerate(data, start=1):
        row(r, y - rh * i)

    # the deviations the layout had to accept
    dev = [f for f in plan.furniture if f.verdict == "DEVIATES"]
    yy = y - rh * (n + 1) - 10
    dl.text(x, yy, "VAASTU DEVIATIONS", h=3.0, layer="TITLE",
            halign="left", bold=True)
    yy -= 5.5
    if not dev:
        dl.text(x, yy, "None — every piece complies.", h=2.4,
                layer="TEXT-SUB", halign="left")
    else:
        for i, f in enumerate(dev, start=1):
            dl.text(x, yy, f"VD{i}   {f.tag}  {f.kind.replace('_', ' ')} in "
                           f"{f.room} — {f.reason}", h=2.4,
                    layer="TEXT-SUB", halign="left")
            yy -= 4.5
    yy -= 3
    dl.text(x, yy, "Vaastu Shastra is traditional practice, not building "
                   "code; it never overrides safety, egress or ergonomics.",
            h=2.3, layer="TEXT-SUB", halign="left")
    return dl
