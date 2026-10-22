"""angles.py <tag>: front-view landmarks + angles on our model (marker cubes rendered at 3D landmarks, found in the image)
next to Joe's photo and the concept trace (landmarks marked by eye; drawn, so they can be checked). Writes
<tag>_angles.png and prints the table."""
import sys, pickle, json
import numpy as np
from PIL import Image, ImageDraw
from hifipushie import cloth, resources
D = "/mnt/data/hifipushie/shirt_spike/"; t = sys.argv[1]; A_OFF = float(sys.argv[2]) if len(sys.argv) > 2 else 0.006
d = pickle.load(open(f"{D}{t}.pkl", "rb")); X = np.asarray(d["A"], float); M = d["mesh"]; P = M["points"]
pid = np.asarray(M["piece"]); nm = list(M["names"]); uv = np.asarray(M["uv"]); F = np.asarray(M["F"])
hps = np.asarray(d["at"]["hps.L"]).reshape(-1)[-3:]
# --- 3D landmarks (wearer's right = image left = -x)
L = {}
L["tipL"], L["tipR"] = X[P["collar:leftTopEdge"]], X[P["collar:rightTopEdge"]]
if L["tipL"][0] > L["tipR"][0]: L["tipL"], L["tipR"] = L["tipR"], L["tipL"]
cL, cR = X[P["collar:leftBottomEdge"]], X[P["collar:rightBottomEdge"]]
L["cornerL"], L["cornerR"] = (cL, cR) if cL[0] < cR[0] else (cR, cL)
# the leaf's outer edge where it turns round the side of the neck: the collar's outer-edge vertex at +-85 deg from CB
ctr = X[pid == nm.index("stand")][:, :2].mean(0)
from collections import Counter
k_ = nm.index("collar"); cnt = Counter(map(tuple, np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1).tolist()))
sw = set(np.asarray(M["sew"]).ravel().tolist())
outer = np.array(sorted({v for (a, b), c in cnt.items() if c == 1 and pid[a] == k_ and pid[b] == k_ for v in (a, b) if v not in sw}))
ang = np.degrees(np.arctan2(X[outer, 0] - ctr[0], X[outer, 1] - ctr[1]))
L["outerL"] = X[outer[np.argmin(np.abs(ang + 85))]]; L["outerR"] = X[outer[np.argmin(np.abs(ang - 85))]]
# the V's bottom: lowest height where the fronts' edges are parted (openm.py's read), x between the edges there
eL = (pid == nm.index("front.L")) & (uv[:, 0] < uv[P["front.L:placketTopFold1"], 0] + 0.003)
eR = (pid == nm.index("front.R")) & (uv[:, 0] > uv[P["front.R:placketTopOut"], 0] - 0.003)
top = max(X[P["front.L:cfNeck"], 2], X[P["front.R:cfNeck"], 2]); vb = None
for z in np.arange(top, hps[2] - 0.25, -0.003):
    a = X[eL & (np.abs(X[:, 2] - z) < 0.003)]; b = X[eR & (np.abs(X[:, 2] - z) < 0.003)]
    if not len(a) or not len(b): continue
    if a[:, 0].min() - b[:, 0].max() > 0.002: vb = (z, 0.5 * (a[:, 0].min() + b[:, 0].max()), min(a[:, 1].min(), b[:, 1].min()))
    else: break
L["V"] = np.array([vb[1], vb[2], vb[0]])
# --- render front with marker cubes
def cube(c, h=0.0035):
    o = np.array([[x, y, z] for x in (-h, h) for y in (-h, h) for z in (-h, h)]) + c
    f = [[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1], [2, 3, 7], [2, 7, 6], [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]]
    return o, np.array(f)
cols = {"tipL": "#ff0000", "tipR": "#ff0000", "cornerL": "#00c000", "cornerR": "#00c000", "outerL": "#0000ff", "outerR": "#0000ff", "V": "#ff00ff"}
objs = [{"name": "body", "V": d["bodyV"], "F": d["bodyF"], "color": "#c4bcb4"}, {"name": "shirt", "V": X, "F": F, "color": "#c9ccd2", "thickness": 0.0004, "offset": 0.0}]
for k, c in L.items():
    V_, F_ = cube(c + np.r_[0, -A_OFF, 0]); objs.append({"name": "m_" + k, "V": V_, "F": F_, "color": cols[k]})
box = [[-0.19, -0.25, 1.33], [0.19, 0.1, 1.62]]
with resources.heavy(f"angles {t}", gb=4.0, gpu=True):
    pth = cloth.render(objs, f"{D}{t}_ang", views=[{"name": "front", "dir": [0, -1, 0]}], resolution=700, box=box)[0]
im = Image.open(pth).convert("RGB")
# landmarks projected straight from 3D (orthographic front view): calibrate the image <- (x, z) map from the two
# marker colours that are always visible (red tips, magenta V), then project every landmark (hidden ones too)
A_ = np.asarray(im).astype(int)
def blob(rgb, side=None):
    m = (np.abs(A_ - np.array(rgb)).max(-1) < 70) & ((A_.max(-1) - A_.min(-1)) > 90); ys, xs = np.nonzero(m)
    if side is not None:
        s_ = xs < im.size[0] / 2 if side == "L" else xs >= im.size[0] / 2; xs, ys = xs[s_], ys[s_]
    return np.array([xs.mean(), ys.mean()])
qa, qb, qc = blob((255, 0, 0), "L"), blob((255, 0, 0), "R"), blob((255, 0, 255))
pa, pb, pc = L["tipL"][[0, 2]], L["tipR"][[0, 2]], L["V"][[0, 2]]
sx = (qb[0] - qa[0]) / (pb[0] - pa[0]); x0 = qa[0] - sx * pa[0]
sz = (qc[1] - 0.5 * (qa[1] + qb[1])) / (pc[1] - 0.5 * (pa[1] + pb[1])); z0 = qc[1] - sz * pc[1]
pix = {k: (float(x0 + sx * v[0]), float(z0 + sz * v[2])) for k, v in L.items()}
# --- references (pixels, marked by eye on 2x grids)
REF = {"photo": ({"tipL": (150, 245), "tipR": (367, 242), "cornerL": (190, 187), "cornerR": (340, 194), "outerL": (100, 100),
                  "outerR": (402, 105), "V": (260, 300)}, "/tmp/claude-1000/-home-joe-dev-hifipushie--claude-worktrees-modest-napier-7b031c/482a48dc-c5a4-432d-b9c3-343ebc9d7803/images/3.png"),
       "trace": ({"tipL": (72, 182), "tipR": (327, 165), "cornerL": (112, 102), "cornerR": (287, 105), "outerL": (68, 40),
                  "outerR": (322, 38), "V": (210, 183)}, "/mnt/data/hifipushie/collar_spike/joe_trace.png")}
def deg(v): return np.degrees(np.arctan2(v[0], v[1]))  # angle from straight DOWN (image y grows down), + toward image right
def reads(p):
    p = {k: np.array(v, float) for k, v in p.items()}
    out = {}
    for s, sg in (("L", -1), ("R", 1)):
        fe = p["tip" + s] - p["corner" + s]          # the leaf's front edge, corner -> tip
        oe = p["tip" + s] - p["outer" + s]           # the leaf's outer edge, side of the neck -> tip
        out[f"front edge {s} (deg out from down)"] = round(float(-sg * deg(fe)), 0)
        out[f"outer edge {s} (deg out from down)"] = round(float(-sg * deg(oe)), 0)
        a1, a2 = -fe, -oe
        out[f"tip angle {s}"] = round(float(np.degrees(np.arccos(a1 @ a2 / np.linalg.norm(a1) / np.linalg.norm(a2)))), 0)
    vl, vr = p["cornerL"] - p["V"], p["cornerR"] - p["V"]
    out["V angle"] = round(float(np.degrees(np.arccos(vl @ vr / np.linalg.norm(vl) / np.linalg.norm(vr)))), 0)
    neck = np.linalg.norm(p["outerR"] - p["outerL"])
    out["tips apart / neck"] = round(float(np.linalg.norm(p["tipR"] - p["tipL"]) / neck), 2)
    out["V depth below tips / neck"] = round(float((p["V"][1] - 0.5 * (p["tipL"][1] + p["tipR"][1])) / neck), 2)
    out["corners apart / neck"] = round(float(np.linalg.norm(p["cornerR"] - p["cornerL"]) / neck), 2)
    return out
rows = {"photo": reads(REF["photo"][0]), "trace": reads(REF["trace"][0]), t: reads(pix)}
print(json.dumps({k: v for k, v in rows.items()}, indent=0))
# --- sheet: each image with its landmarks and lines
def draw(img, p, lab, scale):
    img = img.convert("RGB"); W = int(img.size[0] * scale); img = img.resize((W, int(img.size[1] * scale))); dr = ImageDraw.Draw(img)
    q = {k: (v[0] * scale, v[1] * scale) for k, v in p.items()}
    for s in ("L", "R"):
        dr.line([q["corner" + s], q["tip" + s]], fill=(255, 220, 0), width=3); dr.line([q["outer" + s], q["tip" + s]], fill=(0, 220, 255), width=3)
        dr.line([q["V"], q["corner" + s]], fill=(255, 0, 255), width=2)
    for k, v in q.items(): dr.ellipse([v[0] - 5, v[1] - 5, v[0] + 5, v[1] + 5], outline=(255, 0, 0), width=2)
    r = rows[lab]; yy = 4
    for kk, vv in r.items(): dr.text((6, yy), f"{kk}: {vv}", fill=(255, 255, 0)); yy += 12
    return img
H = 420
ims = [draw(Image.open(REF["photo"][1]), REF["photo"][0], "photo", H / 365), draw(Image.open(REF["trace"][1]), REF["trace"][0], "trace", H / 368),
       draw(im, pix, t, H / im.size[1])]
sh = Image.new("RGB", (sum(i.size[0] for i in ims), H), "black"); x = 0
for i in ims: sh.paste(i, (x, 0)); x += i.size[0]
sh.save(f"{D}{t}_angles.png"); print(f"{D}{t}_angles.png")
