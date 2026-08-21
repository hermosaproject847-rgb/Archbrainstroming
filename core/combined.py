"""One DXF carrying the whole set of drawings, in order.

Sheet 1 the floor plan, Sheet 2 the furniture layout, Sheet 3 the electrical
layout — each present only if that stage has been run, each laid out left to
right at one scale so the set reads across in the order it was designed. Any
schedule a sheet owns sits under that sheet: the furniture schedule under the
furniture plan, the circuit schedule under the electrical plan.

Each drawing keeps its own border and title strip, so the file still reads as
a set of proper sheets rather than things dropped next to each other.
"""

from __future__ import annotations

import os

from . import (autofix, elecsched, engine, export, furnsched, sheet, validate)
from .draw import DrawList
from .model import Plan

GAP_MM = 25.0            # between adjacent drawings on the sheet
TITLE_H = 5.0


def _titled(dl: DrawList, w_mm: float, h_mm: float, title: str,
            subtitle: str = "") -> DrawList:
    """A drawing inside its own border, with a caption under it."""
    out = DrawList()
    out.rect(0, 0, w_mm, h_mm, layer="TITLE")
    out.extend(dl)
    out.text(w_mm / 2, -8, title.upper(), h=TITLE_H, layer="TITLE", bold=True)
    if subtitle:
        out.text(w_mm / 2, -14.5, subtitle, h=2.6, layer="TEXT-SUB")
    return out


def _stage_plan(plan_dict: dict, stage: str) -> Plan:
    """A Plan set up for one stage's sheet: which layers it carries and how its
    title block reads."""
    p = Plan.from_dict(plan_dict)
    autofix.apply(p)
    validate.fill_levels(p)
    p.elec_summary = plan_dict.get("elec_summary")
    p.plumb_calc = plan_dict.get("plumb_calc")
    name = (p.title.plan_name or "FLOOR PLAN").upper()
    if stage == "plan":
        p.furniture = []
        p.elec = []
    elif stage == "furniture":
        p.elec = []
        if "FURNITURE" not in name:
            p.title.plan_name = (name.replace("FLOOR PLAN", "").strip()
                                 + " FURNITURE LAYOUT").strip()
    elif stage == "electrical":
        # electrical hangs off the furniture but is drawn without it, exactly
        # as the on-screen electrical view hides furniture
        p.furniture = []
        p.plumb, p.pipes = [], []
        if "ELECTRICAL" not in name:
            p.title.plan_name = (name.replace("FLOOR PLAN", "").strip()
                                 + " ELECTRICAL LAYOUT").strip()
    elif stage == "plumbing":
        # the plumbing sheet keeps ONLY the sanitary and kitchen fixtures —
        # the rest of the furniture and all the lighting come off
        from . import plumbing as PL
        p.furniture = [f for f in p.furniture if PL.is_plumb_fixture(f.kind)]
        p.elec = []
        if "PLUMBING" not in name:
            p.title.plan_name = (name.replace("FLOOR PLAN", "").strip()
                                 + " PLUMBING LAYOUT").strip()
    elif stage == "flooring":
        # the flooring sheet is the bare shell + the tile grid; furniture,
        # plumbing and electrical all come off
        p.furniture, p.elec, p.plumb, p.pipes = [], [], [], []
        if "FLOORING" not in name:
            p.title.plan_name = (name.replace("FLOOR PLAN", "").strip()
                                 + " FLOORING LAYOUT").strip()
    return p


def build_structural(plan_dict: dict, sheet_size: str = "A3",
                     orientation: str = "auto"):
    """ONLY the structural set, laid out in a row for the Beam-Layout preview:
    beam layout · plinth-beam framing · roof/floor framing · typical foundation
    section · building section(s). Returns (drawlist, w, h, info)."""
    from . import beamlayout as BL, framingplan as FP, founddetail as FD
    from . import section as SEC, bbs as BBS
    src = Plan.from_dict(plan_dict)
    if not getattr(src, "beams", None):
        from . import beams as BM
        src.beams = BM.auto_beams(_stage_plan(plan_dict, "plan"))

    out = DrawList()
    info0 = None
    dx = 0.0

    def _add(dl, cap, sub):
        nonlocal dx, info0
        p = _stage_plan(plan_dict, "plan")
        composed, info = sheet.compose(p, dl, sheet_size, orientation,
                                       schedule="")
        info0 = info0 or info
        w, h = info["w_mm"], info["h_mm"]
        out.extend(_titled(composed, w, h, cap, sub).translated(dx, 0))
        dx += w + GAP_MM

    # beam layout
    pb = _stage_plan(plan_dict, "plan")
    pb.beams = src.beams
    pb.title.plan_name = "BEAM LAYOUT"
    _add(BL.build_sheet(pb), "Beam layout",
         "RCC beams over the walls, numbered")
    # column schedule (only if the plan carries columns)
    if getattr(src, "columns", None):
        from . import columnsched as CS
        pc = _stage_plan(plan_dict, "plan")
        pc.title.plan_name = "COLUMN SCHEDULE"
        _add(CS.build(pc, src.struct), "Column schedule",
             "size, mix, reinforcement, ring spacing per column")
    # plinth + roof framing
    for kind, cap in (("plinth", "Plinth beam framing plan"),
                      ("roof", "Roof / floor beam & slab framing")):
        p = _stage_plan(plan_dict, "plan")
        p.beams = src.beams
        p.title.plan_name = (cap.upper())
        _add(FP.build(p, kind, src.struct), cap,
             "grid dims all sides, rebar section, notes")
    # beam details — each beam as a longitudinal rebar elevation
    from . import beamdetail as BD
    pbd = _stage_plan(plan_dict, "plan")
    pbd.beams = src.beams
    pbd.title.plan_name = "BEAM DETAILS"
    _add(BD.build(pbd, src.struct), "Beam details",
         "each beam: top/bottom bars, stirrup zones, span")
    # bar bending schedule
    pbbs = _stage_plan(plan_dict, "plan")
    pbbs.beams = src.beams
    pbbs.title.plan_name = "BAR BENDING SCHEDULE"
    _add(BBS.build(pbbs, src.struct), "Bar bending schedule",
         "per-beam bars, cutting lengths, steel weight")
    # typical foundation section (structural detail — kept). The building
    # SECTION elevation is a separate part and is NOT shown here.
    pf = _stage_plan(plan_dict, "plan")
    pf.title.plan_name = "TYPICAL FOUNDATION SECTION"
    _add(FD.build(pf, dict(src.section_params or {})),
         "Typical foundation section", "material hatches + dimensions")
    # column + footing layout plans (only if the plan carries columns)
    if getattr(src, "columns", None):
        from . import columnlayout as CL, footinglayout as FL
        from . import footingdetail as FTD
        _add(CL.build(_stage_plan(plan_dict, "plan"), src.struct),
             "Column layout plan", "columns tagged + grid dims")
        _add(FL.build(_stage_plan(plan_dict, "plan"), src.struct),
             "Footing layout plan", "footings tagged + grid dims")
        _add(FTD.build(_stage_plan(plan_dict, "plan"), src.struct),
             "Footing details", "pad plan + section, mesh, PCC, hard rock")
    # typical section details
    from . import structdetails as SD
    _add(SD.slab_section(_stage_plan(plan_dict, "plan"), src.struct),
         "Typical slab section", "top / bottom bars, depth")
    _add(SD.staircase(_stage_plan(plan_dict, "plan"), src.struct),
         "Typical staircase section", "waist slab, main & dist. bars")
    _add(SD.terrace(_stage_plan(plan_dict, "plan"), src.struct),
         "Typical terrace section", "slab, waterproofing, parapet")

    total_w = dx - GAP_MM
    total_h = info0["h_mm"] if info0 else 100.0
    return out, total_w, total_h, {**(info0 or {}), "structural": True}


def build(plan_dict: dict, sheet_size: str = "A3",
          orientation: str = "auto") -> tuple[DrawList, float, float, dict]:
    """The floor / furniture / electrical sheets in a row, in that order.
    Returns (drawlist, w, h, info)."""
    from . import plumbsched, floorsched
    src = Plan.from_dict(plan_dict)
    # the ONE combined file must always carry the full structural set — so if
    # the beams were never generated (Beam Layout not run), make them here, the
    # same way the on-screen structural preview does. This is what puts beam
    # layout / framing / beam details / BBS / column & footing sheets into the
    # single combined DXF even when the user only drew the architecture.
    if not getattr(src, "beams", None) and src.walls:
        from . import beams as BM
        from dataclasses import asdict
        src.beams = BM.auto_beams(src)
        plan_dict = dict(plan_dict)
        plan_dict["beams"] = [asdict(b) for b in src.beams]
    has_furn = bool(src.furniture)
    has_elec = bool(src.elec)
    has_plumb = bool(src.plumb or src.pipes)
    has_floor = bool(src.flooring)
    has_beam = bool(getattr(src, "beams", None))

    SCHED = {"plan": "openings", "furniture": "furniture",
             "electrical": "electrical", "plumbing": "plumbing",
             "flooring": "flooring"}
    CAPTION = {"plan": ("Floor plan", ""),
               "furniture": ("Furniture layout",
                             "standard sizes, clearances and Vaastu"),
               "furniture_lineout": ("Furniture line-out",
                                     "every piece dimensioned from its walls, "
                                     "with a legend"),
               "electrical": ("Electrical layout",
                              "IS 3646 / IS 732, furniture hidden"),
               "plumbing": ("Plumbing & drainage layout",
                            "five separate systems; only the sanitary and "
                            "kitchen fixtures shown"),
               "plumbing_detail": ("Plumbing installation detail",
                                   "fixture set-out — mounting heights and "
                                   "inlet / outlet centre-lines"),
               "flooring": ("Flooring layout",
                            "tile grid, spacers, start point and skirting"),
               "beam": ("Beam layout",
                        "RCC beams over the walls, numbered, with a schedule"),
               "foundation": ("Typical foundation section",
                              "plinth beam, PCC, stone soling and RR-stone "
                              "footing with material hatches"),
               "plinth_framing": ("Plinth beam framing plan",
                                  "beams tagged + sized, grid dims, rebar "
                                  "section, notes"),
               "roof_framing": ("Roof / floor beam & slab framing",
                                "beams + slab panels (depth), slab "
                                "reinforcement, rebar section, notes"),
               "column_schedule": ("Column schedule",
                                   "size, mix, reinforcement, ring spacing"),
               "column_layout": ("Column layout plan",
                                 "columns tagged + grid dimensions"),
               "footing_layout": ("Footing layout plan",
                                  "footings tagged + grid dimensions"),
               "footing_detail": ("Footing details",
                                  "pad plan + section, mesh, PCC, hard rock"),
               "slab_section": ("Typical slab section",
                                "top / bottom bars, slab depth"),
               "staircase_detail": ("Typical staircase section",
                                    "waist slab, main & distribution bars"),
               "terrace_detail": ("Typical terrace section",
                                  "slab, waterproofing, parapet"),
               "beam_detail": ("Beam details",
                               "each beam: top/bottom bars, stirrup zones, span"),
               "bbs": ("Bar bending schedule",
                       "per-beam bars, cutting lengths and steel weight")}
    UNDER = {"furniture": (furnsched, "FURNITURE SCHEDULE — SHEET 2"),
             "electrical": (elecsched, "CIRCUIT SCHEDULE — SHEET 3"),
             "plumbing": (plumbsched, "PLUMBING SCHEDULES — SHEET 4"),
             "flooring": (floorsched, "FLOORING SCHEDULES — SHEET 5")}

    stages = ["plan"]
    if has_furn:
        stages.append("furniture")
        stages.append("furniture_lineout")
    if has_elec:
        stages.append("electrical")
    if has_plumb:
        stages.append("plumbing")
        stages.append("plumbing_detail")
    if has_floor:
        stages.append("flooring")
    if has_beam:
        stages.append("beam")
        if getattr(src, "columns", None):
            stages.append("column_schedule")
            stages.append("column_layout")
            stages.append("footing_layout")
            stages.append("footing_detail")
        stages.append("plinth_framing")
        stages.append("roof_framing")
        stages.append("beam_detail")      # per-beam rebar elevations
        stages.append("bbs")              # bar bending schedule for the beams
        stages.append("slab_section")     # typical slab section
        stages.append("staircase_detail")
        stages.append("terrace_detail")
    stages.append("foundation")            # typical foundation detail, always

    out = DrawList()
    info0 = None
    dx = 0.0
    y_min = 0.0
    for stage in stages:
        if stage == "furniture_lineout":
            from . import furnlineout
            p = _stage_plan(plan_dict, "furniture")
            dl, _rows = furnlineout.build(p)
            composed, info = sheet.compose(p, dl, sheet_size, orientation,
                                           schedule="")
        elif stage == "plumbing_detail":
            from . import plumbdetail
            p = _stage_plan(plan_dict, "plumbing")
            p.title.plan_name = "PLUMBING INSTALLATION DETAIL"
            dl = plumbdetail.build(p)
            composed, info = sheet.compose(p, dl, sheet_size, orientation,
                                           schedule="")
        elif stage == "beam":
            from . import beamlayout as BL
            p = _stage_plan(plan_dict, "plan")
            p.beams = src.beams
            p.title.plan_name = "BEAM LAYOUT"
            dl = BL.build_sheet(p)
            composed, info = sheet.compose(p, dl, sheet_size, orientation,
                                           schedule="")
        elif stage == "foundation":
            from . import founddetail as FD
            p = _stage_plan(plan_dict, "plan")
            p.title.plan_name = "TYPICAL FOUNDATION SECTION"
            dl = FD.build(p, dict(src.section_params or {}))
            composed, info = sheet.compose(p, dl, sheet_size, orientation,
                                           schedule="")
        elif stage in ("plinth_framing", "roof_framing"):
            from . import framingplan as FP
            kind = "plinth" if stage == "plinth_framing" else "roof"
            p = _stage_plan(plan_dict, "plan")
            p.beams = src.beams
            p.title.plan_name = ("PLINTH BEAM FRAMING PLAN"
                                 if kind == "plinth"
                                 else "ROOF / FLOOR BEAM & SLAB FRAMING")
            dl = FP.build(p, kind, src.struct)
            composed, info = sheet.compose(p, dl, sheet_size, orientation,
                                           schedule="")
        elif stage == "column_schedule":
            from . import columnsched as CS
            p = _stage_plan(plan_dict, "plan")
            p.title.plan_name = "COLUMN SCHEDULE"
            dl = CS.build(p, src.struct)
            composed, info = sheet.compose(p, dl, sheet_size, orientation,
                                           schedule="")
        elif stage in ("column_layout", "footing_layout", "footing_detail",
                       "slab_section", "staircase_detail", "terrace_detail"):
            p = _stage_plan(plan_dict, "plan")
            if stage == "column_layout":
                from . import columnlayout as M
                p.title.plan_name = "COLUMN LAYOUT PLAN"
                dl = M.build(p, src.struct)
            elif stage == "footing_layout":
                from . import footinglayout as M
                p.title.plan_name = "FOOTING LAYOUT PLAN"
                dl = M.build(p, src.struct)
            elif stage == "footing_detail":
                from . import footingdetail as M
                p.title.plan_name = "FOOTING DETAILS"
                dl = M.build(p, src.struct)
            else:
                from . import structdetails as SD
                fn = {"slab_section": SD.slab_section,
                      "staircase_detail": SD.staircase,
                      "terrace_detail": SD.terrace}[stage]
                p.title.plan_name = {"slab_section": "TYPICAL SLAB SECTION",
                                     "staircase_detail": "STAIRCASE SECTION",
                                     "terrace_detail": "TERRACE SECTION"}[stage]
                dl = fn(p, src.struct)
            composed, info = sheet.compose(p, dl, sheet_size, orientation,
                                           schedule="")
        elif stage == "beam_detail":
            from . import beamdetail as BD
            p = _stage_plan(plan_dict, "plan")
            p.beams = src.beams
            p.title.plan_name = "BEAM DETAILS"
            dl = BD.build(p, src.struct)
            composed, info = sheet.compose(p, dl, sheet_size, orientation,
                                           schedule="")
        elif stage == "bbs":
            from . import bbs as BBS
            p = _stage_plan(plan_dict, "plan")
            p.beams = src.beams
            p.title.plan_name = "BAR BENDING SCHEDULE"
            dl = BBS.build(p, src.struct)
            composed, info = sheet.compose(p, dl, sheet_size, orientation,
                                           schedule="")
        else:
            p = _stage_plan(plan_dict, stage)
            # the floor plan carries the WALL SCHEDULE, so it must also show the
            # wall NUMBERS — otherwise the schedule cannot be tied to a wall.
            dl = engine.build(p, wall_tags=(stage == "plan"),
                              furniture=(stage in ("furniture", "plumbing")),
                              elec=(stage == "electrical"),
                              plumb=(stage == "plumbing"),
                              floor=(stage == "flooring"),
                              sections=(stage == "plan"))   # line on floor plan only
            composed, info = sheet.compose(p, dl, sheet_size, orientation,
                                           schedule=SCHED[stage])
        info0 = info0 or info
        w, h = info["w_mm"], info["h_mm"]
        cap, sub = CAPTION[stage]
        if stage == "plan":
            sub = f"scale {info['scale']}  ·  sheet {info['sheet']}"
        out.extend(_titled(composed, w, h, cap, sub).translated(dx, 0))

        # this sheet's own table, under it
        if stage in UNDER:
            mod, label = UNDER[stage]
            # the schedule gets the height it ASKS for. Clamping it to the
            # drawing's height (min(h, …)) is what pushed the last rows
            # outside the border and printed the caption over them.
            sh = max(h * 0.5, mod.height_for(p))
            top = -(GAP_MM + 20)
            out.extend(mod.build(p, w, sh).translated(dx, top - sh))
            out.text(dx + w / 2, top - sh - 8, label, h=TITLE_H,
                     layer="TITLE", bold=True)
            y_min = min(y_min, top - sh - 14)

        dx += w + GAP_MM

    # section sheets — one per section line, using the stored questionnaire
    if getattr(src, "sections", None) and getattr(src, "section_params", None):
        from . import section as SEC
        for s in src.sections:
            sdl, _n = SEC.build(src, (s.x1, s.y1), (s.x2, s.y2),
                                dict(src.section_params, tag=s.tag,
                                     view_flip=getattr(s, "flip", False)))
            if not sdl.items:
                continue
            composed, info = sheet.compose(src, sdl, sheet_size, "landscape",
                                           schedule="")
            w, h = info["w_mm"], info["h_mm"]
            out.extend(_titled(composed, w, h, f"Section {s.tag}-{s.tag}",
                               "levels from the section questionnaire")
                       .translated(dx, 0))
            dx += w + GAP_MM

    # elevations sheet — the four outer faces developed with dimensions
    from . import elevation as EL
    edl = EL.build_all(src, dict(src.section_params or {}))
    if edl.items:
        composed, info = sheet.compose(src, edl, sheet_size, "landscape",
                                       schedule="")
        w, h = info["w_mm"], info["h_mm"]
        out.extend(_titled(composed, w, h, "Elevations",
                           "front / rear / left / right, fully dimensioned")
                   .translated(dx, 0))
        dx += w + GAP_MM

    total_w = dx - GAP_MM
    total_h = info0["h_mm"]
    return out, total_w, total_h - y_min, {**info0, "y_min": y_min,
                                           "furniture": has_furn,
                                           "electrical": has_elec,
                                           "sheets": len(stages)}


def build_project(floors: list, sheet_size: str = "A3",
                  orientation: str = "auto") -> tuple[DrawList, float, float, dict]:
    """The WHOLE multi-floor project in ONE drawing: every floor's full set of
    sheets (plan · furniture · electrical · plumbing · flooring · beam ·
    framing · foundation · section · elevation) stacked as its own band, one
    band per floor, wall numbers running continuously across the floors; then
    the combined MULTI-FLOOR section and MULTI-FLOOR elevation at the bottom.
    Returns (drawlist, w, h, info)."""
    from . import pipeline, section as SEC, elevation as EL

    # keep only floors that actually carry a plan, number their walls across
    prepared = []
    start = 1
    for fl in (floors or []):
        pd = fl.get("plan")
        if not pd or not (pd.get("walls") and pd.get("rooms")):
            continue
        name = fl.get("name") or f"Floor {len(prepared) + 1}"
        numbered, _n = pipeline.number_walls(pd, split=True, start=start)
        start += len(numbered.get("walls") or [])
        t = dict(numbered.get("title") or {})
        t["plan_name"] = name.upper() + " PLAN"
        numbered["title"] = t
        prepared.append((name, numbered))

    out = DrawList()
    if not prepared:
        return out, 100.0, 100.0, {"k": 1.0, "y_min": 0.0}

    BAND_GAP = 90.0                # vertical gap between one floor and the next
    info0 = None
    y_top = 0.0                    # top edge of the current band (drops down)
    max_w = 0.0

    def _place(dl, w, h, banner):
        """Drop one sheet-row as a band under the previous one, with a big
        left-hand banner naming it."""
        nonlocal y_top, max_w, info0
        b = dl.bounds()                        # actual extent of the row
        row_h = b[3] - b[1]
        # shift the row so its TOP sits at y_top
        shift_y = y_top - b[3]
        out.extend(dl.translated(0, shift_y))
        yc = shift_y + b[1] + row_h / 2
        out.text(b[0] - 55, yc, banner, h=16, layer="TITLE", bold=True,
                 angle=90)
        out.line(b[0] - 30, shift_y + b[3], b[0] - 30, shift_y + b[1],
                 layer="TITLE")
        max_w = max(max_w, b[2])
        y_top = shift_y + b[1] - BAND_GAP

    for name, pd in prepared:
        dl, w, h, info = build(pd, sheet_size, orientation)
        info0 = info0 or info
        _place(dl, w, h, name.upper())

    # ---- combined MULTI-FLOOR section + elevation bands -------------------
    models = [Plan.from_dict(pd) for _n, pd in prepared]
    if len(models) >= 2:
        gpd = prepared[0][1]
        params = dict(gpd.get("section_params") or {})
        # multi-floor section — one band per section line on the ground plan
        for s in (gpd.get("sections") or []):
            sdl, _n = SEC.build_project(
                models, (s.get("x1", 0), s.get("y1", 0)),
                (s.get("x2", 0), s.get("y2", 0)),
                dict(params, tag=s.get("tag", "A"),
                     view_flip=s.get("flip", False)))
            if not sdl.items:
                continue
            comp, info = sheet.compose(models[0], sdl, sheet_size, "landscape",
                                       schedule="")
            info0 = info0 or info
            tag = s.get("tag", "A")
            _place(_titled(comp, info["w_mm"], info["h_mm"],
                           f"Multi-floor section {tag}-{tag}",
                           "every storey stacked, one dimension stack"),
                   info["w_mm"], info["h_mm"], f"SECTION {tag}-{tag}")
        # multi-floor elevations — every storey's own openings
        eld = EL.build_project(models, params)
        if eld.items:
            comp, info = sheet.compose(models[0], eld, sheet_size, "landscape",
                                       schedule="")
            info0 = info0 or info
            _place(_titled(comp, info["w_mm"], info["h_mm"],
                           "Multi-floor elevations",
                           "four faces, each storey's own openings"),
                   info["w_mm"], info["h_mm"], "ELEVATIONS")

    total_w = max_w + 60.0
    total_h = -y_top                            # y_top is the bottom edge now
    info = {**(info0 or {"k": 1.0}), "y_min": y_top, "floors": len(prepared)}
    return out, total_w, total_h, info


def build_screen_project(floors: list, sheet_size: str = "A3",
                         orientation: str = "auto", wall_tags: bool = False,
                         layer_state: dict | None = None
                         ) -> tuple[DrawList, float, float, dict]:
    """The ON-SCREEN multi-floor view: every floor's CURRENT drawing (whatever
    stages it carries — plan / furniture / electrical / plumbing / flooring)
    laid out side by side, each in its own titled frame, so the whole project
    reads on one canvas. Returns (drawlist, w, h, info)."""
    from . import engine, layers as LY, pipeline

    out = DrawList()
    dx = 0.0
    info0 = None
    n = 0
    for fl in (floors or []):
        pd = fl.get("plan")
        if not pd or not (pd.get("walls") and pd.get("rooms")):
            continue
        name = fl.get("name") or f"Floor {n + 1}"
        p, _notes, _issues = pipeline._prepare(pd, True)
        dl = engine.build(p, wall_tags=wall_tags, furniture=True,
                          sections=True)
        composed, info = sheet.compose(p, dl, sheet_size, orientation,
                                       schedule=pipeline._sheet_kind(p, layer_state))
        composed = LY.apply(composed, layer_state)
        info0 = info0 or info
        w, h = info["w_mm"], info["h_mm"]
        out.extend(_titled(composed, w, h, name, "").translated(dx, 0))
        dx += w + GAP_MM
        n += 1
    if not n:
        return out, 100.0, 100.0, {"k": 1.0, "w_mm": 100.0, "h_mm": 100.0}
    total_w = dx - GAP_MM
    return out, total_w, info0["h_mm"], {**info0, "w_mm": total_w,
                                         "h_mm": info0["h_mm"], "floors": n}


def export_project_folder(floors: list, outroot: str, name: str,
                          sheet_size: str = "A3", orientation: str = "auto",
                          dpi: int = 220) -> dict:
    """The whole multi-floor project as ONE combined file set (DXF + PDF), no
    per-floor sub-folders and no separate stage files — everything a single
    drawing with every floor's sheets in it."""
    folder = os.path.join(outroot, name)
    os.makedirs(folder, exist_ok=True)
    dl, w, h, info = build_project(floors, sheet_size, orientation)
    shifted = dl.translated(0, -info["y_min"])          # lift above y = 0
    stem = os.path.join(folder, name + "_ALL-FLOORS")
    paths = {"folder": folder}
    paths["combined_dxf"] = export.to_dxf(shifted, stem + ".dxf",
                                          model_scale=info.get("k"))
    paths["combined_pdf"] = export.to_pdf(shifted, w, h, stem + ".pdf")
    return {"paths": paths, "folder": folder, "floors": info.get("floors", 0)}


def export_folder(plan_dict: dict, outroot: str, name: str,
                  sheet_size: str = "A3", orientation: str = "auto",
                  dpi: int = 220, light: bool = False) -> dict:
    """One job → ONE combined drawing: EVERY sheet (architecture + full
    structural set) in a single file. No individual per-sheet files are written
    any more — the `<name>_COMBINED.*` IS the whole deliverable.

    light=True (used by the web build) skips the PNG (a slow matplotlib raster
    that nobody downloads) and the SVG file, keeping only the DXF + PDF — that
    is the bulk of the export time, so the web export feels far snappier."""
    from . import pipeline, validate

    folder = os.path.join(outroot, name)
    os.makedirs(folder, exist_ok=True)
    paths: dict[str, str] = {"folder": folder}

    # validation summary for the caller (no per-sheet files written)
    _plan, notes, issues = pipeline._prepare(plan_dict, True)

    # the combined drawing: every stage stacked in ONE file
    dl, w, h, info = build(plan_dict, sheet_size, orientation)
    shifted = dl.translated(0, -info["y_min"])
    stem = os.path.join(folder, name + "_COMBINED")
    # DXF first — it is fast (~0.3 s) and is what the CAD user actually wants
    paths["combined_dxf"] = export.to_dxf(shifted, stem + ".dxf",
                                          model_scale=info["k"])
    paths["combined_pdf"] = export.to_pdf(shifted, w, h, stem + ".pdf")
    if not light:
        with open(stem + ".svg", "w", encoding="utf-8") as fh:
            fh.write(export.to_svg(shifted, w, h))
        paths["combined_svg"] = stem + ".svg"
        paths["combined_png"] = export.to_png(shifted, w, h, stem + ".png", dpi)
    return {"paths": paths, "info": info, "issues": issues, "fixes": notes,
            "summary": validate.summary(issues), "folder": folder}

    # ---- legacy per-sheet exports below are intentionally unreachable -------
    plan = Plan.from_dict(plan_dict)
    has_furn = bool(plan.furniture)
    has_elec = bool(plan.elec)
    has_plumb = bool(plan.plumb or plan.pipes)
    has_floor = bool(plan.flooring)

    base = pipeline.export_all(plan_dict, folder, name + "_floor_plan",
                               sheet_size, orientation, dpi,
                               wall_tags=True, furniture=False)
    paths.update({f"floor_{k}": v for k, v in base["paths"].items()})

    if has_furn:
        fd = dict(plan_dict)
        t = dict(fd.get("title") or {})
        pname = (t.get("plan_name") or "FLOOR PLAN").upper()
        if "FURNITURE" not in pname:
            t["plan_name"] = (pname.replace("FLOOR PLAN", "").strip()
                              + " FURNITURE LAYOUT").strip()
        fd["title"] = t
        furn = pipeline.export_all(fd, folder, name + "_furniture",
                                   sheet_size, orientation, dpi,
                                   furniture=True, sections=False)
        paths.update({f"furniture_{k}": v for k, v in furn["paths"].items()})

    if has_elec:
        from . import layers
        ed = dict(plan_dict)
        t = dict(ed.get("title") or {})
        pname = (t.get("plan_name") or "FLOOR PLAN").upper()
        if "ELECTRICAL" not in pname:
            t["plan_name"] = (pname.replace("FLOOR PLAN", "").strip()
                              + " ELECTRICAL LAYOUT").strip()
        ed["title"] = t
        elec = pipeline.export_all(ed, folder, name + "_electrical",
                                   sheet_size, orientation, dpi,
                                   furniture=False,
                                   layer_state=layers.for_view("electrical"))
        paths.update({f"electrical_{k}": v for k, v in elec["paths"].items()})

    if has_plumb:
        from . import layers as _L
        pd = dict(plan_dict)
        t = dict(pd.get("title") or {})
        pname = (t.get("plan_name") or "FLOOR PLAN").upper()
        if "PLUMBING" not in pname:
            t["plan_name"] = (pname.replace("FLOOR PLAN", "").strip()
                              + " PLUMBING LAYOUT").strip()
        pd["title"] = t
        plb = pipeline.export_all(pd, folder, name + "_plumbing",
                                  sheet_size, orientation, dpi,
                                  layer_state=_L.for_view("plumbing"))
        paths.update({f"plumbing_{k}": v for k, v in plb["paths"].items()})

        # the plumbing INSTALLATION DETAIL sheet (heights / inlet-outlet set-out)
        from . import plumbdetail
        pdp = Plan.from_dict(pd)
        pdp.title.plan_name = "PLUMBING INSTALLATION DETAIL"
        ddl = plumbdetail.build(pdp)
        dcomposed, dinfo = sheet.compose(pdp, ddl, sheet_size, orientation,
                                         schedule="")
        stemd = os.path.join(folder, name + "_plumbing_detail")
        with open(stemd + ".svg", "w", encoding="utf-8") as fh:
            fh.write(export.to_svg(dcomposed, dinfo["w_mm"], dinfo["h_mm"]))
        paths["plumbing_detail_svg"] = stemd + ".svg"
        paths["plumbing_detail_png"] = export.to_png(
            dcomposed, dinfo["w_mm"], dinfo["h_mm"], stemd + ".png", dpi)
        paths["plumbing_detail_pdf"] = export.to_pdf(
            dcomposed, dinfo["w_mm"], dinfo["h_mm"], stemd + ".pdf")
        paths["plumbing_detail_dxf"] = export.to_dxf(
            dcomposed, stemd + ".dxf", model_scale=dinfo.get("k"))

    if has_floor:
        from . import layers as _L2
        fld = pipeline.export_all(plan_dict, folder, name + "_flooring",
                                  sheet_size, orientation, dpi,
                                  layer_state=_L2.for_view("flooring"))
        paths.update({f"flooring_{k}": v for k, v in fld["paths"].items()})

    if getattr(plan, "beams", None):
        from . import beamlayout as BL
        bp = Plan.from_dict(plan_dict)
        bp.title.plan_name = "BEAM LAYOUT"
        bdl = BL.build_sheet(bp)
        bcomposed, binfo = sheet.compose(bp, bdl, sheet_size, orientation,
                                         schedule="")
        stemb = os.path.join(folder, name + "_beam_layout")
        with open(stemb + ".svg", "w", encoding="utf-8") as fh:
            fh.write(export.to_svg(bcomposed, binfo["w_mm"], binfo["h_mm"]))
        paths["beam_svg"] = stemb + ".svg"
        paths["beam_png"] = export.to_png(bcomposed, binfo["w_mm"],
                                          binfo["h_mm"], stemb + ".png", dpi)
        paths["beam_pdf"] = export.to_pdf(bcomposed, binfo["w_mm"],
                                          binfo["h_mm"], stemb + ".pdf")
        paths["beam_dxf"] = export.to_dxf(bcomposed, stemb + ".dxf",
                                          model_scale=binfo.get("k"))

        # plinth-beam and roof beam-&-slab framing plans
        from . import framingplan as FP
        for kind, tag in (("plinth", "plinth_framing"),
                          ("roof", "roof_framing")):
            fp = Plan.from_dict(plan_dict)
            fp.title.plan_name = ("PLINTH BEAM FRAMING PLAN" if kind == "plinth"
                                  else "ROOF / FLOOR BEAM & SLAB FRAMING")
            fdl = FP.build(fp, kind, fp.struct)
            fc, fi = sheet.compose(fp, fdl, sheet_size, orientation, schedule="")
            st = os.path.join(folder, name + "_" + tag)
            with open(st + ".svg", "w", encoding="utf-8") as fh:
                fh.write(export.to_svg(fc, fi["w_mm"], fi["h_mm"]))
            paths[tag + "_svg"] = st + ".svg"
            paths[tag + "_png"] = export.to_png(fc, fi["w_mm"], fi["h_mm"],
                                                st + ".png", dpi)
            paths[tag + "_pdf"] = export.to_pdf(fc, fi["w_mm"], fi["h_mm"],
                                                st + ".pdf")
            paths[tag + "_dxf"] = export.to_dxf(fc, st + ".dxf",
                                                model_scale=fi.get("k"))

        # beam details — per-beam rebar elevations
        from . import beamdetail as BD
        bdp = Plan.from_dict(plan_dict)
        bdp.title.plan_name = "BEAM DETAILS"
        bddl = BD.build(bdp, bdp.struct)
        bdc, bdi = sheet.compose(bdp, bddl, sheet_size, orientation, schedule="")
        stbd = os.path.join(folder, name + "_beam_details")
        with open(stbd + ".svg", "w", encoding="utf-8") as fh:
            fh.write(export.to_svg(bdc, bdi["w_mm"], bdi["h_mm"]))
        paths["beam_details_svg"] = stbd + ".svg"
        paths["beam_details_png"] = export.to_png(bdc, bdi["w_mm"], bdi["h_mm"],
                                                  stbd + ".png", dpi)
        paths["beam_details_pdf"] = export.to_pdf(bdc, bdi["w_mm"], bdi["h_mm"],
                                                  stbd + ".pdf")
        paths["beam_details_dxf"] = export.to_dxf(bdc, stbd + ".dxf",
                                                  model_scale=bdi.get("k"))

        # bar bending schedule for the beams
        from . import bbs as BBS
        bbp = Plan.from_dict(plan_dict)
        bbp.title.plan_name = "BAR BENDING SCHEDULE"
        bbdl = BBS.build(bbp, bbp.struct)
        bbc, bbi = sheet.compose(bbp, bbdl, sheet_size, orientation, schedule="")
        stbb = os.path.join(folder, name + "_bar_bending_schedule")
        with open(stbb + ".svg", "w", encoding="utf-8") as fh:
            fh.write(export.to_svg(bbc, bbi["w_mm"], bbi["h_mm"]))
        paths["bbs_svg"] = stbb + ".svg"
        paths["bbs_png"] = export.to_png(bbc, bbi["w_mm"], bbi["h_mm"],
                                         stbb + ".png", dpi)
        paths["bbs_pdf"] = export.to_pdf(bbc, bbi["w_mm"], bbi["h_mm"],
                                         stbb + ".pdf")
        paths["bbs_dxf"] = export.to_dxf(bbc, stbb + ".dxf",
                                         model_scale=bbi.get("k"))

    # typical foundation section detail
    from . import founddetail as FD
    fdp = Plan.from_dict(plan_dict)
    fdp.title.plan_name = "TYPICAL FOUNDATION SECTION"
    fdl = FD.build(fdp, dict(getattr(fdp, "section_params", None) or {}))
    fcomposed, finfo = sheet.compose(fdp, fdl, sheet_size, orientation,
                                     schedule="")
    stemf = os.path.join(folder, name + "_foundation_section")
    with open(stemf + ".svg", "w", encoding="utf-8") as fh:
        fh.write(export.to_svg(fcomposed, finfo["w_mm"], finfo["h_mm"]))
    paths["foundation_svg"] = stemf + ".svg"
    paths["foundation_png"] = export.to_png(fcomposed, finfo["w_mm"],
                                            finfo["h_mm"], stemf + ".png", dpi)
    paths["foundation_pdf"] = export.to_pdf(fcomposed, finfo["w_mm"],
                                            finfo["h_mm"], stemf + ".pdf")
    paths["foundation_dxf"] = export.to_dxf(fcomposed, stemf + ".dxf",
                                            model_scale=finfo.get("k"))

    # the four outer ELEVATIONS
    from . import elevation as EL
    ep = Plan.from_dict(plan_dict)
    ep.title.plan_name = "ELEVATIONS"
    edl = EL.build_all(ep, dict(getattr(ep, "section_params", None) or {}))
    if edl.items:
        ec, ei = sheet.compose(ep, edl, sheet_size, orientation, schedule="")
        steme = os.path.join(folder, name + "_elevations")
        with open(steme + ".svg", "w", encoding="utf-8") as fh:
            fh.write(export.to_svg(ec, ei["w_mm"], ei["h_mm"]))
        paths["elevations_svg"] = steme + ".svg"
        paths["elevations_png"] = export.to_png(ec, ei["w_mm"], ei["h_mm"],
                                                steme + ".png", dpi)
        paths["elevations_pdf"] = export.to_pdf(ec, ei["w_mm"], ei["h_mm"],
                                                steme + ".pdf")
        paths["elevations_dxf"] = export.to_dxf(ec, steme + ".dxf",
                                                model_scale=ei.get("k"))

    # the combined drawing: every stage in ONE file, in order
    dl, w, h, info = build(plan_dict, sheet_size, orientation)
    shifted = dl.translated(0, -info["y_min"])          # lift above y = 0
    stem = os.path.join(folder, name + "_COMBINED")

    with open(stem + ".svg", "w", encoding="utf-8") as fh:
        fh.write(export.to_svg(shifted, w, h))
    paths["combined_svg"] = stem + ".svg"
    paths["combined_png"] = export.to_png(shifted, w, h, stem + ".png", dpi)
    paths["combined_pdf"] = export.to_pdf(shifted, w, h, stem + ".pdf")
    paths["combined_dxf"] = export.to_dxf(shifted, stem + ".dxf",
                                          model_scale=info["k"])

    return {"paths": paths, "info": info,
            "issues": base["issues"], "fixes": base["fixes"],
            "summary": base["summary"], "folder": folder}
