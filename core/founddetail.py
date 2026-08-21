"""Typical FOUNDATION / PLINTH SECTION detail — drawn like a proper structural
'Section A-A of stone masonry': two footings with the ground-floor build-up
spanning between them, distinct material hatches, arrow leaders and dimensions.

Standard values are used by default (editable later through the structural
questionnaire); the wall thickness and the building span come from the plan.
"""

from __future__ import annotations

import math

from .draw import Arc, DrawList
from . import section as S

MM = 304.8


def _mm(v):
    return (v or 0) / MM


def _pebbles(dl, x0, y0, x1, y1, layer):
    """Rounded-stone soling — one Hatch object (real HATCH in the DXF)."""
    if x1 <= x0 or y1 <= y0:
        return
    dl.hatch([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], kind="pebble",
             step=0.24, layer=layer)


def build(plan, params=None):
    p = params or {}
    dl = DrawList()
    L_CUT, L_SLAB, L_TXT, L_DIM = "SEC-CUT", "SEC-SLAB", "SEC-TEXT", "SEC-DIM"
    L_EARTH = "SEC-EARTH"

    # ---- values (standard defaults; overridable via the questionnaire) ----
    wall = _mm(p.get("wall_mm", 230))            # 9" wall
    pb_ht = _mm(p.get("plinth_beam_ht_mm", 455))  # plinth beam ~1'-6"
    ftg_top = _mm(p.get("ftg_top_mm", 455))       # 1'-6" at top
    ftg_base = _mm(p.get("ftg_base_mm", 610))     # 2'-0" at base
    depth = _mm(p.get("found_depth_mm", 915))     # 3'-0" below road
    pcc = _mm(p.get("pcc_mm", 100))               # 4" PCC under footing
    soling = _mm(p.get("soling_mm", 230))         # 9" stone soling
    flr_pcc = _mm(p.get("floor_pcc_mm", 100))     # 4" floor PCC
    ffl = _mm(p.get("plinth_mm", 150))            # finishing above road

    # building clear span between the two exterior walls
    xs = [w.x1 for w in plan.walls] + [w.x2 for w in plan.walls]
    span = (max(xs) - min(xs)) if xs else 20.0
    span = max(8.0, min(span, 26.0))

    xL, xR = 0.0, span                            # wall centre-lines
    gl = 0.0                                      # road / ground level

    # ---- ground line -----------------------------------------------------
    dl.line(xL - 3, gl, xR + 3, gl, layer=L_SLAB)
    dl.text(xL - 3.3, gl - 0.45, "ROAD LVL:- (0'-0\")", h=0.34, layer=L_DIM,
            halign="right")

    # ---- the two walls + plinth beams + footings -------------------------
    for x, sgn in ((xL, 1), (xR, -1)):
        wx0, wx1 = x - wall / 2, x + wall / 2
        # brick wall above FFL (broken off with a zig line at the top)
        S._cut_wall(dl, wx0, wx1, ffl, ffl + 2.4, L_CUT)
        _break(dl, wx0, wx1, ffl + 2.4, L_CUT)
        # plinth beam (RCC) at FFL
        S._rcc_band(dl, wx0, ffl - pb_ht, wx1, ffl, L_SLAB, L_CUT)
        # RR stone masonry footing, stepped/tapered, below the plinth beam
        _footing(dl, x, ffl - pb_ht, -depth, ftg_top, ftg_base, L_CUT)
        # 4" PCC under the footing
        S._pcc_band(dl, x - ftg_base / 2 - 0.15, -depth - pcc,
                    x + ftg_base / 2 + 0.15, -depth, L_SLAB, L_CUT)

    # ---- ground-floor build-up between the walls -------------------------
    g0, g1 = xL + wall / 2, xR - wall / 2
    # finishing line
    dl.line(xL, ffl, xR, ffl, layer=L_SLAB)
    S._pcc_band(dl, g0, ffl - flr_pcc, g1, ffl, L_SLAB, L_CUT)        # 4" PCC
    _cfill(dl, g0, ffl - flr_pcc - soling, g1, ffl - flr_pcc, "#eef0f4", L_CUT)
    _pebbles(dl, g0, ffl - flr_pcc - soling, g1, ffl - flr_pcc, L_CUT)  # soling
    # compacted soil ONLY in the clear span between the two footings (kept a
    # margin off each footing base + its PCC) so the earth hatch never crosses
    # the stone-masonry footing hatch. Opposite 45° + sparse.
    e0 = xL + ftg_base / 2 + 0.15 + 0.2
    e1 = xR - ftg_base / 2 - 0.15 - 0.2
    if e1 - e0 > 0.4:
        S._hatch(dl, e0, -depth, e1, ffl - flr_pcc - soling, L_EARTH,
                 step=1.3, slope=-1)

    # ---- leaders (arrow callouts, spread so nothing overlaps) ------------
    lx = xL - 3.6                              # left text column
    _cal(dl, wall / 2, ffl + 1.8, lx, ffl + 3.0, "Brick Masonry\nAS/ARCH.",
         L_TXT, right=False)
    _cal(dl, 0, ffl - pb_ht / 2, lx, ffl + 1.4, "Plinth Beam\nT.O.C. Level",
         L_TXT, right=False)
    _cal(dl, g0 + 0.4, ffl, lx, ffl - 0.2, "FINISHING\nLVL. AS/ARCH.",
         L_TXT, right=False)
    _cal(dl, xL + ftg_top / 2, -depth * 0.5, lx, -depth * 0.35,
         "RR Stone\nMasonry (1:6)", L_TXT, right=False)
    _cal(dl, xL, -depth - pcc / 2, lx, -depth - pcc / 2,
         "4\" Thk.\nP.C.C. (M15)", L_TXT, right=False)
    # floor build-up, called up / down in the middle
    mid = (g0 + g1) / 2
    _cal(dl, mid - 2, ffl - flr_pcc / 2, mid - 2, ffl + 1.6,
         "4\" Thk. P.C.C. (M15)", L_TXT, right=True, up=True)
    _cal(dl, mid + 2, ffl - flr_pcc - soling / 2, mid + 2,
         ffl - flr_pcc - soling - 1.4, "9\" Thk. Stone Soling", L_TXT,
         right=True, up=False)
    # COMPACTED SOIL — one label each side, out in the earth field, clear of
    # the footing-base dimension underneath the footing
    dl.text((e0 + xL + ftg_base / 2) / 2, -depth + 0.6, "COMPACTED\nSOIL",
            h=0.32, layer=L_TXT)
    dl.text((e1 + xR - ftg_base / 2) / 2, -depth + 0.6, "COMPACTED\nSOIL",
            h=0.32, layer=L_TXT)

    # ---- dimensions ------------------------------------------------------
    _vdim(dl, xL - 1.5, -depth, gl, "3'", L_DIM)
    _vdim(dl, xL - 6.8, -depth, ffl + 2.4, "UPTO HARD SOIL (MIN. 6'-0\")",
          L_DIM, rot=True)
    # footing base width, dimensioned BELOW the PCC so it clears the earth
    _hdim(dl, xL - ftg_base / 2, xL + ftg_base / 2, -depth - pcc - 0.6, "2'",
          L_DIM)
    # footing TOP width — witness ticks at the top corners, value tucked into
    # the clear pocket beside the (narrower) plinth beam so nothing overlaps
    yt = ffl - pb_ht
    for xx in (xL - ftg_top / 2, xL + ftg_top / 2):
        dl.line(xx, yt, xx, yt + 0.4, layer=L_DIM)
    dl.line(xL - ftg_top / 2, yt + 0.4, xL + ftg_top / 2, yt + 0.4, layer=L_DIM)
    dl.text(-(ftg_top / 2 + wall / 2) / 2, yt + 0.75, "1'-6\"", h=0.3,
            layer=L_DIM, halign="center")

    dl.text((xL + xR) / 2, -depth - 1.8, "SECTION A-A' (TYPICAL FOUNDATION)",
            h=0.6, layer=L_TXT, bold=True)
    return dl


def _cfill(dl, x0, y0, x1, y1, color, edge):
    if y1 <= y0 or x1 <= x0:
        return
    dl.fill([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], color=color,
            layer="SEC-SLAB")
    dl.rect(x0, y0, x1 - x0, y1 - y0, layer=edge)


def _break(dl, x0, x1, y, layer):
    """A little zig-zag break line at the top of a cut wall."""
    xm = (x0 + x1) / 2
    dl.line(x0, y, xm - 0.05, y + 0.12, layer=layer)
    dl.line(xm - 0.05, y + 0.12, xm + 0.05, y - 0.05, layer=layer)
    dl.line(xm + 0.05, y - 0.05, x1, y + 0.08, layer=layer)


def _footing(dl, x, y_top, y_bot, top_w, base_w, layer):
    """A tapered / stepped RR-stone-masonry footing, hatched."""
    ht = top_w / 2
    hb = base_w / 2
    pts = [(x - ht, y_top), (x + ht, y_top), (x + hb, y_bot), (x - hb, y_bot)]
    for a, b in zip(pts, pts[1:] + pts[:1]):
        dl.line(a[0], a[1], b[0], b[1], layer=layer)
    dl.fill([(px, py) for px, py in pts], color="#f5e9dc", layer="SEC-SLAB")
    # 45° stone hatch clipped to the ACTUAL trapezoid, so it never spills past
    # the sloped sides at the (narrower) top
    S._hatch_poly(dl, pts, layer, step=0.4)


def _cal(dl, px, py, tx, ty, text, layer, right=True, up=None):
    """A callout: leader from (px,py) to a text anchor, with an arrowhead."""
    dl.line(px, py, tx, ty, layer=layer)
    dl.line(tx, ty, tx + (0.5 if not right else -0.5)
            if up is None else tx, ty, layer=layer)
    S._arrowhead(dl, px, py, (1 if px < tx else -1), 0, layer)
    ax = tx + (0.6 if right else -0.6)
    for i, ln in enumerate(text.split("\n")):
        dl.text(ax, ty - i * 0.42, ln, h=0.32, layer=layer,
                halign="left" if right else "right")


def _vdim(dl, x, y0, y1, text, layer, rot=False):
    dl.line(x, y0, x, y1, layer=layer)
    for yy in (y0, y1):
        dl.line(x - 0.2, yy, x + 0.2, yy, layer=layer)
    lines = text.split("\n")
    ymid = (y0 + y1) / 2
    if rot:
        # rotated text runs ALONG the dimension line — stack the lines
        # side-by-side in X (columns), never in Y where they would overlap
        for i, ln in enumerate(lines):
            dl.text(x - 0.35 - i * 0.42, ymid, ln, h=0.34, layer=layer,
                    halign="center", angle=90)
    else:
        for i, ln in enumerate(lines):
            dl.text(x - 0.3, ymid - i * 0.42, ln, h=0.34, layer=layer,
                    halign="center")


def _hdim(dl, x0, x1, y, text, layer):
    dl.line(x0, y, x1, y, layer=layer)
    for xx in (x0, x1):
        dl.line(xx, y - 0.2, xx, y + 0.2, layer=layer)
    dl.text((x0 + x1) / 2, y - 0.45, text, h=0.34, layer=layer)
