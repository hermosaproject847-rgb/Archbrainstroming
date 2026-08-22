"""Wall schedule / legend — wall number, length and thickness.

Printed on the floor-plan sheet next to the wall numbers so the numbering can
be read, and it is the base data the BOQ measures masonry and plaster from.
Everything here is DERIVED from the wall geometry, nothing assumed.
"""

from __future__ import annotations

from .draw import DrawList

MM = 304.8


def _ft_in(feet: float) -> str:
    """A length in feet in the chosen drawing unit (feet-inch / mm / m)."""
    from . import units
    return units.fmt_len(feet)


def rows(plan) -> list[dict]:
    """One row per numbered wall: number, length, thickness, type. Railings and
    sub-1ft stubs are skipped — they carry no masonry."""
    out = []
    for w in plan.walls:
        if getattr(w, "railing", False):
            continue
        if w.length < 1.0:
            continue
        num = "".join(ch for ch in w.id if ch.isdigit()) or w.id
        out.append({
            "no": num,
            "length_ft": round(w.length, 3),
            "length_mm": round(w.length * MM),
            "length_label": _ft_in(w.length),
            "thick_in": round(w.thickness_in, 1),
            "thick_mm": round(w.thickness_in * 25.4),
            "type": "EXT" if w.exterior else "INT",
            "room": getattr(w, "room", "") or "",
        })
    # numeric-ish sort by wall number
    def _key(r):
        try:
            return (0, int(r["no"]))
        except ValueError:
            return (1, r["no"])
    return sorted(out, key=_key)


# ---------------------------------------------------------------- drawing
COLS = [("NO", 8.0), ("LENGTH", 20.0), ("THK", 14.0), ("TYPE", 12.0)]
COL_W = sum(c[1] for c in COLS)
RH = 4.0
HDR = 5.0


def draw(dl: DrawList, plan, W: float, H: float,
         x: float | None = None, y: float | None = None,
         max_rows_per_col: int = 24) -> None:
    """A compact multi-column wall legend, top-left of the sheet by default."""
    data = rows(plan)
    if not data:
        return
    from . import sheetformat
    MARGIN = 10.0
    if x is None:
        x = MARGIN + 4
    if y is None:
        y = H - MARGIN - 6

    dl.text(x, y + 2.5, "WALL SCHEDULE  (No · Length · Thickness)", h=2.8,
            layer="TITLE", halign="left", bold=True)

    n = len(data)
    ncol = (n + max_rows_per_col - 1) // max_rows_per_col
    per = (n + ncol - 1) // ncol
    gap = 6.0

    for c in range(ncol):
        chunk = data[c * per:(c + 1) * per]
        if not chunk:
            continue
        bx = x + c * (COL_W + gap)
        _one(dl, chunk, bx, y)


def _one(dl: DrawList, chunk, bx: float, top: float) -> None:
    nrow = len(chunk)
    total_h = HDR + RH * nrow
    dl.rect(bx, top - total_h, COL_W, total_h, layer="TITLE")
    # column rules
    cx = bx
    for _lbl, w in COLS[:-1]:
        cx += w
        dl.line(cx, top - total_h, cx, top, layer="TITLE")
    # header
    dl.line(bx, top - HDR, bx + COL_W, top - HDR, layer="TITLE")
    cx = bx
    for lbl, w in COLS:
        dl.text(cx + 1.5, top - HDR * 0.68, lbl, h=2.0, layer="TITLE",
                halign="left", bold=True)
        cx += w
    # rows
    for i, r in enumerate(chunk):
        yy = top - HDR - RH * i
        vals = [r["no"], r["length_label"], f'{r["thick_in"]:g}"', r["type"]]
        cx = bx
        for v, (_lbl, w) in zip(vals, COLS):
            dl.text(cx + 1.5, yy - RH * 0.66, str(v), h=1.9,
                    layer="TEXT-SUB", halign="left")
            cx += w
