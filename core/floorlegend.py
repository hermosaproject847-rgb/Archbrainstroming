"""The flooring legend, in the title strip's LEGEND panel — so the flooring
sheet shows each material code, its hatch and its quantity without opening the
schedule sheet. One row per legend code actually used."""

from __future__ import annotations

from . import floorsched


def draw(dl, plan, w_mm: float, h_mm: float) -> None:
    from . import sheetformat as SF

    rows = floorsched.legend_rows(plan)     # [code, material, size, finish, …]
    if not rows:
        return
    x0 = SF.X_STRIP * w_mm
    x1 = SF.X_R6 * w_mm
    top = SF.Y_LEGEND_TOP * h_mm
    bot = SF.Y_LEGEND_BOT * h_mm

    head = 9.0
    avail = (top - head) - bot - 2
    n = len(rows)
    row = min(6.5, avail / max(n, 1))
    sym_w = min(14.0, (x1 - x0) * 0.20)
    desc_x = x0 + sym_w + 2

    y = top - head
    dl.line(x0, y, x1, y, layer="TITLE")
    for i, r in enumerate(rows):
        yy = y - row * i
        if i:
            dl.line(x0, yy, x1, yy, layer="TITLE")
        cy = yy - row / 2
        # a small hatch swatch in the material's fill
        bx0, by0 = x0 + 2, cy - row * 0.32
        bx1, by1 = x0 + sym_w - 2, cy + row * 0.32
        dl.rect(bx0, by0, bx1 - bx0, by1 - by0, layer="FLR-GRID")
        for k in range(1, 4):
            hx = bx0 + (bx1 - bx0) * k / 4
            dl.line(hx, by0, hx, by1, layer="FLR-HATCH")
        dl.text(desc_x, cy + row * 0.16, f"{r[0]}  {r[1]} {r[2]}",
                h=min(1.9, row * 0.3), layer="TEXT-SUB", halign="left")
        dl.text(desc_x, cy - row * 0.24,
                f"{r[3]} · joint {r[4]} · {r[8]} m2",
                h=min(1.6, row * 0.26), layer="TEXT-SUB", halign="left")

    dl.line(x0 + sym_w, y, x0 + sym_w, y - row * n, layer="TITLE")
    dl.line(x0, y - row * n, x1, y - row * n, layer="TITLE")
