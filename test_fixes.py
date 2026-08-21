"""Two regressions, both reported from a real drawing:

  1. a shaft (O.T.S) lost the walls enclosing it, because a shaft is open to
     the sky and was being treated as just another open area;
  2. flipping a door's swing by hand did nothing, because the auto-fix pass
     recomputed it on the very next redraw.
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from core import autofix, engine  # noqa: E402
from core.model import Plan  # noqa: E402

# O.T.S sits between a terrace and a bedroom, walled all round.
BASE = {
    "walls": [
        {"id": "EX-S", "x1": 0, "y1": 0, "x2": 20, "y2": 0,
         "thickness_in": 9, "exterior": True},
        {"id": "EX-N", "x1": 0, "y1": 12, "x2": 20, "y2": 12,
         "thickness_in": 9, "exterior": True},
        {"id": "EX-W", "x1": 0, "y1": 0, "x2": 0, "y2": 12,
         "thickness_in": 9, "exterior": True},
        {"id": "EX-E", "x1": 20, "y1": 0, "x2": 20, "y2": 12,
         "thickness_in": 9, "exterior": True},
        # the wall between the terrace and the shaft — this is the one that
        # was going missing
        {"id": "P-OTS-W", "x1": 8, "y1": 6, "x2": 8, "y2": 12,
         "thickness_in": 4.5},
        {"id": "P-OTS-S", "x1": 8, "y1": 6, "x2": 14, "y2": 6,
         "thickness_in": 4.5},
        {"id": "P-OTS-E", "x1": 14, "y1": 6, "x2": 14, "y2": 12,
         "thickness_in": 4.5},
        {"id": "P-BED-S", "x1": 0, "y1": 6, "x2": 8, "y2": 6,
         "thickness_in": 4.5},
    ],
    "rooms": [
        {"name": "Bed Room", "x": 0, "y": 0, "w": 20, "h": 6,
         "open_area": False},
        {"name": "Open Terrace", "x": 0, "y": 6, "w": 8, "h": 6,
         "open_area": True},
        {"name": "O.T.S", "x": 8, "y": 6, "w": 6, "h": 6,
         "open_area": True},
        {"name": "Store", "x": 14, "y": 6, "w": 6, "h": 6,
         "open_area": False},
    ],
    "openings": [
        {"type": "door", "tag": "D1", "wall_id": "P-BED-S", "pos": 2,
         "width": 3, "swing": {"room": "Bed Room"}},
    ],
}


def ots_walls_survive() -> bool:
    plan = Plan.from_dict(BASE)
    ots = plan.room("O.T.S")
    print(f"  O.T.S recognised as a shaft: {ots.void}")
    autofix.apply(plan)
    cut = engine.cut_solid(plan)
    from shapely.geometry import Point
    ok = True
    for wid, pt in (("P-OTS-W", (8, 9)), ("P-OTS-S", (11, 6)),
                    ("P-OTS-E", (14, 9))):
        there = cut.contains(Point(pt))
        print(f"  {wid} still drawn: {there}")
        ok = ok and there
    return ok


def manual_swing_is_kept() -> bool:
    plan = Plan.from_dict(BASE)
    autofix.apply(plan)
    auto = plan.openings[0].swing.side
    flipped = "right" if auto == "left" else "left"
    print(f"  auto-fix chose side={auto}; flipping to {flipped}")

    # what the app does when the swing is edited by hand
    d = {**BASE, "openings": [{**BASE["openings"][0],
                               "swing": {"room": "Bed Room", "hinge": "start",
                                         "side": flipped, "manual": True}}]}
    plan2 = Plan.from_dict(d)
    autofix.apply(plan2)
    kept = plan2.openings[0].swing.side
    print(f"  after a redraw the side is {kept}")
    return kept == flipped


print("shaft walls")
a = ots_walls_survive()
print("manual door flip")
b = manual_swing_is_kept()
print(f"\nshaft walls kept: {'PASS' if a else 'FAIL'}")
print(f"manual flip kept: {'PASS' if b else 'FAIL'}")
sys.exit(0 if (a and b) else 1)
