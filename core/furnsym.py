"""Furniture symbols.

Each piece is its footprint plus the linework that says what it is — pillows
and a blanket fold on a bed, slider lines on a wardrobe, a back line on a
chair, hob rings, a screen line on the TV. A bare rectangle reads as nothing.
"""

from __future__ import annotations

import math

from .draw import DrawList
from . import furniture as F

L = "FURNITURE"


def _inset(f, d: float):
    return (f.x + d, f.y + d, f.w - 2 * d, f.h - 2 * d)


def _long_axis(f) -> str:
    return "x" if f.w >= f.h else "y"


def draw(dl: DrawList, f, layer: str | None = None) -> None:
    """Draw one piece. A rotated piece is built square and then turned about
    its own centre, so every symbol works at any angle without knowing it.

    `layer` overrides the furniture layer — the plumbing stage puts the
    sanitary and kitchen fixtures on SANITARY so they can stay visible when
    the rest of the furniture is switched off.
    """
    angle = float(getattr(f, "angle", 0.0) or 0.0)
    start = len(dl.items)                 # where this piece begins on the list
    target = dl if abs(angle) < 1e-9 else DrawList()

    target.rect(f.x, f.y, f.w, f.h, layer=L)
    fn = _SYMBOLS.get(F.family(f.kind)) or _SYMBOLS.get(f.kind)
    if fn:
        try:
            fn(target, f)
        except Exception:
            pass

    if target is not dl:
        cx, cy = f.centre
        dl.extend(_rotated(target, cx, cy, angle))
    if layer:
        # retag only what THIS piece just added
        for it in dl.items[start:]:
            if it.layer == L:
                it.layer = layer


def _rotated(src: DrawList, cx: float, cy: float, deg: float) -> DrawList:
    from .draw import Arc, Line, Poly, Text
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)

    def rp(x, y):
        dx, dy = x - cx, y - cy
        return (cx + dx * ca - dy * sa, cy + dx * sa + dy * ca)

    out = DrawList()
    for it in src.items:
        if isinstance(it, Line):
            (x1, y1), (x2, y2) = rp(it.x1, it.y1), rp(it.x2, it.y2)
            out.line(x1, y1, x2, y2, it.layer, it.dashed)
        elif isinstance(it, Poly):
            out.poly([rp(*p) for p in it.pts], it.layer, it.closed, it.dashed)
        elif isinstance(it, Arc):
            ncx, ncy = rp(it.cx, it.cy)
            out.arc(ncx, ncy, it.r, it.a1 + deg, it.a2 + deg, it.layer,
                    it.dashed)
        elif isinstance(it, Text):
            x, y = rp(it.x, it.y)
            out.text(x, y, it.s, it.h, it.layer, it.angle + deg,
                     it.halign, it.valign, it.bold)
    return out


# ------------------------------------------------------------------ beds
def _bed(dl, f) -> None:
    """Pillows at the head, a blanket fold across the foot."""
    head = f.facing                     # the wall the head stands against
    pillow = F.ft(400)
    fold = F.ft(500)
    if head in ("N", "S"):
        y = (f.y + f.h - pillow) if head == "N" else f.y
        dl.line(f.x, y if head == "N" else y + pillow,
                f.x + f.w, y if head == "N" else y + pillow, layer=L)
        # two pillows side by side
        n = 2 if f.w > F.ft(1200) else 1
        pw = f.w / n
        for i in range(n):
            dl.rect(f.x + i * pw + F.ft(60), y + F.ft(60),
                    pw - F.ft(120), pillow - F.ft(120), layer=L)
        fy = (f.y + fold) if head == "N" else (f.y + f.h - fold)
        dl.line(f.x, fy, f.x + f.w, fy, layer=L)
    else:
        x = (f.x + f.w - pillow) if head == "E" else f.x
        dl.line(x if head == "E" else x + pillow, f.y,
                x if head == "E" else x + pillow, f.y + f.h, layer=L)
        n = 2 if f.h > F.ft(1200) else 1
        ph = f.h / n
        for i in range(n):
            dl.rect(x + F.ft(60), f.y + i * ph + F.ft(60),
                    pillow - F.ft(120), ph - F.ft(120), layer=L)
        fx = (f.x + fold) if head == "E" else (f.x + f.w - fold)
        dl.line(fx, f.y, fx, f.y + f.h, layer=L)


# -------------------------------------------------------------- storage
def _wardrobe(dl, f) -> None:
    """Sliding-shutter lines."""
    if _long_axis(f) == "x":
        n = max(2, int(f.w / F.ft(900)))
        for i in range(1, n):
            dl.line(f.x + f.w * i / n, f.y, f.x + f.w * i / n, f.y + f.h,
                    layer=L)
        dl.line(f.x, f.y + f.h * 0.5, f.x + f.w, f.y + f.h * 0.5, layer=L)
    else:
        n = max(2, int(f.h / F.ft(900)))
        for i in range(1, n):
            dl.line(f.x, f.y + f.h * i / n, f.x + f.w, f.y + f.h * i / n,
                    layer=L)
        dl.line(f.x + f.w * 0.5, f.y, f.x + f.w * 0.5, f.y + f.h, layer=L)


def _desk(dl, f) -> None:
    """A stool tucked under, drawn dashed — on the ROOM side of the desk (the
    side away from the wall the desk stands against), never climbing the wall."""
    s = F.ft(400)
    cx, cy = f.centre
    face = f.facing
    if face in ("N", "S"):
        # desk against the N (top) wall → room is below → stool below the desk;
        # against the S (bottom) wall → room is above → stool above the desk
        y = (f.y - s * 0.55) if face == "N" else (f.y + f.h - s * 0.45)
        dl.rect(cx - s / 2, y, s, s, layer=L, dashed=True)
    else:
        # against the E (right) wall → room is left; against W (left) → right
        x = (f.x - s * 0.55) if face == "E" else (f.x + f.w - s * 0.45)
        dl.rect(x, cy - s / 2, s, s, layer=L, dashed=True)


# --------------------------------------------------------------- living
def _sofa(dl, f) -> None:
    """Back and arms."""
    b = F.ft(200)
    if f.facing in ("N", "S"):
        by = (f.y + f.h - b) if f.facing == "N" else f.y
        dl.rect(f.x, by, f.w, b, layer=L)
        dl.rect(f.x, f.y, b, f.h, layer=L)
        dl.rect(f.x + f.w - b, f.y, b, f.h, layer=L)
    else:
        bx = (f.x + f.w - b) if f.facing == "E" else f.x
        dl.rect(bx, f.y, b, f.h, layer=L)
        dl.rect(f.x, f.y, f.w, b, layer=L)
        dl.rect(f.x, f.y + f.h - b, f.w, b, layer=L)


def _tv(dl, f) -> None:
    """The screen line on the front face."""
    d = F.ft(80)
    if f.facing in ("N", "S"):
        y = (f.y + d) if f.facing == "N" else (f.y + f.h - d)
        dl.line(f.x + f.w * 0.15, y, f.x + f.w * 0.85, y, layer=L)
    else:
        x = (f.x + d) if f.facing == "E" else (f.x + f.w - d)
        dl.line(x, f.y + f.h * 0.15, x, f.y + f.h * 0.85, layer=L)


# --------------------------------------------------------------- dining
_SEATS = {"dining_2": 2, "dining_4": 4, "dining_6": 6, "dining_8": 8}


def _dining(dl, f) -> None:
    """EVERY seat drawn, abutting the table — the full set the table is named
    for (a 4-seat shows 4), or exactly `f.chairs` when the user has set it.
    Distribution is the way a dining set actually sits: the long sides carry
    the pairs, the two ends take one each once the sides are full."""
    c = F.ft(450)
    gap = F.ft(30)
    n = int(getattr(f, "chairs", 0) or 0) or _SEATS.get(f.kind, 4)
    if n <= 0:
        return
    # split the seats: ends only from the 5th seat up (2/4 = side pairs only)
    ends = 0 if n <= 4 else min(2, n - 4)
    side_total = n - ends
    nA = (side_total + 1) // 2                   # one long side
    nB = side_total - nA                         # the other
    along_x = _long_axis(f) == "x"

    def row(count, side):
        """`count` chairs evenly along one side: N/S/E/W of the table."""
        for i in range(count):
            t = (i + 0.5) / count
            if side in ("N", "S"):
                cx = f.x + f.w * t - c / 2
                cy = (f.y + f.h + gap) if side == "N" else (f.y - c - gap)
            else:
                cy = f.y + f.h * t - c / 2
                cx = (f.x + f.w + gap) if side == "E" else (f.x - c - gap)
            dl.rect(cx, cy, c, c, layer=L)

    if along_x:                                   # long sides = N + S
        row(nA, "N"); row(nB, "S")
        if ends >= 1:
            row(1, "W")
        if ends == 2:
            row(1, "E")
    else:                                         # long sides = E + W
        row(nA, "E"); row(nB, "W")
        if ends >= 1:
            row(1, "N")
        if ends == 2:
            row(1, "S")


# -------------------------------------------------------------- kitchen
def _counter(dl, f) -> None:
    """Sink bowl and hob rings on the run."""
    along = _long_axis(f)
    length = f.w if along == "x" else f.h
    if length < F.ft(1500):
        return
    for frac, kind in ((0.25, "sink"), (0.70, "hob")):
        if along == "x":
            cx, cy = f.x + f.w * frac, f.y + f.h / 2
        else:
            cx, cy = f.x + f.w / 2, f.y + f.h * frac
        if kind == "sink":
            dl.rect(cx - F.ft(250), cy - F.ft(200), F.ft(500), F.ft(400),
                    layer=L)
        else:
            for ox, oy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                dl.items.append(_circle(cx + ox * F.ft(140),
                                        cy + oy * F.ft(110), F.ft(90)))


def _circle(cx, cy, r):
    from .draw import Arc
    return Arc(cx, cy, r, 0, 360, L)


# ------------------------------------------------------------------ wet
def _wc(dl, f) -> None:
    """Cistern against the wall, bowl in front."""
    cist = F.ft(200)
    if f.facing in ("N", "S"):
        cy = (f.y + f.h - cist) if f.facing == "N" else f.y
        dl.rect(f.x, cy, f.w, cist, layer=L)
        bx, by = f.x + f.w / 2, (f.y + f.h * 0.35 if f.facing == "N"
                                 else f.y + f.h * 0.65)
    else:
        cx = (f.x + f.w - cist) if f.facing == "E" else f.x
        dl.rect(cx, f.y, cist, f.h, layer=L)
        bx, by = (f.x + f.w * 0.35 if f.facing == "E"
                  else f.x + f.w * 0.65), f.y + f.h / 2
    dl.items.append(_circle(bx, by, F.ft(170)))


def _basin(dl, f) -> None:
    cx, cy = f.centre
    dl.items.append(_circle(cx, cy, min(f.w, f.h) * 0.34))


def _shower(dl, f) -> None:
    """Diagonals and the rose."""
    dl.line(f.x, f.y, f.x + f.w, f.y + f.h, layer=L)
    dl.line(f.x, f.y + f.h, f.x + f.w, f.y, layer=L)
    dl.items.append(_circle(f.x + f.w * 0.15, f.y + f.h * 0.85, F.ft(80)))


def _fridge(dl, f) -> None:
    dl.line(f.x + f.w * 0.5, f.y, f.x + f.w * 0.5, f.y + f.h, layer=L)


def _chair(dl, f) -> None:
    """Back against the wall it faces, seat in front of it."""
    b = F.ft(80)
    if f.facing in ("N", "S"):
        by = (f.y + f.h - b) if f.facing == "N" else f.y
        dl.rect(f.x, by, f.w, b, layer=L)
    else:
        bx = (f.x + f.w - b) if f.facing == "E" else f.x
        dl.rect(bx, f.y, b, f.h, layer=L)


def _armchair(dl, f) -> None:
    """Back and two arms — a sofa's proportions at one seat."""
    _sofa(dl, f)


def _coffee_table(dl, f) -> None:
    d = min(f.w, f.h) * 0.18
    dl.rect(f.x + d, f.y + d, f.w - 2 * d, f.h - 2 * d, layer=L)


def _sideboard(dl, f) -> None:
    """Shutter divisions, like a wardrobe but shallower."""
    if _long_axis(f) == "x":
        n = max(2, int(f.w / F.ft(600)))
        for i in range(1, n):
            dl.line(f.x + f.w * i / n, f.y, f.x + f.w * i / n, f.y + f.h,
                    layer=L)
    else:
        n = max(2, int(f.h / F.ft(600)))
        for i in range(1, n):
            dl.line(f.x, f.y + f.h * i / n, f.x + f.w, f.y + f.h * i / n,
                    layer=L)


def _shoe_rack(dl, f) -> None:
    """Shelf lines across the depth."""
    if _long_axis(f) == "x":
        for i in (1, 2):
            dl.line(f.x, f.y + f.h * i / 3, f.x + f.w, f.y + f.h * i / 3,
                    layer=L)
    else:
        for i in (1, 2):
            dl.line(f.x + f.w * i / 3, f.y, f.x + f.w * i / 3, f.y + f.h,
                    layer=L)


def _bedside(dl, f) -> None:
    d = min(f.w, f.h) * 0.22
    dl.rect(f.x + d, f.y + d, f.w - 2 * d, f.h - 2 * d, layer=L)


def _stool(dl, f) -> None:
    cx, cy = f.centre
    dl.items.append(_circle(cx, cy, min(f.w, f.h) * 0.42))


def _washing_machine(dl, f) -> None:
    cx, cy = f.centre
    dl.items.append(_circle(cx, cy, min(f.w, f.h) * 0.3))


_SYMBOLS = {
    "bed": _bed,
    "bedside": _bedside,
    "wardrobe": _wardrobe,
    "dresser": _desk,
    "study_table": _desk,
    "sofa": _sofa,
    "armchair": _armchair,
    "chair": _chair,
    "stool": _stool,
    "coffee_table": _coffee_table,
    "sideboard": _sideboard,
    "shoe_rack": _shoe_rack,
    "tv_unit": _tv,
    "dining": _dining,
    "counter": _counter,
    "wc": _wc,
    "basin": _basin,
    "shower": _shower,
    "fridge": _fridge,
    "washing_machine": _washing_machine,
}
