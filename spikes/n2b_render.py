"""N2b renders: the chains ALONE (links as tubes, coloured by piece) on the body, 4 sides, beside the reference.
  capped uv run python spikes/n2b_render.py <run dir> <loaded.pkl> <reference.png> [X.npy] [quick]
quick: a PIL line drawing (no GPU) for a fast look; else Blender tubes via cloth.render."""
import pickle
import sys

import numpy as np
from PIL import Image, ImageDraw

run, src, ref = sys.argv[1:4]
xn = sys.argv[4] if len(sys.argv) > 4 else "X.npy"
quick = "quick" in sys.argv[5:]
d = pickle.load(open(src, "rb"))
body = d["body"]
c = pickle.load(open(f"{run}/cnet.pkl", "rb"))["cnet"]
X = np.load(f"{run}/{xn}")
tag = xn.split(".")[0]
PAL = ["#d62728", "#1f77b4", "#2ca02c", "#9467bd", "#ff7f0e", "#8c564b", "#e377c2", "#17becf", "#bcbd22", "#7f7f7f"]
base = sorted({n[:-2] if n[-2:] in (".L", ".R") else n for n in c.names})
col = {n: PAL[base.index(n[:-2] if n[-2:] in (".L", ".R") else n) % len(PAL)] for n in c.names}
segs = {}
for (a, b), p in zip(c.chain_v, c.chain_piece):
    segs.setdefault(c.names[p], []).append((a, b))
VIEWS = [("front", [0, -1, 0.05]), ("left", [1, 0, 0.05]), ("back", [0, 1, 0.05]), ("right", [-1, 0, 0.05])]
R = Image.open(ref).convert("RGB")
ims = []
if quick:
    S = 900
    for nm, dv in VIEWS:
        dv = np.array(dv, float) / np.linalg.norm(dv)
        right = np.cross(dv, [0, 0, 1.0])
        right /= np.linalg.norm(right)
        up = np.cross(right, dv)
        allp = np.r_[X, body.V]
        lo = np.array([(allp @ right).min(), (allp @ up).min()])
        sc = (S - 40) / max(np.ptp(allp @ right), np.ptp(allp @ up))
        pr = lambda P: np.c_[(P @ right - lo[0]) * sc + 20, S - ((P @ up - lo[1]) * sc + 20)]
        im = Image.new("RGB", (S, S), "white")
        dr = ImageDraw.Draw(im)
        for q in pr(body.V[::3]):
            dr.point(tuple(q), fill="#cccccc")
        depth = X @ dv
        for p, ss in sorted(segs.items(), key=lambda t: -np.mean([depth[a] for a, _ in t[1]])):
            P = pr(X)
            for a, b in ss:
                dr.line([tuple(P[a]), tuple(P[b])], fill=col[p], width=2)
        dr.text((10, 10), nm, fill="black")
        ims.append(im)
else:
    from hifipushie import cloth, resources
    parts = [{"name": "body", "V": body.V, "F": body.T, "color": "#d8d2cc"}]
    ring = np.linspace(0, 2 * np.pi, 7)[:-1]
    for p, ss in segs.items():
        ss = np.array(ss)
        A, B = X[ss[:, 0]], X[ss[:, 1]]
        t = B - A
        t /= np.maximum(np.linalg.norm(t, axis=1), 1e-12)[:, None]
        u = np.cross(t, [0, 0, 1.0])
        u[np.linalg.norm(u, axis=1) < 1e-6] = [1, 0, 0]
        u /= np.linalg.norm(u, axis=1)[:, None]
        w = np.cross(t, u)
        r = 0.0025
        off = r * (np.cos(ring)[None, :, None] * u[:, None] + np.sin(ring)[None, :, None] * w[:, None])
        V = np.concatenate([A[:, None] + off, B[:, None] + off], 1).reshape(-1, 3)
        F = []
        for k in range(6):
            k2 = (k + 1) % 6
            F += [[k, k2, 6 + k2], [k, 6 + k2, 6 + k]]
        F = (np.array(F)[None] + 12 * np.arange(len(ss))[:, None, None]).reshape(-1, 3)
        parts.append({"name": p, "V": V, "F": F, "color": col[p]})
    lo, hi = X.min(0), X.max(0)
    box = [[lo[0] - 0.05, lo[1] - 0.05, lo[2] - 0.03], [hi[0] + 0.05, hi[1] + 0.05, float(body.V[:, 2].max()) + 0.02]]
    with resources.heavy("n2b chains render", gb=3.0, gpu=True, log=print):
        for nm, dv in VIEWS:
            p = cloth.render(parts, f"{run}/{tag}_{nm}", views=[{"name": nm, "dir": dv}], resolution=900, box=box)[0]
            ims.append(Image.open(p).convert("RGB"))
h = ims[0].height
r = R.resize((int(R.width * h / R.height), h))
sheet = Image.new("RGB", (r.width + sum(i.width for i in ims), h), "white")
sheet.paste(r, (0, 0))
x = r.width
for i in ims:
    sheet.paste(i, (x, 0))
    x += i.width
sheet.save(f"{run}/{tag}_{'quick' if quick else 'chains'}_sheet.png")
print(f"{run}/{tag}_{'quick' if quick else 'chains'}_sheet.png")
