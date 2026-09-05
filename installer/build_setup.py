"""Build ARCH-BRAIN-STORMING-Setup.exe (the desktop installer) from the CURRENT code.

The installer is a 7-Zip SFX: installer/sfx-stub.bin (7zS.sfx + the
';!@Install@!' config that runs install.vbs after extraction) followed by a
plain .7z payload holding
    python/                 portable Python 3.12 + packages (SketchToPlan/python,
                            git-ignored — copied out of the previous installer)
    core/ ui/ prompts/ samples/ app.py      the software (same files the web build uses)
    install.vbs  "ARCH BRAIN STORMING.vbs"  "Run in debug mode.bat"
Run:  BUILD-SETUP.bat   (or  python installer\\build_setup.py)
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INST = os.path.join(ROOT, "installer")
SEVENZ = next((p for p in (r"C:\Program Files\7-Zip\7z.exe",
                           r"C:\Program Files (x86)\7-Zip\7z.exe")
               if os.path.isfile(p)), None)
if not SEVENZ:
    sys.exit("7-Zip (7z.exe) not found")
if not os.path.isdir(os.path.join(ROOT, "python")):
    sys.exit("SketchToPlan\\python (portable runtime) missing — extract it from "
             "the previous ARCH-BRAIN-STORMING-Setup.exe with 7-Zip")

tmp = tempfile.mkdtemp(prefix="abs-setup-")
pay = os.path.join(tmp, "payload")
os.makedirs(pay)
IGN = shutil.ignore_patterns("__pycache__", "*.pyc", "*.bak", "tmp_proj.json")
for d in ("python", "core", "prompts", "samples", "ui"):
    shutil.copytree(os.path.join(ROOT, d), os.path.join(pay, d), ignore=IGN)
shutil.copy2(os.path.join(ROOT, "app.py"), pay)
for f in ("install.vbs", "ARCH BRAIN STORMING.vbs", "Run in debug mode.bat"):
    shutil.copy2(os.path.join(INST, f), pay)
for d in ("out", "work"):
    os.makedirs(os.path.join(pay, d), exist_ok=True)

arch = os.path.join(tmp, "payload.7z")
subprocess.check_call([SEVENZ, "a", "-t7z", "-mx=7", "-m0=BCJ",
                       "-m1=LZMA2:d=24m", "-ms=on", arch, "."],
                      cwd=pay, stdout=subprocess.DEVNULL)
out = os.path.join(ROOT, "ARCH-BRAIN-STORMING-Setup.exe")
with open(out, "wb") as fo:
    with open(os.path.join(INST, "sfx-stub.bin"), "rb") as fi:
        fo.write(fi.read())
    with open(arch, "rb") as fi:
        shutil.copyfileobj(fi, fo)
shutil.rmtree(tmp, ignore_errors=True)
print("built", out, round(os.path.getsize(out) / 1e6, 1), "MB")
