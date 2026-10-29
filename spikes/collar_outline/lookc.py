"""lookc.py <tag>: the collar alone, close: band (lilac) + collar (blue) on the body, the curves drawn as tubes
(neckline green, band top / collar seam red, collar outer edge orange). Front, 3/4, side, top; 640 px each."""
import sys, pickle
import numpy as np
from PIL import Image, ImageDraw
from hifipushie import cloth, resources
D = "/mnt/data/hifipushie/folds_ab/D/"; t = sys.argv[1]
d = pickle.load(open(f"{D}{t}.pkl", "rb")); X = np.asarray(d["A"], float); M = d["mesh"]; F = np.asarray(M["F"])
uv = M["uv"]; pc = M["piece"]; nm = M["names"]; iS, iC = nm.index("stand"), nm.index("collar")
def sub(piece):
    Fm = F[np.all(pc[F] == piece, axis=1)]; ids = np.unique(Fm); rm = -np.ones(len(X), int); rm[ids] = np.arange(len(ids))
    return X[ids], rm[Fm]
def tube(P, rad=0.0007, n=6):
    P = np.asarray(P); V, Fs = [], []
    for i in range(len(P)):
        t_ = P[min(i + 1, len(P) - 1)] - P[max(i - 1, 0)]; t_ /= np.linalg.norm(t_) + 1e-12
        a = np.cross(t_, [0, 0, 1.0]); a = a / (np.linalg.norm(a) + 1e-9) if np.linalg.norm(a) > 1e-6 else np.array([1.0, 0, 0]); b = np.cross(t_, a)
        for k in range(n): th = 2 * np.pi * k / n; V.append(P[i] + rad * (np.cos(th) * a + np.sin(th) * b))
    for i in range(len(P) - 1):
        for k in range(n):
            a0, a1, b0, b1 = i * n + k, i * n + (k + 1) % n, (i + 1) * n + k, (i + 1) * n + (k + 1) % n
            Fs += [[a0, b0, a1], [a1, b0, b1]]
    return np.array(V), np.array(Fs)
sew = M["sew"]
def seam(a, b):
    out = {}
    for x, y in sew:
        if pc[x] == a and pc[y] == b: out[x] = y
        elif pc[y] == a and pc[x] == b: out[y] = x
    return out
c2s = seam(iC, iS); s2b = {}
for n_ in ("back", "yoke", "front.L", "front.R"): s2b.update(seam(iS, nm.index(n_)))
order = lambda vs: np.array(sorted(vs, key=lambda v: uv[v, 0]))
C0 = X[order(s2b)]; C1 = X[order(c2s.values())]
E = F[np.all(pc[F] == iC, axis=1)]; ed = np.sort(np.r_[E[:, [0, 1]], E[:, [1, 2]], E[:, [2, 0]]], axis=1)
u_, c_ = np.unique(ed, axis=0, return_counts=True); bv = set(u_[c_ == 1].ravel()); ns = set(c2s)
C3 = X[order([v for v in bv if v not in ns])]
parts = [{"name": "body", "V": d["bodyV"], "F": d["bodyF"], "color": "#c4bcb4"}]
Vs, Fs = sub(iS); parts.append({"name": "stand", "V": Vs, "F": Fs, "color": "#c9b8e8"})
Vc, Fc = sub(iC); parts.append({"name": "collar", "V": Vc, "F": Fc, "color": "#a9c4e6"})
for nmc, C, col in ((() if "plain" in sys.argv[2:] else (("c0", C0, "#2a9d4b"), ("c1", C1, "#d62828"), ("c3", C3, "#f08c00")))):
    Vt, Ft = tube(C); parts.append({"name": nmc, "V": Vt, "F": Ft, "color": col})
box = [[-0.11, -0.16, 1.43], [0.11, 0.08, 1.6]]
views = (("front", [0, -1, 0.1]), ("q", [-0.6, -0.8, 0.15]), ("side", [-1, 0, 0.05]), ("top", [0, -0.45, 1]))
ims = []
with resources.heavy(f"lookc {t}", gb=3.0, gpu=True):
    for nmv, dv in views:
        p = cloth.render(parts, f"{D}{t}_c_{nmv}", views=[{"name": nmv, "dir": dv}], resolution=640, box=box)[0]
        ims.append((nmv, Image.open(p).convert("RGB")))
H = 520; sc = lambda im: im.resize((int(im.size[0] * H / im.size[1]), H))
W = sum(sc(a).size[0] for _, a in ims); sh = Image.new("RGB", (W, H + 22), "white"); x = 0; dr = ImageDraw.Draw(sh)
for nmv, a in ims:
    a = sc(a); sh.paste(a, (x, 22)); dr.text((x + 4, 5), f"{t} {nmv}: band lilac, collar blue; neckline green, seam red, outer edge orange", fill="black"); x += a.size[0]
suf = "_plain" if "plain" in sys.argv[2:] else ""; sh.save(f"{D}{t}_collar{suf}.png"); print(f"{D}{t}_collar{suf}.png")
