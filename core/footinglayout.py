"""FOOTING LAYOUT PLAN — an isolated footing under every column, drawn to a
standard size (larger columns get a larger pad), tagged F1, F2 …, with the
column shown solid inside and grid dimensions all round. Setting-out plan for
the excavation and footing casting.
"""

from __future__ import annotations

from .draw import DrawList
from . import engine
from . import framingplan as FP


def _ftg_size(w_in, d_in):
    """A standard square footing side (feet) by column size — schematic."""
    m = max(w_in, d_in)
    if m <= 12:
        return 4.0
    if m <= 18:
        return 4.5
    if m <= 24:
        return 5.0
    return 5.5


def build(plan, struct=None):
    dl = DrawList()
    wdl = DrawList()
    engine.draw_walls(plan, wdl)
    for it in wdl.items:
        if hasattr(it, "layer"):
            it.layer = "BEAM-WALL"
    dl.extend(wdl)

    cols = [c for c in (getattr(plan, "columns", None) or [])]
    if not cols:
        dl.text(0, 0, "No columns/footings in the plan.", h=0.6,
                layer="BEAM-TAG")
        return dl

    for i, c in enumerate(sorted(cols, key=lambda c: (-round(c.y, 1),
                                                      round(c.x, 1))), start=1):
        w_in, d_in = round(c.w * 12), round(c.h * 12)
        s = _ftg_size(w_in, d_in)
        x0, y0 = c.x - s / 2, c.y - s / 2
        # footing pad (dashed square)
        dl.rect(x0, y0, s, s, layer="BEAM", dashed=True)
        # the column solid inside
        dl.fill_rect(c.x - c.w / 2, c.y - c.h / 2, c.w, c.h,
                     color="#3a3a3a", layer="COLUMN")
        dl.rect(c.x - c.w / 2, c.y - c.h / 2, c.w, c.h, layer="COLUMN")
        # mark + size
        dl.text(c.x, c.y + s / 2 - 0.35, f"F{i}", h=0.4, layer="COLUMNTAG",
                bold=True)
        dl.text(c.x, y0 + 0.3, f"{s:.1f}'x{s:.1f}'", h=0.26, layer="COLUMNTAG")

    xs = [w.x1 for w in plan.walls] + [w.x2 for w in plan.walls]
    ys = [w.y1 for w in plan.walls] + [w.y2 for w in plan.walls]
    wx0, wy0, wx1, wy1 = min(xs), min(ys), max(xs), max(ys)
    vxs = FP._with_faces(sorted({round(c.x, 2) for c in cols}), wx0, wx1)
    hys = FP._with_faces(sorted({round(c.y, 2) for c in cols}), wy0, wy1)
    FP._hchain(dl, vxs, wy1 + 1.6, up=True)
    FP._hchain(dl, vxs, wy0 - 1.6, up=False)
    FP._vchain(dl, hys, wx0 - 1.6, left=True)
    FP._vchain(dl, hys, wx1 + 1.6, left=False)
    FP._overall_h(dl, wx0, wx1, wy1 + 3.4)
    FP._overall_v(dl, wy0, wy1, wx0 - 3.4)
    FP._notes(dl, (wx0 + wx1) / 2 - 8, wy0 - 5.0, struct)
    return dl
