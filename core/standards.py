"""The drafting rulebook, as data.

Every figure here comes from Sketch_to_Plan_Drafting_Rulebook.docx (NBC 2016,
IS 962 / 4021 / 1038, COA practice). Keeping them in one place means the checks
and the defaults can never drift apart, and a rule change is one edit.

Section numbers refer to that document.
"""

from __future__ import annotations

MM_FT = 1.0 / 304.8
SQM_SQFT = 10.7639

# -- §1 walls -----------------------------------------------------------
EXTERNAL_MM = 230.0                 # 9"  brick masonry
PARTITION_MM = 115.0                # 4.5"
PLASTER_INT_MM = 12.0
PLASTER_EXT_MM = 18.0
PARAPET_MIN_MM = 115.0
PARAPET_HEIGHT_MM = 1000.0

EXTERNAL_IN = EXTERNAL_MM / 25.4     # 9.06"
PARTITION_IN = PARTITION_MM / 25.4   # 4.53"

# -- §2 doors -----------------------------------------------------------
DOOR_LINTEL_MM = 2100.0
HINGE_CLEAR_MIN_MM = 150.0          # frame clear of the adjoining wall face
HINGE_CLEAR_MAX_MM = 230.0
DOOR_MIN_W_MM = {                   # by what the door serves
    "main": 1000.0,
    "internal": 900.0,
    "toilet": 750.0,
}
DOOR_MIN_H_MM = 2000.0

# -- §3 windows, §4 ventilators ----------------------------------------
WINDOW_SILL_MM = 900.0
WINDOW_LINTEL_MM = 2100.0
KITCHEN_SILL_MM = 1050.0            # to clear the counter (1050–1200)
VENT_SILL_MM = 1800.0               # 1800–2100
VENT_LINTEL_MM = 2400.0             # 2100–2400
LIGHT_VENT_RATIO_MIN = 1.0 / 10.0   # openable area / floor area (hot-dry)
LIGHT_VENT_RATIO_AIM = 1.0 / 6.0
TOILET_VENT_AREA_MIN_SQM = 0.3

# -- §7 NBC minimum room sizes -----------------------------------------
# name -> (min area m2, min width m).  Matched on the words in a room's name.
ROOM_MINIMA = {
    "habitable": (9.5, 2.4),        # bedroom, living, drawing, dining, office
    "second habitable": (7.5, 2.1),
    "kitchen": (5.0, 1.8),
    "kitchen-cum-dining": (7.5, 2.1),
    "bathroom": (1.8, 1.2),
    "wc": (1.1, 0.9),
    "bath+wc": (2.8, 1.2),
    "store": (3.0, 0.0),
    "garage": (12.5, 2.5),
    "passage": (0.0, 0.9),
    "staircase": (0.0, 0.9),
}

HABITABLE_WORDS = ("bed", "living", "drawing", "dining", "hall", "study",
                   "office", "guest", "master")
WET_WORDS = ("toilet", "bath", "w.c", "wc", "washroom")
KITCHEN_WORDS = ("kitchen", "pantry")
PASSAGE_WORDS = ("passage", "corridor", "lobby", "foyer")
STORE_WORDS = ("store", "storage", "utility")
OPEN_WORDS = ("terrace", "balcony", "verandah", "veranda", "court", "yard",
              "parking", "planter", "porch", "setback", "open")

PASSAGE_MIN_W_M = 0.9
STAIR_MIN_W_M = 0.9

# -- §8 staircase -------------------------------------------------------
RISER_MAX_MM = 190.0
TREAD_MIN_MM = 250.0
COMFORT_MIN_MM = 600.0              # 2R + T
COMFORT_MAX_MM = 640.0
HEADROOM_MIN_MM = 2200.0
HANDRAIL_MM = 900.0

# -- §10 presentation ---------------------------------------------------
NOTE_LEVELS = "PL +450, SL +900, LL +2100, SLAB +3000 ABOVE FFL"


def classify(name: str) -> str:
    """Which rulebook category a room name falls into."""
    n = (name or "").strip().lower()
    if any(w in n for w in OPEN_WORDS):
        return "open"
    if any(w in n for w in KITCHEN_WORDS):
        return "kitchen"
    if any(w in n for w in WET_WORDS):
        return "wet"
    if any(w in n for w in PASSAGE_WORDS):
        return "passage"
    if any(w in n for w in STORE_WORDS):
        return "store"
    if "stair" in n:
        return "stair"
    if any(w in n for w in HABITABLE_WORDS):
        return "habitable"
    return "other"


def default_levels(op_type: str, room_name: str = "") -> tuple[float, float]:
    """(sill_mm, lintel_mm) the rulebook expects, for filling a blank."""
    if op_type in ("door", "single_door", "double_door", "sliding_door"):
        return 0.0, DOOR_LINTEL_MM
    if op_type == "vent":
        return VENT_SILL_MM, VENT_LINTEL_MM
    if op_type == "window":
        if classify(room_name) == "kitchen":
            return KITCHEN_SILL_MM, WINDOW_LINTEL_MM
        return WINDOW_SILL_MM, WINDOW_LINTEL_MM
    return 0.0, 0.0


def default_height(op_type: str) -> float:
    if op_type in ("door", "single_door", "double_door", "sliding_door"):
        return 2100.0
    if op_type == "vent":
        return 600.0
    if op_type == "window":
        return 1200.0
    return 0.0


def fmt_mm(v: float) -> str:
    return f"{v:.0f}" if v else "—"
