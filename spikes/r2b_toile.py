"""R2 step 4 (TOILE) of drape first: the suit jacket's FULL toile (docs/proposals/drape_first.md; R1: spikes/r1_toile.py).

  HIFIPUSHIE_HOME=<ws> slot uv run python spikes/r2_toile.py <out> <loaded.pkl> <jacket.json> <d4 lines.json> <ref.png> <r1 girths.json>

R1's body field (the body's SDF closed by 25 mm minus the calibrated ease k(z) w(theta); R1's k per level reused) plus:
 1 SHOULDER PAD: an ellipsoid smooth-unioned on the shoulder, its top at the reference's jacket top line (read from the
   picture, x scaled so the picture's shoulder point (step 2 row shoulder_w) lands on D4's shoulder point).
 2 SLEEVES: a smooth tapered TUBE round the arm (not the arm's offset): the axis through the arm's section centres (its
   pitch: the arm's own hang), the radius = the section's tape (convex hull) / 2 pi + R1's sleeve ease (18 -> 22 mm),
   made monotone from the wrist up (a sleeve tapers; it does not follow the biceps / forearm bumps) and held at the
   biceps above it; capped at the armhole's plane and smooth-unioned with the body (the torso's own arm pushed out).
 3 SKIRT: below the seat (step 0's hips level) the section is the seat's, extruded straight down, plus a flare that
   meets step 0's hem girth at the hem (a jacket hangs from the seat; it does not follow the buttocks under).
 4 FRONT: buttoned, the left front runs past centre front by the LAP (20 mm: a 20 mm suit button's lap; steps 1-2 give
   none) from the break to the hem; below the bottom button the cutaway curve of step 2's front_edge trace.
 5 LAPEL: above the break the front's edge is the roll line (step 2's roll trace, moved with the closure so the break
   sits at CF + lap); the lapel = the toile under step 2's lapel outline (roll line, front_edge above the break, the
   gorge / notch from collar_top), lifted 4 mm: the facing side out, lying on the chest.
 6 COLLAR: stand (28 mm) from the toile's neckline + the fall (40 mm) turned down over it, from the neckline round to
   the gorge (the stand fading to the collar end); the fall's edge from step 2's collar_top trace in front.
 7 BACK NECK: no closing near the neck (the 25 mm closing raised the back neck as a stand in R1): the body cut at D4's
   neckline, the collar sits on it.
Writes <out>/toile.npz (left half toile, lapel, collar, arm tube, marks as scalars), toile.json, toile_sheet.png."""
import json
import os
import pickle
import sys
import time

import numpy as np
from scipy import ndimage
from scipy.interpolate import RegularGridInterpolator
from scipy.spatial import ConvexHull
from skimage import measure

sys.path.insert(0, os.path.dirname(__file__))
from r1_common import clip, largest, px_to_xz, render, resample, sheet  # noqa: E402
from r2_common import grid_mesh, ref_top  # noqa: E402
from r2b_common import Cone, march, pad_thickness, smooth01  # noqa: E402

out, src, jpath, lpath, ref, r1g = sys.argv[1:7]
os.makedirs(out, exist_ok=True)
t0 = time.time()
log = lambda m: print(f"[{time.time() - t0:6.1f}s] {m}", flush=True)
d = pickle.load(open(src, "rb"))
body = d["body"]
CT = body.contact
T = d["pat"].M["starts"]["tapes"]
steps = json.load(open(jpath))["steps"]
fit = steps["0"]["output"]["fit"]
H0 = steps["0"]["output"]["heights"]
tr = {t["id"]: t for t in steps["2"]["output"]["traces"]}
rows2 = {r["id"]: r for r in steps["2"]["output"]["rows"]}
L = json.load(open(lpath))["lines"]
MIR = np.array([-1.0, 1, 1])
LAP = 0.020
STAND, FALL = 0.028, 0.040
STAND_OUT = 0.15  # s4-31's collar (design.mjs: stand 28, fall 40)
info = {"lap_mm": 20, "lap_from": "convention: a 20 mm suit button's lap past CF (steps 1-2 give no lap)",
        "collar_mm": {"stand": 28, "fall": 40, "from": "s4-31 design.mjs collar (stand 28, fall 40)"}}

h = 0.006
HEM = H0["hem"]["z_mm"] / 1000
xs = np.arange(-0.60, 0.60 + h / 2, h)
ys = np.arange(-0.24, 0.24 + h / 2, h)
zs = np.arange(HEM, 1.64 + h / 2, h)
G = np.stack(np.meshgrid(xs, ys, zs, indexing="ij"), -1).reshape(-1, 3)
sd = np.empty(len(G))
for i in range(0, len(G), 200000):
    sd[i:i + 200000] = CT.query(G[i:i + 200000])[0]
sd = sd.reshape(len(xs), len(ys), len(zs))
R_CL = 0.025
dil = sd <= R_CL
sdc = np.where(dil, R_CL - ndimage.distance_transform_edt(dil) * h, sd)
sdc = ndimage.gaussian_filter(sdc, 1.0)

# 7: no closing round the neck (above the neckline's lowest point - 4 cm, within 11 cm of the neck's axis)
nk = np.concatenate([np.asarray(L["neckline.L"]["pts"]), np.asarray(L["neckline.R"]["pts"])[::-1]])
cn = nk[:, :2].mean(0)
GX, GY, GZ = np.meshgrid(xs, ys, zs, indexing="ij")
rh = np.hypot(GX - cn[0], GY - cn[1])
wn = np.clip((0.11 - rh) / 0.03, 0, 1) * np.clip((GZ - (nk[:, 2].min() - 0.04)) / 0.03, 0, 1)
sdc = sdc + (ndimage.gaussian_filter(sd, 0.7) - sdc) * wn
log(f"body field {sd.shape}; neck unclosed over {np.mean(wn > 0.5) * 100:.2f} % of the grid")

# ---------- arm: axis, armhole plane, the sleeve tube
sh = np.asarray(T["shoulderToWrist"]["pts"], float)[0]
wr = np.asarray(T["wrist"]["pts"], float).mean(0)
A = wr - sh
alen = np.linalg.norm(A)
A /= alen
ah = np.asarray(L["armhole.L"]["pts"], float)
ca = ah.mean(0)
na = np.linalg.svd(ah - ca)[2][2]
na = na if na @ (sh - np.array([0, 0, sh[2]])) > 0 else -na
yc = float(np.asarray(T["chest"]["pts"], float)[:, 1].mean())
CONE = Cone(sh, A, ah)  # the armhole: D4's loop carried out from the shoulder joint (r2b_common)


def folded(P):
    return P * np.where(P[:, :1] < 0, MIR, 1)


BV = np.asarray(body.V, float)
BT = np.asarray(body.T, int)
Q = BV[BV[:, 0] > 0]
tq = (Q - sh) @ A
dax = np.linalg.norm(Q - (sh + np.clip(tq, 0, alen)[:, None] * A), axis=1)
sq = (Q - ca) @ na
sel = (sq > 0.01) & (tq > 0) & (tq < alen) & (dax < 0.10)
Q, tq = Q[sel], tq[sel]
e1 = np.cross(A, [0, 1.0, 0])
e1 /= np.linalg.norm(e1)
e2 = np.cross(A, e1)
bins = np.linspace(tq.min(), alen, 15)
Cs, Ts, Gr = [], [], []
for b0, b1 in zip(bins[:-1], bins[1:]):
    m = (tq >= b0) & (tq < b1)
    if m.sum() < 30:
        continue
    q = Q[m]
    p2 = np.c_[q @ e1, q @ e2]
    hull = ConvexHull(p2)
    c2 = p2[hull.vertices].mean(0)
    Cs.append(c2[0] * e1 + c2[1] * e2 + (q @ A).mean() * A)
    Ts.append(float((Cs[-1] - sh) @ A))
    Gr.append(hull.area)
Cs, Ts, Gr = np.array(Cs), np.array(Ts), np.array(Gr)
# the centres as a smooth axis: a quadratic in t (the arm's pitch and its slight bend), not the bins' jitter
cf = [np.polyfit(Ts, Cs[:, i], 2) for i in range(3)]
tax = np.r_[-0.06, Ts, alen + 0.04]  # the tube runs up into the shoulder: the crown is the tube cut by the armhole
CAX = np.c_[[np.polyval(c, tax) for c in cf]].T
ease_r = 0.018 + 0.004 * np.clip(Ts / alen, 0, 1)
raw_r = Gr / (2 * np.pi) + ease_r
mono = np.maximum.accumulate(raw_r[::-1])[::-1]  # never narrower than anything below it (wrist -> up)
kb = int(np.argmin(np.abs(Ts - 0.30 * alen)))  # the biceps: 30 % down the arm
mono[:kb] = mono[kb]
smooth_r = np.convolve(np.r_[mono[0], mono, mono[-1]], [0.25, 0.5, 0.25], "valid")
RAX = np.r_[smooth_r[0], smooth_r, smooth_r[-1]]
info["sleeve"] = {"t_mm": np.round(Ts * 1000).tolist(), "arm_tape_mm": np.round(Gr * 1000, 1).tolist(),
                  "tube_round_mm": np.round(2 * np.pi * smooth_r * 1000, 1).tolist(),
                  "bumps_bridged_mm": round(float((smooth_r - raw_r).max() * 1000), 1),
                  "pitch_deg_fwd": round(float(np.degrees(np.arctan2(-(CAX[-2] - CAX[1])[1], np.linalg.norm((CAX[-2] - CAX[1])[[0, 2]])))), 1)}
log(f"sleeve tube: {info['sleeve']}")


def axis_param(P):
    """Nearest point on the (folded) tube axis: (distance, radius there, t along the axis, segment direction)."""
    best = np.full(len(P), np.inf)
    rr = np.zeros(len(P))
    tt = np.zeros(len(P))
    dd = np.zeros((len(P), 3))
    for j in range(len(CAX) - 1):
        dv = CAX[j + 1] - CAX[j]
        u = np.clip(((P - CAX[j]) @ dv) / (dv @ dv), 0, 1)
        dist = np.linalg.norm(P - (CAX[j] + u[:, None] * dv), axis=1)
        r = RAX[j] + u * (RAX[j + 1] - RAX[j])
        b = dist - r < best - rr if j else np.ones(len(P), bool)
        best = np.where(b, dist, best)
        rr = np.where(b, r, rr)
        tt = np.where(b, tax[j] + u * (tax[j + 1] - tax[j]), tt)
        dd[b] = dv / np.linalg.norm(dv)
    return best, rr, tt, dd


def tube(P):
    Q = folded(P)
    dist, r, _, _ = axis_param(Q)
    return np.maximum(dist - r, -0.015 - CONE.sdist(Q))


def armness(P, shift=0.0):
    Q = folded(np.atleast_2d(P))
    s = CONE.sdist(Q)
    t = np.clip((Q - sh) @ A, 0, alen)
    dx = np.linalg.norm(Q - (sh + t[:, None] * A), axis=1)
    a = np.clip((s - shift) / 0.04 + 0.5, 0, 1)
    return a * a * (3 - 2 * a) * np.clip((0.13 - dx) / 0.03, 0, 1)


# ---------- torso ease (R1's calibrated k per level)
kmm = json.load(open(r1g))["girths"]
LV = [("hem", fit["hem"]["level_z_m"]), ("hips", fit["hips"]["level_z_m"]), ("waist", fit["waist"]["level_z_m"]),
      ("chest", fit["chest"]["level_z_m"])]
KZ = [HEM - 0.01] + [z for _, z in LV][1:] + [1.45, 1.53]
KV = [kmm[n]["k_front_mm"] / 1000 for n, _ in LV] + [0.012, 0.006]


def ease_torso(P):
    th = np.arctan2(P[:, 0], -(P[:, 1] - yc))
    return np.interp(P[:, 2], KZ, KV) * (0.35 + 0.65 * np.cos(th) ** 2)


def smin(a, b, k):
    hh = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
    return b + (a - b) * hh - k * hh * (1 - hh)


# UNDER THE ARM the sleeve tube (eased) overlaps the torso and fuses with it into a web that dropped the armhole ~9 cm:
# below the body's underarm the arm is pushed out of the torso from 2 cm OUTSIDE the cone (above it, over the top and the
# pitches, only from inside the cone, so the torso there stays whole).
z_ua = float(ah[:, 2].min())
info["underarm"] = {"body_underarm_z": round(z_ua, 3), "rule": "push from 2 cm outside the cone below it, from inside above"}
Ft = np.empty(len(G))
Tb = np.empty(len(G))
Ar = np.empty(len(G))
for i in range(0, len(G), 200000):
    P = G[i:i + 200000]
    Ft[i:i + 200000] = ease_torso(P)
    Tb[i:i + 200000] = tube(P)
    below = smooth01((z_ua - P[:, 2]) / 0.03)
    Ar[i:i + 200000] = np.maximum(armness(P, 0.02), armness(P, -0.02) * below)
Ft = ndimage.gaussian_filter(sdc - Ft.reshape(sdc.shape), 0.8) + 0.08 * Ar.reshape(sdc.shape)
F0 = smin(Ft, Tb.reshape(sdc.shape), 0.015)
log("torso + sleeve tubes")

# 3: skirt: below the seat, the seat's section straight down + a flare to step 0's hem girth
z_seat = fit["hips"]["level_z_m"]
ks = int(np.argmin(np.abs(zs - z_seat)))
SEAT = F0[:, :, ks].copy()
SEAT[np.abs(xs) > 0.27, :] = 1.0


def girth_slice(Fs, z):
    C = measure.find_contours(Fs, 0)
    Qp = np.concatenate([np.c_[np.interp(c[:, 0], np.arange(len(xs)), xs), np.interp(c[:, 1], np.arange(len(ys)), ys)] for c in C])
    a = armness(np.c_[Qp, np.full(len(Qp), z)])
    Qp = Qp[(a < 0.5) & (np.abs(Qp[:, 0]) < 0.30)]
    return ConvexHull(Qp).area * 1000


g_seat = girth_slice(SEAT, zs[ks])
flare = max(0.0, (fit["hem"]["garment_girth_mm"] - g_seat) / 1000 / (2 * np.pi))
torso_cols = (np.abs(xs) <= 0.27)[:, None]
for k in range(ks):  # the torso's columns take the seat's section (+ flare); the sleeves keep their own field
    F0[:, :, k] = np.where(torso_cols, SEAT - flare * (zs[ks] - zs[k]) / (zs[ks] - zs[0]), F0[:, :, k])
info["skirt"] = {"seat_z": round(float(zs[ks]), 3), "seat_round_mm": round(g_seat, 1), "hem_flare_mm": round(flare * 1000, 1)}
log(f"skirt {info['skirt']}")


# 1: shoulder pad, its top at the reference's jacket top line
def top_line(Fd, x):
    """The field's highest surface point (z) over the column x (any y)."""
    ix = int(np.argmin(np.abs(xs - x)))
    col = Fd[ix]  # (y, z)
    inside = col < 0
    zt = []
    for iy in range(len(ys)):
        k = np.where(inside[iy])[0]
        if len(k) and k[-1] + 1 < len(zs):
            f0, f1 = col[iy, k[-1]], col[iy, k[-1] + 1]
            zt.append(zs[k[-1]] + h * f0 / (f0 - f1))
    return max(zt) if zt else np.nan


sh_tip = np.asarray(L["shoulder.L"]["pts"], float)[-1]
xs_ref = rows2["shoulder_w"]["target"]["value"] / 2 * 1.0811e-3  # the picture's shoulder point (half width)
scale = sh_tip[0] / xs_ref
fx = np.linspace(0.55, 1.05, 11)
vref = ref_top(ref, 628 + fx * xs_ref / 1.0811e-3)
zref = px_to_xz(0, vref)[1]
ztoile = np.array([top_line(F0, f * sh_tip[0]) for f in fx])
lift = zref - ztoile
info["pad"] = {"x_mm": np.round(fx * sh_tip[0] * 1000).tolist(), "ref_top_z": np.round(zref, 4).tolist(),
               "toile_top_z_before": np.round(ztoile, 4).tolist(), "x_scale_ref_to_model": round(float(scale), 3)}
SHp = np.asarray(L["shoulder.L"]["pts"], float)
_o = np.argsort(SHp[:, 0])
y_sh = lambda x: np.interp(x, SHp[_o, 0], SHp[_o, 1])
z_sh = lambda x: np.interp(x, SHp[_o, 0], SHp[_o, 2])
x_sp = sh_tip[0]
GAP = 0.002  # the shell lies over the pad at the cloth gap
u_fx = pad_thickness(np.c_[fx * x_sp, y_sh(fx * x_sp), z_sh(fx * x_sp)], x_sp, y_sh, z_sh, 1.0)
okp = (fx > 0.7) & (u_fx > 0.3)
TPAD = float(np.clip(np.nanmax((lift[okp] - GAP) / u_fx[okp]), 0.004, 0.025))
TH = np.empty(len(G))
for i in range(0, len(G), 200000):
    TH[i:i + 200000] = pad_thickness(G[i:i + 200000], x_sp, y_sh, z_sh, TPAD)
TH = TH.reshape(sdc.shape)
F_nopad = F0.copy()
F0 = F0 - (TH + GAP * smooth01(TH / 0.002))
PADF = np.maximum(F_nopad - TH, -F_nopad)  # the pad's own solid: from the toile's inside out to its thickness
info["pad"].update({"kind": "wedge under the shell (its own piece)", "thickness_at_shoulder_point_mm": round(TPAD * 1000, 1),
                    "inward_mm": 130, "past_shoulder_point_mm": 30, "front_back_half_width_mm": 110, "gap_mm": GAP * 1000})
info["pad"]["toile_top_z_after"] = np.round([top_line(F0, f * sh_tip[0]) for f in fx], 4).tolist()
log(f"pad {info['pad']}")

Fd = F0
FD = RegularGridInterpolator((xs, ys, zs), Fd, bounds_error=False, fill_value=1.0)
info["girths"] = {}
for n, z in LV:
    k = int(np.argmin(np.abs(zs - max(z, HEM + 0.003))))
    info["girths"][n] = {"z": round(float(zs[k]), 3), "toile_mm": round(girth_slice(Fd[:, :, k], zs[k]), 1),
                         "plan_mm": fit[n]["garment_girth_mm"]}
log(f"girths {info['girths']}")

V, F, _, _ = measure.marching_cubes(Fd, 0.0, spacing=(h, h, h))
V = V + np.array([xs[0], ys[0], zs[0]])
F = F[:, [0, 2, 1]]
V, F = largest(V, F)
log(f"meshed {len(V)} v")


def grad(P, e=1e-3):
    g = np.stack([(FD(P + e * np.eye(3)[i]) - FD(P - e * np.eye(3)[i])) / (2 * e) for i in range(3)], 1)
    return g / (np.linalg.norm(g, axis=1, keepdims=True) + 1e-12)


def onto(P, n=None):
    n = grad(P) if n is None else n
    t = np.zeros(len(P))
    for _ in range(8):
        f = FD(P + t[:, None] * n)
        df = (FD(P + (t + 1e-3)[:, None] * n) - f) / 1e-3
        t = t - f / np.where(np.abs(df) > 0.1, df, 1.0)
    return P + t[:, None] * n


def front_hit(x, z):
    """The toile seen from the front: the first surface point along +y at (x, z)."""
    yy = np.arange(-0.26, yc, 0.002)
    out = []
    for xi, zi in zip(np.atleast_1d(x), np.atleast_1d(z)):
        f = FD(np.c_[np.full(len(yy), xi), yy, np.full(len(yy), zi)])
        k = int(np.argmax(f < 0))
        y = yy[k - 1] + 0.002 * f[k - 1] / (f[k - 1] - f[k])
        out.append([xi, y, zi])
    return onto(np.array(out))


# ---------- the cuts' scalars
an_n = np.arctan2(nk[:, 1] - cn[1], nk[:, 0] - cn[0])
o = np.argsort(an_n)
an_s, zn_s = an_n[o], nk[o, 2]


def phi_neck(P):
    return np.interp(np.arctan2(P[:, 1] - cn[1], P[:, 0] - cn[0]), an_s, zn_s, period=2 * np.pi) - P[:, 2]


def trace_xz(name, a=None, b=None):
    p = np.array(tr[name]["points"], float)[a:b]
    return np.c_[px_to_xz(p[:, 0], p[:, 1])]


ROLL = trace_xz("roll.L", None, 5)  # gorge -> break
FE = trace_xz("front_edge.L")  # notch ... break (5) ... hem
z_top, z_brk, x_brk = ROLL[0, 1], ROLL[-1, 1], ROLL[-1, 0]


def shift(z):
    """The closure: the roll line's break moves from the open picture's to CF + lap; nothing moves at the gorge."""
    return (-LAP - x_brk) * np.clip((z_top - z) / (z_top - z_brk), 0, 1)


RS = ROLL[np.argsort(ROLL[:, 1])]
x_roll = lambda z: np.interp(z, RS[:, 1], RS[:, 0]) + shift(z)
LE = FE[:6][np.argsort(FE[:6, 1])]
WIDEN = 61.0 / 56.5  # R2's lapel 56.5 mm -> the reference's 59-63 (step 2 row lapel width): widened square from the roll line
x_lapel = lambda z: x_roll(z) + (np.interp(z, LE[:, 1], LE[:, 0]) + shift(z) - x_roll(z)) * WIDEN
BTN = px_to_xz(0, np.array(rows2["buttons"]["at"], float)[:, 1])[1]  # button heights
LOW = FE[5:][np.argsort(FE[5:, 1])]
z_btm = BTN.min()
dx_cut = lambda z: np.where(z < z_btm, np.interp(z, LOW[:, 1], LOW[:, 0]) - np.interp(z_btm, LOW[:, 1], LOW[:, 0]), 0)


def x_edge(z):
    return np.where(z >= z_brk, x_roll(z), -LAP + dx_cut(z))


cb = np.asarray(L["centre_back"]["pts"], float)
o = np.argsort(cb[:, 2])
cb = cb[o]
x_cb = lambda z: np.interp(z, cb[:, 2], cb[:, 0])


def phi_half(P):
    return np.where(P[:, 1] < yc, P[:, 0] - x_edge(P[:, 2]), P[:, 0] - x_cb(P[:, 2]))


z_sl = H0["sleeve_hem"]["z_mm"] / 1000
k_sl = int(np.argmin(np.abs(CAX[:, 2] - z_sl)))
p_sl = CAX[k_sl]
A_sl = (CAX[-1] - CAX[-3]) / np.linalg.norm(CAX[-1] - CAX[-3])


def phi_wrist(P):
    Q = folded(P)
    return np.maximum(-((Q - p_sl) @ A_sl), np.linalg.norm(np.cross(Q - p_sl, A_sl), axis=1) - 0.12)


V, F = clip(V, F, phi_neck(V))
V, F = largest(V, F)
V, F = clip(V, F, phi_wrist(V))
V, F = largest(V, F)
Vfull, Ffull = V, F
Vh, Fh = clip(V, F, phi_half(V))
Vh, Fh = largest(Vh, Fh)
log(f"left half toile {len(Vh)} v")

# ---------- 5: lapel: the toile under the lapel's outline, lifted 4 mm (facing out, on the chest)
TL = np.array(tr["collar_top.L"]["points"], float)
RT = np.r_[ROLL[0]]
Gc = np.r_[px_to_xz(*TL[0])]
Cp = np.r_[px_to_xz(*TL[1])]
TOP = np.array([RT, Gc, Cp])
TOP[:, 0] += shift(TOP[:, 1])
TOP = TOP[np.argsort(TOP[:, 0])]
z_top_line = lambda x: np.interp(x, TOP[:, 0], TOP[:, 1])
Vl, Fl = Vfull, Ffull
for ph in (lambda P: P[:, 0] - x_roll(P[:, 2]), lambda P: x_lapel(P[:, 2]) - P[:, 0],
           lambda P: z_top_line(P[:, 0]) - P[:, 2], lambda P: P[:, 2] - z_brk, lambda P: (yc - 0.03) - P[:, 1]):
    Vl, Fl = clip(Vl, Fl, ph(Vl))
Vl, Fl = largest(Vl, Fl)
Vl0 = Vl.copy()
Vl = Vl + 0.004 * grad(Vl)
# lapel width: the edge's furthest point from the roll line, square to it (3D, on the toile)
rl = front_hit(x_roll(np.linspace(z_brk, z_top, 60)), np.linspace(z_brk, z_top, 60))
zz = np.linspace(z_brk, z_top, 40)
le = front_hit(x_lapel(zz), zz)
wid = [np.min(np.linalg.norm(rl - p, axis=1)) for p in le]
info["lapel"] = {"width_max_mm": round(max(wid) * 1000, 1), "at_z": round(float(zz[int(np.argmax(wid))]), 3),
                 "ref_mm": "59-63", "roll_mm": round(float(np.linalg.norm(np.diff(rl, axis=0), axis=1).sum() * 1000), 1),
                 "break_z": round(float(z_brk), 4), "gorge_top_z": round(float(z_top), 4)}
log(f"lapel {info['lapel']}")

# ---------- 6: collar: stand (neckline -> roll) and fall (roll -> over the stand -> edge on the toile)
Bh = np.unique(np.sort(np.concatenate([Fh[:, [0, 1]], Fh[:, [1, 2]], Fh[:, [2, 0]]]), axis=1), axis=0, return_counts=True)
bv = np.unique(Bh[0][Bh[1] == 1])
on_neck = bv[np.abs(phi_neck(Vh[bv])) < 2e-4]
NP = Vh[on_neck]
ang = np.arctan2(NP[:, 1] - cn[1], NP[:, 0] - cn[0])
NP = NP[(ang < np.pi / 2 + 0.05) & (ang > -np.pi / 2 - 0.2)]
ang = np.arctan2(NP[:, 1] - cn[1], NP[:, 0] - cn[0])
NP = NP[np.argsort(-ang)]  # centre back -> round the left side -> front
NP[0, 0] = 0.0
side_pt = np.asarray(L["shoulder.L"]["pts"], float)[0]
ks_ = int(np.argmin(np.linalg.norm(NP - side_pt, axis=1)))
Gp = front_hit(Gc[0] + shift(Gc[1]), Gc[1])[0] + 0.004 * grad(front_hit(Gc[0] + shift(Gc[1]), Gc[1]))[0]
NA = resample(NP[: ks_ + 1], 0.004)
NB = resample(np.r_[NP[ks_:], [Gp]], 0.004)
na_, nb_ = 24, 20
NA = NA[np.linspace(0, len(NA) - 1, na_).round().astype(int)]
NB = NB[np.linspace(0, len(NB) - 1, nb_).round().astype(int)][1:]
N = np.r_[NA, NB]
n_ = len(N)
hst = np.r_[np.full(na_, STAND), np.maximum(STAND * (1 - np.linspace(0, 1, nb_)[1:]), 0.004)]
inward = np.c_[cn[0] - N[:, 0], cn[1] - N[:, 1], np.zeros(n_)]
inward /= np.linalg.norm(inward, axis=1, keepdims=True)
up = np.array([0, 0, 1.0]) - STAND_OUT * inward  # leans OUT: neck < roll < fall edge (an inward stand makes a saddle)
up /= np.linalg.norm(up, axis=1, keepdims=True)
nN = grad(N)
Rl = N + hst[:, None] * up + 0.002 * nN
# fall edge: at the back FALL - STAND beyond the neckline, on the toile; in front step 2's collar_top trace
tang = np.gradient(N, axis=0)
outw = np.cross(nN, tang)
outw *= np.sign(np.einsum("ij,ij->i", outw, -inward))[:, None]
outw /= np.linalg.norm(outw, axis=1, keepdims=True)
EA = march(N[:na_], outw[:na_], FALL, onto, grad)  # the fall's width along the toile from the roll line's foot
EA = EA + 0.004 * grad(EA)
tp = np.array([px_to_xz(*p) for p in TL[[3, 2, 1]]])
tp[:, 0] += shift(tp[:, 1])
ET = front_hit(tp[:, 0], tp[:, 1])
ET = ET + 0.004 * grad(ET)
EB = resample(np.r_[EA[-1:], ET], 0.003)
EB = EB[np.linspace(0, len(EB) - 1, nb_).round().astype(int)][1:]
E = np.r_[EA, EB]
info["collar"] = {"neck_edge_half_mm": round(float(np.linalg.norm(np.diff(N, axis=0), axis=1).sum() * 1000), 1),
                  "fall_edge_half_mm": round(float(np.linalg.norm(np.diff(E, axis=0), axis=1).sum() * 1000), 1),
                  "trace_vs_back_fall_at_side_mm": round(float(np.linalg.norm(EA[-1] - ET[0]) * 1000), 1)}
N2 = N + 0.006 * nN  # the fall lies over the stand


def lerp_rows(a, b, k):
    return [a + (b - a) * s for s in np.linspace(0, 1, k)]


def mirror_cols(rows):
    """Half rows (CB first) -> whole rows: the right half mirrored, joined at CB."""
    return [np.r_[(r[1:] * MIR)[::-1], r] for r in rows]


Nst = N + 0.002 * nN
under_rows = lerp_rows(Nst, Rl, 6) + lerp_rows(Rl, N2, 6)[1:] + lerp_rows(N2, E, 5)[1:]
k_roll = 5  # the roll line's row
Vu, Fu, Iu = grid_mesh(mirror_cols(under_rows))
nr = len(under_rows)
# the top collar: the under collar with its fall 2 mm further out (the turn of cloth over the under collar)
Vtop = Vu + 0.002 * grad(Vu) * (np.repeat(np.arange(nr), Iu.shape[1]) > k_roll)[:, None]

# the pad's own piece (left)
Vp_, Fp_, _, _ = measure.marching_cubes(PADF, 0.0, spacing=(h, h, h))
Vp_ = Vp_ + np.array([xs[0], ys[0], zs[0]])
Fp_ = Fp_[:, [0, 2, 1]]
Vp_, Fp_ = largest(Vp_, Fp_[Vp_[Fp_].mean(1)[:, 0] > 0]) if (Vp_[:, 0] > 0).any() else (Vp_, Fp_)
info["pad"]["piece_bbox_mm"] = np.round((Vp_.max(0) - Vp_.min(0)) * 1000, 1).tolist()
log(f"pad piece {info['pad']}")
np.savez(os.path.join(out, "toile.npz"), Vpad=Vp_, Fpad=Fp_, **CONE.save(), V=Vh, F=Fh, Vl=Vl, Vl0=Vl0, Fl=Fl, Vu=Vu, Fu=Fu, Vtop=Vtop, Iu=Iu, k_roll=k_roll,
         CAX=CAX, RAX=RAX, tax=tax, ca=ca, na=na, sh=sh, A=A, alen=alen, yc=yc, z_brk=z_brk, z_top=z_top, hem=HEM,
         roll_z=np.linspace(z_brk, z_top, 80), roll_x=x_roll(np.linspace(z_brk, z_top, 80)), lap=LAP)
json.dump(info, open(os.path.join(out, "toile.json"), "w"), indent=1)

# ---------- render: the toile (left half + its mirror), lapels and collar, beside the reference
skin = lambda F: np.tile([[200, 170, 150]], (len(F), 1))
col = lambda F, c: np.tile([c], (len(F), 1))
Vm, Fm = Vh * MIR, Fh[:, ::-1]
Vlm, Flm = Vl * MIR, Fl[:, ::-1]
M3 = [(BV, BT, skin(BT)), (Vh, Fh, col(Fh, [150, 160, 185])), (Vm, Fm, col(Fm, [150, 160, 185])),
      (Vl, Fl, col(Fl, [120, 135, 170])), (Vlm, Flm, col(Flm, [120, 135, 170])), (Vu, Fu, col(Fu, [110, 120, 150]))]
MP = [(BV, BT, skin(BT)), (Vp_, Fp_, col(Fp_, [230, 200, 90]))]
box = ((-0.62, 0.62), (0.80, 1.72))
tiles = [render(M3, view=v, box=box) for v in ("front", "left", "back", "right")]
sheet(tiles, ref, labels=["reference", "front", "left", "back", "right"]).save(os.path.join(out, "toile_sheet.png"))
box2 = ((-0.30, 0.30), (1.15, 1.65))
tiles = [render(M3, view=v, box=box2, mpp=0.0016) for v in ("front", "left", "back")]
sheet(tiles, labels=["front", "left", "back"]).save(os.path.join(out, "collar_sheet.png"))
tiles = [render(MP, view=v, box=box2, mpp=0.0016) for v in ("front", "left", "back")]
sheet(tiles, labels=["pad front", "pad left", "pad back"]).save(os.path.join(out, "pad_sheet.png"))
log("wrote " + out)
