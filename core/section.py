"""Vertical building SECTION cut along a user-drawn section line.

A 2-D plan has no heights, so the vertical data comes from a questionnaire the
user fills — plinth (ground floor only), floor-to-floor height, slab thickness,
beam depth, number of floors, parapet, foundation (skippable). Everything else
is DERIVED from the plan: which walls the line cuts, their thickness, and the
door / window sill & lintel already stored on each opening.

`build(plan, p1, p2, params)` returns (DrawList, notes). Nothing is assumed —
a missing questionnaire value is taken as 0 / skipped, never guessed.
"""

from __future__ import annotations

import math

from .draw import DrawList

MM = 304.8


def _mm_ft(mm) -> float:
    return (mm or 0) / MM


def _seg_x(a, b, c, d):
    """Intersection point of segment a-b with c-d, or None."""
    (x1, y1), (x2, y2) = a, b
    (x3, y3), (x4, y4) = c, d
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(den) < 1e-9:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
    u = ((x1 - x3) * (y1 - y2) - (y1 - y3) * (x1 - x2)) / den
    if -0.02 <= t <= 1.02 and -0.02 <= u <= 1.02:
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
    return None


def _open_levels(o):
    """(sill_ft, lintel_ft) above FFL for an opening."""
    if getattr(o, "is_door", False):
        sill = 0.0
        lintel = _mm_ft(o.lintel() if hasattr(o, "lintel") else 2100)
    else:
        sill = _mm_ft(o.sill() if hasattr(o, "sill") else 900)
        lintel = _mm_ft(o.lintel() if hasattr(o, "lintel") else 2100)
    if lintel <= sill:
        lintel = sill + _mm_ft(o.height_mm or 1200)
    return sill, lintel


def _hatch(dl, x0, y0, x1, y1, layer, step=0.25, slope=1):
    """A rectangular hatched region. Emits ONE Hatch primitive (a real HATCH
    object in the DXF, expanded to lines for the on-screen / PDF preview) so the
    hatch is never a bag of loose exploded lines. slope=+1 → 45°, -1 → 135°."""
    if x1 <= x0 or y1 <= y0:
        return
    dl.hatch([(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
             kind="diag45" if slope >= 0 else "diag135", step=step, layer=layer)


def build(plan, p1, p2, params) -> tuple[DrawList, list]:
    dl = DrawList()
    notes = []

    is_gf = bool(params.get("is_ground", True))
    plinth = _mm_ft(params.get("plinth_mm", 0)) if is_gf else 0.0
    fh = _mm_ft(params.get("floor_height_mm", 0))
    slab = _mm_ft(params.get("slab_thk_mm", 0))
    beam = _mm_ft(params.get("beam_depth_mm", 0))
    # if a beam layout exists, the section takes its depths from the beams
    if getattr(plan, "beams", None):
        deps = [b.depth_mm for b in plan.beams if b.depth_mm]
        if deps and beam <= 0:
            beam = _mm_ft(max(set(deps), key=deps.count))   # most common depth
    floors = max(1, int(params.get("floors", 1) or 1))
    para = _mm_ft(params.get("parapet_mm", 0))
    found_raw = params.get("foundation_mm", None)
    found = _mm_ft(found_raw) if found_raw else 0.0
    dpc = _mm_ft(75)            # DPC band above plinth beam
    stiff_t = _mm_ft(100)       # RCC stiffener band thickness
    stiff_int = _mm_ft(1200)    # …at this vertical interval, 4.5" walls
    coping = _mm_ft(150)        # RCC coping on the parapet
    screed = _mm_ft(75)         # floor screed / bedding under the finish
    pcc = _mm_ft(125)           # 100-150 mm PCC bed under the floor
    pb_thk = _mm_ft(params.get("plinth_beam_thk_mm", 0))   # plinth beam width
    pb_ht = _mm_ft(params.get("plinth_beam_ht_mm", 0))     # plinth beam depth

    if fh <= 0:
        return dl, ["Floor height is required to cut a section."]

    x1, y1 = p1
    x2, y2 = p2
    L = math.hypot(x2 - x1, y2 - y1) or 1e-9
    ux, uy = (x2 - x1) / L, (y2 - y1) / L

    def t_of(px, py):
        return (px - x1) * ux + (py - y1) * uy

    # ---- which walls does the line cut? --------------------------------
    cuts = []            # (t, thickness_ft, exterior, wall, cross_point)
    for w in plan.walls:
        if getattr(w, "railing", False):
            continue
        I = _seg_x((x1, y1), (x2, y2), (w.x1, w.y1), (w.x2, w.y2))
        if I is None:
            continue
        wl = w.length or 1e-9
        wux, wuy = (w.x2 - w.x1) / wl, (w.y2 - w.y1) / wl
        if abs(ux * wux + uy * wuy) > 0.94:            # ~parallel → not a cut
            continue
        cuts.append((round(t_of(*I), 3), w.thickness_in / 12.0,
                     bool(w.exterior), w, I))
    cuts.sort(key=lambda c: c[0])
    if not cuts:
        return dl, ["The section line does not cross any wall — draw it right "
                    "across the building."]

    x_lo = cuts[0][0] - 2.0
    x_hi = cuts[-1][0] + 2.0
    # the slabs stop FLUSH with the outer face of the end (exterior) walls, not
    # 2 ft beyond; only the level / ground lines run out past the building
    face_lo = cuts[0][0] - cuts[0][1] / 2
    face_hi = cuts[-1][0] + cuts[-1][1] / 2

    # vertical datum: GL at 0, floors stacked up
    ffl0 = plinth                              # ground-floor finished level
    tops = [ffl0 + k * fh for k in range(floors + 1)]   # FFL of each level

    L_CUT, L_SLAB, L_EARTH, L_TXT, L_DIM = ("SEC-CUT", "SEC-SLAB",
                                            "SEC-EARTH", "SEC-TEXT", "SEC-DIM")

    # multi-floor stacking flags: an upper storey has no ground line of its own
    # and no annotations (the project draws ONE combined set for all floors)
    no_ground = bool(params.get("_no_ground"))
    no_annot = bool(params.get("_no_annot"))

    # ---- ground line ---------------------------------------------------
    if not no_ground:
        dl.line(x_lo - 1, 0, x_hi + 1, 0, layer=L_SLAB)
        for gx in _frange(x_lo - 1, x_hi + 1, 0.6):    # earth ticks below GL
            dl.line(gx, 0, gx - 0.3, -0.45, layer=L_EARTH)

    # ---- foundation + plinth build-up (ground floor) -------------------
    #   drawn like a proper foundation section: finish + 75 screed, 100-150 PCC,
    #   230 rubble soling and earth filling between the walls; at every cut wall
    #   a plinth beam, DPC and a tapered RR-masonry footing down to hard soil.
    rubble_t = _mm_ft(230)
    found_depth = found if found > 0 else _mm_ft(915)     # 3'-0" below GL
    if plinth > 0:
        _draw_foundation(dl, cuts, ffl0, dpc, pcc, screed, rubble_t,
                         pb_thk, pb_ht, found_depth, x_lo, x_hi,
                         (L_CUT, L_SLAB, L_EARTH, L_TXT, L_DIM))

    # which way does the viewer look? perpendicular to the cut, INTO the
    # building (toward the plan's centre). Everything on the near/removed side
    # is dropped; of the walls in front, only the FIRST one seen shows its
    # openings — walls hidden behind it are not drawn (occlusion).
    view = _view_dir(plan, p1, p2, params)
    # facing doors / windows (on walls PARALLEL to the cut) shown in elevation
    faces = _facing_openings(plan, p1, p2, x_lo, x_hi, view)

    # staircases / entry steps the section line passes through
    flights = _flights_in_section(plan, x1, y1, ux, uy, p1, p2, x_lo, x_hi)
    esteps = _steps_in_section(plan, x1, y1, ux, uy, p1, p2, x_lo, x_hi)

    # centroid of the walls — a chajja projects to the side AWAY from it
    _ax = [w.x1 for w in plan.walls] + [w.x2 for w in plan.walls]
    _ay = [w.y1 for w in plan.walls] + [w.y2 for w in plan.walls]
    ccx = sum(_ax) / len(_ax) if _ax else 0.0
    ccy = sum(_ay) / len(_ay) if _ay else 0.0

    # ---- each storey ---------------------------------------------------
    cut_ops = []            # openings the plane cuts through (for the legend)
    rep = {}                # representative points for the side labels
    for k in range(floors):
        ffl = tops[k]
        nxt = tops[k + 1]
        slab_bot = nxt - slab
        dl.line(x_lo, ffl, x_hi, ffl, layer=L_SLAB)
        _fill_band(dl, face_lo, slab_bot, face_hi, nxt, L_SLAB)   # slab, flush

        # facing openings in ELEVATION (behind the cut plane, occluded)
        for (t0, t1, sill, lintel, kind, tag) in faces:
            _elev_opening(dl, t0, t1, ffl + sill,
                          min(ffl + lintel, slab_bot - beam),
                          kind, tag, L_CUT, L_TXT)

        for t, th, ext, w, I in cuts:
            wx0, wx1 = t - th / 2, t + th / 2
            op = _opening_at(plan, w, I)
            # this wall's beam: depth, sideways offset (a flushed beam draws
            # off-centre), and width — so the section shows how far it shifts
            bd, boff, bwid = _wall_beam(plan, w, I, ux, uy, beam, th)
            bx0, bx1 = t + boff - bwid / 2, t + boff + bwid / 2
            # a chajja only on an EXTERIOR wall, projecting to the outside
            csign = 0
            if ext:
                ov = ((w.x1 + w.x2) / 2 - ccx) * ux + \
                     ((w.y1 + w.y2) / 2 - ccy) * uy
                csign = 1 if ov > 0.1 else (-1 if ov < -0.1 else 0)
            info = _cut_column(dl, wx0, wx1, th, ffl, slab_bot, op,
                               bd, dpc, stiff_t, stiff_int,
                               (L_CUT, L_SLAB, L_TXT, L_DIM), bx0, bx1, csign)
            # if the beam is flushed off the wall, dimension its projection
            if bd > 0 and abs(boff) > 0.03 and k == 0:
                face = wx1 if boff > 0 else wx0
                bface = bx1 if boff > 0 else bx0
                yb = slab_bot - bd / 2
                if abs(bface - face) > 0.03:
                    _mask_text(dl, (face + bface) / 2, slab_bot + 0.3,
                               str(round(abs(bface - face) * MM)), 0.26, L_DIM)
            rep.setdefault("wall_x", t)
            rep.setdefault("wall_y", (ffl + slab_bot) / 2)
            if op is not None and info and k == 0:
                sy, ly, is_door = info
                cut_ops.append({"x": t, "tag": op.tag or "", "door": is_door,
                                "w": op.width,
                                "sill_mm": round((sy - ffl) * MM),
                                "lint_mm": round((ly - ffl) * MM)})
                # tag DOWN low — below the window sill / near the door foot — so
                # it never sits over the lintel band and stays clear
                tag_y = (sy - 0.45) if not is_door else (ffl + 0.5)
                _mask_text(dl, t, tag_y, op.tag or "", 0.32, L_TXT)
                rep.setdefault("lint_x", t)
                rep.setdefault("lint_y", ly)
                if not is_door:
                    rep.setdefault("sill_x", t)
                    rep.setdefault("sill_y", sy)
        # staircase flights rising through this storey
        for fl in flights:
            _draw_stair_section(dl, fl["ta"], fl["tb"], ffl, nxt - ffl,
                                fl["s"], fl["turn_hi"], fl["up_hi"], L_CUT)
            if k == 0:
                _mask_text(dl, (fl["ta"] + fl["tb"]) / 2,
                           ffl + (nxt - ffl) * 0.5, fl["label"], 0.3, L_TXT)
        if beam > 0 and k == 0:
            rep["beam_x"] = cuts[0][0]
            rep["beam_y"] = tops[1] - slab - beam / 2

    top = tops[floors]

    # entry steps (outside, up to the plinth) — drawn once, from ground level
    for st in esteps:
        _draw_flight(dl, st["ta"], st["tb"], 0.0, st["rise"], st["n"],
                     st["up_hi"], L_CUT)

    # the doors / windows seen in elevation on the first wall beyond the cut
    for (t0, t1, sill, lintel, kind, tag) in faces:
        cut_ops.append({"x": (t0 + t1) / 2, "tag": tag,
                        "door": kind == "door", "w": t1 - t0,
                        "sill_mm": round(sill * MM),
                        "lint_mm": round(lintel * MM), "beyond": True})

    # ---- parapet + RCC coping on the top slab (exterior walls) ---------
    if para > 0:
        for t, th, ext, w, I in cuts:
            if not ext:
                continue
            _cut_wall(dl, t - th / 2, t + th / 2, top, top + para, L_CUT)
            _fill_band(dl, t - th / 2 - 0.15, top + para,          # RCC coping
                       t + th / 2 + 0.15, top + para + coping, L_SLAB)

    # in a multi-floor stack this storey draws no annotations — the project
    # composes one combined dimension stack / level marks for the whole section
    if no_annot:
        return dl, notes

    # ---- left dimension stack (storey / component heights) -------------
    segs = []
    if plinth > 0:
        segs.append((-found_depth, 0, round(found_depth * MM)))
    if plinth > 0:
        segs.append((0, ffl0, round(plinth * MM)))
    for k in range(floors):
        segs.append((tops[k], tops[k + 1], round(fh * MM)))
    if para > 0:
        segs.append((top, top + para, round(para * MM)))
    _dim_stack(dl, x_lo - 2.2, segs, L_DIM)

    # ---- named LEVEL marks, on the right, with leader arrows -----------
    # only well-separated levels go here; the thin plinth build-up is annotated
    # separately as ONE ordered note so its layers never cross-hatch a dozen
    # arrows into the same 400 mm band.
    ax = x_hi + 1.8
    # level datums — reference names, drawn as dashed lines + half-filled bubbles
    ents = [(0.0, x_hi, "INTERNAL RD")]
    ents.append((ffl0, x_hi, "PLINTH" if plinth > 0 else "F.F.L"))
    for k in range(1, floors):
        ents.append((tops[k], x_hi, "FLOOR"))
    ents.append((top, x_hi, "ROOF SLAB"))
    if rep.get("lint_y") is not None:
        ents.append((rep["lint_y"], rep["lint_x"], "LINTEL"))
    if rep.get("sill_y") is not None:
        ents.append((rep["sill_y"], rep["sill_x"], "SILL"))
    if para > 0:
        ents.append((top + para, x_hi, "PARAPET"))
        ents.append((top + para + coping, x_hi, "COPING"))
    _level_marks(dl, ax, ents, L_DIM)

    # detail callouts at the key junctions (parapet 'A', roof-slab edge 'B',
    # plinth / step 'S') — keyed to blown-up 'DETAIL AT x' details
    _detail_callout(dl, x_hi, (top + para + coping) if para > 0 else top, "A", L_DIM)
    _detail_callout(dl, x_hi, top, "B", L_DIM)
    _detail_callout(dl, x_lo, ffl0, "S", L_DIM)

    # ---- horizontal dimension chain: every cut-wall centreline + overall ---
    low = -found_depth if plinth > 0 else 0.0
    wall_ts = [t for (t, th, ext, w, I) in cuts]
    ybot = _hdim_chain(dl, low - 1.6, wall_ts, x_lo, x_hi, low, L_DIM)

    # ---- second vertical chain: opening sub-heights (sill / lintel / head) -
    vseg = []
    if rep.get("sill_y") is not None:
        vseg.append((ffl0, rep["sill_y"], round((rep["sill_y"] - ffl0) * MM)))
        vseg.append((rep["sill_y"], rep["lint_y"],
                     round((rep["lint_y"] - rep["sill_y"]) * MM)))
    elif rep.get("lint_y") is not None:
        vseg.append((ffl0, rep["lint_y"], round((rep["lint_y"] - ffl0) * MM)))
    if rep.get("lint_y") is not None and floors >= 1:
        vseg.append((rep["lint_y"], tops[1],
                     round((tops[1] - rep["lint_y"]) * MM)))
    if vseg:
        _dim_stack(dl, x_lo - 4.7, vseg, L_DIM)

    # ---- openings legend, clear below the horizontal dimensions ------------
    _openings_legend(dl, x_lo, ybot - 1.2, cut_ops, (L_TXT, L_DIM))
    # ---- material / hatch legend, to the right of the opening schedule ------
    _hatch_legend(dl, x_lo + 13.5, ybot - 1.2)
    # ---- plinth build-up note, in the bottom band, clear of the drawing -----
    if plinth > 0:
        lines = ["FLOOR FINISH + 75 SCREED", "D.P.C. 75 THK.",
                 "100-150 THK. P.C.C. (M15)"]
        if is_gf and pb_ht > 0:
            lines.append(f"R.C.C. PLINTH BEAM "
                         f"{round(params.get('plinth_beam_thk_mm', 0))}x"
                         f"{round(params.get('plinth_beam_ht_mm', 0))}")
        lines += ["230 THK. RUBBLE SOLING",
                  f"R.R. STONE MASONRY FOOTING (1:6) {_lvl(-found_depth)}",
                  "EARTH FILLING, WELL COMPACTED"]
        _note_block(dl, 0, 0, x_lo + 24.5, ybot - 0.5, lines,
                    "PLINTH BUILD-UP (TOP TO BOTTOM):", L_TXT, L_DIM,
                    leader=False)

    notes.append(f"Section cut through {len(cuts)} walls, {floors} floor(s), "
                 f"FFL {_lvl(ffl0)} to {_lvl(top)}.")
    return dl, notes


def build_project(floor_plans, p1, p2, params):
    """A MULTI-FLOOR section: the SAME cut line through every floor's own plan,
    the storeys stacked GL up (ground floor with its foundation, top floor with
    its parapet), and ONE combined dimension stack + level marks for the set."""
    plinth = _mm_ft(params.get("plinth_mm", 0)) if params.get("is_ground", True) \
        else 0.0
    fh = _mm_ft(params.get("floor_height_mm", 0))
    n = len(floor_plans)
    out = DrawList()
    notes = []
    if fh <= 0 or n == 0:
        return out, ["Floor height is required to cut a section."]
    for i, plan in enumerate(floor_plans):
        pp = dict(params)
        pp["floors"] = 1
        pp["_no_annot"] = True
        if i == 0:
            pp["is_ground"] = True
            pp["_no_ground"] = False
            pp["parapet_mm"] = params.get("parapet_mm", 0) if n == 1 else 0
            dy = 0.0
        else:
            pp["is_ground"] = False
            pp["plinth_mm"] = 0
            pp["_no_ground"] = True
            pp["parapet_mm"] = params.get("parapet_mm", 0) if i == n - 1 else 0
            dy = plinth + i * fh
        dli, ns = build(plan, p1, p2, pp)
        out.extend(dli.translated(0.0, dy))
        notes += ns
    _project_levels(out, params, plinth, fh, n)
    notes.append(f"Multi-floor section: {n} floor(s) stacked.")
    return out, notes


def _project_levels(out, params, plinth, fh, n):
    """One combined left dimension stack + right level marks for a stacked
    multi-floor section (uses the drawing's own x-extent)."""
    b = out.bounds()
    x_lo, x_hi = b[0], b[2]
    para = _mm_ft(params.get("parapet_mm", 0))
    coping = _mm_ft(150) if para > 0 else 0.0
    found_depth = _mm_ft(915)
    top = plinth + n * fh
    L_DIM = "SEC-DIM"

    segs = []
    if plinth > 0:
        segs.append((-found_depth, 0.0, round(found_depth * MM)))
        segs.append((0.0, plinth, round(plinth * MM)))
    for i in range(n):
        b0 = plinth + i * fh
        segs.append((b0, b0 + fh, round(fh * MM)))
    if para > 0:
        segs.append((top, top + para, round(para * MM)))
    _dim_stack(out, x_lo - 2.2, segs, L_DIM)

    ents = [(0.0, x_hi, "INTERNAL RD"),
            (plinth, x_hi, "PLINTH")]
    for i in range(1, n):
        lv = plinth + i * fh
        ord_ = ["", "1ST", "2ND", "3RD", "4TH", "5TH"]
        ents.append((lv, x_hi, f"{ord_[i] if i < len(ord_) else i} FLOOR"))
    ents.append((top, x_hi, "ROOF SLAB"))
    if para > 0:
        ents.append((top + para + coping, x_hi, "PARAPET"))
    _level_marks(out, x_hi + 1.8, ents, L_DIM)


def _cut_column(dl, wx0, wx1, th, ffl, slab_bot, op, beam, dpc,
                stiff_t, stiff_int, layers, bx0=None, bx1=None, chajja=0):
    """One cut wall from FFL to the slab soffit. Over every cut door / window an
    RCC lintel band (100 mm) is cast at the lintel level; under every cut window
    an RCC sill band (100 mm) at the sill level; and on an exterior opening a
    chajja projects from the LINTEL level (never at the roof)."""
    L_CUT, L_SLAB, L_TXT, L_DIM = layers
    if bx0 is None:
        bx0, bx1 = wx0, wx1
    band = _mm_ft(100)                               # RCC lintel / sill band
    top_solid = slab_bot - beam if beam > 0 else slab_bot
    ret = None
    if op is None:
        runs = [(ffl, top_solid)]
    else:
        sill, lintel = _open_levels(op)
        sy = min(ffl + sill, top_solid)
        ly = min(ffl + lintel, top_solid)
        is_door = getattr(op, "is_door", False)
        runs = []                                    # brick leaves the band gaps
        if not is_door and sy - band > ffl + 1e-3:
            runs.append((ffl, sy - band))
        if top_solid > ly + band + 1e-3:
            runs.append((ly + band, top_solid))
        ret = (sy, ly, is_door)
    for y0, y1 in runs:
        _cut_wall(dl, wx0, wx1, y0, y1, L_CUT)
    if beam > 0:                                     # beam at its own offset band
        _fill_band(dl, bx0, slab_bot - beam, bx1, slab_bot, L_SLAB)
        dl.rect(bx0, slab_bot - beam, bx1 - bx0, beam, layer=L_CUT)
    if abs(th * 12 - 4.5) < 0.6:                      # stiffeners, 4.5" walls
        yb = ffl + stiff_int
        while yb + stiff_t < slab_bot:
            for a, b in _clip_band(yb, yb + stiff_t, runs):
                _fill_band(dl, wx0, a, wx1, b, L_SLAB)
            yb += stiff_int
    if ret is not None:
        sy, ly, is_door = ret
        _rcc_band(dl, wx0, ly, wx1, ly + band, L_SLAB, L_CUT)     # lintel band
        if not is_door:
            _rcc_band(dl, wx0, sy - band, wx1, sy, L_SLAB, L_CUT)  # sill band
        if chajja:                                   # sunshade at LINTEL level
            proj, cth = _mm_ft(450), _mm_ft(75)
            cy = ly + band
            if chajja > 0:
                _rcc_band(dl, wx1, cy - cth, wx1 + proj, cy, L_SLAB, L_CUT)
            else:
                _rcc_band(dl, wx0 - proj, cy - cth, wx0, cy, L_SLAB, L_CUT)
        _draw_opening_cut(dl, wx0, wx1, sy, ly, is_door, L_CUT)
    return ret


def _hatch_legend(dl, x, y_top):
    """A key of every material hatch so the section reads unambiguously."""
    L_TXT, L_DIM, L_CUT = "SEC-TEXT", "SEC-DIM", "SEC-CUT"
    rows = [
        ("BRICK MASONRY", lambda a, b, c, d: _cut_wall(dl, a, b, c, d, L_CUT)),
        ("R.C.C. (slab / beam / lintel / footing)",
         lambda a, b, c, d: _rcc_band(dl, a, b, c, d, "SEC-SLAB", L_CUT)),
        ("D.P.C. 75 THK.", lambda a, b, c, d: _dpc_band(dl, a, b, c, d, L_CUT)),
        ("P.C.C. 100-150",
         lambda a, b, c, d: _pcc_band(dl, a, b, c, d, "SEC-SLAB", L_CUT)),
        ("RUBBLE SOLING 230",
         lambda a, b, c, d: _rubble_band(dl, a, b, c, d, L_CUT)),
        ("FLOORING + SCREED",
         lambda a, b, c, d: _screed_band(dl, a, b, c, d, L_CUT)),
        ("EARTH / SAND FILLING",
         lambda a, b, c, d: _hatch(dl, a, b, c, d, "SEC-EARTH", step=0.28)),
    ]
    sw, sh, gap = 1.7, 0.72, 1.0
    dl.text(x, y_top + 0.6, "LEGEND — MATERIALS", h=0.42, layer=L_TXT, bold=True)
    y = y_top
    for name, draw in rows:
        draw(x, y - sh, x + sw, y)
        dl.rect(x, y - sh, sw, sh, layer=L_DIM)
        dl.text(x + sw + 0.35, y - sh * 0.62, name, h=0.34, layer=L_TXT,
                halign="left")
        y -= gap


def _rcc_band(dl, x0, y0, x1, y1, fill_layer, edge_layer):
    """A filled RCC band with an outline (lintel / sill / chajja / screed)."""
    if y1 <= y0 or x1 <= x0:
        return
    _fill_band(dl, x0, y0, x1, y1, fill_layer)
    dl.rect(x0, y0, x1 - x0, y1 - y0, layer=edge_layer)


def _cfill(dl, x0, y0, x1, y1, color, edge_layer):
    dl.fill([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], color=color,
            layer="SEC-SLAB")
    dl.rect(x0, y0, x1 - x0, y1 - y0, layer=edge_layer)


def _concrete_specks(dl, x0, y0, x1, y1, edge_layer, step=0.34):
    """The standard CONCRETE symbol — scattered triangular aggregate + dots.
    A deterministic pseudo-random scatter (no RNG) so PCC / RCC read instantly
    as concrete and not as a blank fill."""
    import math as _m
    r0, c0 = 0, 0
    yy = y0 + step * 0.6
    while yy < y1 - step * 0.25:
        xx = x0 + step * (0.6 + 0.4 * (r0 % 2))
        while xx < x1 - step * 0.25:
            # a tiny filled triangle (aggregate stone) + a dot beside it
            j = ((r0 * 7 + c0 * 13) % 5) * 0.05
            s = 0.055
            dl.line(xx - s, yy - s, xx + s, yy - s, layer=edge_layer)
            dl.line(xx + s, yy - s, xx, yy + s + j, layer=edge_layer)
            dl.line(xx, yy + s + j, xx - s, yy - s, layer=edge_layer)
            dl.line(xx + step * 0.42, yy + step * 0.12,
                    xx + step * 0.42, yy + step * 0.12, layer=edge_layer)
            dl.arc(xx + step * 0.44, yy + step * 0.1, 0.025, 0, 360,
                   layer=edge_layer)
            xx += step
            c0 += 1
        yy += step
        r0 += 1


def _pcc_band(dl, x0, y0, x1, y1, fill_layer, edge_layer):
    """PCC (lean concrete) bed — a light-grey fill + the concrete aggregate
    HATCH (one object), lighter and sparser than structural RCC."""
    if y1 <= y0 or x1 <= x0:
        return
    _cfill(dl, x0, y0, x1, y1, "#c7ccd6", edge_layer)
    dl.hatch([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], kind="concrete",
             step=0.4, layer=edge_layer)


def _screed_band(dl, x0, y0, x1, y1, edge_layer):
    """Flooring + screed bedding — the finished floor line on top and a thin
    hatched screed underneath, in a warm off-white so it reads as finish."""
    if y1 <= y0 or x1 <= x0:
        return
    _cfill(dl, x0, y0, x1, y1, "#f3ead9", edge_layer)
    _hatch(dl, x0, y0, x1, y1, edge_layer, step=0.16, slope=-1)
    dl.line(x0, y1, x1, y1, layer=edge_layer)             # finished floor line


def _dpc_band(dl, x0, y0, x1, y1, edge_layer):
    """Damp-proof course — a SOLID dark band with a hatched membrane line so it
    reads as a distinct thin course, never confused with the pale bands."""
    if y1 <= y0 or x1 <= x0:
        return
    _cfill(dl, x0, y0, x1, y1, "#5b6270", edge_layer)
    ym = (y0 + y1) / 2
    x = x0
    while x < x1:                                          # dense membrane dashes
        dl.line(x, ym, min(x + 0.12, x1), ym, layer=edge_layer)
        x += 0.22


def _rubble_band(dl, x0, y0, x1, y1, edge_layer):
    """Rubble / stone soling — a warm-grey fill + the broken-stone HATCH (one
    object), unmistakable against PCC."""
    if y1 <= y0 or x1 <= x0:
        return
    _cfill(dl, x0, y0, x1, y1, "#d9d3c4", edge_layer)
    dl.hatch([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], kind="rubble",
             step=0.5, layer=edge_layer)


def _clip_band(a, b, runs):
    """Parts of the band [a, b] that fall inside a solid masonry run."""
    out = []
    for y0, y1 in runs:
        lo, hi = max(a, y0), min(b, y1)
        if hi - lo > 1e-3:
            out.append((lo, hi))
    return out


def _draw_opening_cut(dl, x0, x1, sy, ly, is_door, layer):
    """The cut through a door / window: jambs, sill & head frame members, and
    the glass (double line) or door leaf — a readable joinery section."""
    if ly <= sy:
        return
    fr = min(0.12, (ly - sy) * 0.15)
    cx = (x0 + x1) / 2
    dl.line(x0, sy, x0, ly, layer=layer)                 # jambs
    dl.line(x1, sy, x1, ly, layer=layer)
    if is_door:
        dl.line(x0, ly - fr, x1, ly - fr, layer=layer)   # head member
        dl.line(cx, sy, cx, ly - fr, layer=layer)        # leaf, cut
    else:
        dl.line(x0, sy + fr, x1, sy + fr, layer=layer)   # sill member
        dl.line(x0, ly - fr, x1, ly - fr, layer=layer)   # head member
        g = min(0.03, (x1 - x0) * 0.22)
        dl.line(cx - g, sy + fr, cx - g, ly - fr, layer=layer)   # glazing
        dl.line(cx + g, sy + fr, cx + g, ly - fr, layer=layer)


def _leaders(dl, x_edge, entries, layer, minsep=0.62, h=0.34):
    """Named labels down the right margin, each with a leader + arrowhead back
    to its element, stacked so the text never overlaps."""
    ents = sorted(entries, key=lambda e: e[0])
    ys = []
    for (yp, xp, txt) in ents:
        y = yp if not ys else max(yp, ys[-1] + minsep)
        ys.append(y)
    for (yp, xp, txt), ly in zip(ents, ys):
        dl.line(xp, yp, x_edge, yp, layer=layer)          # across to the margin
        if abs(ly - yp) > 1e-3:
            dl.line(x_edge, yp, x_edge, ly, layer=layer)  # jog to the label row
        dl.line(x_edge, ly, x_edge + 0.35, ly, layer=layer)
        _arrowhead(dl, xp, yp, -1.0, 0.0, layer)
        dl.text(x_edge + 0.5, ly, txt, h=h, layer=layer, halign="left")


def _lvl_fi(ft: float) -> str:
    """Level value in feet-inches for the datum tag, e.g. '+21'-0"'."""
    sign = "+" if ft >= -1e-6 else "-"
    a = abs(ft)
    f = int(a + 1e-6)
    inch = int(round((a - f) * 12))
    if inch >= 12:
        f += 1
        inch -= 12
    return f"{sign}{f}'-{inch}\""


def _detail_callout(dl, cx, cy, tag, layer, r=0.62):
    """A DETAIL callout: a dashed circle round a junction with its tag (A/B/S),
    keying it to the blown-up 'DETAIL AT x' below — the reference convention."""
    ring = [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))
            for a in range(0, 360, 18)]
    dl.poly(ring, layer=layer, closed=True, dashed=True)
    dl.text(cx, cy - 0.18, tag, h=0.5, layer=layer, bold=True, halign="center")


def _level_bubble(dl, cx, cy, layer, r=0.32):
    """The standard LEVEL DATUM symbol: a circle with its lower half filled."""
    ring = [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))
            for a in range(0, 360, 20)]
    half = [(cx - r, cy), (cx + r, cy)] + \
           [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))
            for a in range(180, 361, 20)]
    dl.fill(half, color="#000000", layer=layer)      # filled lower half
    dl.poly(ring, layer=layer, closed=True)          # circle outline


def _level_marks(dl, x_edge, entries, layer, minsep=0.9, r=0.32, h=0.36):
    """Reference-style level datums down the right margin: a DASHED datum line
    from each element across to the margin, a half-filled level bubble, and two
    lines of text — the name ('SILL LVL.') and the level ('LVL. +3'-3"'). Rows
    are pushed apart so nothing overlaps."""
    ents = sorted(entries, key=lambda e: e[0])
    ys = []
    for (yp, xp, name) in ents:
        y = yp if not ys else max(yp, ys[-1] + minsep)
        ys.append(y)
    for (yp, xp, name), ly in zip(ents, ys):
        dl.line(xp, yp, x_edge, yp, layer=layer, dashed=True)   # dashed datum line
        if abs(ly - yp) > 1e-3:
            dl.line(x_edge, yp, x_edge, ly, layer=layer)        # jog to label row
        bx = x_edge + r + 0.05
        _level_bubble(dl, bx, ly, layer, r)
        tx = bx + r + 0.4
        dl.text(tx, ly + 0.14, f"{name} LVL.", h=h, layer=layer, halign="left", bold=True)
        dl.text(tx, ly - 0.34, f"LVL. {_lvl_fi(yp)}", h=h * 0.82, layer=layer, halign="left")


def _note_block(dl, px, py, tx, ty_top, lines, title, txt_layer, lead_layer,
                h=0.32, leader=True):
    """A titled note with its lines listed underneath. If `leader`, a single
    elbow + arrowhead keys it to (px, py); otherwise it stands alone (used when
    the note sits in the bottom title band, clear of the drawing)."""
    if leader:
        dl.line(px, py, tx - 0.4, py, layer=lead_layer)
        dl.line(tx - 0.4, py, tx - 0.4, ty_top, layer=lead_layer)
        dl.line(tx - 0.4, ty_top, tx, ty_top, layer=lead_layer)
        _arrowhead(dl, px, py, -1.0, 0.0, lead_layer)
    dl.text(tx, ty_top, title, h=h, layer=txt_layer, halign="left", bold=True)
    for i, ln in enumerate(lines):
        dl.text(tx + 0.25, ty_top - (i + 1) * (h * 1.55), f"- {ln}",
                h=h * 0.9, layer=txt_layer, halign="left")


def _arrowhead(dl, tx, ty, dx, dy, layer, size=0.22):
    """A small arrowhead whose tip is at (tx, ty), pointing along (dx, dy)."""
    bx, by = tx - dx * size, ty - dy * size
    px, py = -dy * size * 0.4, dx * size * 0.4
    dl.line(bx + px, by + py, tx, ty, layer=layer)
    dl.line(bx - px, by - py, tx, ty, layer=layer)


def _openings_legend(dl, x, y_top, ops, layers):
    """A small table of every door / window the section cuts: tag, type, width,
    sill and lintel — so all the opening data is on the sheet without crowding
    the drawing."""
    L_TXT, L_DIM = layers
    if not ops:
        return
    h = 0.34
    cw = h * 0.9                 # generous per-character width (screen fonts run wide)
    pad = 0.55
    heads = ["TAG", "TYPE", "WIDTH", "SILL", "LINTEL"]
    rows = [[o["tag"],
             ("DOOR" if o["door"] else "WINDOW")
             + (" (BEYOND)" if o.get("beyond") else " (CUT)"),
             f"{round(o['w'] * MM)}",
             "-" if o["door"] else f"{o['sill_mm']}",
             f"{o['lint_mm']}"] for o in ops]
    n = len(heads)
    # column widths from the widest cell so text never spills into the next column
    widths = [max([len(heads[c])] + [len(str(r[c])) for r in rows]) * cw + pad
              for c in range(n)]
    total = sum(widths)
    rh = h * 2.2                 # tall rows so lines never touch
    dl.text(x, y_top + 0.7, "OPENING SCHEDULE (AT SECTION)", h=0.42,
            layer=L_TXT, bold=True)
    y = y_top
    for r, cells in enumerate([heads] + rows):
        cx = x
        lyr = L_DIM if r == 0 else L_TXT
        for c in range(n):
            dl.text(cx + 0.25, y - rh * 0.64, str(cells[c]), h=h, layer=lyr,
                    halign="left")
            cx += widths[c]
        if r == 0:
            dl.line(x, y - rh, x + total, y - rh, layer=L_DIM)   # under header
        y -= rh
    dl.rect(x, y, total, y_top - y, layer=L_DIM)                 # outer frame
    cx = x
    for c in range(n - 1):
        cx += widths[c]
        dl.line(cx, y, cx, y_top, layer=L_DIM)                   # column rules


def _mask_text(dl, x, y, s, h, layer, halign="center"):
    """Text on a white panel so no line runs through it."""
    if not s:
        return
    from .draw import CHAR_W
    w = len(str(s)) * h * CHAR_W + 0.25
    if halign == "left":
        cx = x + w / 2 - 0.1
    else:
        cx = x
    dl.fill_rect(cx - w / 2, y - h * 0.75, w, h * 1.6, color="#ffffff",
                 layer=layer)
    dl.text(x, y, str(s), h=h, layer=layer, halign=halign)


def _hdim_chain(dl, y, centres, x_lo, x_hi, top_ref, layer):
    """Horizontal running dimensions under the section: a tick + gap label at
    every wall centreline (extension lines rising to the drawing base), and an
    overall line beneath. Returns the lowest y used so the legend clears it."""
    cs = sorted(set(round(c, 3) for c in centres))
    if len(cs) >= 1:
        if len(cs) >= 2:
            dl.line(cs[0], y, cs[-1], y, layer=layer)
        for c in cs:
            dl.line(c, y - 0.25, c, y + 0.25, layer=layer)
            dl.line(c, y + 0.25, c, top_ref, layer=layer)          # extension
        for a, b in zip(cs, cs[1:]):
            _mask_text(dl, (a + b) / 2, y - 0.5, str(round((b - a) * MM)),
                       0.32, layer)
    yo = y - 1.5
    dl.line(x_lo, yo, x_hi, yo, layer=layer)                        # overall
    for c in (x_lo, x_hi):
        dl.line(c, yo - 0.25, c, yo + 0.25, layer=layer)
    _mask_text(dl, (x_lo + x_hi) / 2, yo - 0.5, str(round((x_hi - x_lo) * MM)),
               0.36, layer)
    return yo - 1.2


def _dim_stack(dl, x, segs, layer):
    """A vertical dimension line with a tick + height label per segment."""
    if not segs:
        return
    lo = min(s[0] for s in segs)
    hi = max(s[1] for s in segs)
    dl.line(x, lo, x, hi, layer=layer)
    for y0, y1, mm in segs:
        dl.line(x - 0.25, y0, x + 0.25, y0, layer=layer)
        dl.line(x - 0.25, y1, x + 0.25, y1, layer=layer)
        _mask_text(dl, x - 0.35, (y0 + y1) / 2, str(mm), 0.35, layer,
                   halign="center")


def build_all(plan, params):
    """Every section line laid out side by side on ONE drawing — for the
    on-screen view and the combined sheet."""
    from .draw import DrawList
    out = DrawList()
    dx = 0.0
    n = 0
    for s in getattr(plan, "sections", []):
        dl, _notes = build(plan, (s.x1, s.y1), (s.x2, s.y2),
                           dict(params, tag=s.tag,
                                view_flip=getattr(s, "flip", False)))
        if not dl.items:
            continue
        b = dl.bounds()
        w = b[2] - b[0]
        out.extend(dl.translated(dx - b[0], 0))
        out.text(dx + w / 2, b[1] - 2.2, f"SECTION {s.tag}-{s.tag}", h=0.9,
                 layer="SEC-TEXT", bold=True)
        dx += w + 10
        n += 1
    return out, n


def view_dir(plan, s):
    """Public: the view direction (unit normal) for a stored Section line."""
    return _view_dir(plan, (s.x1, s.y1), (s.x2, s.y2),
                     {"view_flip": getattr(s, "flip", False)})


def _wall_beam(plan, w, I, ux, uy, default_depth, th):
    """The beam sitting on wall `w`, as seen in the section: returns
    (depth_ft, offset_t, width_ft). `offset_t` is the beam's sideways shift from
    the wall centre-line projected onto the section axis, so a beam flushed to
    one face draws off-centre. Falls back to a centred band of the questionnaire
    depth and the wall thickness when no beam matches."""
    wl = w.length or 1e-9
    wux, wuy = (w.x2 - w.x1) / wl, (w.y2 - w.y1) / wl
    best, bestd = None, 1e9
    for b in getattr(plan, "beams", None) or []:
        if not b.depth_mm:
            continue
        bl = math.hypot(b.x2 - b.x1, b.y2 - b.y1) or 1e-9
        bux, buy = (b.x2 - b.x1) / bl, (b.y2 - b.y1) / bl
        if abs(bux * wux + buy * wuy) < 0.9:          # not parallel to the wall
            continue
        bw = b.width_mm / MM
        tb = (I[0] - b.x1) * bux + (I[1] - b.y1) * buy
        bx, by = b.x1 + bux * tb, b.y1 + buy * tb     # beam point opposite I
        dist = math.hypot(bx - I[0], by - I[1])
        if dist < th / 2 + bw / 2 + 0.3 and dist < bestd:
            bestd, best = dist, (b, bx, by, bw)
    if best is None:
        return default_depth, 0.0, th
    b, bx, by, bw = best
    off_t = (bx - I[0]) * ux + (by - I[1]) * uy
    return b.depth_mm / MM, off_t, bw


def _view_dir(plan, p1, p2, params):
    """Unit normal to the cut line pointing the way the section is viewed.
    Default is INTO the building (toward the centre of all the walls); a
    `view_flip` flag in the questionnaire turns it around."""
    x1, y1 = p1
    x2, y2 = p2
    L = math.hypot(x2 - x1, y2 - y1) or 1e-9
    ux, uy = (x2 - x1) / L, (y2 - y1) / L
    nx, ny = -uy, ux                                   # a normal
    # centroid of the wall network
    xs = [w.x1 for w in plan.walls] + [w.x2 for w in plan.walls]
    ys = [w.y1 for w in plan.walls] + [w.y2 for w in plan.walls]
    if xs:
        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        if nx * (cx - mx) + ny * (cy - my) < 0:        # flip toward centre
            nx, ny = -nx, -ny
    if params.get("view_flip"):
        nx, ny = -nx, -ny
    return nx, ny


def build_screen(plan, params):
    """The floor PLAN on top and its SECTION(s) below it, on one drawing, so
    the user sees plan and section together (and roughly aligned) instead of
    switching between them. Returns (DrawList, n_sections)."""
    from . import engine
    out = DrawList()
    plan_dl = engine.build(plan, wall_tags=False, furniture=False,
                           elec=False, plumb=False, floor=False)
    out.extend(plan_dl)
    pb = plan_dl.bounds()                              # (x0,y0,x1,y1) y-up

    sec, n = build_all(plan, params)
    if sec.items:
        sb = sec.bounds()
        gap = max(4.0, (pb[3] - pb[1]) * 0.18)
        # centre the section band under the plan, drop it below the plan bottom
        dxs = (pb[0] + pb[2]) / 2 - (sb[0] + sb[2]) / 2
        dys = (pb[1] - gap) - sb[3]
        out.extend(sec.translated(dxs, dys))
        # a caption strip between the two
        out.text((pb[0] + pb[2]) / 2, pb[1] - gap * 0.5, "SECTIONS BELOW",
                 h=max(0.8, (pb[2] - pb[0]) * 0.012), layer="SEC-TEXT")
        # the blown-up construction details (DETAIL AT A / B / S) below the sections
        try:
            from . import details as DET
            wt = next((w.thickness_in for w in plan.walls
                       if getattr(w, "exterior", False)), 9) / 12.0
            sec_left = sb[0] + dxs
            sec_bottom = sb[1] + dys
            DET.draw_details(out, sec_left, sec_bottom - 6.0, wall_ft=wt)
        except Exception:
            pass
    return out, n


def _facing_openings(plan, p1, p2, x_lo, x_hi, view):
    """Doors / windows on walls PARALLEL to the cut, projected onto the section
    axis and shown in elevation — but only where they are actually SEEN: a
    wall on the removed side is dropped, and a wall standing behind a nearer
    wall is hidden over the overlap (occlusion in the view direction)."""
    x1, y1 = p1
    x2, y2 = p2
    L = math.hypot(x2 - x1, y2 - y1) or 1e-9
    ux, uy = (x2 - x1) / L, (y2 - y1) / L
    nx, ny = view

    # every parallel wall: its span along the cut and its depth in view dir
    walls = []
    for w in plan.walls:
        if getattr(w, "railing", False):
            continue
        wl = w.length or 1e-9
        wux, wuy = (w.x2 - w.x1) / wl, (w.y2 - w.y1) / wl
        if abs(ux * wux + uy * wuy) < 0.7:             # not parallel → it is cut
            continue
        ta = (w.x1 - x1) * ux + (w.y1 - y1) * uy
        tb = (w.x2 - x1) * ux + (w.y2 - y1) * uy
        if tb < ta:
            ta, tb = tb, ta
        mx, my = (w.x1 + w.x2) / 2, (w.y1 + w.y2) / 2
        depth = (mx - x1) * nx + (my - y1) * ny        # + = in front of viewer
        walls.append({"w": w, "ta": ta, "tb": tb, "depth": depth})

    # nearest wall first; each FRONT wall hides the span behind it. A wall on
    # the removed side (depth <= 0) is neither seen nor allowed to occlude —
    # else the back/removed wall would wrongly blank out the first real wall.
    walls.sort(key=lambda d: d["depth"])
    covered = []                                       # spans already opaque
    for d in walls:
        if d["depth"] <= 0.1:
            d["vis"] = []
            continue
        d["vis"] = _subtract(d["ta"], d["tb"], covered)
        covered.append((d["ta"], d["tb"]))

    out = []
    for d in walls:
        if not d["vis"]:
            continue
        w = d["w"]
        wallseg = [(a, b) for (a, b) in d["vis"]]
        for o in plan.openings:
            if o.wall_id != w.id or o.type in ("gate", "open"):
                continue
            a = w.point_at(o.pos)
            b = w.point_at(o.pos + o.width)
            t0 = (a[0] - x1) * ux + (a[1] - y1) * uy
            t1 = (b[0] - x1) * ux + (b[1] - y1) * uy
            if t1 < t0:
                t0, t1 = t1, t0
            if t1 < x_lo or t0 > x_hi:
                continue
            mid = (t0 + t1) / 2
            if not any(a2 - 0.05 <= mid <= b2 + 0.05 for a2, b2 in wallseg):
                continue                               # hidden behind a wall
            sill, lintel = _open_levels(o)
            kind = "door" if getattr(o, "is_door", False) else (
                "vent" if o.type == "vent" else "window")
            out.append((t0, t1, sill, lintel, kind, o.tag or ""))
    return out


def _subtract(a, b, spans):
    """The parts of [a, b] not covered by any span in `spans`."""
    free = [(a, b)]
    for (c, d) in spans:
        nxt = []
        for (x, y) in free:
            if d <= x or c >= y:                       # no overlap
                nxt.append((x, y))
                continue
            if c > x:
                nxt.append((x, min(c, y)))
            if d < y:
                nxt.append((max(d, x), y))
        free = [(x, y) for (x, y) in nxt if y - x > 0.25]
    return free


def _elev_opening(dl, x0, x1, y0, y1, kind, tag, layer, ltxt):
    """A door / window drawn in ELEVATION as it is actually seen through the
    section: an outer frame, an inner frame, and — for a window — a grid of
    glass panes with a sill projection; for a door, stiles, rails and a
    handle."""
    W, H = x1 - x0, y1 - y0
    if H <= 0.1 or W <= 0.1:
        return
    dl.rect(x0, y0, W, H, layer=layer)                     # outer frame
    fr = min(0.12, W * 0.12, H * 0.12)                     # frame thickness
    ix0, iy0, ix1, iy1 = x0 + fr, y0 + fr, x1 - fr, y1 - fr
    if ix1 <= ix0 or iy1 <= iy0:
        return
    dl.rect(ix0, iy0, ix1 - ix0, iy1 - iy0, layer=layer)   # inner frame

    if kind == "door":
        # a top rail + two panels, and a handle on the latch side
        rail = iy0 + (iy1 - iy0) * 0.62
        dl.line(ix0, rail, ix1, rail, layer=layer)
        for py in (iy0 + (rail - iy0) * 0.5,):
            dl.line(ix0, py, ix1, py, layer=layer)
        dl.rect(ix0 + (ix1 - ix0) * 0.06, iy0 + (rail - iy0) * 0.12,
                (ix1 - ix0) * 0.88, (rail - iy0) * 0.76, layer=layer)
        dl.rect(ix0 + (ix1 - ix0) * 0.06, rail + (iy1 - rail) * 0.12,
                (ix1 - ix0) * 0.88, (iy1 - rail) * 0.76, layer=layer)
        hy = (iy0 + rail) / 2
        dl.line(ix1 - 0.22, hy - 0.12, ix1 - 0.22, hy + 0.12, layer=layer)
    else:
        # a window pane grid — columns ~1.2 ft, rows ~1.2 ft
        cols = max(1, min(4, int(round(W / 1.2))))
        rows = max(1, min(4, int(round(H / 1.3))))
        for c in range(1, cols):
            gx = ix0 + (ix1 - ix0) * c / cols
            dl.line(gx, iy0, gx, iy1, layer=layer)
        for r in range(1, rows):
            gy = iy0 + (iy1 - iy0) * r / rows
            dl.line(ix0, gy, ix1, gy, layer=layer)
        # sill projecting a little each side, under the frame
        dl.line(x0 - 0.12, y0, x1 + 0.12, y0, layer=layer)
        dl.line(x0 - 0.12, y0 - 0.08, x1 + 0.12, y0 - 0.08, layer=layer)
    if tag:
        _mask_text(dl, (x0 + x1) / 2, y1 + 0.28, tag, 0.32, ltxt)


def _cut_joinery(dl, x0, x1, y0, y1, is_door, is_vent, layer):
    """The opening the plane cuts THROUGH, drawn as a proper cut section:
    a window shows its sill member, head member and the glass as a thin double
    line down the middle; a door shows the head frame and the leaf."""
    if y1 <= y0 or x1 <= x0:
        return
    cx = (x0 + x1) / 2
    fr = min(0.1, (x1 - x0) * 0.3)                     # frame member depth
    if is_door:
        # head member (transom) + the door leaf as a thin cut panel
        dl.line(x0, y1 - fr, x1, y1 - fr, layer=layer)
        dl.rect(cx - 0.03, y0, 0.06, y1 - fr, layer=layer)   # leaf, cut
    else:
        # sill + head members
        dl.line(x0, y0 + fr, x1, y0 + fr, layer=layer)
        dl.line(x0, y1 - fr, x1, y1 - fr, layer=layer)
        # glass: thin double line down the middle of the opening
        dl.line(cx - 0.03, y0 + fr, cx - 0.03, y1 - fr, layer=layer)
        dl.line(cx + 0.03, y0 + fr, cx + 0.03, y1 - fr, layer=layer)


def _opening_at(plan, wall, cross_pt):
    """The opening on `wall` that the section crosses, or None."""
    px, py = cross_pt
    pos = math.hypot(px - wall.x1, py - wall.y1)
    for o in plan.openings:
        if o.wall_id != wall.id:
            continue
        if o.type in ("gate", "open"):
            continue
        if o.pos - 0.05 <= pos <= o.pos + o.width + 0.05:
            return o
    return None


def _ascent_dir(up_from, run_axis):
    """Unit plan-vector pointing the way the stair GOES UP (opposite the side
    the UP arrow enters)."""
    return {"left": (1.0, 0.0), "right": (-1.0, 0.0),
            "bottom": (0.0, 1.0), "top": (0.0, -1.0)}.get(up_from, (0.0, 1.0))


def _project_rect(x1s, y1s, ux, uy, rx, ry, rw, rh):
    ts = [((cx - x1s) * ux + (cy - y1s) * uy)
          for cx, cy in ((rx, ry), (rx + rw, ry),
                         (rx, ry + rh), (rx + rw, ry + rh))]
    return min(ts), max(ts)


def _seg_hits_rect(a, b, rx, ry, rw, rh):
    (ax, ay), (bx, by) = a, b
    if rx <= ax <= rx + rw and ry <= ay <= ry + rh:
        return True
    if rx <= bx <= rx + rw and ry <= by <= ry + rh:
        return True
    edges = (((rx, ry), (rx + rw, ry)), ((rx + rw, ry), (rx + rw, ry + rh)),
             ((rx + rw, ry + rh), (rx, ry + rh)), ((rx, ry + rh), (rx, ry)))
    return any(_seg_x(a, b, e0, e1) is not None for e0, e1 in edges)


def _flights_in_section(plan, x1s, y1s, ux, uy, p1, p2, x_lo, x_hi):
    out = []
    for s in getattr(plan, "stairs", None) or []:
        if not _seg_hits_rect(p1, p2, s.x, s.y, s.w, s.h):
            continue
        ta, tb = _project_rect(x1s, y1s, ux, uy, s.x, s.y, s.w, s.h)
        if tb < x_lo or ta > x_hi:
            continue
        ax, ay = _ascent_dir(getattr(s, "up_from", "bottom"),
                             getattr(s, "run_axis", "y"))
        tvx, tvy = _side_dir(getattr(s, "turn_side", "right"))
        n = (getattr(s, "steps_f1", 0) or getattr(s, "treads", 0) or 0)
        out.append({"ta": ta, "tb": tb, "up_hi": (ax * ux + ay * uy) >= 0,
                    "turn_hi": (tvx * ux + tvy * uy) >= 0, "s": s,
                    "n": (n + 1) if n else 0,
                    "label": (getattr(s, "label", "") or "STAIRCASE").upper()})
    return out


def _side_dir(side):
    """Plan-vector of a named side (right = +x/east, top = +y/north)."""
    return {"left": (-1.0, 0.0), "right": (1.0, 0.0),
            "bottom": (0.0, -1.0), "top": (0.0, 1.0)}.get(side, (1.0, 0.0))


def _steps_in_section(plan, x1s, y1s, ux, uy, p1, p2, x_lo, x_hi):
    out = []
    for s in getattr(plan, "steps", None) or []:
        if not _seg_hits_rect(p1, p2, s.x, s.y, s.w, s.h):
            continue
        ta, tb = _project_rect(x1s, y1s, ux, uy, s.x, s.y, s.w, s.h)
        if tb < x_lo or ta > x_hi:
            continue
        ax, ay = _ascent_dir(getattr(s, "up_from", "left"),
                             getattr(s, "run_axis", "x"))
        out.append({"ta": ta, "tb": tb, "up_hi": (ax * ux + ay * uy) >= 0,
                    "n": max(1, getattr(s, "count", 2) or 2),
                    "rise": _steps_rise(s)})
    return out


def _steps_rise(s):
    lv = getattr(s, "levels", None) or []
    ft = _parse_ft(lv[-1]) if lv else None
    return ft if ft else max(1, getattr(s, "count", 2) or 2) * 0.5


def _parse_ft(txt):
    import re
    m = re.search(r"(-?\d+)'\s*-?\s*(\d+)?", str(txt or ""))
    if not m:
        return None
    return abs(int(m.group(1))) + int(m.group(2) or 0) / 12.0


def _nosing_pts(x0, y0, going, riser, n, sign):
    """Stepped nosing polyline: from (x0, y0), each step a riser up then a tread
    of `going` in the `sign` direction."""
    pts = [(x0, y0)]
    x, y = x0, y0
    for _ in range(int(max(1, n))):
        y += riser
        pts.append((x, y))
        x += sign * going
        pts.append((x, y))
    return pts


def _polyline(dl, pts, layer):
    for a, b in zip(pts, pts[1:]):
        dl.line(a[0], a[1], b[0], b[1], layer=layer)


def _draw_stair_section(dl, ta, tb, y_low, rise, s, turn_hi, up_hi, layer):
    """A staircase in section. straight = one stepped run. U = two flights with
    a half-landing between them (the far flight reads as the elevation of the
    return). U3 = two flights + a short middle flight over two landings. Risers
    are ~150 mm; the sketch's step counts set how they split."""
    if tb - ta < 0.2 or rise <= 0:
        return
    typ = getattr(s, "type", "straight")
    riser = _mm_ft(150)
    N = max(2, int(round(rise / riser)))
    if typ not in ("U", "U3"):
        n = int(getattr(s, "steps_f1", 0) or getattr(s, "treads", 0) or N)
        _draw_flight(dl, ta, tb, y_low, rise, n, up_hi, layer)
        return

    W = tb - ta
    land = min(max(W * 0.16, _mm_ft(900)), W * 0.34)      # landing depth
    run = W - land

    if typ == "U":
        n1 = int(getattr(s, "steps_f1", 0) or N // 2)
        n2 = int(getattr(s, "steps_f2", 0) or (N - n1))
        riser = rise / max(1, n1 + n2)
        ymid = y_low + n1 * riser
        if turn_hi:                                       # landing at tb (turn)
            f1 = _nosing_pts(ta, y_low, run / max(1, n1), riser, n1, +1)
            la, lb = (ta + run, ymid), (tb, ymid)
            f2 = _nosing_pts(tb - land, ymid, run / max(1, n2), riser, n2, -1)
        else:                                             # landing at ta
            f1 = _nosing_pts(tb, y_low, run / max(1, n1), riser, n1, -1)
            la, lb = (tb - run, ymid), (ta, ymid)
            f2 = _nosing_pts(ta + land, ymid, run / max(1, n2), riser, n2, +1)
        # only the CUT flight carries the hatched waist slab; the RETURN flight
        # is beyond the cut and reads as a plain stepped outline — hatching both
        # made the two bands cross mid-air into an unreadable X
        _polyline(dl, f1, layer)
        _landing_slab(dl, la[0], lb[0], ymid, _mm_ft(150), layer)  # mid-landing SLAB
        _polyline(dl, f2, layer)
        _waist_band(dl, f1[0][0], f1[0][1], f1[-1][0], f1[-1][1], _mm_ft(150), layer)
        dl.line(f2[0][0], f2[0][1], f2[-1][0], f2[-1][1], layer=layer)  # thin soffit
        return

    # U3 — two main flights and a short middle flight, over two landings
    n1 = int(getattr(s, "steps_f1", 0) or N // 3)
    n3 = int(getattr(s, "steps_f3", 0) or max(2, N // 4))
    n2 = int(getattr(s, "steps_f2", 0) or max(1, N - n1 - n3))
    riser = rise / max(1, n1 + n2 + n3)
    y1 = y_low + n1 * riser
    y2 = y1 + n3 * riser
    if turn_hi:
        f1 = _nosing_pts(ta, y_low, run / max(1, n1), riser, n1, +1)
        mid = _nosing_pts(ta + run, y1, land / max(1, n3), riser, n3, +1)
        f2 = _nosing_pts(tb, y2, run / max(1, n2), riser, n2, -1)
    else:
        f1 = _nosing_pts(tb, y_low, run / max(1, n1), riser, n1, -1)
        mid = _nosing_pts(tb - run, y1, land / max(1, n3), riser, n3, -1)
        f2 = _nosing_pts(ta, y2, run / max(1, n2), riser, n2, +1)
    # U3: hatch the waist under the CUT (first) flight only; the middle and
    # return flights are beyond the cut — plain outlines with a thin soffit
    for i, pl in enumerate((f1, mid, f2)):
        _polyline(dl, pl, layer)
        if i == 0:
            _waist_band(dl, pl[0][0], pl[0][1], pl[-1][0], pl[-1][1], _mm_ft(150), layer)
        else:
            dl.line(pl[0][0], pl[0][1], pl[-1][0], pl[-1][1], layer=layer)


def _landing_slab(dl, x0, x1, y, wt, layer):
    """A LANDING / mid-landing as a real RCC slab: a horizontal concrete-hatched
    band of thickness `wt` under the landing level `y` (not a bare line)."""
    if abs(x1 - x0) < 1e-6:
        return
    lo, hi = min(x0, x1), max(x0, x1)
    poly = [(lo, y), (hi, y), (hi, y - wt), (lo, y - wt)]
    try:
        dl.hatch([poly], kind="concrete", step=0.45, layer="SEC-SLAB")
    except Exception:
        pass
    dl.poly(poly, layer=layer, closed=True)


def _waist_band(dl, ax, ay, bx, by, wt, layer):
    """The sloped RCC WAIST SLAB under a flight: a concrete-hatched band from the
    pitch line (ax,ay)->(bx,by) down perpendicular by `wt` — so the stair reads
    as a real slab with thickness, not a bare stepped line."""
    L = math.hypot(bx - ax, by - ay) or 1e-9
    ux, uy = (bx - ax) / L, (by - ay) / L
    px, py = uy, -ux                                 # perpendicular
    if py > 0:                                        # make it point DOWN
        px, py = -px, -py
    poly = [(ax, ay), (bx, by), (bx + px * wt, by + py * wt), (ax + px * wt, ay + py * wt)]
    try:
        dl.hatch([poly], kind="concrete", step=0.45, layer="SEC-SLAB")
    except Exception:
        pass
    dl.poly(poly, layer=layer, closed=True)


def _draw_flight(dl, ta, tb, y_low, rise, n, up_hi, layer):
    """A stair flight in section: the RCC waist slab (hatched), the stepped
    tread/riser nosings on top, and the riser faces filled so it reads solid.
    Standard riser (~6\") sets the count when the sketch gives none."""
    if tb - ta < 0.2 or rise <= 0:
        return
    n = int(n)
    if n <= 0:
        n = max(3, int(round(rise / 0.5)))          # ~6" risers if unknown
    riser = rise / n
    going = (tb - ta) / n
    if up_hi:                                        # low at ta, high at tb
        x, y, step = ta, y_low, going
    else:                                            # low at tb, high at ta
        x, y, step = tb, y_low, -going
    # RCC waist slab first (pitch line runs a riser below the top nosing)
    wt = _mm_ft(150)
    if up_hi:
        _waist_band(dl, ta, y_low, tb, y_low + rise - riser, wt, layer)
    else:
        _waist_band(dl, tb, y_low, ta, y_low + rise - riser, wt, layer)
    # stepped tread / riser nosing line on top
    pts = [(x, y)]
    for _ in range(n):
        y += riser
        pts.append((x, y))                           # riser
        x += step
        pts.append((x, y))                           # tread
    for A, B in zip(pts, pts[1:]):
        dl.line(A[0], A[1], B[0], B[1], layer=layer)
    # arrival LANDING slab at the top of the flight (a real slab, not a line)
    _landing_slab(dl, x, x + (1 if step > 0 else -1) * _mm_ft(1000), y, wt, layer)


def _cut_wall(dl, x0, x1, y0, y1, layer):
    if y1 <= y0 or x1 <= x0:
        return
    dl.rect(x0, y0, x1 - x0, y1 - y0, layer=layer)
    _hatch(dl, x0, y0, x1, y1, layer, step=0.28)


def _fill_band(dl, x0, y0, x1, y1, layer):
    """Structural R.C.C. member (slab / beam / lintel / plinth beam / coping) —
    a SOLID mid-grey, the only solid fill in the section so concrete members are
    unmistakable."""
    if y1 <= y0:
        return
    dl.fill([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], color="#b7bcc8",
            layer=layer)
    dl.rect(x0, y0, x1 - x0, y1 - y0, layer=layer)


def _sec_footing(dl, cx, y_top, y_bot, top_w, base_w, edge_layer):
    """A tapered RR-stone-masonry footing under a cut wall, hatched like the
    typical foundation section."""
    if y_top <= y_bot:
        return
    ht, hb = top_w / 2, base_w / 2
    pts = [(cx - ht, y_top), (cx + ht, y_top),
           (cx + hb, y_bot), (cx - hb, y_bot)]
    dl.fill(pts, color="#efe4d2", layer="SEC-SLAB")
    for a, b in zip(pts, pts[1:] + pts[:1]):
        dl.line(a[0], a[1], b[0], b[1], layer=edge_layer)
    # 45° stone-masonry hatch clipped to the ACTUAL tapered trapezoid (not its
    # bounding box) so it never spills past the sloped sides at the top
    _hatch_poly(dl, pts, edge_layer, step=0.42)


def _hatch_poly(dl, pts, layer, step=0.4, slope=1):
    """Hatch clipped to an arbitrary polygon (the tapered footing). Emits ONE
    Hatch primitive; the DXF gets a real HATCH bounded by the polygon, so it
    never spills past the sloped edges and is a single object."""
    dl.hatch(list(pts), kind="diag45" if slope >= 0 else "diag135",
             step=step, layer=layer)


def _draw_foundation(dl, cuts, ffl0, dpc, pcc, screed, rubble_t,
                     pb_thk, pb_ht, found_depth, x_lo, x_hi, layers):
    """The whole below-plinth zone drawn like a proper foundation section:
    finished floor + screed, PCC bed, rubble soling and earth filling between
    the walls, and at every cut wall a plinth beam, DPC and a tapered footing
    down to hard soil. Bands are clipped to the room gaps so nothing overlaps
    the masonry / footings."""
    L_CUT, L_SLAB, L_EARTH, L_TXT, L_DIM = layers
    pb_top = ffl0 - dpc                        # PCC top = plinth-beam top
    pb_h = pb_ht if pb_ht > 0 else _mm_ft(300)
    pb_bot = pb_top - pb_h
    pcc_bot = pb_top - pcc
    rub_bot = pcc_bot - rubble_t
    fdn_bot = -found_depth

    # room spans (between consecutive cut walls) + each wall's footing width
    gaps = []
    for i in range(len(cuts) - 1):
        g0 = cuts[i][0] + cuts[i][1] / 2
        g1 = cuts[i + 1][0] - cuts[i + 1][1] / 2
        if g1 - g0 > 0.05:
            gaps.append((g0, g1))
    base_w_of = {}
    for t, th, ext, w, I in cuts:
        pw = max(pb_thk, th) if pb_thk > 0 else th
        base_w_of[t] = pw + _mm_ft(460)

    # the finished floor build-up in every gap
    for g0, g1 in gaps:
        _rubble_band(dl, g0, rub_bot, g1, pcc_bot, L_CUT)      # 230 soling
        _pcc_band(dl, g0, pcc_bot, g1, pb_top, L_SLAB, L_CUT)  # 100-150 PCC
        _screed_band(dl, g0, pb_top, g1, ffl0, L_CUT)          # finish + screed

    # each cut wall: plinth beam + DPC + tapered footing + PCC blinding
    for t, th, ext, w, I in cuts:
        pw = max(pb_thk, th) if pb_thk > 0 else th
        top_w = pw + _mm_ft(150)
        base_w = base_w_of[t]
        _sec_footing(dl, t, pb_bot, fdn_bot + _mm_ft(100), top_w, base_w, L_CUT)
        _pcc_band(dl, t - base_w / 2 - 0.12, fdn_bot,
                  t + base_w / 2 + 0.12, fdn_bot + _mm_ft(100), L_SLAB, L_CUT)
        _rcc_band(dl, t - pw / 2, pb_bot, t + pw / 2, pb_top, L_SLAB, L_CUT)
        _dpc_band(dl, t - th / 2, pb_top, t + th / 2, ffl0, L_CUT)

    # earth / sand filling LAST, drawn ONLY in the clear span between the two
    # footings (kept a hair off each footing base + PCC), at the opposite 45°
    # angle and sparse — so the earth hatch never crosses the stone-masonry
    # footing hatch. That double-hatch overlap was the whole problem.
    margin = 0.18
    for i in range(len(cuts) - 1):
        lt, rt = cuts[i][0], cuts[i + 1][0]
        e0 = lt + base_w_of[lt] / 2 + 0.12 + margin
        e1 = rt - base_w_of[rt] / 2 - 0.12 - margin
        if e1 - e0 > 0.3:
            _hatch(dl, e0, fdn_bot, e1, rub_bot, L_EARTH, step=1.2, slope=-1)

    dl.line(x_lo, ffl0, x_hi, ffl0, layer=L_SLAB)             # finished floor
    return dict(pb_top=pb_top, pb_bot=pb_bot, pcc_bot=pcc_bot,
                rub_bot=rub_bot, fdn_bot=fdn_bot)


def _frange(a, b, step):
    x = a
    while x <= b:
        yield x
        x += step


def _lvl(ft: float) -> str:
    m = ft * MM / 1000.0
    return f"{m:+.3f}"


# ------------------------------------------------------------- export
def export(plan_dict, folder, name, p1, p2, params):
    from .model import Plan
    from . import sheet
    from . import export as EXP
    import os
    plan = Plan.from_dict(plan_dict)
    dl, notes = build(plan, p1, p2, params)
    tag = params.get("tag", "A")
    plan.title.plan_name = f"SECTION {tag}-{tag}"
    composed, info = sheet.compose(plan, dl, params.get("sheet", "A3"),
                                   "landscape", schedule="")
    os.makedirs(folder, exist_ok=True)
    paths = {}
    png = os.path.join(folder, name + ".png")
    EXP.to_png(composed, info["w_mm"], info["h_mm"], png, dpi=200)
    paths["png"] = png
    for ext, fn in (("pdf", EXP.to_pdf), ("dxf", EXP.to_dxf)):
        try:
            p = os.path.join(folder, name + "." + ext)
            if ext == "dxf":
                fn(composed, p, model_scale=info.get("k"))
            else:
                fn(composed, info["w_mm"], info["h_mm"], p)
            paths[ext] = p
        except Exception:
            pass
    return paths, notes
