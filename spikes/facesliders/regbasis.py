"""regbasis.py <region> [k]: M2 groundwork (faces4): a REGIONAL local basis from data. ICT's 100 identity modes carried
onto GNM (ictreg.py) minus what GNM's identity makes of each (MAP over the face, noise NOISE), under the region's smooth
window (faceext._window, WINDOW m), then PCA: ordered local modes with ICT's variance. Reports per mode: variance share,
rms / max mm at 1 sd, curvature change p99 / max (1/m, visible skin), the perceptual effect at +-2 sd (perc.py), and how
much of each MakeHuman handle of the region (faceext.EXT) the first k modes span. Writes out/regbasis_<region>.npz and
human_renders/f4_11_regbasis_<region>.png (modes at -2 / +2 sd on Tess's and the mean head, front and 3/4).

regions: nose, eyes (both orbits + infraorbital), lips (upper + lower lip), chin, brows."""
import os
import sys

import numpy as np
import scipy.sparse as sp

sys.path.insert(0, os.path.dirname(__file__))
import ictreg  # noqa: E402
import perc  # noqa: E402
from hifipushie import faceext  # noqa: E402

REG = {"nose": ["nose_region"], "eyes": ["left_orbital_region", "right_orbital_region", "left_infraorbital_region",
                                          "right_infraorbital_region"],
       "lips": ["upper_lip_region", "lower_lip_region"], "chin": ["chin_region"],
       "brows": ["left_brow_region", "right_brow_region", "middle_brow_region"]}
NOISE = float(os.environ.get("NOISE", "0.0003"))
WINDOW = float(os.environ.get("WINDOW", "0.008"))
region = sys.argv[1]
K = int(sys.argv[2]) if len(sys.argv) > 2 else 8
g = perc.g
n = perc.N
ext = perc.EXT
names = perc.ID_NAMES
hc = [i for i, x in enumerate(names) if x.startswith("head")]
IB = perc.IB[hc]
face = np.zeros(n, bool)
for r in g["groups"]:
    if r.endswith("_region"):
        face |= np.asarray(g["groups"][r], float) > 0.5
sk = np.flatnonzero(ext & face)
Bf = IB[:, sk].reshape(len(hc), -1)
G = Bf @ Bf.T + NOISE ** 2 * np.eye(len(hc))
M = np.load(ictreg.OUT / "ict_modes.npz")["modes"].astype(float)
reg = np.zeros(n, bool)
for r in REG[region]:
    reg |= np.asarray(g["groups"][r], float) > 0.5
reg &= ext
w = faceext._window(reg, WINDOW)
R = []
for k in range(len(M)):
    y = M[k][sk].ravel()
    c = np.linalg.solve(G, Bf @ y)
    res = M[k] - np.tensordot(c, IB, 1)
    R.append((res * w[:, None]).ravel())
R = np.array(R)                                   # (100, 3n): ICT's residual population (each row a 1-sd draw)
rows = np.flatnonzero(np.repeat(w > 0, 3))
U, S, Vt = np.linalg.svd(R[:, rows], full_matrices=False)
var = S ** 2                                      # variance along each mode (ICT's sd units: rows are N(0,1) draws)
basis = np.zeros((K, 3 * n))
basis[:, rows] = Vt[:K] * S[:K, None]             # mode k at 1 sd (m)
basis = basis.reshape(K, n, 3)
# mirror-symmetrise? (report the asymmetry instead: ICT's modes are not exactly symmetric)
mi_tree = None
# curvature (as ncurv.py, on GNM's raw quads)
X = perc.TPL
q = perc.Q
e = np.r_[q[:, [0, 1]], q[:, [1, 2]], q[:, [2, 3]], q[:, [3, 0]]]
A = sp.coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), (n, n)).tocsr()
A = ((A + A.T) > 0).astype(float)
deg = np.maximum(np.asarray(A.sum(1)).ravel(), 1)
L = sp.diags(1 / deg) @ A - sp.eye(n)
r_, c_ = A.nonzero()
l2 = np.zeros(n)
np.add.at(l2, r_, ((X[r_] - X[c_]) ** 2).sum(1))
l2 /= deg
fn = np.cross(X[q[:, 2]] - X[q[:, 0]], X[q[:, 3]] - X[q[:, 1]])
vn = np.zeros_like(X)
for k in range(4):
    np.add.at(vn, q[:, k], fn)
vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-15)
vis = ext & (vn[:, 2] > 0.2)
heads = {h: perc.head(h) for h in ("mean", "tess")}
lines = [f"== {region}: ICT residual (after GNM's MAP) under a {WINDOW*1e3:.0f} mm window; total residual rms over the "
         f"region {np.sqrt((R[:, rows] ** 2).sum() / len(R) / max(reg.sum(), 1)) * 1e3:.3f} mm per sd-draw"]
for k in range(K):
    d = basis[k]
    m = np.linalg.norm(d, axis=1)
    kap = np.abs(np.einsum("ij,ij->i", L @ d, vn)) / np.maximum(l2, 1e-12)
    kap[~vis] = 0
    row = perc.measure(f"{region}_{k}", lambda c, d=d: perc.verts(c, D=2 * d), lambda c, d=d: perc.verts(c, D=-2 * d), heads)
    lines.append(f"mode {k}: variance share {var[k] / var.sum():.3f} | 1 sd: max {m.max()*1e3:.2f} rms {np.sqrt((m[reg]**2).mean())*1e3:.3f} mm | "
                 f"curv @2sd p99 {2*np.percentile(kap[vis & (w > 0)], 99):.0f} max {2*kap.max():.0f} | ID +-2sd sface {row['id']['sface']:.4f}")
    print(lines[-1], flush=True)
# MakeHuman handles of the region: share each one's field (over the window) the first K modes span
grp = {"nose": "nose", "lips": "mouth"}.get(region)
if grp:
    Q_, _ = np.linalg.qr(basis.reshape(K, -1)[:, rows].T)
    for kk, v in faceext.EXT.items():
        if v[0] != grp or kk not in faceext.table():
            continue
        f = (np.asarray(faceext.table()[kk], float)[:n] * w[:, None]).ravel()[rows]
        lines.append(f"  handle {kk:22s}: the first {K} modes span {np.linalg.norm(Q_.T @ f) ** 2 / max(f @ f, 1e-30):.2f} of it")
        print(lines[-1], flush=True)
out = ictreg.OUT
np.savez(out / f"regbasis_{region}.npz", basis=basis.astype(np.float32), var=var, window=w)
(out / f"regbasis_{region}.txt").write_text("\n".join(lines))
# sheet: modes at -2 / +2 sd, front and 3/4, mean head and Tess
from PIL import Image, ImageDraw  # noqa: E402
PX = perc.PX
sheet = Image.new("RGB", (70 + 8 * (PX + 2), 20 + K * (PX + 2)), "white")
dr = ImageDraw.Draw(sheet)
for j, lab in enumerate(["mean -2", "mean +2", "mean -2 3/4", "mean +2 3/4", "tess -2", "tess +2", "tess -2 3/4", "tess +2 3/4"]):
    dr.text((70 + j * (PX + 2) + 4, 4), lab, fill=(0, 0, 0))
for k in range(K):
    d = basis[k]
    tiles = []
    for h in ("mean", "tess"):
        for yaw in (0.0, -35.0):
            tiles += [perc.render(perc.verts(heads[h], D=-2 * d), yaw), perc.render(perc.verts(heads[h], D=2 * d), yaw)]
    dr.text((4, 20 + k * (PX + 2) + PX // 2), f"{region} {k}", fill=(0, 0, 0))
    for j, im in enumerate(tiles):
        sheet.paste(im, (70 + j * (PX + 2), 20 + k * (PX + 2)))
p = f"/home/joe/dev/hifipushie/workspace/human_renders/f4_11_regbasis_{region}.png"
sheet.save(p)
print("wrote", p)
