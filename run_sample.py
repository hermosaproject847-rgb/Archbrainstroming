"""Smoke test: render samples/sample_plan.json to out/."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from core import pipeline  # noqa: E402

src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "samples", "sample_plan.json")
name = os.path.splitext(os.path.basename(src))[0]

with open(src, encoding="utf-8") as fh:
    data = json.load(fh)

res = pipeline.export_all(data, os.path.join(ROOT, "out"), name)

print("INFO   ", res["info"])
print("SUMMARY", res["summary"])
for i in res["issues"]:
    print(f"  [{i['severity']:5}] {i['code']:24} {i['message']}")
print("FILES")
for k, v in res["paths"].items():
    print(f"  {k:4} {v}")
