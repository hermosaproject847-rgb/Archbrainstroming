"""The electrical layout, and layer visibility."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from core import layers as LY, pipeline  # noqa: E402

src = os.path.join(ROOT, "out", "verandah_fixed.json")
with open(src, encoding="utf-8") as fh:
    plan = json.load(fh)

plan, _ = pipeline.furnish(plan)
plan, notes = pipeline.electrify(plan)

print(f"points {len(plan['elec'])}   circuits {len(plan['circuits'])}")
s = plan["elec_summary"]
print(f"connected {s['connected_w']/1000:.2f} kW   "
      f"demand {s['demand_w']/1000:.2f} kW   "
      f"sanction {s['sanctioned_kw']} kW")

print("\nlayer views")
for view in ("floor", "furniture", "electrical", "all"):
    st = LY.for_view(view)
    hidden = LY.hidden_layers(st)
    res = pipeline.render(plan, layer_state=st)
    n = res["svg"].count("<line") + res["svg"].count("<poly") \
        + res["svg"].count("<text")
    print(f"  {view:11} {n:5} elements   hides: "
          f"{', '.join(sorted(hidden)) or 'nothing'}")
    pipeline.export_all(plan, os.path.join(ROOT, "out"),
                        "elec_view_" + view, layer_state=st)

# Prove it from the DXF, where every entity carries its layer name — colours
# are shared between layers, so counting them would prove nothing.
import ezdxf  # noqa: E402
from collections import Counter  # noqa: E402

print("\nwhat each exported view actually contains")
ok = True
for view in ("floor", "furniture", "electrical", "all"):
    doc = ezdxf.readfile(os.path.join(ROOT, "out",
                                      f"elec_view_{view}.dxf"))
    c = Counter(e.dxf.layer for e in doc.modelspace())
    furn = c.get("FURNITURE", 0)
    elec = c.get("ELEC", 0)
    print(f"  {view:11} FURNITURE {furn:4}   ELEC {elec:4}")
    if view == "floor" and (furn or elec):
        ok = False
    if view == "furniture" and (not furn or elec):
        ok = False
    if view == "electrical" and (furn or not elec):
        ok = False
    if view == "all" and not (furn and elec):
        ok = False
print("\nlayer visibility behaves:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
