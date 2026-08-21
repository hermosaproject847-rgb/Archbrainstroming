"""Beam layout — RCC beams generated over the walls, numbered, with a schedule.

The plan says where the walls run; a beam sits on the centre-line of every
load-bearing wall. Width defaults to 230 mm (9"), depth to 300 mm; both are
editable per beam. Numbering runs top-to-bottom, left-to-right so the schedule
reads in a sensible order.
"""

from __future__ import annotations

import math

from .model import Beam

MM = 304.8


def auto_beams(plan, width_mm: float = 230.0, depth_mm: float = 300.0):
    """One beam along every (non-railing) wall centre-line, numbered B1..Bn."""
    walls = [w for w in plan.walls if not getattr(w, "railing", False)]
    # order: by the beam midpoint, top rows first (high y), then left to right
    def key(w):
        my = (w.y1 + w.y2) / 2
        mx = (w.x1 + w.x2) / 2
        return (-round(my, 2), round(mx, 2))
    beams = []
    for i, w in enumerate(sorted(walls, key=key), start=1):
        beams.append(Beam(tag=f"B{i}", x1=w.x1, y1=w.y1, x2=w.x2, y2=w.y2,
                          width_mm=round(width_mm), depth_mm=round(depth_mm)))
    return beams


def renumber(beams):
    """Re-tag beams B1..Bn in top-to-bottom, left-to-right order."""
    def key(b):
        return (-round((b.y1 + b.y2) / 2, 2), round((b.x1 + b.x2) / 2, 2))
    for i, b in enumerate(sorted(beams, key=key), start=1):
        b.tag = f"B{i}"
    return beams


def schedule_rows(plan):
    """(tag, width mm, depth mm, length mm) per beam, in tag order."""
    rows = []
    for b in sorted(getattr(plan, "beams", []) or [],
                    key=lambda b: _numkey(b.tag)):
        rows.append((b.tag or "-", round(b.width_mm), round(b.depth_mm),
                     round(b.length * MM)))
    return rows


def _numkey(tag):
    import re
    m = re.search(r"(\d+)", tag or "")
    return int(m.group(1)) if m else 0
