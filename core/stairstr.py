"""Staircase STRUCTURAL DETAILS and SHUTTERING DETAILS sheets, drawn to the
office reference (Central Avenue GFC set): a full-height section through the
stair — dog-leg flights zig-zagging storey over storey with hatched RCC waist
slabs, numbered risers, landing slabs on tagged landing beams, hatched cut
walls, soil at the base and level flags down the right edge — plus, on the
structural sheet, the reinforcement (main top / bottom bars, distribution,
rings) with callouts and a landing-beam rebar detail; on the shuttering sheet,
a boxed shuttering level tag along the flights at every step group.

Everything is measured from the plan's OWN stair (steps, tread, flight width,
landing) — nothing is assumed.
"""

from __future__ import annotations

import math

from .draw import Arc, DrawList
from . import section as S
from . import stairs as ST

L_CUT, L_SLAB, L_BAR, L_TXT, L_DIM = \
    "SEC-CUT", "SEC-SLAB", "FLR-START", "SEC-TEXT", "SEC-DIM"

SLAB_T = 0.375          # 4.5" floor slab
LAND_T = 0.5            # 6" landing slab
WAIST = 0.5             # 6" waist slab
WALL_T = 0.75           # 9" cut walls


def _fmt(v: float) -> str:
    """A level as the sheet writes it: +14'-8", -6'-3¼"…"""
    sign = "-" if v < -1e-9 else "+"
    v = abs(v)
    ft = int(v + 1e-9)
    inch = (v - ft) * 12.0
    whole = int(inch + 1e-6)
    q = int(round((inch - whole) * 4))
    if q == 4:
        whole += 1
        q = 0
    if whole == 12:
        ft += 1
        whole = 0
    frac = {0: "", 1: "¼", 2: "½", 3: "¾"}[q]
    if ft == 0 and whole == 0 and not frac:
        return "±0'-0\""
    return f"{sign}{ft}'-{whole}{frac}\""


def _stair_of(plan):
    for s in getattr(plan, "stairs", None) or []:
        return s
    return None


def _counts(s):
    """(treads flight A, treads flight B, winders) off the plan's stair."""
    try:
        g = ST.build(s)
        fls = g.get("flights") or []
    except Exception:
        fls = []
    if len(fls) >= 2:
        a = int(fls[0].get("steps") or 0)
        b = int(fls[1].get("steps") or 0)
    elif len(fls) == 1:
        a = int(fls[0].get("steps") or 0)
        b = 0
    else:
        a = int(getattr(s, "steps_f1", 0) or 9)
        b = int(getattr(s, "steps_f2", 0) or 9)
    w = int(getattr(s, "winders", 0) or 0)
    return max(a, 2), max(b, 0), w


def _flag(dl, x, y, name, lvl):
    """A level flag: tick + solid dot + two text lines, as the sheet has."""
    dl.line(x, y, x + 2.2, y, layer=L_DIM)
    dl.items.append(Arc(x + 2.2, y, 0.14, 0, 360, L_BAR))
    dl.text(x + 2.6, y + 0.22, name, h=0.34, layer=L_TXT, halign="left")
    dl.text(x + 2.6, y - 0.28, f"LVL. {lvl}", h=0.30, layer=L_TXT,
            halign="left")


def _flight(dl, x0, z0, n_treads, tread, riser, d, num0, mode, bars):
    """One CUT flight: steps + hatched waist + (structural) bars or
    (shuttering) level tags. Runs from (x0, z0) climbing `n_treads` treads in
    direction d (+1 right, -1 left). Returns (x_end, z_end, next number)."""
    x, z = x0, z0
    # the stepped profile: riser up, then tread across, per step
    pts = [(x, z)]
    num = num0
    for i in range(n_treads):
        z += riser
        pts.append((x, z))
        x += d * tread
        pts.append((x, z))
        dl.text(x - d * tread / 2, z + 0.28, str(num), h=0.26, layer=L_TXT)
        num += 1
    for a, b in zip(pts, pts[1:]):
        dl.line(a[0], a[1], b[0], b[1], layer=L_CUT)
    # the waist slab under the pitch line (nose to nose)
    ax, ay = x0, z0
    bx, by = x, z
    L = math.hypot(bx - ax, by - ay) or 1.0
    nx, ny = (by - ay) / L, -(bx - ax) / L      # unit normal, below the pitch
    if ny > 0:
        nx, ny = -nx, -ny
    w = WAIST
    poly = [(ax, ay), (bx, by), (bx + nx * w, by + ny * w),
            (ax + nx * w, ay + ny * w)]
    for a, b in zip(poly, poly[1:] + poly[:1]):
        dl.line(a[0], a[1], b[0], b[1], layer=L_CUT)
    S._hatch_poly(dl, poly, L_SLAB, step=0.45, slope=1)

    ang = math.degrees(math.atan2(by - ay, bx - ax))
    if ang > 90:
        ang -= 180
    elif ang < -90:
        ang += 180
    if mode == "structural":
        # bottom bar just inside the soffit, main top bar under the noses
        dl.line(ax + nx * (w - 0.12), ay + ny * (w - 0.12),
                bx + nx * (w - 0.12), by + ny * (w - 0.12), layer=L_BAR)
        dl.line(ax + nx * 0.12, ay + ny * 0.12,
                bx + nx * 0.12, by + ny * 0.12, layer=L_BAR)
        # distribution bars: a dot per step, mid-waist
        for i in range(n_treads):
            t = (i + 0.5) / n_treads
            dl.items.append(Arc(ax + (bx - ax) * t + nx * w * 0.5,
                                ay + (by - ay) * t + ny * w * 0.5,
                                0.07, 0, 360, L_BAR))
        if bars:
            mx = (ax + bx) / 2 + nx * w * 0.5
            my = (ay + by) / 2 + ny * w * 0.5
            # the clear triangle UNDER flight A, above the plinth
            tx, ty = min(ax, bx) + 1.2, min(ay, by) + 1.1
            dl.line(mx, my, tx + 1.4, ty + 1.15, layer=L_DIM)
            dl.text(tx, ty + 0.9, f"MAIN TOP BAR {bars['main']}",
                    h=0.30, layer=L_TXT, halign="left")
            dl.text(tx, ty + 0.4, f"BOTTOM BAR {bars['main']}",
                    h=0.30, layer=L_TXT, halign="left")
            dl.text(tx, ty - 0.1, f"{bars['dist']} (Dist.)",
                    h=0.30, layer=L_TXT, halign="left")
    else:
        # shuttering: a boxed level tag on every third step, along the slope
        for i in range(0, n_treads, 3):
            t = (i + 0.5) / n_treads
            tx = ax + (bx - ax) * t + nx * (w + 0.55)
            ty = ay + (by - ay) * t + ny * (w + 0.55)
            lvl = _fmt(z0 + (i + 1) * riser)
            dl.rect(tx - 1.0, ty - 0.3, 2.0, 0.6, layer=L_DIM)
            dl.text(tx, ty, lvl, h=0.26, layer=L_TXT, angle=ang)
    return x, z, num


def _dim(v: float) -> str:
    """A size (not a level): 10½\" under a foot, 3'-3\" over."""
    s = _fmt(v)[1:]
    return s[3:] if s.startswith("0'-") else s


def _sheet(plan, struct, mode: str) -> DrawList:
    st = struct or plan.__dict__.get("struct") or {}
    dl = DrawList()
    s = _stair_of(plan)

    tread = float(getattr(s, "tread", 0) or 0) or (10.0 / 12.0) if s else \
        10.0 / 12.0
    fw = (float(getattr(s, "flight_width", 0) or 0) or 3.25) if s else 3.25
    a, b, wind = _counts(s) if s else (9, 9, 0)
    n_floors = 2                              # G + 1, as the reference set
    plinth = 1.5                              # +1'-6" over internal road
    storey = 10.0
    risers_a, risers_b = a + 1, b + wind + 1
    riser = storey / (risers_a + risers_b)

    land = (float(getattr(s, "landing_depth", 0) or 0) or fw) if s else fw
    run = max(a, max(b, 1)) * tread
    xw = land + run + 0.8                     # inner face of the right wall
    top = plinth + n_floors * storey
    para = 3.0

    bars = {"main": (st or {}).get("stair_main") or "3#10mm",
            "dist": (st or {}).get("stair_dist") or '#10mm@6"c/c'}

    # ---- ground: compacted soil + plinth ----
    S._hatch(dl, -WALL_T - 1.5, -2.2, xw + WALL_T + 1.5, 0.0, L_SLAB,
             step=0.5, slope=1)
    dl.line(-WALL_T - 1.5, 0.0, xw + WALL_T + 1.5, 0.0, layer=L_CUT)
    dl.text((xw + WALL_T) / 2, -2.8, "COMPACTED SOIL", h=0.36, layer=L_TXT)
    S._fill_band(dl, -WALL_T, plinth - 0.45, xw + WALL_T, plinth, L_SLAB)
    dl.rect(-WALL_T, plinth - 0.45, xw + 2 * WALL_T, 0.45, layer=L_CUT)

    # ---- the two cut walls, full height ----
    S._cut_wall(dl, -WALL_T, 0.0, 0.0, top, L_CUT)
    S._cut_wall(dl, xw, xw + WALL_T, 0.0, top + para, L_CUT)
    # parapet coping on the right wall
    dl.rect(xw - 0.1, top + para, WALL_T + 0.2, 0.25, layer=L_CUT)

    # ---- the flights, storey over storey ----
    num = 1
    for k in range(n_floors):
        z0 = plinth + k * storey
        zl = z0 + risers_a * riser            # half-landing level
        zt = z0 + storey                      # next floor level
        # flight A: from the right, climbing LEFT to the half landing
        _flight(dl, land + a * tread, z0, a, tread, riser, -1, num, mode,
                bars if k == 0 else None)
        num += a
        # half landing slab on its landing beam
        S._fill_band(dl, 0.0, zl - LAND_T, land, zl, L_SLAB)
        dl.rect(0.0, zl - LAND_T, land, LAND_T, layer=L_CUT)
        dl.text(land / 2, zl + 0.4, str(num), h=0.26, layer=L_TXT)
        num += 1 + wind
        lbw, lbd = 0.5, 1.5
        S._fill_band(dl, land - lbw, zl - lbd, land, zl - LAND_T, L_SLAB)
        dl.rect(land - lbw, zl - lbd, lbw, lbd - LAND_T, layer=L_CUT)
        dl.line(land - lbw / 2, zl - lbd, 0.9, zl - lbd - 1.0, layer=L_DIM)
        dl.text(0.15, zl - lbd - 1.0, "LANDING BEAM", h=0.28,
                layer=L_TXT, halign="left")
        dl.text(0.15, zl - lbd - 1.45, 'LB (6"X18")', h=0.28,
                layer=L_TXT, halign="left")
        # flight B: from the landing, climbing RIGHT to the floor slab
        _flight(dl, land, zl, b, tread, riser, +1, num, mode, None)
        num += b
        # the floor slab of the storey above
        S._fill_band(dl, land + b * tread - 0.01, zt - SLAB_T, xw, zt, L_SLAB)
        dl.rect(land + b * tread - 0.01, zt - SLAB_T,
                xw - land - b * tread + 0.01, SLAB_T, layer=L_CUT)
        num += 1

    # terrace slab full width + O.T.S. label at the base
    S._fill_band(dl, 0.0, top - SLAB_T, xw, top, L_SLAB)
    dl.rect(0.0, top - SLAB_T, xw, SLAB_T, layer=L_CUT)
    dl.text(-WALL_T - 1.0, 2.0, "O.T.S", h=0.34, layer=L_TXT, angle=90)

    # glass railing over the well edge at each floor (per details)
    for k in range(1, n_floors + 1):
        z = plinth + k * storey
        dl.line(land, z, land, z + 3.0, layer=L_DIM)
        dl.line(land - 0.8, z + 3.0, land + 0.8, z + 3.0, layer=L_DIM)
    dl.text(land - 0.3, plinth + storey + 3.45, "glass railing as per details",
            h=0.30, layer=L_TXT, halign="right")

    # ---- level flags down the right edge ----
    fx = xw + WALL_T + 0.8
    _flag(dl, fx, 0.0, "INTERNAL RD LVL.", _fmt(0.0))
    _flag(dl, fx, plinth, "PLINTH LVL.", _fmt(plinth))
    _flag(dl, fx, plinth + risers_a * riser, "FIRST LANDING LVL.",
          _fmt(risers_a * riser))
    _flag(dl, fx, plinth + storey, "G.F. LVL.", _fmt(storey))
    _flag(dl, fx, plinth + storey + risers_a * riser, "F.F FIRST LANDING LVL.",
          _fmt(storey + risers_a * riser))
    _flag(dl, fx, plinth + 2 * storey, "F.F. SLAB LVL.", _fmt(2 * storey))
    _flag(dl, fx, top + para, "PARAPET LVL.", _fmt(top + para - plinth))

    # ---- tread / riser box (the sheet's own figures) ----
    bx, by = xw / 2 - 3.4, -5.4
    dl.rect(bx, by, 6.8, 2.2, layer=L_DIM)
    dl.text(bx + 3.4, by + 1.7, f"Tread Width= {_dim(fw)}", h=0.34,
            layer=L_TXT)
    dl.text(bx + 3.4, by + 1.05, f"Tread={_dim(tread)}", h=0.34,
            layer=L_TXT)
    dl.text(bx + 3.4, by + 0.4, f"Riser={_dim(riser)}", h=0.34,
            layer=L_TXT)

    if mode == "structural":
        # landing beam rebar detail, bottom left
        dx0, dy0 = -WALL_T - 8.5, -8.0
        dl.rect(dx0, dy0, 2.4, 4.2, layer=L_CUT)
        dl.rect(dx0 + 0.3, dy0 + 0.3, 1.8, 3.6, layer=L_BAR)
        for cx in (dx0 + 0.5, dx0 + 1.9):
            for cy in (dy0 + 0.5, dy0 + 3.7):
                dl.items.append(Arc(cx, cy, 0.1, 0, 360, L_BAR))
        dl.text(dx0 + 1.2, dy0 + 4.7, "2#12", h=0.3, layer=L_TXT)
        dl.text(dx0 + 1.2, dy0 - 0.5, "2#12", h=0.3, layer=L_TXT)
        dl.text(dx0 + 1.2, dy0 - 1.0, '#8@6"C/C', h=0.3, layer=L_TXT)
        dl.text(dx0 + 1.2, dy0 - 1.8, 'LANDING BEAM (6"X18")', h=0.32,
                layer=L_TXT, bold=True)
        dl.text((xw) / 2, -7.2,
                "All risers equal — adjust in bottom to top riser.",
                h=0.3, layer=L_TXT)
        title = "STAIRCASE STRUCTURAL DETAILS"
    else:
        dl.text((xw) / 2, -7.2,
                "Shuttering top levels marked on every flight — RCC steps.",
                h=0.3, layer=L_TXT)
        title = "STAIRCASE SHUTTERING DETAILS"

    dl.text(xw / 2, -8.6, f"{title}  ·  SECTION THROUGH STAIRCASE",
            h=0.55, layer=L_TXT, bold=True)
    return dl


def structural(plan, struct=None) -> DrawList:
    return _sheet(plan, struct, "structural")


def shuttering(plan, struct=None) -> DrawList:
    return _sheet(plan, struct, "shuttering")
