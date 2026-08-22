"""Blown-up construction DETAILS (DETAIL AT A / B / S) drawn exactly like the
Orilite section sheet: a circled enlargement of a junction with hatched
build-up, red finish/membrane lines and blue leader labels.

 A = parapet top: brick parapet + 3" RCC coping + DPC + roof slab with
     brickbat-for-slope, water-proofing and a vata (cove) at the corner.
 B = roof-slab edge over a wall: RCC slab + brickbat slope + water-proofing,
     the wall below plastered.
 S = staircase: sloped RCC waist, brick-work step infill, 19 mm stone tread /
     riser on mortar with anti-slip grooves.

Everything is drawn at an enlarged scale (SC) so it reads next to the section;
only the wall / slab thicknesses follow the plan — the finishes are standard.
"""
from __future__ import annotations

import math

from .draw import DrawList

L_OUT = "SEC-CUT"        # black outlines
L_RED = "DET-RED"        # red finish / RCC / membrane
L_STONE = "DET-STONE"    # stone tread / riser (dark grey fill)
L_DPC = "DET-DPC"        # DPC band (grey fill)
L_LBL = "DET-LBL"        # blue labels + leaders
L_TTL = "SEC-TEXT"       # "DETAIL AT x" title


def _ring(cx, cy, r, n=64):
    return [(cx + r * math.cos(2 * math.pi * i / n),
             cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]


def _rect(dl, x, y, w, h, layer):
    dl.poly([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], layer=layer, closed=True)


def _fill_rect(dl, x, y, w, h, color, layer):
    dl.fill([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], color=color, layer=layer)


def _arrow(dl, tx, ty, ang, layer, size=0.35):
    """Arrowhead tip at (tx,ty) pointing along ang (radians)."""
    for s in (+1, -1):
        a = ang + math.pi + s * math.radians(20)
        dl.line(tx, ty, tx + size * math.cos(a), ty + size * math.sin(a), layer=layer)


def _lead(dl, tip, tx, ty, text, h, halign="left"):
    """Simple straight leader: arrow at tip, text block at (tx,ty)."""
    px, py = tip
    dl.line(px, py, tx, ty, layer=L_LBL)
    _arrow(dl, px, py, math.atan2(py - ty, px - tx), L_LBL, 0.3)
    for i, ln in enumerate(text.split("\n")):
        dl.text(tx, ty - i * (h * 1.35), ln, h=h, layer=L_LBL, halign=halign)


# ---------------------------------------------------------------- DETAIL A
def detail_A(dl: DrawList, ox, oy, sc=6.0, wall_ft=0.75):
    """Parapet top."""
    W = wall_ft * sc                         # parapet wall thickness
    Hp = 3.2 * sc / 1.0 * 0.0 + 4.0          # (kept simple) parapet height in det units
    Hp = 4.0
    slabT = 0.5 * sc                          # roof slab thickness
    slabL = 7.0                               # slab length shown (left of wall)
    cop = 0.25 * sc                           # 3" coping
    R = 7.5                                   # detail circle radius
    # internal corner at (ox, oy)
    x = ox; y = oy
    # roof slab (concrete), spanning left of the parapet
    dl.hatch([[(x - slabL, y - slabT), (x + W, y - slabT), (x + W, y), (x - slabL, y)]],
             kind="concrete", step=0.5, layer=L_OUT)
    _rect(dl, x - slabL, y - slabT, slabL + W, slabT, L_OUT)
    dl.line(x - slabL, y - slabT, x + W, y - slabT, layer=L_RED)   # red soffit finish
    # parapet wall (brick), on the slab
    dl.hatch([[(x, y), (x + W, y), (x + W, y + Hp), (x, y + Hp)]],
             kind="diag45", step=0.5, layer=L_OUT)
    _rect(dl, x, y, W, Hp, L_OUT)
    # DPC band at parapet base
    dl.fill([(x, y), (x + W, y), (x + W, y + 0.9), (x, y + 0.9)], color="#b9b9b9", layer=L_DPC)
    dl.hatch([[(x, y), (x + W, y), (x + W, y + 0.9), (x, y + 0.9)]], kind="concrete", step=0.3, layer=L_DPC)
    dl.line(x, y + 0.9, x + W, y + 0.9, layer=L_RED)
    # coping on top (concrete), slight overhang
    dl.hatch([[(x - 0.2, y + Hp), (x + W + 0.2, y + Hp), (x + W + 0.2, y + Hp + cop), (x - 0.2, y + Hp + cop)]],
             kind="concrete", step=0.4, layer=L_OUT)
    _rect(dl, x - 0.2, y + Hp, W + 0.4, cop, L_RED)
    # brickbat-for-slope wedge on the slab (thicker at the parapet)
    bb = [(x - slabL, y), (x, y), (x, y + 0.9), (x - slabL, y + 0.35)]
    dl.hatch([bb], kind="concrete", step=0.28, layer=L_OUT)
    dl.poly(bb, layer=L_OUT, closed=True)
    # water-proofing membrane (red) over the brickbat and turned up the wall
    dl.poly([(x - slabL, y + 0.4), (x, y + 0.95), (x, y + 1.7)], layer=L_RED, closed=False)
    # 18mm plaster line (thin, above)
    dl.line(x - slabL, y + 0.55, x - 0.1, y + 1.05, layer=L_RED)
    # VATA cove at the internal corner
    dl.poly([(x, y + 0.95), (x - 0.7, y + 0.55), (x, y + 0.55)], layer=L_OUT, closed=True)
    # labels
    _lead(dl, (x - 0.2, y + Hp + cop), x - slabL - 1.0, y + Hp + cop + 1.2, "18MM PLASTER\n+COLOR PAINT", 0.45)
    _lead(dl, (x + W * 0.5, y + Hp + cop * 0.5), x - slabL - 1.0, y + Hp - 0.6, "3\" THK R.C.C COPING", 0.45)
    _lead(dl, (x - 2.5, y + 0.45), x - slabL - 1.0, y + Hp - 2.0, "BRICKBAT FOR SLOPE", 0.45)
    _lead(dl, (x - 2.0, y + 0.9), x - slabL - 1.0, y + Hp - 3.4, "WATER PROOFING\nCHEMICAL", 0.45)
    _lead(dl, (x + W, y + 0.45), x + W + 2.2, y + 0.45, "DPC 9\"THICK", 0.45)
    _lead(dl, (x - 0.4, y + 0.55), x - 1.5, y - 2.0, "VATA", 0.45)
    # circle + title
    cx, cy = x - slabL * 0.35, y + Hp * 0.4
    dl.poly(_ring(cx, cy, R), layer=L_OUT, closed=True)
    dl.text(cx, cy - R - 1.3, "DETAIL AT A", h=1.1, layer=L_TTL, bold=True)
    return (cx - R, cy - R - 2.6, cx + R, cy + R)


# ---------------------------------------------------------------- DETAIL B
def detail_B(dl: DrawList, ox, oy, sc=6.0, wall_ft=0.75):
    """Roof-slab edge over a wall."""
    W = wall_ft * sc
    slabT = 0.5 * sc
    slabL = 7.0
    R = 7.5
    x = ox; y = oy
    # RCC slab (concrete), extends left, drops at the edge (over the wall)
    dl.hatch([[(x - slabL, y - slabT), (x + W, y - slabT), (x + W, y), (x - slabL, y)]],
             kind="concrete", step=0.5, layer=L_OUT)
    _rect(dl, x - slabL, y - slabT, slabL + W, slabT, L_OUT)
    dl.line(x - slabL, y - slabT, x + W, y - slabT, layer=L_RED)
    # wall below, centred under the slab edge
    dl.hatch([[(x - W, y - slabT - 4.0), (x, y - slabT - 4.0), (x, y - slabT), (x - W, y - slabT)]],
             kind="diag45", step=0.5, layer=L_OUT)
    _rect(dl, x - W, y - slabT - 4.0, W, 4.0, L_OUT)
    # brickbat slope + water-proofing + plaster on top of the slab
    dl.hatch([[(x - slabL, y), (x + W, y), (x + W, y + 0.7), (x - slabL, y + 0.35)]],
             kind="concrete", step=0.28, layer=L_OUT)
    dl.poly([(x - slabL, y + 0.35), (x + W, y + 0.7)], layer=L_OUT, closed=False)
    dl.line(x - slabL, y + 0.5, x + W, y + 0.85, layer=L_RED)      # water-proofing
    # 4" and 3" edge dims (as in the reference)
    dl.line(x + W + 0.4, y, x + W + 0.4, y + 0.7, layer=L_LBL)
    dl.text(x + W + 0.6, y + 0.35, "4\"", h=0.45, layer=L_LBL, halign="left")
    # labels
    _lead(dl, (x - 2.0, y + 0.45), x - slabL - 1.0, y + 2.2, "WATER PROOFING\nCHEMICAL", 0.45)
    _lead(dl, (x + 0.5, y + 0.6), x - 2.0, y + 3.0, "BRICKBAT FOR SLOPE", 0.45)
    _lead(dl, (x - W * 0.5, y - slabT - 2.0), x + 1.5, y - slabT - 1.5, "18MM PLASTER\n+COLOR PAINT", 0.45)
    _lead(dl, (x - W, y - slabT - 3.0), x - W - 3.0, y - slabT - 3.0, "BRICK WALL", 0.45, halign="left")
    cx, cy = x - slabL * 0.3, y - slabT * 0.5
    dl.poly(_ring(cx, cy, R), layer=L_OUT, closed=True)
    dl.text(cx, cy - R - 1.3, "DETAIL AT B", h=1.1, layer=L_TTL, bold=True)
    return (cx - R, cy - R - 2.6, cx + R, cy + R)


# ---------------------------------------------------------------- DETAIL S
def detail_S(dl: DrawList, ox, oy, sc=6.0):
    """Staircase step: sloped RCC waist + brick-work + stone tread/riser."""
    R = 7.5
    tread = 1.05 * sc / 1.0 * 0.0 + 4.0       # step run (det units)
    tread = 4.5
    rise = 3.0
    waist = 0.5 * sc                           # RCC waist thickness (perp)
    x = ox; y = oy
    # two steps, going up to the right
    steps = [(x, y), (x + tread, y + rise), (x + 2 * tread, y + 2 * rise)]
    # sloped RCC waist (two parallel red lines under the steps)
    bot = [(x - 1.0, y - waist - 1.0), (x + 2 * tread + 1.0, y + 2 * rise - waist - 1.0)]
    dl.line(bot[0][0], bot[0][1], bot[1][0], bot[1][1], layer=L_RED)
    dl.line(bot[0][0], bot[0][1] - 0.8, bot[1][0], bot[1][1] - 0.8, layer="SEC-TEXT")
    # step profile (RCC) — the zig-zag of treads & risers
    prof = []
    for i, (sx, sy) in enumerate(steps):
        prof.append((sx, sy))
        prof.append((sx + tread, sy))
        prof.append((sx + tread, sy + rise))
    # RCC body under the steps (concrete hatch), bounded by step profile and waist
    body = [steps[0]]
    for (sx, sy) in steps[1:]:
        body.append((sx, sy))
    body = [(x, y), (x + tread, y), (x + tread, y + rise), (x + 2 * tread, y + rise),
            (x + 2 * tread, y + 2 * rise)]
    poly_rcc = body + [(bot[1][0], bot[1][1]), (bot[0][0], bot[0][1])]
    dl.hatch([poly_rcc], kind="concrete", step=0.5, layer=L_OUT)
    # brick-work infill triangles above the waist, under each tread
    dl.hatch([[(x, y), (x + tread, y), (x + tread, y + rise)]], kind="diag45", step=0.45, layer=L_OUT)
    dl.hatch([[(x + tread, y + rise), (x + 2 * tread, y + rise), (x + 2 * tread, y + 2 * rise)]],
             kind="diag45", step=0.45, layer=L_OUT)
    # red outline of the RCC waist top (following the steps)
    dl.poly(body, layer=L_RED, closed=False)
    # stone tread + riser (dark grey) — a thick band over the step profile
    t = 0.45
    for (sx, sy) in [(x, y), (x + tread, y + rise)]:
        # tread band
        dl.fill([(sx - 0.3, sy), (sx + tread + 0.2, sy), (sx + tread + 0.2, sy + t),
                 (sx - 0.3, sy + t)], color="#454545", layer=L_STONE)
        # riser band
        dl.fill([(sx + tread, sy), (sx + tread + t, sy), (sx + tread + t, sy + rise),
                 (sx + tread, sy + rise)], color="#454545", layer=L_STONE)
        # anti-slip grooves near the nosing
        for g in (0.35, 0.6, 0.85):
            dl.line(sx + tread - 0.6 - g, sy + t, sx + tread - 0.6 - g, sy + t - 0.18, layer=L_RED)
    # labels
    _lead(dl, (x + tread + 0.4, y + rise + t), x + tread - 0.5, y + 2 * rise + 2.2, "MORTAR", 0.45)
    _lead(dl, (x + tread + 0.2, y + rise), x + 2 * tread + 1.5, y + 2 * rise + 1.4, "ANTI SLIP GROOVES", 0.45)
    _lead(dl, (x + tread + t, y + rise * 0.5), x + 2 * tread + 1.5, y + rise * 0.5, "19MM STONE\nR BLACK GRANITE", 0.45)
    _lead(dl, (x + tread * 0.7, y + rise * 0.2), x - 0.5, y - 3.0, "R.C.C.", 0.45)
    _lead(dl, (x + tread * 1.3, y + rise), x + tread + 0.5, y - 3.0, "BRICK WORK", 0.45)
    cx, cy = x + tread, y + rise
    dl.poly(_ring(cx, cy, R), layer=L_OUT, closed=True)
    dl.text(cx, cy - R - 1.3, "DETAIL AT S", h=1.1, layer=L_TTL, bold=True)
    return (cx - R, cy - R - 2.6, cx + R, cy + R)


def draw_details(dl: DrawList, x_left, y_top, wall_ft=0.75):
    """Lay DETAIL AT A, B, S in a row starting at (x_left, y_top-ish)."""
    gap = 4.0
    R = 7.5
    step = 2 * R + gap
    cy = y_top - R
    detail_A(dl, x_left + R + 2.0, cy, wall_ft=wall_ft)
    detail_B(dl, x_left + step + R + 2.0, cy, wall_ft=wall_ft)
    detail_S(dl, x_left + 2 * step + R + 2.0, cy)
