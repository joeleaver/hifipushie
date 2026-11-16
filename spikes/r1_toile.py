"""R1 step 4 (TOILE) + step 5 (MARK) of drape first (docs/proposals/drape_first.md) on the suit jacket's body + sleeves.

  HIFIPUSHIE_HOME=<ws> slot uv run python spikes/r1_toile.py <out> <loaded.pkl> <jacket.json> <d4 lines.json> <ref.png>

TOILE: an SDF offset of the body (not a direct mesh offset: an offset mesh folds through itself in every concave place,
the armpit, the spine groove, the crotch; the field offset rounds them and joins the sleeves to the body at the armhole
by itself). The body's signed distance on a 6 mm grid, CLOSED by 25 mm (dilate, then erode by the distance transform: a
jacket bridges hollows narrower than ~5 cm), minus an ease field e(x):
  torso: e = k(z) w(theta), theta round the vertical axis through the chest's centre, w = 0.35 + 0.65 cos^2(theta)
    (full front and back, 35 % under the arm: a jacket stands off the chest and hangs from the blades, the side body
    sits close under a high armhole); k(z) linear between the levels step 0 read (hem, hips, waist, chest), then
    12 mm at the shoulder and 6 mm at the neck; k at each level CALIBRATED (secant) so the toile's section, as a tape
    takes it (convex hull, sleeves out), measures step 0's garment girth = body + ease: the gate by construction.
  sleeves: e = 18 mm at the armhole -> 22 mm at the wrist (the s4-31 bicepsEase 0.36: 114 mm on 317 = 18 mm round),
    blended with the torso's across the armhole's plane (D4's armhole loop) over 4 cm.
Cut: hem = the grid floor at step 0's hem height; neck along D4's neckline (projected); the front opening along step 2's
traces (roll line from the gorge to the break, front edge from the break to the hem: the lapel left OFF, R2 turns it);
each sleeve square to the forearm at step 0's sleeve_hem height. Exact clips (new vertices on the cut edges).
MARK: D4's body lines moved out along the body normal onto the toile (Newton on the field), drawn on it.
Writes <out>/toile.npz (V, F, field grid), marks.json, girths.json, toile_sheet.png, marks_sheet.png."""
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
from r1_common import PAL, clip, largest, length, px_to_xz, render, resample, sheet  # noqa: E402

out, src, jpath, lpath, ref = sys.argv[1:6]
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
L = json.load(open(lpath))["lines"]
MIR = np.array([-1.0, 1, 1])


def pts(name):
    t = T[name]
    return np.asarray(t["pts"], float)


# ---------- the grid and the body's closed signed distance
h = 0.006
HEM = H0["hem"]["z_mm"] / 1000
xs = np.arange(-0.60, 0.60 + h / 2, h)
ys = np.arange(-0.24, 0.24 + h / 2, h)
zs = np.arange(HEM, 1.62 + h / 2, h)
G = np.stack(np.meshgrid(xs, ys, zs, indexing="ij"), -1).reshape(-1, 3)
sd = np.empty(len(G))
for i in range(0, len(G), 200000):
    sd[i:i + 200000] = CT.query(G[i:i + 200000])[0]
sd = sd.reshape(len(xs), len(ys), len(zs))
log(f"body sd on {sd.shape} grid; inside {np.mean(sd < 0):.3f}")
R = 0.025
dil = sd <= R
Din = ndimage.distance_transform_edt(dil) * h
sdc = np.where(dil, R - Din, sd)
sdc = ndimage.gaussian_filter(sdc, 1.0)
log("closed by 25 mm")

# ---------- arms: axis and the armhole plane
sh = pts("shoulderToWrist")[0]
wr = pts("wrist").mean(0)
A = wr - sh
alen = np.linalg.norm(A)
A /= alen
ah = np.asarray(L["armhole.L"]["pts"], float)
ca = ah.mean(0)
na = np.linalg.svd(ah - ca)[2][2]
na = na if na @ (sh - np.array([0, 0, sh[2]])) > 0 else -na
yc = float(pts("chest")[:, 1].mean())


def armness(P):
    """0 torso -> 1 sleeve (each side), with the side's sign of x."""
    P = np.atleast_2d(P)
    Q = P * np.where(P[:, :1] < 0, MIR, 1)  # folded to the left side
    s = (Q - ca) @ na
    t = np.clip((Q - sh) @ A, 0, alen)
    dax = np.linalg.norm(Q - (sh + t[:, None] * A), axis=1)
    a = np.clip(s / 0.04 + 0.5, 0, 1)
    a = a * a * (3 - 2 * a)
    near = np.clip((0.13 - dax) / 0.03, 0, 1)
    return a * near, t / alen


LV = [("hem", fit["hem"]["level_z_m"]), ("hips", fit["hips"]["level_z_m"]), ("waist", fit["waist"]["level_z_m"]),
      ("chest", fit["chest"]["level_z_m"])]
KZ = [HEM - 0.01] + [z for _, z in LV][1:] + [1.45, 1.53]
kv = {n: fit[n]["ease_mm"] / 1000 / (2 * np.pi * 0.6) for n, _ in LV}


def kz(z):
    vals = [kv["hem"], kv["hips"], kv["waist"], kv["chest"], 0.012, 0.006]
    return np.interp(z, KZ, vals)


def ease(P):
    th = np.arctan2(P[:, 0], -(P[:, 1] - yc))  # 0 at the front, pi at the back
    w = 0.35 + 0.65 * np.cos(th) ** 2
    et = kz(P[:, 2]) * w
    a, t = armness(P)
    ea = 0.018 + 0.004 * t
    return (1 - a) * et + a * ea


SDC = RegularGridInterpolator((xs, ys, zs), sdc, bounds_error=False, fill_value=1.0)


def section(z, field_ease=True, step=0.002):
    """The torso's section at height z as a tape takes it: convex hull of the zero contour, sleeve side out (mm)."""
    gx = np.arange(-0.30, 0.30, step)  # (hands hang beside the hem: out)
    gy = np.arange(-0.24, 0.24, step)
    P = np.stack(np.meshgrid(gx, gy, [z], indexing="ij"), -1).reshape(-1, 3)
    f = SDC(P) - (ease(P) if field_ease else 0)
    C = measure.find_contours(f.reshape(len(gx), len(gy)), 0)
    Q = np.concatenate([np.c_[np.interp(c[:, 0], np.arange(len(gx)), gx), np.interp(c[:, 1], np.arange(len(gy)), gy)]
                        for c in C])
    a, _ = armness(np.c_[Q, np.full(len(Q), z)])
    Q = Q[a < 0.5]
    hull = ConvexHull(Q)
    return hull.area * 1000, Q  # 2D: .area is the perimeter


girths = {}
for n, z in LV:
    tgt = fit[n]["garment_girth_mm"]
    zq = max(z, HEM + 0.004)
    k0 = kv[n]
    g0 = section(zq)[0]
    k1 = k0 * 1.15
    kv[n] = k1
    g1 = section(zq)[0]
    for _ in range(5):
        if abs(g1 - tgt) < 1.0:
            break
        k2 = k1 + (tgt - g1) * (k1 - k0) / (g1 - g0 if g1 != g0 else 1e-6)
        k0, g0, k1 = k1, g1, max(k2, 0.0)
        kv[n] = k1
        g1 = section(zq)[0]
    gb = section(zq, field_ease=False)[0]
    girths[n] = {"z": round(zq, 4), "body_tape_mm": fit[n]["body_girth_mm"], "body_hull_mm": round(gb, 1),
                 "ease_plan_mm": fit[n]["ease_mm"], "target_mm": tgt, "toile_mm": round(g1, 1),
                 "toile_minus_body_hull_mm": round(g1 - gb, 1), "k_front_mm": round(k1 * 1000, 1),
                 "k_side_mm": round(k1 * 350, 1)}
    log(f"{n}: {girths[n]}")

# ---------- the toile field, meshed
E = ease(G).reshape(sdc.shape)
Fd = ndimage.gaussian_filter(sdc - E, 0.8)
FD = RegularGridInterpolator((xs, ys, zs), Fd, bounds_error=False, fill_value=1.0)
V, F, _, _ = measure.marching_cubes(Fd, 0.0, spacing=(h, h, h))
V = V + np.array([xs[0], ys[0], zs[0]])
F = F[:, [0, 2, 1]]
V, F = largest(V, F)
log(f"meshed: {len(V)} v {len(F)} f")


z_sl = H0["sleeve_hem"]["z_mm"] / 1000
t_sl = (z_sl - sh[2]) / A[2]
p_sl = sh + t_sl * A


# ---------- marks: D4's lines out along the body normal onto the toile
def onto_toile(P, mode="normal"):
    """Out onto the toile along: the body normal (neck, shoulder, armhole); horizontally from the torso's axis (centre
    back, side seams: the body normal swings sideways in the seat's cleft); square out from the arm's axis (sleeves)."""
    P = np.asarray(P, float)
    if mode == "torso":
        n = P - np.c_[np.zeros(len(P)), np.full(len(P), yc), P[:, 2]]
        n[:, 0] = np.where(np.abs(n[:, 0]) < 1e-4, 0, n[:, 0])
    elif mode == "arm":
        Q = P * np.where(P[:, :1] < 0, MIR, 1)
        n = Q - (sh + ((Q - sh) @ A)[:, None] * A)
        n = n * np.where(P[:, :1] < 0, MIR, 1)
    else:
        _, n = CT.query(P)
    n = n / np.linalg.norm(n, axis=1, keepdims=True)
    t = np.zeros(len(P))
    for _ in range(8):
        f = FD(P + t[:, None] * n)
        df = (FD(P + (t + 1e-3)[:, None] * n) - f) / 1e-3
        t = t - f / np.where(np.abs(df) > 0.1, df, 1.0)
    return P + t[:, None] * n


def extended(k, P):
    """Lines that end on a boundary run past it (to the hem, past the wrist), so the cut reaches it."""
    P = np.asarray(P, float)
    if k.startswith(("centre_back", "front_side", "side_back")):
        P = P[P[:, 2] > HEM + 0.01]
        P = np.r_[P, [[P[-1, 0], P[-1, 1], HEM - 0.03]]] if P[0, 2] > P[-1, 2] else np.r_[[[P[0, 0], P[0, 1], HEM - 0.03]], P]
    if k.startswith("sleeve_"):
        e = 1 if np.linalg.norm(P[-1] - p_sl) < np.linalg.norm(P[0] - p_sl) else 0
        q = P[-1] if e else P[0]
        sg = MIR if q[0] < 0 else np.ones(3)
        q2 = q + 0.05 * A * sg
        P = np.r_[P, [q2]] if e else np.r_[[q2], P]
    return P


MODE = {"centre_back": "torso", "front_side": "torso", "side_back": "torso", "sleeve_fore": "arm", "sleeve_hind": "arm"}
marks = {k: onto_toile(resample(extended(k, v["pts"])), MODE.get(k.split(".")[0], "normal"))
         for k, v in L.items() if k != "centre_front"}

# ---------- cuts
# neck: keep below the projected neckline (z of the loop by angle round the neck)
nk = np.concatenate([np.asarray(L["neckline.L"]["pts"]), np.asarray(L["neckline.R"]["pts"])[::-1]])  # (the body line, by angle)
cn = nk[:, :2].mean(0)
an = np.arctan2(nk[:, 1] - cn[1], nk[:, 0] - cn[0])
o = np.argsort(an)
an_s, zn_s = an[o], nk[o, 2]


def phi_neck(P):
    a = np.arctan2(P[:, 1] - cn[1], P[:, 0] - cn[0])
    return np.interp(a, an_s, zn_s, period=2 * np.pi) - P[:, 2]


# front opening: roll line (gorge -> break) then front edge (break -> hem), both sides; front half only
def edge_x(side):
    r = np.array(tr[f"roll.{side}"]["points"], float)
    fe = np.array(tr[f"front_edge.{side}"]["points"], float)
    brk = fe[tr[f"front_edge.{side}"]["corners"][0]]
    P = np.concatenate([r[r[:, 1] < brk[1]], fe[fe[:, 1] >= brk[1]]])
    x, z = px_to_xz(P[:, 0], P[:, 1])
    o = np.argsort(z)
    return z[o], x[o]


zl, xl = edge_x("L")
zr, xr = edge_x("R")


def phi_front(P):
    x_l = np.interp(P[:, 2], zl, xl)
    x_r = np.interp(P[:, 2], zr, xr)
    return np.maximum.reduce([P[:, 0] - x_l, x_r - P[:, 0], P[:, 1] - (yc - 0.03)])


def phi_wrist(P):
    Q = P * np.where(P[:, :1] < 0, MIR, 1)
    plane = (Q - p_sl) @ A
    dline = np.linalg.norm(np.cross(Q - sh, A), axis=1)
    return np.maximum(-plane, dline - 0.10)


for nm, ph in [("neck", phi_neck), ("front", phi_front), ("wrist", phi_wrist)]:
    V, F = clip(V, F, ph(V))
    V, F = largest(V, F)
    log(f"cut {nm}: {len(V)} v")

# the marks trimmed to the toile (points within 8 mm of it, both sides of the opening)
from scipy.spatial import cKDTree  # noqa: E402

kd = cKDTree(V)
M2 = {}
for k, P in marks.items():
    dd, _ = kd.query(P)
    M2[k] = P[dd < 0.006]
# the hem and the front edges and the sleeve ends are the toile's own boundary
np.savez(os.path.join(out, "toile.npz"), V=V, F=F, ca=ca, na=na, sh=sh, A=A, alen=alen, yc=yc, p_sl=p_sl, hem=HEM)
json.dump({k: {"mm": round(length(P) * 1000, 1), "pts": np.round(P, 5).tolist()} for k, P in M2.items()},
          open(os.path.join(out, "marks.json"), "w"))
json.dump({"girths": girths, "k_levels_mm": {n: round(v * 1000, 1) for n, v in kv.items()},
           "sleeve_ease_mm": [18, 22], "closing_mm": 25, "grid_mm": 6, "hem_z": HEM, "sleeve_hem_z": z_sl,
           "toile_vertices": int(len(V)), "toile_faces": int(len(F))},
          open(os.path.join(out, "girths.json"), "w"), indent=1)

# ---------- renders: toile on the body beside the reference; marks on the toile
BV = np.asarray(body.V, float)
BT = np.asarray(body.T, int)
skin = np.tile([[200, 170, 150]], (len(BT), 1))
cloth = np.tile([[150, 160, 185]], (len(F), 1))
box = ((-0.62, 0.62), (0.80, 1.72))
tiles = [render([(BV, BT, skin), (V, F, cloth)], view=v, box=box) for v in ("front", "left", "back", "right")]
sheet(tiles, ref, labels=["reference", "front", "left", "back", "right"]).save(os.path.join(out, "toile_sheet.png"))
lines = [(P, PAL[i % len(PAL)], 3) for i, (k, P) in enumerate(sorted(M2.items())) if len(P) > 1]
tiles = [render([(BV, BT, skin), (V, F, cloth)], lines=lines, view=v, box=box) for v in ("front", "left", "back", "right")]
sheet(tiles, ref, labels=["reference", "front", "left", "back", "right"]).save(os.path.join(out, "marks_sheet.png"))
log("wrote " + out)
