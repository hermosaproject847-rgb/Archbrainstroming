"""Layers, and what is visible on them.

Every element the software draws belongs to a layer, and every layer can be
turned off — on screen, in the PDF/PNG, and as a DXF layer state. That is what
makes it possible to look at the electrical layout with the furniture hidden,
or the bare shell with everything hidden.

Layers are grouped so a whole discipline goes on or off in one click, and the
groups match the buttons: floor plan, furniture, electrical.
"""

from __future__ import annotations

# group -> (label, [drawing layers], on by default)
GROUPS = [
    ("shell",     "Walls & openings",
     ["WALL-EXT", "WALL-INT", "OPENING", "WINDOW", "DOOR", "RAILING"], True),
    ("columns",   "Columns", ["COLUMN", "COLUMNTAG"], True),
    ("grass",     "Lawn / garden grass", ["GRASS"], True),
    ("seclines",  "Section lines", ["SEC-LINE"], True),
    ("stairs",    "Stairs & steps", ["STAIR"], True),
    ("rooms",     "Room names & sizes", ["TEXT"], True),
    ("dims",      "Dimensions", ["DIM"], True),
    ("plot",      "Plot line", ["PLOT"], True),
    ("north",     "North point", ["NORTH"], True),
    ("walltags",  "Wall numbers", ["WALLTAG"], False),
    ("furniture", "Furniture", ["FURNITURE"], True),
    ("furntags",  "Furniture tags", ["FURNTAG"], True),
    # the sanitary and kitchen fixtures live on their own layer so the
    # plumbing view can keep them while every other piece goes off
    ("sanitary",  "Sanitary & kitchen fixtures", ["SANITARY"], True),
    ("elec",      "Electrical points", ["ELEC"], True),
    ("electags",  "Electrical tags", ["ELECTAG"], True),
    ("elecloops", "Switch loops", ["ELEC-LOOP"], True),
    ("plumbcw",   "Plumbing · cold water", ["PLUMB-CW"], True),
    ("plumbhw",   "Plumbing · hot water", ["PLUMB-HW"], True),
    ("plumbsoil", "Plumbing · soil", ["PLUMB-SOIL"], True),
    ("plumbwaste", "Plumbing · waste", ["PLUMB-WASTE"], True),
    ("plumbcl",   "Plumbing · centre-line & fittings", ["PLUMB-CL", "PLUMB-BORE", "PLUMB-FIT"], True),
    ("plumbvent", "Plumbing · vent", ["PLUMB-VENT"], True),
    ("plumbstorm", "Plumbing · storm / RWP", ["PLUMB-STORM"], True),
    ("plumbacd",  "Plumbing · AC condensate", ["PLUMB-ACD"], True),
    ("plumbtags", "Plumbing key notes", ["PLUMB-TAG"], True),
    ("flrhatch",  "Flooring · material fill", ["FLR-HATCH"], True),
    ("flrgrid",   "Flooring · tile / spacer grid", ["FLR-GRID"], True),
    ("flrstart",  "Flooring · start point", ["FLR-START"], True),
    ("flrskirt",  "Flooring · skirting", ["FLR-SKIRT"], True),
    ("flrlevel",  "Flooring · levels & slopes", ["FLR-LEVEL"], True),
    ("flrtext",   "Flooring · labels", ["FLR-TEXT"], True),
    ("notes",     "Notes & sub-text", ["TEXT-SUB"], True),
    ("title",     "Border & title block", ["TITLE"], True),
]

# which groups each view turns on. A view is a starting point, not a lock —
# every group can still be toggled by hand afterwards.
VIEWS = {
    "floor": ["shell", "columns", "grass", "seclines", "stairs", "rooms", "dims", "plot", "north",
              "walltags", "notes", "title"],
    "furniture": ["shell", "columns", "grass", "seclines", "stairs", "rooms", "plot", "north",
                  "furniture", "furntags", "sanitary", "notes", "title"],
    "electrical": ["shell", "columns", "grass", "seclines", "stairs", "rooms", "plot", "north",
                   "elec", "electags", "elecloops", "notes", "title"],
    # Plumbing is split into TWO clean layouts so the sheets never turn into a
    # khichdi: WATER SUPPLY (cold/hot supply pipes + valves) and DRAINAGE
    # (soil/waste/vent + traps/chambers). Each keeps only the sanitary fixtures.
    "watersupply": ["shell", "columns", "grass", "seclines", "stairs", "rooms", "plot", "north",
                    "sanitary", "plumbcw", "plumbhw", "plumbcl", "plumbtags",
                    "notes", "title"],
    "drainage": ["shell", "columns", "grass", "seclines", "stairs", "rooms", "plot", "north",
                 "sanitary", "plumbsoil", "plumbwaste", "plumbcl", "plumbvent",
                 "plumbstorm", "plumbacd", "plumbtags", "notes", "title"],
    # kept for anything that still asks for the combined plumbing view
    "plumbing": ["shell", "columns", "grass", "seclines", "stairs", "rooms", "plot", "north",
                 "sanitary", "plumbcw", "plumbhw", "plumbsoil", "plumbwaste",
                 "plumbcl", "plumbvent", "plumbstorm", "plumbacd", "plumbtags",
                 "notes", "title"],
    # Flooring keeps only the shell and the flooring layers — furniture,
    # plumbing and electrical all go off, so the tile grid reads.
    "flooring": ["shell", "columns", "grass", "seclines", "stairs", "rooms", "plot", "north",
                 "flrhatch", "flrgrid", "flrstart", "flrskirt", "flrlevel",
                 "flrtext", "notes", "title"],
    "all": [g[0] for g in GROUPS if g[0] != "walltags"],
}

LAYER_GROUP = {ly: g for g, _lbl, lys, _on in GROUPS for ly in lys}


def default_state() -> dict:
    return {g: on for g, _lbl, _lys, on in GROUPS}


def for_view(view: str) -> dict:
    """The layer state a view starts from."""
    want = set(VIEWS.get(view, VIEWS["all"]))
    return {g: (g in want) for g, _lbl, _lys, _on in GROUPS}


def hidden_layers(state: dict | None) -> set:
    """The drawing layers that are off."""
    if not state:
        return set()
    out = set()
    for g, _lbl, lys, on in GROUPS:
        if not state.get(g, on):
            out.update(lys)
    return out


def describe() -> list[dict]:
    """For the UI: the groups, their labels and their layers."""
    return [{"key": g, "label": lbl, "layers": lys, "default": on}
            for g, lbl, lys, on in GROUPS]


def apply(dl, state: dict | None):
    """A copy of the drawing with the hidden layers left out."""
    off = hidden_layers(state)
    if not off:
        return dl
    from .draw import DrawList
    out = DrawList()
    out.items = [it for it in dl.items if it.layer not in off]
    return out
