"""The look of steps 0, 1, 2 (garment_plan.py): drawn OVER the reference picture, one image per view, with a legend.

Step 0: the colour samples (ringed, with the sampled swatch).
Step 1: pieces outlined, labelled in a margin; SEEN solid, OCCLUDED dashed, INFERRED dotted; omitted pieces grey; hidden
edges thin dashed; edge ends dotted; details as rings or outlines in the same line style.
Steps 0 and 1 carry a KEY of the line styles only (C344, Joe 2026-11-03: agents aren't meant to read text off a
picture): every name, value and source is in garment_plan's text answer.
Step 2: the judged rows' marks (yellow) with their targets; the closures' states, the bends and the pose in the legend.
Saved in the record's look directory (garment_record.look_dir) as step<id>_<key>_v<view>.png.
Shape first (C288: pictures are for shape, text is for numbers): labels on the picture are large names only, never
overlapping (a label that would overlap moves); targets and numbers are in garment_plan's text answer, which lists
every item the legend lists.
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw

from . import garment_record as gr
from .pattern_sheet import _font

FONT = _font(20)      # labels on the picture: names only
FONT_LEG = _font(17)  # the legend (every line also in garment_plan.text)

W = 900          # the picture's width in the look
LEG = 420        # the key's width (a key of line styles only; every name and value is in the text answer: C344)
PAL = [(80, 200, 255), (255, 120, 200), (120, 255, 140), (255, 170, 60), (190, 140, 255), (60, 230, 220),
       (255, 90, 90), (200, 230, 80), (150, 190, 255), (255, 210, 150)]
GREY, YEL, WHITE = (150, 150, 150), (255, 230, 40), (240, 240, 240)
DASH = {"seen": None, "occluded": (14, 8), "inferred": (3, 6)}
MARG = 250       # step 1: the labels' margin beside the picture (labels on the picture hid the frogging: t s1-1)
_PENDING: list = []


def _line(d, pts, col, width, dash, closed=False):
    pts = list(pts) + ([pts[0]] if closed and len(pts) > 2 else [])
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if dash is None:
            d.line([(x0, y0), (x1, y1)], fill=col, width=width)
            continue
        L = math.hypot(x1 - x0, y1 - y0) or 1.0
        on, off = dash
        t = 0.0
        while t < L:
            t1 = min(t + on, L)
            d.line([(x0 + (x1 - x0) * t / L, y0 + (y1 - y0) * t / L), (x0 + (x1 - x0) * t1 / L, y0 + (y1 - y0) * t1 / L)],
                   fill=col, width=width)
            t += on + off


_PLACED: list = []   # label boxes on the image being drawn (a label that would overlap one moves down)


def _label(d, xy, s, col):
    w = d.textlength(s, font=FONT)
    x = min(max(xy[0], 2), d.im.size[0] - w - 4)
    y0 = min(max(xy[1], 2), d.im.size[1] - 28)
    hit = lambda x_, y_: any(x_ < b[2] and b[0] < x_ + w and y_ < b[3] and b[1] < y_ + 26 for b in _PLACED)  # noqa: E731
    cands = [(x, min(max(y0 + k * dy, 2), d.im.size[1] - 28)) for k in range(14) for dy in (27, -27)]
    x, y = next((c for c in [(x, y0)] + cands if not hit(*c)), (x, y0))
    _PLACED.append((x - 3, y - 2, x + w + 3, y + 26))
    d.rectangle([x - 3, y - 2, x + w + 3, y + 25], fill=(0, 0, 0))
    d.text((x, y), s, fill=col, font=FONT)


def _mlabel(d, anchor, s, col):
    """A label for later: placed in the margin on its anchor's side of the picture by _place_labels."""
    _PENDING.append((tuple(anchor), s, col))


def _place_labels(d, h: int):
    """Each pending label in the margin on its anchor's side (left half -> left margin: no leader crosses the picture,
    t s1-6), at its anchor's height, moved clear of the labels already on that side, with a leader."""
    used = {"L": [], "R": []}
    for (u, v), s, col in sorted(_PENDING, key=lambda t: t[0][1]):
        side = "L" if u < W / 2 else "R"
        y0 = min(max(v - 12, 2), h - 26)
        y = y0
        for k in range(200):  # (y0, then 24 px further each way, alternating, until clear)
            y = y0 + 24 * ((k + 1) // 2) * (1 if k % 2 else -1)
            if 2 <= y <= h - 26 and all(abs(y - q) >= 24 for q in used[side]):
                break
        used[side].append(y)
        w = d.textlength(s, font=FONT)
        if side == "L":
            _line(d, [(u + MARG, v), (MARG - 6, y + 12)], col, 1, (3, 3))
            d.text((MARG - 10 - w, y), s, fill=col, font=FONT)
        else:
            _line(d, [(u + MARG, v), (MARG + W + 6, y + 12)], col, 1, (3, 3))
            d.text((MARG + W + 10, y), s, fill=col, font=FONT)


def _ring(d, u, v, r, col, dash):
    n = 24
    _line(d, [(u + r * math.cos(2 * math.pi * k / n), v + r * math.sin(2 * math.pi * k / n)) for k in range(n)], col, 3,
          dash, closed=True)


def _base(read: dict, i: int):
    im = Image.open(read["views"][i]["image"]).convert("RGB")
    s = W / im.size[0]
    im = im.resize((W, round(im.size[1] * s)))
    return Image.blend(im, Image.new("RGB", im.size, (0, 0, 0)), 0.25), s


def _sheet(im: Image.Image, legend: list, title: str) -> Image.Image:
    import textwrap
    lines = [(t if k == 0 else "      " + t, col) for s, col in legend
             for k, t in enumerate(textwrap.wrap(s, 54, subsequent_indent="") or [""])]
    h = max(im.size[1], 40 + 22 * len(lines))
    out = Image.new("RGB", (im.size[0] + LEG, h), (24, 25, 28))
    out.paste(im, (0, 0))
    d = ImageDraw.Draw(out)
    d.text((im.size[0] + 10, 6), title, fill=WHITE, font=FONT_LEG)
    for k, (s, col) in enumerate(lines):
        d.text((im.size[0] + 10, 34 + 22 * k), s, fill=col, font=FONT_LEG)
    return out


def _views_used(sid: str, plan: dict, read: dict) -> list:
    if sid == "0":
        return list(range(len(read["views"])))
    vs = set()
    for grp in ("pieces", "details"):
        for x in (plan.get(grp) or {}).values():
            if isinstance(x.get("where"), dict):
                vs.add(x["where"].get("view", 0))
    for r in (plan.get("rows") or []) + (plan.get("traces") or []):
        if r.get("at") or r.get("points"):
            vs.add(r.get("view", 0))
    return sorted(vs) or [0]


def draw(model: str, garment: str, sid: str, plan: dict, read: dict, parts: dict | None = None) -> list:
    key = gr.STEP[sid]["key"]
    paths = []
    for vi in _views_used(sid, plan, read):
        im, s = _base(read, vi)
        _PLACED.clear()
        _PENDING.clear()
        d = ImageDraw.Draw(im)
        fn = {"0": _read, "1": _parts, "2": _style}[sid]
        legend = fn(d, s, vi, plan, read, parts)
        if sid == "1":  # (margins both sides for the labels: C343, C348)
            pad = Image.new("RGB", (im.size[0] + 2 * MARG, im.size[1]), (24, 25, 28))
            pad.paste(im, (MARG, 0))
            im = pad
            _place_labels(ImageDraw.Draw(im), im.size[1])
        v = read["views"][vi]
        out = _sheet(im, legend, f"{garment} step {sid} ({key}) on view {vi} ({v['view']})")
        p = gr.look_dir(model, garment) / f"step{sid}_{key}_v{vi}.png"
        out.save(p)
        paths.append(str(p))
    return paths


def _read(d, s, vi, plan, read, parts):
    leg = [("ring = a colour sample", WHITE), ("square = the colour it sampled", WHITE), ("", WHITE),
           ("cloths, numbers, fit: the text answer", GREY)]
    for k, (n, c) in enumerate(plan["cloth"].items()):
        col = tuple(int(x) for x in c["colour"])
        cf = c.get("colour_from") or {}
        if cf.get("view", 0) == vi:
            for u, v in cf.get("at") or []:
                _ring(d, u * s, v * s, 12, YEL, None)
                d.rectangle([u * s + 14, v * s - 8, u * s + 30, v * s + 8], fill=col, outline=WHITE)
                _label(d, (u * s + 34, v * s - 12), n, YEL)
    return leg


def _style_of(x: dict, col):
    return (GREY if x.get("build") == "omit" else col), DASH.get(x.get("seen"))


def _parts(d, s, vi, plan, read, parts):
    leg = [("solid = seen", WHITE), ("dashed = occluded, dotted = inferred", WHITE),
           ("   (drawn only where given a place)", GREY), ("grey = left out (build omit)", GREY),
           ("thin dashed run = a hidden edge", WHITE), ("white dot = where one edge meets the next", WHITE), ("", WHITE),
           ("pieces with no place, names, edges, seams,", GREY), ("sources: the text answer", GREY)]
    for k, (n, x) in enumerate(plan["pieces"].items()):
        col, dash = _style_of(x, PAL[k % len(PAL)])
        w = x.get("where") or {}
        drawn = w.get("view", 0) == vi and w.get("outline")
        if drawn:
            P = [(u * s, v * s) for u, v in w["outline"]]
            hid = set()  # (segments of hidden edges: dashed thin, C344)
            for k_, sp in (x.get("edges") or {}).items() if isinstance(x.get("edges"), dict) else []:
                if k_ in (x.get("hidden") or []) and isinstance(sp, list) and len(sp) == 2:
                    hid |= {(sp[0] + j) % len(P) for j in range((sp[1] - sp[0]) % len(P))}
            for g in range(len(P)):
                a_, b_ = P[g], P[(g + 1) % len(P)]
                _line(d, [a_, b_], col, 1 if g in hid else 3, (6, 6) if g in hid else dash)
            for sp in (x.get("edges") or {}).values() if isinstance(x.get("edges"), dict) else []:
                if isinstance(sp, list) and sp and isinstance(sp[0], int) and 0 <= sp[0] < len(P):
                    u, v = P[sp[0]]  # (where one edge ends and the next begins)
                    d.ellipse([u - 5, v - 5, u + 5, v + 5], fill=WHITE, outline=col)
            cx, cy = sum(p[0] for p in P) / len(P), sum(p[1] for p in P) / len(P)
            _mlabel(d, (cx, cy), n, col)
    for k, (n, x) in enumerate((plan.get("details") or {}).items()):
        col, dash = _style_of(x, YEL)
        w = x.get("where") or {}
        if w.get("view", 0) == vi:
            for u, v in w.get("at") or []:
                _ring(d, u * s, v * s, 9, col, dash)
            for o in ([w["outline"]] if w.get("outline") else []) + (w.get("outlines") or []):
                _line(d, [(u * s, v * s) for u, v in o], col, 2, dash)
            pts = w.get("at") or w.get("outline") or (w.get("outlines") or [[]])[0]
            if pts:
                _mlabel(d, (pts[0][0] * s, pts[0][1] * s), n, col)
    return leg


def _tgt(t: dict) -> str:
    return str(t["is"]) if "is" in t else f"{t['value']} {t['unit']}" + (f" +-{t['tol']}" if t.get("tol") else "")


def _style(d, s, vi, plan, read, parts):
    leg = [(f"pose: {plan['pose']['name']}", WHITE)]
    leg += [(f"closure {c}: {x['state']}" + (f" ({x['detail']})" if x.get("detail") else ""), YEL)
            for c, x in plan["state"].items()]
    leg += [(f"bend {b.get('id', '')} on {b['on']}: {_tgt(b['target'])}", (120, 255, 140)) for b in plan.get("bends") or []]
    leg.append(("judged rows (yellow on the picture):", WHITE))
    for r in plan["rows"]:
        if r.get("at") and r.get("view", 0) == vi:
            P = [(u * s, v * s) for u, v in r["at"]]
            _line(d, P, YEL, 3, None)
            for u, v in P:
                _ring(d, u, v, 5, YEL, None)
            _label(d, (P[-1][0] + 8, P[-1][1] - 12), r["id"], YEL)  # (the target is the text's)
        leg.append((f"  {r['id']}: {_tgt(r['target'])}" + ("" if r.get("at") else " (not marked)"), YEL))
    CY, MAG = (60, 230, 255), (255, 80, 220)
    if plan.get("traces"):
        leg.append(("traced edges (cyan; corners ringed, body marks magenta):", CY))
    for t in plan.get("traces") or []:
        if t.get("view", 0) == vi:
            P = [(u * s, v * s) for u, v in t["points"]]
            _line(d, P, CY, 3, None)
            for k in t.get("corners") or []:
                _ring(d, *P[k], 9, CY, None)
            _label(d, (P[0][0] + 8, P[0][1] - 30), t["id"], CY)
        leg.append((f"  {t['id']}: {t['what']}" + ("" if t.get("view", 0) == vi else f" (on view {t.get('view', 0)})"), CY))
    for m in plan.get("body_marks") or []:
        if m.get("view", 0) == vi:
            for k, (u, v) in m["at"].items():
                _ring(d, u * s, v * s, 6, MAG, None)
                _label(d, (u * s + 8, v * s - 34), k, MAG)
    return leg
