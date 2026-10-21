"""Collar spike, no sim: Simon's band + collar placed by AS-RIGID-AS-POSSIBLE against the flat pattern
(hifipushie.correctives.arap): hold a few handles, every other vertex takes the least-stretched shape.
Start = geo.py's closed pose (each piece on the surface its own outline makes). OPEN:
  band: its neck edge from CB to Simon's hinge marks held; each front END (the CF edge) turned out `spread` / down
        `drop` deg about the hinge (geo.py's move, on the end edge only); the rest of the band free.
  collar: its sewn edge held on the solved band's top (fold gap out); optional point handles `pt` = [apart, below HPS,
        standoff] (m); the rest free.
Args: json {tag, spread, drop, pt, iters}."""
import sys, json
import numpy as np
from pathlib import Path
OUT = Path("/mnt/data/hifipushie/collar_spike")
A0 = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
src = (OUT / "geo.py").read_text()
head, rest = src.split("# 2. open")
tail = "# measures" + rest.split("# measures")[1]
sys.argv = [sys.argv[0], json.dumps({"tag": A0.get("tag", "a1")})]
exec(compile(head, "geo.py", "exec"))          # X = the closed pose
A = A0; TAG = A.get("tag", "a1")
from hifipushie.correctives import arap
exec(compile("#" + rest.split("# measures")[0].split("Y = X.copy()")[0], "geo.py", "exec"))  # rot(), SH, SPREAD, DROP
X0 = X.copy(); nb = off
Xb = X0[:nb].copy(); REb = REST[:nb]; Fb = g["ST"]
fixed = np.zeros(nb, bool)
ends = []
for side in (1, -1):
    hb = [k for k in ("leftBottomHinge", "rightBottomHinge") if np.sign(s[SN[k]]) == side][0]
    ht = hb.replace("Bottom", "Top")
    pb, pt_ = X0[SN[hb]], X0[SN[ht]]
    ruling = pt_ - pb; radial = np.r_[pb[:2], 0] / np.linalg.norm(pb[:2])
    m = np.where(np.sign(s[:nb]) == side)[0]
    endv = m[np.abs(s[m]) > np.abs(s[m]).max() - A.get("end_w", 0.004)]  # the CF end edge (within 4 mm of the end)
    e0 = X0[m[np.argmax(np.abs(s[m]))]]
    sp = max((1, -1), key=lambda q: np.linalg.norm((pb + rot(ruling, q * 0.3) @ (e0 - pb))[:2]))
    dp = min((1, -1), key=lambda q: (pb + rot(radial, q * 0.3) @ (e0 - pb))[2])
    Rm = rot(radial, dp * DROP) @ rot(ruling, sp * SPREAD)
    Xb[endv] = pb + (Rm @ (X0[endv] - pb).T).T; fixed[endv] = True
    ends.append(endv)
back = neck_e[np.abs(s[neck_e]) <= SH]; fixed[back] = True
Yb = arap(REb, Fb, Xb, ~fixed, iters=A.get("iters", 30))
# collar: sewn edge on the solved band's top (+ fold gap along the band's outward normal ~ radial), points optional
Xc = X0[nb:].copy(); REc = REST[nb:]; Fc = g["CT"]
cfix = np.zeros(len(Xc), bool)
sw_l = SEW[:, 0] - nb; tb = SEW[:, 1]
# each sewn vertex at its own arc fraction along the solved band's top edge (no two snapped onto one band vertex)
P_top = Yb[top_e]; ft_ = g["ft"]; fs_ = g["fs"]
on_top = np.column_stack([np.interp(fs_, ft_, P_top[:, k]) for k in range(3)])
rad = np.c_[on_top[:, :2], 0 * on_top[:, :1]]; rad /= np.linalg.norm(rad, axis=1)[:, None]
Xc[sw_l] = on_top + A.get("fold_gap", 0.002) * rad + np.array([0, 0, 0.0015]); cfix[sw_l] = True
# carry the free collar along with its band at the start (each collar vertex moves like its nearest sewn vertex)
from scipy.spatial import cKDTree
d_, j_ = cKDTree(X0[nb:][sw_l]).query(X0[nb:]); Xc = np.where(cfix[:, None], Xc, X0[nb:] + (Xc[sw_l][j_] - X0[nb:][sw_l][j_]))
if A.get("pt"):
    apart, below, stand = A["pt"]
    hps_z = X0[neck_e][np.abs(X0[neck_e][:, 1]) < 0.01, 2].max()
    for nm, sx in (("leftTopEdge", None), ("rightTopEdge", None)):
        i = CN[nm]; sx = np.sign(Xc[i, 0]) or 1.0
        z = hps_z - below; zc = min(z, g["ZB"]); rc = g["RN"] + (g["RS"] - g["RN"]) * ((zc - g["ZB"]) / g["ZS"])
        y = -np.sqrt(max(rc ** 2 - (apart / 2) ** 2, 0)) - stand
        Xc[i] = [sx * apart / 2, y, z]; cfix[i] = True
Yc = arap(REc, Fc, Xc, ~cfix, iters=A.get("iters", 30))
# the fall lies ON the band it is turned over (pattern_form's FLAP_PULL rule: a turned flap on its base, one THICK out):
# collar vertices within the band's height of the sewn edge (in the flat) are laid on the band + THICK, then re-solved.
LAY, THICK = A.get("lay", 1), 0.0015
if LAY:
    Fb_n = Fb
    sew_flat = REc[sw_l, :2]; dflat, jj = cKDTree(sew_flat).query(REc[:, :2])
    bandH = A.get("lay_h", 0.030)  # the band's height (Simon: ~30 mm at CF, 39 mm at CB); the fall covers it
    over = (dflat < bandH) & ~cfix
    for _ in range(A.get("lay_rounds", 4)):
        # each laid vertex keeps its own angle and height; only its distance from the neck axis is set: the band's
        # radius there (its nearest band vertices, inverse-distance) + two thicknesses (snapping to the nearest band
        # vertex collapsed neighbours onto one point: 100-190 % strain)
        kb = cKDTree(Yb); dd, nb_ = kb.query(Yc[over], k=4)
        w_ = 1 / (dd + 1e-4); rb = (np.linalg.norm(Yb[nb_][..., :2], axis=2) * w_).sum(1) / w_.sum(1)
        p = Yc[over]; rp = np.linalg.norm(p[:, :2], axis=1)
        tgt = p.copy(); tgt[:, :2] *= ((rb + 2 * THICK) / rp)[:, None]
        Xc2 = Yc.copy(); Xc2[over] = tgt; fx = cfix | over
        Yc = arap(REc, Fc, Xc2, ~fx, iters=A.get("iters", 30))
    # final: free the laid vertices again under a short ARAP, so they settle where the lay left them

X = np.r_[Yb, Yc]
print(json.dumps(A))
exec(compile(tail, "geo.py", "exec"))
