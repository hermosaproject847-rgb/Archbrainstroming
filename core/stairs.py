"""Stair geometry — straight, L (quarter-turn) and U (half-turn) stairs.

The reader only has to report the TYPOLOGY it can actually see in the sketch —
the footprint, which way the first flight runs, which way it climbs, which side
the turn is on, and the step counts. Every rectangle below is then DERIVED, so
two flights are always parallel, the landing always lands on the turn side, and
the well is always the true gap between the flights. Nothing here is guessed at
draw time.

Returned geometry (all feet, y-up):

    {"flights": [ {"rect": (x,y,w,h), "axis": "x"|"y", "dir": +1|-1,
                   "steps": n, "first": step_no} , ... ],
     "landing":  (x,y,w,h) | None,
     "winders":  [(x1,y1,x2,y2), ...],
     "well":     (x,y,w,h) | None,
     "arrows":   [ {"from": (x,y), "to": (x,y), "label": "UP"|"DN"} ]}
"""

from __future__ import annotations

# side -> unit vector pointing INTO that side
SIDE_VEC = {"left": (-1, 0), "right": (1, 0), "bottom": (0, -1), "top": (0, 1)}
OPPOSITE = {"left": "right", "right": "left", "top": "bottom", "bottom": "top"}


def _axis_of(side: str) -> str:
    return "x" if side in ("left", "right") else "y"


def build(s) -> dict:
    """`s` is a model.Stair. Returns the derived geometry dict."""
    typ = (s.type or "U").upper()
    if typ == "STRAIGHT":
        return _straight(s)
    if typ == "L":
        return _turn(s, half=False)
    if typ in ("U3", "3", "3FLIGHT", "THREE"):
        return _three_flight(s)
    return _turn(s, half=True)


DEFAULT_LANDING_FT = 3.0        # a landing is drawn square, 3'-0" typical


def _three_flight(s) -> dict:
    """Three flights around a well, with TWO landings.

    The common Indian residential stair: a flight along one side, a square
    landing, a short flight across the end, a second square landing, then the
    return flight. Both landings are SQUARE and their size is set on its own —
    a landing is not a tread, so it is never derived from the tread depth.
    """
    axis, d = _tread_dir(s)                       # how flights 1 and 3 run
    turn = s.turn_side if s.turn_side in SIDE_VEC else ""
    if not turn or _axis_of(turn) == axis:
        turn = "top" if axis == "x" else "right"

    # The landing is SQUARE, and the flights are as wide as it is deep, so
    # each flight runs into a landing without a step in the width. The whole
    # stair therefore wraps a rectangular well: two long flights, a landing at
    # each end of the short flight between them.
    run = s.w if axis == "x" else s.h            # along flights 1 and 3
    span = s.h if axis == "x" else s.w           # across them
    L = s.landing_size or s.landing_depth or DEFAULT_LANDING_FT
    L = max(1.5, min(L, run * 0.45, span * 0.45))

    body = run - L                               # length of flights 1 and 3
    mid_len = span - 2 * L                       # the short middle flight

    # the landing column sits at the turn end of the run
    if axis == "x":
        col = s.x + (body if d > 0 else 0)       # x of the landing column
        low = (s.x + (0 if d > 0 else L), s.y, body, L)          # bottom strip
        high = (s.x + (0 if d > 0 else L), s.y + span - L, body, L)  # top
        land_low = (col, s.y, L, L)
        land_high = (col, s.y + span - L, L, L)
        mid = (col, s.y + L, L, mid_len)
        mid_axis = "y"
    else:
        col = s.y + (body if d > 0 else 0)
        low = (s.x, s.y + (0 if d > 0 else L), L, body)
        high = (s.x + span - L, s.y + (0 if d > 0 else L), L, body)
        land_low = (s.x, col, L, L)
        land_high = (s.x + span - L, col, L, L)
        mid = (s.x + L, col, mid_len, L)
        mid_axis = "x"

    # flight 1 is the one the UP arrow enters — the far side from the turn
    tv = SIDE_VEC[turn]
    toward_high = (tv[1] > 0) if axis == "x" else (tv[0] > 0)
    if toward_high:
        f1, f3, la, lb = low, high, land_low, land_high
        mid_d = 1
    else:
        f1, f3, la, lb = high, low, land_high, land_low
        mid_d = -1

    n1 = max(2, s.steps_f1 or s.treads)
    n3 = max(2, s.steps_f2 or s.treads)
    n2 = max(1, s.steps_f3 or 2)                 # the short middle flight

    first = s.start_step
    flights = [
        {"rect": f1, "axis": axis, "dir": d, "steps": n1, "first": first},
        {"rect": mid, "axis": mid_axis, "dir": mid_d, "steps": n2,
         "first": (first + n1) if first else 0},
        {"rect": f3, "axis": axis, "dir": -d, "steps": n3,
         "first": (first + n1 + n2) if first else 0},
    ]

    return {"flights": flights,
            "landing": la,
            "landings": [la, lb],
            "winders": [],
            "well": None,
            "arrows": _arrows(s, [flights[0], flights[2]], True)}


# ------------------------------------------------------------------ helpers
def _tread_dir(s) -> tuple[str, int]:
    """(axis, direction) that flight 1 climbs, from the side the UP arrow enters."""
    ux, uy = SIDE_VEC.get(s.up_from, (0, -1))    # default: entered from below
    # entering FROM the bottom means climbing TOWARDS the top
    return ("x", -ux) if ux else ("y", -uy)


def _widths(s, span: float) -> tuple[float, float]:
    """(flight_width, well_gap) across the run, given the total span."""
    fw, wg = s.flight_width or 0.0, s.well_gap or 0.0
    if fw > 0 and wg <= 0:
        wg = max(0.0, span - 2 * fw)
    elif wg > 0 and fw <= 0:
        fw = max(0.1, (span - wg) / 2.0)
    elif fw <= 0 and wg <= 0:
        wg = min(1.5, span * 0.22)          # a typical stair well
        fw = (span - wg) / 2.0
    if 2 * fw + wg > span:                  # never overflow the footprint
        fw = (span - min(wg, span * 0.4)) / 2.0
        wg = span - 2 * fw
    return fw, wg


# ---------------------------------------------------------------- straight
def _straight(s) -> dict:
    axis, d = _tread_dir(s)
    r = (s.x, s.y, s.w, s.h)
    start = (s.x + (s.w if (axis == "x" and d < 0) else 0),
             s.y + (s.h if (axis == "y" and d < 0) else 0))
    run = s.w if axis == "x" else s.h
    end = (start[0] + d * run, start[1]) if axis == "x" else (start[0], start[1] + d * run)
    inset = 0.12
    a = (start[0] + (end[0] - start[0]) * inset, start[1] + (end[1] - start[1]) * inset)
    b = (start[0] + (end[0] - start[0]) * 0.9, start[1] + (end[1] - start[1]) * 0.9)
    return {"flights": [{"rect": r, "axis": axis, "dir": d,
                         "steps": max(2, s.steps_f1 or s.treads),
                         "first": s.start_step}],
            "landing": None, "winders": [], "well": None,
            "arrows": [{"from": a, "to": b, "label": s.up_label or "UP"}]}


# ------------------------------------------------------------- L and U turns
def _turn(s, half: bool) -> dict:
    """L = one turn, flights perpendicular.  U = half turn, flights parallel."""
    axis, d = _tread_dir(s)                       # how flight 1 runs
    # A reading can carry anything — "none", a typo, nothing at all — so the
    # turn side is sanitised rather than trusted; an unknown value must not
    # take the drawing down.
    turn = s.turn_side if s.turn_side in SIDE_VEC else ""
    if not turn or _axis_of(turn) == axis:
        # the turn is off the END of flight 1, never along its run
        turn = "top" if axis == "x" else "right"

    # ---- split the footprint: landing at the far end of the run ----------
    run_len = s.w if axis == "x" else s.h
    span = s.h if axis == "x" else s.w            # across the run
    land = s.landing_depth or min(span if half else run_len * 0.4,
                                  max(3.0, run_len * 0.35))
    land = min(land, run_len * 0.6)
    body = run_len - land                          # length available to flights

    if axis == "x":
        lx = s.x + (body if d > 0 else 0)
        landing = (lx, s.y, land, s.h)
        bx = s.x + (0 if d > 0 else land)
        body_rect = (bx, s.y, body, s.h)
    else:
        ly = s.y + (body if d > 0 else 0)
        landing = (s.x, ly, s.w, land)
        by = s.y + (0 if d > 0 else land)
        body_rect = (s.x, by, s.w, body)

    bx, by, bw, bh = body_rect
    fw, wg = _widths(s, bh if axis == "x" else bw)

    # ---- the two flights, either side of the well -----------------------
    if axis == "x":
        near = (bx, by, bw, fw)                      # low side
        far = (bx, by + fw + wg, bw, fw)             # high side
        well = (bx, by + fw, bw, wg)
    else:
        near = (bx, by, fw, bh)
        far = (bx + fw + wg, by, fw, bh)
        well = (bx + fw, by, wg, bh)

    # flight 1 is the one the UP arrow enters: the turn side is where it ENDS,
    # so flight 1 sits on the far side FROM the turn, and flight 2 beside it.
    tv = SIDE_VEC[turn]
    if axis == "x":
        f1, f2 = (near, far) if tv[1] < 0 else (far, near)
    else:
        f1, f2 = (near, far) if tv[0] < 0 else (far, near)

    n1 = max(2, s.steps_f1 or s.treads)
    n2 = max(2, s.steps_f2 or s.treads)
    wind = max(0, int(s.winders or 0))

    flights = [{"rect": f1, "axis": axis, "dir": d, "steps": n1,
                "first": s.start_step}]
    if half:
        flights.append({"rect": f2, "axis": axis, "dir": -d, "steps": n2,
                        "first": (s.start_step + n1 + wind) if s.start_step else 0})
    else:
        # L: the second flight runs along the landing, perpendicular
        ax2 = "y" if axis == "x" else "x"
        d2 = 1 if turn in ("top", "right") else -1
        flights.append({"rect": landing, "axis": ax2, "dir": d2, "steps": n2,
                        "first": (s.start_step + n1) if s.start_step else 0})

    return {"flights": flights,
            "landing": landing,
            "winders": (_winders(landing, well, axis, d, wind,
                                 getattr(s, "winder_style", "straight"))
                        if half else []),
            "well": well if (s.well and wg > 0.05 and half) else None,
            "arrows": _arrows(s, flights, half)}


def _along(path, t: float):
    """Point a fraction `t` along a polyline."""
    segs = [(path[i], path[i + 1]) for i in range(len(path) - 1)]
    lens = [((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5 for a, b in segs]
    total = sum(lens) or 1e-9
    want = t * total
    for (a, b), L in zip(segs, lens):
        if want <= L or L == 0:
            f = (want / L) if L else 0.0
            return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)
        want -= L
    return path[-1]


def _winders(landing, well, axis, d, n, style="straight"):
    """Treads across the turn (0 winders = a flat landing).

    `straight` — the usual drafting convention: the steps keep running square
    across the landing, perpendicular to the way the walk turns.
    `fan` — true radiating winders converging on the well's landing-side edge.
    Either way every line stays inside the stair footprint.
    """
    if n <= 0 or well is None:
        return []
    lx, ly, lw, lh = landing
    wx, wy, ww, wh = well

    if style != "fan":
        out = []
        for i in range(1, n + 1):
            t = i / (n + 1)
            if axis == "x":                       # flights stacked in y
                y = ly + t * lh
                out.append((lx, y, lx + lw, y))
            else:                                 # flights stacked in x
                x = lx + t * lw
                out.append((x, ly, x, ly + lh))
        return out

    if axis == "x":
        if d > 0:                                    # landing at the right
            pivot = (lx, wy + wh / 2)
            path = [(lx, ly + lh), (lx + lw, ly + lh), (lx + lw, ly), (lx, ly)]
        else:                                        # landing at the left
            pivot = (lx + lw, wy + wh / 2)
            path = [(lx + lw, ly + lh), (lx, ly + lh), (lx, ly), (lx + lw, ly)]
    else:
        if d > 0:                                    # landing at the top
            pivot = (wx + ww / 2, ly)
            path = [(lx, ly), (lx, ly + lh), (lx + lw, ly + lh), (lx + lw, ly)]
        else:                                        # landing at the bottom
            pivot = (wx + ww / 2, ly + lh)
            path = [(lx, ly + lh), (lx, ly), (lx + lw, ly), (lx + lw, ly + lh)]

    out = []
    for i in range(1, n + 1):
        e = _along(path, i / (n + 1))
        out.append((pivot[0], pivot[1], e[0], e[1]))
    return out


def _arrows(s, flights, half):
    """UP along flight 1; DN back along flight 2 (a mid-floor plan shows both)."""
    def path(f, shrink=0.12):
        x, y, w, h = f["rect"]
        if f["axis"] == "x":
            a = (x + (w * (1 - shrink) if f["dir"] < 0 else w * shrink), y + h / 2)
            b = (x + (w * shrink if f["dir"] < 0 else w * (1 - shrink)), y + h / 2)
        else:
            a = (x + w / 2, y + (h * (1 - shrink) if f["dir"] < 0 else h * shrink))
            b = (x + w / 2, y + (h * shrink if f["dir"] < 0 else h * (1 - shrink)))
        return {"from": a, "to": b}

    out = [{**path(flights[0]), "label": s.up_label or "UP"}]
    if half and s.show_dn and len(flights) > 1:
        out.append({**path(flights[1]), "label": s.dn_label or "DN"})
    return out
