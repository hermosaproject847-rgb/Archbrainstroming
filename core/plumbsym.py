"""Plumbing symbols — §14 of the master prompt, drawn in the system colour.

The legend draws these with the SAME code the plan uses, so the two can never
drift. A fitting carries only its numbered KEY-NOTE circle on the plan; the
full text lives in the key-notes panel.
"""

from __future__ import annotations

import math

from . import plumbing as P
from .draw import DrawList, LAYERS

LT = "PLUMB-TAG"
R = 0.40                     # keynote circle radius, feet — small in tight toilets
SYM = 0.34                   # fitting icon size — kept small so a wet room reads


def layer_of(system: str) -> str:
    return P.SYSTEMS.get(system, (None, LT))[1]


def dashed_for(system: str) -> bool:
    """Vent is dot-dash and hot water dashed; the DXF only carries DASHED, so
    both are drawn dashed and the legend names the difference."""
    return P.SYSTEMS.get(system, (None, None, None, "solid"))[3] != "solid"


def _circle(dl, cx, cy, r, layer, n=28):
    dl.poly([(cx + r * math.cos(2 * math.pi * i / n),
              cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)],
            layer=layer, closed=True)


def keynote(dl: DrawList, x, y, n: int) -> None:
    _circle(dl, x, y, R, LT)
    dl.text(x, y, str(n), h=0.42, layer=LT, bold=True)


# ---------------------------------------------------------------- fittings
def _rose(dl, x, y, L):
    _circle(dl, x, y, SYM * 0.7, L)
    for i in range(8):
        a = math.pi * i / 4
        dl.line(x + SYM * .7 * math.cos(a), y + SYM * .7 * math.sin(a),
                x + SYM * 1.05 * math.cos(a), y + SYM * 1.05 * math.sin(a), L)


def _mixer(dl, x, y, L):
    dl.rect(x - SYM * .6, y - SYM * .4, SYM * 1.2, SYM * .8, layer=L)
    dl.line(x, y + SYM * .4, x, y + SYM, L)


def _angle_cock(dl, x, y, L):
    """Angle cock: the bow-tie with a right-angle body."""
    s = SYM * .5
    dl.poly([(x - s, y - s), (x, y), (x - s, y + s)], layer=L, closed=True)
    dl.line(x, y, x + s, y, L)
    dl.line(x + s, y, x + s, y + s, L)


def _valve(dl, x, y, L):
    s = SYM * .55
    dl.poly([(x - s, y - s), (x, y), (x - s, y + s)], layer=L, closed=True)
    dl.poly([(x + s, y - s), (x, y), (x + s, y + s)], layer=L, closed=True)


def _bib(dl, x, y, L):
    """Bib cock: valve body with a downturned spout."""
    _valve(dl, x, y, L)
    dl.line(x, y - SYM * .55, x, y - SYM * 1.1, L)
    dl.line(x, y - SYM * 1.1, x + SYM * .35, y - SYM * 1.1, L)


def _bib2(dl, x, y, L):
    """Two-way bib cock — cistern plus health faucet."""
    _valve(dl, x, y, L)
    for dx in (-SYM * .35, SYM * .35):
        dl.line(x + dx, y - SYM * .55, x + dx, y - SYM * 1.05, L)


def _pillar(dl, x, y, L):
    dl.line(x, y - SYM * .8, x, y + SYM * .5, L)
    dl.line(x, y + SYM * .5, x + SYM * .7, y + SYM * .5, L)
    _circle(dl, x, y - SYM * .8, SYM * .25, L)


def _faucet(dl, x, y, L):
    """Health faucet: a small hose loop."""
    _circle(dl, x, y, SYM * .3, L)
    dl.poly([(x, y), (x + SYM * .8, y - SYM * .4),
             (x + SYM * .5, y - SYM * 1.0)], layer=L, closed=False)


def _bottle_trap(dl, x, y, L):
    dl.rect(x - SYM * .35, y - SYM * .8, SYM * .7, SYM * 1.1, layer=L)
    dl.line(x, y + SYM * .3, x, y + SYM * .8, L)


def _nahani(dl, x, y, L):
    """Nahani (floor) trap: a dark square housing with a round grating whose
    mesh reads as a grille — the routing-sheet floor-trap symbol."""
    s = SYM * .9
    dl.fill([(x - s, y - s), (x + s, y - s), (x + s, y + s), (x - s, y + s)],
            color="#3a3a3a", layer=L)                # dark housing
    dl.rect(x - s, y - s, 2 * s, 2 * s, layer=L)
    r = s * .72
    _circle(dl, x, y, r, L)                          # grating rim
    # grille mesh — a fine cross-grid clipped to the round grate
    n = 5
    for i in range(1, n):
        t = -r + 2 * r * i / n
        h = (r * r - t * t) ** 0.5
        dl.line(x + t, y - h, x + t, y + h, L)
        dl.line(x - h, y + t, x + h, y + t, L)
    dl.text(x, y - s - 0.28, "NT", h=0.24, layer=LT)


def _gully(dl, x, y, L):
    s = SYM
    dl.rect(x - s, y - s, 2 * s, 2 * s, layer=L)
    _circle(dl, x, y, s * .5, L)
    dl.text(x, y - s - 0.28, "GT", h=0.24, layer=LT)


def _chamber(dl, x, y, L):
    s = SYM * 1.3
    dl.rect(x - s, y - s, 2 * s, 2 * s, layer=L)
    dl.line(x - s, y - s, x + s, y + s, L)
    dl.line(x - s, y + s, x + s, y - s, L)


def _cleanout(dl, x, y, L):
    _circle(dl, x, y, SYM * .5, L)
    dl.line(x - SYM * .5, y, x + SYM * .5, y, L)
    dl.text(x, y - SYM * 1.1, "CO", h=0.22, layer=LT)


def _khurra(dl, x, y, L):
    s = SYM * 1.1
    dl.rect(x - s, y - s, 2 * s, 2 * s, layer=L)
    _circle(dl, x, y, s * .45, L)
    dl.text(x, y - s - 0.28, "KH", h=0.24, layer=LT)


def _stack(dl, x, y, L):
    """A vertical stack: a circle, the same coordinate on every floor."""
    _circle(dl, x, y, SYM * .8, L)
    _circle(dl, x, y, SYM * .45, L)


def _tank(dl, x, y, L):
    w, h = SYM * 3.2, SYM * 2.2
    dl.rect(x - w / 2, y - h / 2, w, h, layer=L)
    dl.rect(x - w / 2 + .12, y - h / 2 + .12, w - .24, h - .24, layer=L)


def _pump(dl, x, y, L):
    _circle(dl, x, y, SYM, L)
    dl.poly([(x - SYM * .4, y - SYM * .5), (x + SYM * .6, y),
             (x - SYM * .4, y + SYM * .5)], layer=L, closed=True)


def _geyser(dl, x, y, L):
    dl.rect(x - SYM * .8, y - SYM * 1.2, SYM * 1.6, SYM * 2.4, layer=L)
    _circle(dl, x, y, SYM * .4, L)


_SYM = {
    "SH": _rose, "SMX": _mixer, "SAR": _rose,
    "BAC": _angle_cock, "WCAC": _bib2, "HF": _faucet,
    "PC": _pillar, "SKC": _pillar, "WMT": _bib, "GBC": _bib,
    "BBT": _bottle_trap, "SV": _valve,
    "NT": _nahani, "GT": _gully, "IC": _chamber, "CO": _cleanout,
    "KH": _khurra, "UGT": _tank, "OHT": _tank, "PUMP": _pump, "GY": _geyser,
    "SS": _stack, "WS": _stack, "VP": _stack, "RWP": _stack,
    "CWD": _stack, "HWD": _stack,
}


def draw(dl: DrawList, p, keynotes: bool = True) -> None:
    layer = layer_of(p.system)
    fn = _SYM.get(p.code)
    if fn:
        try:
            fn(dl, p.x, p.y, layer)
        except Exception:
            pass
    # §8 — a stack carries its tag so vertical continuity is checkable
    if p.code in ("SS", "WS", "VP", "RWP", "CWD", "HWD") and p.tag:
        dl.text(p.x, p.y + SYM * 1.35, p.tag, h=0.26, layer=LT, bold=True)
    if keynotes and p.key:
        keynote(dl, p.x + getattr(p, "key_dx", 0.0),
                p.y + getattr(p, "key_dy", R * 1.9), p.key)


# §6 asks for the slope written along every DRAINAGE run. Supply pipes carry
# no slope, and tagging every short branch was what filled the sheet with
# repeated "15Ø COLD" — the legend already gives their size. So only the
# drainage / vent / storm / AC runs are tagged, and only if long enough to
# read.
_TAGGED_RUNS = ("SOIL", "WASTE", "VENT", "STORM", "ACD")
_MIN_TAG_FT = 3.5


FT_MM = 304.8
# systems drawn as a real TWO-WALL pipe (you see its thickness), the rest as a
# single line. Drainage & storm carry real bore; supply/vent stay single so a
# tight wet room does not turn into a black smear.
_TWO_WALL = ("SOIL", "WASTE", "STORM")
_SUPPLY = ("CW", "HW")


def _pipe_walls(pts, half):
    """The two side walls of a pipe of half-width `half` (feet), following the
    run's centre-line. Returns [wallA, wallB] coordinate lists, or None."""
    try:
        from shapely.geometry import LineString
        ls = LineString(pts)
        if ls.length <= 0:
            return None
        a = ls.parallel_offset(half, "left", join_style=2)
        b = ls.parallel_offset(half, "right", join_style=2)
        out = []
        for g in (a, b):
            if g.is_empty:
                continue
            geoms = g.geoms if g.geom_type == "MultiLineString" else [g]
            for p in geoms:
                out.append([(round(x, 4), round(y, 4)) for x, y in p.coords])
        return out or None
    except Exception:
        return None


def _sys_color(layer: str) -> str:
    return LAYERS.get(layer, ("#000000",))[0]


def _flow_arrow(dl: DrawList, pts, layer, color) -> None:
    """A solid triangle mid-run, pointing the way the pipe flows (pts order)."""
    best = max(zip(pts, pts[1:]), key=lambda ab: math.dist(ab[0], ab[1]))
    (ax, ay), (bx, by) = best
    if math.dist((ax, ay), (bx, by)) < 1.2:
        return
    mx, my = (ax + bx) / 2, (ay + by) / 2
    ang = math.atan2(by - ay, bx - ax)
    ca, sa, s = math.cos(ang), math.sin(ang), 0.55
    px, py = -sa, ca
    tip = (mx + ca * s, my + sa * s)
    b1 = (mx - ca * s * 0.5 + px * s * 0.5, my - sa * s * 0.5 + py * s * 0.5)
    b2 = (mx - ca * s * 0.5 - px * s * 0.5, my - sa * s * 0.5 - py * s * 0.5)
    dl.fill([tip, b1, b2], color=color, layer=layer)


FIT = "PLUMB-FIT"


def _fitting(dl: DrawList, x, y, a_in, a_out, bore) -> None:
    """The pipe FITTING at a bend (violet, like the routing sheet). A ~90° turn
    gets an elbow block; a ~45° turn gets a 45° Y-connector stub — the fitting a
    fitter actually uses to hold slope on a branch."""
    s = max(0.22, bore * 0.95)
    turn = abs(((math.degrees(a_out - a_in) + 180) % 360) - 180)   # deflection 0..180
    sq = [(x - s, y - s), (x + s, y - s), (x + s, y + s), (x - s, y + s)]
    dl.fill(sq, color="#ffffff", layer="PLUMB-BORE")     # mask the pipe under it
    dl.poly(sq, layer=FIT, closed=True)                  # coupling body (violet)
    if abs(turn - 45) <= 22:                             # 45° Y-connector
        bis = (a_in + a_out) / 2.0 + math.pi            # stub points into the branch
        dl.line(x, y, x + math.cos(bis) * s * 1.6, y + math.sin(bis) * s * 1.6, layer=FIT)
        dl.line(x - s * 0.5, y, x + s * 0.5, y, layer=FIT)
    else:                                                # 90° elbow (or straight coupling)
        dl.line(x - s, y - s, x + s, y + s, layer=FIT)
        dl.line(x - s, y + s, x + s, y - s, layer=FIT)


def draw_run(dl: DrawList, r) -> None:
    """A pipe run drawn like the routing layout: a two-wall pipe in its system
    colour (SWP orange, WWP green) with a dashed centre-line, an elbow collar at
    each bend, a solid flow arrow, and the '110Ø SWP / SLOPE 1:80' tag along it."""
    layer = layer_of(r.system)
    color = _sys_color(layer)
    dashed = dashed_for(r.system)
    pts = list(r.pts)
    bore = (getattr(r, "dia_mm", 0) or 0) / FT_MM          # pipe Ø in feet
    walls = _pipe_walls(pts, bore / 2.0) if (r.system in _TWO_WALL and bore > 0.10 and len(pts) >= 2) else None
    if walls:
        for wl in walls:                                    # outer coloured walls
            dl.poly(wl, layer=layer, closed=False)
        inner = _pipe_walls(pts, bore * 0.32)               # inner black bore walls
        if inner:
            for wl in inner:
                dl.poly(wl, layer="PLUMB-BORE", closed=False)
        dl.poly(pts, layer="PLUMB-CL", closed=False, dashed=True)   # dashed centre
        for i in range(1, len(pts) - 1):                    # fitting at each bend
            a_in = math.atan2(pts[i][1] - pts[i - 1][1], pts[i][0] - pts[i - 1][0])
            a_out = math.atan2(pts[i + 1][1] - pts[i][1], pts[i + 1][0] - pts[i][0])
            _fitting(dl, pts[i][0], pts[i][1], a_in, a_out, bore)
        _flow_arrow(dl, pts, layer, color)
    elif r.system in _SUPPLY and len(pts) >= 2:
        # water supply: one thick dash-dot line + flow arrow + Ø tag (no slope)
        dl.poly(pts, layer=layer, closed=False, dashed=True)
        _flow_arrow(dl, pts, layer, color)
        if r.dia_mm and r.length_ft >= _MIN_TAG_FT:
            best = max(zip(pts, pts[1:]), key=lambda ab: math.dist(ab[0], ab[1]))
            (ax, ay), (bx, by) = best
            if math.dist((ax, ay), (bx, by)) >= _MIN_TAG_FT:
                mx, my = (ax + bx) / 2, (ay + by) / 2
                ang = math.degrees(math.atan2(by - ay, bx - ax))
                if ang > 90:
                    ang -= 180
                if ang < -90:
                    ang += 180
                ar = math.radians(ang)
                px, py = -math.sin(ar), math.cos(ar)
                dl.text(mx + px * 0.5, my + py * 0.5, f"{r.dia_mm:g}Ø",
                        h=0.30, layer=layer, angle=ang)
        return
    else:
        dl.poly(pts, layer=layer, closed=False, dashed=dashed)

    if r.system not in _TAGGED_RUNS or not r.dia_mm or len(pts) < 2:
        return
    if r.length_ft < _MIN_TAG_FT:
        return
    best = max(zip(pts, pts[1:]), key=lambda ab: math.dist(ab[0], ab[1]))
    (ax, ay), (bx, by) = best
    if math.dist((ax, ay), (bx, by)) < _MIN_TAG_FT:
        return
    mx, my = (ax + bx) / 2, (ay + by) / 2
    ang = math.degrees(math.atan2(by - ay, bx - ax))
    if ang > 90:
        ang -= 180
    if ang < -90:
        ang += 180
    # two-line tag stacked ABOVE the pipe (perpendicular offset), rotated to it
    ar = math.radians(ang)
    px, py = -math.sin(ar), math.cos(ar)
    off = max(0.55, bore / 2 + 0.4)
    l1, l2 = P.pipe_label(r.system, r.dia_mm)
    dl.text(mx + px * (off + 0.34), my + py * (off + 0.34), l1,
            h=0.30, layer=layer, angle=ang)
    if l2:
        dl.text(mx + px * off, my + py * off, l2, h=0.26, layer=layer, angle=ang)
