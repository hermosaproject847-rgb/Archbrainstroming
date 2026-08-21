"""One call: plan dict -> preview SVG + validation + exported files."""

from __future__ import annotations

import os

from . import (autofix, eleclayout, engine, export, layers, layout, marks,
               sheet, validate, walltags)
from .model import Plan


def furnish(plan_dict: dict) -> tuple[dict, list[str]]:
    """Lay furniture over a finished floor plan."""
    return layout.furnish(plan_dict)


def electrify(plan_dict: dict) -> tuple[dict, list[str]]:
    """Lay the electrical and lighting over a furnished plan."""
    return eleclayout.design(plan_dict)


def plumb(plan_dict: dict) -> tuple[dict, list[str]]:
    """Lay the plumbing and drainage over a plan that has its fixtures."""
    from . import plumblayout
    return plumblayout.design(plan_dict)


def floor(plan_dict: dict) -> tuple[dict, list[str]]:
    """Set the flooring for every room."""
    from . import floorlayout
    return floorlayout.design(plan_dict)


def number_openings(plan_dict: dict, force: bool = False) -> tuple[dict, list]:
    """Mark every opening D1/W1/V1, and treat a window in a toilet as a
    ventilator. Run on demand — renumbering while the table is open would
    move the row being edited."""
    from dataclasses import asdict
    plan = Plan.from_dict(plan_dict)
    notes = marks.renumber(plan, force)
    out = dict(plan_dict)
    out["openings"] = [asdict(o) for o in plan.openings]
    return out, notes


def number_walls(plan_dict: dict, split: bool = True,
                 start: int = 1) -> tuple[dict, list[str]]:
    """Split walls at room boundaries and number them W1, W2, … .

    `start` continues the numbering across floors of a multi-floor project.
    Run on demand rather than on every redraw: renumbering while someone is
    working through the table would move the row they are looking at.
    """
    from dataclasses import asdict
    plan = Plan.from_dict(plan_dict)
    notes = walltags.split_by_rooms(plan) if split else []
    notes += walltags.renumber(plan, start=start)
    out = dict(plan_dict)
    walls = []
    for w in plan.walls:
        d = asdict(w)
        # the room the wall belongs to, so the table shows the same grouping
        # the numbering used
        d["room"] = walltags.owner_of(plan, w)
        walls.append(d)
    out["walls"] = walls
    out["openings"] = [asdict(o) for o in plan.openings]
    return out, notes


def _sheet_kind(plan, layer_state) -> str:
    """Which schedule this sheet should carry.

    The drawing you are looking at decides it: the floor plan gets the
    door/window schedule, the furniture layout its own schedule, the
    electrical its legend. A sheet never carries someone else's table.
    """
    from . import layers as LY
    off = LY.hidden_layers(layer_state)
    elec_on = bool(plan.elec) and "ELEC" not in off
    plumb_on = bool(plan.pipes) and "PLUMB-CW" not in off
    floor_on = bool(plan.flooring) and "FLR-GRID" not in off
    furn_on = bool(plan.furniture) and "FURNITURE" not in off
    if elec_on:
        return "electrical"
    if plumb_on:
        return "plumbing"          # its legend goes in the strip's LEGEND panel
    if floor_on:
        return "flooring"
    if furn_on:
        return "furniture"
    return "openings"


def _prepare(plan_dict: dict, fix: bool = True):
    plan = Plan.from_dict(plan_dict)
    notes = autofix.apply(plan) if fix else []
    # Rulebook §2.5/§3.2/§4.2: no opening may go out without its levels. Any
    # value taken from the typical table is reported, never applied silently.
    notes += validate.fill_levels(plan)
    return plan, notes, validate.validate(plan)


def render(plan_dict: dict, sheet_size: str = "A3",
           orientation: str = "auto", fix: bool = True,
           wall_tags: bool = True, furniture: bool = True,
           layer_state: dict | None = None) -> dict:
    """Build the drawing and return {svg, info, issues, fixes, summary}.

    `layer_state` turns whole groups off — furniture hidden while looking at
    the electrical, say. It is applied after composing, so the sheet still
    fits the full drawing and hiding a layer does not move anything.
    """
    plan, notes, issues = _prepare(plan_dict, fix)
    # the section line always shows on the ON-SCREEN plan (so it can be seen and
    # edited); hiding it from the furniture / electrical / plumbing / flooring
    # EXPORT sheets is handled in combined.py / export_all, not here
    dl = engine.build(plan, wall_tags, furniture, sections=True)
    sdl, info = sheet.compose(plan, dl, sheet_size, orientation,
                              schedule=_sheet_kind(plan, layer_state))
    sdl = layers.apply(sdl, layer_state)
    svg = export.to_svg(sdl, info["w_mm"], info["h_mm"])
    return {"svg": svg, "info": info, "issues": issues, "fixes": notes,
            "summary": validate.summary(issues)}


def render_fast(plan_dict: dict, sheet_size: str = "A3",
                orientation: str = "auto", wall_tags: bool = True,
                furniture: bool = True, layer_state: dict | None = None) -> dict:
    """DRAW ONLY — no validation / auto-fix (that pass is ~99% of a full render).
    Used for live interactive edits (dragging a door, nudging furniture) so the
    picture updates in ~2 ms instead of ~190 ms. The checks panel is refreshed
    separately by `check()` a moment after the user stops editing."""
    plan = Plan.from_dict(plan_dict)
    dl = engine.build(plan, wall_tags, furniture, sections=True)
    sdl, info = sheet.compose(plan, dl, sheet_size, orientation,
                              schedule=_sheet_kind(plan, layer_state))
    sdl = layers.apply(sdl, layer_state)
    svg = export.to_svg(sdl, info["w_mm"], info["h_mm"])
    return {"svg": svg, "info": info}


def check(plan_dict: dict, fix: bool = True) -> dict:
    """Validation only (issues / fixes / summary) with no drawing — the debounced
    companion to render_fast, to keep the checks panel current."""
    _plan, notes, issues = _prepare(plan_dict, fix)
    return {"issues": issues, "fixes": notes,
            "summary": validate.summary(issues)}


def export_all(plan_dict: dict, outdir: str, basename: str = "floor_plan",
               sheet_size: str = "A3", orientation: str = "auto",
               dpi: int = 220, fix: bool = True,
               wall_tags: bool = False, furniture: bool = True,
               layer_state: dict | None = None, sections: bool = True) -> dict:
    plan, notes, issues = _prepare(plan_dict, fix)
    # section line on the FLOOR PLAN sheet only (no overlay/layer view)
    dl = engine.build(plan, wall_tags, furniture,
                      sections=(sections and layer_state is None))
    sdl, info = sheet.compose(plan, dl, sheet_size, orientation,
                              schedule=_sheet_kind(plan, layer_state))
    sdl = layers.apply(sdl, layer_state)     # hidden layers stay out of every
                                             # file, not just the screen

    os.makedirs(outdir, exist_ok=True)
    paths = {}

    svg_p = os.path.join(outdir, basename + ".svg")
    with open(svg_p, "w", encoding="utf-8") as fh:
        fh.write(export.to_svg(sdl, info["w_mm"], info["h_mm"]))
    paths["svg"] = svg_p

    paths["png"] = export.to_png(sdl, info["w_mm"], info["h_mm"],
                                 os.path.join(outdir, basename + ".png"), dpi)
    paths["pdf"] = export.to_pdf(sdl, info["w_mm"], info["h_mm"],
                                 os.path.join(outdir, basename + ".pdf"))
    paths["dxf"] = export.to_dxf(sdl, os.path.join(outdir, basename + ".dxf"),
                                 model_scale=info["k"])

    with open(os.path.join(outdir, basename + ".json"), "w", encoding="utf-8") as fh:
        fh.write(plan.to_json())
    paths["json"] = os.path.join(outdir, basename + ".json")

    # Sheet 2 — only with the furniture drawing, never beside a bare plan
    if plan.furniture and furniture:
        from . import furnsched
        s2 = furnsched.build(plan, info["w_mm"], info["h_mm"])
        p2 = os.path.join(outdir, basename + "_schedule")
        with open(p2 + ".svg", "w", encoding="utf-8") as fh:
            fh.write(export.to_svg(s2, info["w_mm"], info["h_mm"]))
        export.to_png(s2, info["w_mm"], info["h_mm"], p2 + ".png", dpi)
        export.to_pdf(s2, info["w_mm"], info["h_mm"], p2 + ".pdf")
        paths["schedule"] = p2 + ".pdf"
        paths["schedule_png"] = p2 + ".png"

    return {"paths": paths, "info": info, "issues": issues, "fixes": notes,
            "summary": validate.summary(issues)}
