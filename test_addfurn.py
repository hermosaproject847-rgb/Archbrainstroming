"""Adding furniture by category: the right size, the right symbol, placed."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from core import furniture as F, furnsym, layout, pipeline  # noqa: E402

print("catalogue")
missing = []
for g in F.catalogue():
    names = ", ".join(i["label"] for i in g["items"])
    print(f"  {g['category']:9} {names}")
    for i in g["items"]:
        fam = F.family(i["kind"])
        if fam not in furnsym._SYMBOLS and i["kind"] not in furnsym._SYMBOLS:
            missing.append(i["kind"])
print("\nevery catalogue item has a symbol:",
      "YES" if not missing else f"NO — {missing}")

src = os.path.join(ROOT, "out", "verandah_fixed.json")
with open(src, encoding="utf-8") as fh:
    plan = json.load(fh)
plan, _ = pipeline.furnish(plan)
start = len(plan["furniture"])
print(f"\nlaid out: {start} pieces")

# one from every category, into whichever room suits
for kind, room in (("armchair", "Bedroom"), ("chair", "Office"),
                   ("shoe_rack", "Foyer"), ("sideboard", "Kitchen"),
                   ("stool", "Office")):
    plan, msg = layout.add_piece(plan, kind, room)
    print("  ", msg)

added = len(plan["furniture"]) - start
print(f"\nadded {added} piece(s)")

res = pipeline.export_all(plan, os.path.join(ROOT, "out"), "addfurn_test")
print("SUMMARY", res["summary"])
for i in res["issues"]:
    if "furniture" in i["code"] or "clearance" in i["code"]:
        print(f"   [{i['severity']}] {i['code']}: {i['message'][:70]}")
print(res["paths"]["png"])
