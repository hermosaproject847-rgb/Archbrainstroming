"""Questionnaire brief -> plan JSON, DESIGNED by Claude.

Same Claude CLI that powers the (perfect) sketch reader, but driven by a written
brief instead of an image: it DESIGNS a floor plan to the requirements and NBC
standards and writes the same plan-JSON the rest of the pipeline consumes. This
is the accurate route - a rules engine / template stretch cannot match it.
"""

from __future__ import annotations

import json
import os
import tempfile
import time

from . import reader

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPT = os.path.join(ROOT, "prompts", "design_prompt.md")


def _ftin(v):
    v = float(v or 0)
    f = int(v)
    inch = int(round((v - f) * 12))
    if inch == 12:
        f += 1
        inch = 0
    return f"{f}'-{inch}\"" if inch else f"{f}'-0\""


def brief_text(a: dict) -> str:
    """Turn the questionnaire answers into a clear written brief for the AI."""
    L = []
    if a.get("project"):
        L.append(f"Project: {a['project']}")
    pw, pd = a.get("plot_w"), a.get("plot_d")
    L.append(f"Plot size: {_ftin(pw)} wide x {_ftin(pd)} deep "
             f"({pw} ft x {pd} ft).")
    sb = []
    for k, lab in (("setback_front", "front"), ("setback_rear", "rear"),
                   ("setback_left", "left"), ("setback_right", "right")):
        if float(a.get(k, 0) or 0) > 0:
            sb.append(f"{lab} {_ftin(a[k])}")
    L.append("Set-backs: " + (", ".join(sb) if sb else "none (build to plot edges)."))
    L.append(f"Entry / road is on the {a.get('entry', 'south').upper()} side.")
    L.append(f"Number of floors: {int(a.get('floors', 1) or 1)} "
             f"(design the GROUND floor).")

    rooms = []
    n_bed = int(a.get("bedrooms", 2) or 0)
    att = a.get("attached", "all")
    if a.get("master", True) and n_bed:
        att_txt = {"all": "with attached toilet", "master": "with attached toilet",
                   "none": "no attached toilet"}.get(att, "with attached toilet")
        rooms.append(f"1 Master bedroom ({att_txt})")
        rest = n_bed - 1
    else:
        rest = n_bed
    if rest > 0:
        if att == "all":
            rooms.append(f"{rest} more bedroom(s), each with an attached toilet")
        else:
            rooms.append(f"{rest} more bedroom(s) (common bath)")
    if a.get("living_dining_combined"):
        rooms.append("a combined Living/Dining")
    else:
        rooms.append("a Living room")
        if a.get("dining", True):
            rooms.append("a separate Dining")
    rooms.append("a Kitchen")
    if a.get("utility"):
        rooms.append("a Utility")
    if a.get("powder", True):
        rooms.append("a Powder toilet")
    if a.get("common_bath"):
        rooms.append("a Common bathroom")
    if a.get("pooja"):
        rooms.append("a Pooja room")
    if a.get("store"):
        rooms.append("a Store")
    if int(a.get("floors", 1) or 1) > 1 or a.get("staircase", True):
        rooms.append("an internal Staircase")
    L.append("Rooms required on the ground floor: " + "; ".join(rooms) + ".")
    if a.get("notes"):
        L.append("Extra notes: " + str(a["notes"]))
    return "\n".join("- " + x for x in L)


def design(answers: dict, workdir: str | None = None,
           on_log=None, timeout: int = 1800) -> dict:
    """Return {'plan': dict|None, 'log': str, 'error': str}."""
    log = on_log or (lambda _s: None)
    st = reader.cli_status()
    if not st.get("ok"):
        return {"plan": None, "log": "", "error": st.get("error", "")}
    exe = st["exe"]

    workdir = workdir or tempfile.mkdtemp(prefix="design_")
    os.makedirs(workdir, exist_ok=True)
    out_json = os.path.join(workdir, "plan.json")
    try:
        if os.path.isfile(out_json):
            os.remove(out_json)
    except OSError:
        pass

    with open(PROMPT, encoding="utf-8") as fh:
        prompt = fh.read()
    prompt = (prompt.replace("{BRIEF}", brief_text(answers or {}))
                    .replace("{OUT_PATH}", out_json))

    log("Claude is designing the plan from your brief…")
    t0 = time.time()
    import subprocess
    _no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # hide claude's
    try:                                                     # console on Windows
        proc = subprocess.Popen(
            [exe, "-p", prompt, "--permission-mode", "acceptEdits"],
            cwd=workdir, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
            creationflags=_no_window)
    except Exception as e:
        return {"plan": None, "log": "",
                "error": f"Could not start the Claude CLI: {e}"}
    reader._ACTIVE.add(proc)
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        return {"plan": None, "log": "",
                "error": f"Design passed {round(timeout / 60)} min and was stopped."}
    finally:
        reader._ACTIVE.discard(proc)

    log(f"Design finished in {time.time() - t0:.0f}s.")
    text = (out or "") + "\n" + (err or "")
    if reader._NOT_LOGGED_IN.search(text):
        return {"plan": None, "log": text, "error": reader.NOT_LOGGED_IN_MSG}
    plan = reader._extract_json(text, out_json)
    if plan is None:
        return {"plan": None, "log": text,
                "error": "Claude did not return a usable plan. See the log."}
    return {"plan": plan, "log": text, "error": ""}
