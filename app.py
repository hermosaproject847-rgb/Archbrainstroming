"""Sketch → Floor Plan — desktop application.

Native window (pywebview / Edge WebView2) around the local UI. All the work
happens in-process: core.reader does the vision read, core.* does the geometry.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import subprocess
import sys
import threading
import time
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

try:                                 # desktop-only (native window); absent on
    import webview  # noqa: E402     # the web host, where dialogs are disabled
except Exception:                    # so a missing pywebview must not break import
    webview = None

from core import combined, library, pipeline, reader  # noqa: E402

WORK = os.path.join(ROOT, "work")
OUT = os.path.join(ROOT, "out")
IMAGE_TYPES = ("Drawings (*.png;*.jpg;*.jpeg;*.pdf;*.webp;*.bmp;*.tif;*.tiff;"
               "*.dxf)",)


def _dataurl(path: str) -> str:
    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as fh:
        return f"data:{mime};base64," + base64.b64encode(fh.read()).decode()


class Api:
    def __init__(self):
        self.window = None
        self.sketch_path = ""
        self.pages: list[str] = []
        self.log_lines: list[str] = []
        self.plan_path = ""            # where Ctrl+S writes
        self._indexing = False

    # -- plumbing ------------------------------------------------------
    def _log(self, s: str) -> None:
        self.log_lines.append(s)
        if self.window:
            try:
                self.window.evaluate_js(f"window.pushLog({json.dumps(s)})")
            except Exception:
                pass

    @staticmethod
    def _fail(e: Exception) -> dict:
        return {"ok": False, "error": f"{type(e).__name__}: {e}",
                "trace": traceback.format_exc()}

    # -- file handling -------------------------------------------------
    def pick_sketch(self) -> dict:
        try:
            sel = self.window.create_file_dialog(
                webview.OPEN_DIALOG, allow_multiple=False,
                file_types=IMAGE_TYPES)
            if not sel:
                return {"ok": True, "cancelled": True}
            path = sel[0]
            self.sketch_path = path
            os.makedirs(WORK, exist_ok=True)
            # A DXF is converted DIRECTLY to an editable plan by reading its CAD
            # layers (walls / doors / windows / room labels) — no image, no AI.
            # If the DXF has no usable layers, we fall back to the vision reader.
            if path.lower().endswith(".dxf"):
                from core import dxfimport
                try:
                    plan, notes, _ = dxfimport.read(path, WORK)
                except Exception as e:
                    plan, notes = None, [f"DXF layer read failed: {e}"]
                for n in notes:
                    self._log("dxf: " + n)
                if plan is not None:
                    self._log("dxf: converted straight to an editable plan.")
                    self.pages = []
                    return {"ok": True, "dxf": True, "plan": plan, "path": path,
                            "name": os.path.basename(path), "pages": []}
                # fall through: render the DXF and let the AI read it
                self._log("dxf: falling back to the vision reader.")
            self.pages = reader.prepare(path, WORK)
            self._log(f"Opened drawing: {os.path.basename(path)} "
                      f"({len(self.pages)} page image(s)).")
            return {"ok": True, "path": path, "name": os.path.basename(path),
                    "pages": [_dataurl(p) for p in self.pages]}
        except Exception as e:
            return self._fail(e)

    def pdf_to_dxf(self, pdf_path: str = "") -> dict:
        """Convert a VECTOR PDF straight to a DXF (geometry only — no AI). On the
        desktop, an empty path opens a file picker. Writes the DXF into the
        output folder and returns its path + entity counts."""
        try:
            from core import pdf2dxf
            if not pdf_path and self.window:
                sel = self.window.create_file_dialog(
                    webview.OPEN_DIALOG, allow_multiple=False,
                    file_types=("PDF (*.pdf)",))
                if not sel:
                    return {"ok": True, "cancelled": True}
                pdf_path = sel[0]
            if not pdf_path or not os.path.isfile(pdf_path):
                return {"ok": False, "error": "No PDF selected."}
            os.makedirs(OUT, exist_ok=True)
            base = os.path.splitext(os.path.basename(pdf_path))[0]
            base = "".join(c for c in base
                           if c.isalnum() or c in " -_").strip() or "drawing"
            out = os.path.join(OUT, base + ".dxf")
            self._log(f"PDF→DXF: converting {os.path.basename(pdf_path)} …")
            res = pdf2dxf.convert(pdf_path, out, "all")
            e = res.get("entities", {})
            self._log(f"PDF→DXF: {res.get('pages')} page(s) → "
                      f"{e.get('lines',0)} lines, {e.get('rects',0)} rects, "
                      f"{e.get('curves',0)} curves, {e.get('text',0)} text  →  "
                      f"{os.path.basename(out)}")
            try:
                if self.window:
                    subprocess.Popen(["explorer", os.path.normpath(OUT)])
            except Exception:
                pass
            return {"ok": True, "path": out, "name": os.path.basename(out),
                    "entities": res.get("entities", {}),
                    "pages": res.get("pages", 0), "folder": OUT}
        except Exception as e:
            return self._fail(e)

    def load_plan_json(self) -> dict:
        try:
            sel = self.window.create_file_dialog(
                webview.OPEN_DIALOG, allow_multiple=False,
                file_types=("Plan JSON (*.json)",))
            if not sel:
                return {"ok": True, "cancelled": True}
            with open(sel[0], encoding="utf-8") as fh:
                plan = json.load(fh)
            # Ctrl+S goes back to the file it came from
            self.plan_path = sel[0]
            return {"ok": True, "plan": plan, "path": sel[0],
                    "name": os.path.basename(sel[0])}
        except Exception as e:
            return self._fail(e)

    def save_plan_json(self, plan: dict, path: str = "") -> dict:
        """Save the plan.

        With a path (Ctrl+S on a plan that has one) it overwrites silently;
        without one it asks where to put it and remembers the answer, so every
        later Ctrl+S — through the floor plan AND the furniture layout — goes
        back to the same file.
        """
        try:
            p = path or self.plan_path
            if not p:
                base = (os.path.splitext(os.path.basename(self.sketch_path))[0]
                        if self.sketch_path else "plan")
                dest = self.window.create_file_dialog(
                    webview.SAVE_DIALOG, save_filename=base + ".json",
                    directory=OUT, file_types=("Plan JSON (*.json)",))
                if not dest:
                    return {"ok": True, "cancelled": True}
                p = dest if isinstance(dest, str) else dest[0]
                if not p.lower().endswith(".json"):
                    p += ".json"
            os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(plan, fh, indent=2)
            self.plan_path = p
            self._log(f"saved {p}")
            return {"ok": True, "path": p, "name": os.path.basename(p)}
        except Exception as e:
            return self._fail(e)

    def save_as(self, plan: dict) -> dict:
        """Ask for a new file and save there from now on."""
        self.plan_path = ""
        return self.save_plan_json(plan)

    # -- the vision read ------------------------------------------------
    # -- the code library ------------------------------------------------
    def library_status(self) -> dict:
        try:
            return {"ok": True, **library.status()}
        except Exception as e:
            return self._fail(e)

    def library_search(self, query: str, limit: int = 5) -> dict:
        try:
            if not library.ready():
                return {"ok": False,
                        "error": "The code library has not been indexed yet. "
                                 "Press Build index — it reads the books in "
                                 "NBC/ once and takes a few minutes."}
            return {"ok": True, "hits": library.search(query, int(limit) or 5)}
        except Exception as e:
            return self._fail(e)

    def library_build(self) -> dict:
        """Index the books. Runs off the UI thread so the window stays alive."""
        if self._indexing:
            return {"ok": True, "already": True}
        self._indexing = True

        def work():
            try:
                self._log("Indexing the code library — this runs once…")
                n = library.build(verbose=False)
                self._log(f"Library indexed: {n} pages.")
            except Exception as e:
                self._log(f"Library indexing failed: {e}")
            finally:
                self._indexing = False

        threading.Thread(target=work, daemon=True).start()
        return {"ok": True, "started": True}

    def cancel_read(self) -> dict:
        try:
            n = reader.cancel_all()
            self._log(f"read cancelled ({n} process(es) stopped)")
            return {"ok": True, "stopped": n}
        except Exception as e:
            return self._fail(e)

    def pick_sketches(self) -> dict:
        """Select MULTIPLE drawings at once (one per floor of a project)."""
        try:
            sel = self.window.create_file_dialog(
                webview.OPEN_DIALOG, allow_multiple=True,
                file_types=IMAGE_TYPES)
            if not sel:
                return {"ok": True, "cancelled": True}
            return {"ok": True, "paths": list(sel),
                    "names": [os.path.basename(p) for p in sel]}
        except Exception as e:
            return self._fail(e)

    def read_path(self, path: str, notes: str = "", fresh: bool = False) -> dict:
        """Read ONE drawing file (given its path) into an editable plan - a DXF
        straight from its layers, anything else via the AI reader. Used to read
        each floor of a multi-floor project."""
        try:
            if not path or not os.path.isfile(path):
                return {"ok": False, "error": "File not found."}
            os.makedirs(WORK, exist_ok=True)
            self.sketch_path = path
            if path.lower().endswith(".dxf"):
                from core import dxfimport
                try:
                    plan, ns, _ = dxfimport.read(path, WORK)
                    for n in ns:
                        self._log("dxf: " + n)
                    if plan is not None:
                        return {"ok": True, "plan": plan, "dxf": True,
                                "name": os.path.basename(path)}
                except Exception as e:
                    self._log(f"dxf: layer read failed ({e}); using AI reader.")
            res = reader.read_sketch(path, WORK, notes, on_log=self._log,
                                     fresh=fresh)
            if res["error"]:
                return {"ok": False, "error": res["error"],
                        "log": res.get("log", "")[-6000:]}
            plan, _n = pipeline.number_openings(res["plan"])
            return {"ok": True, "plan": plan, "name": os.path.basename(path)}
        except Exception as e:
            return self._fail(e)

    def read_sketch(self, notes: str = "", fresh: bool = False) -> dict:
        if not self.sketch_path:
            return {"ok": False, "error": "Open a sketch first."}
        try:
            res = reader.read_sketch(self.sketch_path, WORK, notes,
                                     on_log=self._log, fresh=fresh)
            if res["error"]:
                return {"ok": False, "error": res["error"],
                        "log": res.get("log", "")[-6000:]}
            # Sketches letter their openings "W", "D", "V" and leave the
            # numbering to the draughtsman, so it is done here — along with
            # re-marking any toilet window as the ventilator it is.
            plan, notes = pipeline.number_openings(res["plan"])
            for n in notes:
                self._log("mark: " + n)
            return {"ok": True, "plan": plan,
                    "log": res.get("log", "")[-6000:]}
        except Exception as e:
            return self._fail(e)

    # -- async read (web) ------------------------------------------------
    # An AI read takes ~1-2 min. Behind a proxy / Cloudflare tunnel a single
    # request held that long returns 502. So the web build starts the read as a
    # background job and POLLS for the result with quick requests instead.
    _read_jobs: dict = {}

    def read_async_start(self, path: str, notes: str = "",
                         fresh: bool = False) -> dict:
        import uuid
        job = uuid.uuid4().hex
        Api._read_jobs[job] = {"done": False, "result": None}

        def worker():
            try:
                res = self.read_path(path, notes, fresh)
            except Exception as e:
                res = {"ok": False, "error": str(e)}
            Api._read_jobs[job] = {"done": True, "result": res}

        threading.Thread(target=worker, daemon=True).start()
        return {"ok": True, "job": job}

    def read_async_status(self, job: str = "") -> dict:
        j = Api._read_jobs.get(job)
        if not j:
            return {"ok": False, "error": "unknown job"}
        if not j["done"]:
            return {"ok": True, "done": False}
        # keep the finished result so a retried poll still gets it; prune other
        # old finished jobs so the store cannot grow without bound.
        for k in [k for k, v in Api._read_jobs.items()
                  if v.get("done") and k != job]:
            Api._read_jobs.pop(k, None)
        return {"ok": True, "done": True,
                "result": j["result"] or {"ok": False, "error": "no result"}}

    # -- draw ------------------------------------------------------------
    def number_walls(self, plan: dict, split: bool = True) -> dict:
        """Split walls at room boundaries and renumber them W1, W2, …"""
        try:
            out, notes = pipeline.number_walls(plan, bool(split))
            for n in notes:
                self._log(n)
            return {"ok": True, "plan": out, "notes": notes}
        except Exception as e:
            return self._fail(e)

    def number_openings(self, plan: dict, force: bool = False) -> dict:
        """Re-mark D1/W1/V1 and re-check toilet windows."""
        try:
            out, notes = pipeline.number_openings(plan, bool(force))
            for n in notes:
                self._log("mark: " + n)
            return {"ok": True, "plan": out, "notes": notes}
        except Exception as e:
            return self._fail(e)

    def furnish(self, plan: dict) -> dict:
        """Lay out furniture over the finished floor plan."""
        try:
            out, notes = pipeline.furnish(plan)
            for n in notes:
                self._log("layout: " + n)
            return {"ok": True, "plan": out, "notes": notes,
                    "count": len(out.get("furniture") or [])}
        except Exception as e:
            return self._fail(e)

    def electrify(self, plan: dict) -> dict:
        """Lay the electrical and lighting over the furnished plan."""
        try:
            out, notes = pipeline.electrify(plan)
            for n in notes:
                self._log("elec: " + n)
            return {"ok": True, "plan": out, "notes": notes,
                    "count": len(out.get("elec") or []),
                    "circuits": len(out.get("circuits") or []),
                    "summary": out.get("elec_summary") or {}}
        except Exception as e:
            return self._fail(e)

    def plumb(self, plan: dict) -> dict:
        """Lay the plumbing and drainage over the plan's fixtures."""
        try:
            out, notes = pipeline.plumb(plan)
            for n in notes:
                self._log("plumb: " + n)
            return {"ok": True, "plan": out, "notes": notes,
                    "count": len(out.get("plumb") or []),
                    "pipes": len(out.get("pipes") or [])}
        except Exception as e:
            return self._fail(e)

    def floor(self, plan: dict) -> dict:
        """Set the flooring for every room."""
        try:
            out, notes = pipeline.floor(plan)
            for n in notes:
                self._log("floor: " + n)
            return {"ok": True, "plan": out, "notes": notes,
                    "count": len(out.get("flooring") or [])}
        except Exception as e:
            return self._fail(e)

    def boq(self, plan: dict, floor_height_ft: float = 10.0) -> dict:
        """Generate the architectural BOQ as an Excel workbook with formulas."""
        try:
            from core import boq as BOQ
            from core.model import Plan
            os.makedirs(OUT, exist_ok=True)
            base = os.path.splitext(os.path.basename(
                self.plan_path or self.sketch_path or "plan"))[0].strip() \
                or "plan"
            # if a previous BOQ is still OPEN in Excel the file is locked, so
            # fall back to a fresh name instead of failing
            out_path = os.path.join(OUT, base + "_BOQ.xlsx")
            res = last = None
            for i in range(8):
                try:
                    res = BOQ.generate(Plan.from_dict(plan), out_path,
                                       float(floor_height_ft or 10))
                    break
                except PermissionError as e:
                    last = e
                    out_path = os.path.join(OUT, f"{base}_BOQ ({i + 2}).xlsx")
            if res is None:
                return {"ok": False, "error":
                        "Could not write the BOQ — the file is open in Excel. "
                        "Close it and press BOQ again. (" + str(last) + ")"}
            name = os.path.basename(out_path)
            self._log(f"boq: {res['items']} items, {res['blocked']} blocked "
                      f"→ {name}")
            try:
                subprocess.Popen(["explorer", os.path.normpath(OUT)])
            except Exception:
                pass
            return {"ok": True, "path": out_path, "name": name, "folder": OUT,
                    "items": res["items"], "blocked": res["blocked"]}
        except Exception as e:
            return self._fail(e)

    def questionnaire(self, answers: dict) -> dict:
        """Design a floor plan from the questionnaire. Claude (the same engine as
        Read Drawing) DESIGNS it from the brief + NBC standards - the accurate
        route. Needs the Claude CLI; if it is missing, says so clearly."""
        try:
            from core import designer
            a = answers or {}
            res = designer.design(a, workdir=os.path.join(WORK, "design"),
                                  on_log=self._log)
            if res.get("plan"):
                self.plan_path = ""
                self._log("questionnaire: AI designed a plan with "
                          f"{len(res['plan'].get('rooms') or [])} rooms")
                return {"ok": True, "plan": res["plan"], "source": "ai"}
            return {"ok": False, "error": res.get("error")
                    or "The AI could not design a plan.", "log": res.get("log")}
        except Exception as e:
            return self._fail(e)

    def save_template(self, plan: dict, label: str = "") -> dict:
        """Store the CURRENT plan in the template library so the questionnaire
        can fit it to a new plot later. This is how the accurate library is
        built - from the user's own real plans."""
        try:
            from core import templates
            m = templates.save(plan, label)
            self._log(f"template saved: {m.get('name')} "
                      f"({m.get('bedrooms')} BR, {int(m.get('plot_w'))}x"
                      f"{int(m.get('plot_d'))})")
            return {"ok": True, "meta": m, "count": len(templates.library())}
        except Exception as e:
            return self._fail(e)

    def list_templates(self) -> dict:
        try:
            from core import templates
            return {"ok": True, "templates": templates.library()}
        except Exception as e:
            return self._fail(e)

    def delete_template(self, path: str) -> dict:
        try:
            from core import templates
            return {"ok": templates.delete(path)}
        except Exception as e:
            return self._fail(e)

    def lineout(self, plan: dict) -> dict:
        """Furniture line-out sheet — every piece dimensioned from its walls."""
        try:
            from core import furnlineout
            os.makedirs(OUT, exist_ok=True)
            base = os.path.splitext(os.path.basename(
                self.plan_path or self.sketch_path or "plan"))[0] or "plan"
            paths = furnlineout.export(plan, OUT, base + "_furniture_lineout")
            self._log("lineout: exported " + ", ".join(
                os.path.basename(p) for p in paths.values()))
            try:
                subprocess.Popen(["explorer", os.path.normpath(OUT)])
            except Exception:
                pass
            return {"ok": True, "path": paths.get("pdf") or paths.get("png"),
                    "name": os.path.basename(paths.get("pdf")
                                             or paths.get("png") or ""),
                    "folder": OUT, "paths": paths}
        except Exception as e:
            return self._fail(e)

    def section(self, plan: dict, params: dict) -> dict:
        """Cut every section line onto ONE drawing, show it on screen, store the
        height questionnaire on the plan (so Export reuses it) and write the
        section sheet. Nothing assumed — missing = 0 / skipped."""
        try:
            from core import section as SEC, sheet
            from core import export as EXP
            from core.model import Plan
            os.makedirs(OUT, exist_ok=True)
            if not (plan.get("sections") or []):
                return {"ok": False, "error":
                        "Add a section line on the plan first (Sections tab)."}
            plan = dict(plan)
            plan["section_params"] = dict(params)      # remember for Export
            p = Plan.from_dict(plan)
            # plan on top + section(s) below, together on one drawing
            dl, n = SEC.build_screen(p, params)
            if not n:
                return {"ok": False, "error":
                        "The section line does not cross any wall — move it "
                        "right across the building."}
            composed, info = sheet.compose(p, dl, "A2", "landscape",
                                           schedule="")
            svg = EXP.to_svg(composed, info["w_mm"], info["h_mm"])
            base = os.path.splitext(os.path.basename(
                self.plan_path or self.sketch_path or "plan"))[0].strip() \
                or "plan"
            stem = os.path.join(OUT, base + "_SECTIONS")
            EXP.to_png(composed, info["w_mm"], info["h_mm"], stem + ".png", 200)
            try:
                EXP.to_pdf(composed, info["w_mm"], info["h_mm"], stem + ".pdf")
                EXP.to_dxf(composed, stem + ".dxf", model_scale=info.get("k"))
            except Exception:
                pass
            self._log(f"section: {n} section(s) cut → {os.path.basename(stem)}")
            return {"ok": True, "svg": svg, "info": info, "plan": plan,
                    "count": n, "folder": OUT}
        except Exception as e:
            return self._fail(e)

    def section_project(self, floors: list, params: dict) -> dict:
        """MULTI-FLOOR section: the SAME cut line through every floor's own
        plan, the storeys stacked GL up (ground floor with its foundation, top
        floor with its parapet), one combined dimension stack. `floors` is the
        app's floor list [{name, plan}]; the section lines live on the ground
        (first) plan. Falls back to the single-floor cut for one floor."""
        try:
            from core import section as SEC, sheet
            from core import export as EXP
            from core.model import Plan
            from core.draw import DrawList
            os.makedirs(OUT, exist_ok=True)
            plans = [f.get("plan") for f in (floors or []) if f.get("plan")]
            if len(plans) < 2:
                return self.section(plans[0] if plans else {}, params)
            gf = dict(plans[0])
            secs = gf.get("sections") or []
            if not secs:
                return {"ok": False, "error":
                        "Add a section line on the ground-floor plan first "
                        "(Sections tab) — it applies to every floor."}
            gf["section_params"] = dict(params)
            models = [Plan.from_dict(p) for p in plans]
            out = DrawList()
            dx = 0.0
            n = 0
            for s in secs:
                p1 = (s.get("x1", 0), s.get("y1", 0))
                p2 = (s.get("x2", 0), s.get("y2", 0))
                pp = dict(params, tag=s.get("tag", "A"),
                          view_flip=s.get("flip", False))
                dl, _notes = SEC.build_project(models, p1, p2, pp)
                if not dl.items:
                    continue
                b = dl.bounds()
                w = b[2] - b[0]
                out.extend(dl.translated(dx - b[0], 0))
                tag = s.get("tag", "A")
                out.text(dx + w / 2, b[1] - 2.2,
                         f"SECTION {tag}-{tag}  ·  {len(models)} FLOORS",
                         h=0.9, layer="SEC-TEXT", bold=True)
                dx += w + 12
                n += 1
            if not n:
                return {"ok": False, "error":
                        "The section line does not cross any wall — move it "
                        "right across the building."}
            pm = Plan.from_dict(gf)
            pm.title.plan_name = "MULTI-FLOOR SECTION"
            composed, info = sheet.compose(pm, out, "A2", "landscape",
                                           schedule="")
            svg = EXP.to_svg(composed, info["w_mm"], info["h_mm"])
            base = os.path.splitext(os.path.basename(
                self.plan_path or self.sketch_path or "plan"))[0].strip() \
                or "plan"
            stem = os.path.join(OUT, base + "_SECTION_MULTIFLOOR")
            EXP.to_png(composed, info["w_mm"], info["h_mm"], stem + ".png", 200)
            try:
                EXP.to_pdf(composed, info["w_mm"], info["h_mm"], stem + ".pdf")
                EXP.to_dxf(composed, stem + ".dxf", model_scale=info.get("k"))
            except Exception:
                pass
            self._log(f"multi-floor section: {len(models)} floors, "
                      f"{n} cut(s) stacked")
            return {"ok": True, "svg": svg, "info": info, "plan": gf,
                    "count": n, "folder": OUT}
        except Exception as e:
            return self._fail(e)

    def beams(self, plan: dict, width_mm: float = 230.0,
              depth_mm: float = 300.0, regenerate: bool = False,
              save: bool = True) -> dict:
        """Generate / show the BEAM LAYOUT: a beam on every wall centre-line at
        the given width (default 230 mm) and depth, numbered, with a schedule.
        Beams live on this sheet only. Returns svg + the plan (carrying the
        beams) + the schedule rows."""
        try:
            from core import beamlayout as BL, beams as BM, sheet
            from core import export as EXP
            from core.model import Plan
            from dataclasses import asdict
            os.makedirs(OUT, exist_ok=True)
            # render from a LIGHT plan — only what the beam sheet draws — so a
            # re-render on every edit stays fast even on a big plan (no parsing
            # of furniture / electrical / plumbing / flooring)
            lite = {k: plan[k] for k in ("walls", "rooms", "beams", "title",
                    "plot", "north_deg", "dims") if k in plan}
            p = Plan.from_dict(lite)
            if regenerate or not p.beams:
                p.beams = BM.auto_beams(p, width_mm, depth_mm)
            beams_out = [asdict(b) for b in p.beams]
            p.title.plan_name = "BEAM LAYOUT"
            dl = BL.build_sheet(p)
            composed, info = sheet.compose(p, dl, "A2", "landscape",
                                           schedule="")
            svg = EXP.to_svg(composed, info["w_mm"], info["h_mm"])
            # while editing (save=False) only the SVG is returned — writing the
            # PNG / PDF / DXF on every keystroke is what made it hang
            if save:
                base = os.path.splitext(os.path.basename(
                    self.plan_path or self.sketch_path or "plan"))[0].strip() \
                    or "plan"
                stem = os.path.join(OUT, base + "_BEAM_LAYOUT")
                EXP.to_png(composed, info["w_mm"], info["h_mm"],
                           stem + ".png", 200)
                try:
                    EXP.to_pdf(composed, info["w_mm"], info["h_mm"],
                               stem + ".pdf")
                    EXP.to_dxf(composed, stem + ".dxf",
                               model_scale=info.get("k"))
                except Exception:
                    pass
                self._log(f"beam layout: {len(p.beams)} beams")
            # return ONLY the small beams array (not the whole plan) so the
            # bridge payload per edit stays tiny
            return {"ok": True, "svg": svg, "info": info, "beams": beams_out,
                    "rows": BM.schedule_rows(p), "count": len(p.beams)}
        except Exception as e:
            return self._fail(e)

    def render_project(self, floors: list, sheet: str = "A3",
                       orientation: str = "auto", wall_tags: bool = False,
                       layer_state: dict | None = None) -> dict:
        """The ON-SCREEN multi-floor view — every floor's current drawing side
        by side on one canvas. Used whenever the project has 2+ floors so the
        user sees all floors at once instead of switching between them."""
        try:
            from core import combined
            from core import export as EXP
            out, w, h, info = combined.build_screen_project(
                floors, sheet, orientation, wall_tags, layer_state)
            svg = EXP.to_svg(out, w, h)
            info = {**info, "w_mm": w, "h_mm": h}
            return {"ok": True, "svg": svg, "info": info,
                    "floors": info.get("floors", 0)}
        except Exception as e:
            return self._fail(e)

    def struct_sheets(self, plan: dict) -> dict:
        """The WHOLE structural set on one drawing for the Beam-Layout preview:
        beam layout · plinth framing · roof framing · typical foundation
        section · building section(s). Read-only preview (no files written)."""
        try:
            from core import combined
            from core import export as EXP
            out, w, h, info = combined.build_structural(plan, "A3", "landscape")
            svg = EXP.to_svg(out, w, h)
            info = {**info, "w_mm": w, "h_mm": h}
            return {"ok": True, "svg": svg, "info": info}
        except Exception as e:
            return self._fail(e)

    def elevations(self, plan: dict, params: dict | None = None) -> dict:
        """The four outer ELEVATIONS (front / rear / left / right), developed
        with openings, plinth / roof / parapet and full dimensions. Uses the
        section questionnaire heights if given, else stored, else defaults."""
        try:
            from core import elevation as EL, sheet
            from core import export as EXP
            from core.model import Plan
            os.makedirs(OUT, exist_ok=True)
            plan = dict(plan)
            prm = dict(params or plan.get("section_params") or {})
            if params:
                plan["section_params"] = prm
            p = Plan.from_dict(plan)
            dl = EL.build_all(p, prm)
            if not dl.items:
                return {"ok": False, "error":
                        "No exterior walls found to develop elevations."}
            p.title.plan_name = "ELEVATIONS"
            composed, info = sheet.compose(p, dl, "A2", "landscape", schedule="")
            svg = EXP.to_svg(composed, info["w_mm"], info["h_mm"])
            base = os.path.splitext(os.path.basename(
                self.plan_path or self.sketch_path or "plan"))[0].strip() \
                or "plan"
            stem = os.path.join(OUT, base + "_ELEVATIONS")
            EXP.to_png(composed, info["w_mm"], info["h_mm"], stem + ".png", 200)
            try:
                EXP.to_pdf(composed, info["w_mm"], info["h_mm"], stem + ".pdf")
                EXP.to_dxf(composed, stem + ".dxf", model_scale=info.get("k"))
            except Exception:
                pass
            self._log("elevations: 4 faces developed")
            return {"ok": True, "svg": svg, "info": info, "plan": plan}
        except Exception as e:
            return self._fail(e)

    def elevation_project(self, floors: list, params: dict | None = None) -> dict:
        """MULTI-FLOOR elevations: the four outer faces developed to the full
        building height, EACH storey carrying its own floor's doors / windows.
        `floors` is the app's floor list [{name, plan}]. Falls back to the
        single-floor elevations for one floor."""
        try:
            from core import elevation as EL, sheet
            from core import export as EXP
            from core.model import Plan
            os.makedirs(OUT, exist_ok=True)
            dicts = [f.get("plan") for f in (floors or []) if f.get("plan")]
            if len(dicts) < 2:
                return self.elevations(dicts[0] if dicts else {}, params)
            gf = dict(dicts[0])
            prm = dict(params or gf.get("section_params") or {})
            models = [Plan.from_dict(p) for p in dicts]
            dl = EL.build_project(models, prm)
            if not dl.items:
                return {"ok": False, "error":
                        "No exterior walls found to develop elevations."}
            pm = Plan.from_dict(gf)
            pm.title.plan_name = "MULTI-FLOOR ELEVATIONS"
            composed, info = sheet.compose(pm, dl, "A2", "landscape",
                                           schedule="")
            svg = EXP.to_svg(composed, info["w_mm"], info["h_mm"])
            base = os.path.splitext(os.path.basename(
                self.plan_path or self.sketch_path or "plan"))[0].strip() \
                or "plan"
            stem = os.path.join(OUT, base + "_ELEVATIONS_MULTIFLOOR")
            EXP.to_png(composed, info["w_mm"], info["h_mm"], stem + ".png", 200)
            try:
                EXP.to_pdf(composed, info["w_mm"], info["h_mm"], stem + ".pdf")
                EXP.to_dxf(composed, stem + ".dxf", model_scale=info.get("k"))
            except Exception:
                pass
            self._log(f"multi-floor elevations: {len(models)} floors developed")
            return {"ok": True, "svg": svg, "info": info, "plan": gf}
        except Exception as e:
            return self._fail(e)

    def layer_groups(self) -> dict:
        """The layers the drawing has, and what each view starts from."""
        try:
            from core import layers as LY
            return {"ok": True, "groups": LY.describe(), "views": LY.VIEWS}
        except Exception as e:
            return self._fail(e)

    def furniture_catalogue(self) -> dict:
        """What the Add-furniture dialog offers, grouped by category."""
        try:
            from core import furniture as F
            return {"ok": True, "groups": F.catalogue()}
        except Exception as e:
            return self._fail(e)

    def add_furniture(self, plan: dict, kind: str, room: str = "",
                      wall: str = "") -> dict:
        """Add one piece of the chosen kind, placed to the rules."""
        try:
            from core import layout
            out, msg = layout.add_piece(plan, kind, room, wall)
            self._log("add: " + msg)
            placed = len(out.get("furniture") or []) > \
                len(plan.get("furniture") or [])
            return {"ok": True, "plan": out, "message": msg, "placed": placed}
        except Exception as e:
            return self._fail(e)

    def render(self, plan: dict, sheet: str = "A3",
               orientation: str = "auto", wall_tags: bool = True,
               layer_state: dict | None = None) -> dict:
        try:
            res = pipeline.render(plan, sheet, orientation,
                                  wall_tags=bool(wall_tags),
                                  layer_state=layer_state)
            return {"ok": True, **res}
        except Exception as e:
            return self._fail(e)

    def export(self, plan: dict, sheet: str = "A3",
               orientation: str = "auto", basename: str = "",
               wall_tags: bool = False) -> dict:
        """Everything for this job into its own folder under out/.

        Alongside the individual sheets there is a COMBINED file with the
        floor plan and the furniture layout side by side — one DXF holding
        both, plus the schedule.
        """
        try:
            base = basename or (os.path.splitext(
                os.path.basename(self.sketch_path))[0] if self.sketch_path
                else "floor_plan")
            base = "".join(c for c in base
                           if c.isalnum() or c in " -_").strip() or "plan"
            res = combined.export_folder(plan, OUT, base, sheet, orientation,
                                         light=getattr(self, "WEB", False))
            self._log(f"Exported to {res['folder']}")
            for k, v in res["paths"].items():
                if k.startswith("combined"):
                    self._log(f"  {os.path.basename(v)}")
            return {"ok": True, **res}
        except Exception as e:
            return self._fail(e)

    def export_project(self, floors: list, sheet: str = "A3",
                       orientation: str = "auto", basename: str = "") -> dict:
        """Export a MULTI-FLOOR project as ONE combined file: every floor's
        full set of sheets stacked in a single DXF + PDF (no per-floor folders,
        no separate furniture / plumbing files), wall numbers running
        CONTINUOUSLY across the floors, plus the combined multi-floor section
        and multi-floor elevation at the bottom."""
        try:
            base = "".join(c for c in (basename or "project")
                           if c.isalnum() or c in " -_").strip() or "project"
            usable = [fl for fl in (floors or [])
                      if (fl.get("plan") or {}).get("walls")
                      and (fl.get("plan") or {}).get("rooms")]
            if not usable:
                return {"ok": False,
                        "error": "No floors with a plan to export."}
            res = combined.export_project_folder(usable, OUT, base, sheet,
                                                 orientation)
            for k, v in res.get("paths", {}).items():
                if k.startswith("combined"):
                    self._log(f"  {os.path.basename(v)}")
            self._log(f"Exported {res.get('floors', 0)} floor(s) → "
                      f"one combined DXF + PDF in {res['folder']}")
            try:
                subprocess.Popen(["explorer", os.path.normpath(res["folder"])])
            except Exception:
                pass
            return {"ok": True, "folder": res["folder"],
                    "paths": res.get("paths", {}),
                    "floors": res.get("floors", 0)}
        except Exception as e:
            return self._fail(e)

    def open_folder(self, path: str = "") -> dict:
        try:
            p = path or OUT
            os.makedirs(p, exist_ok=True)
            subprocess.Popen(["explorer", os.path.normpath(p)])
            return {"ok": True}
        except Exception as e:
            return self._fail(e)

    def open_output_folder(self) -> dict:
        try:
            os.makedirs(OUT, exist_ok=True)
            subprocess.Popen(["explorer", os.path.normpath(OUT)])
            return {"ok": True}
        except Exception as e:
            return self._fail(e)

    def open_login(self) -> dict:
        """Open a terminal on the CLI so the user can run /login once."""
        try:
            if os.path.isfile(reader.LOGIN_HELPER):
                subprocess.Popen(["cmd", "/c", "start", "", reader.LOGIN_HELPER],
                                 shell=False)
            else:
                exe = reader.claude_path()
                if not exe:
                    return {"ok": False, "error": "Claude CLI not found."}
                subprocess.Popen(["cmd", "/c", "start", "", exe], shell=False)
            return {"ok": True}
        except Exception as e:
            return self._fail(e)

    def cli_status(self) -> dict:
        try:
            return {"ok": True, **reader.cli_status()}
        except Exception as e:
            return self._fail(e)

    def load_sample(self) -> dict:
        try:
            p = os.path.join(ROOT, "samples", "sample_plan.json")
            with open(p, encoding="utf-8") as fh:
                return {"ok": True, "plan": json.load(fh)}
        except Exception as e:
            return self._fail(e)


APP_TITLE = "ARCH BRAIN STORMING"


def _apply_window_icon() -> None:
    """Give the WebView2 window our creative icon (title bar + taskbar).

    pywebview's Windows backend has no icon parameter, so we find the native
    window by its title once it exists and push the .ico in with WM_SETICON.
    Runs in a daemon thread; failures are silent (icon is cosmetic)."""
    ico = os.path.join(ROOT, "ui", "appicon.ico")
    if os.name != "nt" or not os.path.isfile(ico):
        return
    try:
        import ctypes
        u = ctypes.windll.user32
        IMAGE_ICON, LR = 1, 0x00000010 | 0x00000040   # LOADFROMFILE|DEFAULTSIZE
        WM_SETICON, ICON_SMALL, ICON_BIG = 0x0080, 0, 1
        for _ in range(80):                            # up to ~20 s
            hwnd = u.FindWindowW(None, APP_TITLE)
            if hwnd:
                big = u.LoadImageW(None, ico, IMAGE_ICON, 0, 0, LR)
                sm = u.LoadImageW(None, ico, IMAGE_ICON, 16, 16, 0x00000010)
                if big:
                    u.SendMessageW(hwnd, WM_SETICON, ICON_BIG, big)
                if sm:
                    u.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, sm)
                return
            time.sleep(0.25)
    except Exception:
        pass


def _webview2_present() -> bool:
    """True if the Edge WebView2 runtime is installed. Without it pywebview
    silently falls back to the ancient IE 'WebBrowser' control, which cannot
    render this UI — so we detect it and tell the user plainly instead."""
    if os.name != "nt":
        return True
    try:
        import winreg
        key = (r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients"
               r"\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}")
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(root, key) as k:
                    pv, _ = winreg.QueryValueEx(k, "pv")
                    if pv and pv not in ("", "0.0.0.0"):
                        return True
            except OSError:
                continue
    except Exception:
        pass
    return False


def main() -> None:
    if not _webview2_present():
        # a clear message beats a window full of IE COM-cast errors
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0,
                "Microsoft Edge WebView2 Runtime is not installed on this PC, "
                "so the app cannot draw its window.\n\n"
                "Please install it (free, from Microsoft):\n"
                "https://go.microsoft.com/fwlink/p/?LinkId=2124703\n\n"
                "Then open ARCH BRAIN STORMING again.",
                "ARCH BRAIN STORMING - WebView2 required", 0x10)
            os.startfile("https://go.microsoft.com/fwlink/p/?LinkId=2124703")
        except Exception:
            pass
        return
    api = Api()
    win = webview.create_window(
        APP_TITLE,
        os.path.join(ROOT, "ui", "index.html"),
        js_api=api, width=1500, height=950, min_size=(1100, 700),
        background_color="#12141a")
    api.window = win
    threading.Thread(target=_apply_window_icon, daemon=True).start()
    # force the Edge Chromium backend so it never falls back to the broken IE
    # control; if the runtime is somehow missing this raises cleanly
    try:
        webview.start(gui="edgechromium", debug=False)
    except Exception:
        webview.start(debug=False)


if __name__ == "__main__":
    main()
