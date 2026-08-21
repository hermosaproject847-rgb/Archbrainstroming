"""FOOTING DETAILS — every isolated RCC pad footing type drawn as a PLAN (the
pad with the column and the reinforcement mesh) and a SECTION (the pad on its
PCC blinding over hard rock, the column rising out of it, the main / distribution
bars and binder). Schematic to the standard drafting format — the pad size and
bars follow a rule from the column size, not a bearing-capacity analysis.
"""

from __future__ import annotations

from .draw import Arc, DrawList
from . import section as S
from . import framingplan as FP
from . import footinglayout as FL

L_CUT, L_SLAB, L_BAR, L_TXT, L_DIM, L_EARTH = \
    "SEC-CUT", "SEC-SLAB", "FLR-START", "SEC-TEXT", "SEC-DIM", "SEC-EARTH"


def _ftin(ft):
    ft = abs(ft)
    f = int(ft)
    inch = round((ft - f) * 12)
    if inch == 12:
        f, inch = f + 1, 0
    return f"{f}'-{inch}\"" if inch else f"{f}'"


def _depth_ft(ftg_ft):
    return 1.5 if ftg_ft <= 4.0 else (1.75 if ftg_ft <= 4.5 else 2.0)


CELL_W = 18.0
CELL_H = 22.5
COLS = 2


def _one(dl, ox, oy, mark, ftg_ft, cw_in, cd_in, struct):
    """PLAN (top) + SECTION (below), top-left of the cell at (ox, oy)."""
    st = struct or {}
    pad = 6.0                                   # drawn pad width (uniform)
    cw = pad * (cw_in / 12.0) / ftg_ft          # column drawn width
    cd = pad * (cd_in / 12.0) / ftg_ft

    # ================= PLAN =================
    px, py = ox + 2.0, oy - 1.0                  # pad top-left
    dl.rect(px, py - pad, pad, pad, layer=L_CUT)                     # pad
    ccx, ccy = px + pad / 2, py - pad / 2
    dl.fill_rect(ccx - cw / 2, ccy - cd / 2, cw, cd, "#3a3a3a", L_CUT)
    dl.rect(ccx - cw / 2, ccy - cd / 2, cw, cd, layer=L_CUT)
    # reinforcement mesh — bars both ways
    for i in range(1, 8):
        gx = px + pad * i / 8
        dl.line(gx, py - pad + 0.3, gx, py - 0.3, layer=L_BAR)
        gy = py - pad + pad * i / 8
        dl.line(px + 0.3, gy, px + pad - 0.3, gy, layer=L_BAR)
    dl.line(ccx + cw, ccy, ccx + cw + 1.0, ccy + 1.0, layer=L_BAR)
    dl.text(ccx + cw + 1.1, ccy + 1.0, f'#12@6"C/C\n(MAIN & DIST.)', h=0.28,
            layer=L_BAR, halign="left")
    # pad dims
    dl.line(px, py + 0.4, px + pad, py + 0.4, layer=L_DIM)
    for xx in (px, px + pad):
        dl.line(xx, py + 0.25, xx, py + 0.55, layer=L_DIM)
    dl.text(ccx, py + 0.65, _ftin(ftg_ft), h=0.3, layer=L_DIM)
    dl.text(px - 0.4, ccy, _ftin(ftg_ft), h=0.3, layer=L_DIM, angle=90)
    dl.text(ccx, py - pad - 0.6, f"PLAN — {mark}", h=0.34, layer=L_TXT,
            bold=True)

    # ================= SECTION =================
    sy = oy - 12.5                               # section reference (pad top)
    depth = _depth_ft(ftg_ft)
    pcc = 0.5
    sx0, sx1 = ox + 1.0, ox + 1.0 + pad + 1.4    # pad base a touch wider
    pad_t = 1.1                                  # drawn pad thickness
    # hard rock line + earth hatch below
    dl.line(sx0 - 1.0, sy - pad_t - pcc, sx1 + 1.0, sy - pad_t - pcc,
            layer=L_CUT)
    for gx in [sx0 - 0.7 + 0.6 * i for i in range(int((sx1 - sx0 + 2) / 0.6))]:
        dl.line(gx, sy - pad_t - pcc, gx - 0.25, sy - pad_t - pcc - 0.35,
                layer=L_EARTH)
    dl.text((sx0 + sx1) / 2, sy - pad_t - pcc - 0.7, "HARD ROCK", h=0.3,
            layer=L_TXT)
    # PCC blinding
    S._pcc_band(dl, sx0 - 0.2, sy - pad_t - pcc, sx1 + 0.2, sy - pad_t,
                L_SLAB, L_CUT)
    # RCC pad
    S._fill_band(dl, sx0, sy - pad_t, sx1, sy, L_SLAB)
    dl.rect(sx0, sy - pad_t, sx1 - sx0, pad_t, layer=L_CUT)
    # column rising from the pad, broken at top
    colw = (sx1 - sx0) * 0.28
    cx0 = (sx0 + sx1) / 2 - colw / 2
    S._cut_wall(dl, cx0, cx0 + colw, sy, sy + 3.0, L_CUT)
    by = sy + 3.0                                # zigzag break at the column top
    dl.line(cx0, by, cx0 + colw * 0.4, by + 0.15, layer=L_CUT)
    dl.line(cx0 + colw * 0.4, by + 0.15, cx0 + colw * 0.6, by - 0.15,
            layer=L_CUT)
    dl.line(cx0 + colw * 0.6, by - 0.15, cx0 + colw, by, layer=L_CUT)
    # rebar: L-bars off the pad bottom, main mesh + column dowels
    for bx in (sx0 + 0.35, sx1 - 0.35):
        dl.line(bx, sy - 0.25, bx, sy + 2.6, layer=L_BAR)            # dowel up
        dl.line(bx, sy - 0.25, bx + (0.6 if bx < cx0 else -0.6), sy - 0.25,
                layer=L_BAR)
    dl.line(sx0 + 0.3, sy - pad_t + 0.25, sx1 - 0.3, sy - pad_t + 0.25,
            layer=L_BAR)                                            # main mat
    # callouts
    dl.line(sx1 - 0.35, sy + 1.2, sx1 + 1.2, sy + 1.6, layer=L_BAR)
    dl.text(sx1 + 1.3, sy + 1.6, "COLUMN DOWELS\n(REFER COL. SCH.)", h=0.26,
            layer=L_BAR, halign="left")
    dl.line((sx0 + sx1) / 2, sy - pad_t + 0.25, (sx0 + sx1) / 2 - 2.2,
            sy - pad_t - 1.0, layer=L_BAR)
    dl.text((sx0 + sx1) / 2 - 2.3, sy - pad_t - 1.0, '#12@6"C/C MAIN',
            h=0.26, layer=L_BAR, halign="right")
    dl.text(sx0 - 0.2, sy - pad_t - pcc / 2, '4" THK\nP.C.C. 1:3:6', h=0.26,
            layer=L_TXT, halign="right")
    # depth dim
    dl.line(sx1 + 1.6, sy, sx1 + 1.6, sy - pad_t - pcc, layer=L_DIM)
    for yy in (sy, sy - pad_t - pcc):
        dl.line(sx1 + 1.45, yy, sx1 + 1.75, yy, layer=L_DIM)
    dl.text(sx1 + 1.9, sy - (pad_t + pcc) / 2, _ftin(depth), h=0.3,
            layer=L_DIM, angle=90)
    dl.text((sx0 + sx1) / 2, sy - pad_t - pcc - 1.3, f"SECTION — {mark}",
            h=0.34, layer=L_TXT, bold=True)


def build(plan, struct=None):
    dl = DrawList()
    cols = [c for c in (getattr(plan, "columns", None) or [])]
    if not cols:
        dl.text(0, 0, "No columns/footings in the plan.", h=0.6, layer=L_TXT)
        return dl
    # group columns into footing TYPES by their pad size
    types = {}
    for c in cols:
        cw_in, cd_in = round(c.w * 12), round(c.h * 12)
        s = FL._ftg_size(cw_in, cd_in)
        types.setdefault(round(s, 2), (cw_in, cd_in))
    ordered = sorted(types.items())              # small → large
    for i, (s, (cw_in, cd_in)) in enumerate(ordered):
        r, cix = divmod(i, COLS)
        ox = cix * (CELL_W + 3.0)
        oy = -r * (CELL_H + 2.0)
        _one(dl, ox, oy, f"F{i+1}", s, cw_in, cd_in, struct)
    # notes below
    rows = (len(ordered) + COLS - 1) // COLS
    FP._notes(dl, 0, -rows * (CELL_H + 2.0) - 0.5, struct)
    return dl
