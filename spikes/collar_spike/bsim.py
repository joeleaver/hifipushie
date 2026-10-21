"""Collar spike, Blender cloth: Simon's stand + collar (form_c0) start wrapped as in wrap.py (stand up the neck, the
collar turned down outside it), rest shape = the FLAT pattern pieces, settled by Blender's cloth sim: high bending
stiffness (interfaced), sewing springs collar sewn edge -> stand top, the stand's neck edge pinned on the neckline,
little gravity. Args: json {tag, open, grav, bend, frames, ...}."""
import sys, json, time, subprocess
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw
OUT = Path("/mnt/data/hifipushie/collar_spike")
A = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
TAG = A.get("tag", "b1")
import pickle
from scipy.spatial import Delaunay
pcs = pickle.load(open("/mnt/data/hifipushie/drape_band1/form_c0.pkl", "rb"))["pieces"]["pieces"]
H = A.get("h", 0.005)
def ring(name):
    p = pcs[name]; return np.asarray(p["P"], float), p["names"]
def resample(P, h):
    """the outline: every original point (no chords cut: the sewn lengths stay the pattern's), long segments split at
    ~h, points closer than 0.5 mm merged; returns points + old->new index map."""
    out, idx = [], {}
    for i, (a, b) in enumerate(zip(P, np.roll(P, -1, 0))):
        if out and np.linalg.norm(a - out[-1]) < 0.0005:
            idx[i] = len(out) - 1
        else:
            idx[i] = len(out); out.append(a)
        n = int(np.ceil(np.linalg.norm(b - a) / h))
        out += [a + (b - a) * k / n for k in range(1, n)]
    return np.array(out), idx
def inside(P, Q):
    x, y = Q[:, 0], Q[:, 1]; c = np.zeros(len(Q), bool)
    for a, b in zip(P, np.roll(P, -1, 0)):
        c ^= ((a[1] > y) != (b[1] > y)) & (x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1] + 1e-12) + a[0])
    return c
def mesh_flat(P0, names):
    P, idx = resample(P0, H)
    # drop near-duplicate outline points (short original segments)
    lo, hi = P.min(0), P.max(0)
    gy = np.arange(lo[1] + H / 2, hi[1], H * 0.866)
    G = np.array([[x + (j % 2) * H / 2, y] for j, y in enumerate(gy) for x in np.arange(lo[0], hi[0], H)])
    G = G[inside(P, G)]
    d = np.min(np.linalg.norm(G[:, None] - P[None], axis=2), 1); G = G[d > 0.6 * H]
    U = np.r_[P, G]; T = Delaunay(U).simplices; T = T[inside(P, U[T].mean(1))]
    e1 = U[T[:, 1]] - U[T[:, 0]]; e2 = U[T[:, 2]] - U[T[:, 0]]; ar = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]; T = T[np.abs(ar) > 1e-9]
    T[ar[np.abs(ar) > 1e-9] < 0] = T[ar[np.abs(ar) > 1e-9] < 0][:, ::-1]
    return U, T, len(P), {n: idx[i] for n, i in names.items()}
def arc(P, n, nm, a, b):
    i, j = nm[a], nm[b]
    f_ = [(i + k) % n for k in range((j - i) % n + 1)]; r_ = [(i - k) % n for k in range((i - j) % n + 1)]
    L = lambda ix: np.linalg.norm(np.diff(P[ix], axis=0), axis=1).sum()
    return np.array(f_ if L(f_) <= L(r_) else r_)
def alen(P, ix): return np.r_[0, np.cumsum(np.linalg.norm(np.diff(P[ix], axis=0), axis=1))]
def edges(T):
    E = np.r_[T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]]; E.sort(1); return np.unique(E, axis=0)
SP0, SN0 = ring("stand"); CP0, CN0 = ring("collar")
SU, ST, sn, SN = mesh_flat(SP0, SN0); CU, CT, cn, CN = mesh_flat(CP0, CN0)
neck_e = arc(SU, sn, SN, "leftBottomCf", "rightBottomCf"); top_e = arc(SU, sn, SN, "leftTopCf", "rightTopCf")
sewn_e = arc(CU, cn, CN, "leftBottomEdge", "rightBottomEdge")
Lneck = alen(SU, neck_e)[-1]; R = Lneck / (2 * np.pi); RN = R - 0.003; ZS, RS = -0.06, 0.20
off_c = len(SU); T = np.r_[ST, CT + off_c]; is_c = np.r_[np.zeros(len(SU), bool), np.ones(len(CU), bool)]
print(f"mesh {len(SU)}+{len(CU)} verts; stand neck {Lneck*1000:.0f} top {alen(SU, top_e)[-1]*1000:.0f} collar sewn {alen(CU, sewn_e)[-1]*1000:.0f} mm")
# start: each flat piece wrapped isometrically on a cylinder (x -> angle, y -> height); CB (x = 0) at +Y, CF at -Y
xc = 0.5 * (SU[:, 0].min() + SU[:, 0].max())
yb = np.interp(xc, *zip(*sorted(zip(SU[neck_e, 0], SU[neck_e, 1]))))  # the neck edge's height at CB
th = np.pi / 2 - (SU[:, 0] - xc) / R
XS = np.c_[R * np.cos(th), R * np.sin(th), SU[:, 1] - yb]
zt = np.interp(xc, *zip(*sorted(zip(SU[top_e, 0], SU[top_e, 1])))) - yb  # the stand's top at CB
# the collar: its sewn edge is a circular arc in the flat (centre c, radius rho), so the piece is an annular sector and
# wraps isometrically onto a CONE: the sewn edge round the stand's top (radius Rc), the outer edge (farther from c) turned
# down and out. No shape is invented: the cone is the one the flat piece itself makes.
Rc = R + A.get("gap", 0.004)
Q = CU[sewn_e]; cfit = np.linalg.lstsq(np.c_[2 * Q, np.ones(len(Q))], (Q ** 2).sum(1), rcond=None)[0]
cc = cfit[:2]; rho = np.sqrt(cfit[2] + cc @ cc)
rr = np.linalg.norm(CU - cc, axis=1); phi = np.arctan2(CU[:, 1] - cc[1], CU[:, 0] - cc[0])
phic = np.arctan2(-cc[1], -cc[0]) if False else np.pi / 2 * np.sign(-cc[1]) * -1  # direction from c to the piece's CB
phic = np.arctan2(np.mean(CU[:, 1]) - cc[1], np.mean(CU[:, 0]) - cc[0])
sb = Rc / rho; cb = np.sqrt(1 - sb ** 2)
thc = np.pi / 2 + (phi - phic) * rho / Rc * np.sign(cc[1] - np.mean(CU[:, 1])) * -1
out = 1.0 if rr[CN["leftTopEdge"]] > rho else -1.0
XC = np.c_[rr * sb * np.cos(thc), rr * sb * np.sin(thc), zt + A.get("fold_gap", 0.002) - out * (rr - rho) * cb]
print(f"collar cone: rho {rho*1000:.0f} mm, half-angle {np.degrees(np.arcsin(sb)):.1f} deg")
X = np.r_[XS, XC]
REST = np.c_[np.r_[SU, CU + [0.0, 0.25]], np.zeros(len(X))]
ft = alen(SU, top_e) / alen(SU, top_e)[-1]; fs = alen(CU, sewn_e) / alen(CU, sewn_e)[-1]
SEW = np.c_[sewn_e + off_c, [top_e[np.argmin(np.abs(ft - q))] for q in fs]]
PIN = neck_e
BENDW = np.where(is_c, A.get("w_collar", 1.0), A.get("w_stand", 1.0))
def rev(prof, n=128):
    t = np.linspace(0, 2*np.pi, n, endpoint=False)
    V = np.array([[rr*np.cos(a), rr*np.sin(a), z] for rr, z in prof for a in t]); F = []
    for i in range(len(prof)-1):
        for j in range(n):
            a, b = i*n+j, i*n+(j+1)%n; F += [[a, b, b+n], [a, b+n, a+n]]
    return V, np.array(F)
# body: neck cylinder + shoulder cone (wrap.py's profile)
ZB = XS[:, 2].min() - A.get("below", 0.003)  # the shoulder starts below the stand's lowest point (the neck seam)
prof = [(RS, ZB + ZS)] + [(RN + (RS - RN) * (1 - q), ZB + ZS * (1 - q)) for q in np.linspace(0.05, 1, 20)] \
       + [(RN, z) for z in np.linspace(ZB + 0.003, 0.12, 20)]
BV, BF = rev(prof)
inp = OUT / f"{TAG}_in.npz"; res = OUT / f"{TAG}_out.npz"
np.savez(inp, REST=REST, X=X, T=T, SEW=SEW, PIN=PIN, BENDW=BENDW, BV=BV, BF=BF)
t0 = time.time()
r = subprocess.run(["blender", "-b", "--factory-startup", "--python", str(OUT / "bl_cloth.py"), "--", str(inp), str(res),
                    json.dumps(A)], capture_output=True, text=True)
if "BLDONE" not in r.stdout:
    print(r.stdout[-3000:], r.stderr[-3000:]); sys.exit(1)
tsim = time.time() - t0
Y = np.load(res)["X"].astype(float)
E = edges(T); L0 = np.linalg.norm(REST[E[:, 0]] - REST[E[:, 1]], axis=1)
ee = np.abs(np.linalg.norm(Y[E[:, 1]] - Y[E[:, 0]], axis=1) / L0 - 1); ec = is_c[E[:, 0]]
sew_gap = np.linalg.norm(Y[SEW[:, 0]] - Y[SEW[:, 1]], axis=1)
# measures: collar points (left/rightTopEdge) relative to the neckline top-front, height below the stand top at CF
off = off_c
pts = Y[[off + CN["leftTopEdge"], off + CN["rightTopEdge"]]]
rb = np.linalg.norm(pts[:, :2], axis=1)
print(f"sim {tsim:.1f}s; strain p99 stand {np.percentile(ee[~ec],99)*100:.1f} % collar {np.percentile(ee[ec],99)*100:.1f} %; "
      f"sew gap p99 {np.percentile(sew_gap,99)*1000:.1f} mm")
print(f"points: apart {np.linalg.norm(pts[0]-pts[1])*1000:.0f} mm, z {pts[:,2].round(3)}, radius {rb.round(3)} (neck {RN:.3f})")
V = np.r_[BV, Y]; F = np.r_[BF, T + len(BV)]
col = np.r_[np.tile([.8, .72, .66, 1], (len(BV), 1)), np.where(is_c[:, None], [[.95, .62, .25, 1]], [[.35, .55, .85, 1]])]
np.savez(OUT / f"{TAG}.npz", verts=V.astype(np.float32), faces=F.astype(np.int32), part_colors=col.astype(np.float32))
from hifipushie import render
fr_ = render.view_frames(V[V[:, 2] > -0.07], ["front", "three_quarter", "side"], focus=[0, 0, 0.0], zoom=1.1)
ims = render.render_views(OUT / f"{TAG}.npz", fr_, 420, "clay_studio.exr", cavity=False)
sh = Image.new("RGB", (1260, 460), "white")
for i, im in enumerate(ims): sh.paste(im, (420 * i, 40))
ImageDraw.Draw(sh).text((8, 8), f"{TAG}: Simon's stand + collar, Blender cloth {json.dumps({k: v for k, v in A.items() if k != 'tag'})}; sim {tsim:.0f}s", fill="black")
sh.save(OUT / f"{TAG}.png"); print("saved", OUT / f"{TAG}.png")
