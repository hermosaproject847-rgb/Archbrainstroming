"""Opening marks: bare letters get numbered, toilet windows become vents."""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from core import pipeline  # noqa: E402

# every opening carries only its letter, as a sketch usually draws them
PLAN = {
    "title": {"project": "MARKS", "plan_name": "TEST"},
    "walls": [
        {"id": "W1", "x1": 0, "y1": 0, "x2": 30, "y2": 0,
         "thickness_in": 9, "exterior": True},
        {"id": "W2", "x1": 0, "y1": 20, "x2": 30, "y2": 20,
         "thickness_in": 9, "exterior": True},
        {"id": "W3", "x1": 0, "y1": 0, "x2": 0, "y2": 20,
         "thickness_in": 9, "exterior": True},
        {"id": "W4", "x1": 30, "y1": 0, "x2": 30, "y2": 20,
         "thickness_in": 9, "exterior": True},
        {"id": "W5", "x1": 12, "y1": 0, "x2": 12, "y2": 20,
         "thickness_in": 4.5},
        {"id": "W6", "x1": 12, "y1": 10, "x2": 30, "y2": 10,
         "thickness_in": 4.5},
    ],
    "rooms": [
        {"name": "Bed Room", "x": 0, "y": 0, "w": 12, "h": 20,
         "size_label": "12'-0\" x 20'-0\""},
        {"name": "Toilet", "x": 12, "y": 0, "w": 18, "h": 10,
         "size_label": "18'-0\" x 10'-0\""},
        {"name": "Bath", "x": 12, "y": 10, "w": 18, "h": 10,
         "size_label": "18'-0\" x 10'-0\""},
    ],
    "openings": [
        # bare letters, exactly as a sketch labels them
        {"type": "window", "tag": "W", "wall_id": "W3", "pos": 3, "width": 4},
        {"type": "window", "tag": "W", "wall_id": "W3", "pos": 13, "width": 4},
        {"type": "window", "tag": "W", "wall_id": "W2", "pos": 3, "width": 4},
        # windows drawn in the wet rooms — these must become ventilators
        {"type": "window", "tag": "W", "wall_id": "W4", "pos": 3, "width": 2},
        {"type": "window", "tag": "W", "wall_id": "W4", "pos": 14, "width": 2},
        {"type": "single_door", "tag": "D", "wall_id": "W1", "pos": 4,
         "width": 3, "swing": {"room": "Bed Room"}},
        {"type": "single_door", "tag": "D", "wall_id": "W5", "pos": 3,
         "width": 2.5, "swing": {"room": "Toilet"}},
        # a mark the sketch already made distinct — it must survive
        {"type": "single_door", "tag": "D7", "wall_id": "W6", "pos": 4,
         "width": 2.5, "swing": {"room": "Bath"}},
    ],
}

out, notes = pipeline.number_openings(PLAN)
print("what changed:")
for n in notes:
    print("  ", n)

print("\nresult:")
for o in out["openings"]:
    print(f"  {o['tag']:4} {o['type']:14} "
          f"sill {o.get('sill_mm') or 0:6.0f}  "
          f"lintel {o.get('lintel_mm') or 0:6.0f}")

tags = [o["tag"] for o in out["openings"]]
print("\nall marks distinct:", len(tags) == len(set(tags)))
print("D7 kept:", "D7" in tags)
print("two ventilators:", sum(1 for o in out["openings"]
                              if o["type"] == "vent") == 2)

res = pipeline.export_all(out, os.path.join(ROOT, "out"), "marks_test")
print("SUMMARY", res["summary"])
for i in res["issues"]:
    print(f"  [{i['severity']}] {i['code']}: {i['message'][:70]}")
