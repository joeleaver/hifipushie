"""Spike: wrap the PATTERN's own stand + collar (Simon, from form_c0) on the primitive neck. Pins the stand's neck
edge on the neckline, sews the collar's short edge to the stand's top, folds it down outside, and relaxes with the
flat pieces' own edge lengths + a little gravity + the body / stand as a floor. No re-drafting."""
import sys, json, time, pickle
import numpy as np
from pathlib import Path
from scipy.spatial import Delaunay
from PIL import Image, ImageDraw
from hifipushie import render

OUT = Path("/mnt/data/hifipushie/collar_spike")
A = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
TAG = A.get("tag", "w1")
OPEN = A.get("open", 0.0)       # how far the top button is undone: the stand's front ends lie back this angle (deg)
GRAV = A.get("grav", 0.4)
f = pickle.load(open("/mnt/data/hifipushie/drape_band1/form_c0.pkl", "rb"))
pcs = f["pieces"]["pieces"]

def ring(name):
    p = pcs[name]; P = np.asarray(p["P"], float); return P, p["names"]

def mesh_flat(P, h=0.004):
    lo, hi = P.min(0), P.max(0)
    gx, gy = np.meshgrid(np.arange(lo[0], hi[0], h), np.arange(lo[1], hi[1], h))
    G = np.c_[gx.ravel(), gy.ravel()]
    def inside(Q):
        x, y = Q[:, 0], Q[:, 1]; c = np.zeros(len(Q), bool)
        for a, b in zip(P, np.roll(P, -1, 0)):
            m = ((a[1] > y) != (b[1] > y)) & (x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1] + 1e-12) + a[0])
            c ^= m
        return c
    G = G[inside(G)]
    # keep interior points away from the boundary
    d = np.min(np.linalg.norm(G[:, None] - P[None], axis=2), 1); G = G[d > 0.6 * h]
    U = np.r_[P, G]
    T = Delaunay(U).simplices
    T = T[inside(U[T].mean(1))]
    return U, T, len(P)

def edges(T):
    E = np.r_[T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]]; E.sort(1); return np.unique(E, axis=0)

def arc_idx(P, names, a, b):
    """ring indices from name a to name b, the short way round."""
    i, j, n = names[a], names[b], len(P)
    f_ = [(i + k) % n for k in range((j - i) % n + 1)]; r_ = [(i - k) % n for k in range((i - j) % n + 1)]
    L = lambda ix: np.linalg.norm(np.diff(P[ix], axis=0), axis=1).sum()
    return np.array(f_ if L(f_) <= L(r_) else r_)

SP, SN = ring("stand"); CP, CN = ring("collar")
neck_e = arc_idx(SP, SN, "leftBottomCf", "rightBottomCf")
top_e = arc_idx(SP, SN, "leftTopCf", "rightTopCf")
sewn_e = arc_idx(CP, CN, "leftBottomEdge", "rightBottomEdge")
def alen(P, ix): return np.r_[0, np.cumsum(np.linalg.norm(np.diff(P[ix], axis=0), axis=1))]
Lneck = alen(SP, neck_e)[-1]; R = Lneck / (2 * np.pi)  # a neckline exactly as long as the stand's neck edge
RN = R - 0.003                                            # the neck under it (a 3 mm gap)
ZS, RS = -0.06, 0.20                                      # the shoulder cone's foot
print(f"stand neck edge {Lneck*1000:.0f} mm, top {alen(SP, top_e)[-1]*1000:.0f}, collar sewn {alen(CP, sewn_e)[-1]*1000:.0f}, neckline r {R*1000:.1f}")

def floor_r(z, off):
    """the body's radius at height z (neck cylinder above 0, the cone below) + off."""
    zc = np.minimum(z, 0); return np.where(z >= 0, RN, RN + (RS - RN) * (zc / ZS)) + off

# meshes
SU, ST, sn = mesh_flat(SP); CU, CT, cn = mesh_flat(CP)
U = np.r_[SU, CU]; T = np.r_[ST, CT + len(SU)]; off_c = len(SU)
E = edges(T)
# interfacing: the stand also keeps its lengths between points up to ~2.5 grid steps apart (resists bending)
from scipy.spatial import cKDTree as _K
pr = np.array(sorted(_K(SU).query_pairs(A.get('bend_r', 0.010))))
if A.get('stiff_collar', 0):  # the collar is interfaced too: it keeps its lengths across ~2.5 steps (resists bending)
    pc_ = np.array(sorted(_K(CU).query_pairs(A.get('bend_r', 0.010)))) + len(SU)
    pr = np.r_[pr, pc_] if len(pr) else pc_
E = np.unique(np.r_[E, pr], axis=0) if len(pr) else E
L0 = np.linalg.norm(U[E[:, 0]] - U[E[:, 1]], axis=1)
is_c = np.r_[np.zeros(len(SU), bool), np.ones(len(CU), bool)]
# parameter round the neck: the stand's neck edge arc from its midpoint; CB at +Y
s_neck = alen(SP, neck_e); s_mid = np.interp(0.0, SP[neck_e, 0], s_neck) if SP[neck_e[0], 0] < SP[neck_e[-1], 0] else s_neck[-1] / 2
def theta_of_x(x):  # flat x -> angle (x = 0 at CB)
    return np.pi / 2 - x / R
# initial: stand wrapped up the neck; collar hanging down outside it from the stand's top
X = np.zeros((len(U), 3))
ybot = np.interp(SU[:, 0], SP[neck_e, 0][np.argsort(SP[neck_e, 0])], SP[neck_e, 1][np.argsort(SP[neck_e, 0])])
ALPHA = np.arctan2(-ZS, RS - RN)
def open_w(theta):
    """0 at CB .. 1 at CF (CF at -Y): how much of the opening this point of the neckline takes."""
    u = np.abs(np.angle(np.exp(1j * (theta - np.pi / 2)))) / np.pi  # 0 CB .. 1 CF
    return np.clip((u - 0.55) / 0.45, 0, 1) ** 2 * OPEN / 90
HALF = Lneck / 2
def _open_path(n=800):
    """half the neckline, CB (s = 0) to CF (s = HALF): the same LENGTH as the band's neck edge; its front part turns
    down the shoulder slope (a V) by up to OPEN degrees, walked over the body surface, so nothing is stretched."""
    ss = np.linspace(0, HALF, n); ds = ss[1] - ss[0]
    th, d = np.pi / 2, 0.0; out = []
    for s_ in ss:
        rr = R + max(d, 0) * np.cos(ALPHA); zz = -max(d, 0) * np.sin(ALPHA)
        out.append((th, rr, zz))
        u = s_ / HALF; phi = np.radians(OPEN) * np.clip((u - 0.5) / 0.5, 0, 1) ** 1.2
        th -= np.cos(phi) * ds / rr; d += np.sin(phi) * ds
    return ss, np.array(out)
_SS, _OP = _open_path()
def neck_at_s(sv):
    """sv: signed arc from CB (+ toward -X side ... mirrored by sign)."""
    a_ = np.abs(sv); sg = np.where(sv >= 0, 1.0, -1.0)
    th = np.interp(a_, _SS, _OP[:, 0]); rr = np.interp(a_, _SS, _OP[:, 1]); zz = np.interp(a_, _SS, _OP[:, 2])
    th = np.pi / 2 + sg * (th - np.pi / 2)
    return np.c_[rr * np.cos(th), rr * np.sin(th), zz], th
def neck_pt(theta):
    sv = (np.pi / 2 - np.angle(np.exp(1j * (theta - np.pi / 2))) - np.pi / 2) * R  # (closed-circle arc as the lookup)
    sv = -np.angle(np.exp(1j * (theta - np.pi / 2))) * R
    return neck_at_s(sv)[0]
def up_dir(theta, sv=None):
    u_ = np.abs(sv) / HALF if sv is not None else None
    w = np.clip(np.clip((u_ - 0.55) / 0.45, 0, 1) ** 2 * OPEN / 90 * A.get("lie", 1.6), 0, 1)[:, None]
    radial = np.c_[np.cos(theta), np.sin(theta), np.zeros_like(theta)]
    slope = radial * np.cos(ALPHA) + np.c_[0 * theta, 0 * theta, -np.sin(ALPHA) + 0 * theta]
    v = (1 - w) * np.array([0, 0, 1.0]) + w * slope
    return v / np.linalg.norm(v, axis=1)[:, None]
XN = np.abs(SP[neck_e, 0]).max(); svs = SU[:, 0] * HALF / XN
bp, th = neck_at_s(svs); X[:len(SU)] = bp + (SU[:, 1] - ybot)[:, None] * up_dir(th, svs)
xs = np.sort(CP[sewn_e, 0]); ys = CP[sewn_e, 1][np.argsort(CP[sewn_e, 0])]
dy = CU[:, 1] - np.interp(CU[:, 0], xs, ys)          # below the sewn edge (negative: toward the outer edge)
ztop = 0.035
svc = CU[:, 0] * (alen(SP, top_e)[-1] / alen(CP, sewn_e)[-1]) * HALF / XN; bpc, th = neck_at_s(svc)
top_pt = bpc + 0.033 * up_dir(th, svc); rad = np.c_[np.cos(th), np.sin(th), 0 * th]
X[off_c:] = top_pt + 0.004 * rad - dy[:, None] * up_dir(th, svc)
# pins: the stand's neck edge on the neckline (by arc); the collar's sewn edge sewn to the stand's top edge (by arc)
pin_i = neck_e; s = alen(SP, neck_e) / Lneck
thp = np.pi / 2 + (s - 0.5) * 2 * np.pi * np.sign(SP[neck_e[-1], 0] - SP[neck_e[0], 0]) * -1
pin_X = neck_at_s(SP[neck_e, 0] * HALF / np.abs(SP[neck_e, 0]).max())[0]
st_t = top_e; sw = sewn_e + off_c
ft = alen(SP, top_e) / alen(SP, top_e)[-1]; fs = alen(CP, sewn_e) / alen(CP, sewn_e)[-1]
pair = np.array([st_t[np.argmin(np.abs(ft - q))] for q in fs])
from scipy.spatial import cKDTree
def vnormals(V, Tt):
    n = np.cross(V[Tt[:, 1]] - V[Tt[:, 0]], V[Tt[:, 2]] - V[Tt[:, 0]]); N = np.zeros_like(V)
    for k in range(3): np.add.at(N, Tt[:, k], n)
    N /= np.linalg.norm(N, axis=1)[:, None] + 1e-12
    out = np.sign((N * np.c_[V[:, 0], V[:, 1], 0 * V[:, 2]]).sum(1).mean() or 1.0)  # point away from the neck axis
    return N * out
XS0 = X[:len(SU)].copy()  # the stand is interfaced: it keeps its wrapped shape (a made piece)
NS0 = vnormals(XS0, ST); KS = cKDTree(XS0)
t0 = time.time()
for it in range(int(A.get("iters", 600))):
    # gravity
    X[:, 2] -= GRAV * 1e-4
    # edge lengths (Jacobi)
    for _ in range(A.get('sub', 10)):
        d = X[E[:, 1]] - X[E[:, 0]]; Ln = np.linalg.norm(d, axis=1) + 1e-12
        corr = (0.5 * (Ln - L0) / Ln)[:, None] * d
        acc = np.zeros_like(X); cnt = np.zeros(len(X))
        np.add.at(acc, E[:, 0], corr); np.add.at(acc, E[:, 1], -corr); np.add.at(cnt, E[:, 0], 1); np.add.at(cnt, E[:, 1], 1)
        X += 0.9 * acc / np.maximum(cnt, 1)[:, None]
    # sewing + pins
    m = 0.5 * (X[sw] + X[pair]); X[sw] = m; X[pair] = m
    X[pin_i] = pin_X
    X[:len(SU)] += A.get('stiff', 0.6) * (XS0 - X[:len(SU)])
    X[pair] = XS0[pair]  # (the collar is sewn to the stiff stand's top)
    # floors: the stand outside the neck; the collar outside the stand (and the body)
    r = np.linalg.norm(X[:, :2], axis=1) + 1e-12
    rmin = np.where(is_c, floor_r(X[:, 2], 0.0015), floor_r(X[:, 2], 0.0))
    low = r < rmin; X[low, :2] *= (rmin[low] / r[low])[:, None]
    # the collar lies OUTSIDE the stand (it is turned over it): along the stand's own normal, where it is over it
    if it % 10 == 0:
        XSn = X[:len(SU)].copy(); NS0 = vnormals(XSn, ST); KS = cKDTree(XSn)
    ci = np.where(is_c)[0]; dd, j = KS.query(X[ci]); near = dd < 0.012
    ci, j = ci[near], j[near]
    h = ((X[ci] - X[j]) * NS0[j]).sum(1); bad = h < 0.0015
    X[ci[bad]] += (0.0015 - h[bad])[:, None] * NS0[j[bad]]
ee = np.abs(np.linalg.norm(X[E[:,1]]-X[E[:,0]],axis=1)/L0-1); ec = is_c[E[:,0]]
e0 = np.abs(np.linalg.norm(XS0[E[~ec][:,1]]-XS0[E[~ec][:,0]],axis=1)/L0[~ec]-1)
print(f"strain p99: stand {np.percentile(ee[~ec],99)*100:.1f} % (its wrapped start {np.percentile(e0,99)*100:.1f}), collar {np.percentile(ee[ec],99)*100:.1f} %")
print(f"relaxed {time.time()-t0:.1f}s; edge strain p99 {np.percentile(np.abs(np.linalg.norm(X[E[:,1]]-X[E[:,0]],axis=1)/L0-1),99)*100:.1f} %")
# render: body + stand (blue) + collar (orange)
def rev(prof, n=128):
    t = np.linspace(0, 2*np.pi, n, endpoint=False)
    V = np.array([[rr*np.cos(a), rr*np.sin(a), z] for rr, z in prof for a in t]); F = []
    for i in range(len(prof)-1):
        for j in range(n):
            a, b = i*n+j, i*n+(j+1)%n; F += [[a, b, b+n], [a, b+n, a+n]]
    return V, np.array(F)
prof = [(RS, ZS)] + [(RN + (RS-RN)*(1-q), ZS*(1-q)) for q in np.linspace(0.05, 1, 20)] + [(RN, z) for z in np.linspace(0.003, 0.12, 20)]
BV, BF = rev(prof)
V = np.r_[BV, X]; F = np.r_[BF, T + len(BV)]
col = np.r_[np.tile([.8, .72, .66, 1], (len(BV), 1)), np.where(is_c[:, None], [[.95, .62, .25, 1]], [[.35, .55, .85, 1]])]
col = np.r_[col]
np.savez(OUT / f"{TAG}.npz", verts=V.astype(np.float32), faces=F.astype(np.int32), part_colors=col.astype(np.float32))
fr_ = render.view_frames(V[V[:, 2] > -0.07], ["front", "three_quarter", "side"], focus=[0, 0, 0.0], zoom=1.1)
ims = render.render_views(OUT / f"{TAG}.npz", fr_, 420, "clay_studio.exr", cavity=False)
sh = Image.new("RGB", (1260, 460), "white")
for i, im in enumerate(ims): sh.paste(im, (420*i, 40))
ImageDraw.Draw(sh).text((8, 8), f"{TAG}: Simon's own stand + collar wrapped (open {OPEN}, grav {GRAV}); {time.time()-t0:.1f}s", fill="black")
sh.save(OUT / f"{TAG}.png"); print("saved", OUT / f"{TAG}.png")
