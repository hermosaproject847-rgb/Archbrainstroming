"""COLUMN LAYOUT PLAN — the building shell drawn light with every structural
column solid and tagged (C1, C2 …) plus its size, and grid dimensions on all
four sides. The setting-out plan a site engineer marks the columns from.
"""

from __future__ import annotations

from .draw import DrawList
from . import engine
from . import framingplan as FP

MM = 25.4


def build(plan, struct=None):
    dl = DrawList()
    # walls light, as a background shell
    wdl = DrawList()
    engine.draw_walls(plan, wdl)
    for it in wdl.items:
        if hasattr(it, "layer"):
            it.layer = "BEAM-WALL"
    dl.extend(wdl)

    cols = [c for c in (getattr(plan, "columns", None) or [])]
    if not cols:
        dl.text(0, 0, "No columns in the plan.", h=0.6, layer="BEAM-TAG")
        return dl

    # columns solid + tag + size
    engine.draw_columns(plan, dl)
    for c in cols:
        w_in, d_in = round(c.w * 12), round(c.h * 12)
        dl.text(c.x, c.y - c.h / 2 - 0.5, f'{w_in}"x{d_in}"', h=0.28,
                layer="COLUMNTAG")

    xs = [w.x1 for w in plan.walls] + [w.x2 for w in plan.walls]
    ys = [w.y1 for w in plan.walls] + [w.y2 for w in plan.walls]
    wx0, wy0, wx1, wy1 = min(xs), min(ys), max(xs), max(ys)

    # grid lines through the column centres, dimensioned on all four sides
    vxs = FP._with_faces(sorted({round(c.x, 2) for c in cols}), wx0, wx1)
    hys = FP._with_faces(sorted({round(c.y, 2) for c in cols}), wy0, wy1)
    # thin grid lines
    for x in vxs:
        dl.line(x, wy0 - 1.0, x, wy1 + 1.0, layer="BEAM-CL", dashed=True)
    for y in hys:
        dl.line(wx0 - 1.0, y, wx1 + 1.0, y, layer="BEAM-CL", dashed=True)
    FP._hchain(dl, vxs, wy1 + 1.6, up=True)
    FP._hchain(dl, vxs, wy0 - 1.6, up=False)
    FP._vchain(dl, hys, wx0 - 1.6, left=True)
    FP._vchain(dl, hys, wx1 + 1.6, left=False)
    FP._overall_h(dl, wx0, wx1, wy1 + 3.4)
    FP._overall_v(dl, wy0, wy1, wx0 - 3.4)

    FP._notes(dl, (wx0 + wx1) / 2 - 8, wy0 - 5.0, struct)
    return dl
