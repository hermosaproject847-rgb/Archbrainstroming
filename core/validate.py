"""STEP 4 — programmatic self-validation.

Every check is geometric, so correctness is provable without looking at the
image. Each issue has a severity: "error" blocks a clean drawing, "warn" is
worth the user's eye.
"""

from __future__ import annotations

from shapely.geometry import Point, box
from shapely.ops import unary_union
from shapely.ops import unary_union

from . import autofix
from . import standards as std
from .engine import wall_solid, cut_solid, wall_rect, opening_rect, _door_frame, _polys
from .model import Plan

STEP_V = 0.25          # sampling step along a wall, feet


def _issue(sev, code, msg, ref="", rule=""):
    return {"severity": sev, "code": code, "message": msg, "ref": ref,
            "rule": rule}


# ------------------------------------------------- the drafting rulebook
def _room_of(plan: Plan, o) -> str:
    """The room an opening serves, for choosing the right rule."""
    if o.is_door and o.swing and o.swing.room:
        return o.swing.room
    w = plan.wall(o.wall_id)
    if w is None:
        return ""
    mid = w.point_at(o.pos + o.width / 2)
    best, best_d = "", 1e9
    for r in plan.rooms:
        cx, cy = r.centre
        d = (cx - mid[0]) ** 2 + (cy - mid[1]) ** 2
        if d < best_d:
            best, best_d = r.name, d
    return best


def check_rulebook(plan: Plan) -> list[dict]:
    """The checks of §11, plus the rules they refer to. Findings are LISTED,
    never corrected: the rulebook is explicit that the designer decides."""
    out: list[dict] = []
    S = std

    # -- §2/§3/§4 every opening carries its levels ---------------------
    for o in plan.openings:
        if not (o.is_door or o.type in ("window", "vent")):
            continue
        tag = o.tag or o.type
        room = _room_of(plan, o)
        if not o.lintel_mm:
            out.append(_issue("error", "missing-lintel",
                              f"{tag}: lintel level (LL) is missing. It is "
                              "mandatory on every opening — typically 2100 "
                              "above FFL.", tag, "§11 / §2.5"))
        if o.type in ("window", "vent") and not o.sill_mm:
            want = S.KITCHEN_SILL_MM if S.classify(room) == "kitchen" \
                else (S.VENT_SILL_MM if o.type == "vent" else S.WINDOW_SILL_MM)
            out.append(_issue("error", "missing-sill",
                              f"{tag}: sill level (SL) is missing. Typical for "
                              f"this opening is {want:.0f} above FFL.",
                              tag, "§11 / §3.2"))
        if o.type in ("window", "vent") and o.sill_mm and o.lintel_mm \
                and o.lintel_mm <= o.sill_mm:
            out.append(_issue("error", "sill-above-lintel",
                              f"{tag}: sill {o.sill_mm:.0f} is not below "
                              f"lintel {o.lintel_mm:.0f}.", tag, "§3.2"))

        # -- §2.6 door widths
        if o.is_door:
            w_mm = o.width_mm
            kind = S.classify(room)
            if kind == "wet":
                lo, what = S.DOOR_MIN_W_MM["toilet"], "toilet/bath door"
            elif kind == "open" or "main" in tag.lower() or tag.upper() == "D1":
                lo, what = S.DOOR_MIN_W_MM["main"], "main entrance door"
            else:
                lo, what = S.DOOR_MIN_W_MM["internal"], "internal door"
            if w_mm + 1 < lo:
                out.append(_issue("warn", "door-narrow",
                                  f"{tag} is {w_mm:.0f} wide; a {what} needs "
                                  f"at least {lo:.0f}.", tag, "§2.6"))
            if o.height_mm and o.height_mm < S.DOOR_MIN_H_MM:
                out.append(_issue("warn", "door-low",
                                  f"{tag} is {o.height_mm:.0f} high; minimum "
                                  f"is {S.DOOR_MIN_H_MM:.0f}.", tag, "§2.6"))

    # -- §1 wall thicknesses -------------------------------------------
    for w in plan.walls:
        if w.railing:
            continue
        mm = w.thickness_in * 25.4
        # 230 and 115 are both standard. A 230 internal wall is normal drafting
        # (party walls, the walls flanking a stair), so only a thickness that
        # is neither is a conflict worth the designer's time.
        if min(abs(mm - S.EXTERNAL_MM), abs(mm - S.PARTITION_MM)) > 20:
            out.append(_issue("warn", "wall-thickness",
                              f"Wall {w.id} is {mm:.0f} mm; the rule is "
                              f"{S.EXTERNAL_MM:.0f} external / "
                              f"{S.PARTITION_MM:.0f} internal. Flagged, not "
                              "changed — confirm with the designer.",
                              w.id, "§11 / §1"))
        elif w.exterior and abs(mm - S.PARTITION_MM) < 20:
            out.append(_issue("warn", "wall-thickness",
                              f"External wall {w.id} is only {mm:.0f} mm; "
                              f"external walls are {S.EXTERNAL_MM:.0f}.",
                              w.id, "§1.1"))

    # -- §7 minimum room sizes -----------------------------------------
    for r in plan.rooms:
        if r.open_area:
            continue
        kind = S.classify(r.name)
        area = r.w * r.h / S.SQM_SQFT
        width = min(r.w, r.h) * 0.3048
        want = None
        if kind == "habitable":
            want = S.ROOM_MINIMA["habitable"]
        elif kind == "kitchen":
            want = S.ROOM_MINIMA["kitchen"]
        elif kind == "wet":
            want = S.ROOM_MINIMA["bath+wc"]
        elif kind == "store":
            want = S.ROOM_MINIMA["store"]
        elif kind == "passage":
            want = (0.0, S.PASSAGE_MIN_W_M)
        elif kind == "stair":
            want = (0.0, S.STAIR_MIN_W_M)
        if not want:
            continue
        min_area, min_w = want
        if min_area and area + 0.05 < min_area:
            out.append(_issue("warn", "room-undersized",
                              f"'{r.name}' is {area:.1f} m²; NBC minimum for "
                              f"this use is {min_area} m². Flagged, never "
                              "auto-resized.", r.name, "§11 / §7"))
        if min_w and width + 0.02 < min_w:
            out.append(_issue("warn", "room-narrow",
                              f"'{r.name}' is {width:.2f} m wide; minimum is "
                              f"{min_w} m.", r.name, "§11 / §7"))

    # -- §11 light & ventilation ---------------------------------------
    served: dict[str, float] = {}
    has_vent: set = set()
    for o in plan.openings:
        if o.type not in ("window", "vent"):
            continue
        room = _room_of(plan, o)
        h_mm = o.height_mm or S.default_height(o.type)
        served[room] = served.get(room, 0.0) + \
            (o.width_mm * h_mm) / 1e6 * max(1, o.count)
        if o.type == "vent":
            has_vent.add(room)

    for r in plan.rooms:
        if r.open_area:
            continue
        kind = S.classify(r.name)
        area = r.w * r.h / S.SQM_SQFT
        got = served.get(r.name, 0.0)
        if kind == "habitable":
            if got <= 0:
                out.append(_issue("error", "no-window",
                                  f"Habitable room '{r.name}' has no window — "
                                  "light and ventilation failure.",
                                  r.name, "§11 / §3"))
            elif got < area * S.LIGHT_VENT_RATIO_MIN:
                out.append(_issue("warn", "light-vent-short",
                                  f"'{r.name}': openable area {got:.2f} m² is "
                                  f"under 1/10 of its {area:.1f} m² floor "
                                  f"({area * S.LIGHT_VENT_RATIO_MIN:.2f} m²).",
                                  r.name, "§3.3"))
        elif kind == "wet":
            if r.name not in has_vent:
                out.append(_issue("error", "no-ventilator",
                                  f"'{r.name}' has no ventilator. Provide one, "
                                  "or note mechanical exhaust with duct.",
                                  r.name, "§11 / §4"))
            elif got < S.TOILET_VENT_AREA_MIN_SQM:
                out.append(_issue("warn", "vent-small",
                                  f"'{r.name}': ventilation {got:.2f} m² is "
                                  f"under the {S.TOILET_VENT_AREA_MIN_SQM} m² "
                                  "minimum.", r.name, "§4.3"))

    # -- §11 dimension chains must close --------------------------------
    # measured against the BUILDING, not plan.extents(), which also spans the
    # plot line and the dimension chains themselves
    xs = [v for w in plan.walls if not w.railing for v in (w.x1, w.x2)]
    ys = [v for w in plan.walls if not w.railing for v in (w.y1, w.y2)]
    for c in plan.dims:
        ticks = sorted(set(c.ticks))
        if len(ticks) < 2 or not xs:
            continue
        span = ticks[-1] - ticks[0]
        overall = (max(xs) - min(xs)) if c.axis in ("top", "bottom") \
            else (max(ys) - min(ys))
        if overall > 0 and abs(span - overall) > 0.75:
            out.append(_issue("warn", "chain-not-closing",
                              f"The {c.axis} dimension chain spans "
                              f"{span:.2f} ft but the plan is {overall:.2f} ft "
                              "overall — the chain does not close.",
                              c.axis, "§11 / §6.2"))

    # -- §8 staircase ---------------------------------------------------
    for s in plan.stairs:
        n = int(s.steps_f1 or s.treads or 0) + int(s.steps_f2 or 0)
        if n and s.type.upper() == "U":
            run = max(s.w, s.h) * 304.8
            tread = run / max(1, int(s.steps_f1 or s.treads or 1))
            if tread + 1 < S.TREAD_MIN_MM:
                out.append(_issue("warn", "tread-short",
                                  f"Tread works out at {tread:.0f} mm; the "
                                  f"minimum is {S.TREAD_MIN_MM:.0f}.",
                                  "", "§8.1"))
        if min(s.w, s.h) * 0.3048 + 0.02 < S.STAIR_MIN_W_M:
            out.append(_issue("warn", "stair-narrow",
                              f"Stair is {min(s.w, s.h) * 0.3048:.2f} m wide; "
                              f"minimum {S.STAIR_MIN_W_M} m.", "", "§7"))
    return out


def check_furniture(plan: Plan) -> list[dict]:
    """STEP 4 of the furniture prompt, proved rather than eyeballed:
    every piece fits its room, clears every door swing and the stair, does not
    overlap another piece, and keeps its own clearance."""
    from . import furniture as F
    from . import layout as LO

    out: list[dict] = []
    if not plan.furniture:
        return out

    bad = LO.blocked(plan)
    # a turned piece is checked as the shape it really occupies, not as its
    # upright box — otherwise rotating something into a wall goes unnoticed
    boxes = {f.tag or f.kind: LO.footprint(f) for f in plan.furniture}
    rooms = {r.name.strip().lower(): r for r in plan.rooms}

    for f in plan.furniture:
        tag = f.tag or f.kind
        fp = boxes[tag]

        r = rooms.get((f.room or "").strip().lower())
        if r is not None:
            rb = box(r.x, r.y, r.x + r.w, r.y + r.h)
            if not rb.buffer(0.05).contains(fp):
                out.append(_issue("error", "furniture-outside",
                                  f"{tag} ({f.kind}) is not fully inside "
                                  f"'{f.room}'.", tag, "STEP 4"))

        if not bad.is_empty and fp.intersection(bad.buffer(-0.03)).area > 0.05:
            out.append(_issue("error", "furniture-clash",
                              f"{tag} ({f.kind}) overlaps a wall, a door "
                              "swing or the stair.", tag, "STEP 4"))

    # pieces must not overlap each other — abutting chairs are allowed
    items = list(plan.furniture)
    for i, a in enumerate(items):
        for b in items[i + 1:]:
            ab = boxes[a.tag or a.kind].intersection(boxes[b.tag or b.kind])
            if ab.area > 0.15:
                out.append(_issue("error", "furniture-overlap",
                                  f"{a.tag} ({a.kind}) and {b.tag} "
                                  f"({b.kind}) overlap by {ab.area:.1f} sq ft.",
                                  a.tag, "STEP 4"))

    # the clearance each piece needs in front of it
    NEED = {"bed": F.CLEAR["bed_side"], "wardrobe": F.CLEAR["wardrobe_front"],
            "dresser": F.CLEAR["chair_pullback"],
            "study_table": F.CLEAR["chair_pullback"],
            "wc": F.CLEAR["wc_front"], "basin": F.CLEAR["basin_front"]}
    for f in plan.furniture:
        need = NEED.get(F.family(f.kind))
        if not need or not f.facing:
            continue
        fp = boxes[f.tag or f.kind]
        strip = LO._front(fp, f.facing, F.ft(need))
        blocked_by = [g.tag for g in plan.furniture
                      if g is not f
                      and boxes[g.tag or g.kind].intersection(strip).area > 0.2]
        hits_wall = (not bad.is_empty
                     and strip.intersection(bad.buffer(-0.05)).area > 0.2)
        if blocked_by or hits_wall:
            what = ", ".join(blocked_by) if blocked_by else "a wall"
            out.append(_issue("warn", "clearance-short",
                              f"{f.tag} ({f.kind}) needs {need:.0f} mm clear "
                              f"in front; {what} is in the way.",
                              f.tag, "STEP 3B"))
    return out


def fill_levels(plan: Plan) -> list[str]:
    """Give every opening the rulebook's typical sill/lintel where the sketch
    states none, so the schedule is complete. Each fill is reported — the
    rulebook forbids silent correction."""
    notes: list[str] = []
    for o in plan.openings:
        if not (o.is_door or o.type in ("window", "vent")):
            continue
        room = _room_of(plan, o)
        sill, lintel = std.default_levels(o.type, room)
        tag = o.tag or o.type
        if not o.height_mm:
            o.height_mm = std.default_height(o.type)
            notes.append(f"{tag}: height taken as {o.height_mm:.0f} (typical)")
        if not o.lintel_mm and lintel:
            o.lintel_mm = lintel
            notes.append(f"{tag}: lintel taken as {lintel:.0f} above FFL "
                         "(typical) — confirm on site")
        if o.type in ("window", "vent") and not o.sill_mm and sill:
            o.sill_mm = sill
            notes.append(f"{tag}: sill taken as {sill:.0f} above FFL "
                         f"(typical for a {std.classify(room) or 'room'})")
    return notes


def validate(plan: Plan, rulebook: bool = True) -> list[dict]:
    out: list[dict] = []
    if rulebook:
        out.extend(check_rulebook(plan))
    out.extend(check_furniture(plan))
    solid = wall_solid(plan)

    # -- walls ---------------------------------------------------------
    if not plan.walls:
        out.append(_issue("error", "no-walls", "Plan has no walls."))
        return out
    if not solid.is_valid:
        out.append(_issue("error", "bad-union",
                          "Wall union is not a valid polygon — junctions overlap badly."))
    for w in plan.walls:
        if w.length < 1e-6:
            out.append(_issue("error", "zero-wall", f"Wall {w.id} has zero length.", w.id))
        if w.thickness_in <= 0:
            out.append(_issue("error", "zero-thk", f"Wall {w.id} has no thickness.", w.id))

    # -- openings sit on their wall, inside its length ------------------
    for o in plan.openings:
        w = plan.wall(o.wall_id)
        if w is None:
            out.append(_issue("error", "orphan-opening",
                              f"{o.tag or o.type} refers to missing wall {o.wall_id}.", o.tag))
            continue
        if o.width <= 0:
            out.append(_issue("error", "zero-opening",
                              f"{o.tag or o.type} has zero width.", o.tag))
            continue
        if o.pos < -1e-6 or o.pos + o.width > w.length + 1e-6:
            out.append(_issue("error", "opening-off-wall",
                              f"{o.tag or o.type} runs past the end of wall {w.id} "
                              f"(needs {o.pos:.2f}+{o.width:.2f} of {w.length:.2f} ft).",
                              o.tag))
        # the cut must actually remove wall material
        if not opening_rect(w, o).intersects(wall_rect(w)):
            out.append(_issue("error", "opening-misses-wall",
                              f"{o.tag or o.type} does not land on wall {w.id}.", o.tag))

    # -- no wall left across a door ------------------------------------
    cut = cut_solid(plan)
    for o in plan.openings:
        w = plan.wall(o.wall_id)
        if w is None or not (o.is_door or o.type in ("gate", "open")):
            continue
        mid = w.point_at(o.pos + o.width / 2)
        if cut.contains(Point(mid)):
            out.append(_issue("error", "wall-across-door",
                              f"A wall still crosses {o.tag or o.type} on {w.id}.", o.tag))

    # -- door swings land in clear floor of the room they serve ---------
    for o in plan.openings:
        if not o.is_door:
            continue
        w = plan.wall(o.wall_id)
        if w is None or o.swing is None:
            out.append(_issue("warn", "no-swing",
                              f"{o.tag or 'door'} has no swing defined.", o.tag))
            continue
        hinge, u, n, wd = _door_frame(plan, o)
        # sample the quarter-circle: points must be clear of walls
        for f in (0.35, 0.6, 0.85):
            sx = hinge[0] + (u[0] * 0.7 + n[0] * 0.7) * wd * f
            sy = hinge[1] + (u[1] * 0.7 + n[1] * 0.7) * wd * f
            if solid.contains(Point(sx, sy)):
                out.append(_issue("error", "swing-into-wall",
                                  f"{o.tag or 'door'} swings into a wall.", o.tag))
                break
        # and they must be inside the owning room
        r = plan.room(o.swing.room) if o.swing.room else None
        if r is not None:
            tip = (hinge[0] + n[0] * wd * 0.9, hinge[1] + n[1] * wd * 0.9)
            if not box(r.x, r.y, r.x + r.w, r.y + r.h).contains(Point(tip)):
                out.append(_issue("error", "swing-wrong-side",
                                  f"{o.tag or 'door'} does not open into {r.name} — "
                                  "flip the swing side.", o.tag))
        elif o.swing.room:
            out.append(_issue("warn", "swing-unknown-room",
                              f"{o.tag or 'door'} swings into unknown room "
                              f"'{o.swing.room}'.", o.tag))

    # -- open areas carry no walls -------------------------------------
    # checked against the CUT solid: a span punched out by autofix is genuinely
    # not there, so an open frontage reads as open.
    opens = [r for r in plan.rooms if r.open_area and not r.void]
    for r in opens:
        # Inset past the thickest wall that could sit on this room's own
        # boundary, so a wall bounding the area is not reported as crossing it.
        pad = 1.0
        inner = box(r.x + pad, r.y + pad, r.x + r.w - pad, r.y + r.h - pad)
        if not cut.is_empty and cut.intersects(inner):
            out.append(_issue("warn", "wall-in-open-area",
                              f"A wall runs through open area '{r.name}'.", r.name))
    # No partition between two adjacent open areas. Sampled along each wall the
    # same way autofix does, so the two always agree — a box-overlap test would
    # false-positive on the corner return walls that legitimately end there.
    for w in plan.walls:
        run = 0.0
        d = 0.0
        while d <= w.length + 1e-9:
            at = min(d, w.length)
            ra, rb, _, _ = autofix._sides_of(plan, w, at)
            both_open = (ra and rb
                         and all(r.open_area and not r.void for r in ra)
                         and all(r.open_area and not r.void for r in rb))
            if both_open and cut.contains(Point(w.point_at(at))):
                run += STEP_V
                if run > 0.75:
                    out.append(_issue(
                        "error", "wall-between-open-areas",
                        f"Wall {w.id} still separates open areas "
                        f"'{ra[0].name}' and '{rb[0].name}' — they are one "
                        "continuous space.", w.id))
                    break
            else:
                run = 0.0
            d += STEP_V

    # -- rooms ---------------------------------------------------------
    for r in plan.rooms:
        if r.w <= 0 or r.h <= 0:
            out.append(_issue("error", "zero-room", f"Room '{r.name}' has no area.", r.name))
    for i, a in enumerate(plan.rooms):
        for b in plan.rooms[i + 1:]:
            if a.open_area and b.open_area:
                continue
            ov = box(a.x, a.y, a.x + a.w, a.y + a.h).intersection(
                 box(b.x, b.y, b.x + b.w, b.y + b.h))
            if ov.area > 0.5:
                out.append(_issue("warn", "rooms-overlap",
                                  f"'{a.name}' and '{b.name}' overlap by "
                                  f"{ov.area:.1f} sq ft.", a.name))

    # -- stairs ---------------------------------------------------------
    from . import stairs as _st
    for s in plan.stairs:
        if s.w <= 0 or s.h <= 0:
            out.append(_issue("error", "zero-stair", "Stair has no footprint."))
            continue
        g = _st.build(s)
        n = len(g["flights"])
        if s.type.upper() in ("U", "L") and n < 2:
            out.append(_issue("error", "missing-flight",
                              f"A {s.type} stair needs two flights — only "
                              f"{n} was built."))
        if s.type.upper() == "U3":
            lands = g.get("landings") or []
            if len(lands) < 2:
                out.append(_issue("error", "missing-landing",
                                  "A three-flight stair has TWO landings — "
                                  f"only {len(lands)} was built."))
            for (lx, ly, lw, lh) in lands:
                # the rulebook: landing width >= stair width, and these
                # landings are drawn square
                if abs(lw - lh) > 0.35:
                    out.append(_issue("warn", "landing-not-square",
                                      f"A landing is {lw:.2f} x {lh:.2f} ft. "
                                      "The landings of this stair are square.",
                                      "", "§8.4"))
                if min(lw, lh) * 0.3048 + 0.02 < _st.DEFAULT_LANDING_FT * 0.3048 \
                        and min(lw, lh) * 0.3048 < 0.9:
                    out.append(_issue("warn", "landing-small",
                                      f"A landing is only {min(lw, lh):.2f} ft "
                                      "across; it must be at least the width "
                                      "of the flight.", "", "§8.4"))
        if s.type.upper() == "U":
            if g["well"] is None:
                out.append(_issue("warn", "no-well",
                                  "U stair has no stairwell gap between the "
                                  "flights."))
            if g["landing"] is None:
                out.append(_issue("error", "no-landing",
                                  "U stair has no landing at the turn."))
            f1, f2 = g["flights"][0], g["flights"][1]
            if f1["dir"] == f2["dir"]:
                out.append(_issue("error", "flights-same-way",
                                  "Both flights of the U stair climb the same "
                                  "way — the half turn is missing."))
        if s.type.upper() == "L" and n == 2:
            if g["flights"][0]["axis"] == g["flights"][1]["axis"]:
                out.append(_issue("error", "l-not-turning",
                                  "An L stair's two flights must be "
                                  "perpendicular."))
        # the stair must stand inside the plan, not beside it. Two entry steps
        # read as a staircase land outside the walls, and that is the tell.
        fp_box = box(s.x, s.y, s.x + s.w, s.y + s.h)
        rooms = [box(r.x, r.y, r.x + r.w, r.y + r.h) for r in plan.rooms]
        if rooms:
            inside = unary_union(rooms).intersection(fp_box).area
            if fp_box.area > 0 and inside / fp_box.area < 0.5:
                out.append(_issue(
                    "error", "stair-outside",
                    f"The stair at ({s.x:.1f}, {s.y:.1f}) lies mostly outside "
                    "every room. Entry steps drawn beside a verandah are often "
                    "misread as a staircase — check the Stairs tab."))
        if max(s.w, s.h) > 0 and int(s.steps_f1 or s.treads) <= 3:
            out.append(_issue(
                "warn", "few-treads",
                f"This stair has only {int(s.steps_f1 or s.treads)} treads — if "
                "these are entry steps rather than a staircase, delete it."))

        # every flight must sit inside the stair footprint
        fp = box(s.x - 0.05, s.y - 0.05, s.x + s.w + 0.05, s.y + s.h + 0.05)
        for f in g["flights"]:
            fx, fy, fw, fh = f["rect"]
            if not fp.contains(box(fx, fy, fx + fw, fy + fh)):
                out.append(_issue("error", "flight-outside",
                                  "A stair flight falls outside the stair "
                                  "footprint."))
                break
    return out


def summary(issues: list[dict]) -> dict:
    return {
        "errors": sum(1 for i in issues if i["severity"] == "error"),
        "warnings": sum(1 for i in issues if i["severity"] == "warn"),
        "clean": not any(i["severity"] == "error" for i in issues),
    }
