"""The combined export: one folder, and one DXF holding both drawings."""
import json
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from core import combined, pipeline  # noqa: E402

src = os.path.join(ROOT, "out", "verandah_fixed.json")
with open(src, encoding="utf-8") as fh:
    plan = json.load(fh)

furnished, _ = pipeline.furnish(plan)
res = combined.export_folder(furnished, os.path.join(ROOT, "out"),
                             "Verandah House")

print("folder :", os.path.basename(res["folder"]))
print("SUMMARY", res["summary"])
for f in sorted(os.listdir(res["folder"])):
    print("   ", f)

import ezdxf  # noqa: E402
doc = ezdxf.readfile(res["paths"]["combined_dxf"])
msp = doc.modelspace()
counts = Counter(e.dxf.layer for e in msp)
print("\ncombined DXF, entities per layer:")
for k, v in sorted(counts.items()):
    print(f"   {k:12} {v:5}")

xs = [p[0] for e in msp if e.dxftype() == "LWPOLYLINE"
      for p in e.get_points("xy")]
print(f"\n   x spans {min(xs):.1f} .. {max(xs):.1f}")
mid = (min(xs) + max(xs)) / 2
left = sum(1 for x in xs if x < mid)
right = len(xs) - left
print(f"   {left} points left of centre, {right} right "
      f"-> {'two drawings side by side' if left and right else 'ONLY ONE'}")
print("   FURNITURE on the sheet:", counts.get("FURNITURE", 0), "entities")
