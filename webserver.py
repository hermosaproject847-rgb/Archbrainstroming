"""SketchToPlan as a WEB app — serves the same HTML/JS UI and exposes the Api
over HTTP so it runs in any browser (phone included), hosted on a cloud server.

Access is gated by a simple login: an ADMIN (you) signs in to an admin panel to
create / block / delete client logins; a client signs straight into the software.
Users live in users.json next to this file (auto-created with a default admin).

Run locally:   python webserver.py         (then open http://localhost:8080)
On a host:     the platform sets $PORT; bind 0.0.0.0.
"""

from __future__ import annotations

import json as _json
import os
import secrets as _secrets
import sys
import threading as _threading
import traceback

# the embeddable Python's restricted ._pth does not add the script directory, so
# do it here before importing the app modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bottle
from bottle import (Bottle, request, response, redirect, static_file,
                    HTTPResponse)

# Bottle parses request.json only up to MEMFILE_MAX (default 100 KB) and
# answers 413 'Request entity too large' beyond it — a multi-floor project
# ("All floors on one sheet") posts the WHOLE project JSON, megabytes of it.
bottle.BaseRequest.MEMFILE_MAX = 256 * 1024 * 1024

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

# ---------------------------------------------------------------- auth store
# NOTE: passwords are stored as typed so the admin can SEE them in the panel
# (an explicit product requirement for handing logins to paying clients). Keep
# users.json private; it is git-ignored. Sessions are in-memory tokens.
USERS_FILE = os.path.join(os.environ.get("DATA_DIR") or ROOT, "users.json")
_users_lock = _threading.Lock()
SESSIONS: dict = {}                 # token -> {"user":..., "role":...}


def _default_users():
    return {"users": [{"username": "admin", "password": "sara@admin",
                       "role": "admin", "active": True}]}


def load_users():
    try:
        with open(USERS_FILE, encoding="utf-8") as fh:
            data = _json.load(fh)
        if data.get("users"):
            return data
    except Exception:
        pass
    data = _default_users()
    save_users(data)
    return data


def save_users(data):
    with open(USERS_FILE, "w", encoding="utf-8") as fh:
        _json.dump(data, fh, indent=2)


def _find_user(uname):
    for u in load_users()["users"]:
        if u["username"].lower() == (uname or "").strip().lower():
            return u
    return None


def _current():
    tok = request.get_cookie("abs_sess")
    return SESSIONS.get(tok) if tok else None


def _is_admin():
    c = _current()
    return c if (c and c.get("role") == "admin") else None


# ---------------------------------------------------------------- no-cache
def _no_cache(resp):
    resp.set_header("Cache-Control", "no-cache, no-store, must-revalidate")
    resp.set_header("Pragma", "no-cache")
    resp.set_header("Expires", "0")
    return resp


def _serve_app_html():
    """The software UI (index.html) with a mtime version query on app.js /
    style.css so Cloudflare's edge never serves a stale build."""
    try:
        with open(os.path.join(UI, "index.html"), encoding="utf-8") as fh:
            html = fh.read()

        def _v(fn):
            try:
                return str(int(os.path.getmtime(os.path.join(UI, fn))))
            except Exception:
                return "1"

        html = html.replace('src="app.js"', 'src="app.js?v=%s"' % _v("app.js"))
        html = html.replace('href="style.css"',
                            'href="style.css?v=%s"' % _v("style.css"))
        r = HTTPResponse(body=html)
        r.set_header("Content-Type", "text/html; charset=utf-8")
        return _no_cache(r)
    except Exception:
        return _no_cache(static_file("index.html", root=UI))


# ---------------------------------------------------------------- pages
@web.get("/")
def login_page():
    return _no_cache(static_file("login.html", root=UI))


# login-page assets must be public (the visitor is not signed in yet)
@web.get("/login-bg.jpg")
def login_bg():
    return _no_cache(static_file("login-bg.jpg", root=UI))


@web.get("/favicon.ico")
def favicon():
    # Google fetches /favicon.ico on every site; it must be PUBLIC and an
    # image — behind the login redirect it received HTML, hence the globe
    return static_file("appicon.png", root=UI, mimetype="image/png")


@web.get("/robots.txt")
def robots():
    response.content_type = "text/plain; charset=utf-8"
    return "User-agent: *\nAllow: /\n"


@web.get("/appicon.png")
def appicon():
    return static_file("appicon.png", root=UI)


@web.get("/app")
def app_page():
    if not _current():
        return redirect("/")
    return _serve_app_html()


@web.get("/health")
def health():
    return {"ok": True}


# ---------------------------------------------------------------- auth API
@web.post("/login")
def do_login():
    d = request.json or {}
    u = _find_user(d.get("username"))
    if not u or u.get("password") != d.get("password"):
        return {"ok": False, "error": "Wrong username or password."}
    if not u.get("active", True):
        return {"ok": False,
                "error": "This login is blocked — contact admin to renew."}
    tok = _secrets.token_hex(24)
    SESSIONS[tok] = {"user": u["username"], "role": u.get("role", "client")}
    response.set_cookie("abs_sess", tok, path="/", httponly=True,
                        max_age=86400 * 7)
    return {"ok": True, "user": u["username"], "role": u.get("role", "client")}


@web.post("/logout")
def do_logout():
    tok = request.get_cookie("abs_sess")
    if tok:
        SESSIONS.pop(tok, None)
    response.delete_cookie("abs_sess", path="/")
    return {"ok": True}


@web.get("/me")
def me():
    c = _current()
    if not c:
        return {"ok": True, "user": None}
    return {"ok": True, "user": c["user"], "role": c["role"]}


# ---------------------------------------------------------------- admin API
@web.get("/admin/users")
def admin_users():
    if not _is_admin():
        return {"ok": False, "error": "admin only"}
    return {"ok": True, "users": load_users()["users"]}


@web.post("/admin/create")
def admin_create():
    if not _is_admin():
        return {"ok": False, "error": "admin only"}
    d = request.json or {}
    uname = (d.get("username") or "").strip()
    pw = (d.get("password") or "").strip()
    if not uname or not pw:
        return {"ok": False, "error": "username & password required"}
    with _users_lock:
        data = load_users()
        if any(x["username"].lower() == uname.lower() for x in data["users"]):
            return {"ok": False, "error": "that username already exists"}
        data["users"].append({"username": uname, "password": pw,
                               "role": "client", "active": True})
        save_users(data)
    return {"ok": True}


@web.post("/admin/setactive")
def admin_setactive():
    if not _is_admin():
        return {"ok": False, "error": "admin only"}
    d = request.json or {}
    uname = (d.get("username") or "").lower()
    with _users_lock:
        data = load_users()
        for x in data["users"]:
            if x["username"].lower() == uname and x.get("role") != "admin":
                x["active"] = (not x.get("active", True)) if d.get("toggle") \
                    else bool(d.get("active"))
        save_users(data)
    # drop any live session of a just-blocked user so the block is immediate
    for tok, s in list(SESSIONS.items()):
        u = _find_user(s["user"])
        if not u or not u.get("active", True):
            SESSIONS.pop(tok, None)
    return {"ok": True}


@web.post("/admin/delete")
def admin_delete():
    if not _is_admin():
        return {"ok": False, "error": "admin only"}
    d = request.json or {}
    uname = (d.get("username") or "").lower()
    with _users_lock:
        data = load_users()
        data["users"] = [x for x in data["users"]
                         if not (x["username"].lower() == uname
                                 and x.get("role") != "admin")]
        save_users(data)
    for tok, s in list(SESSIONS.items()):
        if s["user"].lower() == uname:
            SESSIONS.pop(tok, None)
    return {"ok": True}


@web.post("/admin/passwd")
def admin_passwd():
    c = _is_admin()
    if not c:
        return {"ok": False, "error": "admin only"}
    pw = ((request.json or {}).get("password") or "").strip()
    if not pw:
        return {"ok": False, "error": "password required"}
    with _users_lock:
        data = load_users()
        for x in data["users"]:
            if x["username"] == c["user"]:
                x["password"] = pw
        save_users(data)
    return {"ok": True}


# ---------------------------------------------------------------- app API
@web.post("/rpc/<method>")
def rpc(method):
    if not _current():
        return {"ok": False, "auth": False, "error": "Please sign in again."}
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
    if not _current():
        return {"ok": False, "error": "Please sign in again."}
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
    if not _current():
        return HTTPResponse(status=403, body="sign in")
    p = request.query.get("path", "")
    ap = os.path.abspath(p)
    if not (ap.startswith(os.path.abspath(APP.OUT)) and os.path.isfile(ap)):
        return HTTPResponse(status=404, body="not found")
    return static_file(os.path.basename(ap), root=os.path.dirname(ap),
                       download=os.path.basename(ap))


@web.get("/<filepath:path>")
def statics(filepath):
    # login page is self-contained; every other UI asset needs a session
    if not _current():
        return redirect("/")
    return _no_cache(static_file(filepath, root=UI))


def _seed_claude_credentials():
    """Cloud host: the Claude CLI login token comes in as the CLAUDE_CREDENTIALS
    secret (the content of ~/.claude/.credentials.json from the user's PC).
    Write it where the CLI expects it, once, at startup. No secret → no-op."""
    raw = os.environ.get("CLAUDE_CREDENTIALS")
    if not raw:
        return
    try:
        d = os.path.join(os.path.expanduser("~"), ".claude")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, ".credentials.json")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(raw)
        try:
            os.chmod(p, 0o600)
        except Exception:
            pass
        print("Claude CLI credentials seeded from CLAUDE_CREDENTIALS.")
    except Exception as e:
        print("Could not seed Claude credentials:", e)


def _seed_users():
    """Cloud host without persistent disk: the USERS_JSON secret (the content of
    users.json) restores the user list on every container restart. Only used
    when no users.json exists yet, so live edits during a run still win."""
    raw = os.environ.get("USERS_JSON")
    if not raw or os.path.isfile(USERS_FILE):
        return
    try:
        json.loads(raw)             # must be valid JSON before we trust it
        with open(USERS_FILE, "w", encoding="utf-8") as fh:
            fh.write(raw)
        print("users.json seeded from USERS_JSON.")
    except Exception as e:
        print("Could not seed users.json:", e)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    _seed_claude_credentials()      # cloud: CLI login token from the secret
    _seed_users()                   # cloud: user list from the secret
    load_users()                    # ensure users.json + default admin exist
    # waitress is a real production WSGI server (threaded, correct Content-Length
    # behind a proxy). wsgiref — the stdlib fallback — is single-threaded and can
    # send a response the cloud proxy truncates. Prefer waitress.
    try:
        from waitress import serve
        print(f"ARCH BRAIN STORMING web (waitress) on http://0.0.0.0:{port}")
        serve(web, host="0.0.0.0", port=port, threads=8, channel_timeout=300)
    except ImportError:
        print(f"ARCH BRAIN STORMING web (wsgiref) on http://0.0.0.0:{port}")
        bottle.run(web, host="0.0.0.0", port=port, server="wsgiref",
                   quiet=False)
