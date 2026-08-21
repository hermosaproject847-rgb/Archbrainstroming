"""Three-flight stair: two square landings, a short flight between them.

Figures from the user's sketch: 4'-2" flights, 3'-0" x 3'-0" landings.
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from core import pipeline, stairs  # noqa: E402
from core.model import Stair  # noqa: E402

W = H = 11.0
S = Stair(x=0, y=0, w=W, h=H, type="U3", run_axis="x", up_from="left",
          turn_side="right", steps_f1=7, steps_f2=7, steps_f3=2,
          landing_size=3.0, start_step=1, show_dn=True)

g = stairs.build(S)
print(f"flights {len(g['flights'])}   landings {len(g.get('landings') or [])}")
for i, f in enumerate(g["flights"], start=1):
    x, y, w, h = f["rect"]
    print(f"  flight {i}: {w:5.2f} x {h:5.2f}  runs {f['axis']} "
          f"dir {f['dir']:+d}  {f['steps']} treads")
for i, (x, y, w, h) in enumerate(g.get("landings") or [], start=1):
    sq = "square" if abs(w - h) < 0.02 else "NOT SQUARE"
    print(f"  landing {i}: {w:5.2f} x {h:5.2f}  {sq}")

inside = all(x >= -.01 and y >= -.01 and x + w <= W + .01 and y + h <= H + .01
             for (x, y, w, h) in
             [f["rect"] for f in g["flights"]] + (g.get("landings") or []))
print("everything inside the footprint:", inside)

# every orientation, so no combination can produce a broken stair
bad = 0
for ax in ("x", "y"):
    for uf in ("left", "right", "top", "bottom"):
        for ts in ("left", "right", "top", "bottom"):
            gg = stairs.build(Stair(x=0, y=0, w=W, h=H, type="U3",
                                    run_axis=ax, up_from=uf, turn_side=ts,
                                    steps_f1=7, steps_f2=7, steps_f3=2,
                                    landing_size=3.0))
            for (x, y, w, h) in ([f["rect"] for f in gg["flights"]]
                                 + (gg.get("landings") or [])):
                if not (x >= -.01 and y >= -.01
                        and x + w <= W + .01 and y + h <= H + .01):
                    bad += 1
            if len(gg.get("landings") or []) != 2:
                bad += 1
print(f"32 orientations checked, {bad} failures")

PLAN = {
    "title": {"project": "STAIR TYPES", "plan_name": "THREE-FLIGHT",
              "wall_note": "TWO SQUARE LANDINGS, SHORT MIDDLE FLIGHT"},
    "walls": [
        {"id": "W1", "x1": 0, "y1": 0, "x2": 13, "y2": 0,
         "thickness_in": 9, "exterior": True},
        {"id": "W2", "x1": 0, "y1": 13, "x2": 13, "y2": 13,
         "thickness_in": 9, "exterior": True},
        {"id": "W3", "x1": 0, "y1": 0, "x2": 0, "y2": 13,
         "thickness_in": 9, "exterior": True},
        {"id": "W4", "x1": 13, "y1": 0, "x2": 13, "y2": 13,
         "thickness_in": 9, "exterior": True},
    ],
    "rooms": [{"name": "Room Stair", "x": 0, "y": 0, "w": 13, "h": 13}],
    "openings": [{"type": "single_door", "tag": "D1", "wall_id": "W3",
                  "pos": 4, "width": 3, "swing": {"room": "Room Stair"}}],
    "stairs": [{"x": 1, "y": 1, "w": 11, "h": 11, "type": "U3",
                "run_axis": "x", "up_from": "left", "turn_side": "right",
                "steps_f1": 7, "steps_f2": 7, "steps_f3": 2,
                "landing_size": 3, "start_step": 1, "show_dn": True}],
}
res = pipeline.export_all(PLAN, os.path.join(ROOT, "out"), "stair_u3")
print("SUMMARY", res["summary"])
for i in res["issues"]:
    print(f"  [{i['severity']}] {i['code']}: {i['message'][:75]}")
print(res["paths"]["png"])
