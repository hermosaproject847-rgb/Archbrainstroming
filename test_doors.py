"""Door symbols: single leaf, double leaf, sliding — all on one plan."""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from core import pipeline  # noqa: E402

PLAN = {
    "title": {"project": "DOOR SYMBOLS", "plan_name": "TYPES",
              "wall_note": "SINGLE / DOUBLE / SLIDING LEAF"},
    "walls": [
        {"id": "W1", "x1": 0, "y1": 0, "x2": 30, "y2": 0,
         "thickness_in": 9, "exterior": True},
        {"id": "W2", "x1": 0, "y1": 14, "x2": 30, "y2": 14,
         "thickness_in": 9, "exterior": True},
        {"id": "W3", "x1": 0, "y1": 0, "x2": 0, "y2": 14,
         "thickness_in": 9, "exterior": True},
        {"id": "W4", "x1": 30, "y1": 0, "x2": 30, "y2": 14,
         "thickness_in": 9, "exterior": True},
        {"id": "W5", "x1": 10, "y1": 0, "x2": 10, "y2": 14,
         "thickness_in": 4.5},
        {"id": "W6", "x1": 20, "y1": 0, "x2": 20, "y2": 14,
         "thickness_in": 4.5},
    ],
    "rooms": [
        {"name": "Single", "x": 0, "y": 0, "w": 10, "h": 14,
         "size_label": "SINGLE LEAF"},
        {"name": "Double", "x": 10, "y": 0, "w": 10, "h": 14,
         "size_label": "DOUBLE LEAF"},
        {"name": "Sliding", "x": 20, "y": 0, "w": 10, "h": 14,
         "size_label": "SLIDING"},
    ],
    "openings": [
        {"type": "single_door", "tag": "D1", "wall_id": "W1", "pos": 3,
         "width": 3, "swing": {"room": "Single"}},
        {"type": "double_door", "tag": "D2", "wall_id": "W1", "pos": 12,
         "width": 6, "swing": {"room": "Double"}},
        {"type": "sliding_door", "tag": "D3", "wall_id": "W1", "pos": 23,
         "width": 5, "swing": {"room": "Sliding"}},
        # left as single, but 5 ft is over 1200 mm — the width makes it double
        {"type": "single_door", "tag": "D4", "wall_id": "W5", "pos": 4,
         "width": 5, "swing": {"room": "Double"}},
        {"type": "window", "tag": "W1", "wall_id": "W2", "pos": 3, "width": 4},
    ],
}

res = pipeline.export_all(PLAN, os.path.join(ROOT, "out"), "door_types",
                          wall_tags=True)
print("SUMMARY", res["summary"])
for i in res["issues"]:
    print(f"  [{i['severity']}] {i['code']}: {i['message'][:80]}")
print(res["paths"]["png"])
