"""Exporters: sheet-space DrawList (mm, y-up) -> SVG / PNG / PDF / DXF."""

from __future__ import annotations

import math
from xml.sax.saxutils import escape

from .draw import DrawList, Line, Arc, Poly, Text, Fill, Hatch, LAYERS
from . import hatchgen

MM_PT = 72.0 / 25.4


def _expand_hatches(dl: DrawList) -> DrawList:
    """A copy with every Hatch replaced by its equivalent preview geometry —
    used by the raster / vector previews (SVG / PNG / PDF). The DXF exporter
    keeps the Hatch as a real HATCH object instead."""
    out = DrawList()
    for it in dl.items:
        if isinstance(it, Hatch):
            hatchgen.render_preview(out, it)
        else:
            out.items.append(it)
    return out


def _lw(layer: str) -> float:
    return LAYERS.get(layer, ("#111111", 0.25, 7))[1]


def _col(layer: str) -> str:
    return LAYERS.get(layer, ("#111111", 0.25, 7))[0]


def _aci(layer: str) -> int:
    return LAYERS.get(layer, ("#111111", 0.25, 7))[2]


def _arc_pts(a: Arc, seg: int = 48):
    a1, a2 = a.a1, a.a2
    while a2 < a1:
        a2 += 360
    n = max(4, int(seg * (a2 - a1) / 360) + 2)
    return [(a.cx + a.r * math.cos(math.radians(a1 + (a2 - a1) * i / n)),
             a.cy + a.r * math.sin(math.radians(a1 + (a2 - a1) * i / n)))
            for i in range(n + 1)]


# --------------------------------------------------------------------- SVG
def to_svg(dl: DrawList, w_mm: float, h_mm: float) -> str:
    dl = _expand_hatches(dl)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w_mm}mm" '
         f'height="{h_mm}mm" viewBox="0 0 {w_mm} {h_mm}">',
         f'<rect width="{w_mm}" height="{h_mm}" fill="#ffffff"/>',
         '<g fill="none" stroke-linecap="round" stroke-linejoin="round">']
    Y = lambda v: h_mm - v          # noqa: E731  flip to SVG's y-down

    for it in dl.items:
        st = f'stroke="{_col(it.layer)}" stroke-width="{_lw(it.layer)}"'
        dash = ' stroke-dasharray="3 2"' if getattr(it, "dashed", False) else ""
        if isinstance(it, Fill):
            pts = " ".join(f"{p[0]:.3f},{Y(p[1]):.3f}" for p in it.pts)
            o.append(f'<polygon points="{pts}" fill="{it.color}" stroke="none"/>')
            continue
        if isinstance(it, Line):
            o.append(f'<line x1="{it.x1:.3f}" y1="{Y(it.y1):.3f}" '
                     f'x2="{it.x2:.3f}" y2="{Y(it.y2):.3f}" {st}{dash}/>')
        elif isinstance(it, Poly):
            pts = " ".join(f"{p[0]:.3f},{Y(p[1]):.3f}" for p in it.pts)
            tag = "polygon" if it.closed else "polyline"
            o.append(f'<{tag} points="{pts}" {st}{dash}/>')
        elif isinstance(it, Arc):
            pts = " ".join(f"{p[0]:.3f},{Y(p[1]):.3f}" for p in _arc_pts(it))
            o.append(f'<polyline points="{pts}" {st}{dash}/>')
        elif isinstance(it, Text):
            anchor = {"left": "start", "center": "middle", "right": "end"}[it.halign]
            base = {"bottom": "auto", "middle": "central", "top": "hanging"}[it.valign]
            rot = f' transform="rotate({-it.angle} {it.x:.3f} {Y(it.y):.3f})"' if it.angle else ""
            weight = ' font-weight="700"' if it.bold else ""
            o.append(f'<text x="{it.x:.3f}" y="{Y(it.y):.3f}" font-size="{it.h:.2f}" '
                     f'font-family="Arial, Helvetica, sans-serif" text-anchor="{anchor}" '
                     f'dominant-baseline="{base}" fill="{_col(it.layer)}" stroke="none"'
                     f'{weight}{rot}>{escape(it.s)}</text>')
    o.append("</g></svg>")
    return "\n".join(o)


# ------------------------------------------------------------- PNG and PDF
def _mpl_figure(dl: DrawList, w_mm: float, h_mm: float):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    dl = _expand_hatches(dl)

    fig = plt.figure(figsize=(w_mm / 25.4, h_mm / 25.4))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, w_mm)
    ax.set_ylim(0, h_mm)
    ax.axis("off")
    ax.set_facecolor("white")

    from matplotlib.patches import Polygon as _MplPolygon
    for it in dl.items:
        if isinstance(it, Fill):
            # material washes sit BELOW the line work so their hatch / speck
            # pattern reads through; white text-masks sit ABOVE the line work
            # (but below the text) so labels blank out busy areas cleanly.
            z = 2.6 if it.color.lower() in ("#ffffff", "#fff", "white") else 1.6
            ax.add_patch(_MplPolygon([(p[0], p[1]) for p in it.pts],
                                     closed=True, facecolor=it.color,
                                     edgecolor="none", zorder=z))
            continue
        style = dict(color=_col(it.layer), linewidth=_lw(it.layer) * 2.0,
                     solid_capstyle="round")
        if getattr(it, "dashed", False):
            style["linestyle"] = (0, (3, 2))
        if isinstance(it, Line):
            ax.add_line(Line2D([it.x1, it.x2], [it.y1, it.y2], **style))
        elif isinstance(it, Poly):
            pts = it.pts + ([it.pts[0]] if it.closed else [])
            ax.add_line(Line2D([p[0] for p in pts], [p[1] for p in pts], **style))
        elif isinstance(it, Arc):
            pts = _arc_pts(it)
            ax.add_line(Line2D([p[0] for p in pts], [p[1] for p in pts], **style))
        elif isinstance(it, Text):
            va = {"bottom": "bottom", "middle": "center", "top": "top"}[it.valign]
            ha = {"left": "left", "center": "center", "right": "right"}[it.halign]
            ax.text(it.x, it.y, it.s, fontsize=it.h * 2.55, color=_col(it.layer),
                    ha=ha, va=va, rotation=it.angle,
                    fontweight="bold" if it.bold else "normal",
                    family="DejaVu Sans", rotation_mode="anchor")
    return fig


def to_png(dl: DrawList, w_mm: float, h_mm: float, path: str, dpi: int = 200) -> str:
    fig = _mpl_figure(dl, w_mm, h_mm)
    fig.savefig(path, dpi=dpi, facecolor="white")
    fig.clf()
    return path


def to_pdf(dl: DrawList, w_mm: float, h_mm: float, path: str) -> str:
    fig = _mpl_figure(dl, w_mm, h_mm)
    fig.savefig(path, format="pdf", facecolor="white")
    fig.clf()
    return path


# --------------------------------------------------------------------- DXF
# MTEXT attachment point (1..9) from our (halign, valign)
_ATTACH = {
    ("left", "top"): 1, ("center", "top"): 2, ("right", "top"): 3,
    ("left", "middle"): 4, ("center", "middle"): 5, ("right", "middle"): 6,
    ("left", "bottom"): 7, ("center", "bottom"): 8, ("right", "bottom"): 9,
}


def _mtext_escape(s: str) -> str:
    """MTEXT treats \\ { } as control characters — protect them so a name
    with a stray brace or slash prints literally instead of vanishing."""
    return s.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def to_dxf(dl: DrawList, path: str, model_scale: float = 1.0) -> str:
    """DXF in real-world units. `model_scale` converts sheet mm back to
    drawing units (pass k from sheet.compose to get feet).

    Text is written as MTEXT in an Arial style, honouring each label's own
    alignment. Writing every label centre-justified (the old behaviour) was
    what slid the schedule columns into each other and read as a mesh; a
    left-set column now stays a column. Rectangles and rings are already
    single polylines, arcs are true arcs, so nothing is stroked out of
    segments.
    """
    import ezdxf

    doc = ezdxf.new("R2013", setup=True)
    from . import units
    doc.header["$INSUNITS"] = units.dxf_insunits()   # 2=feet, 4=mm, 6=metre
    # real Arial, so TrueView stops falling back to the thin SHX stick font
    for name, font in (("ARIAL", "arial.ttf"), ("ARIAL-BD", "arialbd.ttf")):
        if name not in doc.styles:
            doc.styles.add(name, font=font)
    msp = doc.modelspace()
    for name, (_c, _w, aci) in LAYERS.items():
        if name not in doc.layers:
            doc.layers.add(name, color=aci)

    # feet → model units, then feet → the chosen unit (mm / m) so the DXF opens
    # at the right real-world size with matching $INSUNITS
    s = (1.0 / model_scale if model_scale else 1.0) * units.dxf_scale()
    P = lambda p: (p[0] * s, p[1] * s)   # noqa: E731

    for it in dl.items:
        attr = {"layer": it.layer}
        if isinstance(it, Line):
            msp.add_line(P((it.x1, it.y1)), P((it.x2, it.y2)), dxfattribs=attr)
        elif isinstance(it, Poly):
            msp.add_lwpolyline([P(p) for p in it.pts],
                               close=it.closed, dxfattribs=attr)
        elif isinstance(it, Arc):
            msp.add_arc(P((it.cx, it.cy)), it.r * s, it.a1, it.a2, dxfattribs=attr)
        elif isinstance(it, Text):
            mt = msp.add_mtext(_mtext_escape(it.s), dxfattribs={
                **attr,
                "style": "ARIAL-BD" if it.bold else "ARIAL",
                "char_height": it.h * s,
            })
            mt.set_location(P((it.x, it.y)), rotation=it.angle,
                            attachment_point=_ATTACH[(it.halign, it.valign)])
        elif isinstance(it, Hatch):
            _add_dxf_hatch(msp, it, P, s)
    doc.saveas(path)
    return path


def _grid_block(msp, it: Hatch, P, s):
    """The tile-joint grid (vlines / hlines) as REAL clipped line geometry,
    wrapped in ONE anonymous BLOCK per room. A pattern-fill HATCH is the 'proper'
    CAD object, but many DXF viewers (and lightweight CAD) render a line-pattern
    hatch as a SOLID GREY FILL — so the whole room reads as a grey block. Real
    lines render identically everywhere, and the block keeps them a single
    selectable object (so it is still 'grouped', not hundreds of loose lines)."""
    from shapely.geometry import Polygon, LineString
    doc = msp.doc
    step = max(1e-6, it.step)
    made_any = False
    n = sum(1 for b in doc.blocks if b.name.startswith("FLRGRID_"))
    bname = f"FLRGRID_{n}"
    blk = doc.blocks.new(name=bname)
    for loop in ([it.loops[0]] if it.loops else []):
        ext = it.loops[0]
        holes = it.loops[1:]
        try:
            poly = Polygon(ext, holes)
            if not poly.is_valid or poly.is_empty:
                poly = Polygon(ext)
        except Exception:
            continue
        x0, y0, x1, y1 = poly.bounds
        vert = (it.kind == "vlines")
        lo, hi = (x0, x1) if vert else (y0, y1)
        v = lo
        while v <= hi + 1e-9:
            seg = (LineString([(v, y0 - 1), (v, y1 + 1)]) if vert
                   else LineString([(x0 - 1, v), (x1 + 1, v)]))
            inter = seg.intersection(poly)
            if not inter.is_empty:
                parts = getattr(inter, "geoms", [inter])
                for pr in parts:
                    if getattr(pr, "geom_type", "") != "LineString":
                        continue
                    cs = list(pr.coords)
                    for a, b in zip(cs, cs[1:]):
                        blk.add_line(P(a), P(b),
                                     dxfattribs={"layer": it.layer})
                        made_any = True
            v += step
    if made_any:
        msp.add_blockref(bname, (0, 0), dxfattribs={"layer": it.layer})
    else:
        try:
            del doc.blocks[bname]
        except Exception:
            pass


def _add_dxf_hatch(msp, it: Hatch, P, s):
    """One real associative HATCH object per region — not exploded lines. The
    pattern scale is converted back to the hatch's own drawing units (`s` undoes
    the sheet scale) so the pattern density matches the sheet."""
    # tile-joint grids → real grouped lines (see _grid_block): pattern hatches
    # show as a solid grey block in many viewers.
    if it.kind in ("vlines", "hlines"):
        try:
            _grid_block(msp, it, P, s)
            return
        except Exception:
            pass
    pat, angle, sfac = hatchgen.DXF_PATTERN.get(
        it.kind, hatchgen.DXF_PATTERN["diag45"])
    pscale = max(0.02, it.step * s * sfac)
    try:
        h = msp.add_hatch(dxfattribs={"layer": it.layer, "color": 256})
        for i, loop in enumerate(it.loops):
            pts = [P(p) for p in loop]
            # outer loop external, the rest holes (even-odd nesting)
            flags = 1 if i == 0 else 0
            h.paths.add_polyline_path(pts, is_closed=True, flags=flags)
        try:
            if it.kind in ("vlines", "hlines"):
                # ONE hatch with a custom single-direction line pattern at the
                # tile spacing — the whole room's joints as one object
                d = max(0.02, it.step * s)     # spacing in sheet units
                ang = 90.0 if it.kind == "vlines" else 0.0
                # pattern line: [angle, base(x,y), offset(along, perp), dashes]
                h.set_pattern_fill("_LINES", definition=[[ang, (0.0, 0.0),
                                   (0.0, d), []]], scale=1.0)
            else:
                h.set_pattern_fill(pat, scale=pscale, angle=angle)
        except Exception:
            h.set_pattern_fill("ANSI31", scale=pscale)
        h.dxf.color = 256                      # BYLAYER so it takes layer colour
    except Exception:
        # last-ditch: fall back to the loose preview lines so nothing is lost
        tmp = DrawList()
        hatchgen.render_preview(tmp, it)
        for ln in tmp.items:
            if isinstance(ln, Line):
                msp.add_line(P((ln.x1, ln.y1)), P((ln.x2, ln.y2)),
                             dxfattribs={"layer": it.layer})
