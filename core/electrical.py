"""Electrical and lighting standards, as data.

From MASTER_PROMPT_Electrical_Lighting_Design (NBC 2016 Part 8 Sec 2, IS 732,
IS 3646, IS 1646, IS 8828, IS 12640, ECBC/Eco-Niwas, CEA).

Nothing here places anything — `eleclayout.py` does that and `validate` proves
it. Millimetres throughout, because that is how the standards are written.
"""

from __future__ import annotations

MM = 1.0 / 304.8


def ft(mm: float) -> float:
    return mm * MM


# ---------------------------------------------- 1.1 fixture palette
# code -> (description, watts, CCT, symbol key)
FIXTURES = {
    "SL":  ("COB spotlight, recessed", 9, "3000K", "spot"),
    "ASL": ("Adjustable spotlight", 9, "3000K", "spot_adj"),
    "PL":  ("LED panel light, recessed", 15, "3000-4000K", "panel"),
    "CSL": ("Ceiling surface light", 18, "3000K", "surface"),
    "CV":  ("Cove LED strip, indirect", 9, "2700-3000K", "cove"),
    "WL":  ("Wall light / sconce", 7, "3000K", "wall"),
    "BWL": ("Bedside wall light", 7, "2700K", "wall"),
    "HL":  ("Hanging / pendant light", 20, "3000K", "pendant"),
    "CH":  ("Chandelier", 60, "2700K", "chandelier"),
    "ML":  ("Mirror / vanity light", 10, "4000K", "mirror"),
    "STL": ("Step / foot light", 2, "3000K", "step"),
    "TR":  ("Magnetic / profile track", 15, "3000K", "track"),
    "CF":  ("Ceiling fan with regulator", 75, "", "fan"),
    "EF":  ("Exhaust fan", 40, "", "exhaust"),
    "AC":  ("AC indoor unit", 0, "", "ac"),
    "SB":  ("Switchboard", 0, "", "board"),
    "DB":  ("Distribution board", 0, "", "db"),
}

LUMEN_PER_W = 100.0        # LED, typical
UF = 0.55                  # utilisation factor 0.5–0.6
MF = 0.8                   # maintenance factor


# ------------------------------------- 1.2 room-wise lux targets (IS 3646)
# category -> (avg lux, task lux, CCT, mandatory layers)
LUX = {
    "living":    (225, 300, "2700-3000K", ["PL", "SL", "CH"]),
    "dining":    (225, 300, "2700-3000K", ["HL", "SL"]),
    "master":    (125, 200, "2700-3000K", ["CV", "BWL", "SL"]),
    "bedroom":   (150, 300, "3000K",      ["PL", "SL"]),
    "kitchen":   (275, 300, "4000K",      ["PL", "SL"]),
    "wet":       (175, 300, "3000-4000K", ["CSL", "ML", "EF"]),
    "study":     (400, 500, "4000K",      ["PL"]),
    "passage":   (100, 100, "3000K",      ["SL"]),
    "stair":     (125, 150, "3000K",      ["CSL", "STL"]),
    "pooja":     (150, 150, "2700K",      ["SL", "CV"]),
    "open":      (100, 100, "3000K",      ["CSL"]),
    "store":     (100, 100, "3000K",      ["CSL"]),
    "other":     (150, 200, "3000K",      ["CSL"]),
}

LPD_RESIDENTIAL = 8.0      # W/m2, ECBC ceiling
LPD_OFFICE = 10.8


# ---------------------------------------- 1.3 ceiling fan + light placement
FAN_SWEEP = ((8.0, 900), (12.0, 1200), (1e9, 1400))   # area m2 -> sweep mm
FAN_TWO_IF_SIDE_M = 4.5
FAN_TWO_IF_AREA_M2 = 17.0
FAN_MIN_SPACING_MM = 2400
FAN_BLADE_CLEAR_MM = 600           # blade tip to any wall
FAN_TO_PENDANT_MM = 1200
FAN_CLEAR_ZONE_MM = 600            # no fixture within this of a fan centre
FAN_HEIGHT_MM = 2400

LIGHT_EDGE_MM = 375                # first row 300–450 from finished wall face
LIGHT_SPACING_MM = 1050            # 900–1200 c/c
PANEL_EDGE_MM = 600
PANEL_SPACING_MM = 1350            # 1200–1500 for offices/kitchens


def fan_sweep(area_m2: float) -> int:
    for limit, sweep in FAN_SWEEP:
        if area_m2 <= limit:
            return sweep
    return 1400


def fan_count(w_m: float, h_m: float) -> int:
    area = w_m * h_m
    if max(w_m, h_m) > FAN_TWO_IF_SIDE_M or area > FAN_TWO_IF_AREA_M2:
        return 2
    return 1


def lumen_count(lux: float, area_m2: float, watt: float) -> int:
    """N = (E x A) / (F x UF x MF) — the fixture count the target needs."""
    flux = watt * LUMEN_PER_W
    if flux <= 0:
        return 0
    n = (lux * area_m2) / (flux * UF * MF)
    return max(1, int(n + 0.999))


# -------------------------------------- 2.x switchboard and point heights
# Every light the plan numbers in one L-series — ceiling AND wall mounted, so
# the switch-loop schedule can name each fitting it loops through.
LIGHT_CODES = ("SL", "ASL", "PL", "CSL", "CV", "WL", "BWL", "HL", "CH",
               "ML", "STL", "TR")

H_ENTRY_BOARD = 1200               # every room's first board, to centre
H_BEDSIDE_BOARD = 675              # 600–750
H_SOFA_SIDE = 300                  # skirting level
H_TV_BOARD = 1000                  # 900–1100
H_AC_POINT = 2175                  # 2100–2250
H_KITCHEN_COUNTER = 1150           # 1100–1200, counter at 850
H_CHIMNEY = 2025
H_FRIDGE = 1200
H_GEYSER = 1950                    # 1800–2100
H_MIRROR_LIGHT = 2025              # 1950–2100
H_EXHAUST = 2100
H_MIRROR_POINT = 1800
H_DOORBELL = 1200
H_DB_BOTTOM = 1500                 # bottom 1500, top <= 1800
BOARD_FROM_FRAME_MM = 250          # 200–300 from the door frame, lock side


# ------------------------------------------- 3. circuits and load (IS 732)
CKT_LIGHT_MAX_W = 800
CKT_LIGHT_MAX_PTS = 10
CKT_POWER_MAX_W = 3000
CKT_POWER_MAX_PTS = 2
W_6A = 100                         # assumed load per 6A point
W_16A = 1200                       # 1000–1500
DIVERSITY = {"light": 0.75, "power": 0.5, "ac": 0.9, "fixed": 1.0}

MCB = {"light": "6A", "power": "16A", "ac": "20A", "geyser": "20A"}
WIRE = {"light": "1.5", "power": "2.5", "ac": "4.0", "geyser": "4.0"}
RCCB = "30 mA"


# ------------------------------------------------ 5. air conditioning
SQFT_PER_TR = 600.0                # residential, 10 ft ceiling
TR_SIZES = (0.8, 1.0, 1.5, 2.0, 2.2)
AC_DIVERSITY = 0.75                # VRV/VRF, residential 0.7–0.75


def tonnage(area_sqft: float, west_or_south: bool = False,
            top_floor: bool = False) -> float:
    tr = area_sqft / SQFT_PER_TR
    if west_or_south:
        tr += 0.5
    if top_floor:
        tr *= 1.15
    for s in TR_SIZES:
        if tr <= s + 1e-6:
            return s
    return round(tr * 2) / 2


# --------------------------------------------------- 4.2 room codes
ROOM_CODE = {
    "living": "LIV", "dining": "DIN", "master": "MBR", "bedroom": "BR",
    "kitchen": "KIT", "wet": "TL", "study": "STD", "passage": "PAS",
    "stair": "STR", "pooja": "PJA", "open": "BAL", "store": "UTL",
    "other": "RM",
}


def classify(name: str) -> str:
    """Which lighting category a room falls into."""
    n = (name or "").strip().lower()
    if any(w in n for w in ("toilet", "bath", "w.c", "wc", "washroom")):
        return "wet"
    if any(w in n for w in ("kitchen", "pantry")):
        return "kitchen"
    if "dining" in n:
        return "dining"
    if any(w in n for w in ("living", "drawing", "lounge")):
        return "living"
    if any(w in n for w in ("study", "office")):
        return "study"
    if "master" in n and "bed" in n:
        return "master"
    if "bed" in n:
        return "bedroom"
    if any(w in n for w in ("passage", "corridor", "lobby", "foyer", "hall")):
        return "passage"
    if "stair" in n:
        return "stair"
    if any(w in n for w in ("pooja", "puja", "mandir")):
        return "pooja"
    if any(w in n for w in ("terrace", "balcony", "verandah", "veranda",
                            "court", "yard", "parking", "planter", "open")):
        return "open"
    if any(w in n for w in ("store", "utility")):
        return "store"
    return "other"


def code_for(name: str, seen: dict) -> str:
    """LIV, MBR, BR2, TL1 … — unique per room."""
    base = ROOM_CODE.get(classify(name), "RM")
    n = seen.get(base, 0) + 1
    seen[base] = n
    return base if n == 1 and base in ("LIV", "DIN", "MBR", "KIT",
                                       "STD", "PAS", "STR", "PJA") \
        else f"{base}{n}"
