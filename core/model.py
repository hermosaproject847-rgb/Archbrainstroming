"""Plan data model — the contract between the sketch reader and the drawing engine.

Everything is in FEET. Wall thickness is in INCHES (as the sketch calls it out).
Walls are stored as CENTRE-LINES, per STEP 2 of the master prompt.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Literal
import json

IN = 1.0 / 12.0  # inches -> feet

# Names that mean "open to the sky, but walled all round".
SHAFT_WORDS = ("o.t.s", "ots", "open to sky", "shaft", "duct", "void",
               "light well", "lightwell")


def _looks_like_shaft(name: str) -> bool:
    n = (name or "").strip().lower()
    return any(w in n for w in SHAFT_WORDS)


# A lawn / garden is soft landscape: open to sky, GRASS on the ground — no
# tiled floor, no ceiling, no electrical. Shown with a grass hatch and nothing
# else.
LAWN_WORDS = ("lawn", "garden", "grass", "landscape", "green area", "turf")


def is_lawn(name: str) -> bool:
    n = (name or "").strip().lower()
    return any(w in n for w in LAWN_WORDS)


@dataclass
class Wall:
    id: str
    x1: float
    y1: float
    x2: float
    y2: float
    thickness_in: float = 9.0
    exterior: bool = False
    # A railing / parapet edges a verandah, balcony or terrace. It is drawn,
    # but it is NOT wall: it encloses nothing and no opening is punched
    # through it, so it stays out of the wall solid entirely.
    railing: bool = False
    # which room this wall belongs to, filled in by the numbering pass so the
    # table shows the same grouping the numbers follow
    room: str = ""

    @property
    def th(self) -> float:
        return self.thickness_in * IN

    @property
    def length(self) -> float:
        return ((self.x2 - self.x1) ** 2 + (self.y2 - self.y1) ** 2) ** 0.5

    @property
    def horizontal(self) -> bool:
        return abs(self.y2 - self.y1) < 1e-9

    def point_at(self, d: float) -> tuple[float, float]:
        """Point `d` feet from the wall start, along the centre-line."""
        L = self.length or 1e-9
        return (self.x1 + (self.x2 - self.x1) * d / L,
                self.y1 + (self.y2 - self.y1) * d / L)


@dataclass
class Room:
    """A room's CENTRE-LINE box. Clear inside faces = box inset by half the
    thickness of each bounding wall (computed by the engine, not stored)."""
    name: str
    x: float
    y: float
    w: float
    h: float
    size_label: str = ""       # e.g. "12'-0\" x 10'-6\"" as written on the sketch
    open_area: bool = False    # parking / yard / "5' wide open" -> NO enclosing walls
    # a full-room X on a lower floor (living/dining crossed corner to corner)
    # = DOUBLE HEIGHT: the volume runs two storeys, NO slab over it
    double_height: bool = False
    # A shaft is open to the sky but WALLED all round — O.T.S, light/vent
    # shafts, ducts. Without this it counts as just another open area and the
    # walls enclosing it get stripped away.
    void: bool = False
    # the room's NAME + SIZE label can be nudged off the centre (feet) when it
    # overlaps furniture / stairs — dragged on the canvas, stored here
    label_dx: float = 0.0
    label_dy: float = 0.0

    @property
    def centre(self) -> tuple[float, float]:
        return (self.x + self.w / 2, self.y + self.h / 2)

    @property
    def is_lawn(self) -> bool:
        return is_lawn(self.name)


@dataclass
class Swing:
    room: str = ""                              # room the leaf swings INTO
    hinge: Literal["start", "end"] = "start"    # which jamb, measured along the wall
    side: Literal["left", "right"] = "left"     # which side of the wall it opens to
    manual: bool = False                        # set by hand — autofix leaves it alone


MM = 1.0 / 304.8            # millimetres -> feet

# Rulebook 2/3/4: typical levels above FFL, in millimetres.
DEFAULT_LINTEL_MM = 2100.0
DEFAULT_SILL_MM = {"window": 900.0, "vent": 1800.0, "door": 0.0, "gate": 0.0}


DOOR_TYPES = ("single_door", "double_door", "sliding_door")

# A door wider than this is a double door — a single leaf that big is neither
# built nor drawn, so the type follows the width rather than being asked for.
DOUBLE_DOOR_MM = 1200.0


@dataclass
class Opening:
    type: Literal["single_door", "double_door", "sliding_door",
                  "window", "vent", "gate", "open"]
    wall_id: str
    pos: float                  # feet from wall start to the opening's NEAR jamb
    width: float                # feet
    tag: str = ""               # D1 / W2 / V1
    swing: Swing | None = None  # doors only
    leaves: int = 0             # derived from the type; 0 = work it out
    # Rulebook §2.5, §3.2, §4.2: sill and lintel levels are MANDATORY on every
    # opening (lintel on doors, sill AND lintel on windows and ventilators).
    # Millimetres above FFL, matching the schedule the rulebook asks for.
    height_mm: float = 0.0      # leaf / opening height
    sill_mm: float = 0.0        # windows and ventilators
    lintel_mm: float = 0.0      # all openings
    count: int = 1              # "Nos." column of the schedule
    sill_note: str = ""

    @property
    def width_mm(self) -> float:
        return self.width * 304.8

    @property
    def is_door(self) -> bool:
        return self.type in DOOR_TYPES or self.type == "door"

    @property
    def is_sliding(self) -> bool:
        return self.type == "sliding_door"

    @property
    def leaf_count(self) -> int:
        """How many leaves this door actually has.

        The type decides it, and a door wider than 1200 is a double door
        whatever it was called — a 1800 single leaf does not exist.
        """
        if not self.is_door:
            return 0
        if self.type == "double_door":
            return 2
        if self.type == "sliding_door":
            return 1
        if self.leaves and int(self.leaves) >= 2:
            return 2
        return 2 if self.width_mm > DOUBLE_DOOR_MM else 1
    # Rulebook 3.24 / 4.30: sill and lintel levels are MANDATORY on every
    # window and ventilator, and the lintel level on every door. Held in
    # millimetres above FFL, the units the rulebook and the schedule use.
    sill_mm: float | None = None
    lintel_mm: float | None = None
    height_mm: float | None = None      # leaf/opening height, W x H schedule
    depth_mm: float | None = None       # frame depth, windows and ventilators
    count: int = 1                      # "Nos." column of the schedule

    def size_label(self) -> str:
        """W x H in mm, as the schedule wants it."""
        w = round(self.width / MM)
        h = self.height_mm
        if not h:
            h = (2100.0 if self.type == "door" else
                 (self.lintel_mm or DEFAULT_LINTEL_MM) - (self.sill_mm or 0.0))
        return f"{w:.0f} x {h:.0f}"

    def sill(self) -> float:
        return self.sill_mm if self.sill_mm is not None \
            else DEFAULT_SILL_MM.get(self.type, 0.0)

    def lintel(self) -> float:
        return self.lintel_mm if self.lintel_mm is not None else DEFAULT_LINTEL_MM


@dataclass
class Stair:
    """Typology as read off the sketch. Every rectangle is derived from these
    by core.stairs, so the drawing cannot contradict the typology."""
    x: float
    y: float
    w: float
    h: float
    # straight  one flight
    # L         two flights at a right angle, one landing
    # U         two parallel flights, one landing between them (dog-leg)
    # U3        THREE flights around a well: two parallel flights with a short
    #           flight between them, and TWO landings — each square, and sized
    #           independently of the treads
    type: Literal["straight", "L", "U", "U3"] = "U"
    run_axis: Literal["x", "y"] = "y"          # direction flight 1 runs
    up_from: Literal["top", "bottom", "left", "right"] = "bottom"  # side the UP arrow enters
    turn_side: Literal["top", "bottom", "left", "right"] = "right"  # where the turn/landing is
    flight_width: float = 0.0                  # 0 = derive from the footprint
    landing_depth: float = 0.0                 # 0 = derive
    well_gap: float = 0.0                      # 0 = derive
    steps_f1: int = 0                          # treads in flight 1 (0 = use `treads`)
    steps_f2: int = 0
    steps_f3: int = 0                          # U3 only: the middle flight
    landing_size: float = 0.0                  # U3: square landing side, feet
    winders: int = 0                           # steps in the turn; 0 = flat landing
    winder_style: Literal["straight", "fan"] = "straight"
    start_step: int = 0                        # first step number, 0 = do not number
    well: bool = True                          # draw the stairwell void
    show_dn: bool = True                       # a mid-floor plan shows UP and DN
    up_label: str = "UP"
    dn_label: str = "DN"
    label: str = ""                            # room label, e.g. "STAIRCASE"
    # legacy fields kept so older plan JSON still loads
    flights: int = 2
    treads: int = 9
    rotation: Literal["cw", "ccw"] = "ccw"
    landing_at: str = ""


@dataclass
class Steps:
    """Entry steps up to a plinth or verandah — two or three treads with level
    marks. Not a staircase: no flights, no landing, no UP/DN. Reading them as a
    stair is what put a floating stair box beside a verandah."""
    x: float
    y: float
    w: float
    h: float
    count: int = 2
    run_axis: Literal["x", "y"] = "x"                        # ascent direction
    up_from: Literal["top", "bottom", "left", "right"] = "left"
    levels: list[str] = field(default_factory=list)          # "+0'-6\"", "+1'-0\""
    label: str = ""


@dataclass
class Section:
    """A section cut line drawn on the plan. The vertical data (heights) is
    supplied at cut time through the questionnaire, never stored here."""
    tag: str = "A"
    x1: float = 0.0
    y1: float = 0.0
    x2: float = 0.0
    y2: float = 0.0
    flip: bool = False          # look the OTHER way across the cut line


@dataclass
class Beam:
    """An RCC beam over the walls. `(x1,y1)-(x2,y2)` is its centre-line (feet);
    width is the plan thickness (default 230 mm), depth the section height."""
    tag: str = ""
    x1: float = 0.0
    y1: float = 0.0
    x2: float = 0.0
    y2: float = 0.0
    width_mm: float = 230.0
    depth_mm: float = 300.0

    @property
    def length(self) -> float:
        import math
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)


@dataclass
class Column:
    """A structural column, drawn solid. `x, y` is its CENTRE (feet). A square
    or rectangular column uses w x h; a round one uses w as its diameter."""
    x: float
    y: float
    shape: Literal["square", "rectangular", "round"] = "square"
    w: float = 1.0              # size in x, feet (diameter if round)
    h: float = 1.0              # size in y, feet (ignored if round)
    tag: str = ""               # C1, C2 …
    room: str = ""
    note: str = ""

    @property
    def centre(self) -> tuple[float, float]:
        return (self.x, self.y)


@dataclass
class Furniture:
    """One piece, placed. `kind` indexes the catalogue in furniture.py."""
    kind: str
    x: float                    # bottom-left of the footprint, feet
    y: float
    w: float                    # extent in x
    h: float                    # extent in y
    room: str = ""
    tag: str = ""               # F1, F2 …
    facing: Literal["N", "S", "E", "W"] = "N"   # the side it is used from
    angle: float = 0.0          # degrees anticlockwise about the piece centre
    zone: str = ""              # compass zone it sits in
    verdict: str = ""           # COMPLIES / DEVIATES
    reason: str = ""
    note: str = ""
    chairs: int = 0             # dining: seat count (0 = the kind's default)
    # printed size (feet). The drawn box may be stretched to the room the way
    # the sketch drew it, while the NUMBER stays the room-label truth. 0 = the
    # drawn size IS the printed size.
    size_w: float = 0.0
    size_h: float = 0.0

    @property
    def centre(self) -> tuple[float, float]:
        return (self.x + self.w / 2, self.y + self.h / 2)


@dataclass
class ElecPoint:
    """One electrical point — a fixture, a fan, a board, an AC, a DB.

    `code` is the legend code (SL, PL, CF, EF, AC, SB, DB…); `tag` is the
    drawing number in the prompt's format, LIV-SL-01.
    """
    code: str
    x: float
    y: float
    room: str = ""
    tag: str = ""
    watts: float = 0.0
    height_mm: float = 0.0          # above FFL; 0 = ceiling
    circuit: str = ""               # L1, P1, AC1, GYS1 …
    angle: float = 0.0
    size: float = 0.0               # feet; fans use their sweep
    controls: list = field(default_factory=list)   # boards: fixture tags
    note: str = ""
    visible: bool = True

    @property
    def is_light(self) -> bool:
        return self.code in ("SL", "ASL", "PL", "CSL", "CV", "WL", "BWL",
                             "HL", "CH", "ML", "STL", "TR")


@dataclass
class PlumbPoint:
    """One plumbing point — a valve, a rose, a trap, a chamber, a pit.

    `code` keys the key-note text (SR, SM, FT, WC, BAV, SKV, GT, IC, RWP …);
    `key` is the numbered circle actually drawn on the plan, so a wet room
    carries a circle and nothing else.
    """
    code: str
    x: float
    y: float
    room: str = ""
    tag: str = ""
    key: int = 0                    # the keynote circle number
    height_mm: float = 0.0          # above FFL
    system: str = ""                # CW | HW | SOIL | WASTE | RW
    dia_mm: float = 0.0
    cover_m: float = 0.0            # chambers: cover level
    invert_m: float = 0.0           # chambers: invert level
    # where the keynote circle sits relative to the fitting — spread by the
    # layout so two circles never touch (STEP 3E)
    key_dx: float = 0.0
    key_dy: float = 1.05
    note: str = ""
    visible: bool = True


@dataclass
class PlumbRun:
    """A pipe run, as a polyline so its length — and therefore its fall — is
    computed rather than guessed."""
    system: str                     # CW | HW | SOIL | WASTE | RW
    pts: list = field(default_factory=list)     # [(x, y), …] in feet
    dia_mm: float = 0.0
    slope: float = 0.0              # 1:slope, 0 = pressurised (no fall)
    note: str = ""
    visible: bool = True

    @property
    def length_ft(self) -> float:
        import math
        return sum(math.dist(a, b) for a, b in zip(self.pts, self.pts[1:]))


@dataclass
class FloorSpec:
    """The flooring of one room — everything editable per room. The tile grid
    itself is regenerated from this at draw time, so changing a size or a
    spacer redraws the whole room and re-totals the quantities."""
    room: str = ""
    rx: float = 0.0                 # a point inside the room (duplicate names)
    ry: float = 0.0
    material: str = "tile"          # tile | marble | wood | granite
    finish: str = ""                # matt / polished / anti-skid …
    tile_w: float = 600.0           # mm, along x
    tile_h: float = 600.0           # mm, along y
    spacer_mm: float = 2.0          # joint width; 0 = butt-jointed
    start: str = "symmetry"         # symmetry | entry | corner-sw … start rule
    start_dx: float = 0.0           # manual origin nudge, feet
    start_dy: float = 0.0
    skirting_mm: float = 75.0       # 0 = none (wet rooms use dado)
    skirting_type: str = "surface"
    drop_mm: float = 0.0            # finished level vs FFL (negative = down)
    junction_drop: bool = True      # show a tile drop / threshold at the door
    code: str = ""                  # legend code, VT-01 …
    visible: bool = True


@dataclass
class Circuit:
    """A final circuit on the DB."""
    id: str                         # L1, P1, AC1 …
    kind: str = "light"             # light | power | ac | geyser
    description: str = ""
    rooms: list = field(default_factory=list)
    points: int = 0
    load_w: float = 0.0
    mcb: str = ""
    wire: str = ""


@dataclass
class DimChain:
    axis: Literal["top", "bottom", "left", "right"] = "top"
    at: float = 0.0             # offset from the building, feet
    ticks: list[float] = field(default_factory=list)   # centre-line stations
    # absolute position of the dimension line (feet). When set, the chain is
    # drawn HERE (beside an internal wall) instead of out on the building edge.
    # For a horizontal chain `base` is the y of the line; for a vertical one, x.
    base: float | None = None


@dataclass
class TitleBlock:
    project: str = ""
    plan_name: str = "GROUND FLOOR PLAN"
    plot_size: str = ""
    scale: str = "1:50 @ A3"
    wall_note: str = "WALLS: 9\" EXTERNAL, 4\" PARTITION UNLESS NOTED"
    revision: str = "R0"
    drawn_by: str = ""
    date: str = ""
    client: str = ""            # the practice sheet names the client
    drawing_no: str = "01"


@dataclass
class Plan:
    walls: list[Wall] = field(default_factory=list)
    rooms: list[Room] = field(default_factory=list)
    openings: list[Opening] = field(default_factory=list)
    columns: list[Column] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    beams: list[Beam] = field(default_factory=list)
    struct: dict = field(default_factory=dict)   # rebar / grades for framing
    section_params: dict[str, Any] = field(default_factory=dict)
    stairs: list[Stair] = field(default_factory=list)
    steps: list[Steps] = field(default_factory=list)
    furniture: list[Furniture] = field(default_factory=list)
    elec: list[ElecPoint] = field(default_factory=list)
    circuits: list[Circuit] = field(default_factory=list)
    plumb: list[PlumbPoint] = field(default_factory=list)
    pipes: list[PlumbRun] = field(default_factory=list)
    flooring: list[FloorSpec] = field(default_factory=list)
    # raw geometry imported from a DXF, drawn VERBATIM (exact trace) — each
    # item {"t": line|poly|arc|text, …, "layer"}. When present, the engine
    # reproduces the DXF as-is and does not thicken walls or re-label rooms.
    raw: list = field(default_factory=list)
    dims: list[DimChain] = field(default_factory=list)
    autodim: bool = False            # draw automatic internal (clear) dimensions
    title: TitleBlock = field(default_factory=TitleBlock)
    north_deg: float = 90.0          # bearing of North on the sheet, 90 = up
    plot: dict[str, Any] | None = None   # {"x","y","w","h"} plot line, optional
    notes: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)

    # ---- serialisation -------------------------------------------------
    def to_json(self, indent: int = 2) -> str:
        return json.dumps(asdict(self), indent=indent)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Plan":
        def mk(cls, item):
            fields = {f for f in cls.__dataclass_fields__}
            return cls(**{k: v for k, v in item.items() if k in fields})

        p = Plan()
        p.walls = [mk(Wall, w) for w in d.get("walls", [])]
        for r in d.get("rooms", []):
            room = mk(Room, r)
            # A shaft read as a plain open area would lose its enclosing walls,
            # so recognise the usual names when the reading does not say.
            if room.open_area and "void" not in r and _looks_like_shaft(room.name):
                room.void = True
            p.rooms.append(room)
        for o in d.get("openings", []):
            op = mk(Opening, o)
            sw = o.get("swing")
            op.swing = mk(Swing, sw) if isinstance(sw, dict) else None
            # Older plans said type "door" with leaves/sliding beside it.
            # Fold that into the single/double/sliding type.
            if op.type == "door":
                if o.get("sliding"):
                    op.type = "sliding_door"
                elif int(o.get("leaves") or 0) >= 2 \
                        or op.width_mm > DOUBLE_DOOR_MM:
                    op.type = "double_door"
                else:
                    op.type = "single_door"
            p.openings.append(op)
        for s in d.get("stairs", []):
            st = mk(Stair, s)
            # older plans said landing_at / flights instead of turn_side / type
            if "turn_side" not in s and s.get("landing_at"):
                st.turn_side = s["landing_at"]
            if "type" not in s:
                st.type = "U" if int(s.get("flights", 2)) >= 2 else "straight"
            p.stairs.append(st)
        for s in d.get("steps", []):
            st = mk(Steps, s)
            st.levels = [str(v) for v in (s.get("levels") or [])]
            p.steps.append(st)
        p.columns = [mk(Column, c) for c in d.get("columns", [])]
        p.sections = [mk(Section, s) for s in d.get("sections", [])]
        p.beams = [mk(Beam, b) for b in d.get("beams", [])]
        p.struct = dict(d.get("struct") or {})
        p.section_params = dict(d.get("section_params") or {})
        p.furniture = [mk(Furniture, f) for f in d.get("furniture", [])]
        # NOTE: room-fit clamping happens ONCE in the client's own data
        # (app.js clampFurniture) — never here at render time, or the drawn
        # sheet and the client's gizmo/labels drift apart.
        for e in d.get("elec", []):
            pt = mk(ElecPoint, e)
            pt.controls = list(e.get("controls") or [])
            p.elec.append(pt)
        for c in d.get("circuits", []):
            ck = mk(Circuit, c)
            ck.rooms = list(c.get("rooms") or [])
            p.circuits.append(ck)
        p.plumb = [mk(PlumbPoint, q) for q in d.get("plumb", [])]
        for r in d.get("pipes", []):
            run = mk(PlumbRun, r)
            run.pts = [tuple(pt) for pt in (r.get("pts") or [])]
            p.pipes.append(run)
        p.flooring = [mk(FloorSpec, s) for s in d.get("flooring", [])]
        p.raw = list(d.get("raw", []))
        p.dims = [mk(DimChain, c) for c in d.get("dims", [])]
        p.autodim = bool(d.get("autodim", False))
        t = d.get("title") or {}
        p.title = mk(TitleBlock, t) if isinstance(t, dict) else TitleBlock()
        p.north_deg = float(d.get("north_deg", 90.0))
        p.plot = d.get("plot")
        p.notes = list(d.get("notes", []))
        p.assumptions = list(d.get("assumptions", []))
        return p

    @staticmethod
    def load(path: str) -> "Plan":
        with open(path, "r", encoding="utf-8") as fh:
            return Plan.from_dict(json.load(fh))

    # ---- lookups -------------------------------------------------------
    def wall(self, wid: str) -> Wall | None:
        return next((w for w in self.walls if w.id == wid), None)

    def room(self, name: str) -> Room | None:
        n = (name or "").strip().lower()
        return next((r for r in self.rooms if r.name.strip().lower() == n), None)

    def extents(self) -> tuple[float, float, float, float]:
        xs, ys = [], []
        for w in self.walls:
            xs += [w.x1, w.x2]
            ys += [w.y1, w.y2]
        for r in self.rooms:
            xs += [r.x, r.x + r.w]
            ys += [r.y, r.y + r.h]
        if self.plot:
            xs += [self.plot["x"], self.plot["x"] + self.plot["w"]]
            ys += [self.plot["y"], self.plot["y"] + self.plot["h"]]
        if not xs:
            return (0.0, 0.0, 1.0, 1.0)
        return (min(xs), min(ys), max(xs), max(ys))
