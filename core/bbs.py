"""BAR BENDING SCHEDULE for the beam framing.

Computed deterministically from the beam layout and the reinforcement config
(the same STRUCT defaults the framing plans use, overridable through the
Structural dialog / plan['struct']). For each beam it lists the top bars, the
bottom bars and the stirrups with diameter, number, cutting length and weight,
then a diameter-wise summary and the grand total steel weight.

Standard shop conventions used (all editable through the defaults):
  main bar cutting length = c/c length - 2·cover + 2·(anchorage 10·Ø)
  stirrup cutting length  = 2·((b-2c)+(D-2c)) + 2·(hook 10·Ø)
  unit weight             = Ø²/162 kg/m
"""

from __future__ import annotations

import math
import re

from .draw import DrawList
from .framingplan import STRUCT, _s

MM = 304.8


def _bars(spec):
    """'2#10' / '3-12' / '2 # 16' -> (count, dia_mm). Returns (0,0) if blank."""
    if not spec:
        return 0, 0.0
    m = re.findall(r"\d+", str(spec))
    if len(m) >= 2:
        return int(m[0]), float(m[1])
    if len(m) == 1:                       # just a diameter
        return 1, float(m[0])
    return 0, 0.0


def _stirrup(spec):
    """'#8@8\"C/C' -> (dia_mm, spacing_mm); '#8@150' treats 150 as mm."""
    if not spec:
        return 0.0, 0.0
    dia_m = re.search(r"#?\s*(\d+)", str(spec))
    dia = float(dia_m.group(1)) if dia_m else 8.0
    sp_m = re.search(r"@\s*(\d+)\s*(\"|mm|in)?", str(spec))
    if not sp_m:
        return dia, 203.2
    val = float(sp_m.group(1))
    unit = (sp_m.group(2) or "").lower()
    spacing = val * 25.4 if (unit in ('"', "in") or val <= 12) else val
    return dia, spacing


def _in_mm(spec, default_mm):
    """A cover like '1\"' or '25' -> mm."""
    if not spec:
        return default_mm
    m = re.search(r"([\d.]+)", str(spec))
    if not m:
        return default_mm
    v = float(m.group(1))
    return v * 25.4 if v <= 6 else v          # inches if small, else mm


def rows(plan, struct=None):
    """One dict per bar-type per beam + a diameter summary. Deterministic."""
    beams = [b for b in (getattr(plan, "beams", None) or [])
             if math.hypot(b.x2 - b.x1, b.y2 - b.y1) > 1e-6]
    top_c, top_d = _bars(_s(struct, "beam_top"))
    bot_c, bot_d = _bars(_s(struct, "beam_bot"))
    st_d, st_sp = _stirrup(_s(struct, "stirrup"))
    cover = _in_mm(_s(struct, "cover_beam"), 25.0)

    out = []
    by_dia = {}

    def add(mark, member, dia, typ, nos, cut_mm):
        total_m = nos * cut_mm / 1000.0
        uw = dia * dia / 162.0
        wt = total_m * uw
        out.append({"mark": mark, "member": member, "dia": round(dia),
                    "type": typ, "nos": nos, "cut": round(cut_mm),
                    "total_m": round(total_m, 2), "uw": round(uw, 3),
                    "wt": round(wt, 2)})
        by_dia[round(dia)] = by_dia.get(round(dia), 0.0) + wt

    for b in sorted(beams, key=lambda b: _numkey(b.tag)):
        L = b.length * MM
        bw, bd = b.width_mm, b.depth_mm
        tag = b.tag or "B"
        if top_c:
            cut = L - 2 * cover + 2 * (10 * top_d)
            add(f"{tag}-T", tag, top_d, "Top - straight", top_c, cut)
        if bot_c:
            cut = L - 2 * cover + 2 * (10 * bot_d)
            add(f"{tag}-B", tag, bot_d, "Bottom - straight", bot_c, cut)
        if st_d and st_sp:
            nos = int(L / st_sp) + 1
            peri = 2 * ((bw - 2 * cover) + (bd - 2 * cover)) + 2 * (10 * st_d)
            add(f"{tag}-S", tag, st_d, f'Stirrup 2-leg @{round(st_sp)}',
                nos, peri)

    summary = [{"dia": d, "wt": round(w, 2)} for d, w in sorted(by_dia.items())]
    grand = round(sum(by_dia.values()), 2)
    return out, summary, grand


# ---- table sheet ----------------------------------------------------------
COLS = [("MARK", 1.5), ("MEMBER", 1.6), ("DIA\nmm", 1.0), ("TYPE / SHAPE", 4.6),
        ("NOS", 1.1), ("CUT LEN\nmm", 2.2), ("TOTAL\nm", 1.7),
        ("UNIT WT\nkg/m", 2.0), ("WEIGHT\nkg", 1.9)]
RH = 0.62
LAY = "BEAM-TAG"


def build(plan, struct=None):
    dl = DrawList()
    data, summary, grand = rows(plan, struct)
    xs = [0.0]
    for _n, w in COLS:
        xs.append(xs[-1] + w)
    total_w = xs[-1]
    n = len(data)
    top = 0.0

    dl.text(0, top + 1.0, "BAR BENDING SCHEDULE — BEAMS", h=0.5, layer="TITLE",
            halign="left", bold=True)

    # header
    hy = top
    dl.rect(0, hy - RH, total_w, RH, layer=LAY)
    for (name, _w), x0, x1 in zip(COLS, xs, xs[1:]):
        for j, ln in enumerate(name.split("\n")):
            dl.text((x0 + x1) / 2, hy - 0.24 - j * 0.26, ln, h=0.24, layer=LAY,
                    bold=True)
    # rows
    y = hy - RH
    for r in data:
        cells = [r["mark"], r["member"], str(r["dia"]), r["type"],
                 str(r["nos"]), f'{r["cut"]}', f'{r["total_m"]}', f'{r["uw"]}',
                 f'{r["wt"]}']
        for c, (name, _w), x0, x1 in zip(cells, COLS, xs, xs[1:]):
            al = "left" if name in ("TYPE / SHAPE",) else "center"
            tx = x0 + 0.15 if al == "left" else (x0 + x1) / 2
            dl.text(tx, y - RH / 2, c, h=0.24, layer=LAY, halign=al)
        y -= RH
    # grid
    dl.rect(0, y, total_w, hy - y, layer=LAY)
    for x in xs[1:-1]:
        dl.line(x, y, x, hy, layer=LAY)
    for i in range(n + 1):
        yy = hy - RH - i * RH
        dl.line(0, yy, total_w, yy, layer=LAY)

    # ---- diameter-wise summary + grand total ----
    sy = y - 0.9
    dl.text(0, sy, "STEEL SUMMARY", h=0.34, layer=LAY, halign="left", bold=True)
    sy -= 0.5
    dl.text(0, sy, "Ø (mm)", h=0.26, layer=LAY, halign="left", bold=True)
    dl.text(3.0, sy, "WEIGHT (kg)", h=0.26, layer=LAY, halign="left", bold=True)
    for s in summary:
        sy -= 0.45
        dl.text(0, sy, str(s["dia"]), h=0.26, layer=LAY, halign="left")
        dl.text(3.0, sy, f'{s["wt"]}', h=0.26, layer=LAY, halign="left")
    sy -= 0.55
    dl.text(0, sy, "TOTAL STEEL", h=0.3, layer=LAY, halign="left", bold=True)
    dl.text(3.0, sy, f"{grand} kg  (+ 3% wastage = {round(grand * 1.03, 1)} kg)",
            h=0.3, layer=LAY, halign="left", bold=True)
    dl.text(0, sy - 0.7,
            "Cutting length = member length − 2·cover + anchorage/hooks; "
            "unit weight = D²/162 kg/m. Standard defaults — editable via the "
            "Structural dialog.", h=0.2, layer="TEXT-SUB", halign="left")
    return dl


def _numkey(tag):
    m = re.search(r"(\d+)", tag or "")
    return int(m.group(1)) if m else 0
