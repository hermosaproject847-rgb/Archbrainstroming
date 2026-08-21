"""Backend-neutral drawing primitives.

The engine emits a DrawList; the exporters turn it into SVG / PDF / PNG / DXF.
All coordinates are in FEET, y-up (drawing space).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math

# layer -> (colour, line weight in mm, dxf aci colour)
LAYERS = {
    "WALL-EXT":  ("#111111", 0.50, 7),
    "WALL-INT":  ("#111111", 0.30, 7),
    "OPENING":   ("#111111", 0.25, 7),
    "DOOR":      ("#444444", 0.18, 8),
    "WINDOW":    ("#222222", 0.22, 7),
    "STAIR":     ("#333333", 0.22, 8),
    "RAILING":   ("#444444", 0.15, 8),
    "COLUMN":    ("#111111", 0.35, 7),       # structural columns, drawn solid
    "COLUMNTAG": ("#111111", 0.13, 7),
    "GRASS":     ("#4a8a3a", 0.16, 3),       # lawn / garden — grass tufts only
    # building section (vertical cut)
    "SEC-CUT":   ("#111111", 0.30, 7),       # cut masonry / concrete outline
    "SEC-SLAB":  ("#333333", 0.35, 8),       # slabs, plinth, footing
    "SEC-EARTH": ("#7a5a3a", 0.12, 34),      # earth / filling hatch
    "SEC-TEXT":  ("#111111", 0.13, 7),
    "SEC-DIM":   ("#1d3557", 0.15, 5),       # level marks
    "SEC-LINE":  ("#d1495b", 0.30, 1),       # section cut line on the plan
    "WALLTAG":   ("#2f5fd0", 0.15, 5),
    "FURNITURE": ("#666666", 0.18, 8),
    "FURNTAG":   ("#333333", 0.13, 7),
    "SETOUT":    ("#2f5fd0", 0.13, 5),
    "ELEC":      ("#b8541a", 0.20, 30),
    "ELECTAG":   ("#8a3f14", 0.13, 30),
    "ELEC-LOOP": ("#c98a5a", 0.10, 31),   # switch → fixture loops, own layer
    # §14 of the plumbing prompt — the seven systems, the same colours on the
    # plan, in the legend and on the DXF layers
    "PLUMB-CW":    ("#0d47a1", 0.28, 5),     # cold water, blue solid
    "PLUMB-HW":    ("#d32f2f", 0.28, 1),     # hot water, red dashed
    "PLUMB-SOIL":  ("#6d4c41", 0.40, 34),    # soil pipe, brown
    "PLUMB-WASTE": ("#757575", 0.32, 8),     # waste pipe, grey
    "PLUMB-VENT":  ("#2e7d32", 0.22, 3),     # vent, green dot-dash
    "PLUMB-STORM": ("#00acc1", 0.28, 4),     # storm / RWP, cyan
    "PLUMB-ACD":   ("#ad1457", 0.20, 6),     # AC condensate, magenta
    "PLUMB-TAG":   ("#263238", 0.13, 8),     # keynote circles and Ø tags
    "SANITARY":    ("#555555", 0.20, 8),     # the fixtures plumbing keeps
    # plumbing INSTALLATION DETAIL sheet — heights & set-out, red like the ref
    "PDET-NOTE":   ("#d21f1f", 0.16, 1),     # red installation-height notes
    "PDET-LEAD":   ("#d21f1f", 0.12, 1),     # red leaders / dimension ticks
    "PDET-TRAP":   ("#7b1fa2", 0.20, 6),     # trap / point symbols (purple)
    # beam layout sheet
    "BEAM":        ("#1565c0", 0.35, 5),     # beam edges (width), blue
    "BEAM-CL":     ("#90a4c8", 0.12, 5),     # beam centre-line, dashed
    "BEAM-TAG":    ("#0d3b66", 0.15, 5),     # beam number / size
    "BEAM-WALL":   ("#c2c2c2", 0.12, 8),     # walls shown light under the beams
    # flooring (master prompt SECTION 12 drafting layers)
    "FLR-GRID":    ("#8d99ae", 0.10, 8),     # the tile joints / spacer grid
    "FLR-HATCH":   ("#c9ccd4", 0.08, 254),   # material fill hatch
    "FLR-START":   ("#d1495b", 0.22, 1),     # start point, its own colour
    "FLR-SKIRT":   ("#5a7d5a", 0.18, 3),     # skirting run
    "FLR-LEVEL":   ("#1d3557", 0.15, 5),     # spot levels & slope arrows
    "FLR-TEXT":    ("#222222", 0.13, 7),     # room flooring labels
    "DIM":       ("#7a7a7a", 0.13, 250),
    "TEXT":      ("#111111", 0.13, 7),
    "TEXT-SUB":  ("#666666", 0.13, 8),
    "PLOT":      ("#999999", 0.20, 253),
    "NORTH":     ("#111111", 0.25, 7),
    "TITLE":     ("#111111", 0.25, 7),
    "HATCH":     ("#bbbbbb", 0.10, 254),
}


@dataclass
class Line:
    x1: float; y1: float; x2: float; y2: float
    layer: str = "WALL-INT"
    dashed: bool = False


@dataclass
class Arc:
    cx: float; cy: float; r: float
    a1: float; a2: float          # degrees, ccw from +x
    layer: str = "DOOR"
    dashed: bool = False


@dataclass
class Poly:
    pts: list[tuple[float, float]]
    layer: str = "WALL-INT"
    closed: bool = True
    dashed: bool = False


@dataclass
class Fill:
    """A solid-filled polygon with no outline. Used for white text masks so
    labels read cleanly over a busy grid, and for material washes."""
    pts: list[tuple[float, float]]
    color: str = "#ffffff"
    layer: str = "MASK"


@dataclass
class Hatch:
    """A filled REGION carrying a hatch pattern. In DXF it becomes ONE real
    associative HATCH entity (a single object, not loose lines); on screen / PDF
    it is expanded to the equivalent line / speck pattern so the preview matches.
    `loops` is [outer, hole1, …] each a list of (x, y). `kind` picks the pattern."""
    loops: list
    kind: str = "diag45"           # diag45|diag135|concrete|rubble|pebble
    step: float = 0.28
    layer: str = "HATCH"


@dataclass
class Text:
    x: float; y: float
    s: str
    h: float = 0.6                 # cap height in feet
    layer: str = "TEXT"
    angle: float = 0.0             # degrees
    halign: str = "center"         # left | center | right
    valign: str = "middle"         # bottom | middle | top
    bold: bool = False


# ------------------------------------------------------- fitting text
# Arial at cap height h runs about 0.58 h per character across mixed case and
# rather more in all-caps, which the schedules use heavily. Estimating low is
# what let schedule cells run over their column rule and into the next column.
CHAR_W = 0.58
# baseline-to-baseline as a multiple of cap height. Below about 1.2 the
# descenders of one line touch the caps of the next and wrapped cells read as
# a smudge.
LINE_SP = 1.25


def _wrap_to(s: str, width_mm: float, h: float) -> list[str]:
    per = max(3, int(width_mm / (h * CHAR_W)))
    out, line = [], ""
    for word in str(s).split():
        trial = (line + " " + word).strip()
        if len(trial) <= per:
            line = trial
        else:
            if line:
                out.append(line)
            # a single word longer than the column has to be broken
            while len(word) > per:
                out.append(word[:per])
                word = word[per:]
            line = word
    if line:
        out.append(line)
    return out or [""]


def fit_cell(s, width_mm: float, h: float, max_lines: int = 1,
             min_h: float = 1.25) -> tuple[list[str], float]:
    """Lay text out inside a table cell WITHOUT running past its column.

    Wraps to at most `max_lines`; if it still does not fit, steps the type
    down to `min_h`; if it still does not fit, truncates the last line with an
    ellipsis. Returns (lines, height). Nothing a schedule prints is ever worth
    letting it overwrite the neighbouring column.
    """
    s = str(s)
    hh = h
    while hh >= min_h:
        lines = _wrap_to(s, width_mm, hh)
        if len(lines) <= max_lines:
            return lines, hh
        hh -= 0.15
    lines = _wrap_to(s, width_mm, min_h)
    if len(lines) > max_lines:
        per = max(3, int(width_mm / (min_h * CHAR_W)))
        lines = lines[:max_lines]
        lines[-1] = lines[-1][:max(1, per - 1)] + "…"
    return lines, min_h


@dataclass
class DrawList:
    items: list = field(default_factory=list)

    # -- emitters --------------------------------------------------------
    def line(self, x1, y1, x2, y2, layer="WALL-INT", dashed=False):
        self.items.append(Line(x1, y1, x2, y2, layer, dashed))

    def arc(self, cx, cy, r, a1, a2, layer="DOOR", dashed=False):
        self.items.append(Arc(cx, cy, r, a1, a2, layer, dashed))

    def poly(self, pts, layer="WALL-INT", closed=True, dashed=False):
        if len(pts) >= 2:
            self.items.append(Poly(list(pts), layer, closed, dashed))

    def text(self, x, y, s, h=0.6, layer="TEXT", angle=0.0,
             halign="center", valign="middle", bold=False):
        if s:
            self.items.append(Text(x, y, str(s), h, layer, angle, halign, valign, bold))

    def rect(self, x, y, w, h, layer="WALL-INT", dashed=False):
        self.poly([(x, y), (x + w, y), (x + w, y + h), (x, y + h)],
                  layer=layer, closed=True, dashed=dashed)

    def fill(self, pts, color="#ffffff", layer="MASK"):
        if len(pts) >= 3:
            self.items.append(Fill(list(pts), color, layer))

    def fill_rect(self, x, y, w, h, color="#ffffff", layer="MASK"):
        self.fill([(x, y), (x + w, y), (x + w, y + h), (x, y + h)],
                  color=color, layer=layer)

    def hatch(self, loops, kind="diag45", step=0.28, layer="HATCH"):
        """A hatched region. `loops` is one polygon [(x,y),…] or a list of such
        loops (outer first, holes after)."""
        if loops and isinstance(loops[0][0], (int, float)):
            loops = [loops]                       # a single polygon was passed
        loops = [lp for lp in loops if len(lp) >= 3]
        if loops:
            self.items.append(Hatch(loops, kind, step, layer))

    def arrow(self, x1, y1, x2, y2, layer="STAIR", head=0.45):
        self.line(x1, y1, x2, y2, layer)
        ang = math.atan2(y2 - y1, x2 - x1)
        for s in (+1, -1):
            a = ang + math.pi + s * math.radians(22)
            self.line(x2, y2, x2 + head * math.cos(a), y2 + head * math.sin(a), layer)

    def extend(self, other: "DrawList"):
        self.items.extend(other.items)

    def translated(self, dx: float, dy: float) -> "DrawList":
        """A copy moved by (dx, dy) — used to set two drawings side by side
        in one file."""
        out = DrawList()
        for it in self.items:
            if isinstance(it, Line):
                out.line(it.x1 + dx, it.y1 + dy, it.x2 + dx, it.y2 + dy,
                         it.layer, it.dashed)
            elif isinstance(it, Poly):
                out.poly([(p[0] + dx, p[1] + dy) for p in it.pts],
                         it.layer, it.closed, it.dashed)
            elif isinstance(it, Fill):
                out.fill([(p[0] + dx, p[1] + dy) for p in it.pts],
                         it.color, it.layer)
            elif isinstance(it, Arc):
                out.arc(it.cx + dx, it.cy + dy, it.r, it.a1, it.a2,
                        it.layer, it.dashed)
            elif isinstance(it, Text):
                out.text(it.x + dx, it.y + dy, it.s, it.h, it.layer,
                         it.angle, it.halign, it.valign, it.bold)
            elif isinstance(it, Hatch):
                out.items.append(Hatch(
                    [[(p[0] + dx, p[1] + dy) for p in lp] for lp in it.loops],
                    it.kind, it.step, it.layer))
        return out

    # -- bounds ----------------------------------------------------------
    def bounds(self) -> tuple[float, float, float, float]:
        xs, ys = [], []
        for it in self.items:
            if isinstance(it, Line):
                xs += [it.x1, it.x2]; ys += [it.y1, it.y2]
            elif isinstance(it, (Poly, Fill)):
                xs += [p[0] for p in it.pts]; ys += [p[1] for p in it.pts]
            elif isinstance(it, Arc):
                xs += [it.cx - it.r, it.cx + it.r]; ys += [it.cy - it.r, it.cy + it.r]
            elif isinstance(it, Text):
                xs.append(it.x); ys.append(it.y)
            elif isinstance(it, Hatch):
                for lp in it.loops:
                    xs += [p[0] for p in lp]; ys += [p[1] for p in lp]
        if not xs:
            return (0.0, 0.0, 1.0, 1.0)
        return (min(xs), min(ys), max(xs), max(ys))
