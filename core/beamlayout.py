"""The BEAM LAYOUT sheet: the walls shown light, the beams over them with
numbers and sizes, and a beam schedule. Beams appear ONLY here — never on the
floor / furniture / electrical / plumbing / flooring sheets.
"""

from __future__ import annotations

from . import beams as BM
from .draw import CHAR_W, DrawList


def build(plan) -> DrawList:
    from . import engine
    dl = DrawList()
    # walls light, so the beams (blue) read on top
    wdl = DrawList()
    engine.draw_walls(plan, wdl)
    for it in wdl.items:                       # re-layer the walls to light grey
        if hasattr(it, "layer"):
            it.layer = "BEAM-WALL"
    dl.extend(wdl)
    engine.draw_rooms(plan, dl)
    engine.draw_beams(plan, dl)
    return dl


def draw_schedule(plan, x, y_top) -> DrawList:
    """A BEAM SCHEDULE table (No. | Width | Depth | Length)."""
    dl = DrawList()
    rows = BM.schedule_rows(plan)
    if not rows:
        return dl
    heads = ["BEAM", "WIDTH", "DEPTH", "LENGTH"]
    body = [[t, f"{w}", f"{d}", f"{L}"] for (t, w, d, L) in rows]
    h = 0.34
    cw = h * 0.9
    pad = 0.55
    n = len(heads)
    widths = [max([len(heads[c])] + [len(str(r[c])) for r in body]) * cw + pad
              for c in range(n)]
    total = sum(widths)
    rh = h * 2.2
    dl.text(x, y_top + 0.7, "BEAM SCHEDULE  (all sizes in mm)", h=0.42,
            layer="BEAM-TAG", bold=True)
    y = y_top
    for r, cells in enumerate([heads] + body):
        cx = x
        for c in range(n):
            dl.text(cx + 0.25, y - rh * 0.64, str(cells[c]), h=h,
                    layer="BEAM-TAG", halign="left", bold=(r == 0))
            cx += widths[c]
        if r == 0:
            dl.line(x, y - rh, x + total, y - rh, layer="BEAM-TAG")
        y -= rh
    dl.rect(x, y, total, y_top - y, layer="BEAM-TAG")
    cx = x
    for c in range(n - 1):
        cx += widths[c]
        dl.line(cx, y, cx, y_top, layer="BEAM-TAG")
    return dl


def build_sheet(plan) -> DrawList:
    """Beam layout with its schedule placed under it."""
    dl = build(plan)
    b = dl.bounds()
    sched = draw_schedule(plan, b[0], b[1] - 1.6)
    dl.extend(sched)
    return dl
