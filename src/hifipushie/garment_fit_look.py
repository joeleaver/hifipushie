"""The look of step 0's fit (garment_fit.py): the picture with the agent's marks (garment edges yellow, body edges cyan,
dashed where inferred; landmarks grey; garment heights orange) with the VERTICAL reading drawn as plainly as the widths:
a ruler down the left with every landmark's tick (dashed = inferred, dotted = floor / crown: never used for heights) and,
for each height, a bracket over the span it was read in with its tick; where the tool moved a seen edge to the picture's
edge, the agent's mark is a small grey ring. BESIDE it the model's own body with the widths and
heights those ratios give, drawn at the same landmarks: whether the fit READS right. Shape only: numbers are the tool's
text (C288)."""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from . import garment_record as gr
from .garment_plan_look import FONT, FONT_LEG, _line

H = 900
OX = 110  # (the photo's left margin: the ruler)
RM = 150  # (each panel's right margin: every label, outside the picture, so no garment's shape decides where they fit)
YEL, CYAN, ORANGE, GREY, WHITE = (250, 210, 40), (60, 220, 230), (255, 140, 30), (150, 150, 150), (235, 235, 235)


GAP = 12  # (the garment's bar this far above the body's: 6 px overlapped on a narrow limb, Joe 2026-11-03)


def _seg(d, a, b, col, w, dash):
    """A width bar with short end ticks across it (circles overlapped on a narrow limb)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    _line(d, [tuple(a), tuple(b)], col, w, dash)
    t = b - a
    n = np.array([-t[1], t[0]]) / (np.linalg.norm(t) or 1.0) * 5
    for p in (a, b):
        d.line([tuple(p - n), tuple(p + n)], fill=col, width=2)


def _label(d, anchor, text, x, used, col=YEL):
    """A label in the panel's right margin at x, at the anchor's height (moved down past earlier labels), with a thin
    leader from the anchor: general for any garment, the margin is never covered by one."""
    y = float(anchor[1]) - 8
    while any(abs(y - u) < 18 for u in used):
        y += 18
    used.append(y)
    _line(d, [tuple(anchor), (x - 4, y + 8)], col, 1, (3, 3))
    d.text((x, y), text, fill=col, font=FONT)


def _lmarks(read: dict) -> dict:
    from .garment_fit_marks import landmark
    out = {}
    for k, x in (read["fit_read"].get("landmarks") or {}).items():
        m = landmark(x)
        if m:
            out[k] = m[:2]
    return out


def _ruler(d, ys: dict, inferred: set, heights: dict, hy: dict, x0: float, width: float):
    """A ruler at x0: landmark ticks (dashed inferred, dotted floor / crown), a bracket per height over its span."""
    from .garment_fit import UNDER
    if not ys:
        return
    lo, hi = min(ys.values()), max(ys.values())
    _line(d, [(x0, lo), (x0, hi)], GREY, 2, None)
    for k, y in ys.items():
        dash = (2, 5) if k in UNDER else (8, 8) if k in inferred else None
        _line(d, [(x0 - 10, y), (x0 + 10, y)], GREY, 2, dash)
        _line(d, [(x0 + 10, y), (x0 + width, y)], GREY, 1, dash)
        d.text((x0 - 8, y - 18), k, fill=GREY, font=FONT)
    for i, (k, h) in enumerate(heights.items()):
        a, b = h.get("between") or [None, None]
        if a not in ys or b not in ys or k not in hy:
            continue
        x, y = x0 + 22 + 12 * i, hy[k]
        ya, yb = ys[a], ys[b]
        top, bot = min(ya, yb, y), max(ya, yb, y)
        _line(d, [(x, ys[a]), (x, ys[b])], ORANGE, 2, None)
        if not min(ya, yb) <= y <= max(ya, yb):  # (extrapolated: the reach beyond its span dashed)
            _line(d, [(x, top), (x, bot)], ORANGE, 1, (4, 4))
        for yy in (ya, yb):
            _line(d, [(x - 4, yy), (x + 4, yy)], ORANGE, 2, None)
        d.ellipse([x - 5, y - 5, x + 5, y + 5], fill=ORANGE)


def _photo(read: dict, fit: dict) -> Image.Image:
    fr = read["fit_read"]
    im = Image.open(read["views"][fr["view"]]["image"]).convert("RGB")
    s = H / im.size[1]
    im = im.resize((round(im.size[0] * s), H))
    im = Image.blend(im, Image.new("RGB", im.size, (0, 0, 0)), 0.3)
    base = Image.new("RGB", (im.size[0] + OX + RM, H), (24, 25, 28))  # (the ruler in a margin: grey on the photo doesn't read)
    base.paste(im, (OX, 0))
    im, d = base, ImageDraw.Draw(base)
    lm = _lmarks(read)
    heights = read.get("heights") or {}
    hy = {h["name"]: (h["at"][1] if isinstance(h["at"], list) else h["at"]) * s for h in fr.get("heights") or []
          if isinstance(h, dict) and h.get("name") in heights}
    _ruler(d, {k: v * s for k, (v, _) in lm.items()}, {k for k, (_, f) in lm.items() if f != "seen"}, heights, hy, 40,
           im.size[0] - RM - 40)
    used, lx = [], im.size[0] - RM + 8
    for w in fr.get("widths") or []:
        if not isinstance(w, dict):
            continue
        inf = str(w.get("body_from") or "seen") != "seen"
        meas = (fit.get(w.get("at")) or {}).get("measured") or {}
        for key in ("body", "garment"):
            pair = (meas.get(key) or {}).get("measured") or w.get(key)
            if not pair:
                continue
            P = [np.array(p) * s + [OX, 0] for p in pair]
            for q, m in zip((meas.get(key) or {}).get("marked") or [], (meas.get(key) or {}).get("moved_px") or []):
                if m >= 1:  # (the agent's mark, where the tool moved it to the picture's edge)
                    c = np.array(q) * s + ([OX, -GAP] if key == "garment" else [OX, 0])
                    d.ellipse([c[0] - 3, c[1] - 3, c[0] + 3, c[1] + 3], outline=GREY, width=1)
            if key == "body":
                _seg(d, *P, CYAN, 2, (8, 6) if inf else None)
            else:
                _seg(d, *[q + [0, -GAP] for q in P], YEL, 3, None if str(w.get("garment_from") or "seen") == "seen" else (8, 6))
                _label(d, P[1] + [6, -GAP], w["at"], lx, used)
    for k, v in hy.items():
        _line(d, [(OX, v), (lx - 6, v)], ORANGE, 2, None)
        _label(d, (lx - 6, v), k, lx, used, ORANGE)
    return im


def _model(read: dict, body, fit: dict, heights: dict) -> Image.Image:
    view = read["views"][read["fit_read"]["view"]].get("view", "front")
    ax = (1, 2) if view == "side" else (0, 2)
    im = Image.new("RGB", (600 + RM, H), (24, 25, 28))
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
    from .garment_fit_heights import section, standing
    lm = _lmarks(read)
    up = standing(lm)  # (torso + leg landmarks on the ruler; the arm's are drawn on the arm: its pose is the model's)
    ys = {k: H - 30 - (body.at(k, view)["z_mm"] / 1000) * s for k in up}
    straight = {k: h for k, h in heights.items() if not (h.get("along") or {}).get("bone")}
    hy = {k: H - 30 - (h["z_mm"] / 1000) * s for k, h in straight.items()}
    _ruler(d, ys, {k for k, (_, f) in lm.items() if f != "seen"}, straight, hy, 40, 560)
    lx = 600 + 8
    used = []
    for k in lm:  # (a limb's own landmarks: a grey tick across the limb)
        if k in up:
            continue
        m = body.at(k, view)
        if m.get("centre") is not None:
            c, u = np.array(m["centre"]), np.array(m["dir"])
            _seg(d, px(c - u * m["width_mm"] / 2000), px(c + u * m["width_mm"] / 2000), GREY, 2,
                 (6, 4) if lm[k][1] != "seen" else None)
            _label(d, px(c + u * m["width_mm"] / 2000) + [4, 0], k, lx, used, GREY)
    for k, h in heights.items():  # (an edge read along a limb: across the limb where it lands)
        if k in straight:
            continue
        m = section(body, h, view)[0]
        c, u = np.array(m["centre"]), np.array(m["dir"])
        a, b = px(c - u * m["width_mm"] / 1600), px(c + u * m["width_mm"] / 1600)
        _seg(d, a, b, ORANGE, 3, (8, 6) if h.get("extrapolated") else None)
        _label(d, b + [4, 0], k, lx, used, ORANGE)
    for k, e in fit.items():
        sec = e.get("section")  # (a width at a garment edge: the body's section at that edge's height)
        if sec:
            from .garment_fit_heights import section
            m = section(body, sec, view)[0]
        else:
            m = body.at(k, view)
        if m.get("centre") is None:
            continue
        c, u = np.array(m["centre"]), np.array(m["dir"])
        hb, hg = m["width_mm"] / 2000, m["width_mm"] * e["ratio"] / 2000
        _seg(d, px(c - u * hb), px(c + u * hb), CYAN, 2, (8, 6) if e["body"] != "seen" else None)
        _seg(d, px(c - u * hg) + [0, -GAP], px(c + u * hg) + [0, -GAP], YEL, 3, (8, 6) if e["garment"] != "seen" else None)
        _label(d, px(c + u * hg) + [6, -GAP], k, lx, used)
    for k, y in hy.items():
        _line(d, [(110, y), (lx - 6, y)], ORANGE, 2, (8, 6) if straight[k].get("extrapolated") else None)
        _label(d, (lx - 6, y), k, lx, used, ORANGE)
    return im


def card(model: str, garment: str, body, view: str = "front") -> str | None:
    """The model's own landmarks, drawn where the tool takes each (a limb's section across the limb, a torso level
    across the body), before any mark: the agent matches these points on the picture (t s0-3). Names only: where each
    is, in words, is the tool's text (garment_fit.FIND)."""
    from .garment_fit import LANDMARKS
    mesh = getattr(body, "mesh", None)
    if mesh is None:
        return None
    ax = (1, 2) if view == "side" else (0, 2)
    V, T = np.asarray(mesh[0], float), np.asarray(mesh[1])
    P = V[:, ax]
    z0, z1 = P[:, 1].min(), P[:, 1].max()
    s = (H - 60) / (z1 - z0)
    cx = (P[:, 0].min() + P[:, 0].max()) / 2
    im = Image.new("RGB", (600 + RM, H + 40), (24, 25, 28))
    d = ImageDraw.Draw(im)

    def px(q):
        return np.array([300 + (q[0] - cx) * s, H + 10 - (q[1] - z0) * s])
    Q = np.c_[300 + (P[:, 0] - cx) * s, H + 10 - (P[:, 1] - z0) * s]
    for t in T:
        d.polygon([tuple(Q[i]) for i in t], fill=(95, 95, 100))
    used = []
    for k in sorted(LANDMARKS, key=lambda k: -_z(body, k, view)):
        try:
            m = body.at(k, view)
        except Exception:  # (a landmark this body lacks: left off the card)
            continue
        y = H + 10 - m["z_mm"] / 1000 * s
        if m.get("centre") is not None:
            c, u = np.array(m["centre"]), np.array(m["dir"])
            a, b = px(c - u * m["width_mm"] / 2000), px(c + u * m["width_mm"] / 2000)
            _seg(d, a, b, CYAN, 3, None)
            anchor = b + [6, 0]
            if LANDMARKS[k][0]["square_to"] == "body":
                _line(d, [(40, y), (a[0] - 6, y)], GREY, 1, (4, 4))
        else:
            _line(d, [(40, y), (560, y)], GREY, 1, (2, 5))
            anchor = np.array([560.0, y])
        _label(d, anchor, k, 608, used, CYAN)
    d.text((8, 8), f"{model}: the model's landmarks, where the tool takes each (cyan); find the same points on the "
                   "picture (their words: the tool's text)", fill=WHITE, font=FONT_LEG)
    p = gr.look_dir(model, garment) / "step0_landmarks.png"
    im.save(p)
    return str(p)


def _z(body, k, view):
    try:
        return body.at(k, view)["z_mm"]
    except Exception:
        return -1.0


def draw(model: str, garment: str, read: dict, body) -> str:
    a, b = _photo(read, read["fit"]), _model(read, body, read["fit"], read.get("heights") or {})
    out = Image.new("RGB", (a.size[0] + b.size[0] + 20, H + 40), (24, 25, 28))
    out.paste(a, (0, 40))
    out.paste(b, (a.size[0] + 20, 40))
    ImageDraw.Draw(out).text((8, 8), f"{garment} step 0 fit: the picture's marks | the model with what they give. yellow "
                             "garment, cyan body, orange heights + their spans (left ruler); dashed = inferred, dotted = "
                             "floor / crown (unused); numbers: the text", fill=WHITE, font=FONT_LEG)
    p = gr.look_dir(model, garment) / "step0_fit.png"
    out.save(p)
    return str(p)
