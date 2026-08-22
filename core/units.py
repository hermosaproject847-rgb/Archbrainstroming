"""Central length formatting + unit config for the whole drawing.

The model stores every length in FEET. `set_unit()` picks how lengths are shown
(feet-inch / millimetre / metre) and how the exported DXF is emitted, so the
on-screen dimensions, the room / furniture / wall labels AND the DXF all follow
the one unit the user chose. Call `set_unit()` before building / exporting.
"""

_UNIT = "ft"                       # "ft" | "mm" | "m"


def set_unit(u):
    global _UNIT
    _UNIT = u if u in ("ft", "mm", "m") else "ft"


def current():
    return _UNIT


def fmt_len(feet):
    """A length in feet → a display string in the current unit."""
    f = float(feet or 0)
    if _UNIT == "mm":
        return str(int(round(f * 304.8)))
    if _UNIT == "m":
        s = f"{f * 0.3048:.3f}".rstrip("0").rstrip(".")
        return (s or "0") + " m"
    total_in = round(f * 12.0)                      # feet-inch (default)
    ft, inch = divmod(int(total_in), 12)
    return f"{ft}'-{inch}\""


import re as _re
_FTIN = _re.compile(r"(\d+)\s*'\s*-?\s*(\d+)?\s*([½¼¾])?\s*\"")
_FRAC = {"½": 0.5, "¼": 0.25, "¾": 0.75}


def relabel(text):
    """Convert every feet-inch token in a label (e.g. "12'-6\" X 10'-0\"") into
    the current unit, keeping the SAME dimensions — so a room's recorded size
    reads correctly in mm / m instead of being recomputed and drifting."""
    if not text or _UNIT == "ft":
        return text

    def _sub(m):
        ft = int(m.group(1))
        inch = int(m.group(2)) if m.group(2) else 0
        frac = _FRAC.get(m.group(3), 0.0)
        return fmt_len(ft + (inch + frac) / 12.0)

    return _FTIN.sub(_sub, text)


def dxf_insunits():
    """AutoCAD $INSUNITS code for the current unit (2=feet, 4=mm, 6=metre)."""
    return {"ft": 2, "mm": 4, "m": 6}.get(_UNIT, 2)


def dxf_scale():
    """Multiplier from feet to the current unit, for DXF geometry."""
    return {"ft": 1.0, "mm": 304.8, "m": 0.3048}.get(_UNIT, 1.0)
