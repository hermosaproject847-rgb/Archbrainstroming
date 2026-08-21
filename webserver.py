"""SketchToPlan as a WEB app — serves the same HTML/JS UI and exposes the Api
over HTTP so it runs in any browser (phone included), hosted on a cloud server.

The AI 'Read Drawing' / questionnaire features need the Claude CLI and are NOT
available here; every OFFLINE feature works fully — load a DXF/JSON plan, edit,
furniture, the whole structural set, and the single combined-DXF export.

Run locally:   python webserver.py         (then open http://localhost:8080)
On a host:     the platform sets $PORT; bind 0.0.0.0.
"""

from __future__ import annotations

import os
import sys
import traceback

# the embeddable Python's restricted ._pth does not add the script directory, so
# do it here before importing the app modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bottle
from bottle import Bottle, request, static_file, HTTPResponse

import app as APP

ROOT = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(ROOT, "ui")
UPLOADS = os.path.join(APP.WORK, "uploads")
os.makedirs(APP.OUT, exist_ok=True)
os.makedirs(UPLOADS, exist_ok=True)

api = APP.Api()                     # window is None — dialog methods unused here
try:
    api.WEB = True                  # let the bridge know it is headless
except Exception:
    pass

web = Bottle()

# methods that open a NATIVE dialog / the file explorer — meaningless on the web,
# where the browser handles files. The UI uses /upload and /download instead.
_DESKTOP_ONLY = {"pick_sketch", "pick_sketches", "load_plan_json",
                 "save_plan_json", "open_folder", "open_output_folder",
                 "open_login"}


@web.get("/")
def index():
    return static_file("index.html", root=UI)


@web.get("/health")
def health():
    return {"ok": True}


@web.post("/rpc/<method>")
def rpc(method):
    try:
        args = request.json
        if args is None:
            args = []
        if not isinstance(args, list):
            args = [args]
        if method in _DESKTOP_ONLY:
            return {"ok": False, "web": True,
                    "error": "Use the browser's file picker (Open) / Download."}
        fn = getattr(api, method, None)
        if not callable(fn):
            return {"ok": False, "error": f"unknown method: {method}"}
        result = fn(*args)
        if isinstance(result, dict):
            return result
        return {"ok": True, "result": result}
    except Exception as e:
        traceback.print_exc()
        return {"ok": False, "error": str(e)}


@web.post("/upload")
def upload():
    """Receive a sketch / DXF / JSON from the browser, save it server-side, and
    return the path so the normal read_path(path) / load flow can use it."""
    try:
        f = request.files.get("file")
        if not f:
            return {"ok": False, "error": "no file"}
        safe = os.path.basename(f.raw_filename or f.filename or "upload")
        dest = os.path.join(UPLOADS, safe)
        if os.path.exists(dest):
            os.remove(dest)
        f.save(dest, overwrite=True)
        return {"ok": True, "path": dest, "name": safe}
    except Exception as e:
        traceback.print_exc()
        return {"ok": False, "error": str(e)}


@web.get("/download")
def download():
    """Stream an exported file (given its server path, under OUT) to the
    browser as a download."""
    p = request.query.get("path", "")
    ap = os.path.abspath(p)
    if not (ap.startswith(os.path.abspath(APP.OUT)) and os.path.isfile(ap)):
        return HTTPResponse(status=404, body="not found")
    return static_file(os.path.basename(ap), root=os.path.dirname(ap),
                       download=os.path.basename(ap))


@web.get("/<filepath:path>")
def statics(filepath):
    return static_file(filepath, root=UI)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    # waitress is a real production WSGI server (threaded, correct Content-Length
    # behind a proxy). wsgiref — the stdlib fallback — is single-threaded and can
    # send a response the cloud proxy truncates, which the browser then sees as an
    # empty body ("Unexpected end of JSON input"). Prefer waitress; fall back to
    # wsgiref only if it is not installed (e.g. a bare desktop checkout).
    try:
        from waitress import serve
        print(f"SketchToPlan web (waitress) on http://0.0.0.0:{port}  "
              f"(AI read disabled)")
        serve(web, host="0.0.0.0", port=port, threads=8,
              channel_timeout=300)
    except ImportError:
        print(f"SketchToPlan web (wsgiref fallback) on http://0.0.0.0:{port}")
        bottle.run(web, host="0.0.0.0", port=port, server="wsgiref",
                   quiet=False)
