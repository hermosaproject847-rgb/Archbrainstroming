"""Sheet 4 — the plumbing panels (deliverables D7, D8, D9 of the master
prompt): KEY NOTES, FIXTURE SCHEDULE, CHAMBER SCHEDULE, CALCULATION SHEET,
BOQ SUMMARY, LEGEND and NOTES.

The plan itself carries only numbered circles and the slope text along each
run; everything else is here. The legend samples are drawn in the same colours
and line styles the plan uses.
"""

from __future__ import annotations

from collections import defaultdict

from . import plumbing as P
from .draw import DrawList, LINE_SP, fit_cell

RH = 5.6

KCOLS = [("No.", 12), ("FITTING / SERVICE", 124)]
FCOLS = [("FIXTURE / FITTING", 62), ("HEIGHT FROM FFL", 34),
         ("POSITION / REMARKS", 74)]
CCOLS = [("CHAMBER", 22), ("SIZE mm", 26), ("COVER LEVEL", 28),
         ("INVERT LEVEL", 28), ("DEPTH", 22)]
QCOLS = [("ITEM", 74), ("SPECIFICATION", 60), ("QTY", 24)]
LGCOLS = [("SYMBOL", 22), ("SYSTEM", 40), ("MATERIAL / SIZE", 74)]


def _total(cols):
    return sum(c[1] for c in cols)


# --------------------------------------------------------------- the rows
def key_rows(plan) -> list[list[str]]:
    out = []
    for q in sorted(plan.plumb, key=lambda q: q.key):
        if not q.key:
            continue
        txt = q.note or P.KEYNOTES.get(q.code, q.code)
        if q.tag and q.code in ("SS", "WS", "VP", "RWP", "CWD", "HWD", "IC",
                                "KH", "CO", "GBC"):
            txt = f"{q.tag} — {txt}"
        if q.room:
            txt = f"{txt} ({q.room})"
        out.append([str(q.key), txt])
    return out


def fixture_rows(plan) -> list[list[str]]:
    """§4 — every fitting used on this plan, with its mounting height."""
    used = {q.code for q in plan.plumb}
    order = ["BASIN", "PC", "BAC", "BBT", "WCAC", "HF", "SH", "SMX", "SAR",
             "GY", "SINK", "SKC", "WMT", "GBC", "NT", "GT", "SV"]
    out = []
    for c in order:
        if c not in used and c not in ("BASIN", "SINK", "PC", "SAR"):
            continue
        name, h, remark = P.FIXTURES[c]
        out.append([name, f"{h:g} mm" if h else "—", remark])
    return out


def chamber_rows(plan) -> list[list[str]]:
    out = []
    ics = [q for q in plan.plumb if q.code == "IC"]
    for c in sorted(ics, key=lambda q: int((q.tag or "IC-0").split("-")[-1]
                                           or 0)):
        depth = (c.cover_m - c.invert_m) * 1000
        out.append([c.tag or "IC", P.chamber_size(depth),
                    f"{c.cover_m:+.3f} m", f"{c.invert_m:+.3f} m",
                    f"{depth:.0f} mm"])
    return out


def calc_rows(plan) -> list[list[str]]:
    """§3 and §7 — the working, not just the answer."""
    c = getattr(plan, "plumb_calc", None) or {}
    if not c:
        return []
    d, t, pm = c.get("demand", {}), c.get("tanks", {}), c.get("pump", {})
    rw = c.get("rwp", {})
    out = [
        ["Occupants (standard bungalow)", "assumed",
         f"{d.get('occupants', 0)} persons"],
        ["Domestic demand", f"{P.LPCD_DOMESTIC} lpcd",
         f"{d.get('domestic_l', 0):.0f} L/day"],
        ["Flushing demand", f"{P.LPCD_FLUSHING} lpcd",
         f"{d.get('flushing_l', 0):.0f} L/day"],
        ["Garden / irrigation",
         f"{d.get('garden_sqm', 0):.0f} sq.m x {P.GARDEN_L_PER_SQM:g} L",
         f"{d.get('garden_l', 0):.0f} L/day"],
        ["TOTAL DAILY DEMAND", f"{P.LPCD_TOTAL} lpcd + garden",
         f"{d.get('total_l', 0):.0f} L/day"],
    ]
    if t:
        ug, oh = t.get("ug_dims", (0, 0, 0)), t.get("oht_dims", (0, 0, 0))
        out += [
            ["UG tank", f"{t.get('days')} days of total demand",
             f"{t.get('ug_l', 0):.0f} L — {ug[0]}x{ug[1]}x{ug[2]} m"],
            ["Overhead tank", "1 day domestic + flushing",
             f"{t.get('oht_l', 0):.0f} L — {oh[0]}x{oh[1]}x{oh[2]} m"],
            ["Freeboard", "NBC", f"{P.FREEBOARD_MM} mm on both tanks"],
        ]
    if pm:
        out += [
            ["Pump flow",
             f"OHT filled in {pm.get('fill_hours')} h",
             f"{pm.get('q_lpm', 0):.0f} LPM"],
            ["Pump head",
             f"lift {c.get('lift_m', 0):g} m + "
             f"{P.PUMP_FRICTION_PC * 100:.0f}% friction + "
             f"{P.PUMP_RESIDUAL_HEAD_M:g} m residual",
             f"{pm.get('head_m', 0):.0f} m"],
            ["Pump rating", "duty above", f"{pm.get('hp')} HP"],
        ]
    if rw:
        out += [["Rain-water pipes",
                 f"{rw.get('roof_sqm', 0):.0f} sq.m roof at "
                 f"{rw.get('intensity')} mm/hr, one per "
                 f"{rw.get('per_rwp_sqm', 0):.0f} sq.m",
                 f"{rw.get('count', 0)} nos {P.D_RWP}Ø"]]
    return out


def boq_rows(plan) -> list[list[str]]:
    """D9 — pipe lengths measured off the runs, fittings counted."""
    by_sys = defaultdict(float)
    for r in plan.pipes:
        by_sys[(r.system, r.dia_mm)] += r.length_ft * 0.3048
    out = []
    for (sys, dia), m in sorted(by_sys.items()):
        label, _layer, spec, _st = P.SYSTEMS.get(sys, (sys, "", "", ""))
        out.append([f"{label} pipe {dia:g}Ø", spec, f"{m:.1f} m"])
    counts = defaultdict(int)
    for q in plan.plumb:
        counts[q.code] += 1
    for code in ("NT", "GT", "IC", "CO", "KH", "BAC", "BBT", "WCAC", "HF",
                 "SMX", "SH", "SKC", "WMT", "GBC", "SV", "GY", "UGT", "OHT",
                 "PUMP"):
        if counts.get(code):
            name, h, _rm = P.FIXTURES.get(code, (code, 0, ""))
            out.append([name, f"{h:g} mm AFL" if h else "—",
                        f"{counts[code]} nos"])
    return out


def legend_rows(plan) -> list:
    used = {r.system for r in plan.pipes}
    return [c for c in ("CW", "HW", "SOIL", "WASTE", "VENT", "STORM", "ACD")
            if c in used]


# every point code -> (system for its colour, legend name). Drives the SYMBOL
# LEGEND directly, so any fitting on the plan is guaranteed a legend row.
_SYM_NAME = {
    "BAC": ("CW", "Angle cock (hot + cold)"),
    "WCAC": ("CW", "WC 2-way angle cock"),
    "HF": ("CW", "Health faucet"),
    "PC": ("CW", "Pillar cock / basin mixer"),
    "SKC": ("CW", "Sink cock / wall mixer"),
    "SMX": ("HW", "Shower mixer / diverter"),
    "SH": ("HW", "Shower head"),
    "SAR": ("HW", "Shower arm take-off"),
    "GY": ("HW", "Geyser"),
    "GBC": ("CW", "Garden bib cock"),
    "WMT": ("CW", "Washing-machine tap"),
    "SV": ("CW", "Full-way isolation valve"),
    "BBT": ("WASTE", "Bottle trap"),
    "NT": ("WASTE", "Nahani (floor) trap"),
    "GT": ("WASTE", "Gully trap"),
    "IC": ("SOIL", "Inspection chamber"),
    "CO": ("SOIL", "Cleanout plug"),
    "KH": ("STORM", "Khurra (spout)"),
    "SS": ("SOIL", "Soil stack"),
    "WS": ("WASTE", "Waste stack"),
    "VP": ("VENT", "Vent pipe / stack"),
    "RWP": ("STORM", "Rain-water pipe"),
    "CWD": ("CW", "Cold water down-take"),
    "HWD": ("HW", "Hot water down-take"),
    "UGT": ("CW", "Underground water tank"),
    "OHT": ("CW", "Overhead tank"),
    "PUMP": ("CW", "Submersible pump"),
}
# these share one drawn icon — list the first, skip the rest
_SAME_ICON = {"SKC": "PC", "WMT": "GBC", "WS": "SS", "VP": "SS", "RWP": "SS",
              "CWD": "SS", "HWD": "SS", "UGT": "OHT"}


def sym_legend_rows(plan) -> list:
    """Every distinct symbol the plan actually draws — computed from the
    points present, so nothing is ever left out of the legend."""
    from . import plumbsym
    used = {q.code for q in plan.plumb}
    seen_icon = set()
    out = []
    # keep a sensible reading order
    order = ["BAC", "WCAC", "HF", "PC", "SKC", "GBC", "WMT", "SV",
             "SMX", "SH", "SAR", "GY", "BBT", "NT", "GT", "IC", "CO",
             "SS", "WS", "VP", "RWP", "CWD", "HWD", "KH", "UGT", "OHT", "PUMP"]
    for code in order:
        if code not in used or code not in plumbsym._SYM:
            continue
        icon = _SAME_ICON.get(code, code)   # which icon actually gets drawn
        if icon in seen_icon:
            continue                        # its twin is already shown
        seen_icon.add(icon)
        sysid, name = _SYM_NAME.get(code, ("CW", code))
        # icons shared by several tagged items get a combined name
        if icon == "SS":
            name = "Vertical stack (SS/WS/VP/RWP/CWD/HWD by tag)"
            sysid = "SOIL"
        elif icon == "OHT":
            name = "Water tank (overhead / underground)"
        out.append((icon, sysid, name))
    return out


def height_for(plan) -> float:
    blocks = [key_rows(plan), fixture_rows(plan), chamber_rows(plan),
              calc_rows(plan), boq_rows(plan),
              [1] * len(legend_rows(plan)), [1] * len(sym_legend_rows(plan))]
    return (10 + 32 + sum(14 + RH * (len(b) + 1) for b in blocks)
            + 12 + 5.5 + 5.0 * len(P.NOTES_BLOCK) + 30)


def _table(dl: DrawList, data, cols, x, top, title, sub="",
           draw_cell=None) -> float:
    total = _total(cols)
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

    def put(vals, yy, bold=False, skip0=False):
        cxx = x
        for i, (v, (_n, cw)) in enumerate(zip(vals, cols)):
            if skip0 and i == 0:
                cxx += cw
                continue
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
        yy = y - RH * i
        if draw_cell:
            draw_cell(dl, r, x, yy, cols)
        put(list(r), yy, skip0=bool(draw_cell))
    return y - RH * (n + 1)


def build(plan, w_mm: float, h_mm: float) -> DrawList:
    from . import plumbsym, eleclegend

    dl = DrawList()
    m = 10.0
    dl.rect(m / 2, m / 2, w_mm - m, h_mm - m, layer="TITLE")
    dl.rect(m, m, w_mm - 2 * m, h_mm - 2 * m, layer="TITLE")

    t = plan.title
    dl.text(m + 4, h_mm - m - 8, (t.project or "PROJECT").upper(), h=5.0,
            layer="TITLE", halign="left", bold=True)
    dl.text(m + 4, h_mm - m - 16,
            "PLUMBING, SANITARY & DRAINAGE  —  SHEET 4", h=3.6,
            layer="TITLE", halign="left", bold=True)
    dl.text(m + 4, h_mm - m - 23,
            "NBC 2016 PART 9 · IS 1172 · IS 1742 · IS 2065 · CPHEEO. "
            "TWO-PIPE SYSTEM. DIMENSIONS IN mm, LEVELS IN m.", h=2.4,
            layer="TEXT-SUB", halign="left")

    x = m + 4
    y = _table(dl, key_rows(plan), KCOLS, x, h_mm - m - 32, "KEY NOTES",
               "the numbered circles on the plan")
    y = _table(dl, fixture_rows(plan), FCOLS, x, y - 14,
               "FIXTURE SCHEDULE", "mounting heights from FFL (section 4)")
    y = _table(dl, chamber_rows(plan), CCOLS, x, y - 14,
               "CHAMBER SCHEDULE",
               "cover and invert levels computed from the runs and gradients")
    cr = calc_rows(plan)
    if cr:
        y = _table(dl, cr, [("ITEM", 62), ("BASIS", 62), ("VALUE", 46)],
                   x, y - 14, "CALCULATION SHEET",
                   "demand, tank sizing, pump duty and rain-water pipes")
    y = _table(dl, boq_rows(plan), QCOLS, x, y - 14, "BOQ SUMMARY",
               "pipe lengths measured off the runs; fittings counted")

    def sample(dl_, row, x0, yy, cols):
        code = row[0]
        _lbl, layer, _spec, _style = P.SYSTEMS[code]
        dl_.poly([(x0 + 3, yy - RH * 0.5), (x0 + cols[0][1] - 3,
                                            yy - RH * 0.5)],
                 layer=layer, closed=False, dashed=plumbsym.dashed_for(code))

    lg = [(c, P.SYSTEMS[c][0], P.SYSTEMS[c][2]) for c in legend_rows(plan)]
    y = _table(dl, lg, LGCOLS, x, y - 14, "PIPE LEGEND",
               "each system in the colour and line it carries on the plan",
               draw_cell=sample)

    # the SYMBOL legend — each fitting icon drawn and named, so the numbered
    # circles on the plan can be decoded
    syms = sym_legend_rows(plan)

    sys_of = {c: s for c, s, _n in syms}

    def draw_sym(dl_, row, x0, yy, cols):
        from .draw import DrawList
        code = row[0]
        cell = DrawList()
        fn = plumbsym._SYM.get(code)
        if fn:
            try:
                fn(cell, 0.0, 0.0, plumbsym.layer_of(sys_of.get(code, "CW")))
            except Exception:
                pass
        eleclegend._place(dl_, cell, x0 + cols[0][1] / 2, yy - RH / 2, 3.0)

    # the table shows [icon | name]; col0 (the code) is drawn as the icon
    y = _table(dl, [(c, n) for c, _s, n in syms],
               [("SYMBOL", 22), ("FITTING", 114)], x, y - 14,
               "SYMBOL LEGEND", "what each icon on the plan means",
               draw_cell=draw_sym)

    yy = y - 12
    dl.text(x, yy, "NOTES", h=3.0, layer="TITLE", halign="left", bold=True)
    yy -= 5.5
    for line in P.NOTES_BLOCK:
        dl.text(x, yy, line, h=2.2, layer="TEXT-SUB", halign="left")
        yy -= 5.0
    return dl
