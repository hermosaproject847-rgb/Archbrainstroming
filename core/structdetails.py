"""Typical structural section details drawn to the standard drafting format:
a slab section, a staircase section, and a terrace/parapet section — each with
the concrete outline, the reinforcement (as bars + callouts) and dimensions.
Schematic typical details (standard bar rules), not a full analysis.
"""

from __future__ import annotations

from .draw import Arc, DrawList
from . import section as S

L_CUT, L_SLAB, L_BAR, L_TXT, L_DIM = \
    "SEC-CUT", "SEC-SLAB", "FLR-START", "SEC-TEXT", "SEC-DIM"


def _cal(dl, px, py, tx, ty, text, h=0.32):
    dl.line(px, py, tx, ty, layer=L_DIM)
    dl.items.append(Arc(px, py, 0.05, 0, 360, L_BAR))
    dl.text(tx + (0.2 if tx >= px else -0.2), ty, text, h=h, layer=L_TXT,
            halign="left" if tx >= px else "right")


def _hdim(dl, x0, x1, y, text):
    dl.line(x0, y, x1, y, layer=L_DIM)
    for x in (x0, x1):
        dl.line(x, y - 0.15, x, y + 0.15, layer=L_DIM)
    dl.text((x0 + x1) / 2, y - 0.4, text, h=0.3, layer=L_DIM)


def _vdim(dl, x, y0, y1, text):
    dl.line(x, y0, x, y1, layer=L_DIM)
    for y in (y0, y1):
        dl.line(x - 0.15, y, x + 0.15, y, layer=L_DIM)
    dl.text(x - 0.35, (y0 + y1) / 2, text, h=0.3, layer=L_DIM, angle=90)


# --------------------------------------------------------------- slab section
def slab_section(plan, struct=None):
    from . import framingplan as FP
    st = struct or plan.__dict__.get("struct") or {}

    dl = DrawList()
    span = 12.0                    # drawn span between two supports
    th = 1.0                       # drawn slab thickness (schematic)
    bw, bd = 1.4, 2.2              # support beam width/depth
    x0, x1 = 0.0, span
    yt = 0.0                       # slab top
    yb = yt - th

    # two support beams
    for xc in (x0, x1):
        S._fill_band(dl, xc - bw / 2, yb - bd, xc + bw / 2, yb, L_SLAB)
        dl.rect(xc - bw / 2, yb - bd, bw, bd, layer=L_CUT)
    # slab band
    S._fill_band(dl, x0 - bw / 2, yb, x1 + bw / 2, yt, L_SLAB)
    dl.line(x0 - bw / 2, yt, x1 + bw / 2, yt, layer=L_CUT)
    dl.line(x0 - bw / 2, yb, x1 + bw / 2, yb, layer=L_CUT)

    # bottom (main) bars — straight, near the soffit
    for i in range(1, 13):
        bx = x0 + span * i / 13
        dl.items.append(Arc(bx, yb + 0.18, 0.06, 0, 360, L_BAR))
    dl.line(x0 + 0.4, yb + 0.18, x0 + 0.4, yb - 1.3, layer=L_BAR)
    dl.text(x0 + 0.4, yb - 1.5, f"MAIN {FP._s(st,'slab_main')} (BOT)", h=0.3,
            layer=L_BAR)
    # top bars — over the supports, cranked down into the span (negative steel)
    for xc, d in ((x0, 1), (x1, -1)):
        a, b = xc, xc + d * span * 0.3
        lo, hi = sorted((a, b))
        dl.line(lo, yt - 0.16, hi, yt - 0.16, layer=L_BAR)
    dl.line(x1 - 0.4, yt - 0.16, x1 - 0.4, yt + 1.3, layer=L_BAR)
    dl.text(x1 - 0.4, yt + 1.5, f"TOP {FP._s(st,'slab_main')} @ SUPPORTS",
            h=0.3, layer=L_BAR)
    # distribution note
    dl.text((x0 + x1) / 2, yb - 0.5, f"DIST. {FP._s(st,'slab_dist')}", h=0.3,
            layer=L_TXT)

    _vdim(dl, x0 - bw / 2 - 0.9, yb, yt, f"D={FP._s(st,'slab_depth')}")
    _hdim(dl, x0, x1, yb - bd - 0.8, "CLEAR SPAN (AS PLAN)")
    dl.text((x0 + x1) / 2, yb - bd - 1.8, "TYPICAL SLAB SECTION DETAIL",
            h=0.5, layer=L_TXT, bold=True)
    return dl


# ------------------------------------------------------------- staircase section
def staircase(plan, struct=None):
    from . import framingplan as FP
    st = struct or plan.__dict__.get("struct") or {}
    dl = DrawList()

    import math
    n = 10
    tread, rise = 1.0, 0.6         # drawn tread/riser
    waist = 0.55
    x, y = 0.0, 0.0
    ang = math.atan2(n * rise, n * tread)
    dxn, dyn = math.sin(ang) * waist, -math.cos(ang) * waist
    x_end, y_end = x + n * tread, y + n * rise
    # the stepped top profile
    px, py = x, y
    for i in range(n):
        dl.line(px, py, px + tread, py, layer=L_CUT)              # tread
        dl.line(px + tread, py, px + tread, py + rise, layer=L_CUT)   # riser
        px, py = px + tread, py + rise
    # soffit (inclined waist)
    dl.line(x + dxn, y + dyn, x_end + dxn, y_end + dyn, layer=L_CUT)
    dl.line(x, y, x + dxn, y + dyn, layer=L_CUT)
    dl.line(x_end, y_end, x_end + dxn, y_end + dyn, layer=L_CUT)
    S._hatch_poly(dl, [(x, y), (x_end, y_end), (x_end + dxn, y_end + dyn),
                       (x + dxn, y + dyn)], L_SLAB, step=0.5, slope=1)

    # main bars along the waist + distribution
    dl.line(x + dxn * 0.6, y + dyn * 0.6, x_end + dxn * 0.6, y_end + dyn * 0.6,
            layer=L_BAR)
    dl.text((x + x_end) / 2 + 1.0, (y + y_end) / 2 - 1.2,
            'MAIN 12MM @ 6" C/C', h=0.3, layer=L_BAR)
    dl.text((x + x_end) / 2 + 1.0, (y + y_end) / 2 - 1.7,
            f"DIST. {FP._s(st,'slab_dist')}", h=0.3, layer=L_BAR)
    dl.text(x - 0.2, y_end + 1.0, f'WAIST SLAB {FP._s(st,"slab_depth")} THK',
            h=0.3, layer=L_TXT, halign="left")
    _hdim(dl, x, x_end, y - 1.6, "GOING (AS PLAN)")
    dl.text((x + x_end) / 2, y - 2.6, "TYPICAL STAIRCASE SECTION",
            h=0.5, layer=L_TXT, bold=True)
    return dl


# --------------------------------------------------------------- terrace section
def terrace(plan, struct=None):
    from . import framingplan as FP
    st = struct or plan.__dict__.get("struct") or {}
    dl = DrawList()

    x0, x1 = 0.0, 12.0
    yt = 0.0
    slab = 1.0
    # RCC roof slab
    S._fill_band(dl, x0, yt - slab, x1, yt, L_SLAB)
    dl.rect(x0, yt - slab, x1 - x0, slab, layer=L_CUT)
    # screed to slope + brickbat coba (waterproofing) as a thin band on top
    dl.line(x0, yt + 0.05, x1, yt + 0.45, layer=L_CUT)     # slope
    S._hatch(dl, x0, yt, x1, yt + 0.45, L_SLAB, step=0.35)
    dl.text((x0 + x1) / 2, yt + 0.8, "BRICK-BAT COBA W/PROOFING + SCREED "
            "TO SLOPE", h=0.28, layer=L_TXT)
    # parapet wall at the right end
    pw, ph = 0.6, 3.0
    S._cut_wall(dl, x1 - pw, x1, yt, yt + ph, L_CUT)
    S._fill_band(dl, x1 - pw - 0.15, yt + ph, x1 + 0.15, yt + ph + 0.3, L_SLAB)
    dl.text(x1 - pw - 0.3, yt + ph + 0.6, "R.C.C. COPING", h=0.28, layer=L_TXT,
            halign="right")
    dl.text(x1 - pw - 0.3, yt + ph / 2, 'PARAPET 4½"\nBRICK', h=0.28,
            layer=L_TXT, halign="right")
    # slab reinforcement note
    dl.text((x0 + x1) / 2 - 2, yt - slab / 2,
            f"R.C.C. SLAB {FP._s(st,'slab_depth')}  ·  MAIN "
            f"{FP._s(st,'slab_main')}", h=0.28, layer=L_BAR)
    _vdim(dl, x0 - 0.9, yt - slab, yt, f"D={FP._s(st,'slab_depth')}")
    _vdim(dl, x0 - 2.0, yt, yt + ph, "PARAPET HT.")
    dl.text((x0 + x1) / 2, yt - slab - 1.4, "TYPICAL TERRACE / PARAPET SECTION",
            h=0.5, layer=L_TXT, bold=True)
    return dl
