"""The project's own sheet format.

Reproduced from `Sheet format 2026.dxf`, measured as fractions of the sheet so
it comes out identical at any paper size. The layout is the standard practice
sheet: the drawing on the left, and a full-height title strip down the right
carrying, from the top —

    KEY PLAN
    issue status ticks  +  the drawing title
    LEGEND
    REVISION table (R1–R5)
    CLIENT / PROJECT  + the practice logo
    NOTES
    SCALE · DRN. BY · DATE · SHEET SIZE · DRG. NO · REV, and the north point

Every figure below is the fraction measured off that file.
"""

from __future__ import annotations

from .draw import Arc, DrawList

L = "TITLE"
LS = "TEXT-SUB"

# ---- vertical rules, as a fraction of the sheet width -----------------
X_FRAME = 0.0048          # the inner frame line
X_STRIP = 0.8479          # where the title strip starts — the drawing ends here
X_R1 = 0.8641             # first inner rule (the "no." column of REVISION)
X_R2 = 0.8997             # second (label / value split at the bottom)
X_R3 = 0.9494
X_R4 = 0.9592
X_R5 = 0.9754
X_R6 = 0.9952             # the outer rule

# ---- horizontal bands, as a fraction of the sheet height --------------
Y_KEYPLAN_TOP = 0.9950
Y_KEYPLAN_BOT = 0.7800
Y_STATUS_TOP = 0.7800
Y_STATUS_BOT = 0.6600
Y_LEGEND_TOP = 0.6600
Y_LEGEND_BOT = 0.4700     # deepened: an electrical legend runs to 17 rows
Y_REV_TOP = 0.4700
Y_REV_BOT = 0.3600
Y_CLIENT_TOP = 0.3600
Y_CLIENT_BOT = 0.2700
Y_NOTES_TOP = 0.2700
Y_NOTES_BOT = 0.0760
Y_INFO_TOP = 0.0760
Y_INFO_BOT = 0.0050

STATUS = ["FOR APPROVAL", "FOR TENDER", "GOOD FOR CONSTRUCTION",
          "FOR COORDINATION", "FOR ACTION/INFORMATION"]

NOTES_TEXT = (
    "ALL DRAWINGS AND WRITTEN MATERIAL APPEARING HEREIN CONSTITUTE THE "
    "ORIGINAL AND UNPUBLISHED WORK OF THE ARCHITECT AND MAY NOT BE "
    "DUPLICATED, USED OR DISCLOSED WITHOUT WRITTEN CONSENT. "
    "DRAWING MUST NOT BE SCALED. ALL DIMENSIONS TO BE CHECKED ON SITE AND "
    "THE ARCHITECT INFORMED OF ANY DISCREPANCY BEFORE PROCEEDING. "
    "READ THIS DRAWING WITH ALL RELEVANT STRUCTURAL AND SERVICES DRAWINGS."
)


def drawing_right(w_mm: float) -> float:
    """Where the drawing window has to stop."""
    return X_STRIP * w_mm


def draw(dl: DrawList, plan, w_mm: float, h_mm: float, scale: str,
         sheet_name: str, drawing_title: str = "") -> None:
    W, H = w_mm, h_mm
    t = plan.title

    def X(f):
        return f * W

    def Y(f):
        return f * H

    # -- the frame -----------------------------------------------------
    dl.rect(0, 0, W, H, layer=L)
    dl.rect(X(X_FRAME), Y(0.0050), W - 2 * X(X_FRAME), H - 2 * Y(0.0050),
            layer=L)

    sx0, sx1 = X(X_STRIP), X(X_R6)
    dl.line(sx0, Y(0.0050), sx0, H - Y(0.0050), layer=L)

    def band(y0, y1):
        dl.line(sx0, Y(y0), sx1, Y(y0), layer=L)
        dl.line(sx0, Y(y1), sx1, Y(y1), layer=L)

    def label(x, y, s, h=2.4, bold=False, layer=L, align="left"):
        dl.text(X(x), Y(y), s, h=h, layer=layer, halign=align, bold=bold)

    # -- KEY PLAN ------------------------------------------------------
    band(Y_KEYPLAN_BOT, Y_KEYPLAN_TOP)
    label((X_STRIP + X_R6) / 2, Y_KEYPLAN_TOP - 0.012, "KEY PLAN", 3.0,
          bold=True, align="center")

    # -- issue status, with the drawing title down the right -----------
    band(Y_STATUS_BOT, Y_STATUS_TOP)
    box = (Y_STATUS_TOP - Y_STATUS_BOT) / (len(STATUS) + 1)
    tick_x = X(X_STRIP) + 4
    for i, s in enumerate(STATUS):
        yy = Y_STATUS_TOP - box * (i + 1)
        b = 2.6
        dl.rect(tick_x, Y(yy) - b / 2, b, b, layer=L)
        dl.text(tick_x + b + 2.5, Y(yy), s, h=2.1, layer=LS, halign="left")
    # the drawing this sheet carries, running up the right edge
    dl.text(X((X_R5 + X_R6) / 2), Y((Y_STATUS_TOP + Y_STATUS_BOT) / 2),
            (drawing_title or t.plan_name or "FLOOR PLAN").upper(),
            h=3.2, layer=L, angle=90, bold=True)
    dl.line(X(X_R5), Y(Y_STATUS_BOT), X(X_R5), Y(Y_STATUS_TOP), layer=L)

    # -- LEGEND --------------------------------------------------------
    band(Y_LEGEND_BOT, Y_LEGEND_TOP)
    label((X_STRIP + X_R6) / 2, Y_LEGEND_TOP - 0.012, "LEGEND", 3.0,
          bold=True, align="center")

    # -- REVISION ------------------------------------------------------
    band(Y_REV_BOT, Y_REV_TOP)
    label((X_STRIP + X_R6) / 2, Y_REV_TOP - 0.012, "REVISION", 3.0,
          bold=True, align="center")
    hdr = Y_REV_TOP - 0.030
    dl.line(sx0, Y(hdr), sx1, Y(hdr), layer=L)
    label(X_STRIP + 0.010, hdr - 0.014, "no.", 2.0, layer=LS)
    label(X_R2 - 0.030, hdr - 0.014, "description", 2.0, layer=LS)
    label(X_R5 + 0.004, hdr - 0.014, "date", 2.0, layer=LS)
    for c in (X_R1, X_R5):
        dl.line(X(c), Y(Y_REV_BOT), X(c), Y(hdr), layer=L)
    rows = 5
    step = (hdr - 0.018 - Y_REV_BOT) / rows
    for i in range(rows):
        yy = hdr - 0.018 - step * i
        label(X_STRIP + 0.010, yy - step * 0.62, f"R{i + 1}", 2.2, bold=True)
        if i:
            dl.line(sx0, Y(yy), sx1, Y(yy), layer=L)

    # -- CLIENT / PROJECT ----------------------------------------------
    band(Y_CLIENT_BOT, Y_CLIENT_TOP)
    mid = (Y_CLIENT_TOP + Y_CLIENT_BOT) / 2
    dl.line(sx0, Y(mid), sx1, Y(mid), layer=L)
    # the practice mark gets its own column so it never sits on the names
    logo_w = (X_R6 - X_STRIP) * W * 0.26
    dl.line(X(X_STRIP) + logo_w, Y(Y_CLIENT_BOT),
            X(X_STRIP) + logo_w, Y(Y_CLIENT_TOP), layer=L)
    dl.text(X(X_STRIP) + logo_w / 2, Y((Y_CLIENT_BOT + Y_CLIENT_TOP) / 2),
            "OLS", h=min(6.0, logo_w * 0.42), layer=L, bold=True)

    tx = X(X_STRIP) + logo_w + 3
    for y0, y1, key, val in ((mid, Y_CLIENT_TOP, "CLIENT",
                              getattr(t, "client", "") or "—"),
                             (Y_CLIENT_BOT, mid, "PROJECT",
                              t.project or "—")):
        dl.text(tx, Y(y1) - 5.0, key, h=2.0, layer=LS, halign="left")
        dl.text(tx, Y(y1) - 10.5, str(val).upper()[:34], h=2.7, layer=L,
                halign="left")

    # -- NOTES ---------------------------------------------------------
    band(Y_NOTES_BOT, Y_NOTES_TOP)
    label(X_STRIP + 0.008, Y_NOTES_TOP - 0.016, "NOTES", 2.6, bold=True)
    strip_w = (X_R6 - X_STRIP) * W - 6
    yy = Y_NOTES_TOP - 0.030
    body = NOTES_TEXT
    if t.wall_note:
        from . import units as _u
        body = _u.relabel(t.wall_note.upper()) + "  " + body
    for line in _wrap(body, strip_w, 1.9)[:26]:
        dl.text(X(X_STRIP) + 3, Y(yy), line, h=1.9, layer=LS, halign="left")
        yy -= 0.0088
        if yy < Y_NOTES_BOT + 0.004:
            break

    # -- the bottom information block ----------------------------------
    # left two thirds carry the five label/value rows, the right third the
    # north point, so nothing shares a cell
    band(Y_INFO_BOT, Y_INFO_TOP)
    split = X_STRIP + (X_R6 - X_STRIP) * 0.62
    dl.line(X(split), Y(Y_INFO_BOT), X(split), Y(Y_INFO_TOP), layer=L)

    rows = [("SCALE", scale or "NTS"), ("DRN. BY", t.drawn_by or "—"),
            ("DATE", t.date or "—"), ("SHEET SIZE", sheet_name),
            ("DRG. NO", f"{getattr(t, 'drawing_no', '') or '01'}   "
                        f"{t.revision or 'R0'}")]
    step = (Y_INFO_TOP - Y_INFO_BOT) / len(rows)
    keyx = X(X_STRIP) + 3
    valx = X(X_STRIP) + (X(split) - X(X_STRIP)) * 0.52
    dl.line(valx - 2, Y(Y_INFO_BOT), valx - 2, Y(Y_INFO_TOP), layer=L)
    for i, (k, v) in enumerate(rows):
        yy = Y_INFO_TOP - step * (i + 1)
        if i:
            dl.line(sx0, Y(yy + step), X(split), Y(yy + step), layer=L)
        dl.text(keyx, Y(yy + step * 0.36), k, h=1.9, layer=LS, halign="left")
        dl.text(valx, Y(yy + step * 0.36), str(v), h=2.3, layer=L,
                halign="left")

    # -- north point, in its own cell ----------------------------------
    ncx = X((split + X_R6) / 2)
    dl.text(ncx, Y(Y_INFO_TOP) - 4.5, "NORTH", h=2.0, layer=LS)
    _north(dl, ncx, Y((Y_INFO_BOT + Y_INFO_TOP) / 2) - 2.0,
           min((X(X_R6) - X(split)) * 0.26, (Y(Y_INFO_TOP) - Y(Y_INFO_BOT))
               * 0.22), plan.north_deg)


def _north(dl: DrawList, cx: float, cy: float, r: float, deg: float) -> None:
    """The compass rose of the practice sheet: N/E/S/W with a filled needle."""
    import math
    a = math.radians(deg)
    tip = (cx + r * math.cos(a), cy + r * math.sin(a))
    tail = (cx - r * math.cos(a), cy - r * math.sin(a))
    p = a + math.pi / 2
    lft = (cx + r * 0.3 * math.cos(p), cy + r * 0.3 * math.sin(p))
    rgt = (cx - r * 0.3 * math.cos(p), cy - r * 0.3 * math.sin(p))
    dl.poly([tip, lft, tail, rgt], layer=L, closed=True)
    dl.line(tip[0], tip[1], tail[0], tail[1], layer=L)
    for lbl, ang in (("N", deg), ("S", deg + 180), ("E", deg - 90),
                     ("W", deg + 90)):
        t = math.radians(ang)
        dl.text(cx + r * 1.45 * math.cos(t), cy + r * 1.45 * math.sin(t),
                lbl, h=2.0, layer=LS)


def _wrap(text: str, width_mm: float, h: float) -> list[str]:
    per = max(10, int(width_mm / (h * 0.52)))
    out, line = [], ""
    for word in (text or "").split():
        trial = (line + " " + word).strip()
        if len(trial) <= per:
            line = trial
        else:
            if line:
                out.append(line)
            line = word
    if line:
        out.append(line)
    return out
