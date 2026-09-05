"""Sketch reader: PNG / JPG / PDF  ->  plan JSON.

The reading itself is done by Claude (vision), driven headlessly through the
Claude CLI with prompts/extract_prompt.md: one call, one plan. Everything
downstream of the JSON is deterministic geometry, so this is the only
non-deterministic step.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPT = os.path.join(ROOT, "prompts", "extract_prompt.md")

HOME = os.path.expanduser("~")

# Claude Desktop keeps versioned CLI builds here and auto-updates them, so the
# version is discovered at run time — never hard-code it. NOT
# ~\AppData\Local\AnthropicClaude\claude.exe, which is only the desktop app's
# launcher stub: it exits 0 and prints nothing, so a read against it silently
# returns no JSON.
CLI_VERSION_DIR = os.path.join(HOME, "AppData", "Roaming", "Claude", "claude-code")

CLI_CANDIDATES = [
    os.path.join(HOME, "nodejs", "node_modules", "@anthropic-ai",
                 "claude-code", "bin", "claude.exe"),
    os.path.join(HOME, "AppData", "Roaming", "npm", "node_modules",
                 "@anthropic-ai", "claude-code", "bin", "claude.exe"),
    # Linux (cloud image): npm -g puts the launcher here
    "/usr/bin/claude",
    "/usr/local/bin/claude",
    "/usr/lib/node_modules/@anthropic-ai/claude-code/cli.js",
    os.path.join(HOME, ".local", "bin", "claude"),
]

LOGIN_HELPER = os.path.join(HOME, "drawing-watcher", "login-helper.cmd")

_NOT_LOGGED_IN = re.compile(
    r"not logged in|please run /login|oauth session expired|"
    r"invalid api key|authentication_error", re.I)

NOT_LOGGED_IN_MSG = (
    "The Claude CLI's sign-in has expired, so it cannot read the sketch.\n\n"
    "Fix it once, then it keeps working:\n"
    "  1. Run:  %USERPROFILE%\\drawing-watcher\\login-helper.cmd\n"
    "     (or open a terminal and run the CLI directly)\n"
    "  2. Type  /login  and finish the sign-in in the browser\n"
    "  3. Type  /quit , then press Read Sketch (AI) again\n\n"
    "Being signed in to the Claude desktop app is not enough — the CLI keeps "
    "its own session. Alternatively set an ANTHROPIC_API_KEY environment "
    "variable (that bills the API per use instead of your subscription).")


def _version_key(name: str) -> tuple:
    return tuple(int(p) if p.isdigit() else -1 for p in name.split("."))


def claude_path() -> str | None:
    # explicit override first — the Docker/cloud image sets CLAUDE_BIN
    env = os.environ.get("CLAUDE_BIN")
    if env and os.path.isfile(env):
        return env
    if os.path.isdir(CLI_VERSION_DIR):
        for v in sorted(os.listdir(CLI_VERSION_DIR), key=_version_key,
                        reverse=True):
            p = os.path.join(CLI_VERSION_DIR, v, "claude.exe")
            if os.path.isfile(p):
                return p
    for p in CLI_CANDIDATES:
        if os.path.isfile(p):
            return p
    found = shutil.which("claude")
    # reject the desktop launcher stub if that is what `claude` resolves to
    if found and "AnthropicClaude" not in found:
        return found
    return None


def cli_status() -> dict:
    """Cheap preflight so the user is not left waiting on a doomed read."""
    exe = claude_path()
    if not exe:
        return {"ok": False, "exe": "",
                "error": "Claude Code CLI not found. Install it with\n"
                         "    npm install -g @anthropic-ai/claude-code\n"
                         "or set the path in core/reader.py."}
    if os.environ.get("ANTHROPIC_API_KEY"):
        return {"ok": True, "exe": exe, "auth": "api-key"}
    cred = os.path.join(HOME, ".claude", ".credentials.json")
    try:
        with open(cred, encoding="utf-8") as fh:
            tok = (json.load(fh).get("claudeAiOauth") or {}).get("accessToken")
        if not tok:
            return {"ok": False, "exe": exe, "error": NOT_LOGGED_IN_MSG}
    except FileNotFoundError:
        return {"ok": False, "exe": exe, "error": NOT_LOGGED_IN_MSG}
    except Exception:
        pass                      # unreadable is not proof of trouble
    return {"ok": True, "exe": exe, "auth": "subscription"}


# ------------------------------------------------------------ input prep
def prepare(path: str, workdir: str, dpi: int = 300) -> list[str]:
    """Normalise the input to a list of high-DPI PNG page images."""
    os.makedirs(workdir, exist_ok=True)
    for stale in os.listdir(workdir):          # a new sketch every time
        if stale.startswith("page_"):
            try:
                os.remove(os.path.join(workdir, stale))
            except OSError:
                pass

    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        # one clean, sharp image per page — the tracing the user found perfect.
        # (No tiling: splitting the sheet into a grid made the AI mis-place a
        # few walls/columns when it stitched the tiles back together.)
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(path)
        out = []
        # Cap the rendered long side. An A1 sheet at 400 dpi is 13000 px wide
        # (~370 MB as RGB) and on a 512 MB cloud box that alone restarts the
        # container mid-read; the vision model never sees more than a few
        # thousand px anyway. MAX_PAGE_PX overrides (default 4200).
        max_px = int(os.environ.get("MAX_PAGE_PX", "4200"))
        for i in range(len(pdf)):
            page = pdf[i]
            w_pt, h_pt = page.get_size()
            scale = max(dpi, 400) / 72.0
            long_pt = max(w_pt, h_pt) or 1.0
            if long_pt * scale > max_px:
                scale = max_px / long_pt
            img = page.render(scale=scale).to_pil()
            p = os.path.join(workdir, f"page_{i + 1:02d}.png")
            img.convert("RGB").save(p)
            img.close()
            out.append(p)
        return out

    if ext == ".dxf":
        # A DXF is rendered to a clean, high-resolution PNG so the very same
        # vision reader that handles photos and PDFs can read it — walls,
        # dimensions, doors, windows, stairs and all. No geometric guessing.
        #
        # CAD files store their line colours by layer, and many are faint greys
        # that all but vanish on a white page — the user saw "no lines". So we
        # force a high-contrast render: every entity redrawn dark on white with
        # thicker strokes, which is what both the eye and the AI need.
        import ezdxf
        from ezdxf.addons.drawing import RenderContext, Frontend
        from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
        from ezdxf.addons.drawing import config as _dcfg
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        doc = ezdxf.readfile(path)
        msp = doc.modelspace()
        cfg = _dcfg.Configuration(
            background_policy=_dcfg.BackgroundPolicy.WHITE,
            color_policy=_dcfg.ColorPolicy.MONOCHROME_LIGHT_BG,
            lineweight_scaling=2.2,
            min_lineweight=1.2,
        )
        fig = plt.figure()
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_axis_off()
        ctx = RenderContext(doc)
        Frontend(ctx, MatplotlibBackend(ax), config=cfg).draw_layout(
            msp, finalize=True)
        p = os.path.join(workdir, "page_01.png")
        fig.savefig(p, dpi=dpi, facecolor="white",
                    bbox_inches="tight", pad_inches=0.1)
        plt.close(fig)
        return [p]

    from PIL import Image
    img = Image.open(path)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    # upscale small phone photos so the dimension text stays readable
    long_side = max(img.size)
    max_px = int(os.environ.get("MAX_PAGE_PX", "4200"))
    if long_side < 2000:
        k = 2000 / long_side
        img = img.resize((int(img.width * k), int(img.height * k)),
                         Image.LANCZOS)
    elif long_side > max_px:            # huge scans: same memory cap as PDFs
        k = max_px / long_side
        img = img.resize((int(img.width * k), int(img.height * k)),
                         Image.LANCZOS)
    p = os.path.join(workdir, "page_01.png")
    img.save(p)
    return [p]


def _tile_label(crop, text: str):
    """Burn a small position label into a tile's top-left corner so the AI can
    place it on the full sheet with certainty (no guessing which tile is which)."""
    from PIL import ImageDraw, ImageFont
    d = ImageDraw.Draw(crop)
    s = max(22, crop.size[0] // 26)
    font = None
    for fp in (r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\arial.ttf"):
        try:
            font = ImageFont.truetype(fp, s)
            break
        except Exception:
            continue
    if font is None:
        font = ImageFont.load_default()
    pad = s // 2
    try:
        w = int(d.textlength(text, font=font))
    except Exception:
        w = len(text) * s
    d.rectangle([0, 0, w + 2 * pad, s + 2 * pad], fill=(210, 30, 30))
    d.text((pad, pad), text, fill=(255, 255, 255), font=font)


def _emit_tiled(img, workdir: str) -> list[str]:
    """Save the full sheet (for scale + overall layout) and, for a large dense
    sheet, a grid of high-resolution TILES of that same sheet so the AI can read
    fine detail it would lose in one shrunk image. Each tile is labelled RrCc
    (row r, col c of the R×C grid) so the AI maps it to the sheet exactly.

    page_01 = full sheet; page_02… = tiles row-major (top row L→R, then down)."""
    from PIL import Image
    pages = []
    W, H = img.size

    # 1. the full sheet, a clean overview for scale and layout
    full = img
    if max(W, H) > 2600:
        k = 2600 / max(W, H)
        full = img.resize((int(W * k), int(H * k)), Image.LANCZOS)
    p0 = os.path.join(workdir, "page_01.png")
    full.convert("RGB").save(p0, quality=95)
    pages.append(p0)

    # 2. tiles — only when the sheet is big enough that one image loses detail
    if max(W, H) <= 2600:
        return pages
    # aim for ~2200 px of source per tile so each tile, once the vision channel
    # samples it, still holds real detail; cap the grid at 4×4.
    cols = max(1, min(4, round(W / 2200)))
    rows = max(1, min(4, round(H / 2200)))
    if cols * rows < 2:
        return pages
    ov = 0.12
    tw, th = W / cols, H / rows
    idx = 2
    for r in range(rows):
        for c in range(cols):
            x0 = max(0, int(c * tw - ov * tw))
            x1 = min(W, int((c + 1) * tw + ov * tw))
            y0 = max(0, int(r * th - ov * th))
            y1 = min(H, int((r + 1) * th + ov * th))
            crop = img.crop((x0, y0, x1, y1)).convert("RGB")
            _tile_label(crop, f"R{r + 1}C{c + 1} of {rows}x{cols}")
            cp = os.path.join(workdir, f"page_{idx:02d}.png")
            crop.save(cp, quality=95)
            pages.append(cp)
            idx += 1
    return pages


# ------------------------------------------------------------- the read
def _extract_json(text: str, out_path: str) -> dict | None:
    """Prefer the file the model was asked to write; fall back to its output."""
    if os.path.isfile(out_path):
        try:
            with open(out_path, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            pass
    for blob in reversed(re.findall(r"```(?:json)?\s*(\{.*?\})\s*```",
                                    text, re.S)):
        try:
            obj = json.loads(blob)
            if isinstance(obj, dict) and "walls" in obj:
                return obj
        except Exception:
            continue
    i, j = text.find("{"), text.rfind("}")
    if i >= 0 and j > i:
        try:
            obj = json.loads(text[i:j + 1])
            if isinstance(obj, dict) and "walls" in obj:
                return obj
        except Exception:
            pass
    return None


# ----------------------------------------------------------- read cache
def _cache_path(workdir: str, sketch: str, prompt: str) -> str:
    """One file per (sketch, prompt). The sketch's size and mtime are in the
    key, so a new or edited drawing is always read afresh — only an identical
    job is ever reused."""
    try:
        stat = os.stat(sketch)
        sig = f"{os.path.abspath(sketch)}|{stat.st_size}|{int(stat.st_mtime)}"
    except OSError:
        sig = sketch
    key = hashlib.sha1((sig + "\n" + prompt).encode("utf-8", "replace"))
    d = os.path.join(workdir, "cache")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, key.hexdigest()[:16] + ".json")


_ACTIVE: set = set()          # running CLI processes, so a read can be stopped


def cancel_all() -> int:
    """Stop every read in flight. Returns how many were stopped."""
    n = 0
    for proc in list(_ACTIVE):
        try:
            proc.kill()
            n += 1
        except Exception:
            pass
        _ACTIVE.discard(proc)
    return n


def read_sketch(sketch_path: str, workdir: str | None = None,
                notes: str = "", timeout: int = 7200,
                on_log=None, fresh: bool = False) -> dict:
    """Return {'plan': dict|None, 'log': str, 'pages': [png...], 'error': str}.

    A sketch that has already been read is not read again: the plan is cached
    against the file's identity and the prompt, so re-opening yesterday's
    drawing is instant. `fresh=True` forces a new read.
    """
    log = on_log or (lambda _s: None)
    workdir = workdir or tempfile.mkdtemp(prefix="sketch2plan_")
    os.makedirs(workdir, exist_ok=True)

    st = cli_status()
    if not st["ok"]:
        return {"plan": None, "pages": [], "log": "", "error": st["error"]}
    exe = st["exe"]

    log("Preparing the sketch at 300 dpi…")
    pages = prepare(sketch_path, workdir)
    log(f"{len(pages)} page image(s) ready.")

    out_json = os.path.join(workdir, "plan.json")
    if os.path.isfile(out_json):
        try:
            os.remove(out_json)          # never read a previous sketch's plan
        except OSError:
            pass

    with open(PROMPT, encoding="utf-8") as fh:
        prompt = fh.read()
    prompt = (prompt
              .replace("{IMAGE_PATH}", "\n    ".join(pages))
              .replace("{OUT_PATH}", out_json))
    if notes.strip():
        prompt += ("\n\n## USER NOTES — these override your reading where they "
                   "conflict\n\n" + notes.strip() + "\n")

    cache = _cache_path(workdir, sketch_path, prompt)
    if not fresh and os.path.isfile(cache):
        try:
            with open(cache, encoding="utf-8") as fh:
                plan = json.load(fh)
            log("This sketch has been read before — reusing that plan, "
                "nothing to read again.")
            return {"plan": plan, "pages": pages, "log": "", "error": ""}
        except Exception:
            pass                      # unreadable cache is simply ignored

    log("Claude is reading the sketch (forensic examination)…")
    t0 = time.time()
    # On Windows, when the server runs windowless (pythonw / the silent VBS), a
    # console child like claude.exe pops its OWN black console window. CREATE_NO_
    # WINDOW keeps it hidden. (0 on Linux, so the cloud build is unaffected.)
    _no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    # Cloud (Render free, 512 MB): cap the CLI's node heap so a heavy read
    # fails inside the child instead of the host killing the whole container.
    env = dict(os.environ)
    if os.environ.get("CLAUDE_NODE_HEAP_MB") or os.environ.get("RENDER"):
        mb = os.environ.get("CLAUDE_NODE_HEAP_MB") or "300"
        env["NODE_OPTIONS"] = (env.get("NODE_OPTIONS", "") +
                               " --max-old-space-size=" + mb).strip()
    try:
        proc = subprocess.Popen(
            [exe, "-p", prompt, "--permission-mode", "acceptEdits"],
            cwd=workdir, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
            creationflags=_no_window, env=env)
    except Exception as e:
        return {"plan": None, "pages": pages, "log": "",
                "error": f"Could not start the Claude CLI: {e}"}

    _ACTIVE.add(proc)
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        return {"plan": None, "pages": pages, "log": "",
                "error": f"The read passed {round(timeout / 60)} minutes and "
                         "was stopped."}
    finally:
        _ACTIVE.discard(proc)

    log(f"Read finished in {time.time() - t0:.0f}s.")
    text = (out or "") + "\n" + (err or "")
    if _NOT_LOGGED_IN.search(text):
        return {"plan": None, "pages": pages, "log": text,
                "error": NOT_LOGGED_IN_MSG}

    plan = _extract_json(text, out_json)
    if plan is None:
        return {"plan": None, "pages": pages, "log": text,
                "error": "Claude did not return usable JSON. See the log."}

    try:
        with open(cache, "w", encoding="utf-8") as fh:
            json.dump(plan, fh, indent=1)
    except Exception:
        pass                          # a read that cannot be cached still counts

    log("Extraction complete.")
    return {"plan": plan, "pages": pages, "log": text, "error": ""}
