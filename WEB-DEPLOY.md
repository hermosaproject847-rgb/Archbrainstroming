# SketchToPlan — Web version (host on the cloud, use from your phone)

The same app, in any browser. **AI "Read Drawing" / Questionnaire are OFF** in the
web build (they need the Claude CLI). Everything else works fully **offline on the
server**: open a DXF or a saved JSON plan, edit, Furniture, the whole Structural
set, **PDF → DXF**, and the single **combined-DXF Export** (downloads to your phone).

## Run it locally first (test)
```
python webserver.py
```
Open http://localhost:8080 in a browser. (On the desktop Python, use the bundled
`pyembed\python.exe`.)

## Host it free on Render.com (recommended, no server PC)
1. Put this folder in a **GitHub repo** (the `.gitignore` already excludes the big
   `out/`, `work/`, `python/`, `*.exe`, `*.dwg` — do NOT push those).
2. Go to **render.com** → sign up (free) → **New +** → **Web Service** →
   connect your GitHub repo.
3. Settings:
   - **Runtime:** Python 3
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `python webserver.py`
   - **Environment variable:** `MPLBACKEND` = `Agg`
   - **Instance type:** Free
   (Or just pick **Blueprint** and Render reads `render.yaml` automatically.)
4. **Create Web Service** → wait for the build → you get a URL like
   `https://sketchtoplan.onrender.com`.
5. Open that URL on your **phone browser**. Add to Home Screen to use it like an app.

## How to use the web build
- **Open a DXF** (or **Open Plan** for a saved `.json`) → the browser file picker.
- Edit rows, **Furniture**, **Beam Layout / Structural**, **Flooring**, etc.
- **PDF → DXF**: pick a vector PDF → it converts and downloads the `.dxf`.
- **Export**: makes ONE combined DXF (+ PDF) with every sheet and **downloads** it.

## Notes / limits
- **Free tier sleeps** after ~15 min idle — the first load then takes ~30–60 s to
  wake. That is normal on free hosting; a paid plan (~$7/mo) stays always-on.
- **AI read is off** (no Anthropic key). To turn it on later you would set an
  `ANTHROPIC_API_KEY` env var on the host (that bills the API per use).
- Big PDF → DXF conversions (very dense CAD sheets) can take 10–60 s.

## Other cheap hosts
Railway.app, Fly.io, or any VPS (DigitalOcean / AWS Lightsail ~$5/mo) work the same
way: install `requirements.txt`, run `python webserver.py`, it binds `$PORT`.
