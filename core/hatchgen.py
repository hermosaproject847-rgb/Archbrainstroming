"""Hatch pattern helpers.

A `Hatch` primitive names a filled region + a pattern KIND. Here we:
  * expand it to the equivalent line / speck geometry for the SVG / PNG / PDF
    preview (so the screen looks exactly as before), and
  * map the kind to a real DXF hatch pattern so the exported DXF carries ONE
    associative HATCH object per region instead of loose exploded lines.
"""

from __future__ import annotations

import math

# kind -> (dxf pattern name, angle°, scale factor applied to the region's step)
DXF_PATTERN = {
    "diag45":  ("ANSI31", 0.0, 8.0),      # 45° lines  (brick / footing / earth)
    "diag135": ("ANSI31", 90.0, 8.0),     # 135° lines (earth / screed)
    "concrete": ("AR-CONC", 0.0, 0.9),    # concrete aggregate (PCC)
    "rubble":  ("GRAVEL", 0.0, 1.6),      # broken-stone soling
    "pebble":  ("GRAVEL", 0.0, 1.3),      # rounded pebble soling
    "cross":   ("ANSI37", 0.0, 8.0),      # cross-hatch (sunk slab)
    # orthogonal single-direction line grids (tile joints, wood planks) — these
    # are emitted with a CUSTOM pattern definition in the DXF exporter so a whole
    # room's tiling is ONE hatch object, never loose lines
    "vlines":  ("_VLINES", 90.0, 1.0),    # vertical joint lines
    "hlines":  ("_HLINES", 0.0, 1.0),     # horizontal joint / plank lines
}


def _bbox(loops):
    xs = [p[0] for lp in loops for p in lp]
    ys = [p[1] for lp in loops for p in lp]
    return min(xs), min(ys), max(xs), max(ys)


def _poly(loops):
    try:
        from shapely.geometry import Polygon
        if len(loops) == 1:
            return Polygon(loops[0])
        return Polygon(loops[0], loops[1:])
    except Exception:
        return None


def _inside(poly, x, y):
    if poly is None:
        return True
    try:
        from shapely.geometry import Point
        return poly.contains(Point(x, y))
    except Exception:
        return True


def _diag_lines(dl, loops, layer, step, slope):
    """45° (slope +1) or 135° (slope -1) lines clipped to the region polygon."""
    x0, y0, x1, y1 = _bbox(loops)
    poly = _poly(loops)
    big = (x1 - x0) + (y1 - y0) + 2
    if slope >= 0:
        d, end = x0 - y1, x1 - y0
    else:
        d, end = x0 + y0, x1 + y1
    while d <= end:
        if slope >= 0:
            a, b = (x0 - big, (x0 - big) - d), (x1 + big, (x1 + big) - d)
        else:
            a, b = (x0 - big, d - (x0 - big)), (x1 + big, d - (x1 + big))
        if poly is not None:
            try:
                from shapely.geometry import LineString
                inter = poly.intersection(LineString([a, b]))
                for g in getattr(inter, "geoms", [inter]):
                    if getattr(g, "geom_type", "") == "LineString" and not g.is_empty:
                        c = list(g.coords)
                        if len(c) >= 2:
                            dl.line(c[0][0], c[0][1], c[-1][0], c[-1][1],
                                    layer=layer)
            except Exception:
                dl.line(a[0], a[1], b[0], b[1], layer=layer)
        else:
            dl.line(a[0], a[1], b[0], b[1], layer=layer)
        d += step


def _ortho_lines(dl, loops, layer, step, vertical, phase=None):
    """Vertical (or horizontal) parallel lines at `step` spacing, clipped to the
    region polygon — the preview expansion of the tile-joint / plank hatch.
    `phase` anchors the lattice at the tiling origin so neighbouring rooms'
    grids LINE UP instead of each starting at its own bbox edge."""
    x0, y0, x1, y1 = _bbox(loops)
    poly = _poly(loops)
    step = max(step, 1e-3)
    from shapely.geometry import LineString

    def seg(a, b):
        if poly is None:
            dl.line(a[0], a[1], b[0], b[1], layer=layer)
            return
        try:
            inter = poly.intersection(LineString([a, b]))
            for g in getattr(inter, "geoms", [inter]):
                if getattr(g, "geom_type", "") == "LineString" and not g.is_empty:
                    c = list(g.coords)
                    if len(c) >= 2:
                        dl.line(c[0][0], c[0][1], c[-1][0], c[-1][1],
                                layer=layer)
        except Exception:
            dl.line(a[0], a[1], b[0], b[1], layer=layer)

    if vertical:
        v = x0 if phase is None else x0 + ((phase - x0) % step)
        while v <= x1 + 1e-6:
            seg((v, y0 - 1), (v, y1 + 1))
            v += step
    else:
        v = y0 if phase is None else y0 + ((phase - y0) % step)
        while v <= y1 + 1e-6:
            seg((x0 - 1, v), (x1 + 1, v))
            v += step


def _concrete(dl, loops, layer, step):
    x0, y0, x1, y1 = _bbox(loops)
    poly = _poly(loops)
    r0, c0 = 0, 0
    s = max(step, 1e-3)                        # spacing = step (already scaled)
    t = s * 0.14                               # aggregate size scales with step
    yy = y0 + s * 0.6
    while yy < y1 - s * 0.25:
        xx = x0 + s * (0.6 + 0.4 * (r0 % 2))
        while xx < x1 - s * 0.25:
            if _inside(poly, xx, yy):
                j = ((r0 * 7 + c0 * 13) % 5) * (t * 0.9)
                dl.line(xx - t, yy - t, xx + t, yy - t, layer=layer)
                dl.line(xx + t, yy - t, xx, yy + t + j, layer=layer)
                dl.line(xx, yy + t + j, xx - t, yy - t, layer=layer)
                dl.arc(xx + s * 0.44, yy + s * 0.1, t * 0.45, 0, 360,
                       layer=layer)
            xx += s
            c0 += 1
        yy += s
        r0 += 1


def _rubble(dl, loops, layer, step):
    x0, y0, x1, y1 = _bbox(loops)
    poly = _poly(loops)
    stone = max(step * 1.1, 1e-3)              # stone width scales with step
    yy = y0
    while yy < y1 - stone * 0.1:
        band = min(stone * 1.15, y1 - yy)
        x = x0 + stone * 0.1
        while x < x1 - stone * 0.1:
            wsto = min(stone, x1 - x)
            cxs, cys = x + wsto / 2, yy + band / 2
            if _inside(poly, cxs, cys):
                pts = [(x, yy + band * 0.12), (x + wsto * 0.35, yy + band * 0.02),
                       (x + wsto * 0.8, yy + band * 0.2),
                       (x + wsto, yy + band * 0.75),
                       (x + wsto * 0.45, yy + band - band * 0.05),
                       (x + wsto * 0.08, yy + band * 0.6)]
                for a, b in zip(pts, pts[1:] + pts[:1]):
                    dl.line(a[0], a[1], b[0], b[1], layer=layer)
            x += wsto + stone * 0.12
        yy += band + stone * 0.04


def _pebble(dl, loops, layer, step):
    x0, y0, x1, y1 = _bbox(loops)
    poly = _poly(loops)
    r = min(step, (y1 - y0) * 0.42)
    if r <= 1e-3:
        return
    gy = y0 + r
    row = 0
    while gy < y1:
        gx = x0 + r + (r if row % 2 else 0)
        while gx < x1 - r * 0.4:
            if _inside(poly, gx, gy):
                dl.arc(gx, gy, r, 0, 360, layer=layer)
            gx += 1.7 * r
        gy += 1.5 * r
        row += 1


def render_preview(dl, hatch):
    """Expand a Hatch into equivalent line / arc geometry on its layer."""
    k = hatch.kind
    if k == "diag45":
        _diag_lines(dl, hatch.loops, hatch.layer, hatch.step, 1)
    elif k == "diag135":
        _diag_lines(dl, hatch.loops, hatch.layer, hatch.step, -1)
    elif k == "concrete":
        _concrete(dl, hatch.loops, hatch.layer, hatch.step)
    elif k == "rubble":
        _rubble(dl, hatch.loops, hatch.layer, hatch.step)
    elif k == "pebble":
        _pebble(dl, hatch.loops, hatch.layer, hatch.step)
    elif k == "cross":                       # sunk slab — a real cross-hatch
        _diag_lines(dl, hatch.loops, hatch.layer, hatch.step, 1)
        _diag_lines(dl, hatch.loops, hatch.layer, hatch.step, -1)
    elif k == "vlines":
        _ortho_lines(dl, hatch.loops, hatch.layer, hatch.step, True,
                     getattr(hatch, "phase", None))
    elif k == "hlines":
        _ortho_lines(dl, hatch.loops, hatch.layer, hatch.step, False,
                     getattr(hatch, "phase", None))
    else:
        _diag_lines(dl, hatch.loops, hatch.layer, hatch.step, 1)
