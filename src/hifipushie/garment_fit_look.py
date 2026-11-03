"""The look of step 0's fit (garment_fit.py): the picture with the agent's marks (garment edges yellow, body edges cyan,
dashed where inferred; landmarks grey; garment heights orange) and BESIDE it the model's own body with the widths and
heights those ratios give, drawn at the same landmarks: whether the fit READS right. Shape only: numbers are the tool's
text (C288)."""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from . import garment_record as gr
from .garment_plan_look import FONT, FONT_LEG, _line

H = 900
YEL, CYAN, ORANGE, GREY, WHITE = (250, 210, 40), (60, 220, 230), (255, 140, 30), (150, 150, 150), (235, 235, 235)


def _seg(d, a, b, col, w, dash):
    _line(d, [tuple(a), tuple(b)], col, w, dash)
    for p in (a, b):
        d.ellipse([p[0] - 4, p[1] - 4, p[0] + 4, p[1] + 4], outline=col, width=2)


def _photo(read: dict, fit: dict) -> Image.Image:
    fr = read["fit_read"]
    im = Image.open(read["views"][fr["view"]]["image"]).convert("RGB")
    s = H / im.size[1]
    im = im.resize((round(im.size[0] * s), H))
    im = Image.blend(im, Image.new("RGB", im.size, (0, 0, 0)), 0.3)
    d = ImageDraw.Draw(im)
    for k, x in (fr.get("landmarks") or {}).items():
        v = (x[1] if isinstance(x, list) else x) * s
        _line(d, [(0, v), (im.size[0], v)], GREY, 1, (6, 6))
        d.text((4, v - 16), k, fill=GREY, font=FONT)
    for w in fr.get("widths") or []:
        inf = str(w.get("body_from") or "seen") != "seen"
        if w.get("body"):
            _seg(d, *[np.array(p) * s for p in w["body"]], CYAN, 2, (8, 6) if inf else None)
        if w.get("garment"):
            g = [np.array(p) * s for p in w["garment"]]
            _seg(d, *[q + [0, -6] for q in g], YEL, 3, None if str(w.get("garment_from") or "seen") == "seen" else (8, 6))
            d.text((g[1][0] + 8, g[1][1] - 14), w["at"], fill=YEL, font=FONT)
    for h in fr.get("heights") or []:
        v = (h["at"][1] if isinstance(h["at"], list) else h["at"]) * s
        _line(d, [(im.size[0] * 0.15, v), (im.size[0] * 0.85, v)], ORANGE, 2, None)
        d.text((im.size[0] * 0.85 + 4, v - 14), h["name"], fill=ORANGE, font=FONT)
    return im


def _model(read: dict, body, fit: dict, heights: dict) -> Image.Image:
    view = read["views"][read["fit_read"]["view"]].get("view", "front")
    ax = (1, 2) if view == "side" else (0, 2)
    im = Image.new("RGB", (600, H), (24, 25, 28))
    d = ImageDraw.Draw(im)
    mesh = getattr(body, "mesh", None)
    if mesh is None:
        d.text((10, 10), "no body mesh", fill=WHITE, font=FONT_LEG)
        return im
    V, T = np.asarray(mesh[0], float), np.asarray(mesh[1])
    P = V[:, ax]
    z0, z1 = P[:, 1].min(), P[:, 1].max()
    s = (H - 60) / (z1 - z0)
    cx = (P[:, 0].min() + P[:, 0].max()) / 2

    def px(q):
        return np.array([300 + (q[0] - cx) * s, H - 30 - (q[1] - z0) * s])
    Q = np.c_[300 + (P[:, 0] - cx) * s, H - 30 - (P[:, 1] - z0) * s]
    for t in T:
        d.polygon([tuple(Q[i]) for i in t], fill=(95, 95, 100))
    for k, e in fit.items():
        m = body.at(k, view)
        if m.get("centre") is None:
            continue
        c, u = np.array(m["centre"]), np.array(m["dir"])
        hb, hg = m["width_mm"] / 2000, m["width_mm"] * e["ratio"] / 2000
        _seg(d, px(c - u * hb), px(c + u * hb), CYAN, 2, (8, 6) if e["body"] != "seen" else None)
        _seg(d, px(c - u * hg) + [0, -6], px(c + u * hg) + [0, -6], YEL, 3, (8, 6) if e["garment"] != "seen" else None)
        d.text(tuple(px(c + u * hg) + [8, -20]), k, fill=YEL, font=FONT)
    for k, h in heights.items():
        y = H - 30 - (h["z_mm"] / 1000) * s
        _line(d, [(110, y), (490, y)], ORANGE, 2, (8, 6) if h.get("extrapolated") else None)
        d.text((494, y - 14), k, fill=ORANGE, font=FONT)
    return im


def draw(model: str, garment: str, read: dict, body) -> str:
    a, b = _photo(read, read["fit"]), _model(read, body, read["fit"], read.get("heights") or {})
    out = Image.new("RGB", (a.size[0] + b.size[0] + 20, H + 40), (24, 25, 28))
    out.paste(a, (0, 40))
    out.paste(b, (a.size[0] + 20, 40))
    ImageDraw.Draw(out).text((8, 8), f"{garment} step 0 fit: the picture's marks | the model with the widths and heights "
                             "they give (yellow garment, cyan body, orange heights; dashed = inferred; numbers: the text)",
                             fill=WHITE, font=FONT_LEG)
    p = gr.look_dir(model, garment) / "step0_fit.png"
    out.save(p)
    return str(p)
