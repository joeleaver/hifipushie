"""The look of the outline rows (structure_outline.py, T15): each trace and the build's matching outline, drawn over the
reference view, shape only (C288: numbers are the rows' text). Yellow = the traced edge (corners ringed: green kept, red
lost); cyan = the build's outline matched to it (the border points the row compares, shifted by the row's best shift:
the shape); thin grey = the same border placed by the body marks only (where it sits before the shift); magenta = the
worst place. One sheet per view: the whole view on the left, a 3x crop per trace on the right.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from . import structure_outline as so
from .garment_plan_look import _label, _line, _ring, _PLACED

YEL, CY, GREY, MAG, GRN, RED = (255, 225, 0), (0, 220, 255), (160, 160, 160), (255, 60, 220), (60, 230, 90), (255, 50, 50)
CROP_H = 330


def _draw(d, m, sc, off=(0, 0), width=2):
    pl, r = m["placement"], m["result"]
    o = np.asarray(off, float)
    T = np.asarray(m["trace"]["points"], float) * sc - o
    for a in m["arcs"]:
        _line(d, [tuple(p) for p in so.to_px(a, pl) * sc - o], GREY, 1, None)
    sh = np.asarray(r.get("shift_mm") or [0, 0])
    for a, keep in zip(m["arcs"], r.get("kept_masks") or []):  # (only the compared points)
        P = so.to_px(a + sh, pl) * sc - o
        for i in range(len(P) - 1):
            if keep[i] and keep[i + 1]:
                d.line([tuple(P[i]), tuple(P[i + 1])], fill=CY, width=width)
    _line(d, [tuple(p) for p in T], YEL, width, None)
    for c in r.get("corners") or []:
        _ring(d, *T[c["index"]], 8, GRN if c["kept"] else RED if c["kept"] is False else GREY, None)
    if r.get("worst_px"):
        w = np.asarray(r["worst_px"]) * sc - o
        _ring(d, *w, 12, MAG, None)
    return T


def sheet(measured: list, image: str, path: str, title: str = "") -> str:
    """Draw every measured trace of one view (structure_outline.measure's items) over `image`; save to `path`."""
    base = Image.open(image).convert("RGB")
    W = 700
    s = W / base.size[0]
    whole = Image.blend(base.resize((W, round(base.size[1] * s))), Image.new("RGB", (W, round(base.size[1] * s)), (0, 0, 0)), 0.3)
    d = ImageDraw.Draw(whole)
    _PLACED.clear()
    ok = [m for m in measured if m.get("placement") and m.get("arcs") is not None]
    for m in ok:
        T = _draw(d, m, s)
        _label(d, (T[0][0] + 6, T[0][1] - 30), m["trace"]["id"], YEL)
    crops = []
    for m in ok:
        T = np.asarray(m["trace"]["points"], float)
        lo, hi = T.min(0), T.max(0)
        pad = max(25.0, 0.25 * float((hi - lo).max()))
        box = [int(max(lo[0] - pad, 0)), int(max(lo[1] - pad, 0)), int(min(hi[0] + pad, base.size[0])),
               int(min(hi[1] + pad, base.size[1]))]
        k = CROP_H / max(box[3] - box[1], 1)
        if (box[2] - box[0]) * k > 2 * CROP_H:
            k = 2 * CROP_H / (box[2] - box[0])
        c = base.crop(box).resize((round((box[2] - box[0]) * k), round((box[3] - box[1]) * k)))
        c = Image.blend(c, Image.new("RGB", c.size, (0, 0, 0)), 0.3)
        dc = ImageDraw.Draw(c)
        _PLACED.clear()
        _draw(dc, m, k, (box[0] * k, box[1] * k), 3)
        _label(dc, (6, 4), f"{m['trace']['id']}: {m['result']['status']}", WHITE if m["result"]["status"] == "PASS" else RED)
        crops.append(c)
    cw = max([c.size[0] for c in crops] or [1])
    h = max(whole.size[1], sum(c.size[1] + 8 for c in crops))
    out = Image.new("RGB", (W + 10 + cw, h + 30), (24, 25, 28))
    out.paste(whole, (0, 30))
    y = 30
    for c in crops:
        out.paste(c, (W + 10, y))
        y += c.size[1] + 8
    ImageDraw.Draw(out).text((8, 6), title or "outline vs reference: yellow traced, cyan built (shifted), grey built as "
                             "placed, rings: corners (green kept / red lost), magenta worst", fill=(240, 240, 240))
    out.save(path)
    return path


WHITE = (240, 240, 240)
