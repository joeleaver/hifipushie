"""lookline.py <tag>: render ONLY the outline chains on the body (front, 3/4, side, top)."""
import sys, pickle
import numpy as np
from PIL import Image, ImageDraw
from hifipushie import cloth, resources
D = "/mnt/data/hifipushie/folds_ab/D/"; t = sys.argv[1]
o = pickle.load(open(f"{D}{t}_outline.pkl", "rb"))
def tube(P, rad=0.0008, n=6):
    P = np.asarray(P); V, Fs = [], []
    for i in range(len(P)):
        t_ = P[min(i + 1, len(P) - 1)] - P[max(i - 1, 0)]; t_ = t_ / (np.linalg.norm(t_) + 1e-12)
        a = np.cross(t_, [0, 0, 1.0]); a = a / np.linalg.norm(a) if np.linalg.norm(a) > 1e-6 else np.array([1.0, 0, 0]); b = np.cross(t_, a)
        for k in range(n): th = 2 * np.pi * k / n; V.append(P[i] + rad * (np.cos(th) * a + np.sin(th) * b))
    for i in range(len(P) - 1):
        for k in range(n):
            a0, a1, b0, b1 = i * n + k, i * n + (k + 1) % n, (i + 1) * n + k, (i + 1) * n + (k + 1) % n
            Fs += [[a0, b0, a1], [a1, b0, b1]]
    return np.array(V), np.array(Fs)
cols = {"C0": "#2a9d4b", "band_top": "#d62828", "roll": "#7b2cbf", "outer": "#f08c00", "endL": "#f08c00", "endR": "#f08c00", "neckline": "#2a9d4b"}
parts = [{"name": "body", "V": o["bodyV"], "F": o["bodyF"], "color": "#c4bcb4"}]
for k, P in ([] if "neckline" in o["chains"] else [("C0", o["C0"])]) + list(o["chains"].items()):
    V, F = tube(P); parts.append({"name": k, "V": V, "F": F, "color": cols[k]})
for i, (a, b) in enumerate(o["cross"]):
    V, F = tube(np.linspace(a, b, 8), rad=0.0005); parts.append({"name": f"x{i}", "V": V, "F": F, "color": "#1d3557"})
box = [[-0.11, -0.16, 1.43], [0.11, 0.08, 1.6]]
views = (("front", [0, -1, 0.1]), ("q", [-0.6, -0.8, 0.15]), ("side", [-1, 0, 0.05]), ("top", [0, -0.45, 1]))
ims = []
with resources.heavy(f"lookline {t}", gb=3.0, gpu=True):
    for nmv, dv in views:
        p = cloth.render(parts, f"{D}{t}_l_{nmv}", views=[{"name": nmv, "dir": dv}], resolution=640, box=box)[0]
        ims.append((nmv, Image.open(p).convert("RGB")))
H = 520; sc = lambda im: im.resize((int(im.size[0] * H / im.size[1]), H))
W = sum(sc(a).size[0] for _, a in ims); sh = Image.new("RGB", (W, H + 22), "white"); x = 0; dr = ImageDraw.Draw(sh)
for nmv, a in ims:
    a = sc(a); sh.paste(a, (x, 22)); dr.text((x + 4, 5), f"{t} {nmv}: neckline green, band top red, roll purple, collar edge orange, cross lines navy", fill="black"); x += a.size[0]
sh.save(f"{D}{t}_outline.png"); print(f"{D}{t}_outline.png")
