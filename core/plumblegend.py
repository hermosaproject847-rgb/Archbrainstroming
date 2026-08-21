"""The plumbing legend, drawn inside the title strip's LEGEND panel.

The same panel the electrical legend uses, so on the PLUMBING sheet the reader
sees which colour is which system without opening Sheet 4. Each line sample is
drawn in the system's own colour and line style, so the legend can never drift
from the plan.
"""

from __future__ import annotations

from . import plumbing as P
from .draw import DrawList

# system codes in legend order, plus the point-symbol rows
_SYS_ORDER = ("CW", "HW", "SOIL", "WASTE", "VENT", "STORM", "ACD")
# short marks that appear on the plan, so the reader can decode them
_MARKS = [("NT", "Nahani trap"), ("GT", "Gully trap"),
          ("IC", "Inspection chamber"), ("CO", "Cleanout"),
          ("KH", "Khurra (spout)")]


def _dashed(system: str) -> bool:
    return P.SYSTEMS.get(system, (None, None, None, "solid"))[3] != "solid"


def draw(dl: DrawList, plan, w_mm: float, h_mm: float) -> None:
    from . import sheetformat as SF

    used = [c for c in _SYS_ORDER if any(r.system == c for r in plan.pipes)]
    if not used:
        return

    rows = [("sys", c) for c in used] + [("mark", m) for m in _MARKS]

    x0 = SF.X_STRIP * w_mm
    x1 = SF.X_R6 * w_mm
    top = SF.Y_LEGEND_TOP * h_mm
    bot = SF.Y_LEGEND_BOT * h_mm

    head = 9.0
    avail = (top - head) - bot - 2
    n = len(rows)
    row = min(5.2, avail / max(n, 1))
    sym_w = min(16.0, (x1 - x0) * 0.30)
    desc_x = x0 + sym_w + 2

    y = top - head
    dl.line(x0, y, x1, y, layer="TITLE")
    for i, (kind, item) in enumerate(rows):
        yy = y - row * i
        if i:
            dl.line(x0, yy, x1, yy, layer="TITLE")
        cy = yy - row / 2
        if kind == "sys":
            label, layer, _spec, _style = P.SYSTEMS[item]
            # a line sample in the system colour, dashed where it is dashed
            dl.line(x0 + 2, cy, x0 + sym_w - 2, cy, layer=layer,
                    dashed=_dashed(item))
            dl.text(desc_x, cy, label, h=min(2.0, row * 0.46),
                    layer="TEXT-SUB", halign="left")
        else:
            code, label = item
            dl.text(x0 + sym_w / 2, cy, code, h=min(2.2, row * 0.5),
                    layer="PLUMB-TAG", halign="center", bold=True)
            dl.text(desc_x, cy, label, h=min(2.0, row * 0.46),
                    layer="TEXT-SUB", halign="left")

    dl.line(x0 + sym_w, y, x0 + sym_w, y - row * n, layer="TITLE")
    dl.line(x0, y - row * n, x1, y - row * n, layer="TITLE")
