"""BEAM DETAILS sheet — every beam drawn as a longitudinal reinforcement
elevation, the way a structural consultant details it: the beam between its two
column supports, the top and bottom bars (continuous + extra/curtailed), the
stirrup zones coded R1..R6 (see the RING DETAILS table), the clear span, and the
beam name with its size. A schematic to the real drafting FORMAT — the bar
choice follows a standard rule from the beam depth, not a full analysis.
"""

from __future__ import annotations

import re

from .draw import Arc, DrawList
from . import framingplan as FP

MM = 25.4


def _numkey(tag):
    m = re.search(r"(\d+)", tag or "")
    return (int(m.group(1)) if m else 0, tag or "")


def _rebar(depth_mm):
    """Standard bar arrangement by beam depth — matches how the reference set
    reinforces shallow hidden beams vs full-depth beams."""
    d_in = depth_mm / MM
    if d_in <= 8:                      # hidden / shallow beam (HB)
        return {"top": "2#12 (Cont.)", "top_ext": None,
                "bot": "2#12 (Cont.)", "bot_ext": None, "stir": '8MM @ 6" C/C'}
    if d_in <= 15:
        return {"top": "2#16 (Cont.)", "top_ext": "1#12 (Ext.)",
                "bot": "2#16 (Cont.)", "bot_ext": "1#16 (Ext.)",
                "stir": '8MM @ 8" C/C'}
    return {"top": "2#20 (Cont.)", "top_ext": "1#16 (Ext.)",
            "bot": "2#20+1#16 (Cont.)", "bot_ext": "1#16 (Ext.)",
            "stir": '8MM @ 8" C/C'}


def _ftin(ft):
    ft = abs(ft)
    f = int(ft)
    inch = round((ft - f) * 12)
    if inch == 12:
        f, inch = f + 1, 0
    return f"{f}'-{inch}\"" if inch else f"{f}'"


CELL_W = 15.0        # drawing units (feet) per beam cell
CELL_H = 6.2
GAP_X = 4.0
GAP_Y = 2.2
COLS = 3


def _one(dl, b, ox, oy, struct):
    """One beam elevation, its centre-line at (ox+.., oy)."""
    L_BEAM, L_BAR, L_TXT, L_DIM = "BEAM", "FLR-START", "BEAM-TAG", "SEC-DIM"
    Lb = b.length                      # true span (feet)
    draw = CELL_W - 3.0                # uniform drawn length, real span noted
    x0, x1 = ox + 1.2, ox + 1.2 + draw
    hb = 1.1                           # drawn beam depth (schematic)
    yt, yb = oy + hb / 2, oy - hb / 2
    w_in = round(b.width_mm / MM)
    d_in = round(b.depth_mm / MM)
    rb = _rebar(b.depth_mm)

    # ---- column supports at each end (a small hatched stub) --------------
    cs = 0.55
    for xe in (x0, x1):
        dl.rect(xe - cs / 2, yb - 0.7, cs, hb + 1.4, layer=L_BEAM)
        for gy in (yb - 0.7, oy, yt + 0.7):
            dl.line(xe - cs / 2, gy, xe + cs / 2, gy - 0.18, layer=L_TXT)

    # ---- the beam outline ------------------------------------------------
    dl.rect(x0, yb, x1 - x0, hb, layer=L_BEAM)

    # ---- top bar (continuous) + extra bars over the supports -------------
    dl.line(x0, yt - 0.16, x1, yt - 0.16, layer=L_BAR)
    dl.text((x0 + x1) / 2, yt + 0.95, rb["top"], h=0.3, layer=L_BAR)
    dl.line((x0 + x1) / 2, yt + 0.8, (x0 + x1) / 2, yt - 0.16, layer=L_BAR)
    if rb["top_ext"]:
        ext = draw * 0.28
        for sx, d in ((x0, 1), (x1, -1)):
            dl.line(sx, yt - 0.3, sx + d * ext, yt - 0.3, layer=L_BAR,
                    dashed=True)
        dl.text(x0 + ext / 2, yt + 0.45, rb["top_ext"], h=0.26, layer=L_BAR)
        dl.text(x0 + ext, yt + 0.2, _ftin(Lb * 0.28), h=0.24, layer=L_DIM)

    # ---- bottom bar (continuous) + extra at mid --------------------------
    dl.line(x0, yb + 0.16, x1, yb + 0.16, layer=L_BAR)
    dl.text((x0 + x1) / 2, yb - 0.95, rb["bot"], h=0.3, layer=L_BAR)
    dl.line((x0 + x1) / 2, yb - 0.8, (x0 + x1) / 2, yb + 0.16, layer=L_BAR)
    if rb["bot_ext"]:
        emid = draw * 0.5
        cx = (x0 + x1) / 2
        dl.line(cx - emid / 2, yb + 0.32, cx + emid / 2, yb + 0.32,
                layer=L_BAR, dashed=True)
        dl.text(cx, yb - 0.5, rb["bot_ext"], h=0.26, layer=L_BAR)

    # ---- stirrup zones R1 (supports) · R3 (mid) --------------------------
    zy = yb - 1.35
    z = draw * 0.22
    zones = [(x0, x0 + z, "R1"), (x0 + z, x1 - z, "R3"), (x1 - z, x1, "R1")]
    for za, zb, tag in zones:
        dl.line(za, zy + 0.18, zb, zy + 0.18, layer=L_DIM)
        dl.line(za, zy, za, zy + 0.36, layer=L_DIM)
        dl.line(zb, zy, zb, zy + 0.36, layer=L_DIM)
        dl.text((za + zb) / 2, zy - 0.1, tag, h=0.28, layer=L_DIM, bold=True)

    # ---- clear span dimension --------------------------------------------
    sy = zy - 0.7
    dl.line(x0, sy, x1, sy, layer=L_DIM)
    for xe in (x0, x1):
        dl.line(xe, sy - 0.18, xe, sy + 0.18, layer=L_DIM)
    dl.text((x0 + x1) / 2, sy - 0.42, _ftin(Lb), h=0.3, layer=L_DIM)

    # ---- name + size ------------------------------------------------------
    dl.text((x0 + x1) / 2, sy - 1.15, f'{b.tag}  ({w_in}"X{d_in}")  '
            f'STIRRUP {rb["stir"]}', h=0.34, layer=L_TXT, bold=True)


def build(plan, struct=None):
    """The whole BEAM DETAILS sheet."""
    dl = DrawList()
    beams = sorted([b for b in (getattr(plan, "beams", None) or [])
                    if b.length > 0.3], key=lambda b: _numkey(b.tag))
    if not beams:
        dl.text(0, 0, "No beams — run Beam Layout first.", h=0.6,
                layer="BEAM-TAG")
        return dl
    for i, b in enumerate(beams):
        r, c = divmod(i, COLS)
        ox = c * (CELL_W + GAP_X)
        oy = -r * (CELL_H + GAP_Y)
        _one(dl, b, ox, oy, struct)

    # RING DETAILS table under the grid, on the left
    rows = (len(beams) + COLS - 1) // COLS
    ytab = -rows * (CELL_H + GAP_Y) - 1.0
    FP.ring_table(dl, 0, ytab)
    # notes to its right
    FP._notes(dl, CELL_W + GAP_X, ytab + 0.5, struct)
    return dl
