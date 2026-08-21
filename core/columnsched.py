"""COLUMN SCHEDULE — the standard structural table: for every column its SIZE,
concrete MIX, vertical REINFORCEMENT, and the ring (tie) spacing at the support
and at mid-span, with a small rebar cross-section, laid out C-1, C-2, … across.
A schematic to the real drafting FORMAT — the bar choice follows a standard rule
from the column size, not a full analysis.
"""

from __future__ import annotations

import re

from .draw import Arc, DrawList
from . import framingplan as FP

L_TXT, L_GRID, L_BAR, L_SEC = "BEAM-TAG", "BEAM", "FLR-START", "SEC-LINE"


def _numkey(tag):
    m = re.search(r"(\d+)", tag or "")
    return (int(m.group(1)) if m else 0, tag or "")


def _reinf(w_in, d_in):
    """Standard vertical reinforcement by column size."""
    m = max(w_in, d_in)
    if m <= 12:
        return "4#16", (2, 2)          # bars, (per-short-face, per-long-face)
    if m <= 18:
        return "4#16 + 4#12", (2, 3)
    if m <= 24:
        return "4#20 + 4#16", (2, 4)
    return "6#20 + 2#16", (2, 4)


def _section(dl, cx, cy, w_in, d_in, bars, box_w, box_h):
    """A small column rebar section centred at (cx, cy), fit inside box."""
    # scale the real proportion into the cell
    ar = d_in / max(w_in, 1e-6)
    sw = min(box_w, box_h / max(ar, 1e-6))
    sh = sw * ar
    sw = min(sw, box_w)
    sh = min(sh, box_h)
    x0, y0 = cx - sw / 2, cy - sh / 2
    dl.rect(x0, y0, sw, sh, layer=L_SEC)                        # concrete
    dl.rect(x0 + 0.12, y0 + 0.12, sw - 0.24, sh - 0.24, layer=L_BAR)  # tie
    pf, lf = bars                       # bars along short / long face
    ins = 0.22
    xs = [x0 + ins + (sw - 2 * ins) * i / (lf - 1) for i in range(lf)] \
        if lf > 1 else [cx]
    ys = [y0 + ins + (sh - 2 * ins) * i / (pf - 1) for i in range(pf)] \
        if pf > 1 else [cy]
    for i, xx in enumerate(xs):
        for j, yy in enumerate(ys):
            edge = i in (0, len(xs) - 1) or j in (0, len(ys) - 1)
            if edge:
                dl.items.append(Arc(xx, yy, 0.06, 0, 360, L_BAR))


HDR_W = 5.0
COL_W = 5.4
ROWS = [("SIZE", 1.0), ("MIX", 1.0), ("REINF.", 1.3),
        ("RINGS AT SUPPORT", 1.2), ("RINGS AT MID SPAN", 1.2)]
SEC_H = 3.4
PER_BLOCK = 7


def _block(dl, cols, ox, oy):
    """One table block (up to PER_BLOCK columns), top-left at (ox, oy)."""
    n = len(cols)
    heights = [h for _, h in ROWS] + [SEC_H] + [0.9]     # +section +label row
    total_h = sum(heights)
    ys = [oy]
    for h in heights:
        ys.append(ys[-1] - h)
    x_end = ox + HDR_W + n * COL_W

    # horizontal grid
    for y in ys:
        dl.line(ox, y, x_end, y, layer=L_GRID)
    # vertical grid
    dl.line(ox, oy, ox, oy - total_h, layer=L_GRID)
    dl.line(ox + HDR_W, oy, ox + HDR_W, oy - total_h, layer=L_GRID)
    for j in range(n):
        dl.line(ox + HDR_W + (j + 1) * COL_W, oy, ox + HDR_W + (j + 1) * COL_W,
                oy - total_h, layer=L_GRID)

    # row header labels
    for i, (lbl, _h) in enumerate(ROWS):
        yc = (ys[i] + ys[i + 1]) / 2
        dl.text(ox + 0.2, yc, lbl, h=0.3, layer=L_TXT, halign="left", bold=True)
    dl.text(ox + 0.2, (ys[len(ROWS)] + ys[len(ROWS) + 1]) / 2, "SECTION",
            h=0.3, layer=L_TXT, halign="left", bold=True)
    dl.text(ox + 0.2, (ys[-2] + ys[-1]) / 2, "COLUMN", h=0.32, layer=L_TXT,
            halign="left", bold=True)

    # each column's data
    for j, c in enumerate(cols):
        cx = ox + HDR_W + j * COL_W + COL_W / 2
        w_in, d_in = round(c.w * 12), round(c.h * 12)
        reinf, bars = _reinf(w_in, d_in)
        vals = [f'{w_in}"X{d_in}"', "M-25", reinf, '#8@100 C/C', '#8@200 C/C']
        for i, v in enumerate(vals):
            yc = (ys[i] + ys[i + 1]) / 2
            dl.text(cx, yc, v, h=0.3, layer=L_TXT)
        # section
        secy = (ys[len(ROWS)] + ys[len(ROWS) + 1]) / 2
        _section(dl, cx, secy, w_in, d_in, bars, COL_W - 1.4, SEC_H - 1.0)
        # column tag (bold, at the bottom label row)
        dl.text(cx, (ys[-2] + ys[-1]) / 2, (c.tag or f"C{j+1}").upper(),
                h=0.4, layer=L_SEC, bold=True)
    return total_h


def build(plan, struct=None):
    dl = DrawList()
    cols = sorted([c for c in (getattr(plan, "columns", None) or [])],
                  key=lambda c: _numkey(c.tag))
    if not cols:
        dl.text(0, 0, "No columns in the plan.", h=0.6, layer=L_TXT)
        return dl
    oy = 0.0
    for start in range(0, len(cols), PER_BLOCK):
        block = cols[start:start + PER_BLOCK]
        h = _block(dl, block, 0, oy)
        oy -= h + 2.2
    # notes below the last block
    FP._notes(dl, 0, oy - 0.5, struct)
    return dl
