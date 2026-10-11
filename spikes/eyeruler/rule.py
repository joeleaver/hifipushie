"""rule.py <tag>=<model> ...: the eye ruler on fitted-camera shots (out/s_<tag>.png; "photo" = the picture) against the
model's mesh truth; overlays out/o_<tag>.png, numbers out/rule.json. Env TRUTH=0: image reads only."""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

from hifipushie import blockin_brows as bb, eye_ruler as er, likeness, store

G = os.environ["G"] + "/out"
bx = json.load(open(G + "/box.json"))
K, box = bx["K"], bx["box"]
q = bb._inputs("gd_T12")
mm, cam = q["mm"], q["cam"]


def clean(m):
    return {k: (np.round(np.asarray(v, float), 3).tolist() if isinstance(v, (list, np.ndarray)) else
                (round(v, 3) if isinstance(v, float) else v)) for k, v in m.items() if not k.startswith("_") and k not in ("frame", "ring", "gap")}


def overlay(im, eyes, tru, path):
    """Both eyes' patches (x4 of the patch px would be huge: 0.05 mm -> shown at 0.05 mm / px), reads drawn."""
    A = np.asarray(im.convert("RGB"), float) / 255
    tiles = []
    for s in (0, 1):
        e = eyes[s]
        fr = {k: np.asarray(v) for k, v in e["frame"].items() if k != "k"}
        pat = er.patch(A, fr, e["frame"]["k"])[::-1]
        sel = (er.V[::-1] < 16) & (er.V[::-1] > -8)
        v_top = er.V[::-1][sel][0]
        t = Image.fromarray((pat[sel] * 255).astype(np.uint8))
        d = ImageDraw.Draw(t)
        X = lambda u: (u - er.U[0]) / er.STEP  # noqa: E731
        Y = lambda v: (v_top - v) / er.STEP  # noqa: E731
        g = e.get("_dbg")
        if g:
            for arr, col in ((g["T"], (255, 200, 0)), (g["B"], (255, 200, 0))):
                d.line([(X(u), Y(v)) for u, v in zip(g["uu"], arr)], fill=col, width=1)
            a, b = g["a"], g["b"]
            for arr in (g["up"], g["lo"]):
                pts = [(X(u), Y(v)) for u, v in zip(g["uu"][a:b + 1], arr[a:b + 1]) if np.isfinite(v)]
                d.line(pts, fill=(0, 255, 0), width=2)
            if g["cr"] is not None:
                d.line([(X(u), Y(v)) for u, v in zip(*g["cr"])], fill=(0, 255, 255), width=1)
            for (u, v) in g["br"] or []:
                d.ellipse([X(u) - 4, Y(v) - 4, X(u) + 4, Y(v) + 4], outline=(255, 0, 255))
        for key, col in (("inner", (255, 0, 0)), ("outer", (255, 0, 0))):
            u, v = e[key]
            d.line([(X(u), 0), (X(u), t.size[1])], fill=col, width=1)
            d.ellipse([X(u) - 5, Y(v) - 5, X(u) + 5, Y(v) + 5], outline=col, width=2)
        d.line([(X(e["sclera_in"]), Y(-3)), (X(e["sclera_in"]), Y(3))], fill=(255, 255, 255), width=1)
        rr = e["iris"] / 2 / er.STEP
        d.ellipse([X(0) - rr, Y(0) - rr, X(0) + rr, Y(0) + rr], outline=(255, 255, 0))
        d.line([(X(0) - 6, Y(0)), (X(0) + 6, Y(0))], fill=(255, 255, 0))
        if tru is not None:
            m = tru[s]
            # the truth sits in ITS frame: shift by the iris centres' difference
            dc = (np.asarray(m["c"]) - np.asarray(e["c"])) * mm
            du, dv = float(dc @ fr["ex"]), -float(dc @ fr["ey"])
            R = np.asarray(m["ring"])
            d.line([(X(u + du), Y(v + dv)) for u, v in R[np.argsort(np.arctan2(R[:, 1] - R[:, 1].mean(), R[:, 0] - R[:, 0].mean()))]] , fill=(80, 120, 255), width=1)
            for x, a_, b_ in zip(er.COLS, m["up"], m["lo"]):
                for v in (a_, b_):
                    if np.isfinite(v):
                        d.ellipse([X(x + du) - 3, Y(v + dv) - 3, X(x + du) + 3, Y(v + dv) + 3], fill=(80, 120, 255))
        tiles.append(t)
    W = Image.new("RGB", (tiles[0].size[0] * 2 + 6, tiles[0].size[1]), "white")
    W.paste(tiles[0], (0, 0))
    W.paste(tiles[1], (tiles[0].size[0] + 6, 0))
    W.save(path)


out = {}
try:
    out = json.load(open(G + "/rule.json"))
except Exception:  # noqa: BLE001
    pass
for a in sys.argv[1:]:
    tag, model = (a.split("=", 1) + [None])[:2]
    im = Image.open(f"{G}/s_{tag}.png").convert("RGB")
    if tag == "photo":
        eyes = er.read(q["img"], q["P"], mm, debug=True)
        im_o = q["img"]
    else:
        P = likeness.detect([im])[0]
        if P is None:
            print(tag, "NOT detected: the photo's points are used")
            P = (q["P"] - box[:2]) * K
        P = np.asarray(P, float)[:, :2] / K + box[:2]            # picture px
        eyes = er.read(im, P, mm, scale=K, origin=box[:2], debug=True)
        im_o = im
    tru = None
    if model and os.environ.get("TRUTH", "1") != "0":
        tru = er.model(store.load(model), cam)
    overlay(im_o, eyes, tru, f"{G}/o_{tag}.png")
    out[tag] = {"read": [clean(e) for e in eyes], "model": [clean(m) for m in tru] if tru else None}
    r = er.mean(eyes)
    line = f"{tag}: fissure {r['fissure']:.1f} tilt {r['tilt']:.1f} inner {np.round(r['inner'], 1)} outer {np.round(r['outer'], 1)} caruncle {r['caruncle']:.1f} iris {r['iris']:.1f} mrd {r['mrd1']:.2f}/{r['mrd2']:.2f} peak_u {r['peak_u']:.1f}\n   up {np.round(r['up'], 1)} lo {np.round(r['lo'], 1)}\n   crease {np.round(r['crease'], 1)} dark {r['crease_dark']:.3f} brow {np.round(r['brow'], 1)}"
    print(line)
    if tru:
        t = er.mean(tru)
        print(f"   MODEL fissure {t['fissure']:.1f} tilt {t['tilt']:.1f} inner {np.round(t['inner'], 1)} outer {np.round(t['outer'], 1)} caruncle {t['caruncle']:.1f} iris {t['iris']:.1f} mrd {t['mrd1']:.2f}/{t['mrd2']:.2f} peak_u {t['peak_u']:.1f}\n   up {np.round(t['up'], 1)} lo {np.round(t['lo'], 1)}\n   crease {np.round(t['crease'], 1)} platform {np.round(np.nanmean([m['platform'] for m in tru], 0), 1)} brow {np.round(t['brow'], 1)}")
json.dump(out, open(G + "/rule.json", "w"), indent=1)
