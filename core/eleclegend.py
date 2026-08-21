"""The electrical legend — which symbol means which item.

Printed on the electrical sheet in place of the door/window schedule, because
each drawing should carry only the table that belongs to it. Every symbol is
drawn by the SAME code that draws it on the plan, so the legend can never
drift from the drawing.
"""

from __future__ import annotations

from . import electrical as E
from . import elecsym
from .draw import DrawList

ROW_H = 5.2
W_SYM = 12.0
W_CODE = 10.0
W_DESC = 46.0
W_SPEC = 8.0          # qty column; the spec goes under the description
TOTAL = W_SYM + W_CODE + W_DESC + W_SPEC

MARGIN = 10.0
TB_W = 165.0          # the title block occupies this much of the bottom right
TB_H = 34.0

# how big a symbol is drawn in the legend box, in sheet mm
SYM_SCALE = 2.6


class _Ghost:
    """A stand-in point, so the legend calls the real symbol routine."""

    def __init__(self, code, size=0.0, angle=0.0):
        self.code = code
        self.x = 0.0
        self.y = 0.0
        self.size = size
        self.angle = angle
        self.tag = ""
        self.height_mm = 0.0
        self.controls = [1, 2, 3]
        self.visible = True


def used_codes(plan) -> list[str]:
    """The codes actually on this drawing, in legend order."""
    order = ["SL", "ASL", "PL", "CSL", "CV", "WL", "BWL", "HL", "CH", "ML",
             "STL", "TR", "CF", "EF", "AC", "SB", "DB"]
    have = {p.code for p in plan.elec if getattr(p, "visible", True)}
    return [c for c in order if c in have]


def counts(plan) -> dict:
    out: dict = {}
    for p in plan.elec:
        if getattr(p, "visible", True):
            out[p.code] = out.get(p.code, 0) + 1
    return out


def draw(dl: DrawList, plan, w_mm: float, h_mm: float) -> None:
    """The legend, inside the title strip's LEGEND panel.

    That panel exists for exactly this, so the legend never touches the
    drawing — which is what made the earlier sheets unreadable.
    """
    from . import sheetformat as SF

    codes = used_codes(plan)
    if not codes:
        return
    qty = counts(plan)

    x0 = SF.X_STRIP * w_mm
    x1 = SF.X_R6 * w_mm
    top = SF.Y_LEGEND_TOP * h_mm
    bot = SF.Y_LEGEND_BOT * h_mm

    head = 9.0                              # the panel's own title
    avail = (top - head) - bot - 2
    n = len(codes)
    row = min(ROW_H, avail / max(n, 1))
    sym_w = min(W_SYM, (x1 - x0) * 0.16)
    qty_w = 7.0
    desc_x = x0 + sym_w + 2
    qty_x = x1 - qty_w

    y = top - head
    dl.line(x0, y, x1, y, layer="TITLE")
    for i, code in enumerate(codes):
        yy = y - row * i
        desc, watt, cct, _key = E.FIXTURES[code]
        if i:
            dl.line(x0, yy, x1, yy, layer="TITLE")

        cell = DrawList()
        g = _Ghost(code, size=_legend_size(code))
        elecsym.draw(cell, g, tag=False)
        _place(dl, cell, x0 + sym_w / 2, yy - row / 2, min(SYM_SCALE, row * 0.5))

        # two lines only where the row is tall enough for them; otherwise the
        # description alone, which is what the legend is actually for
        if row >= 5.2:
            dl.text(desc_x, yy - row * 0.36, f"{code}   {desc}", h=1.9,
                    layer="TEXT-SUB", halign="left")
            dl.text(desc_x, yy - row * 0.74, _spec(code, watt, cct, plan),
                    h=1.5, layer="TEXT-SUB", halign="left")
        else:
            dl.text(desc_x, yy - row * 0.55,
                    f"{code}   {desc}", h=min(1.9, row * 0.44),
                    layer="TEXT-SUB", halign="left")
        dl.text(qty_x + qty_w / 2, yy - row * 0.55, str(qty.get(code, 0)),
                h=min(1.9, row * 0.46), layer="TEXT-SUB")

    dl.line(x0 + sym_w, y, x0 + sym_w, y - row * n, layer="TITLE")
    dl.line(qty_x, y, qty_x, y - row * n, layer="TITLE")
    dl.line(x0, y - row * n, x1, y - row * n, layer="TITLE")


def _legend_size(code: str) -> float:
    return {"CF": 1.7, "AC": 1.2, "TR": 1.6, "CV": 1.6}.get(code, 0.0)


def _spec(code, watt, cct, plan) -> str:
    if code == "CF":
        sweeps = sorted({int(p.size * 304.8) for p in plan.elec
                         if p.code == "CF" and p.size})
        s = "/".join(str(v) for v in sweeps[:3]) if sweeps else "1200"
        return f"{s} sweep, {watt} W, regulator"
    if code == "AC":
        trs = sorted({p.size for p in plan.elec if p.code == "AC" and p.size})
        return f"{'/'.join(f'{t:g}' for t in trs)} TR high-wall split"
    if code == "SB":
        return "modular, ISI, height tagged"
    if code == "DB":
        return "RCCB 30 mA, separate banks"
    if code == "EF":
        return f"{watt} W, over the wet zone"
    return f"{watt} W{', ' + cct if cct else ''}"


def _place(dl: DrawList, cell: DrawList, cx: float, cy: float,
           scale: float) -> None:
    """Drop a symbol into the legend, scaled and centred on its cell."""
    from .draw import Arc, Line, Poly, Text
    bx0, by0, bx1, by1 = cell.bounds()
    ox, oy = (bx0 + bx1) / 2, (by0 + by1) / 2
    span = max(bx1 - bx0, by1 - by0, 0.4)
    k = min(scale, (ROW_H * 0.62) / span)

    def P(x, y):
        return (cx + (x - ox) * k, cy + (y - oy) * k)

    for it in cell.items:
        if isinstance(it, Line):
            dl.line(*P(it.x1, it.y1), *P(it.x2, it.y2), it.layer, it.dashed)
        elif isinstance(it, Poly):
            dl.poly([P(*p) for p in it.pts], it.layer, it.closed, it.dashed)
        elif isinstance(it, Arc):
            ncx, ncy = P(it.cx, it.cy)
            a = dl.arc(ncx, ncy, it.r * k, it.a1, it.a2, it.layer)
            dl.items[-1].dashed = it.dashed
        elif isinstance(it, Text):
            dl.text(*P(it.x, it.y), it.s, max(1.4, it.h * k), it.layer,
                    it.angle, it.halign, it.valign, it.bold)
