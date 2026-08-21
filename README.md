# Sketch → Floor Plan

Hand sketch (PNG / JPG / PDF) → professional, dimensioned CAD floor plan
(**DXF + PDF + SVG + PNG**), with an image-preview workbench in between.

Built to the `PROMPT_sketch_to_floorplan_v2` master prompt.

---

## Run it

Double-click **`Sketch to Floor Plan.exe`**.

(It launches `app.py` with the portable Python at `%USERPROFILE%\pyembed`.
To run it directly: `%USERPROFILE%\pyembed\pythonw.exe app.py`.)

## How it works

The software does **not** pixel-trace the sketch — pixel tracing cannot read
`12'-6"`, tell a 9" wall from a 4" one, or see which way a door swings. It does
what a draughtsman does: **read the sketch, build a model, redraw it clean.**

```
sketch (png/jpg/pdf)
      │  300 dpi render
      ▼
STEP 1  forensic read  ──────────────  core/reader.py + prompts/extract_prompt.md
      │  rooms · sizes · wall callouts · every D/W/V · stair rotation · open areas
      ▼
        plan JSON  ◄──── you correct it in the app's tables (live)
      │
      ▼
STEP 2/3  geometry  ─────────────────  core/engine.py
      │  centre-line grid → wall rectangles → union → subtract openings
      ▼
STEP 4  self-validation  ────────────  core/validate.py
      │  provable geometric checks, not eyeballing
      ▼
        sheet + title block  ────────  core/sheet.py
      ▼
        DXF · PDF · SVG · PNG  ──────  core/export.py
```

## Using the app

1. **Open Sketch** — pick the PNG / JPG / PDF. It appears in the left pane
   (mouse wheel = zoom, drag = pan).
2. **Read Sketch (AI)** — the forensic read. Add notes first for anything the
   sketch does not state (wall thicknesses, plot size, north); they override the
   reading. Takes a few minutes.
3. The drawing appears on the right and every finding fills the bottom tables:
   **Rooms · Walls · Doors/Windows · Stairs · Title block**.
4. **Fix anything the read got wrong** — edit a cell and the drawing redraws
   immediately. This is the step that makes the output exact.
5. Tick **Overlay on sketch** to lay the drawing straight over the sketch. The
   slider fades between the two, the arrows nudge and stretch the alignment, and
   any door, window or wall that sits even slightly off shows up at once. This
   is how placement is verified rather than trusted.
6. Watch the **Checks** tab: it must say all checks passed. **Auto-fixes** lists
   what the software corrected from the geometry itself.
6. **Export** → `out/` gets `.dxf` (AutoCAD), `.pdf` (vector), `.svg`, `.png`
   and the `.json` model.

Press **Sample** any time to load a known-good plan and see the target quality.

## What the drawing rules guarantee

Built into the geometry, not left to chance:

- walls are **two thin parallel lines** (hollow), never solid black poché
- adjacent rooms **share one common wall**, drawn once from a single centre-line
- junctions close cleanly — no overshoots (the wall union guarantees it)
- **no wall across any opening**; every door is punched with proper jambs
- doors **open inward into the room they serve** and fold flat along a wall,
  with the 90° swing arc drawn
- the stair is drawn to its **read typology** — `straight`, `L` (quarter-turn)
  or `U` (half-turn) — with the flights, landing, winders, well and UP/DN arrows
  all derived from it, so the drawing cannot contradict the typology
- **door swing sides and hinge jambs are computed, not read**: name the room a
  door serves and the software works out which side of the wall that room is on
  and which jamb puts the open leaf flat against the adjacent wall
- the **stair mouth stays open** — no wall or jamb where it opens off a room
- **open areas carry no walls**: parking, yards, courts, setbacks and
  "X wide open" strips are one continuous space with nothing between them
- wall thickness is **literal to the callouts** (9" external, 4" partition, …),
  never a uniform guess

`core/validate.py` proves each of these geometrically before you export, so a
clean **Checks** tab is evidence, not an opinion.

## The plan JSON

Everything is in **feet**; wall thickness in **inches**; walls are
**centre-lines**. See `samples/sample_plan.json` and `core/model.py`.
The JSON tab lets you edit the whole model directly and re-apply it, and every
export writes the JSON alongside the drawings so a plan can be reopened later.

## Layout

```
app.py                  desktop shell (pywebview / WebView2)
ui/                     the workbench UI
core/model.py           the data model
core/reader.py          sketch → JSON (the only AI step)
core/engine.py          JSON → geometry
core/validate.py        STEP 4 checks
core/sheet.py           sheet, scale, border, title block
core/export.py          SVG / PNG / PDF / DXF
core/pipeline.py        render + export in one call
prompts/                the extraction prompt
samples/                a known-good plan
out/                    exports land here
work/                   page renders and the read log
```

## Requirements

Portable Python at `%USERPROFILE%\pyembed` with `shapely`, `ezdxf`,
`matplotlib`, `pillow`, `pypdfium2`, `pywebview`; the Claude CLI at
`%LOCALAPPDATA%\AnthropicClaude\claude.exe` for the sketch read; Edge WebView2
(ships with Windows) for the window.
