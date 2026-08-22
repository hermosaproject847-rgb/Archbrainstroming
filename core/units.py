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


def dxf_insunits():
    """AutoCAD $INSUNITS code for the current unit (2=feet, 4=mm, 6=metre)."""
    return {"ft": 2, "mm": 4, "m": 6}.get(_UNIT, 2)


def dxf_scale():
    """Multiplier from feet to the current unit, for DXF geometry."""
    return {"ft": 1.0, "mm": 304.8, "m": 0.3048}.get(_UNIT, 1.0)
