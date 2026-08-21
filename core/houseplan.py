"""Offline QUESTIONNAIRE -> FLOOR PLAN generator.

Given a small brief (plot size, set-backs, floors, and the room programme) this
lays a bungalow floor plan out DETERMINISTICALLY - no AI, no network - using
standard Indian residential room sizes (NBC 2016 minimums + typical practice).

The plot is filled with a squarified treemap so rooms come out close to their
target proportions with no left-over gaps; the room list is ordered so related
spaces (a bedroom and its attached toilet, the wet core) land next to each
other. Walls are then built from the room edges (shared edge = 115 mm internal,
outer edge = 230 mm external), and each room gets a door to its neighbour and a
window on its longest external wall.

The output is the SAME plan dict the sketch reader produces, so it flows
straight into the section / elevation / beam / BOQ pipeline.
"""

from __future__ import annotations

import math

# ---- standard room sizes (feet) : (target_w, target_d, min_area_sqft) --------
# targets are typical; areas are scaled to fill the plot but never below min.
STD = {
    "living":        (16, 13, 120),
    "dining":        (12, 10, 90),
    "living_dining": (18, 13, 170),
    "kitchen":       (10, 9, 55),
    "utility":       (6, 5, 25),
    "pooja":         (4.5, 4, 12),
    "store":         (6, 5, 24),
    "powder":        (4.5, 3.5, 14),
    "bath":          (7, 5, 30),
    "bath_attached": (8, 5, 30),
    "stair":         (8, 11, 80),
    "lobby":         (7, 6, 40),
    "master":        (14, 12, 130),
    "bedroom":       (12, 11, 100),
    "study":         (10, 9, 80),
    "balcony":       (10, 5, 0),
}


def _std(kind):
    return STD.get(kind, STD["bedroom"])


def _area(kind):
    w, d, _ = _std(kind)
    return w * d


# ---------------------------------------------------------------- programme
def _programme(a):
    """Ordered list of rooms to place, from the questionnaire answers `a`.
    Order matters: the treemap keeps consecutive rooms spatially adjacent, so
    we interleave each bedroom with its own toilet and keep the wet core
    together."""
    rooms = []                      # (name, kind, parent_or_None)
    n_bed = int(a.get("bedrooms", 2) or 0)
    master = bool(a.get("master", True))
    att = a.get("attached", "all")   # "all" | "master" | "none"
    floors = max(1, int(a.get("floors", 1) or 1))

    # public / social zone first (lands near the entry side)
    if a.get("living_dining_combined"):
        rooms.append(("Living / Dining", "living_dining", None))
    else:
        rooms.append(("Living Room", "living", None))
        if a.get("dining", True):
            rooms.append(("Dining", "dining", None))
    rooms.append(("Kitchen", "kitchen", None))
    if a.get("utility"):
        rooms.append(("Utility", "utility", None))
    if a.get("pooja"):
        rooms.append(("Pooja", "pooja", None))
    if a.get("store"):
        rooms.append(("Store", "store", None))
    if a.get("powder", True):
        rooms.append(("Powder Toilet", "powder", None))
    if floors > 1 or a.get("staircase", True):
        rooms.append(("Staircase", "stair", None))
    if a.get("common_bath"):
        rooms.append(("Common Bath", "bath", None))

    # private zone: each bedroom, its attached toilet right after it
    for i in range(n_bed):
        is_master = master and i == 0
        nm = "Master Bedroom" if is_master else f"Bedroom {i + 1}"
        rooms.append((nm, "master" if is_master else "bedroom", None))
        want = (att == "all") or (att == "master" and is_master)
        if want:
            rooms.append((f"Toilet ({nm})", "bath_attached", nm))
    return rooms


# ---------------------------------------------------------------- squarify
def _worst(row, length, scale):
    s = sum(row)
    if s <= 0 or length <= 0:
        return math.inf
    mx, mn = max(row), min(row)
    a = (length * length * mx) / (s * s)
    b = (s * s) / (length * length * mn)
    return max(a * scale, b / scale) if scale else max(a, b)


def _squarify(items, x, y, w, h, out):
    """Classic squarified treemap. `items` = list of dicts with 'val' (area);
    fills the rect (x,y,w,h) and appends {'item':.., 'rect':(x,y,w,h)}."""
    items = [it for it in items if it["val"] > 0]
    if not items:
        return
    if len(items) == 1:
        out.append((items[0], (x, y, w, h)))
        return
    total = sum(it["val"] for it in items)
    # normalise areas to the rect
    scale = (w * h) / total
    vals = [it["val"] * scale for it in items]

    i = 0
    cx, cy, cw, ch = x, y, w, h
    while i < len(items):
        short = min(cw, ch)
        row_idx = [i]
        row_val = [vals[i]]
        j = i + 1
        cur = _worst(row_val, short, 1.0)
        while j < len(items):
            trial = row_val + [vals[j]]
            nw = _worst(trial, short, 1.0)
            if nw > cur:
                break
            row_val = trial
            row_idx.append(j)
            cur = nw
            j += 1
        # lay this row along the shorter side
        rsum = sum(row_val)
        if cw <= ch:
            rh = rsum / cw if cw else 0
            ox = cx
            for k, v in zip(row_idx, row_val):
                rw = (v / rsum) * cw if rsum else 0
                out.append((items[k], (ox, cy, rw, rh)))
                ox += rw
            cy += rh
            ch -= rh
        else:
            rw = rsum / ch if ch else 0
            oy = cy
            for k, v in zip(row_idx, row_val):
                rh = (v / rsum) * ch if rsum else 0
                out.append((items[k], (cx, oy, rw, rh)))
                oy += rh
            cx += rw
            cw -= rw
        i = j


def _snap(v, g=0.25):
    return round(v / g) * g


def _layout_spine(a, bx, by, bw, bd, floors):
    """A structured bungalow layout: a Living room across the entry front, a
    central circulation PASSAGE running back from it, and the remaining rooms
    stacked in the two columns either side of the passage - service rooms in
    front, bedrooms at the back with their attached toilet on the outer wall.
    Every room ends up sharing a wall with the passage or the living room, so
    doors land where they belong."""
    rooms = []

    def add(name, kind, x, y, w, h, parent=None):
        if w > 0.4 and h > 0.4:
            rooms.append({"name": name, "kind": kind, "parent": parent,
                          "x": x, "y": y, "w": w, "h": h})

    combined = bool(a.get("living_dining_combined"))
    n_bed = int(a.get("bedrooms", 2) or 0)
    master = bool(a.get("master", True))
    att = a.get("attached", "all")

    # ---- front public band (at the entry) ----
    ld = min(max(bd * 0.30, 11.0), 15.0)
    if combined:
        add("Living / Dining", "living_dining", bx, by, bw, ld)
    else:
        add("Living Room", "living", bx, by, bw, ld)

    col_top = by + ld
    col_h = bd - ld
    pass_w = 3.5 if bw > 16 else 3.0
    cw = (bw - pass_w) / 2.0
    lx = bx
    px = bx + cw
    rx = bx + cw + pass_w
    add("Passage", "lobby", px, col_top, pass_w, col_h)

    # ---- service rooms (front cells of the columns) ----
    service = []
    if not combined and a.get("dining", True):
        service.append(("Dining", "dining"))
    service.append(("Kitchen", "kitchen"))
    if floors > 1 or a.get("staircase", True):
        service.append(("Staircase", "stair"))
    if a.get("pooja"):
        service.append(("Pooja Room", "pooja"))
    if a.get("store"):
        service.append(("Store", "store"))
    if a.get("utility"):
        service.append(("Utility", "utility"))
    if a.get("powder", True):
        service.append(("Powder Toilet", "powder"))
    if a.get("common_bath"):
        service.append(("Common Bath", "bath"))

    beds = []
    for i in range(n_bed):
        is_m = master and i == 0
        nm = "Master Bedroom" if is_m else f"Bedroom {i + 1}"
        want = (att == "all") or (att == "master" and is_m)
        beds.append((nm, "master" if is_m else "bedroom", want))

    # distribute: services fill the FRONT of each column, bedrooms the BACK
    left, right = [], []
    t = 0
    for s in service:
        (left if t == 0 else right).append(("room", s[0], s[1]))
        t ^= 1
    t = 0
    for b in beds:
        (left if t == 0 else right).append(("bed", b[0], b[1], b[2]))
        t ^= 1

    def cell_area(c):
        if c[0] == "room":
            return _area(c[2])
        return _area(c[2]) + (_area("bath_attached") if c[3] else 0)

    for cells, colx, side in ((left, lx, "L"), (right, rx, "R")):
        if not cells:
            continue
        svc = [c for c in cells if c[0] == "room"]
        bed = [c for c in cells if c[0] == "bed"]
        # service cells take a sensible depth (never a sliver); bedrooms share
        # whatever depth is left, so a bedroom is always full column width
        sdep = []
        for c in svc:
            d = max(_std(c[2])[1], 5.0)
            sdep.append(d)
        # keep at least 11 ft of depth for each bedroom cell
        min_bed = 11.0 * len(bed)
        if sum(sdep) + min_bed > col_h and sdep:
            k = max(0.4, (col_h - min_bed) / sum(sdep))
            sdep = [max(4.5, s * k) for s in sdep]
        rem = col_h - sum(sdep)

        y = col_top
        for c, dep in zip(svc, sdep):
            add(c[1], c[2], colx, y, cw, dep)
            y += dep
        for bi, c in enumerate(bed):
            ch = (col_top + col_h - y) if bi == len(bed) - 1 else \
                 rem / max(1, len(bed))
            nm, kd, want = c[1], c[2], c[3]
            if want and ch > 9:
                td = min(5.5, ch * 0.38)       # toilet stacked at the BACK
                add(nm, kd, colx, y, cw, ch - td)
                add(f"Toilet ({nm})", "bath_attached", colx, y + ch - td,
                    cw, td, parent=nm)
            else:
                add(nm, kd, colx, y, cw, ch)
            y += ch
    return rooms


# ---------------------------------------------------------------- build
def build(answers: dict) -> dict:
    a = dict(answers or {})
    pw = float(a.get("plot_w", 30) or 30)
    pd = float(a.get("plot_d", 40) or 40)
    sf = float(a.get("setback_front", 0) or 0)
    sr = float(a.get("setback_rear", 0) or 0)
    sl = float(a.get("setback_left", 0) or 0)
    srr = float(a.get("setback_right", 0) or 0)
    floors = max(1, int(a.get("floors", 1) or 1))
    ext_t = 9.0
    int_t = 4.5

    bx, by = sl, sf
    bw = max(6.0, pw - sl - srr)
    bd = max(6.0, pd - sf - sr)

    raw = _layout_spine(a, bx, by, bw, bd, floors)

    # snap rectangles to a 3-inch grid for tidy dimensions
    rooms = []
    for it in raw:
        x0, y0 = _snap(it["x"]), _snap(it["y"])
        x1, y1 = _snap(it["x"] + it["w"]), _snap(it["y"] + it["h"])
        rooms.append({"name": it["name"], "kind": it["kind"],
                      "parent": it.get("parent"),
                      "x": x0, "y": y0, "w": max(0.5, x1 - x0),
                      "h": max(0.5, y1 - y0)})

    walls, wall_id = _walls_from_rooms(rooms, bx, by, bw, bd, ext_t, int_t)
    openings = _openings(rooms, walls, a)

    room_out = []
    for r in rooms:
        room_out.append({
            "name": r["name"], "x": r["x"], "y": r["y"],
            "w": r["w"], "h": r["h"],
            "size_label": f'{_ftin(r["w"])} x {_ftin(r["h"])}',
            "open_area": False})

    stairs = []
    if floors > 1:
        st = next((r for r in rooms if r["kind"] == "stair"), None)
        if st:
            stairs.append({"x": st["x"] + 0.4, "y": st["y"] + 0.4,
                           "w": st["w"] - 0.8, "h": st["h"] - 0.8,
                           "type": "U", "up": "left"})

    plan = {
        "north_deg": 90,
        "plot": {"x": 0, "y": 0, "w": pw, "h": pd},
        "title": {"project": a.get("project", ""),
                  "plan_name": "GROUND FLOOR PLAN",
                  "plot_size": f"{_ftin(pw)} X {_ftin(pd)}",
                  "wall_note": "EXTERIOR WALLS 9\" THK., INTERNAL 4 1/2\" THK.",
                  "revision": "R0", "date": ""},
        "walls": walls,
        "rooms": room_out,
        "openings": openings,
        "stairs": stairs,
        "dims": [{"axis": "top", "at": 2, "ticks": [0, pw]},
                 {"axis": "left", "at": 2, "ticks": [0, pd]}],
        "notes": [
            f"Auto-generated from the design questionnaire ({len(room_out)} "
            f"rooms, {floors} floor(s)).",
            "Room sizes to NBC 2016 minimums + typical practice; refine as "
            "needed with the editing tools."],
        "meta": {"floors": floors, "source": "questionnaire"},
    }
    return plan


# --------------------------------------------------- walls from room edges
def _walls_from_rooms(rooms, bx, by, bw, bd, ext_t, int_t):
    """Every distinct room edge becomes a wall. An edge shared by two rooms is
    an internal partition; an edge on the plot's built envelope is external."""
    import collections
    EPS = 0.05
    verts = collections.defaultdict(list)     # vertical: x -> list of (y0,y1,room)
    horis = collections.defaultdict(list)     # horizontal: y -> (x0,x1,room)
    for r in rooms:
        x0, y0, x1, y1 = r["x"], r["y"], r["x"] + r["w"], r["y"] + r["h"]
        verts[round(x0, 2)].append((y0, y1, r["name"]))
        verts[round(x1, 2)].append((y0, y1, r["name"]))
        horis[round(y0, 2)].append((x0, x1, r["name"]))
        horis[round(y1, 2)].append((x0, x1, r["name"]))

    walls = []
    n = [0]

    def add(x1, y1, x2, y2, shared):
        length = math.hypot(x2 - x1, y2 - y1)
        if length < 0.4:
            return
        on_env = (abs(x1 - bx) < EPS and abs(x2 - bx) < EPS) or \
                 (abs(x1 - (bx + bw)) < EPS and abs(x2 - (bx + bw)) < EPS) or \
                 (abs(y1 - by) < EPS and abs(y2 - by) < EPS) or \
                 (abs(y1 - (by + bd)) < EPS and abs(y2 - (by + bd)) < EPS)
        ext = on_env or not shared
        n[0] += 1
        walls.append({"id": f"W{n[0]}", "x1": x1, "y1": y1, "x2": x2,
                      "y2": y2, "thickness_in": ext_t if ext else int_t,
                      "exterior": bool(ext)})

    # merge overlapping vertical segments at each x; a sub-range covered by two
    # rooms is a shared (internal) wall
    for x, segs in verts.items():
        _emit_axis(segs, lambda y0, y1, sh: add(x, y0, x, y1, sh))
    for y, segs in horis.items():
        _emit_axis(segs, lambda x0, x1, sh: add(x0, y, x1, y, sh))
    return walls, n[0]


def _emit_axis(segs, emit):
    """Given 1-D segments (a,b,room) on a line, emit maximal runs flagged as
    shared where >=2 rooms overlap."""
    pts = sorted(set([s[0] for s in segs] + [s[1] for s in segs]))
    i = 0
    while i < len(pts) - 1:
        lo, hi = pts[i], pts[i + 1]
        mid = (lo + hi) / 2
        cover = sum(1 for (a, b, _r) in segs if a - 1e-6 <= mid <= b + 1e-6)
        if cover >= 1:
            shared = cover >= 2
            # extend the run while the shared-state stays the same
            j = i + 1
            while j < len(pts) - 1:
                m2 = (pts[j] + pts[j + 1]) / 2
                c2 = sum(1 for (a, b, _r) in segs if a - 1e-6 <= m2 <= b + 1e-6)
                if (c2 >= 2) != shared or c2 < 1:
                    break
                j += 1
            emit(lo, pts[j], shared)
            i = j
        else:
            i += 1


# --------------------------------------------------- doors & windows
# how "public" a room is — a room's door prefers to open onto the lowest rank
PUBLIC_RANK = {"living_dining": 0, "living": 1, "dining": 2, "lobby": 3,
               "kitchen": 4, "utility": 5}


def _openings(rooms, walls, a):
    """One door per room, placed on the wall it SHARES with the room it should
    open onto (an attached toilet -> its bedroom; everything else -> the most
    public neighbour), swinging INTO the room. Plus a window on each habitable
    room's longest external wall."""
    out = []
    d = [0]
    w = [0]
    entry_side = str(a.get("entry", "south")).lower()
    by_name = {r["name"]: r for r in rooms}

    # ENTRY door on the external wall of the first public room facing entry
    pub = next((r for r in rooms if r["kind"] in
                ("living", "living_dining")), rooms[0] if rooms else None)
    if pub:
        _door_on_external(pub, walls, entry_side, out, d, tag_entry=True)

    for r in rooms:
        if r["kind"] == "stair" or r.get("open_area"):
            continue
        if r["kind"] in ("living", "living_dining") and r is pub:
            target = None                     # already has the entry door
        elif r.get("parent") and r["parent"] in by_name:
            target = by_name[r["parent"]]     # attached toilet -> its bedroom
        else:
            target = _pick_target(r, rooms)   # most public neighbour
        if target is None:
            continue
        seg = _shared_edge(r, target)
        if not seg:
            continue
        lo, hi, orient, coord = seg
        wl = _wall_on(walls, orient, coord, lo, hi)
        if not wl:
            continue
        wide = r["kind"] in ("bath", "bath_attached", "powder", "pooja",
                             "store", "utility")
        width = 2.5 if wide else 3.0
        span = hi - lo
        if span < width + 0.4:
            width = max(2.0, span - 0.4)
        center = (lo + hi) / 2
        pos = _pos_on_wall(wl, coord if orient == "h" else center,
                           center if orient == "h" else coord)
        wlen = math.hypot(wl["x2"] - wl["x1"], wl["y2"] - wl["y1"])
        # keep the whole leaf ON the wall
        near = min(max(0.3, pos - width / 2), max(0.3, wlen - width - 0.3))
        d[0] += 1
        out.append({"type": "door", "tag": f"D{d[0]}", "wall_id": wl["id"],
                    "pos": round(near, 2), "width": round(width, 2),
                    "swing": {"room": r["name"], "hinge": "start",
                              "side": "left"}})

    used_win = set()
    for r in rooms:
        if r["kind"] in ("living", "dining", "living_dining", "kitchen",
                         "bedroom", "master", "study"):
            wl = _longest_external_edge(r, walls)
            if wl and wl["id"] not in used_win:
                used_win.add(wl["id"])
                length = math.hypot(wl["x2"] - wl["x1"], wl["y2"] - wl["y1"])
                wid = min(5.0, max(3.0, length * 0.5))
                w[0] += 1
                out.append({"type": "window", "tag": f"W{w[0]}",
                            "wall_id": wl["id"],
                            "pos": round(max(0.5, length / 2 - wid / 2), 2),
                            "width": round(wid, 2)})
    return out


def _pick_target(r, rooms):
    """The neighbour this room should open onto: the most public room it shares
    a usable wall with (falls back to the longest shared wall)."""
    best, best_key = None, (99, 0.0)
    for o in rooms:
        if o is r or o["kind"] == "stair" or o.get("open_area"):
            continue
        seg = _shared_edge(r, o)
        if not seg or (seg[1] - seg[0]) < 2.2:
            continue
        key = (PUBLIC_RANK.get(o["kind"], 6), -(seg[1] - seg[0]))
        if key < best_key:
            best_key, best = key, o
    return best


def _shared_edge(r, o):
    """The overlapping boundary between two rooms, as (lo, hi, orient, coord).
    orient 'v' = a vertical shared wall at x=coord; 'h' = horizontal at y=coord."""
    rx0, ry0, rx1, ry1 = r["x"], r["y"], r["x"] + r["w"], r["y"] + r["h"]
    ox0, oy0, ox1, oy1 = o["x"], o["y"], o["x"] + o["w"], o["y"] + o["h"]
    for cx in (rx0, rx1):
        if abs(cx - ox0) < 0.12 or abs(cx - ox1) < 0.12:
            lo, hi = max(ry0, oy0), min(ry1, oy1)
            if hi - lo > 0.5:
                return (lo, hi, "v", cx)
    for cy in (ry0, ry1):
        if abs(cy - oy0) < 0.12 or abs(cy - oy1) < 0.12:
            lo, hi = max(rx0, ox0), min(rx1, ox1)
            if hi - lo > 0.5:
                return (lo, hi, "h", cy)
    return None


def _wall_on(walls, orient, coord, lo, hi):
    """The wall segment lying on the shared line and covering [lo, hi]."""
    best, best_ov = None, 0
    for wl in walls:
        vert = abs(wl["x1"] - wl["x2"]) < 0.08
        if orient == "v" and vert and abs(wl["x1"] - coord) < 0.12:
            a, b = min(wl["y1"], wl["y2"]), max(wl["y1"], wl["y2"])
        elif orient == "h" and not vert and abs(wl["y1"] - coord) < 0.12:
            a, b = min(wl["x1"], wl["x2"]), max(wl["x1"], wl["x2"])
        else:
            continue
        ov = max(0, min(b, hi) - max(a, lo))
        if ov > best_ov + 0.01:
            best_ov, best = ov, wl
    return best


def _colinear(wl, x1, y1, x2, y2):
    return (abs(wl["x1"] - x1) < 0.06 and abs(wl["y1"] - y1) < 0.06 and
            abs(wl["x2"] - x2) < 0.06 and abs(wl["y2"] - y2) < 0.06) or \
           (abs(wl["x1"] - x2) < 0.06 and abs(wl["y1"] - y2) < 0.06 and
            abs(wl["x2"] - x1) < 0.06 and abs(wl["y2"] - y1) < 0.06)


def _room_edges(r):
    x0, y0, x1, y1 = r["x"], r["y"], r["x"] + r["w"], r["y"] + r["h"]
    return {"S": (x0, y0, x1, y0), "N": (x0, y1, x1, y1),
            "W": (x0, y0, x0, y1), "E": (x1, y0, x1, y1)}


def _best_internal_edge(r, walls, rooms):
    """The internal wall on this room's boundary that is longest (most likely a
    circulation-facing partition)."""
    best = None
    best_len = 0
    for side, (x1, y1, x2, y2) in _room_edges(r).items():
        for wl in walls:
            if wl["exterior"]:
                continue
            ov = _overlap_len(wl, x1, y1, x2, y2)
            if ov > best_len + 0.01:
                best_len = ov
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                best = (wl, (cx, cy, side))
    return best


def _longest_external_edge(r, walls):
    best, best_len = None, 0
    for side, (x1, y1, x2, y2) in _room_edges(r).items():
        for wl in walls:
            if not wl["exterior"]:
                continue
            ov = _overlap_len(wl, x1, y1, x2, y2)
            if ov > best_len + 0.01:
                best_len, best = ov, wl
    return best


def _overlap_len(wl, x1, y1, x2, y2):
    # only if the wall lies on the same line as the edge
    if abs(wl["x1"] - wl["x2"]) < 0.06 and abs(x1 - x2) < 0.06 and \
       abs(wl["x1"] - x1) < 0.06:                       # both vertical, same x
        lo = max(min(wl["y1"], wl["y2"]), min(y1, y2))
        hi = min(max(wl["y1"], wl["y2"]), max(y1, y2))
        return max(0, hi - lo)
    if abs(wl["y1"] - wl["y2"]) < 0.06 and abs(y1 - y2) < 0.06 and \
       abs(wl["y1"] - y1) < 0.06:                       # both horizontal, same y
        lo = max(min(wl["x1"], wl["x2"]), min(x1, x2))
        hi = min(max(wl["x1"], wl["x2"]), max(x1, x2))
        return max(0, hi - lo)
    return 0


def _pos_on_wall(wl, px, py):
    # distance from the wall START (x1,y1) — point_at() walks from there
    if abs(wl["x1"] - wl["x2"]) < 0.06:                 # vertical
        return abs(py - wl["y1"])
    return abs(px - wl["x1"])


def _door_on_external(r, walls, entry_side, out, d, tag_entry=False):
    side = {"south": "S", "north": "N", "west": "W", "east": "E"}.get(
        entry_side, "S")
    x1, y1, x2, y2 = _room_edges(r)[side]
    for wl in walls:
        if wl["exterior"] and _overlap_len(wl, x1, y1, x2, y2) > 3.0:
            length = math.hypot(wl["x2"] - wl["x1"], wl["y2"] - wl["y1"])
            d[0] += 1
            out.append({"type": "door", "tag": "D0" if tag_entry else f"D{d[0]}",
                        "wall_id": wl["id"],
                        "pos": max(0.5, length / 2 - 1.75), "width": 3.5,
                        "swing": {"room": r["name"], "hinge": "start",
                                  "side": "left"}})
            return


# --------------------------------------------------- helpers
def _ftin(v):
    f = int(v)
    inch = int(round((v - f) * 12))
    if inch == 12:
        f += 1
        inch = 0
    return f"{f}'-{inch}\"" if inch else f"{f}'-0\""
