# BRIEF → FLOOR PLAN JSON  (design a bungalow ground-floor plan)

You are a practising residential architect. From the written brief below, DESIGN
a sensible, buildable **ground-floor** plan and write it as a single JSON file.
There is no image to read — you are DESIGNING. Ask no questions. Your only
deliverable is the JSON file.

## The brief

{BRIEF}

## How to design (think like an architect, then encode it)

Work in FEET. Origin (0,0) at the bottom-left of the plot; x to the right, y up.
The building sits inside the plot minus the set-backs. Lay rooms out as
non-overlapping rectangles that TILE the built area with no gaps.

1. **Zoning.** Public/social spaces (living, dining, drawing) near the entry
   side; private spaces (bedrooms) deeper in; the wet core (kitchen, toilets,
   utility) grouped so plumbing stacks. Provide clear CIRCULATION — an entry
   lobby / passage that reaches every room. Do not make one room the only way
   into another (except an attached toilet, which opens off its bedroom).
2. **A MAIN ENTRANCE DOOR is mandatory** — a 3'-6" to 4'-0" door on the entry /
   road side, opening into the living / lobby. Never omit it.
3. **Every room gets a door** to the circulation it belongs to. An attached
   toilet's door opens INTO its bedroom. Bedrooms open off the passage/lobby.
4. **Windows** on the external wall of every habitable room (living, dining,
   bedrooms, kitchen, study); a small high vent for internal toilets.
5. **Staircase** if the brief has more than one floor (type "U" is fine).
6. **Standard sizes — NBC 2016 minimums and common practice** (use these unless
   the brief gives a size):
   - Master bedroom 13'×12' to 15'×13'; other bedrooms 11'×10' to 12'×11'
     (NBC min habitable ≈ 9.5 m²).
   - Living 15'×13'+, Dining 11'×10', combined living/dining 18'×13'.
   - Kitchen 10'×8' (NBC min 5.5 m²); utility 6'×5'.
   - Attached toilet 8'×5'; common bath 7'×5'; powder 4'6"×3'6' (min 1.1 m²);
     pooja 4'×4'; store 6'×5'.
   - Passage/lobby 3'6" to 4' wide.
   - Exterior walls 9" thick, internal walls 4½".
7. **Fit the plot.** Scale the room sizes so the rooms exactly fill the built
   area — no empty leftover strips, no rooms spilling outside the plot.

## Rules the JSON must satisfy

- Rooms tile the built area; adjacent rooms share an edge; nothing overlaps.
- A wall segment on every room boundary. Give each wall a unique `id`. A wall on
  the plot's outer face → `"exterior": true, "thickness_in": 9`; an internal
  partition → `"thickness_in": 4.5` (no `exterior`).
- Every opening references an existing wall by `wall_id`. `pos` is the distance
  in FEET from that wall's start point `(x1,y1)` to the opening's near jamb;
  `pos + width` must stay within the wall's length.
- Doors: `"type":"single_door"` (≤3'6") or `"double_door"` (>3'6"); include
  `"swing": {"room": "<the room it opens INTO>"}`.
- Windows: `"type":"window"` with `"sill_mm":900, "lintel_mm":2100`; toilet
  vents `"type":"vent"` with `"sill_mm":1800, "lintel_mm":2400`.
- `size_label` on each room like `"12'-0\" x 10'-0\""`.
- Put the plot size in the title and floor count in `meta.floors`.

## Output — write ONLY valid JSON (nothing else) to:

    {OUT_PATH}

Schema (lengths in FEET, thickness in INCHES):

```json
{
  "north_deg": 90,
  "plot": {"x": 0, "y": 0, "w": 25, "h": 50},
  "title": {"project": "", "plan_name": "GROUND FLOOR PLAN",
            "plot_size": "25'-0\" X 50'-0\"", "revision": "R0", "date": ""},
  "walls": [
    {"id": "EX-S", "x1": 0, "y1": 0, "x2": 25, "y2": 0,
     "thickness_in": 9, "exterior": true},
    {"id": "P1", "x1": 0, "y1": 15, "x2": 25, "y2": 15, "thickness_in": 4.5}
  ],
  "rooms": [
    {"name": "Living Room", "x": 0, "y": 0, "w": 25, "h": 15,
     "size_label": "25'-0\" x 15'-0\"", "open_area": false}
  ],
  "openings": [
    {"type": "single_door", "tag": "D0", "wall_id": "EX-S", "pos": 11,
     "width": 3.5, "swing": {"room": "Living Room"}},
    {"type": "window", "tag": "W1", "wall_id": "EX-S", "pos": 4, "width": 5,
     "sill_mm": 900, "lintel_mm": 2100}
  ],
  "stairs": [
    {"x": 2, "y": 25, "w": 8, "h": 11, "type": "U", "run_axis": "y",
     "up_from": "left", "show_dn": false}
  ],
  "dims": [
    {"axis": "top", "at": 2, "ticks": [0, 25]},
    {"axis": "left", "at": 2, "ticks": [0, 50]}
  ],
  "meta": {"floors": 2, "source": "questionnaire-ai"},
  "notes": ["designed from the questionnaire brief"]
}
```

Design the plan now and write the JSON file. Output nothing else.
