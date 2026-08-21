"""Electrical symbols — the PART 4.1 legend, drawn as real CAD symbols.

Two things matter on an electrical sheet: the symbol must be recognisable at
1:50, and the sheet must stay readable. So the symbols are drawn small and
consistent, the fan shows its sweep as a thin dashed circle rather than a
heavy one, and tags sit on a short leader clear of the symbol instead of on
top of the next fixture.
"""

from __future__ import annotations

import math

from .draw import Arc, DrawList

L = "ELEC"
LT = "ELECTAG"

R = 0.26                     # the standard symbol radius, feet at true scale
TAG_DROP = 0.52              # how far the tag sits below the symbol


def _circle(cx, cy, r, layer=L, dashed=False):
    a = Arc(cx, cy, r, 0, 360, layer)
    a.dashed = dashed
    return a


#: the boards, AC, fans and exhausts an electrician finds by name, plus EVERY
#: light — each carries an L-number so the lighting and switch-loop schedules
#: can name the exact fitting they loop through.
from . import electrical as _E
_CEILING = _E.LIGHT_CODES
TAGGED = ("SB", "DB", "AC", "CF", "EF") + tuple(_CEILING)

_SHORT = {"SB": "S.B.", "DB": "D.B.", "AC": "A.C.", "CF": "F", "EF": "E.F."}
_SHORT.update({c: "L" for c in _CEILING})     # every ceiling light -> L{n}


def draw(dl: DrawList, p, tag: bool = True) -> None:
    fn = _SYM.get(p.code)
    if fn:
        try:
            fn(dl, p)
        except Exception:
            pass
    if not (tag and p.tag and p.code in TAGGED):
        return
    # short marks only: S.B.1, L7, not "+1200 SB01". Heights belong in the
    # schedule, and long tags are what buried the drawing.
    n = p.tag.rsplit("-", 1)[-1].lstrip("0") or "1"
    short = _SHORT[p.code]
    drop = getattr(p, "_tagdrop", None) or TAG_DROP
    # a light's number rides just off the crosshair so it never lands on it
    h = 0.20 if p.code in _CEILING else 0.24
    dl.text(p.x + (0.34 if p.code in _CEILING else 0.0),
            p.y - drop, f"{short}{n}", h=h, layer=LT)


# ---------------------------------------------------------------- lights
def _spot(dl, p):
    """COB spotlight: a small circle with a crosshair through it."""
    r = R * 0.62
    dl.items.append(_circle(p.x, p.y, r))
    dl.line(p.x - r * 1.6, p.y, p.x + r * 1.6, p.y, layer=L)
    dl.line(p.x, p.y - r * 1.6, p.x, p.y + r * 1.6, layer=L)


def _spot_adj(dl, p):
    _spot(dl, p)
    a = math.radians(p.angle or -45)
    dl.arrow(p.x + math.cos(a) * R, p.y + math.sin(a) * R,
             p.x + math.cos(a) * R * 2.4, p.y + math.sin(a) * R * 2.4,
             head=0.14)


def _panel(dl, p):
    """LED panel: a square with an X, drawn to its real 600 x 600 face."""
    s = 0.98                                   # 600 mm
    dl.rect(p.x - s / 2, p.y - s / 2, s, s, layer=L)
    dl.line(p.x - s / 2, p.y - s / 2, p.x + s / 2, p.y + s / 2, layer=L)
    dl.line(p.x - s / 2, p.y + s / 2, p.x + s / 2, p.y - s / 2, layer=L)


def _surface(dl, p):
    dl.items.append(_circle(p.x, p.y, R * 0.85))
    dl.items.append(_circle(p.x, p.y, R * 0.45))


def _cove(dl, p):
    ln = max(p.size, 2.0)
    for d in (-0.05, 0.05):
        dl.line(p.x - ln / 2, p.y + d, p.x + ln / 2, p.y + d,
                layer=L, dashed=True)


def _wall(dl, p):
    """Wall light: half-disc against its wall, with the hatch that marks the
    filled half."""
    r = R * 0.8
    a = math.radians(p.angle or 90)
    nx, ny = math.cos(a), math.sin(a)
    dl.items.append(Arc(p.x, p.y, r, math.degrees(a) - 90,
                        math.degrees(a) + 90, L))
    dl.line(p.x - ny * r, p.y + nx * r, p.x + ny * r, p.y - nx * r, layer=L)
    for i in (-0.5, 0, 0.5):
        dl.line(p.x + ny * r * i, p.y - nx * r * i,
                p.x + ny * r * i + nx * r * 0.7,
                p.y - nx * r * i + ny * r * 0.7, layer=L)


def _bedside_wall(dl, p):
    _wall(dl, p)


def _pendant(dl, p):
    """Pendant: the drop line, then the shade seen from above."""
    r = R * 0.9
    dl.line(p.x, p.y, p.x, p.y + r * 2.2, layer=L)
    dl.items.append(_circle(p.x, p.y, r))
    dl.items.append(_circle(p.x, p.y, r * 0.35))


def _chandelier(dl, p):
    """Chandelier: a ring of lamps on radiating arms."""
    r = R * 1.9
    dl.items.append(_circle(p.x, p.y, r * 0.3))
    for i in range(6):
        a = math.radians(60 * i + 15)
        ex, ey = p.x + r * math.cos(a), p.y + r * math.sin(a)
        dl.line(p.x, p.y, ex, ey, layer=L)
        dl.items.append(_circle(ex, ey, r * 0.22))


def _mirror(dl, p):
    """Mirror light: a slim linear fitting."""
    w, h = 1.6, 0.24
    dl.rect(p.x - w / 2, p.y - h / 2, w, h, layer=L)
    for i in (0.25, 0.5, 0.75):
        dl.line(p.x - w / 2 + w * i, p.y - h / 2,
                p.x - w / 2 + w * i, p.y + h / 2, layer=L)


def _step(dl, p):
    s = 0.34
    dl.rect(p.x - s / 2, p.y - s / 2, s, s, layer=L)
    dl.line(p.x - s / 2, p.y, p.x + s / 2, p.y, layer=L)


def _track(dl, p):
    """Track: the rail with its heads."""
    ln = max(p.size, 2.5)
    for d in (-0.05, 0.05):
        dl.line(p.x - ln / 2, p.y + d, p.x + ln / 2, p.y + d, layer=L)
    n = max(2, int(ln / 1.0))
    for i in range(n):
        t = -ln / 2 + ln * (i + 0.5) / n
        dl.items.append(_circle(p.x + t, p.y, 0.09))


# ------------------------------------------------------------------ fans
def _fan(dl, p):
    """Ceiling fan, drawn the way a services drawing draws it: a hub with
    three swept blades and a rim. No dashed sweep circle — the blades already
    say how far it reaches, and the extra circle is what made the sheet look
    busy."""
    r = (p.size or 4.0) / 2
    hub = r * 0.16
    dl.items.append(_circle(p.x, p.y, hub))
    dl.items.append(_circle(p.x, p.y, hub * 0.45))
    for i in range(3):
        a0 = math.radians(120 * i + (p.angle or 0))
        sweep = math.radians(46)          # how far the blade wraps
        wr = math.radians(7)
        pts = [(p.x + hub * math.cos(a0 - wr),
                p.y + hub * math.sin(a0 - wr))]
        # leading edge, curving out to the tip
        for k in range(7):
            t = k / 6
            a = a0 + sweep * t * 0.30
            rr = hub + (r - hub) * t
            pts.append((p.x + rr * math.cos(a), p.y + rr * math.sin(a)))
        # the tip, then the trailing edge back to the hub
        for k in range(7):
            t = 1 - k / 6
            a = a0 + sweep * (0.30 + 0.70 * (1 - t))
            rr = hub + (r - hub) * t
            pts.append((p.x + rr * math.cos(a), p.y + rr * math.sin(a)))
        dl.poly(pts, layer=L, closed=True)


def _exhaust(dl, p):
    """Exhaust fan: a square housing with the impeller inside."""
    s = 0.72
    dl.rect(p.x - s / 2, p.y - s / 2, s, s, layer=L)
    dl.items.append(_circle(p.x, p.y, s * 0.34))
    for i in range(4):
        a = math.radians(90 * i + 20)
        dl.line(p.x, p.y, p.x + s * 0.33 * math.cos(a),
                p.y + s * 0.33 * math.sin(a), layer=L)


# -------------------------------------------------------------------- AC
def _ac(dl, p):
    """High-wall indoor unit: the casing, its louvre, and the throw."""
    w, h = 3.2, 0.62
    a = math.radians(p.angle or 0)
    ca, sa = math.cos(a), math.sin(a)

    def rp(dx, dy):
        return (p.x + dx * ca - dy * sa, p.y + dx * sa + dy * ca)

    dl.poly([rp(-w / 2, -h / 2), rp(w / 2, -h / 2),
             rp(w / 2, h / 2), rp(-w / 2, h / 2)], layer=L, closed=True)
    # louvre blades along the face
    for i in range(1, 6):
        t = -w / 2 + w * i / 6
        dl.line(*rp(t, -h / 2 + 0.06), *rp(t, h / 2 - 0.06), layer=L)
    # the throw, dashed
    for t in (-w * 0.28, 0, w * 0.28):
        dl.line(*rp(t, -h / 2), *rp(t - 0.35, -h / 2 - 0.85),
                layer=L, dashed=True)
    p._tagdrop = -(h / 2 + 0.42)          # the mark goes above the casing


# ------------------------------------------------------ boards and the DB
def _board(dl, p):
    """Switchboard: the plate with its module divisions, and the height tag.

    Drawn small — a board on a 1:50 plan is a marker, not a scale object; the
    old 0.28 ft module made it the size of a piece of furniture. It rotates
    with `angle`, so it can sit flush on any wall the user turns it to.
    """
    n = max(2, min(len(p.controls) or 2, 8))
    w = 0.16 * n + 0.06
    h = 0.30
    a = math.radians(getattr(p, "angle", 0.0) or 0.0)
    ca, sa = math.cos(a), math.sin(a)

    def rp(dx, dy):
        return (p.x + dx * ca - dy * sa, p.y + dx * sa + dy * ca)

    dl.poly([rp(-w / 2, -h / 2), rp(w / 2, -h / 2),
             rp(w / 2, h / 2), rp(-w / 2, h / 2)], layer=L, closed=True)
    for i in range(1, n):
        x = -w / 2 + (w / n) * i
        dl.line(*rp(x, -h / 2), *rp(x, h / 2), layer=L)
    # drop the mark clear of the plate whatever its rotation
    p._tagdrop = abs(w / 2 * sa) + abs(h / 2 * ca) + 0.24


def _db(dl, p):
    """Distribution board: a double rectangle, marked DB. Kept small and set
    flush on its wall — rotated when it hangs on a vertical face."""
    w, h = 0.95, 0.5
    a = math.radians(getattr(p, "angle", 0.0) or 0.0)
    ca, sa = math.cos(a), math.sin(a)

    def rp(dx, dy):
        return (p.x + dx * ca - dy * sa, p.y + dx * sa + dy * ca)

    def rrect(hw, hh):
        dl.poly([rp(-hw, -hh), rp(hw, -hh), rp(hw, hh), rp(-hw, hh)],
                layer=L, closed=True)

    rrect(w / 2, h / 2)
    rrect(w / 2 - 0.06, h / 2 - 0.06)
    for i in range(1, 4):
        t = -w / 2 + w * i / 4
        dl.line(*rp(t, -h / 2 + 0.06), *rp(t, h / 2 - 0.06), layer=L)
    lx, ly = rp(0, h * 0.9)
    dl.text(lx, ly, "DB", h=0.22, layer=LT, bold=True)
    p._tagdrop = h / 2 + 0.3


_SYM = {
    "SL": _spot, "ASL": _spot_adj, "PL": _panel, "CSL": _surface,
    "CV": _cove, "WL": _wall, "BWL": _bedside_wall, "HL": _pendant,
    "CH": _chandelier, "ML": _mirror, "STL": _step, "TR": _track,
    "CF": _fan, "EF": _exhaust, "AC": _ac, "SB": _board, "DB": _db,
}
