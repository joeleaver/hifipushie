"""regbasis2.py <region> [k=8]: faces5 M2, the LOCAL residual layer r, one region at a time, from M3's prior.

ICT's 100 carried identity modes (1-sd population draws) minus what the IDENTITY makes of each under the M3 prior
(PRIOR, default out/m3_em_tau1.npz: the c block, MAP at that prior's ML face noise, similarity projected out over the
face) = the detail a global identity can't draw at a probable cost. Under the region's smooth window (faceext._window,
WINDOW m): PCA -> ordered local modes with ICT's variance (the first draft of r's prior: diag(var) per region).

Per mode: variance share; 1-sd rms / max mm; symmetric share (mirror; ICT's scan noise is not symmetric, real faces
mostly are); curvature change p99 / max at 2 sd (visible skin, 1/m; gate < 70); fold-free at 2.5 sd (faceext._turned,
test_faceslide's criteria); face-ID effect at -2 / +2 sd (perc.measure: 1 - cos, heads mean / tess, 3 views; caveat:
the 112 px embedding can't see sub-mm detail, so this UNDER-rates lids and lip borders). Modes are listed in variance
order and ranked by ID effect.
Writes out/regbasis2_<region>.npz / .txt and human_renders/f5_<NN>_r_<region>.png: FEATURE-CROP strips (region close-up
~0.1 mm/px, Tess, front and 3/4, -2 / 0 / +2 sd per mode).

regions: nose, upper_lid, lower_lid, lips, chin, brows."""
import os
import sys
from pathlib import Path

import numpy as np
import scipy.sparse as sp
from PIL import Image, ImageDraw

import perc
from hifipushie import faceext, faceslide, gnmloops, likeness

F = Path(os.environ.get("F", "/mnt/data/hifipushie/faces5"))
OUT = F / "out"
R = Path("/home/joe/dev/hifipushie/workspace/human_renders")
WINDOW = float(os.environ.get("WINDOW", "0.008"))
PRIOR = os.environ.get("PRIOR", str(OUT / "m3_em_tau1.npz"))
region = sys.argv[1]
K = int(sys.argv[2]) if len(sys.argv) > 2 else 8
g = perc.g
N = perc.N
EXT = perc.EXT
TPL = perc.TPL
HC = [i for i, x in enumerate(perc.ID_NAMES) if x.startswith("head")]
IB = perc.IB[HC]
NC = len(HC)
grp = perc.grp
EYES = np.asarray(g["template_joint_positions"], float)[2:4]   # GNM frame (x left, y up, z forward)
eye_y = EYES[:, 1].mean()


def region_mask(name):
    if name == "nose":
        return grp("nose_region")
    if name in ("upper_lid", "lower_lid"):
        orb = grp("left_orbital_region") | grp("right_orbital_region")
        up = TPL[:, 1] >= eye_y - 0.001
        m = orb & (up if name == "upper_lid" else ~up)
        if name == "lower_lid":
            m |= grp("left_infraorbital_region") | grp("right_infraorbital_region")
        return m
    if name == "lips":
        return grp("upper_lip_region") | grp("lower_lip_region")
    if name == "chin":
        return grp("chin_region")
    if name == "brows":
        return grp("left_brow_region") | grp("right_brow_region") | grp("middle_brow_region")
    raise SystemExit(f"unknown region {name}")


CROP = {"nose": 0.028, "upper_lid": 0.045, "lower_lid": 0.045, "lips": 0.03, "chin": 0.035, "brows": 0.05}

# --- the residual population ---------------------------------------------------------------------------------------
face = np.zeros(N, bool)
for r_ in g["groups"]:
    if r_.endswith("_region"):
        face |= grp(r_)
fi = np.flatnonzero(EXT & face)
z = np.load(PRIOR)
Sz = z["cov"][:NC, :NC]
sig = float(z["sig_face"]) if "sig_face" in z.files else 0.0005
Pp = TPL[fi] - TPL[fi].mean(0)
S = np.zeros((len(fi) * 3, 7))
S[:, :3] = np.tile(np.eye(3), (len(fi), 1))
S[0::3, 4], S[0::3, 5] = Pp[:, 2], -Pp[:, 1]
S[1::3, 3], S[1::3, 5] = -Pp[:, 2], Pp[:, 0]
S[2::3, 3], S[2::3, 4] = Pp[:, 1], -Pp[:, 0]
S[:, 6] = Pp.ravel()
Qs, _ = np.linalg.qr(S)
Bf = IB[:, fi].reshape(NC, -1)
Bp = Bf - (Bf @ Qs) @ Qs.T
M = np.load(OUT / "ict_modes.npz")["modes"].astype(float)
Y = np.stack([M[k][fi].ravel() for k in range(len(M))])
Yp = Y - (Y @ Qs) @ Qs.T
Hm = Bp @ Bp.T + sig ** 2 * np.linalg.inv(Sz)
C = np.linalg.solve(Hm, Bp @ Yp.T)                  # (170, 100): the identity's part of every mode
Rf = Yp - C.T @ Bp                                  # (100, 3 nf): the residual over the face (similarity removed)
Rall = np.zeros((len(M), N, 3))
Rall[:, fi] = Rf.reshape(len(M), len(fi), 3)
reg = region_mask(region) & EXT
w = faceext._window(reg, WINDOW)
Rw = (Rall * w[None, :, None]).reshape(len(M), -1)
rows = np.flatnonzero(np.repeat(w > 0, 3))
U, Sv, Vt = np.linalg.svd(Rw[:, rows], full_matrices=False)
var = Sv ** 2
basis = np.zeros((K, 3 * N))
basis[:, rows] = Vt[:K] * Sv[:K, None]
basis = basis.reshape(K, N, 3)
# conditioned as the extensions are (faceext): the field carried into the skin that isn't exterior (nostril walls,
# lids' backs), the lips' inner rolls moved whole, creases moved rigidly. Without it every nose mode turned quads over
# just inside the nostrils at 2.5 sd (the exterior-only residual stopped dead at the rim: faces4's nose-target fault)
COND = os.environ.get("COND", "1") == "1"
if COND:
    for k in range(K):
        d = faceext.fill_inside(gnmloops.ext(basis[k]))
        if region == "lips":
            d = faceext.hold_rolls(d)
        basis[k] = faceext.hold_creases(d)[:N]
tot_face = float(np.sum(Yp ** 2))
print(f"{region}: residual over the face {np.sum(Rf ** 2) / tot_face:.3f} of ICT's face variance (prior "
      f"{Path(PRIOR).name}, noise {sig * 1e3:.2f} mm); in this window {np.sum(Rw ** 2) / tot_face:.4f}", flush=True)

# --- measures ------------------------------------------------------------------------------------------------------
X = TPL
q = perc.Q
e = np.r_[q[:, [0, 1]], q[:, [1, 2]], q[:, [2, 3]], q[:, [3, 0]]]
A = sp.coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), (N, N)).tocsr()
A = ((A + A.T) > 0).astype(float)
deg = np.maximum(np.asarray(A.sum(1)).ravel(), 1)
L = sp.diags(1 / deg) @ A - sp.eye(N)
r_, c_ = A.nonzero()
l2 = np.zeros(N)
np.add.at(l2, r_, ((X[r_] - X[c_]) ** 2).sum(1))
l2 /= deg
fn = np.cross(X[q[:, 2]] - X[q[:, 0]], X[q[:, 3]] - X[q[:, 1]])
vn = np.zeros_like(X)
for k in range(4):
    np.add.at(vn, q[:, k], fn)
vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-15)
vis = EXT & (vn[:, 2] > 0.2)
mi = faceslide.template()["mirror"][:N]


def sym_share(d):
    dm = d[mi] * [-1.0, 1.0, 1.0]
    s = 0.5 * (d + dm)
    return float(np.sum(s ** 2) / max(np.sum(d ** 2), 1e-30))


heads = {h: perc.head(h) for h in ("mean", "tess")}
info = []
lines = []
for k in range(K):
    d = basis[k]
    m = np.linalg.norm(d, axis=1)
    kap = np.abs(np.einsum("ij,ij->i", L @ d, vn)) / np.maximum(l2, 1e-12)
    kap[~vis] = 0
    sel = vis & (w > 0)
    p99, kmax = 2 * float(np.percentile(kap[sel], 99)), 2 * float(kap.max())
    turned = faceext._turned(gnmloops.ext(2.5 * d)) + faceext._turned(gnmloops.ext(-2.5 * d))
    row = perc.measure(f"{region}_{k}", lambda c, d=d: perc.verts(c, D=2 * d), lambda c, d=d: perc.verts(c, D=-2 * d), heads)
    it = {"k": k, "share": float(var[k] / var.sum()), "max": float(m.max() * 1e3), "rms": float(np.sqrt((m[reg] ** 2).mean()) * 1e3),
          "sym": sym_share(d), "p99": p99, "kmax": kmax, "turned": int(turned), "id": float(row["id"]["sface"] or 0)}
    gate = "OK" if (p99 < 70 and turned == 0) else "FAIL(" + ",".join(
        x for x, b in (("curv", p99 >= 70), ("fold", turned > 0)) if b) + ")"
    it["gate"] = gate
    info.append(it)
    lines.append(f"mode {k}: var share {it['share']:.3f} | 1 sd max {it['max']:.2f} rms {it['rms']:.3f} mm | symmetric "
                 f"{it['sym']:.2f} | curv @2sd p99 {p99:.0f} max {kmax:.0f} /m | turned @2.5sd {turned} | ID +-2sd "
                 f"{it['id']:.4f} | {gate}")
    print(lines[-1], flush=True)
rank = sorted(info, key=lambda x: -x["id"])
lines.append("ranked by ID effect: " + ", ".join(f"{x['k']} ({x['id']:.3f})" for x in rank))
print(lines[-1])
# MakeHuman handles in the region's window: how much of each the K modes span
Qb, _ = np.linalg.qr(basis.reshape(K, -1)[:, rows].T)
grpname = {"nose": "nose", "lips": "mouth"}.get(region)
tab = faceext.table()
for kk, v in faceext.EXT.items():
    if grpname and v[0] == grpname and kk in tab:
        f = (np.asarray(tab[kk], float)[:N] * w[:, None]).ravel()[rows]
        lines.append(f"  handle {kk:22s}: the first {K} modes span {np.linalg.norm(Qb.T @ f) ** 2 / max(f @ f, 1e-30):.2f}")
        print(lines[-1], flush=True)
np.savez_compressed(OUT / f"regbasis2_{region}.npz", basis=basis.astype(np.float32), var=var, window=w.astype(np.float32),
                    info=np.array([str(x) for x in info]))
(OUT / f"regbasis2_{region}.txt").write_text("\n".join(lines))


# --- feature-crop strips -------------------------------------------------------------------------------------------
PX = 300


def crop(V, yaw, centre_gnm, half):
    Ww = perc.world(V)
    cen = perc.world(centre_gnm[None])[0]
    cam = {"r": [0.0, 0.0, 0.0], "t": [0.0, 0.0, 0.8], "f": PX / 2 * 0.8 / half, "size": [PX, PX],
           "centre": list(map(float, cen)), "yaw": yaw}
    mesh = {"V": Ww, "F": perc.F_SKIN, "eyes": [(Ww, f, col) for f, col in perc.EYE_PARTS], "L": perc.WLM @ Ww}
    im, _ = likeness.render(mesh, cam, (0, 0, PX, PX), px=PX, brows=(region == "brows"))
    return im


cen = (TPL[reg] * w[reg, None]).sum(0) / w[reg].sum()
half = CROP[region]
order = [x["k"] for x in rank]
ct = heads["tess"]
cols = [("front -2", 0.0, -2), ("front 0", 0.0, 0), ("front +2", 0.0, 2), ("3/4 -2", -35.0, -2), ("3/4 0", -35.0, 0),
        ("3/4 +2", -35.0, 2)]
sheet = Image.new("RGB", (150 + len(cols) * (PX + 2), 22 + len(order) * (PX + 2)), "white")
dr = ImageDraw.Draw(sheet)
for j, (lab, _, _) in enumerate(cols):
    dr.text((150 + j * (PX + 2) + 4, 4), lab, fill=(0, 0, 0))
for i, k in enumerate(order):
    it = info[k]
    dr.text((4, 22 + i * (PX + 2) + 8), f"{region} mode {k}\nvar {it['share']:.2f}\nrms {it['rms']:.2f} mm/sd\nID {it['id']:.3f}"
                                         f"\nsym {it['sym']:.2f}\ncurv {it['p99']:.0f}\n{it['gate']}", fill=(0, 0, 0))
    for j, (_, yaw, s) in enumerate(cols):
        im = crop(perc.verts(ct, D=s * basis[k]), yaw, cen, half)
        sheet.paste(im.convert("RGB"), (150 + j * (PX + 2), 22 + i * (PX + 2)))
NUM = {"nose": "10", "upper_lid": "11", "lower_lid": "12", "lips": "13", "chin": "14", "brows": "15"}[region]
p = R / f"f5_{NUM}_r_{region}.png"
sheet.save(p)
print("wrote", p)
