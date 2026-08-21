"""Flooring design — the standards as data.

From `MASTER_PROMPT_Flooring_Design_Layout.md` (NBC 2016 + IS codes). The
material palette, the spacer matrix (SECTION 5), the wastage table
(SECTION 11), the level drops (SECTION 8) and skirting defaults (SECTION 10),
plus the universal setting-out computation (SECTION 4.2) that every room's cut
pieces come from.
"""

from __future__ import annotations

import math

FT_MM = 304.8
PERIM_JOINT_MM = 5.0          # §4.2 compressible perimeter joint behind skirting

# ------------------------------------------------------ the material palette
# the four the user picks from; toilets/kitchen default to tile with an
# anti-skid finish. Each: label, default size (mm), size options, spacer,
# wastage, legend prefix, hatch angle, slip, default skirting height + type.
MATERIALS = {
    "tile": {
        "label": "Vitrified tile", "size": (600, 600),
        "sizes": [(600, 600), (600, 1200), (800, 800), (900, 900),
                  (300, 300)],
        "spacer": 2.0, "wastage": 0.05, "code": "VT", "finish": "Matt",
        "slip": "R9", "skirt": 75.0, "skirt_type": "surface",
        "bedding": "Adhesive C2TE (IS 15477)",
    },
    "marble": {
        "label": "Italian marble", "size": (1200, 800),
        "sizes": [(1200, 800), (1200, 600), (900, 600), (600, 600)],
        "spacer": 1.5, "wastage": 0.10, "code": "IM", "finish": "Polished",
        "slip": "R9", "skirt": 100.0, "skirt_type": "surface",
        "bedding": "CM 1:4 + white cement slurry (IS 1130)",
    },
    "wood": {
        "label": "Wooden flooring", "size": (1200, 190),
        "sizes": [(1200, 190), (1200, 150), (900, 125), (1800, 190)],
        "spacer": 0.0, "wastage": 0.08, "code": "WD", "finish": "Matt lacquer",
        "slip": "R9", "skirt": 75.0, "skirt_type": "wooden beading",
        "bedding": "Floating + IXPE underlay + DPM (IS 303)",
    },
    "granite": {
        "label": "Granite", "size": (1200, 600),
        "sizes": [(1200, 600), (900, 600), (600, 600), (600, 300)],
        "spacer": 3.0, "wastage": 0.08, "code": "GR", "finish": "Polished",
        "slip": "R10", "skirt": 75.0, "skirt_type": "surface",
        "bedding": "CM 1:4 with slurry (IS 14223)",
    },
}

MATERIAL_ORDER = ["tile", "marble", "wood", "granite"]

# §8 finished-floor level drops (mm below internal dry FFL)
DROPS = {"wet": -20.0, "kitchen": -5.0, "balcony": -25.0, "utility": -25.0,
         "open": -25.0, "dry": 0.0}
SLOPES = {"wet": "1:80", "kitchen": "1:120", "balcony": "1:100",
          "open": "1:100"}

# §11 wastage extra for small/irregular rooms and toilets
SMALL_ROOM_EXTRA = 0.02
SMALL_ROOM_SQM = 6.0

START_RULES = ["symmetry", "entry", "corner-sw", "corner-se", "corner-nw",
               "corner-ne", "feature"]
SKIRT_TYPES = ["surface", "flush", "groove", "recessed", "wooden beading"]


# --------------------------------------------- default flooring per room type
def default_material(cat: str) -> str:
    if cat in ("wet",):
        return "tile"          # anti-skid finish set below
    if cat in ("bedroom", "master", "study"):
        return "wood"
    if cat in ("living", "dining"):
        return "marble"
    if cat == "kitchen":
        return "tile"
    return "tile"


def default_spec(cat: str) -> dict:
    """The starting flooring for a room of this lighting/plumbing category —
    the user edits it afterwards."""
    mat = default_material(cat)
    m = MATERIALS[mat]
    w, h = m["size"]
    finish = m["finish"]
    spacer = m["spacer"]
    drop = DROPS["dry"]
    skirt = m["skirt"]
    skirt_type = m["skirt_type"]
    if cat == "wet":
        w = h = 600.0
        finish = "Anti-skid R11"
        spacer = 3.0
        drop = DROPS["wet"]
        skirt = 0.0                       # dado, not skirting
    elif cat == "kitchen":
        finish = "Anti-skid R10"
        spacer = 3.0
        drop = DROPS["kitchen"]
    elif cat == "open":
        finish = "Rough R11"
        spacer = 5.0
        drop = DROPS["open"]
    return {"material": mat, "finish": finish, "tile_w": w, "tile_h": h,
            "spacer_mm": spacer, "skirting_mm": skirt,
            "skirting_type": skirt_type, "drop_mm": drop}


# --------------------------------------------- SECTION 4.2 setting-out maths
def cut_pieces(clear_ft: float, tile_mm: float, joint_mm: float) -> dict:
    """Full-tile count and the equal cut piece at each aligned end, one axis.
    Straight out of SECTION 4.2."""
    Lc = clear_ft * FT_MM
    T = max(tile_mm, 1.0)
    j = joint_mm
    M = T + j
    p = PERIM_JOINT_MM
    n = math.floor((Lc - 2 * p + j) / M)
    n = max(n, 0)
    R = (Lc - 2 * p) - (n * M - j)
    c = R / 2.0
    if n >= 1 and c < 0.5 * T:
        n -= 1
        c = (R + M) / 2.0
    return {"Lc_mm": round(Lc, 1), "T": T, "j": j, "full": n,
            "cut_mm": round(max(c, 0.0), 1)}


def slip_note(cat: str) -> str:
    return {"wet": "R10-R11, wet DCOF >= 0.42", "kitchen": "R10",
            "open": "R10-R11", "balcony": "R10"}.get(cat, "R9")


def wastage_for(material: str, area_sqm: float) -> float:
    w = MATERIALS.get(material, MATERIALS["tile"])["wastage"]
    if area_sqm < SMALL_ROOM_SQM:
        w += SMALL_ROOM_EXTRA
    return w
