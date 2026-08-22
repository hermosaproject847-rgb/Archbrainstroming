"""Plumbing, sanitary & drainage — the standards as data.

From `Plumbing_Master_Prompt.docx` (the final prompt), which is NBC 2016
Part 9 based, with IS 1172 (water supply requirements), IS 1742 (building
drainage), IS 2065 and the CPHEEO manual.

Nothing here is a guess: the demands, tank sizes, pump duty and rain-water
pipe counts are all COMPUTED by the functions at the foot of this file, and
every slope is the code figure the drawing has to print along its run.
"""

from __future__ import annotations

import math

# ---------------------------------------------------- §14 the seven systems
# code -> (label, drawing layer, material / size text, line style)
SYSTEMS = {
    "CW":    ("Cold water", "PLUMB-CW", "CPVC SDR 11 · 32/25/20/15", "solid"),
    "HW":    ("Hot water", "PLUMB-HW", "CPVC SDR 11 · 20/15, insulated",
              "dashed"),
    "SOIL":  ("Soil pipe", "PLUMB-SOIL", "UPVC SWR Type B · 110", "solid"),
    "WASTE": ("Waste pipe", "PLUMB-WASTE", "UPVC SWR Type B · 75/50", "solid"),
    "VENT":  ("Vent pipe", "PLUMB-VENT", "UPVC · 50/75, cowl 600 over terrace",
              "dashdot"),
    "STORM": ("Storm / RWP", "PLUMB-STORM", "UPVC · 110", "solid"),
    "ACD":   ("AC condensate", "PLUMB-ACD", "UPVC · 25/32 @ 1:50", "dashed"),
}

# ------------------------------------------------------- §12 pipe diameters
D_CW_MAIN, D_CW_DOWN, D_CW_BRANCH, D_CW_TAIL = 32, 25, 20, 15
D_HW_DOWN, D_HW_TAIL = 20, 15
D_SOIL = 110
D_WASTE_STACK, D_WASTE_BRANCH = 75, 50
D_VENT = 75
D_RWP = 110
D_ACD = 32
D_EXT_DRAIN = 160          # UG external 110/160

# ------------------------------- §4 fixture heights (mm from FFL) & remarks
FIXTURES = {
    # code: (name, height_mm, remark)
    "BASIN":  ("Wash basin rim", 825, "counter type, counter depth 500-600"),
    "PC":     ("Pillar cock / basin mixer", 850,
               "on counter deck, hot LEFT cold RIGHT"),
    "BAC":    ("Basin angle cocks (hot + cold)", 525,
               "below counter, 150-200 c/c, under the basin"),
    "BBT":    ("Basin bottle trap", 425, "32 CP bottle trap, waste to wall"),
    "WC":     ("WC (EWC) floor mounted", 0, "water inlet angle cock at 300"),
    "WCAC":   ("WC angle cock", 300, "2-way valve feeds cistern + faucet"),
    "HF":     ("Health faucet, 2-way bib cock", 525,
               "RIGHT-HAND side of the WC when seated"),
    "SH":     ("Shower head", 2100, "centred on the shower area"),
    "SMX":    ("Shower mixer / diverter", 975, "hot left cold right, 150 c/c"),
    "SAR":    ("Shower arm take-off", 1800, "riser concealed in a wall chase"),
    "GY":     ("Geyser", 1900, "bottom; unions + NRV on inlet, 15 A point"),
    "SINK":   ("Kitchen sink", 850, "counter"),
    "SKC":    ("Sink cock / wall mixer", 1075, "bottle trap below"),
    "WMT":    ("Washing machine tap", 1050, "dedicated nahani trap beside"),
    "GBC":    ("Garden bib cock", 525, "external wall / pedestal"),
    "NT":     ("Nahani trap", 0, "min 50 water seal, CP/SS jali"),
    "GT":     ("Gully trap", 0, "waste stacks only, before the chamber"),
    "IC":     ("Inspection chamber", 0, "benching + channel, SFRC/CI cover"),
    "CO":     ("Cleanout plug", 0, "base of every stack before it turns"),
    "KH":     ("Khurra (spout)", 0, "450 x 450 dished portion with grating"),
    "UGT":    ("Underground water tank", 0, "outside the footprint"),
    "PUMP":   ("Submersible pump", 0, "float switch + NRV at delivery"),
    "OHT":    ("Overhead tank", 0, "300 freeboard"),
    "SV":     ("Isolation valve", 0, "full-way, at every toilet/kitchen entry"),
}

# ------------------------------------------ §6 slope table (write on the run)
SLOPES = {
    ("SOIL", 110):  40.0,      # 1:40 adopted (min 1:60)
    ("WASTE", 75):  40.0,
    ("WASTE", 50):  30.0,
    ("EXT", 160):   100.0,     # external drain to IC / sewer, 1:100
    ("TERRACE", 0): 100.0,     # screed to khurra
    ("BATH", 0):    80.0,      # bathroom floor to nahani trap
    ("ACD", 32):    50.0,      # AC condensate, continuous fall
}


def slope_for(system: str, dia: float) -> float:
    """The code gradient for a run — 1:N."""
    if system == "SOIL":
        return SLOPES[("SOIL", 110)]
    if system == "WASTE":
        return SLOPES[("WASTE", 75)] if dia >= 75 else SLOPES[("WASTE", 50)]
    if system == "ACD":
        return SLOPES[("ACD", 32)]
    if system == "STORM":
        return SLOPES[("EXT", 160)]
    return 0.0


def slope_text(system: str, dia: float) -> str:
    """e.g. '110Ø SOIL @ 1:40' — §6 asks for this along every horizontal run."""
    s = slope_for(system, dia)
    name = SYSTEMS.get(system, (system,))[0].split()[0].upper()
    return f"{dia:g}Ø {name}" + (f" @ 1:{s:g}" if s else "")


# Routing-layout abbreviations (match the Orilite plumbing routing sheet):
# SWP = soil water pipe, WWP = waste water pipe, RWP = rain water pipe.
PIPE_ABBR = {"SOIL": "SWP", "WASTE": "WWP", "STORM": "RWP",
             "VENT": "VP", "ACD": "ACP", "CW": "CWP", "HW": "HWP"}


def pipe_label(system: str, dia: float) -> tuple[str, str]:
    """Two-line pipe tag as on the routing sheet: ('110Ø SWP', 'SLOPE 1:80')."""
    s = slope_for(system, dia)
    ab = PIPE_ABBR.get(system, system)
    return (f"{dia:g}Ø {ab}", f"SLOPE 1:{s:g}" if s else "")


# ------------------------------------------------------ §9 chamber sizing
def chamber_size(depth_mm: float) -> str:
    if depth_mm <= 600:
        return "450 x 600"
    if depth_mm <= 900:
        return "500 x 700"
    return "600 x 850"


IC_MAX_SPACING_M = 30.0        # §9 — intervals not exceeding 30 m
IC_MIN_DEPTH_MM = 300.0
SEWER_INVERT_M = -1.20         # assumed, flagged VERIFY
BATH_SUNK_MM = 275             # §15 recommend 250-300 sunken

# ------------------------------------------------------ §3 demand figures
LPCD_DOMESTIC = 90
LPCD_FLUSHING = 45
LPCD_TOTAL = LPCD_DOMESTIC + LPCD_FLUSHING          # 135
GARDEN_L_PER_SQM = 7.0                              # 6-8 L/sq.m/day
OCCUPANTS_DEFAULT = 6                               # standard bungalow 5-6
UG_DAYS = 1.5
FREEBOARD_MM = 300
PUMP_FILL_HOURS = 1.5
PUMP_RESIDUAL_HEAD_M = 3.0
PUMP_FRICTION_PC = 0.15

# §7 rain water
ROOF_PER_RWP_SQM = 42.0        # 100 dia serves ~40-45 sq.m
RWP_MIN = 2
RAIN_INTENSITY_MM_HR = 100

# garden taps
GARDEN_TAP_SPACING_M = 18.0    # every 15-20 m along the periphery


# ------------------------------------------------------------ calculations
def water_demand(occupants: int, garden_sqm: float) -> dict:
    """§3 — show the working."""
    dom = occupants * LPCD_DOMESTIC
    flush = occupants * LPCD_FLUSHING
    garden = garden_sqm * GARDEN_L_PER_SQM
    return {"occupants": occupants, "domestic_l": dom, "flushing_l": flush,
            "garden_l": garden, "total_l": dom + flush + garden,
            "garden_sqm": garden_sqm}


def _tank_dims(volume_l: float, depth_m: float = 1.5) -> tuple:
    """L x B x D in metres for a volume, with 300 freeboard on the depth."""
    vol_m3 = volume_l / 1000.0
    area = vol_m3 / depth_m
    side = math.sqrt(area / 1.5)            # a 1.5:1 rectangle reads better
    L, B = round(side * 1.5, 2), round(side, 2)
    return L, B, round(depth_m + FREEBOARD_MM / 1000.0, 2)


def tanks(demand: dict) -> dict:
    """UG tank 1-1.5 days total; OHT at least one day's domestic (+flushing
    where it is not a separate tank)."""
    total = demand["total_l"]
    ug_l = round(total * UG_DAYS / 100.0) * 100
    oht_l = round((demand["domestic_l"] + demand["flushing_l"]) / 100.0) * 100
    ugL, ugB, ugD = _tank_dims(ug_l, 1.8)
    ohL, ohB, ohD = _tank_dims(oht_l, 1.2)
    return {"ug_l": ug_l, "ug_dims": (ugL, ugB, ugD),
            "oht_l": oht_l, "oht_dims": (ohL, ohB, ohD),
            "days": UG_DAYS}


def pump(oht_l: float, static_lift_m: float) -> dict:
    """Q to fill the OHT in 1-2 h; head = lift + friction + residual."""
    q_lpm = oht_l / (PUMP_FILL_HOURS * 60.0)
    head = static_lift_m * (1 + PUMP_FRICTION_PC) + PUMP_RESIDUAL_HEAD_M
    # hydraulic kW = rho g Q H, motor at ~55 % overall
    kw = (1000 * 9.81 * (q_lpm / 60000.0) * head) / 1000.0 / 0.55
    hp = max(0.5, round(kw / 0.7457 * 2) / 2)
    return {"q_lpm": round(q_lpm, 1), "head_m": round(head, 1),
            "hp": hp, "fill_hours": PUMP_FILL_HOURS}


def rwp_count(roof_sqm: float) -> dict:
    """§7 — 100 dia serves ~42 sq.m; never fewer than two."""
    n = max(RWP_MIN, math.ceil(roof_sqm / ROOF_PER_RWP_SQM))
    return {"roof_sqm": round(roof_sqm, 1), "count": n,
            "per_rwp_sqm": ROOF_PER_RWP_SQM,
            "intensity": RAIN_INTENSITY_MM_HR}


def invert_after(start_m: float, length_ft: float, slope: float) -> float:
    """Fall over a run — computed from the length, never typed."""
    if not slope:
        return start_m
    return start_m - (length_ft * 0.3048) / slope


# --------------------------------------- the fixtures this stage keeps shown
PLUMB_FIXTURES = ("wc", "basin", "shower", "counter", "sink",
                  "washing_machine")


def is_plumb_fixture(kind: str) -> bool:
    k = (kind or "").lower()
    return any(k == f or k.startswith(f) for f in PLUMB_FIXTURES)


# ------------------------------------------------- §14 legend / key notes
KEYNOTES = {
    "BASIN": "Wash basin, rim 800-850, counter 500-600 deep",
    "PC":   "Pillar cock / basin mixer on the counter deck, hot LEFT cold RIGHT",
    "BAC":  "Basin angle cocks, hot + cold, 500-550 AFL, 150-200 c/c",
    "BBT":  "Basin bottle trap 32 CP, waste to wall at 400-450",
    "WCAC": "WC 2-way angle cock at 300 AFL — cistern + health faucet",
    "HF":   "Health faucet 450-600 AFL, RIGHT-HAND side of the WC",
    "SH":   "Shower head 2000-2200, centred on the shower area",
    "SMX":  "Shower mixer 950-1000, hot left cold right, 150 c/c",
    "GY":   "Geyser, bottom 1800-2000; unions + NRV on the inlet",
    "SINK": "Kitchen sink on 850 counter, bottle trap 40 below",
    "SKC":  "Sink cock / wall mixer 1050-1100",
    "WMT":  "Washing machine tap 1050 with a dedicated nahani trap",
    "GBC":  "Garden bib cock 450-600 on the external wall",
    "NT":   "Nahani trap, 50 min water seal, CP/SS jali",
    "GT":   "Gully trap — waste stacks only, before the chamber",
    "IC":   "Inspection chamber — see the chamber schedule",
    "CO":   "Cleanout plug at the base of the stack",
    "KH":   "Khurra 450 x 450 dished with grating, terrace slope 1:100",
    "UGT":  "Underground water tank — see the calculation sheet",
    "PUMP": "Submersible pump, float switch + NRV at delivery",
    "OHT":  "Overhead tank — see the calculation sheet",
    "SV":   "Full-way isolation valve at the entry",
    "SS":   "Soil stack 110 in the shaft, vent extended over the terrace",
    "WS":   "Waste stack 75 in the shaft",
    "VP":   "Vent pipe 75, 600 above terrace with a cowl",
    "RWP":  "Rain-water pipe 110 from the terrace khurra",
    "CWD":  "Cold water down-take from the OHT",
    "HWD":  "Hot water down-take, insulated",
}

NOTES_BLOCK = [
    "Design to NBC 2016 Part 9, IS 1172, IS 1742, IS 2065 and CPHEEO; local "
    "bye-laws where stricter.",
    "Two-pipe system: soil and waste are separate to the chamber. Soil stacks "
    "connect DIRECTLY to the IC; only waste passes a gully trap.",
    "Nahani trap with 50 mm minimum water seal in every shower, beside every "
    "WC, at the washing machine and at the kitchen.",
    f"Sunken slab {BATH_SUNK_MM} mm recommended for concealed traps.",
    "Rain-water pipes never discharge into the sewer or soil line.",
    "Hot-left / cold-right at every mixer; hot runs under 8-10 m dead leg, "
    "insulated on exposed lengths.",
    f"Sewer connection invert assumed {SEWER_INVERT_M:+.2f} m — VERIFY on site.",
    "Test supply pipework at 1.5x working pressure for 2 hours.",
    "Verify with a licensed plumbing consultant and the local authority "
    "before execution.",
]
