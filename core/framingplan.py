"""Structural FRAMING PLANS — the plinth-beam framing plan and the roof/floor
beam-&-slab framing plan, drawn like the reference tender sheets: beams tagged
with size over the walls, grid dimensions, a beam reinforcement cross-section,
slab panels with depth + slab reinforcement (roof only), and a NOTES block.

Reinforcement / grades are STANDARD DEFAULTS (see STRUCT) and can be overridden
by passing a `struct` dict (the plan carries `struct` once the user edits it).
"""

from __future__ import annotations

import math

from .draw import Arc, DrawList

MM = 304.8

# standard defaults — editable through the Structural dialog / plan["struct"].
# The values follow real GFC structural sets (Orilite / KU-KE, IS 456-2000):
# cover Col 1½" · Beam 1" · Slab 0.75" · Footing 2", M-25 / Fe-550, LL 2.5 kN/m².
STRUCT = {
    "beam_top": "2#10", "beam_bot": "2#10", "stirrup": '#8@8"C/C',
    "cover_beam": '1"', "cover_col": '1½"', "cover_slab": '0.75"',
    "cover_ftg": '2"', "slab_depth": '5"', "slab_main": '8MM@5"C/C',
    "slab_dist": '8MM@8"C/C', "conc": "M-25", "steel": "FE-550",
    "live_load": "2.5 kN/sqm", "pcc": '4" THK P.C.C. 1:3:6',
}

# stirrup / ring zoning used on every beam-detail sheet (R-codes on the beam
# elevation point to this table): dense near supports, wider at mid-span.
RING_DETAILS = [
    ("R1", '8MM @ 4" C/C'), ("R2", '8MM @ 8" C/C'), ("R3", '8MM @ 6" C/C'),
    ("R4", '10MM @ 4" C/C'), ("R5", '10MM @ 8" C/C'), ("R6", '10MM @ 6" C/C'),
]


def ring_table(dl, x, y, layer="BEAM-TAG"):
    """Draw the standard RING DETAILS table (R1–R6) at (x, y) top-left."""
    rh, w1, w2 = 0.75, 2.2, 4.6
    dl.text(x, y + 0.9, "RING DETAILS", h=0.42, layer=layer,
            halign="left", bold=True)
    n = len(RING_DETAILS)
    for i in range(n + 1):
        yy = y - i * rh
        dl.line(x, yy, x + w1 + w2, yy, layer=layer)
    for xx in (x, x + w1, x + w1 + w2):
        dl.line(xx, y, xx, y - n * rh, layer=layer)
    for i, (tag, spec) in enumerate(RING_DETAILS):
        yc = y - i * rh - rh / 2
        dl.text(x + w1 / 2, yc, tag, h=0.34, layer=layer, bold=True)
        dl.text(x + w1 + 0.25, yc, spec, h=0.34, layer=layer, halign="left")


def _s(struct, k):
    return (struct or {}).get(k, STRUCT[k])


def build(plan, kind="plinth", struct=None):
    """kind = 'plinth' or 'roof'. Returns a DrawList."""
    from . import engine
    dl = DrawList()
    prefix = "PB" if kind == "plinth" else "B"

    # walls hatched light as masonry, then the beams as the framing
    _hatch_walls(dl, plan)
    wdl = DrawList()
    engine.draw_walls(plan, wdl)
    for it in wdl.items:
        if hasattr(it, "layer"):
            it.layer = "BEAM-WALL"
    dl.extend(wdl)
    engine.draw_beams(plan, dl, prefix=prefix, inch=True)

    beams = [b for b in (getattr(plan, "beams", None) or [])
             if math.hypot(b.x2 - b.x1, b.y2 - b.y1) > 1e-6]
    # building extent from the WALLS (not the annotated bounds) for the dims
    xs = [w.x1 for w in plan.walls] + [w.x2 for w in plan.walls]
    ys = [w.y1 for w in plan.walls] + [w.y2 for w in plan.walls]
    wx0, wy0, wx1, wy1 = min(xs), min(ys), max(xs), max(ys)

    # ---- grid dimensions on ALL FOUR sides + an overall run each way ------
    vxs = sorted({round((bm.x1 + bm.x2) / 2, 2) for bm in beams
                  if abs(bm.x1 - bm.x2) < abs(bm.y1 - bm.y2)})
    hys = sorted({round((bm.y1 + bm.y2) / 2, 2) for bm in beams
                  if abs(bm.y1 - bm.y2) < abs(bm.x1 - bm.x2)})
    vxs = _with_faces(vxs, wx0, wx1)
    hys = _with_faces(hys, wy0, wy1)
    _hchain(dl, vxs, wy1 + 1.6, up=True)                     # top
    _hchain(dl, vxs, wy0 - 1.6, up=False)                    # bottom
    _vchain(dl, hys, wx0 - 1.6, left=True)                   # left
    _vchain(dl, hys, wx1 + 1.6, left=False)                  # right
    # overall runs, one tier out
    _overall_h(dl, wx0, wx1, wy1 + 3.4)
    _overall_v(dl, wy0, wy1, wx0 - 3.4)

    # ---- section mark A-A across the plan (mid height) --------------------
    _section_mark(dl, wx0, wx1, (wy0 + wy1) / 2)

    # ---- roof: SUNK wet panels (grouped hatch) then slab panels S1,S2… ----
    has_sunk = False
    if kind == "roof":
        has_sunk = _sunk_slabs(dl, plan) > 0     # hatch first, labels on top
        _slab_panels(dl, plan, struct)

    # ---- LEGEND to the right of the plan (clear of the grid dims) ---------
    _legend(dl, wx1 + 5.0, wy1 - 1.0, has_sunk)

    # ---- beam reinforcement cross-section (bottom-left) ------------------
    _beam_xsection(dl, wx0, wy0 - 5.0, struct, prefix, beams)

    # ---- notes block (bottom-centre of the plan) -------------------------
    _notes(dl, (wx0 + wx1) / 2 + 1.0, wy0 - 5.0, struct)
    # ---- RING DETAILS table (left column, below the beam cross-section) ---
    ring_table(dl, wx0, wy0 - 9.5)
    return dl


def _with_faces(vals, lo, hi):
    """Add the two building faces to a grid-line list so the end bays are
    dimensioned too (deduped, sorted)."""
    out = set(round(v, 2) for v in vals)
    out.add(round(lo, 2))
    out.add(round(hi, 2))
    return sorted(out)


def _hatch_walls(dl, plan):
    """A light 45° masonry hatch inside every wall so the framing reads over a
    proper wall, like the reference tender sheet."""
    from . import section as S
    for w in plan.walls:
        if getattr(w, "railing", False):
            continue
        th = w.thickness_in / 12.0
        if abs(w.x1 - w.x2) < abs(w.y1 - w.y2):             # vertical wall
            cx = (w.x1 + w.x2) / 2
            y0, y1 = sorted((w.y1, w.y2))
            S._hatch(dl, cx - th / 2, y0, cx + th / 2, y1, "BEAM-WALL",
                     step=0.35)
        else:                                               # horizontal wall
            cy = (w.y1 + w.y2) / 2
            x0, x1 = sorted((w.x1, w.x2))
            S._hatch(dl, x0, cy - th / 2, x1, cy + th / 2, "BEAM-WALL",
                     step=0.35)


def _hchain(dl, xs, y, up=True):
    if len(xs) < 2:
        return
    ext = -1.4 if up else 1.4            # witness lines point at the plan
    toff = 0.35 if up else -0.55
    dl.line(xs[0], y, xs[-1], y, layer="BEAM-TAG")
    for x in xs:
        dl.line(x, y - 0.25, x, y + 0.25, layer="BEAM-TAG")
        dl.line(x, y, x, y + ext, layer="BEAM-TAG")
    for a, b in zip(xs, xs[1:]):
        if b - a > 0.05:
            dl.text((a + b) / 2, y + toff, _ftin(b - a), h=0.34,
                    layer="BEAM-TAG")


def _vchain(dl, ys, x, left=True):
    if len(ys) < 2:
        return
    ext = 1.4 if left else -1.4
    toff = -0.35 if left else 0.35
    dl.line(x, ys[0], x, ys[-1], layer="BEAM-TAG")
    for y in ys:
        dl.line(x - 0.25, y, x + 0.25, y, layer="BEAM-TAG")
        dl.line(x, y, x + ext, y, layer="BEAM-TAG")
    for a, b in zip(ys, ys[1:]):
        if b - a > 0.05:
            dl.text(x + toff, (a + b) / 2, _ftin(b - a), h=0.34,
                    layer="BEAM-TAG", angle=90,
                    halign="center", valign="bottom" if left else "top")


def _overall_h(dl, x0, x1, y):
    dl.line(x0, y, x1, y, layer="BEAM-TAG")
    for x in (x0, x1):
        dl.line(x, y - 0.3, x, y + 0.3, layer="BEAM-TAG")
    dl.text((x0 + x1) / 2, y + 0.4, _ftin(x1 - x0), h=0.4, layer="BEAM-TAG",
            bold=True)


def _overall_v(dl, y0, y1, x):
    dl.line(x, y0, x, y1, layer="BEAM-TAG")
    for y in (y0, y1):
        dl.line(x - 0.3, y, x + 0.3, y, layer="BEAM-TAG")
    dl.text(x - 0.4, (y0 + y1) / 2, _ftin(y1 - y0), h=0.4, layer="BEAM-TAG",
            bold=True, angle=90)


def _section_mark(dl, x0, x1, y):
    """An A-A section line straight across the plan with arrow bubbles each
    end, like the reference framing sheet."""
    dl.line(x0 - 1.4, y, x1 + 1.4, y, layer="SEC-LINE", dashed=True)
    for xe, dx in ((x0 - 1.4, 1), (x1 + 1.4, -1)):
        dl.items.append(Arc(xe, y, 0.5, 0, 360, "SEC-LINE"))
        dl.text(xe, y, "A", h=0.4, layer="SEC-LINE", bold=True)
        # little direction arrow
        dl.line(xe + dx * 0.5, y, xe + dx * 1.1, y, layer="SEC-LINE")
        dl.line(xe + dx * 1.1, y, xe + dx * 0.85, y + 0.18, layer="SEC-LINE")
        dl.line(xe + dx * 1.1, y, xe + dx * 0.85, y - 0.18, layer="SEC-LINE")


def _slab_panels(dl, plan, struct):
    d = _s(struct, "slab_depth")
    for i, r in enumerate([r for r in plan.rooms
                           if not getattr(r, "is_lawn", False)
                           and not getattr(r, "open_area", False)], start=1):
        cx, cy = r.x + r.w / 2, r.y + r.h / 2
        dl.items.append(Arc(cx, cy + 0.7, 0.5, 0, 360, "BEAM-TAG"))
        dl.text(cx, cy + 0.7, f"S{i}", h=0.4, layer="BEAM-TAG", bold=True)
        dl.rect(cx - 0.9, cy - 0.55, 1.8, 0.7, layer="BEAM-TAG")
        dl.text(cx, cy - 0.2, f"D={d}", h=0.34, layer="BEAM-TAG")
    # one representative reinforcement callout
    if plan.rooms:
        r = plan.rooms[0]
        cx, cy = r.x + r.w / 2, r.y + r.h / 2
        dl.text(cx - 2.0, cy - 2.0, f"MAIN {_s(struct,'slab_main')}", h=0.3,
                layer="BEAM-TAG", halign="left")
        dl.text(cx - 2.0, cy - 2.5, f"DIST {_s(struct,'slab_dist')}", h=0.3,
                layer="BEAM-TAG", halign="left")
    # TOP / BOTTOM reinforcement legend
    lx, ly = plan.rooms and 0 or 0, 0


def _sunk_slabs(dl, plan):
    """Cross-hatch every WET-area slab panel (toilet / bath / wash / balcony) as
    SUNK 1.5". Uses ONE grouped HATCH per panel (a real cross-hatch), never
    loose line-by-line geometry."""
    wet = ("toilet", "bath", "w.c", "wc", "washroom", "wash", "balcony",
           "terrace", "utility", "dry")
    n = 0
    for r in plan.rooms:
        if getattr(r, "open_area", False) or getattr(r, "is_lawn", False):
            continue
        if not any(w in (r.name or "").lower() for w in wet):
            continue
        x0, y0 = r.x + 0.12, r.y + 0.12
        x1, y1 = r.x + r.w - 0.12, r.y + r.h - 0.12
        if x1 - x0 < 0.6 or y1 - y0 < 0.6:
            continue
        dl.hatch([[(x0, y0), (x1, y0), (x1, y1), (x0, y1)]],
                 kind="cross", step=0.4, layer="FLR-START")
        dl.text((x0 + x1) / 2, y0 + 0.3, 'SUNK 1.5"', h=0.28,
                layer="SEC-LINE", bold=True)
        n += 1
    return n


def _legend(dl, x, y, has_sunk):
    """A small key box to the RIGHT of the plan (clear of the grid dimensions)
    for the sunk-slab and sleeve symbols."""
    dl.text(x, y + 0.9, "LEGEND", h=0.42, layer="BEAM-TAG", halign="left",
            bold=True)
    row = y
    if has_sunk:
        dl.rect(x, row - 0.5, 1.3, 1.0, layer="BEAM-TAG")
        dl.hatch([[(x, row - 0.5), (x + 1.3, row - 0.5),
                   (x + 1.3, row + 0.5), (x, row + 0.5)]],
                 kind="cross", step=0.3, layer="FLR-START")
        dl.text(x + 1.6, row, 'SUNK 1.5"', h=0.32, layer="BEAM-TAG",
                halign="left")
        row -= 1.5
    # sleeve symbols
    dl.rect(x, row - 0.35, 0.7, 0.7, layer="BEAM-TAG")
    dl.line(x, row - 0.35, x + 0.7, row + 0.35, layer="BEAM-TAG")
    dl.line(x, row + 0.35, x + 0.7, row - 0.35, layer="BEAM-TAG")
    dl.text(x + 1.0, row, 'SLEEVE 6"Ø FOR 4" PIPE', h=0.3, layer="BEAM-TAG",
            halign="left")
    row -= 1.1
    dl.items.append(Arc(x + 0.35, row, 0.32, 0, 360, "SEC-LINE"))
    dl.text(x + 1.0, row, 'SLEEVE 4"Ø FOR 3" PIPE', h=0.3, layer="SEC-LINE",
            halign="left")


def _beam_xsection(dl, x, y, struct, prefix, beams):
    """A beam section: square with 4 corner bars, stirrup, and callouts."""
    w = 1.6
    top = y
    dl.rect(x, top - w, w, w, layer="BEAM")                 # concrete outline
    dl.rect(x + 0.18, top - w + 0.18, w - 0.36, w - 0.36, layer="BEAM-TAG")  # stirrup
    for cx in (x + 0.28, x + w - 0.28):                     # 4 corner bars
        for cy in (top - 0.28, top - w + 0.28):
            dl.items.append(Arc(cx, cy, 0.07, 0, 360, "FLR-START"))
    dl.line(x + 0.4, top + 0.1, x + 0.9, top + 0.7, layer="BEAM-TAG")
    dl.text(x + 1.0, top + 0.7, _s(struct, "beam_top"), h=0.3, layer="BEAM-TAG",
            halign="left")
    dl.line(x + w, top - w / 2, x + w + 0.6, top - w / 2, layer="BEAM-TAG")
    dl.text(x + w + 0.7, top - w / 2, _s(struct, "stirrup"), h=0.3,
            layer="BEAM-TAG", halign="left")
    dl.line(x + 0.4, top - w - 0.1, x + 0.9, top - w - 0.7, layer="BEAM-TAG")
    dl.text(x + 1.0, top - w - 0.7, _s(struct, "beam_bot"), h=0.3,
            layer="BEAM-TAG", halign="left")
    sz = ""
    if beams:
        sz = f' ({round(beams[0].width_mm / 25.4)}"X{round(beams[0].depth_mm / 25.4)}")'
    dl.text(x + w / 2, top - w - 1.1, f"{prefix}-1{sz}", h=0.36,
            layer="BEAM-TAG", bold=True)


def _notes(dl, x, y, struct):
    # the standard GFC structural-notes block, matching a real IS 456-2000 set
    lines = [
        "NOTES:",
        f"1- Clear cover for Column {_s(struct,'cover_col')}, Beam "
        f"{_s(struct,'cover_beam')}, Slab {_s(struct,'cover_slab')}, "
        f"Footing {_s(struct,'cover_ftg')}.",
        f"2- Grade of Concrete {_s(struct,'conc')}.",
        f"3- Grade of Steel {_s(struct,'steel')}.",
        "4- For Analysis & design of Building following parameters as per",
        f"   IS Code. Live Load {_s(struct,'live_load')}.",
        "5- Refer IS CODE 456-2000 for const. practice.",
        "6- Refer General Drawing for Reinforcement arrangement.",
        "7- Refer MEP Drawing for actual position of Sleeves.",
        "8- Reinf. for Floating Column, Refer Column Schedule.",
        "9- Follow QC parameter Annex. for quality assurance of each",
        "   construction activity.",
    ]
    dl.rect(x - 0.3, y - len(lines) * 0.55 - 0.2, 17, len(lines) * 0.55 + 0.5,
            layer="BEAM-TAG")
    for i, ln in enumerate(lines):
        dl.text(x, y - i * 0.55, ln, h=0.36 if i == 0 else 0.3,
                layer="BEAM-TAG", halign="left", bold=(i == 0))


def _ftin(ft):
    ft = abs(ft)
    f = int(ft)
    inch = round((ft - f) * 12)
    if inch == 12:
        f += 1
        inch = 0
    return f"{f}'-{inch}\"" if inch else f"{f}'"
