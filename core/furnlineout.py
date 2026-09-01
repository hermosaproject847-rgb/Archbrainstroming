"""Furniture line-out — a sheet that dimensions every furniture piece from the
walls around it, with a legend. Deterministic: distances are measured from the
piece's footprint to the nearest wall face on each side. No AI.
"""

from __future__ import annotations

import os

from .model import Plan
from .draw import DrawList
from . import engine, sheet
from . import export as EXP

MM = 304.8


def _ft_in(feet: float) -> str:
    from . import units          # feet-inch / mm / m per the chosen drawing unit
    return units.fmt_len(feet)


def _wall_faces(plan: Plan):
    """Vertical wall x-faces and horizontal wall y-faces, as (coord, lo, hi)."""
    vx, hy = [], []
    for w in plan.walls:
        th = w.thickness_in / 12.0 / 2.0
        if abs(w.x1 - w.x2) < 1e-6:                # vertical wall
            lo, hi = sorted((w.y1, w.y2))
            vx.append((w.x1 - th, lo, hi)); vx.append((w.x1 + th, lo, hi))
        elif abs(w.y1 - w.y2) < 1e-6:              # horizontal wall
            lo, hi = sorted((w.x1, w.x2))
            hy.append((w.y1 - th, lo, hi)); hy.append((w.y1 + th, lo, hi))
    return vx, hy


def _nearest(faces, coord, lo, hi, before: bool):
    """Nearest face coordinate on one side of [coord], overlapping [lo,hi]."""
    best = None
    for fc, a, b in faces:
        if min(hi, b) - max(lo, a) <= 0.2:         # must overlap the piece span
            continue
        if before and fc <= coord + 1e-6:
            if best is None or fc > best:
                best = fc
        elif not before and fc >= coord - 1e-6:
            if best is None or fc < best:
                best = fc
    return best


def _dim(dl: DrawList, x1, y1, x2, y2, text):
    """A slim dimension line with ticks and a label."""
    dl.line(x1, y1, x2, y2, layer="DIM")
    tick = 0.12
    if abs(y1 - y2) < 1e-6:                         # horizontal dim
        for xx in (x1, x2):
            dl.line(xx, y1 - tick, xx, y1 + tick, layer="DIM")
        dl.text((x1 + x2) / 2, y1 + 0.18, text, h=0.32, layer="DIM")
    else:                                          # vertical dim
        for yy in (y1, y2):
            dl.line(x1 - tick, yy, x1 + tick, yy, layer="DIM")
        dl.text(x1 + 0.18, (y1 + y2) / 2, text, h=0.32, layer="DIM", angle=90)


def build(plan: Plan) -> tuple[DrawList, list[dict]]:
    """Draw the shell + furniture + a dimension from each piece to its nearest
    walls. Returns (drawlist, legend rows)."""
    dl = engine.build(plan, wall_tags=False, furniture=True, elec=False,
                      plumb=False, floor=False, sections=False)
    vx, hy = _wall_faces(plan)
    MIN_DIM = 0.3          # ft — a gap smaller than this = "against the wall"
    legend = []
    for i, f in enumerate(plan.furniture, 1):
        tag = f.tag or f"F{i}"
        x0, y0, x1, y1 = f.x, f.y, f.x + f.w, f.y + f.h
        left = _nearest(vx, x0, y0, y1, before=True)
        right = _nearest(vx, x1, y0, y1, before=False)
        bot = _nearest(hy, y0, x0, x1, before=True)
        top = _nearest(hy, y1, x0, x1, before=False)
        cy = (y0 + y1) / 2
        cx = (x0 + x1) / 2
        dl_left = round(x0 - left, 3) if left is not None else None
        dl_right = round(right - x1, 3) if right is not None else None
        dl_bot = round(y0 - bot, 3) if bot is not None else None
        dl_top = round(top - y1, 3) if top is not None else None

        # ON THE DRAWING keep it clean: dimension to only the NEAREST wall on
        # each axis, and skip a gap that is basically zero (piece against wall).
        # The full four-side clearances still go in the legend.
        xcands = [(d, "L", left) for d in (dl_left,) if d and d >= MIN_DIM] + \
                 [(d, "R", right) for d in (dl_right,) if d and d >= MIN_DIM]
        if xcands:
            d, side, fc = min(xcands, key=lambda t: t[0])
            yline = cy
            if side == "L":
                _dim(dl, fc, yline, x0, yline, _ft_in(d))
            else:
                _dim(dl, x1, yline, fc, yline, _ft_in(d))
        ycands = [(d, "B", bot) for d in (dl_bot,) if d and d >= MIN_DIM] + \
                 [(d, "T", top) for d in (dl_top,) if d and d >= MIN_DIM]
        if ycands:
            d, side, fc = min(ycands, key=lambda t: t[0])
            xline = cx
            if side == "B":
                _dim(dl, xline, fc, xline, y0, _ft_in(d))
            else:
                _dim(dl, xline, y1, xline, fc, _ft_in(d))

        legend.append({
            "tag": tag, "kind": f.kind, "room": f.room,
            "size": f"{_ft_in(f.size_w or f.w)} x {_ft_in(f.size_h or f.h)}",
            "left": dl_left, "right": dl_right, "bot": dl_bot, "top": dl_top,
        })
    _legend(dl, plan, legend)
    return dl, legend


def _legend(dl: DrawList, plan: Plan, rows: list[dict]) -> None:
    """A legend table to the right of the plan: tag, piece, room, size, and the
    clear distance to the wall on each side."""
    if not rows:
        return
    x0, y0, x1, y1 = plan.extents()
    x = x1 + 3.0
    y = y1
    RH = 1.05
    cols = [("TAG", 2.6), ("PIECE", 6.0), ("ROOM", 5.5), ("SIZE", 4.6),
            ("L", 2.6), ("R", 2.6), ("BOT", 2.6), ("TOP", 2.6)]
    W = sum(c[1] for c in cols)
    dl.text(x, y + 1.4, "FURNITURE LINE-OUT — clearances to wall (L/R/BOT/TOP)",
            h=0.55, layer="TEXT", halign="left", bold=True)
    n = len(rows)
    dl.rect(x, y - RH * (n + 1), W, RH * (n + 1), layer="TITLE")
    cx = x
    for _lbl, w in cols[:-1]:
        cx += w
        dl.line(cx, y - RH * (n + 1), cx, y, layer="TITLE")
    dl.line(x, y - RH, x + W, y - RH, layer="TITLE")

    def put(vals, yy, bold=False):
        cx = x
        for v, (_lbl, w) in zip(vals, cols):
            dl.text(cx + 0.2, yy - RH * 0.66, str(v), h=0.42,
                    layer="TEXT" if bold else "TEXT-SUB", halign="left",
                    bold=bold)
            cx += w

    put([c[0] for c in cols], y, bold=True)
    for i, r in enumerate(rows, 1):
        d = lambda v: (_ft_in(v) if v is not None else "-")   # noqa: E731
        put([r["tag"], r["kind"], r["room"], r["size"],
             d(r["left"]), d(r["right"]), d(r["bot"]), d(r["top"])],
            y - RH * i)


def export(plan_dict: dict, folder: str, name: str) -> dict:
    """Compose the line-out sheet and write PNG + PDF + DXF."""
    plan = Plan.from_dict(plan_dict)
    dl, _rows = build(plan)
    composed, info = sheet.compose(plan, dl, "A2", "auto", schedule="")
    os.makedirs(folder, exist_ok=True)
    paths = {}
    png = os.path.join(folder, name + ".png")
    EXP.to_png(composed, info["w_mm"], info["h_mm"], png, dpi=200)
    paths["png"] = png
    try:
        pdf = os.path.join(folder, name + ".pdf")
        EXP.to_pdf(composed, info["w_mm"], info["h_mm"], pdf)
        paths["pdf"] = pdf
    except Exception:
        pass
    try:
        dxf = os.path.join(folder, name + ".dxf")
        EXP.to_dxf(composed, dxf, model_scale=info.get("k"))
        paths["dxf"] = dxf
    except Exception:
        pass
    return paths
