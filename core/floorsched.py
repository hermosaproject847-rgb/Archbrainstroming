"""Sheet 5 — the flooring schedules (master prompt SECTION 11 / 15):
FLOORING LEGEND with quantities, SETTING-OUT table, SKIRTING schedule with
deductions, LEVEL & DROP schedule, and the notes.

Every number comes from the same specs the drawing is built from, so a change
in the table re-totals here too.
"""

from __future__ import annotations

from collections import defaultdict

from shapely.geometry import box

from . import engine
from . import electrical as E
from . import flooring as F
from .draw import DrawList, LINE_SP, fit_cell

RH = 5.6
FT_MM = 304.8

LGCOLS = [("CODE", 16), ("MATERIAL", 34), ("SIZE mm", 22), ("FINISH", 22),
          ("JOINT", 14), ("SLIP", 12), ("NET m2", 18), ("WASTE", 14),
          ("GROSS m2", 18), ("NOS", 12)]
SCOLS = [("ROOM", 34), ("AXIS", 14), ("CLEAR mm", 22), ("TILE", 20),
         ("JOINT", 14), ("FULL", 12), ("CUT each end mm", 30), ("START", 24)]
KCOLS = [("ROOM", 40), ("PERIMETER m", 26), ("DEDUCT m", 24),
         ("NET Rm", 20), ("HT mm", 16), ("NET m2", 20)]
VCOLS = [("ROOM", 40), ("FFL DROP", 24), ("SLOPE", 20), ("SKIRTING", 34)]


def _clear(plan, room):
    b = box(room.x, room.y, room.x + room.w, room.y + room.h)
    solid = engine.wall_solid(plan)
    c = b.difference(solid) if not solid.is_empty else b
    if c.geom_type == "MultiPolygon":
        c = max(c.geoms, key=lambda g: g.area)
    return c


def _room_at(plan, x, y):
    best, bd = None, 1e18
    for r in plan.rooms:
        if r.void:
            continue
        dx = max(r.x - x, 0, x - (r.x + r.w))
        dy = max(r.y - y, 0, y - (r.y + r.h))
        d = dx * dx + dy * dy
        if d < bd:
            best, bd = r, d
    return best


def _area_sqm(plan, s):
    room = _room_at(plan, s.rx, s.ry)
    if room is None:
        return 0.0
    c = _clear(plan, room)
    return 0.0 if c.is_empty else c.area * 0.3048 * 0.3048


def legend_rows(plan) -> list[list[str]]:
    """One row per legend code, with net/gross area and tile count."""
    groups = defaultdict(lambda: {"net": 0.0, "rooms": 0, "s": None})
    for s in plan.flooring:
        g = groups[s.code]
        g["net"] += _area_sqm(plan, s)
        g["rooms"] += 1
        g["s"] = s
    out = []
    for code, g in sorted(groups.items()):
        s = g["s"]
        m = F.MATERIALS[s.material]
        w = F.wastage_for(s.material, g["net"])
        gross = g["net"] * (1 + w)
        tile_m2 = (s.tile_w * s.tile_h) / 1e6 or 1e-6
        nos = int(gross / tile_m2 + 0.999)
        out.append([code, m["label"], f"{s.tile_w:g}x{s.tile_h:g}", s.finish,
                    f"{s.spacer_mm:g} mm", m["slip"], f"{g['net']:.1f}",
                    f"{w * 100:.0f}%", f"{gross:.1f}", str(nos)])
    return out


def setout_rows(plan) -> list[list[str]]:
    out = []
    for s in plan.flooring:
        room = _room_at(plan, s.rx, s.ry)
        if room is None:
            continue
        c = _clear(plan, room)
        if c.is_empty:
            continue
        x0, y0, x1, y1 = c.bounds
        ax = F.cut_pieces(x1 - x0, s.tile_w, s.spacer_mm)
        ay = F.cut_pieces(y1 - y0, s.tile_h, s.spacer_mm)
        out.append([s.room, "X", f"{ax['Lc_mm']:.0f}", f"{s.tile_w:g}",
                    f"{s.spacer_mm:g}", str(ax["full"]),
                    f"{ax['cut_mm']:.0f}", s.start])
        out.append(["", "Y", f"{ay['Lc_mm']:.0f}", f"{s.tile_h:g}",
                    f"{s.spacer_mm:g}", str(ay["full"]),
                    f"{ay['cut_mm']:.0f}", ""])
    return out


def skirting_rows(plan) -> list[list[str]]:
    """SECTION 10.2 — perimeter less door openings, per room."""
    out = []
    for s in plan.flooring:
        if s.skirting_mm <= 0:
            continue
        room = _room_at(plan, s.rx, s.ry)
        if room is None:
            continue
        c = _clear(plan, room)
        if c.is_empty:
            continue
        x0, y0, x1, y1 = c.bounds
        perim = 2 * ((x1 - x0) + (y1 - y0)) * 0.3048
        # deduct every door opening that touches this room
        ded = 0.0
        for o in plan.openings:
            if not o.is_door:
                continue
            w = plan.wall(o.wall_id)
            if w is None:
                continue
            pt = w.point_at(o.pos + o.width / 2)
            if (x0 - 0.6 <= pt[0] <= x1 + 0.6
                    and y0 - 0.6 <= pt[1] <= y1 + 0.6):
                ded += o.width * 0.3048
        net = max(0.0, perim - ded)
        out.append([s.room, f"{perim:.2f}", f"{ded:.2f}", f"{net:.2f}",
                    f"{s.skirting_mm:g}", f"{net * s.skirting_mm / 1000:.2f}"])
    return out


def level_rows(plan) -> list[list[str]]:
    out = []
    for s in plan.flooring:
        room = _room_at(plan, s.rx, s.ry)
        cat = E.classify(room.name) if room else "dry"
        drop = "+/-0.000" if abs(s.drop_mm) < 1e-6 else f"{s.drop_mm:+.0f} mm"
        slope = F.SLOPES.get(cat, "level")
        sk = (f"{s.skirting_mm:g} mm {s.skirting_type}"
              if s.skirting_mm > 0 else "full-height dado")
        out.append([s.room, drop, slope, sk])
    return out


def height_for(plan) -> float:
    blocks = [legend_rows(plan), setout_rows(plan), skirting_rows(plan),
              level_rows(plan)]
    return (10 + 32 + sum(14 + RH * (len(b) + 1) for b in blocks)
            + 12 + 5.5 + 5.0 * 6 + 26)


def _table(dl, data, cols, x, top, title, sub=""):
    total = sum(c[1] for c in cols)
    dl.text(x, top + 2, title, h=3.2, layer="TITLE", halign="left", bold=True)
    if sub:
        dl.text(x, top - 2.6, sub, h=2.0, layer="TEXT-SUB", halign="left")
    y = top - (7 if sub else 4)
    n = len(data)
    dl.rect(x, y - RH * (n + 1), total, RH * (n + 1), layer="TITLE")
    cx = x
    for _nm, cw in cols[:-1]:
        cx += cw
        dl.line(cx, y - RH * (n + 1), cx, y, layer="TITLE")

    def put(vals, yy, bold=False):
        cxx = x
        for v, (_n, cw) in zip(vals, cols):
            lines, hh = fit_cell(v, cw - 3, 2.3, 2)
            step = hh * LINE_SP
            top_ = yy - RH * 0.5 + (len(lines) - 1) * step / 2
            for li, ln in enumerate(lines):
                dl.text(cxx + 1.5, top_ - li * step, ln, h=hh,
                        layer="TITLE" if bold else "TEXT-SUB",
                        halign="left", bold=bold)
            cxx += cw

    put([c[0] for c in cols], y, bold=True)
    dl.line(x, y - RH, x + total, y - RH, layer="TITLE")
    for i, r in enumerate(data, start=1):
        put(r, y - RH * i)
    return y - RH * (n + 1)


def build(plan, w_mm: float, h_mm: float) -> DrawList:
    dl = DrawList()
    m = 10.0
    dl.rect(m / 2, m / 2, w_mm - m, h_mm - m, layer="TITLE")
    dl.rect(m, m, w_mm - 2 * m, h_mm - 2 * m, layer="TITLE")
    t = plan.title
    dl.text(m + 4, h_mm - m - 8, (t.project or "PROJECT").upper(), h=5.0,
            layer="TITLE", halign="left", bold=True)
    dl.text(m + 4, h_mm - m - 16, "FLOORING DESIGN & SETTING-OUT  —  SHEET 5",
            h=3.6, layer="TITLE", halign="left", bold=True)
    dl.text(m + 4, h_mm - m - 23,
            "NBC 2016 + IS 15622 / 1130 / 1200(11). START POINT HATCHED; "
            "SPACERS SHOWN; DIMENSIONS mm, LEVELS m.", h=2.4,
            layer="TEXT-SUB", halign="left")

    x = m + 4
    y = _table(dl, legend_rows(plan), LGCOLS, x, h_mm - m - 32,
               "FLOORING LEGEND", "material, area, wastage and tile count")
    y = _table(dl, setout_rows(plan), SCOLS, x, y - 14,
               "SETTING-OUT", "full tiles and the equal cut piece each end")
    y = _table(dl, skirting_rows(plan), KCOLS, x, y - 14,
               "SKIRTING SCHEDULE", "perimeter less door openings (IS 1200-11)")
    y = _table(dl, level_rows(plan), VCOLS, x, y - 14,
               "LEVEL, DROP & SKIRTING", "finished level and slope per room")

    yy = y - 12
    dl.text(x, yy, "NOTES", h=3.0, layer="TITLE", halign="left", bold=True)
    yy -= 5.5
    for line in _NOTES:
        dl.text(x, yy, line, h=2.2, layer="TEXT-SUB", halign="left")
        yy -= 5.0
    return dl


_NOTES = [
    "Start point marked and hatched; lay from the two chalk datum lines, "
    "dry-lay one row per axis before bedding.",
    "Equal cut pieces at both aligned ends unless the entry-sightline or "
    "feature rule governs (SECTION 4).",
    "Perimeter joint 5 mm at all walls, concealed behind skirting; movement "
    "joint every 20-25 sq.m internal, 3-4 m external.",
    "Wet areas: anti-skid, epoxy grout, floor sloped to the trap, full-height "
    "dado in place of skirting.",
    "Wooden flooring: 10-12 mm expansion gap at all perimeters, 1/3 stagger; "
    "prohibited in toilets, balcony and utility.",
    "Verify shade/lot per space before laying; confirm sunk depth for wet-area "
    "drops (NBC Part 9).",
]
