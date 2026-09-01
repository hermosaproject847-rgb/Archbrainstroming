"""Furniture catalogue, clearances and Vaastu rules.

Every figure comes from MASTER_PROMPT_Furniture_Layout_Vaastu_REV2 (STEP 3).
Sizes are held in MILLIMETRES because that is how the standards are written;
the drawing works in feet, so `ft()` converts at the boundary.

Nothing here places anything — this is the rulebook. `layout.py` does the
placing and `validate` proves it.
"""

from __future__ import annotations

MM = 1.0 / 304.8            # mm -> feet


def ft(mm: float) -> float:
    return mm * MM


# ---------------------------------------------------------------- A. sizes
# name -> (depth mm, length mm). Depth is the dimension against the wall.
CATALOGUE = {
    # beds
    "bed_single":     (1900, 900),
    "bed_double":     (1900, 1350),
    "bed_queen":      (2000, 1500),
    "bed_king":       (2000, 1800),
    "bedside":        (450, 450),
    # storage
    "wardrobe":       (600, 1800),
    "dresser":        (500, 1050),
    "study_table":    (600, 1200),
    "sideboard":      (400, 1050),
    "shoe_rack":      (350, 500),
    # living
    "sofa_3":         (850, 1950),
    "sofa_2":         (850, 1500),
    "armchair":       (750, 750),
    "coffee_table":   (600, 1100),
    "tv_unit":        (450, 1500),
    # dining
    "dining_2":       (700, 750),          # compact / folding 2-seat
    "dining_4":       (900, 1200),
    "dining_6":       (900, 1800),
    "dining_8":       (1000, 2400),
    "chair":          (450, 450),
    # kitchen
    "counter":        (600, 0),        # length follows the wall
    "fridge":         (700, 700),
    "washing_machine": (600, 600),
    # wet
    "wc":             (700, 400),
    "basin":          (500, 600),
    "shower":         (900, 900),
}

STOOL = (400, 400)

# --------------------------------------------------------- B. clearances
CLEAR = {
    "bed_side":        600,      # 750 preferred
    "bed_side_pref":   750,
    "wardrobe_front":  600,
    "chair_pullback":  750,      # measured over the CHAIR's width (REV 2)
    "sofa_coffee_min": 350,
    "sofa_coffee_max": 450,
    "route_main":      750,      # 900 preferred
    "route_main_pref": 900,
    "route_spur":      600,
    "wc_side":         380,      # centre line to any wall or fixture
    "wc_front":        600,
    "basin_side":      400,
    "basin_front":     700,
    "shower_min":      900,
}

WALL_GAP = 25                    # furniture sits this far off a finished face
NE_KEEP_CLEAR = 100              # 75–100 gap off N/E walls for beds

MICRO_TIE_MM = 150               # never draw a tie shorter than this (REV 2)


# ------------------------------------------------------------- C. Vaastu
# Compass zones as (name, from_deg, to_deg), measured anticlockwise from East
# in the drawing's own frame once north_deg is applied.
ZONES = ("E", "NE", "N", "NW", "W", "SW", "S", "SE")


def zone_of(dx: float, dy: float, north_deg: float = 90.0) -> str:
    """Which compass zone a point lies in, relative to a room's centre."""
    import math
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return "C"
    ang = math.degrees(math.atan2(dy, dx))          # from +x, anticlockwise
    # rotate so that north_deg becomes 90 (up)
    ang = (ang - (north_deg - 90.0)) % 360.0
    idx = int(((ang + 22.5) % 360.0) // 45.0)
    return ("E", "NE", "N", "NW", "W", "SW", "S", "SE")[idx]


# piece -> (preferred zones, forbidden zones, note)
VAASTU = {
    "bed":        (("S", "SW", "W"), ("N",),
                   "head south is best; never north"),
    "wardrobe":   (("S", "W", "SW"), ("NE",),
                   "heavy storage south/west, SW ideal, never NE"),
    "dresser":    (("N", "E"), (),
                   "dresser/mirror on the north or east wall"),
    "study_table": (("N", "E"), (),
                    "the user faces east or north"),
    "sofa":       (("W", "S", "SW"), (),
                   "sofa on the west/south wall facing east/north"),
    "tv_unit":    (("SE", "E"), (),
                   "television on the south-east or east wall"),
    "dining":     (("W", "NW"), (),
                   "dining toward the west/north-west of its zone"),
    "hob":        (("SE",), ("NE",), "hob south-east, the cook faces east"),
    "sink":       (("NE", "N", "E"), (),
                   "sink north-east"),
    "fridge":     (("S", "SW", "W"), ("NE",),
                   "fridge south/south-west/west, never NE"),
    "wc":         (("W", "NW", "S"), (),
                   "pan in the west/north-west/south part, seat axis N–S"),
    "basin":      (("N", "NE", "E"), (),
                   "basin on the north/north-east/east wall"),
    "shower":     (("N", "NE", "E"), (),
                   "shower north/north-east/east"),
}

# heaviest masses SW, NE and the Brahmasthan (centre) light and open
KEEP_LIGHT = ("NE",)


def vaastu_check(kind: str, zone: str) -> tuple[str, str]:
    """(verdict, reason) for a piece sitting in `zone`."""
    rule = VAASTU.get(kind)
    if not rule:
        return "n/a", ""
    good, bad, note = rule
    if zone in bad:
        return "DEVIATES", f"{zone} — {note}"
    if not good or zone in good:
        return "COMPLIES", note
    return "DEVIATES", f"in {zone}; {note}"


# ------------------------------------------------- room -> what goes in it
ROOM_KIT = {
    "bedroom_master": ["bed_queen", "bedside", "bedside", "wardrobe",
                       "dresser"],
    "bedroom":        ["bed_double", "bedside", "wardrobe", "study_table"],
    "living":         ["sofa_3", "sofa_2", "coffee_table", "tv_unit"],
    "dining":         ["dining_6"],
    "kitchen":        ["counter", "fridge"],
    "wet":            ["wc", "basin", "shower"],
    "study":          ["study_table", "wardrobe"],
}


def kit_for(name: str, area_sqft: float) -> list[str]:
    """What a room of this name and size should hold."""
    n = (name or "").lower()
    if any(w in n for w in ("toilet", "bath", "w.c", "wc", "washroom")):
        return ["wc", "basin"] + (["shower"] if area_sqft >= 30 else [])
    if any(w in n for w in ("kitchen", "pantry")):
        return ROOM_KIT["kitchen"]
    if "dining" in n:
        return ROOM_KIT["dining"]
    if any(w in n for w in ("living", "drawing", "hall", "lounge")):
        return ROOM_KIT["living"]
    if any(w in n for w in ("study", "office")):
        return ROOM_KIT["study"]
    if "bed" in n:
        if "master" in n or area_sqft >= 140:
            return ROOM_KIT["bedroom_master"]
        return ROOM_KIT["bedroom"]
    if any(w in n for w in ("store", "utility")):
        return ["shoe_rack"]
    return []


LABEL = {
    "bed_single": "SINGLE BED", "bed_double": "DOUBLE BED",
    "bed_queen": "QUEEN BED", "bed_king": "KING BED",
    "bedside": "BEDSIDE", "wardrobe": "WARDROBE", "dresser": "DRESSER",
    "study_table": "STUDY TABLE", "sideboard": "SIDEBOARD",
    "shoe_rack": "SHOE RACK", "sofa_3": "SOFA 3-SEAT",
    "sofa_2": "SOFA 2-SEAT", "armchair": "ARMCHAIR",
    "coffee_table": "COFFEE TABLE", "tv_unit": "TV UNIT",
    "dining_2": "FOLDING DINING 2", "dining_4": "DINING 4",
    "dining_6": "DINING 6", "dining_8": "DINING 8",
    "chair": "CHAIR", "counter": "COUNTER", "fridge": "FRIDGE",
    "washing_machine": "W/M", "wc": "WC", "basin": "BASIN",
    "shower": "SHOWER", "stool": "STOOL",
}


# ------------------------------------------- the printed size, label-true
def _label_ft(s: str) -> float | None:
    """One side of a room size label -> feet. \"6'-0\\\"\" or bare mm/ft."""
    import re
    s = (s or "").strip()
    m = re.match(r"^(\d+)\s*'\s*-?\s*(\d+(?:\.\d+)?)?", s)
    if m:
        return float(m.group(1)) + (float(m.group(2) or 0) / 12.0)
    m = re.match(r"^(\d+(?:\.\d+)?)", s)
    if m:
        v = float(m.group(1))
        return v / 304.8 if v > 50 else v
    return None


def room_scale(plan, f) -> tuple[float, float]:
    """The room-local drawn/label scale for a piece, per STORED axis.

    The sketch reads a room a touch bigger than its printed size label, so
    everything drawn inside it carries the same stretch. Dividing a drawn
    size by this factor gives the size the sheet PRINTS; multiplying a typed
    size by it gives the drawn box. Rotation is folded in, so the factors
    apply directly to f.w / f.h. (1, 1) when the piece is not wholly inside
    one labelled room, or the label reads smaller than sane.
    """
    import re
    rot = abs(((float(f.angle or 0) % 180) + 180) % 180 - 90) < 45
    cx, cy = f.centre
    dw, dh = (f.h, f.w) if rot else (f.w, f.h)   # drawn extents
    rm = None
    for r in plan.rooms:
        if r.void:
            continue
        if (r.x - 0.6 <= cx - dw / 2 and cx + dw / 2 <= r.x + r.w + 0.6 and
                r.y - 0.6 <= cy - dh / 2 and cy + dh / 2 <= r.y + r.h + 0.6):
            rm = r
            break
    if rm is None:
        return 1.0, 1.0
    parts = re.split(r"[xX×]", str(getattr(rm, "size_label", "") or ""))
    lw = _label_ft(parts[0]) if parts else None
    lh = _label_ft(parts[1]) if len(parts) > 1 else None
    sx = rm.w / lw if (lw and lw < rm.w) else 1.0
    sy = rm.h / lh if (lh and lh < rm.h) else 1.0
    # a misparsed label must not warp sizes — only a mild read-stretch is real
    if not (1.0 <= sx <= 1.6):
        sx = 1.0
    if not (1.0 <= sy <= 1.6):
        sy = 1.0
    return (sy, sx) if rot else (sx, sy)         # stored-axis order


def printed_wh(plan, f) -> tuple[float, float]:
    """The size a piece PRINTS (sheet text / schedule / legend), in feet.

    Drawn size divided by the room's own drawn/label scale — so a wardrobe
    drawn wall-to-wall in a room that reads 1670 against a 1372 label prints
    exactly 1372, and the number always tracks the drawn box. Runs at DRAW
    time, so it holds for any client state, old saves included.
    """
    kw, kh = room_scale(plan, f)
    return float(f.w) / kw, float(f.h) / kh


# ------------------------------------------------ the catalogue, grouped
# What the "add furniture" dialog offers: category -> the pieces in it, in the
# order a designer would look for them. Every entry draws its own symbol.
CATEGORIES = [
    ("Beds", ["bed_single", "bed_double", "bed_queen", "bed_king",
              "bedside"]),
    ("Seating", ["sofa_3", "sofa_2", "armchair", "chair", "stool"]),
    ("Tables", ["coffee_table", "dining_2", "dining_4", "dining_6", "dining_8",
                "study_table", "dresser"]),
    ("Storage", ["wardrobe", "sideboard", "tv_unit", "shoe_rack"]),
    ("Kitchen", ["counter", "fridge", "washing_machine"]),
    ("Sanitary", ["wc", "basin", "shower"]),
]


def catalogue() -> list[dict]:
    """Every piece the software can draw, grouped, with its standard size."""
    out = []
    for cat, kinds in CATEGORIES:
        items = []
        for k in kinds:
            dep, ln = CATALOGUE.get(k, (600, 900))
            items.append({
                "kind": k,
                "label": LABEL.get(k, k.replace("_", " ").upper()),
                "depth_mm": dep,
                "length_mm": ln or 1800,      # counters take the wall's length
                "depth_ft": round(ft(dep), 3),
                "length_ft": round(ft(ln or 1800), 3),
                "vaastu": VAASTU.get(family(k), ((), (), ""))[2],
            })
        out.append({"category": cat, "items": items})
    return out


def family(kind: str) -> str:
    """The Vaastu family a catalogue item belongs to."""
    if kind.startswith("bed_"):
        return "bed"
    if kind.startswith("sofa"):
        return "sofa"
    if kind.startswith("dining"):
        return "dining"
    return kind
