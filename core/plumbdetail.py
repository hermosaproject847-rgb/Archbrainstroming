"""Plumbing INSTALLATION DETAIL sheet.

The plumbing layout says WHERE each fixture and point sits; this sheet says HOW
each one is set out on the wall — the standard mounting heights and the inlet /
outlet centre-lines, called out in red with a leader to the fixture, exactly the
way a site plumbing detail reads (WC top @ 1'-6", flush-tank C/L @ 3'-0",
health-faucet @ 1'-6", basin inlet @ 1'-9" / outlet @ 1'-6", and so on).

Nothing new is invented: the fixtures and their positions come straight from the
plan the software already produced; only the standard set-out notes are added.
"""

from __future__ import annotations

from .draw import DrawList

# standard set-out notes per fixture type (feet-inch, the site convention)
DETAIL = {
    "wc":    ["W.C — connect to P / S-TRAP",
              "W.C top @ ht 1'-6\" from FFL",
              "C/L for flush tank / cistern @ ht 3'-0\" from FFL",
              "Health faucet @ ht 1'-6\" from FFL"],
    "ewc":   ["E.W.C — P/S-TRAP",
              "Standing cistern @ 1200 mm ht from FFL",
              "Health faucet @ ht 1'-6\" from FFL",
              "C/L for outlet @ ht 1'-6\" from FFL"],
    "basin": ["WASH BASIN — rim @ 800-850 from FFL",
              "C/L for inlet @ ht 1'-9\" from FFL",
              "C/L for outlet @ ht 1'-6\" from FFL",
              "2-way bibcock w/ health faucet @ 1'-6\""],
    "urinal": ["URINAL — lip @ ht 2'-0\" from FFL",
               "Flush spreader C/L @ ht 3'-6\" from FFL",
               "Waste C/L @ ht 1'-4\" from FFL"],
    "shower": ["SHOWER rose @ ht 7'-0\" (2100) from FFL",
               "Diverter / mixer C/L @ ht 3'-3\" (1000) from FFL"],
    "sink":  ["SINK cock / wall mixer @ ht 3'-6\" from FFL",
              "Waste (bottle-trap) C/L @ ht 1'-6\" from FFL"],
}

L_N, L_L, L_DIM = "PDET-NOTE", "PDET-LEAD", "PDET-LEAD"


def _kind(k: str):
    k = (k or "").lower()
    if "ewc" in k or "western" in k:
        return "ewc"
    if k.startswith("wc") or k == "wc" or "indian" in k or "iwc" in k:
        return "wc"
    if "basin" in k:
        return "basin"
    if "urinal" in k:
        return "urinal"
    if "shower" in k:
        return "shower"
    if "sink" in k or "counter" in k:
        return "sink"
    return None


def _room(plan, name):
    for r in plan.rooms:
        if r.name == name:
            return r
    return None


def build(plan) -> DrawList:
    """A CLEAN toilet-block detail — walls, doors and the sanitary fixtures
    only, with the red set-out notes on each fixture. The full pipe network and
    keynotes are deliberately left OFF so the sheet reads exactly like a site
    plumbing detail."""
    from . import engine, plumbing as PL
    from .draw import Arc
    dl = DrawList()
    engine.draw_walls(plan, dl)
    engine.draw_windows(plan, dl)
    engine.draw_doors(plan, dl)
    engine.draw_rooms(plan, dl)

    keep = [f for f in plan.furniture if PL.is_plumb_fixture(f.kind)]
    saved = plan.furniture
    plan.furniture = keep
    try:
        engine.draw_furniture(plan, dl)
    finally:
        plan.furniture = saved
    # a small trap / connection marker on each fixture
    for f in keep:
        cx, cy = f.centre
        dl.items.append(Arc(cx, cy, 0.16, 0, 360, "PDET-TRAP"))

    # fixtures that carry a detail, split to the nearer side of the plan and
    # laid out as non-overlapping note columns just outside the building
    fx = [f for f in keep if DETAIL.get(_kind(f.kind))]
    if not fx:
        return dl
    xs = [w.x1 for w in plan.walls] + [w.x2 for w in plan.walls]
    ys = [w.y1 for w in plan.walls] + [w.y2 for w in plan.walls]
    minx, maxx, maxy = min(xs), max(xs), max(ys)
    left = [f for f in fx if (f.centre[0] - minx) <= (maxx - f.centre[0])]
    right = [f for f in fx if f not in left]
    _column(dl, plan, left, minx - 2.6, "right", maxy)
    _column(dl, plan, right, maxx + 2.6, "left", maxy)
    return dl


def _column(dl, plan, fixtures, col_x, align, top_y):
    """A tidy vertical stack of note blocks down one side, each with a leader to
    its fixture and a set-out dimension. Blocks are pushed down so they never
    overlap."""
    if not fixtures:
        return
    from .draw import CHAR_W
    h = 0.42
    gap = h * 1.32
    # widest note in this column → how far the text reaches past the column line
    reach = max(len(nt) for f in fixtures for nt in DETAIL[_kind(f.kind)]) \
        * h * CHAR_W + 0.5
    far = col_x - reach if align == "right" else col_x + reach
    y_hi = y_lo = None
    cursor = top_y + 1.5
    for f in sorted(fixtures, key=lambda f: -f.centre[1]):
        cx, cy = f.centre
        notes = DETAIL[_kind(f.kind)]
        bh = len(notes) * gap
        top = min(cy + bh / 2, cursor)               # near the fixture, but…
        cursor = top - bh - gap * 0.8                # …clear of the block above
        mid = top - bh / 2
        y_hi = top if y_hi is None else max(y_hi, top)
        y_lo = top - bh if y_lo is None else min(y_lo, top - bh)
        # leader: fixture → column, with a target cross on the fixture
        dl.line(cx, cy, col_x, mid, layer=L_L)
        dl.line(cx - 0.12, cy - 0.12, cx + 0.12, cy + 0.12, layer=L_L)
        dl.line(cx - 0.12, cy + 0.12, cx + 0.12, cy - 0.12, layer=L_L)
        tx = col_x + (0.25 if align == "left" else -0.25)
        for i, note in enumerate(notes):
            dl.text(tx, top - i * gap, note, h=h, layer=L_N,
                    halign=align, bold=(i == 0))
        # set-out dimension to the nearest vertical wall
        wx = _nearest_v_wall(plan, cx, cy)
        if wx is not None:
            yy = cy - 0.85
            dl.line(wx, yy, cx, yy, layer=L_DIM)
            for xx in (wx, cx):
                dl.line(xx, yy - 0.16, xx, yy + 0.16, layer=L_DIM)
            s = str(round(abs(cx - wx) * 304.8))
            w = len(s) * 0.32 * CHAR_W + 0.2
            mx = (wx + cx) / 2
            dl.fill_rect(mx - w / 2, yy - 0.27, w, 0.48, color="#ffffff",
                         layer=L_DIM)
            dl.text(mx, yy - 0.04, s, h=0.3, layer=L_DIM)
    # a light rule at the far edge of the text — frames the column AND makes the
    # sheet reserve room for it (bounds only see line endpoints, not text width)
    if y_hi is not None:
        dl.line(far, y_lo - 0.4, far, y_hi + 0.4, layer=L_L)


def _nearest_v_wall(plan, cx, cy):
    best = None
    for w in plan.walls:
        if abs(w.x1 - w.x2) < 0.01:                    # vertical wall
            if min(w.y1, w.y2) - 0.6 <= cy <= max(w.y1, w.y2) + 0.6:
                d = abs(w.x1 - cx)
                if 0.05 < d and (best is None or d < best[0]):
                    best = (d, w.x1)
    return best[1] if best else None
