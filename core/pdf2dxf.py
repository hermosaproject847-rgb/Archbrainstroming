"""PDF -> DXF — a direct, colour-and-fill-preserving GEOMETRIC conversion (no AI,
offline), the way the online PDF-to-DWG tools do it. Uses PyMuPDF's vector path
extraction: every drawn path keeps its STROKE colour + line width and its FILL
colour, so a solid black column stays a solid black fill, light hatching stays
light thin lines, and outlined text keeps its shape — the DXF looks like the PDF,
not a black mesh. Real text (where the PDF has it) is written as DXF TEXT.

Output is in millimetres (PDF points x 25.4/72); scale to a known dimension in
CAD if a true 1:1 size is needed. VECTOR PDFs only (a scanned photo has no vector
geometry to extract).
"""

from __future__ import annotations

import os

PT_MM = 25.4 / 72.0        # PDF points -> mm


def _pages_arg(spec, n):
    if not spec or str(spec).lower() in ("all", ""):
        return list(range(n))
    out = []
    for part in str(spec).split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            out += list(range(int(a) - 1, int(b)))
        elif part:
            out.append(int(part) - 1)
    return [i for i in out if 0 <= i < n]


def _rgb_tuple(c):
    """PyMuPDF colour (r,g,b floats 0-1, or a grey float, or None) -> 0-255
    (r,g,b) tuple, or None."""
    if c is None:
        return None
    if isinstance(c, (int, float)):
        v = int(round(float(c) * 255))
        return (v, v, v)
    try:
        return (int(round(c[0] * 255)), int(round(c[1] * 255)),
                int(round(c[2] * 255)))
    except Exception:
        return None


def _bezier(p0, p1, p2, p3, X, Y, n=6):
    out = []
    for i in range(n + 1):
        t = i / n
        mt = 1 - t
        x = (mt ** 3 * p0.x + 3 * mt * mt * t * p1.x + 3 * mt * t * t * p2.x
             + t ** 3 * p3.x)
        y = (mt ** 3 * p0.y + 3 * mt * mt * t * p1.y + 3 * mt * t * t * p2.y
             + t ** 3 * p3.y)
        out.append((X(x), Y(y)))
    return out


def _flatten(items, X, Y):
    """A drawing path's items -> a list of point-run polylines (beziers
    flattened, rects/quads closed)."""
    polys = []
    cur = []

    def pt(p):
        return (X(p.x), Y(p.y))

    for it in items:
        op = it[0]
        if op == "l":
            a, b = pt(it[1]), pt(it[2])
            if cur and cur[-1] == a:
                cur.append(b)
            else:
                if cur:
                    polys.append(cur)
                cur = [a, b]
        elif op == "c":
            seg = _bezier(it[1], it[2], it[3], it[4], X, Y)
            if cur and cur[-1] == seg[0]:
                cur += seg[1:]
            else:
                if cur:
                    polys.append(cur)
                cur = seg
        elif op == "re":
            if cur:
                polys.append(cur)
                cur = []
            r = it[1]
            polys.append([(X(r.x0), Y(r.y0)), (X(r.x1), Y(r.y0)),
                          (X(r.x1), Y(r.y1)), (X(r.x0), Y(r.y1)),
                          (X(r.x0), Y(r.y0))])
        elif op == "qu":
            if cur:
                polys.append(cur)
                cur = []
            q = it[1]
            polys.append([pt(q.ul), pt(q.ur), pt(q.lr), pt(q.ll), pt(q.ul)])
    if cur:
        polys.append(cur)
    return polys


def _snap(p, t):
    return (round(p[0] / t), round(p[1] / t))


def _join_chains(polys, tol=0.05):
    """Chain point-runs that meet end-to-end into longer polylines. Only walks
    THROUGH a node where exactly two path-ends meet (a clean pass-through) — a
    T-junction or crossing (degree >= 3) is left as a break, so walls become
    single polylines without wrongly fusing unrelated lines."""
    from collections import defaultdict
    n = len(polys)
    if n < 2:
        return polys
    ends = [(_snap(pl[0], tol), _snap(pl[-1], tol)) for pl in polys]
    deg = defaultdict(int)
    inc = defaultdict(list)
    for i, (a, b) in enumerate(ends):
        deg[a] += 1
        deg[b] += 1
        inc[a].append((i, 0))
        inc[b].append((i, 1))
    used = [False] * n
    out = []
    for i in range(n):
        if used[i]:
            continue
        used[i] = True
        chain = list(polys[i])
        start_node, node = ends[i]
        # extend forward
        while deg[node] == 2:
            nxt = next(((j, we) for (j, we) in inc[node] if not used[j]), None)
            if nxt is None:
                break
            j, we = nxt
            used[j] = True
            seg = polys[j] if we == 0 else polys[j][::-1]
            chain += seg[1:]
            node = ends[j][1] if we == 0 else ends[j][0]
            if node == start_node:
                break
        # extend backward
        node = start_node
        while deg[node] == 2:
            nxt = next(((j, we) for (j, we) in inc[node] if not used[j]), None)
            if nxt is None:
                break
            j, we = nxt
            used[j] = True
            seg = polys[j] if we == 1 else polys[j][::-1]
            chain = seg[:-1] + chain
            node = ends[j][0] if we == 1 else ends[j][1]
        out.append(chain)
    return out


def _simplify(pl, tol=0.08):
    """Drop interior points that lie on the straight line between their kept
    neighbours (collapses a straight wall drawn as many short segments into one
    run). Curves survive — their points deviate by more than tol."""
    if len(pl) < 3:
        return pl
    out = [pl[0]]
    for i in range(1, len(pl) - 1):
        ax, ay = out[-1]
        bx, by = pl[i]
        cx, cy = pl[i + 1]
        base = ((cx - ax) ** 2 + (cy - ay) ** 2) ** 0.5
        d = (abs((bx - ax) * (cy - ay) - (by - ay) * (cx - ax)) / base
             if base > 1e-9 else 0.0)
        if d > tol:
            out.append((bx, by))
    out.append(pl[-1])
    return out


def convert(pdf_path, dxf_path=None, pages="all"):
    """Convert `pdf_path` to a DXF. Returns {ok, path, pages, entities}."""
    import pymupdf
    import ezdxf

    if dxf_path is None:
        dxf_path = os.path.splitext(pdf_path)[0] + ".dxf"

    doc = ezdxf.new()
    msp = doc.modelspace()
    for lname in ("PDF_GEOM", "PDF_FILL", "PDF_TEXT"):
        if lname not in doc.layers:
            doc.layers.add(lname)

    counts = {"strokes": 0, "fills": 0, "text": 0}
    npages = 0
    src = pymupdf.open(pdf_path)
    for pi in _pages_arg(pages, src.page_count):
        page = src[pi]
        H = page.rect.height
        page_w = page.rect.width * PT_MM * 0.98    # a fill wider than the page
        page_h = H * PT_MM * 0.98                  # is an unclipped background
        dy = pi * (H * PT_MM + 40)

        def X(x):
            return x * PT_MM

        def Y(y):
            return (H - y) * PT_MM - dy

        # accumulate strokes by style so connected segments can be joined into
        # continuous polylines (walls) at the end of the page.
        from collections import defaultdict
        stroke_acc = defaultdict(list)

        for d in page.get_drawings():
            polys = _flatten(d.get("items", []), X, Y)
            if not polys:
                continue
            dtype = d.get("type", "s")           # 's' | 'f' | 'fs'
            stroke = _rgb_tuple(d.get("color"))
            fill = _rgb_tuple(d.get("fill"))
            w = d.get("width") or 0.0
            lw = max(0, min(211, int(round(w * PT_MM * 100))))

            # FILL first (so the stroke outline sits on top). Each closed
            # sub-path is filled on ITS OWN — filling one hatch across several
            # disjoint sub-paths with even-odd holes is what made the fills
            # 'spread' (fans between separate shapes / glyph counters).
            if dtype in ("f", "fs") and fill is not None:
                for pl in polys:
                    if len(pl) < 3:
                        continue
                    xs = [p[0] for p in pl]
                    ys = [p[1] for p in pl]
                    if (max(xs) - min(xs)) > page_w or \
                       (max(ys) - min(ys)) > page_h:
                        continue                 # unclipped page-size fill: skip
                    try:
                        h = msp.add_hatch(dxfattribs={"layer": "PDF_FILL"})
                        h.paths.add_polyline_path(pl, is_closed=True)
                        h.set_solid_fill(rgb=fill)
                        counts["fills"] += 1
                    except Exception:
                        pass
            # STROKE — held per style, joined below
            if dtype in ("s", "fs") or (dtype == "f" and stroke is not None):
                for pl in polys:
                    if len(pl) >= 2:
                        stroke_acc[(stroke, lw)].append(pl)

        # join connected segments per style, collapse straight runs, then emit
        for (stroke, lw), polys in stroke_acc.items():
            for pl in _join_chains(polys):
                pl = _simplify(pl)
                if len(pl) < 2:
                    continue
                try:
                    e = msp.add_lwpolyline(pl, dxfattribs={"layer": "PDF_GEOM"})
                    if stroke is not None:
                        e.rgb = stroke
                    if lw:
                        e.dxf.lineweight = lw
                    counts["strokes"] += 1
                except Exception:
                    pass

        # real text (kept as editable TEXT where the PDF has it). Use the span's
        # FONT SIZE for the height (not its bbox — a rotated/merged span's bbox
        # is the wrong height) and its writing direction for the rotation.
        import math
        seen_text = set()
        try:
            td = page.get_text("dict")
            for block in td.get("blocks", []):
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        t = (span.get("text") or "").rstrip()
                        if not t.strip():
                            continue
                        fsz = float(span.get("size", 8)) * PT_MM
                        if fsz < 0.4 or fsz > 80:
                            continue
                        bx = span["bbox"]
                        ox, oy = span.get("origin", (bx[0], bx[3]))
                        # drop a label the PDF drew twice at (nearly) the same
                        # spot — that overprint is what reads as 'double text'
                        key = (t, round(ox / 3), round(oy / 3))
                        if key in seen_text:
                            continue
                        seen_text.add(key)
                        dvec = span.get("dir", (1.0, 0.0))
                        ang = 0.0
                        if abs(dvec[1]) > 1e-6 or dvec[0] < 0:
                            ang = -math.degrees(math.atan2(dvec[1], dvec[0]))
                        # height = cap height (~0.7 of the font size), so stacked
                        # labels ("IL 44:" over "99.484") don't touch vertically.
                        h_mm = fsz * 0.72
                        # WIDTH FIT — the key fix for 'messy/overlapping' text:
                        # the CAD default font is wider than the PDF's, so make
                        # each label span exactly the width the PDF gave it. Run
                        # length is measured along the writing direction (bbox
                        # width for horizontal text, bbox height for vertical).
                        bw = (bx[2] - bx[0]) * PT_MM
                        bh = (bx[3] - bx[1]) * PT_MM
                        run = bw if abs(dvec[0]) >= abs(dvec[1]) else bh
                        natural = h_mm * 0.72 * max(1, len(t))
                        wf = 1.0
                        if natural > 1e-6 and run > 1e-6:
                            wf = max(0.35, min(1.6, run / natural))
                        try:
                            e = msp.add_text(
                                t, dxfattribs={"layer": "PDF_TEXT",
                                               "height": round(h_mm, 4),
                                               "width": round(wf, 3),
                                               "rotation": round(ang, 2)})
                            e.set_placement((X(ox), Y(oy)))
                            col = span.get("color")
                            if isinstance(col, int):
                                e.rgb = ((col >> 16) & 255, (col >> 8) & 255,
                                         col & 255)
                            counts["text"] += 1
                        except Exception:
                            pass
        except Exception:
            pass
        npages += 1

    doc.saveas(dxf_path)
    src.close()
    return {"ok": True, "path": dxf_path, "pages": npages, "entities": counts}
