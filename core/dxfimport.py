"""Convert a DXF straight into a PROPER editable plan — no image, no AI.

A CAD floor plan already tells us what everything is, through LAYERS:

* wall / AR-WALLS / column  → the walls (drawn as parallel face-lines)
* door                      → the doors  (blocks)
* AR-windows / *window*     → the windows (rectangles)
* the room TEXT             → the room name AND its exact size ("13'-0 x 11'-0")

So instead of guessing geometry from a rendered picture, we read each layer for
what it is:

* pair the two face-lines of every wall into ONE centre-line wall carrying the
  measured thickness, guarantee a closed outer envelope, keep the interior
  partitions;
* take each room's rectangle from its label's EXACT written size, placed at the
  label — so a "BEDROOM 13'-0 x 11'-0" is a true 13x11 room;
* place every door from the door layer and every window from the window layer,
  snapped onto the nearest wall — numbered D1 / W1 with a schedule.

The result drives furniture / electrical / plumbing / flooring exactly like a
read sketch does.  `read()` returns (plan | None, notes, ""); a None plan means
"couldn't read this DXF by its layers — fall back to the vision reader".
"""

from __future__ import annotations

import math
import os
import re

TOL_PERP = 0.15          # ft, two faces count as the same line within this
THK_MIN, THK_MAX = 0.28, 1.35     # wall thickness 3.4"–16"
OVERLAP_MIN = 0.5        # ft, two faces must run together this far to pair
MIN_WALL = 1.0           # ft, ignore shorter stray segments
MIN_PIECE = 1.5          # ft, drop wall pieces shorter than this
EDGE = 0.9               # ft, a wall this close to the bbox edge is exterior
EXT_THK = 9.0            # in, default outer-wall thickness


def _units_to_ft(doc) -> float:
    u = doc.header.get("$INSUNITS", 0)
    return {1: 1 / 12.0, 2: 1.0, 4: 1 / 304.8, 5: 1 / 30.48,
            6: 1 / 0.3048}.get(u, 1 / 304.8)


def _is_layer(name: str, *keys) -> bool:
    n = name.lower()
    return any(k in n for k in keys)


# ------------------------------------------------------------- read
def read(path: str, workdir: str):
    """Return (plan_dict | None, notes, "").  None → let the caller fall back."""
    import ezdxf
    notes = []
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    s = _units_to_ft(doc)

    def P(p):
        return (round(p[0] * s, 4), round(p[1] * s, 4))

    # ---- 1. wall-layer line segments -----------------------------------
    segs = []

    def take_seg(e):
        t = e.dxftype()
        try:
            if t == "LINE":
                segs.append((*P(e.dxf.start), *P(e.dxf.end)))
            elif t in ("LWPOLYLINE", "POLYLINE"):
                pts = ([P(p[:2]) for p in e.get_points()] if t == "LWPOLYLINE"
                       else [P(v.dxf.location) for v in e.vertices])
                closed = bool(getattr(e, "closed", False)
                              or e.dxf.get("flags", 0) & 1)
                seq = pts + ([pts[0]] if closed and len(pts) > 2 else [])
                for a, b in zip(seq, seq[1:]):
                    segs.append((a[0], a[1], b[0], b[1]))
        except Exception:
            pass

    for e in msp:
        if not _is_layer(e.dxf.layer, "wall"):
            continue
        if e.dxftype() == "INSERT":
            try:
                for ve in e.virtual_entities():
                    take_seg(ve)
            except Exception:
                pass
        else:
            take_seg(e)

    columns = _columns(msp, P, s)

    if len(segs) < 4:
        notes.append("No wall layer found in this DXF — using the vision "
                     "reader instead.")
        return None, notes, ""

    # ---- 2. pair opposite faces into centre-lines ----------------------
    horiz, vert = [], []
    for x1, y1, x2, y2 in segs:
        if abs(y1 - y2) <= TOL_PERP and abs(x1 - x2) > MIN_WALL:
            horiz.append((round((y1 + y2) / 2, 3), min(x1, x2), max(x1, x2)))
        elif abs(x1 - x2) <= TOL_PERP and abs(y1 - y2) > MIN_WALL:
            vert.append((round((x1 + x2) / 2, 3), min(y1, y2), max(y1, y2)))

    H = _cluster(_pair(horiz))     # (perp, lo, hi, thickness_in)
    V = _cluster(_pair(vert))
    if len(H) < 2 or len(V) < 2:
        notes.append("Walls are not drawn as double lines — using the vision "
                     "reader instead.")
        return None, notes, ""

    # ---- 3. real building envelope from the paired walls ---------------
    xps = [p for p, _l, _h, _t in V]
    yps = [p for p, _l, _h, _t in H]
    x0b, x1b = min(xps), max(xps)
    y0b, y1b = min(yps), max(yps)

    # ---- 4. build walls: closed envelope + interior partitions ---------
    walls = []

    def add(x1, y1, x2, y2, thk, ext):
        walls.append({"id": f"W{len(walls) + 1}",
                      "x1": round(x1, 3), "y1": round(y1, 3),
                      "x2": round(x2, 3), "y2": round(y2, 3),
                      "thickness_in": round(thk, 1),
                      "exterior": ext, "railing": False})

    add(x0b, y0b, x1b, y0b, EXT_THK, True)      # south
    add(x0b, y1b, x1b, y1b, EXT_THK, True)      # north
    add(x0b, y0b, x0b, y1b, EXT_THK, True)      # west
    add(x1b, y0b, x1b, y1b, EXT_THK, True)      # east
    for perp, lo, hi, thk in H:
        if abs(perp - y0b) < EDGE or abs(perp - y1b) < EDGE:
            continue
        add(lo, perp, hi, perp, thk, False)
    for perp, lo, hi, thk in V:
        if abs(perp - x0b) < EDGE or abs(perp - x1b) < EDGE:
            continue
        add(perp, lo, perp, hi, thk, False)

    # ---- 5. rooms from their EXACT written sizes -----------------------
    rooms = _rooms(msp, P, (x0b, y0b, x1b, y1b))
    if len(rooms) < 2:
        # labels carry no size (just names) — recover each room as the enclosed
        # area around its name label
        rooms = _rooms_geom(walls, msp, P, (x0b, y0b, x1b, y1b))

    # ---- 6. doors & windows straight off their layers ------------------
    openings = _openings(msp, P, walls, rooms, (x0b, y0b, x1b, y1b))

    # number the columns C1, C2 … and place them in a room
    for i, c in enumerate(columns, 1):
        c["tag"] = f"C{i}"
        c["room"] = _room_at(c["x"], c["y"], rooms)

    # ---- 7. translate the whole plan to a sensible origin --------------
    _translate(walls, rooms, -x0b, -y0b)
    for c in columns:
        c["x"] = round(c["x"] - x0b, 3)
        c["y"] = round(c["y"] - y0b, 3)

    plan = {
        "north_deg": 90,
        "title": {"project": os.path.splitext(os.path.basename(path))[0],
                  "plan_name": "IMPORTED DXF"},
        "walls": walls, "rooms": rooms, "openings": openings,
        "columns": columns,
        "stairs": [], "steps": [], "dims": [],
        "notes": [f"Imported from {os.path.basename(path)} by its CAD layers."],
        "assumptions": [
            f"{len(walls)} walls (outer envelope + partitions), "
            f"{len(rooms)} rooms sized from their labels, "
            f"{len(openings)} doors/windows read from the door and window "
            "layers.",
        ],
    }
    try:
        from . import pipeline
        plan, _n = pipeline.number_openings(plan, force=True)
    except Exception:
        pass
    doors = sum(1 for o in openings if "door" in o.get("type", ""))
    wins = len(openings) - doors
    notes.append(f"{len(walls)} walls, {len(rooms)} rooms, "
                 f"{doors} doors, {wins} windows imported.")
    return _native(plan), notes, ""


# ---------------------------------------------------- wall reconstruction
def _pair(items):
    """Pair opposite faces into (perp_mid, s0, s1, thickness). `items` are
    (perp, span0, span1)."""
    items = sorted(items)
    used = [False] * len(items)
    out = []
    for i in range(len(items)):
        if used[i]:
            continue
        pi, a0, a1 = items[i]
        for j in range(i + 1, len(items)):
            if used[j]:
                continue
            pj, b0, b1 = items[j]
            gap = pj - pi
            if gap > THK_MAX:
                break
            if gap < THK_MIN:
                continue
            if min(a1, b1) - max(a0, b0) < OVERLAP_MIN:
                continue
            used[i] = used[j] = True
            out.append(((pi + pj) / 2, max(a0, b0), min(a1, b1), gap))
            break
    return out


def _cluster(paired):
    """Merge collinear paired pieces (same perpendicular line) into one wall
    spanning their full extent; thickness is the median gap in inches."""
    paired = sorted(paired)
    groups = []
    for perp, a, b, thk in paired:
        for g in groups:
            if abs(g["perp"] - perp) < 0.6:
                g["segs"].append((a, b))
                g["thk"].append(thk)
                break
        else:
            groups.append({"perp": perp, "segs": [(a, b)], "thk": [thk]})
    out = []
    for g in groups:
        lo = min(a for a, _b in g["segs"])
        hi = max(b for _a, b in g["segs"])
        if hi - lo < MIN_PIECE:
            continue
        thk = sorted(g["thk"])[len(g["thk"]) // 2] * 12.0
        out.append((round(g["perp"], 3), round(lo, 3), round(hi, 3),
                    round(thk, 1)))
    return out


# --------------------------------------------------------------- rooms
_FT_RE = re.compile(r"(\d+)'\s*-?\s*(\d+(?:\.\d+)?)?")


def _clean_text(txt: str) -> str:
    """Strip DXF text formatting codes (\\P line breaks, \\A1; alignment,
    {\\f...;} font runs) so 'Living\\P12'-0" x ...' reads as plain words."""
    txt = re.sub(r"\\[Pp]", " ", txt)          # line breaks
    txt = re.sub(r"\\[A-Za-z][^;\\]*;", "", txt)   # \A1;  \fArial|..;  \pt36;
    txt = txt.replace("{", "").replace("}", "").replace("\\", " ")
    return " ".join(txt.split())


def _parse_ft(tok: str):
    m = _FT_RE.search(tok)
    if not m:
        return None
    inch = float(m.group(2)) / 12.0 if m.group(2) else 0.0
    return int(m.group(1)) + inch


def _rooms(msp, P, bbox):
    x0b, y0b, x1b, y1b = bbox
    out = []
    for e in msp:
        if e.dxftype() not in ("MTEXT", "TEXT"):
            continue
        if _is_layer(e.dxf.layer, "dim", "lvl", "level"):
            continue
        try:
            txt = e.plain_text() if e.dxftype() == "MTEXT" else e.dxf.text
        except Exception:
            continue
        txt = _clean_text(txt)
        parts = re.split(r"[xX×]", txt)
        if len(parts) != 2:
            continue
        m = re.search(r"([A-Za-z][A-Za-z .]+?)\s*(\d+'.*)$", parts[0])
        if not m:
            continue
        name = m.group(1).strip(" .-")
        a, b = _parse_ft(m.group(2)), _parse_ft(parts[1])
        if not (name and len(name) > 2 and a and b):
            continue
        ins = e.dxf.get("insert") or e.dxf.get("align_point")
        if ins is None:
            continue
        cx, cy = P(ins)
        if not (x0b - 2 <= cx <= x1b + 2 and y0b - 2 <= cy <= y1b + 2):
            continue
        out.append({"name": name.upper()[:20],
                    "x": round(cx - a / 2, 3), "y": round(cy - b / 2, 3),
                    "w": round(a, 3), "h": round(b, 3),
                    "size_label": txt[m.start(2):].strip(),
                    "open_area": _is_open(name)})
    return out


def _is_open(name: str) -> bool:
    return any(k in name.lower() for k in ("terrace", "balcony", "verandah",
                                           "veranda", "court", "o.t.s", "ots",
                                           "open", "planter"))


def _columns(msp, P, s):
    """Read structural columns off the `column` layer — a closed polyline is a
    square/rectangle, a CIRCLE is a round column. `s` is the units→feet factor
    (the radius is a length, so it must be scaled like every other length)."""
    out = []
    for e in msp:
        if not _is_layer(e.dxf.layer, "column", "col"):
            continue
        t = e.dxftype()
        try:
            if t == "CIRCLE":
                cx, cy = P(e.dxf.center)
                out.append({"x": cx, "y": cy, "shape": "round",
                            "w": round(e.dxf.radius * 2 * s, 3), "h": 0.0,
                            "tag": "", "room": ""})
            elif t in ("LWPOLYLINE", "POLYLINE"):
                pts = ([P(p[:2]) for p in e.get_points()] if t == "LWPOLYLINE"
                       else [P(v.dxf.location) for v in e.vertices])
                if len(pts) < 3:
                    continue
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                w, h = max(xs) - min(xs), max(ys) - min(ys)
                if w < 0.15 or h < 0.15 or w > 4 or h > 4:
                    continue                       # not a column-sized box
                shape = "square" if abs(w - h) < 0.15 else "rectangular"
                out.append({"x": round((min(xs) + max(xs)) / 2, 3),
                            "y": round((min(ys) + max(ys)) / 2, 3),
                            "shape": shape, "w": round(w, 3), "h": round(h, 3),
                            "tag": "", "room": ""})
        except Exception:
            pass
    return out


_FURN_WORDS = ("table", "sink", "machine", "washing", "wardrobe", "hob",
               "fridge", "basin", "shower", "library", "certificate",
               "burner", "platform", "slab", "shelf", "loft", "cupboard",
               "counter")


def _room_name_ok(t: str) -> bool:
    low = " ".join(t.split()).lower()
    if sum(c.isalpha() for c in low) < 3:        # dimensions / symbols
        return False
    return not any(w in low for w in _FURN_WORDS)


def _rooms_geom(walls, msp, P, bbox):
    """Recover rooms with NO size text: split the walled interior into its
    enclosed regions and name each from the label sitting inside it."""
    from shapely.geometry import box, LineString, Point
    from shapely.ops import unary_union
    x0, y0, x1, y1 = bbox
    solids = []
    for w in walls:
        th = max(w["thickness_in"] / 12.0, 0.1)
        solids.append(LineString([(w["x1"], w["y1"]), (w["x2"], w["y2"])])
                      .buffer(th / 2, cap_style=2, join_style=2))
    if not solids:
        return []
    solid = unary_union(solids)
    pad = 0.1
    foot = box(x0 - pad, y0 - pad, x1 + pad, y1 + pad)
    interior = foot.difference(solid)
    pieces = (list(interior.geoms)
              if interior.geom_type == "MultiPolygon" else [interior])
    texts = []
    for e in msp:
        if e.dxftype() not in ("MTEXT", "TEXT"):
            continue
        if _is_layer(e.dxf.layer, "dim", "lvl", "level"):
            continue
        try:
            t = e.plain_text() if e.dxftype() == "MTEXT" else e.dxf.text
        except Exception:
            continue
        t = _clean_text(t)
        ins = e.dxf.get("insert") or e.dxf.get("align_point")
        if t and ins is not None and _room_name_ok(t):
            px, py = P(ins)
            texts.append((px, py, t))
    fa = foot.area
    rooms = []
    for g in pieces:
        if g.area < 12:                          # slivers between wall faces
            continue
        gx0, gy0, gx1, gy1 = g.bounds
        edge = ((abs(gx0 - (x0 - pad)) < 0.25) + (abs(gy0 - (y0 - pad)) < 0.25)
                + (abs(gx1 - (x1 + pad)) < 0.25) + (abs(gy1 - (y1 + pad)) < 0.25))
        if edge >= 2 and g.area > 0.35 * fa:     # the exterior leftover
            continue
        cen = g.representative_point()
        gb = g.buffer(0.25)
        best, bd = "", 1e18
        for tx, ty, txt in texts:
            if not gb.contains(Point(tx, ty)):
                continue
            d = (tx - cen.x) ** 2 + (ty - cen.y) ** 2
            if d < bd:
                best, bd = txt, d
        rooms.append({"name": (best or "ROOM").upper()[:24],
                      "x": round(gx0, 3), "y": round(gy0, 3),
                      "w": round(gx1 - gx0, 3), "h": round(gy1 - gy0, 3),
                      "size_label": "", "open_area": False})
    return rooms


def _room_at(x, y, rooms):
    for r in rooms:
        if r["x"] <= x <= r["x"] + r["w"] and r["y"] <= y <= r["y"] + r["h"]:
            return r["name"]
    best, bd = "", 1e18
    for r in rooms:
        cx, cy = r["x"] + r["w"] / 2, r["y"] + r["h"] / 2
        d = (cx - x) ** 2 + (cy - y) ** 2
        if d < bd:
            best, bd = r["name"], d
    return best


# ------------------------------------------------------------- openings
def _nearest_wall(cx, cy, walls):
    best, bd, bpos = None, 1e18, 0.0
    for w in walls:
        ax, ay, bx, by = w["x1"], w["y1"], w["x2"], w["y2"]
        vx, vy = bx - ax, by - ay
        L2 = vx * vx + vy * vy or 1e-9
        t = max(0.0, min(1.0, ((cx - ax) * vx + (cy - ay) * vy) / L2))
        px, py = ax + vx * t, ay + vy * t
        d = math.hypot(cx - px, cy - py)
        if d < bd:
            best, bd, bpos = w, d, t * math.hypot(vx, vy)
    return best, bpos, bd


def _openings(msp, P, walls, rooms, bbox):
    x0b, y0b, x1b, y1b = bbox

    def in_plan(x, y, m=2):
        return x0b - m <= x <= x1b + m and y0b - m <= y <= y1b + m

    out = []
    wn = dn = 0
    # windows — each AR-window rectangle, long axis is the width
    for e in msp:
        if e.dxftype() != "LWPOLYLINE" or not _is_layer(e.dxf.layer,
                                                         "window", "glaz"):
            continue
        pts = [P(p[:2]) for p in e.get_points()]
        if len(pts) < 4:
            continue
        X = [p[0] for p in pts]
        Y = [p[1] for p in pts]
        cx, cy = (min(X) + max(X)) / 2, (min(Y) + max(Y)) / 2
        width = max(max(X) - min(X), max(Y) - min(Y))
        w, pos, _d = _nearest_wall(cx, cy, walls)
        if not w:
            continue
        wn += 1
        out.append({"type": "window", "wall_id": w["id"], "pos": round(pos, 3),
                    "width": round(width, 2), "tag": f"W{wn}", "count": 1})
    # doors — each door block; ignore mirror artifacts outside the plan
    for e in msp:
        if e.dxftype() != "INSERT" or not _is_layer(e.dxf.layer, "door"):
            continue
        pts = []
        try:
            for ve in e.virtual_entities():
                if ve.dxftype() == "LINE":
                    for q in (ve.dxf.start, ve.dxf.end):
                        x, y = P(q)
                        if in_plan(x, y):
                            pts.append((x, y))
                elif ve.dxftype() == "ARC":
                    x, y = P(ve.dxf.center)
                    if in_plan(x, y):
                        pts.append((x, y))
        except Exception:
            pass
        if not pts:
            continue
        X = [p[0] for p in pts]
        Y = [p[1] for p in pts]
        cx, cy = (min(X) + max(X)) / 2, (min(Y) + max(Y)) / 2
        w, pos, _d = _nearest_wall(cx, cy, walls)
        if not w:
            continue
        dn += 1
        room = _room_at(cx, cy, rooms)
        out.append({"type": "single_door", "wall_id": w["id"],
                    "pos": round(pos, 3), "width": 3.0, "tag": f"D{dn}",
                    "swing": {"room": room, "hinge": "start", "side": "left"},
                    "count": 1})
    return out


# ------------------------------------------------------------- helpers
def _translate(walls, rooms, dx, dy):
    for w in walls:
        w["x1"] += dx
        w["y1"] += dy
        w["x2"] += dx
        w["y2"] += dy
        for k in ("x1", "y1", "x2", "y2"):
            w[k] = round(w[k], 3)
    for r in rooms:
        r["x"] = round(r["x"] + dx, 3)
        r["y"] = round(r["y"] + dy, 3)


def _native(o):
    """Recursively convert numpy scalars/arrays to plain Python types so the
    plan is JSON-serialisable across the pywebview bridge."""
    if isinstance(o, dict):
        return {k: _native(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_native(v) for v in o]
    if isinstance(o, bool):
        return o
    if type(o).__module__ == "numpy":
        item = getattr(o, "item", None)
        if callable(item):
            return o.item()
        tolist = getattr(o, "tolist", None)
        if callable(tolist):
            return _native(o.tolist())
    return o
