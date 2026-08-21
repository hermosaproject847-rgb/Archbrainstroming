"""Plan TEMPLATE library - the accurate, offline route to questionnaire plans.

Instead of inventing a layout from rules (which only ever gives a rough draft),
we keep a library of REAL, proven plans (the user's own past bungalows, imported
as plans) tagged with plot size / bedrooms / floors / rooms. The questionnaire
then picks the closest template and FITS it to the exact plot - so the result is
a genuine design, just re-proportioned, not something computed from scratch.

A template is a normal plan dict plus a small `meta` block. Templates live as
JSON files under templates/ so they can be inspected, shared and version-safe.
"""

from __future__ import annotations

import json
import os
import re
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, "templates")

_BED = re.compile(r"bed\s*room|master|guest\s*room", re.I)
_TOILET = re.compile(r"toilet|bath|w\.?c|powder", re.I)


def _has(rooms, *subs):
    for r in rooms:
        nm = (r.get("name") or "").lower()
        if any(s in nm for s in subs):
            return True
    return False


def _count_beds(rooms):
    n = 0
    for r in rooms:
        nm = (r.get("name") or "")
        if _BED.search(nm) and not _TOILET.search(nm):
            n += 1
    return n


def _floors(plan):
    m = (plan.get("meta") or {}).get("floors")
    if m:
        return int(m)
    name = ((plan.get("title") or {}).get("plan_name") or "").lower()
    if "first" in name or "upper" in name or "typical" in name:
        return 2
    return 1


def meta_of(plan: dict) -> dict:
    rooms = plan.get("rooms") or []
    plot = plan.get("plot") or {}
    return {
        "plot_w": round(float(plot.get("w") or 0), 2),
        "plot_d": round(float(plot.get("h") or 0), 2),
        "bedrooms": _count_beds(rooms),
        "floors": _floors(plan),
        "rooms": len(rooms),
        "kitchen": _has(rooms, "kitchen"),
        "dining": _has(rooms, "dining"),
        "pooja": _has(rooms, "pooja"),
        "store": _has(rooms, "store"),
        "name": (plan.get("title") or {}).get("plan_name") or "Untitled",
    }


def _slug(s):
    s = re.sub(r"[^A-Za-z0-9]+", "_", str(s)).strip("_")
    return s[:40] or "template"


def save(plan: dict, label: str = "") -> dict:
    """Store the given plan as a template. Returns its meta + path."""
    os.makedirs(DIR, exist_ok=True)
    m = meta_of(plan)
    if label:
        m["name"] = label
    stamp = str(int(time.time()))
    fn = f"{_slug(m['name'])}_{int(m['plot_w'])}x{int(m['plot_d'])}_{stamp}.json"
    path = os.path.join(DIR, fn)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"meta": m, "plan": plan}, fh)
    m["path"] = path
    return m


def library() -> list:
    """Every template's meta + path, newest first."""
    out = []
    if not os.path.isdir(DIR):
        return out
    for fn in os.listdir(DIR):
        if not fn.endswith(".json"):
            continue
        p = os.path.join(DIR, fn)
        try:
            with open(p, encoding="utf-8") as fh:
                rec = json.load(fh)
            m = dict(rec.get("meta") or meta_of(rec.get("plan") or {}))
            m["path"] = p
            out.append(m)
        except Exception:
            continue
    out.sort(key=lambda m: os.path.getmtime(m["path"]), reverse=True)
    return out


def delete(path: str) -> bool:
    try:
        if os.path.commonpath([os.path.abspath(path), DIR]) == DIR:
            os.remove(path)
            return True
    except Exception:
        pass
    return False


def _score(m: dict, brief: dict) -> float:
    """Lower = better match. Bedroom count dominates; then the template must be
    a SIMILAR SIZE (a mansion squashed onto a narrow plot is the worst failure);
    then floors, then proportion. Optional rooms are a small nudge."""
    s = 0.0
    s += abs(int(m.get("bedrooms", 0)) - int(brief.get("bedrooms", 0))) * 120
    tw, td = m.get("plot_w") or 1, m.get("plot_d") or 1
    bw, bd = brief.get("plot_w") or 1, brief.get("plot_d") or 1
    # ABSOLUTE size mismatch — the fit stretches the template to the plot, so a
    # very different size means heavy distortion. Penalise it hard, relative to
    # the plot so it scales sensibly.
    s += abs(tw - bw) / max(bw, 1) * 120
    s += abs(td - bd) / max(bd, 1) * 120
    if m.get("floors") and brief.get("floors"):
        s += abs(int(m["floors"]) - int(brief["floors"])) * 30
    ar_t = tw / td if td else 1
    ar_b = bw / bd if bd else 1
    s += abs(ar_t - ar_b) * 40
    for k in ("pooja", "store", "dining"):
        if brief.get(k) and not m.get(k):
            s += 5
    return s


def design(brief: dict, max_score: float = 130.0):
    """Pick the best template for the brief and FIT it to the plot. Returns
    (plan, meta) or (None, None) if the library has nothing close enough."""
    lib = library()
    if not lib:
        return None, None
    lib.sort(key=lambda m: _score(m, brief))
    best = lib[0]
    if _score(best, brief) > max_score:
        return None, None
    with open(best["path"], encoding="utf-8") as fh:
        rec = json.load(fh)
    plan = fit(rec.get("plan") or {}, brief.get("plot_w"), brief.get("plot_d"))
    return plan, best


def fit(plan: dict, plot_w: float, plot_d: float) -> dict:
    """Re-proportion a template plan to an exact plot (anisotropic scale about
    the plot origin). Walls, rooms and openings all scale together."""
    import copy
    plan = copy.deepcopy(plan)
    src = plan.get("plot") or {}
    sw = float(src.get("w") or plot_w or 1) or 1
    sd = float(src.get("h") or plot_d or 1) or 1
    ox = float(src.get("x") or 0)
    oy = float(src.get("y") or 0)
    kx = (float(plot_w) / sw) if plot_w else 1.0
    ky = (float(plot_d) / sd) if plot_d else 1.0

    def sx(v):
        return round(ox + (float(v) - ox) * kx, 3)

    def sy(v):
        return round(oy + (float(v) - oy) * ky, 3)

    # wall_id -> the factor its LENGTH scales by (so openings stay in place)
    wfac = {}
    for w in plan.get("walls") or []:
        w["x1"], w["y1"] = sx(w["x1"]), sy(w["y1"])
        w["x2"], w["y2"] = sx(w["x2"]), sy(w["y2"])
        horiz = abs(w["x2"] - w["x1"]) >= abs(w["y2"] - w["y1"])
        wfac[w.get("id")] = kx if horiz else ky

    for r in plan.get("rooms") or []:
        nx, ny = sx(r["x"]), sy(r["y"])
        nw = round((float(r["x"]) + float(r["w"]) - float(r["x"])) * kx, 3)
        nh = round((float(r["y"]) + float(r["h"]) - float(r["y"])) * ky, 3)
        r["x"], r["y"], r["w"], r["h"] = nx, ny, max(0.5, nw), max(0.5, nh)
        r["size_label"] = f'{_ftin(r["w"])} x {_ftin(r["h"])}'

    for o in plan.get("openings") or []:
        f = wfac.get(o.get("wall_id"), (kx + ky) / 2)
        o["pos"] = round(float(o.get("pos", 0)) * f, 3)
        o["width"] = round(float(o.get("width", 3)) * f, 3)

    for s in plan.get("stairs") or []:
        s["x"], s["y"] = sx(s["x"]), sy(s["y"])
        s["w"] = round(float(s["w"]) * kx, 3)
        s["h"] = round(float(s["h"]) * ky, 3)

    plan["plot"] = {"x": ox, "y": oy, "w": float(plot_w), "h": float(plot_d)}
    t = plan.get("title") or {}
    t["plot_size"] = f"{_ftin(plot_w)} X {_ftin(plot_d)}"
    plan["title"] = t
    plan["dims"] = [{"axis": "top", "at": 2, "ticks": [0, float(plot_w)]},
                    {"axis": "left", "at": 2, "ticks": [0, float(plot_d)]}]
    return plan


def _ftin(v):
    v = float(v)
    f = int(v)
    inch = int(round((v - f) * 12))
    if inch == 12:
        f += 1
        inch = 0
    return f"{f}'-{inch}\"" if inch else f"{f}'-0\""
