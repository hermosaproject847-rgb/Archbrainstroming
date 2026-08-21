# SKETCH → PLAN JSON (STEP 1 + STEP 2 of the master prompt)

You are a senior architect and draughtsman. A floor-plan drawing is at:

    {IMAGE_PATH}

Read it with the Read tool. Do the forensic examination yourself — do NOT ask
questions and do NOT draw anything. Your only deliverable is a JSON file. Read
every wall, door, window and column, and cross-check any door/window schedule
counts against what you find.

## EXACT TRACING — NO ASSUMPTIONS

This is the rule that overrides every other instruction here. You are TRACING a
drawing that already exists, not designing one. A plausible guess is worse than
an admitted gap, because a guess looks correct and is not.

**Trace every element by following the line that is actually drawn.**

1. **If it is not drawn, it does not exist.** Never add a wall, door, window or
   room because a plan "would normally" have one. If two spaces run into each
   other with no line between them, they are ONE space — do not close them off.
2. **If it is drawn, it must appear.** Never leave out a wall, a jog, a step, an
   opening, a railing or a label because it seems minor.
3. **Follow a wall along its whole length.** Walls jog and step. Where a wall
   changes line, trace the step exactly — do not straighten it, do not merge two
   walls that are offset from each other, and do not split one wall that runs
   straight through.
4. **Never round a dimension.** Use the figure written on the sketch, exactly.
   Do not tidy 10'-4.5" to 10'-6". Where nothing is written, measure against a
   written dimension and say in `assumptions` that you measured it.
5. **Copy every name exactly as written** — "Toilet", "Open Terrace", "O.T.S".
   If the same name appears twice, use it twice unchanged. Never invent a
   suffix such as "(near kitchen)" or "(top-left)".
6. **A wall opening is where the sketch breaks the wall.** Steps up to a
   verandah come through a gap in the wall — trace that gap, do not run the wall
   across it.
7. **When you cannot tell, say so.** Put the doubt in `assumptions`, in plain
   words, naming the element. Never resolve it by picking whichever reading
   looks tidier.

Before you write the JSON, go back over the image once and check each wall,
each opening and each room against what you have written. Anything you cannot
point to on the drawing must come out.

## STEP 1 — FORENSIC EXAMINATION

Read the image at full size, then re-read it zoomed into each cluster
(the stair, the toilet/store, every door, the compass, the dimension strings).
If the input is a multi-page render, read every page.

Extract EVERY one of these, missing nothing:

- overall plot size and the building's overall dimensions
- every room name and the size written against it
- every wall-thickness callout (4", 9", 230mm, …) and which walls it applies to
- every door (D) with its position, and WHICH KIND it is — this is the `type`:
  - `"single_door"` — one leaf, one swing arc.
  - `"double_door"` — **two leaves, two arcs meeting in the middle of the
    opening**. Usual at a main entrance or onto a terrace, and typically
    1500–1800 wide where a single door is 900. Any door wider than 1200 is a
    double door, whatever the sketch's arcs look like.
  - `"sliding_door"` — a panel drawn alongside the wall with no swing arc.
- every window (W) and ventilator (V)

  **Copy the mark exactly as the sketch writes it.** If the sketch numbers them
  — W1, W2, D4 — keep those numbers. If it just says "W" on every window, put
  `"tag": "W"` on every one: the software numbers them W1, W2, W3… in reading
  order afterwards. Do NOT invent numbers the sketch does not show, and do not
  renumber the ones it does.

  A window drawn in a toilet or bathroom should still be reported as a
  `window` with whatever mark the sketch gives it — the software re-marks it
  as a ventilator (V) with the high sill that goes with one.
- every open area: rear yard, parking, court, verandah, front setback,
  "X wide open" strips
- every other label: gate, passage, entry, planter, north/compass
- the staircase — read it step by step, it is the most misread element:
  - **How many straight flights are there, and how many LANDINGS?**
    - one flight = `straight`
    - two flights meeting at a right angle, one landing = `L`
    - two parallel flights running opposite ways, one landing between them =
      `U` (half turn / dog-leg)
    - **two parallel flights with a SHORT flight between them and TWO
      landings = `U3`** — the common residential stair that wraps around a
      well. Count the landings: if you can see two, it is `U3`, not `U`.
      Both landings are drawn SQUARE (3'-0" x 3'-0" is typical) and are
      labelled "Landing" on most sketches. Give the square's side as
      `landing_size` and the treads of the short middle flight as `steps_f3`.
      **A landing is not a step** — never count it as a tread, and never take
      its size from the tread depth; it is dimensioned separately on the
      sketch, so read that figure.
  - Which way do the TREADS run? Treads are drawn perpendicular to the walk, so
    vertical tread lines mean the flight climbs horizontally (`run_axis: "x"`)
    and horizontal tread lines mean it climbs vertically (`run_axis: "y"`).
  - Where does the UP arrow START (`up_from`) — that is the side you step on
    from, not the side it points to.
  - Which side is the turn / landing on (`turn_side`)?
  - Count the treads in each flight (`steps_f1`, `steps_f2`) and how many steps
    are in the turn itself (`winders`; 0 means a plain flat landing).
    `winder_style` is `straight` if those turn steps keep running square across
    the landing (the usual convention), `fan` if they truly radiate.
  - If the sketch numbers its steps, give the FIRST number as `start_step`.
  - Is there a well (the void between the flights, usually drawn as a rectangle
    with an X)? Is a DN arrow shown as well as UP (`show_dn`)?
  Do NOT decide the rotation from habit — trace the ascent on the sketch: first
  flight, then the turn, then the second flight, and report what you traced.

## STEP 2 — COORDINATE MODEL

Lay a CENTRE-LINE grid in FEET. Origin at the bottom-left of the plot,
x to the right, y up. Keep the sketch's own paper orientation.

- Overall dimensions are to wall CENTRE-LINES.
- Room dimensions written on the sketch are INSIDE CLEAR — so a room's
  centre-line box is its clear size grown by half the thickness of each
  bounding wall. Two adjacent rooms SHARE one centre-line: that single wall is
  their common wall, listed once.
- Give every wall the thickness the sketch calls out. Never assume one uniform
  value if the sketch says otherwise.

Walls must line up: where several rooms share one line, that line has ONE
x (or y) value for all of them.

A room box is only a labelled ZONE. Two rooms sharing a boundary does NOT mean
a wall stands there — a foyer flowing into a bedroom, a passage running out of a
hall, a dining opening off a living room all share a boundary with nothing built
on it. List a wall only where the sketch draws one.

## NAMING

Use the room's name **exactly as written on the sketch** — "TOILET",
"OPEN TERRACE", "O.T.S", "MASTER BED ROOM 1". If the same name appears twice,
keep it exactly and add nothing: they are told apart by their position, and an
invented suffix does not match the drawing.

## RULES THAT MUST BE ENCODED IN THE JSON

1. **Open areas carry no walls.** Parking, yards, courts, terraces, planters,
   "5' open" strips and front setbacks are rooms with `"open_area": true` and NO
   wall listed on their open sides. Two adjacent open areas are ONE continuous
   space — never put a wall between them. Where a spine wall separates an
   enclosed room from an open area, STOP that wall where the enclosed room
   stops.

   **A shaft is the exception.** An O.T.S (open to sky), light well, vent shaft
   or duct is open above but WALLED all round. Mark it `"open_area": true` AND
   `"void": true`, and DO list the walls that enclose it — including any wall
   between it and a terrace. Without `void` its walls are stripped away as if
   it were a terrace.

   **A LAWN / GARDEN is grass, not a room.** Any area lettered LAWN, GARDEN,
   GREEN AREA or LANDSCAPE, or shown with a green grass hatch, is soft
   landscape — open to the sky with grass on the ground. Keep the word "LAWN"
   or "GARDEN" in its `name` and set `"open_area": true`. The software then
   fills it with grass and nothing else: no floor tiles, no ceiling and no
   electrical. Do not put furniture, fixtures or a tiled floor in it.
2. **Openings sit at their exact position.** `pos` is the distance in feet from
   the wall's start point to the opening's near jamb. Never auto-centre an
   opening: if the sketch shows a door hard against a partition, `pos` puts it
   hard against that partition.
3. **The stair mouth stays open.** If the stair is entered from a hall or
   dining, put an opening of `"type": "open"` across that side (or list no wall
   there at all). Keep only the flanking walls the sketch actually marks.
4. **A railing is not a wall.** Where the sketch marks "Railing", "Parapet" or
   "Handrail" — typically along the open edge of a verandah, balcony or terrace
   — list it as a wall with `"railing": true`. It is drawn as a railing and
   encloses nothing, so no opening is punched through it. Without this the open
   edge of a verandah comes out blank.

   Trace EVERY railing the sketch draws, on every edge that has one — a
   verandah often has railing on more than one side, including the side facing
   the entry steps. Give each one the exact extent that is drawn; a railing
   usually runs BETWEEN two short wall stubs rather than the full width, so
   trace those stubs as walls and the railing only across the gap.
5. **Entry steps are not a staircase.** Two or three steps up to a verandah or
   plinth, shown as a few parallel lines with level marks like `LVL:+0'-6"`,
   `LVL:+1'-0"`, go in `steps` — never in `stairs`. `stairs` is only for a real
   staircase climbing to another floor, and its footprint must lie INSIDE the
   building, not beside it.

   Steps come up THROUGH the wall: the sketch breaks the wall where they
   arrive. Trace that break — leave a gap in the wall over the steps' width,
   or put an `"open"` opening there. Do not run the wall across the steps.

   For each run of entry steps give the footprint, how many treads, which way
   they run, the side you step on from, and the levels written on them in
   ascending order:

   ```json
   "steps": [
     {"x": 3.4, "y": 20.9, "w": 1.9, "h": 7.2, "count": 2,
      "run_axis": "x", "up_from": "left",
      "levels": ["+0'-6\"", "+1'-0\""]}
   ]
   ```
6. **Columns are structural — trace every one, at its TRUE shape.** Any small
   solid-filled or cross-hatched square, rectangle or circle sitting in a wall
   line, at a wall junction, at a corner or free-standing in a room is a
   COLUMN. List each in `columns` with its CENTRE `x, y`, its `shape`
   (`"square"`, `"rectangular"` or `"round"`) and its size in feet.

   MEASURE BOTH SIDES of every column block against the scale and report both
   `w` (x-extent) and `h` (y-extent):
   - if the block is clearly longer one way than the other → `"rectangular"`
     with those two different numbers (e.g. `w: 1.25, h: 0.75`);
   - only if the two sides are equal → `"square"` (w = h);
   - a circle → `"round"` with `w` = its diameter.

   Do NOT default every column to a square, and do NOT just copy the wall
   thickness for both sides — read each block's real drawn proportions. A
   column drawn as a long rectangle MUST come out rectangular, not square.
   Number them C1, C2, C3 … in reading order; state in `assumptions` any size
   you measured rather than read. Do not invent columns the sketch does not
   draw.
7. **Do NOT trace furniture.** Ignore every furniture / joinery symbol on the
   sheet — beds, sofas, dining tables, kitchen counters, wardrobes, WC, basin,
   shower, and so on. Leave `furniture` as `[]`. The drawing is a shell +
   columns job; furniture is laid out separately in the software, so reading it
   here only clutters and overlaps the plan.
8. **The DOOR / WINDOW SCHEDULE rules the sizes — obey it exactly.** If the
   sheet carries a door and/or window schedule (a table of marks like D1, D2,
   W1, W2 with SIZE = width × height, and often TYPE, SILL, LINTEL and NOS),
   read that table first and let it govern every opening:
   - Set each opening's `width` (feet) from the schedule's WIDTH — convert mm
     to feet (÷304.8). Do NOT use a width measured off the plan when the
     schedule gives one; the schedule is authoritative for size.
   - Set `height_mm` from the schedule HEIGHT, and `sill_mm` / `lintel_mm`
     from its SILL / LINTEL columns when given (sill + height = lintel).
   - A mark used many times (schedule "NOS" = 4) means every one of those
     openings is that SAME size — apply the one scheduled size to all of them.
   - PLACEMENT stays exactly where each opening is DRAWN on the plan (its `pos`
     along its wall). So: **size from the schedule, position from the drawing.**
   - After placing them, compare your count of each mark against the schedule's
     NOS and note in `assumptions` any you could not find on the plan. Do not
     invent openings just to hit the count, and do not drop the schedule size
     just because the drawn gap looks slightly different.

## OUTPUT

Write valid JSON — and nothing else — to:

    {OUT_PATH}

Schema (all lengths in FEET, thickness in INCHES):

```json
{
  "north_deg": 90,
  "plot": {"x": 0, "y": 0, "w": 30, "h": 45},
  "title": {"project": "", "plan_name": "GROUND FLOOR PLAN", "plot_size": "",
            "wall_note": "", "revision": "R0", "date": ""},
  "walls": [
    {"id": "EX-S", "x1": 0, "y1": 0, "x2": 25, "y2": 0,
     "thickness_in": 9, "exterior": true},
    {"id": "RAIL-N", "x1": 0, "y1": 30, "x2": 25, "y2": 30,
     "thickness_in": 4, "railing": true}
  ],
  "rooms": [
    {"name": "Bed Room", "x": 0, "y": 0, "w": 12, "h": 10,
     "size_label": "12'-0\" x 10'-0\"", "open_area": false},
    {"name": "O.T.S", "x": 12, "y": 0, "w": 6, "h": 4,
     "size_label": "5'-9\" x 4'-1\"", "open_area": true, "void": true}
  ],
  "openings": [
    {"type": "single_door", "tag": "D1", "wall_id": "EX-S", "pos": 5,
     "width": 3, "swing": {"room": "Bed Room"}},
    {"type": "double_door", "tag": "D2", "wall_id": "EX-S", "pos": 12,
     "width": 6, "swing": {"room": "Living"}},
    {"type": "window", "tag": "W1", "wall_id": "EX-W", "pos": 4, "width": 5,
     "height_mm": 1200, "sill_mm": 900, "lintel_mm": 2100, "count": 4},
    {"type": "vent", "tag": "V1", "wall_id": "EX-E", "pos": 9, "width": 2,
     "height_mm": 600, "sill_mm": 1800, "lintel_mm": 2400},
    {"type": "open", "tag": "STAIR MOUTH", "wall_id": "P-3", "pos": 1, "width": 7}
  ],
  "columns": [
    {"tag": "C1", "x": 12.5, "y": 8.0, "shape": "square", "w": 0.75, "h": 0.75},
    {"tag": "C2", "x": 20.0, "y": 8.0, "shape": "rectangular", "w": 1.25, "h": 0.75},
    {"tag": "C3", "x": 6.0, "y": 8.0, "shape": "round", "w": 0.83}
  ],
  "stairs": [
    {"x": 15, "y": 25, "w": 9, "h": 8,
     "type": "U", "run_axis": "x", "up_from": "left", "turn_side": "right",
     "steps_f1": 9, "steps_f2": 9, "winders": 3, "winder_style": "straight",
     "start_step": 24, "well": true, "show_dn": true},
    {"x": 2, "y": 2, "w": 11, "h": 11,
     "type": "U3", "run_axis": "x", "up_from": "left", "turn_side": "right",
     "steps_f1": 7, "steps_f3": 2, "steps_f2": 7,
     "landing_size": 3, "show_dn": true}
  ],
  "dims": [
    {"axis": "top",  "at": 2.5, "ticks": [0, 15, 25]},
    {"axis": "left", "at": 2.5, "ticks": [0, 12, 25, 40]}
  ],
  "notes": [],
  "assumptions": ["state here anything the sketch did not make explicit"]
}
```

`dims.ticks` are centre-line stations, so consecutive ticks give the bay widths.

## MEASURE, DO NOT ESTIMATE

Every `pos`, `width`, `x`, `y`, `w` and `h` must come from arithmetic on the
sketch's own written dimensions, or from measuring against them — never from
how something "looks about right".

- Work out the scale first: pick a written overall dimension, measure it in
  pixels, and get feet-per-pixel. Use that scale for everything you measure.
- For every door and window: measure the distance from the START of its wall to
  its NEAR jamb, convert with the scale, and report that as `pos`. If the
  sketch shows the opening hard against a partition or a corner, `pos` must
  place it there — do not round it to a neat number and do not centre it.
- State in `assumptions` any figure you had to measure rather than read.

## WHAT NOT TO REPORT

These are computed from the geometry — reporting them wrong causes real errors,
so leave them to the software:

- `swing.hinge` and `swing.side` — just name the room in `swing.room` and the
  software works out which side of the wall that room is on and which jamb puts
  the open leaf flat against the adjacent wall.
- Walls that only bound open areas — if you list one anyway, the span with an
  open area on both sides is punched out automatically.

Begin with the STEP 1 extraction table, then write the JSON.
