"""Collar spike, no sim: Simon's band + collar POSED, not simulated. Each flat piece goes onto the surface its own outline
makes (bsim.py's start: the band on the neck cylinder, the collar on its own cone, turned down outside the band), the
collar's sewn edge set on the band's top (a per-angle height shift: the band's top dips toward CF), and OPEN = each
front (past Simon's own hinge marks on the band, ~65 mm back from CF) turned as one stiff piece about the hinge:
`spread` (deg, about the band's hinge ruling: the ends part) and `drop` (deg, about the horizontal at the hinge: the
fronts roll back and down), ramped over `ramp` m of arc so the band bends there instead of creasing.
Args: json {tag, spread, drop, ramp, gap}."""
import sys, json, time
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw
OUT = Path("/mnt/data/hifipushie/collar_spike")
A = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
TAG = A.get("tag", "g1")
src = (OUT / "bsim.py").read_text().split("inp = OUT")[0]
g = {"__name__": "bsimcore", "A": {"gap": A.get("gap", 0.002)}}
sys.argv = [sys.argv[0], json.dumps({"gap": A.get("gap", 0.002)})]
exec(compile(src, "bsim.py", "exec"), g)
X = g["X"].copy(); REST, T, SEW, is_c, off = g["REST"], g["T"], g["SEW"], g["is_c"], g["off_c"]
SU, CU, SN, CN, R, top_e, neck_e = g["SU"], g["CU"], g["SN"], g["CN"], g["R"], g["top_e"], g["neck_e"]
def arc_from_cb(t):  # signed arc round the band from CB (+Y); + toward +X (the creature's left)
    return -np.angle(np.exp(1j * (t - np.pi / 2))) * R
# unwrapped (the two front ends meet at CF: the angle alone can't tell them apart): from each piece's own wrap angle
s = -(np.r_[g["th"], g["thc"]] - np.pi / 2) * R
# 1. the collar's sewn edge on the band's top: shift each collar column by (band top z - sewn edge z) at its arc
tz = X[top_e]; ts = arc_from_cb(np.arctan2(tz[:, 1], tz[:, 0])); o = np.argsort(ts)
sw = SEW[:, 0]; ss = s[sw]; o2 = np.argsort(ss)
dz = np.interp(ss[o2], ts[o], tz[o, 2]) + A.get("fold_gap", 0.002) - X[sw[o2], 2]
c = np.where(is_c)[0]
X[c, 2] += np.interp(s[c], ss[o2], dz)
# 2. open: each front turned about its hinge
hx = 0.5 * (np.linalg.norm(SU[SN["leftBottomHinge"]] - SU[SN["bottomMid"]]) + np.linalg.norm(SU[SN["rightBottomHinge"]] - SU[SN["bottomMid"]]))
sh = np.abs(arc_from_cb(np.arctan2(*X[[SN["leftBottomHinge"], SN["rightBottomHinge"]]][:, [1, 0]].T)))
SH = sh.mean()
def rot(axis, ang):
    axis = axis / np.linalg.norm(axis); K = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    return np.eye(3) + np.sin(ang) * K + (1 - np.cos(ang)) * K @ K
SPREAD, DROP, RAMP = np.radians(A.get("spread", 0.0)), np.radians(A.get("drop", 0.0)), A.get("ramp", 0.02)
Y = X.copy()
for side, hname_b, hname_t in ((1, "leftBottomHinge", "leftTopHinge"), (-1, "rightBottomHinge", "rightTopHinge")):
    pb, pt = X[SN[hname_b]], X[SN[hname_t]]
    if np.sign(s[SN[hname_b]]) != side:
        pb, pt = X[SN[{"leftBottomHinge": "rightBottomHinge", "rightBottomHinge": "leftBottomHinge"}[hname_b]]], \
                 X[SN[{"leftTopHinge": "rightTopHinge", "rightTopHinge": "leftTopHinge"}[hname_t]]]
    ruling = pt - pb; radial = np.r_[pb[:2], 0] / np.linalg.norm(pb[:2])
    tang = np.cross(ruling / np.linalg.norm(ruling), radial)  # along the band, round the neck
    m = (np.sign(s) == side)
    end = X[np.where(m)[0][np.argmax(np.abs(s[m]))]]
    # spread: the end swings OUT (away from the neck axis); drop: the end goes DOWN. Signs picked by testing both.
    sp = max((1, -1), key=lambda q: np.linalg.norm((pb + rot(ruling, q * 0.3) @ (end - pb))[:2]))
    dp = min((1, -1), key=lambda q: (pb + rot(radial, q * 0.3) @ (end - pb))[2])
    mk_rot = lambda ww: rot(radial, dp * DROP * ww) @ rot(ruling, sp * SPREAD * ww)
    w = np.clip((np.abs(s[m]) - (SH - RAMP / 2)) / RAMP, 0, 1)
    for k, i in enumerate(np.where(m)[0]):
        if w[k] == 0: continue
        # spread about the ruling (outward: the end swings away from the body's CF), then drop about the radial axis
        Y[i] = pb + rots[k] @ (X[i] - pb) if False else pb + mk_rot(w[k]) @ (X[i] - pb)
X = Y
# measures
E = g["edges"](T); L0 = np.linalg.norm(REST[E[:, 0]] - REST[E[:, 1]], axis=1)
ee = np.abs(np.linalg.norm(X[E[:, 1]] - X[E[:, 0]], axis=1) / L0 - 1); ec = is_c[E[:, 0]]
gap = np.linalg.norm(X[SEW[:, 0]] - X[SEW[:, 1]], axis=1)
ne = X[neck_e]; side_i = np.argmin(np.abs(ne[:, 1])); hps = ne[np.abs(ne[:, 1]) < 0.01, 2].max()
pts = X[[off + CN["leftTopEdge"], off + CN["rightTopEdge"]]]
v = X[[SN["leftBottomCf"], SN["rightBottomCf"]]]
rr = np.linalg.norm(X[:, :2], axis=1)
inside = (rr < g["RN"] - 0.0005) & (X[:, 2] > g["ZB"])
meas = {"strain_p99_band_%": round(np.percentile(ee[~ec], 99) * 100, 1), "strain_p99_collar_%": round(np.percentile(ee[ec], 99) * 100, 1),
        "seam_gap_p99_mm": round(np.percentile(gap, 99) * 1000, 1),
        "points_apart_mm (147)": round(np.linalg.norm(pts[0] - pts[1]) * 1000), "points_below_HPS_mm (50-61)": (hps - pts[:, 2]).round(3) * 1000,
        "V_below_HPS_mm (~60)": round((hps - v[:, 2].min()) * 1000), "band_ends_apart_mm": round(np.linalg.norm(v[0] - v[1]) * 1000),
        "verts_inside_neck": int(inside.sum())}
print(json.dumps({k: (v_.tolist() if hasattr(v_, "tolist") else v_) for k, v_ in meas.items()}))
BV, BF = g["BV"], g["BF"]
V = np.r_[BV, X]; F = np.r_[BF, T + len(BV)]
col = np.r_[np.tile([.8, .72, .66, 1], (len(BV), 1)), np.where(is_c[:, None], [[.95, .62, .25, 1]], [[.35, .55, .85, 1]])]
np.savez(OUT / f"{TAG}.npz", verts=V.astype(np.float32), faces=F.astype(np.int32), part_colors=col.astype(np.float32))
from hifipushie import render
fr_ = render.view_frames(V[V[:, 2] > -0.07], ["front", "three_quarter", "side"], focus=[0, 0, 0.0], zoom=1.1)
ims = render.render_views(OUT / f"{TAG}.npz", fr_, 420, "clay_studio.exr", cavity=False)
sh_ = Image.new("RGB", (1260, 460), "white")
for i, im in enumerate(ims): sh_.paste(im, (420 * i, 40))
ImageDraw.Draw(sh_).text((8, 8), f"{TAG}: Simon's band + collar POSED (no sim) {json.dumps({k: v_ for k, v_ in A.items() if k != 'tag'})}", fill="black")
sh_.save(OUT / f"{TAG}.png"); print("saved", OUT / f"{TAG}.png")
