"""register.py <pose> [n=<cameras>]: the scan's frame against the RIG's. HSRD's exported scan is NOT in the frame of the
photos' .xmp calibration (found by laying the scan on the photos: turned ~30 deg about the vertical and moved), so the
rigid transform T (scan -> rig) is measured here:
  1. first guess: the detector's landmarks on the head cameras' photos, triangulated through the calibration (DLT,
     undistorted), laid on the same landmarks marked on the scan (align0.py);
  2. refined on SILHOUETTES: the dataset's own foreground masks of the head cameras all round (each undistorted and
     turned onto the head: hsrd.head_view), against the scan's silhouette through the same camera; 2D point-to-line
     Gauss-Newton on T's six freedoms (the scan's cut edge at the shoulders left out).
-> work/<pose>/T_rig.json {"s": 1, "R", "t", "rms_px", "rms_mm"} and out/register_<pose>.png (photo | scan through
the camera | blend: LOOK)."""
import json
import sys
import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.spatial import cKDTree
import gt, hsrd, rast, draw
from hifipushie import likeness

Image.MAX_IMAGE_PIXELS = None
pose = sys.argv[1]
kw = dict(a.split("=") for a in sys.argv[2:])
scan = gt.load_scan(pose)
Lm = np.asarray(json.loads((gt.WORK / pose / "S0.json").read_text())["landmarks_scan"])
C = hsrd.cams(pose)
names = sorted(C)
sizes = {}
for n in names:
    with Image.open(C[n]["image"]) as im:
        sizes[n] = im.size


def undist(cam, size, P):
    """photo pixels -> normalised pinhole coordinates (the radial distortion inverted by fixed-point steps)."""
    m = max(size)
    f = cam["f35"] / 36.0 * m
    xd = np.c_[(P[:, 0] - size[0] / 2 - cam["ppu"] * m) / f, (P[:, 1] - size[1] / 2 - cam["ppv"] * m) / f]
    x = xd.copy()
    for _ in range(8):
        r2 = (x ** 2).sum(1, keepdims=True)
        x = xd / (1 + cam["k"][0] * r2 + cam["k"][1] * r2 ** 2 + cam["k"][2] * r2 ** 3)
    return x


# ---- 1. landmarks triangulated ----------------------------------------------------------------------------------------
cache = gt.WORK / pose / "rig_landmarks.json"
if cache.exists():
    det = {k: np.asarray(v) for k, v in json.loads(cache.read_text()).items()}
else:
    det = {}
    for tele in (True, False):          # the head cameras (the long setting) first; the others when those are few
        for n in names:
            if (C[n]["f35"] >= 120) != tele or n in det:
                continue
            im = Image.open(C[n]["image"]).convert("RGB")
            k = 1280 / max(im.size)
            P = likeness.detect([im.resize((int(im.width * k), int(im.height * k)), Image.LANCZOS)])[0]
            if P is not None:
                det[n] = np.asarray(P)[likeness.MP68][:, :2] / k
        if len(det) >= 8:
            break
    cache.write_text(json.dumps({k: v.tolist() for k, v in det.items()}))
print(f"{pose}: the detector found a face in {len(det)} head-camera photos: {sorted(det)}")
use = list(range(17, 68))


def triangulate(sel):
    X = []
    for i in use:
        A = []
        for n in sel:
            x = undist(C[n], sizes[n], det[n][[i]])[0]
            R, c0 = C[n]["R"], C[n]["C"]
            A.append(x[0] * R[2] - R[0])
            A.append(x[1] * R[2] - R[1])
        A = np.asarray(A)
        b = np.array([a @ C[sel[j // 2]]["C"] for j, a in enumerate(A)])
        X.append(np.linalg.lstsq(A, b, rcond=None)[0])
    return np.asarray(X)


# a robust choice of views (a detection may be of ANOTHER face: a bystander behind the subject, a poster): every PAIR
# of views triangulates the points; the pair that most other views agree with (median reprojection under TOL) wins,
# then all its agreeing views triangulate together
allv = sorted(det)
TOL = 70.0          # px: the detector's own view-to-view disagreement is 1-6 mm = 10-60 px on a head camera
best = (0, None)
for i in range(len(allv)):
    for j in range(i + 1, len(allv)):
        if abs(np.dot(C[allv[i]]["R"][2], C[allv[j]]["R"][2])) > 0.995:
            continue                       # the two cameras look the same way: no depth
        Xp = triangulate([allv[i], allv[j]])
        e = {n: float(np.median(np.linalg.norm(hsrd.project(C[n], Xp, sizes[n])[0] - det[n][use], axis=1))) for n in allv}
        inl = [n for n in allv if e[n] < TOL]
        if len(inl) > best[0]:
            best = (len(inl), inl)
sel = best[1] or allv
for _ in range(2):
    X = triangulate(sel)
    err = {n: float(np.median(np.linalg.norm(hsrd.project(C[n], X, sizes[n])[0] - det[n][use], axis=1))) for n in allv}
    sel = [n for n in allv if err[n] < TOL] or sel
med = float(np.median([err[n] for n in sel]))
ok = np.isfinite(Lm[use]).all(1)
T = gt.umeyama(Lm[use][ok], X[ok], scale=False)
Ts = gt.umeyama(Lm[use][ok], X[ok], scale=True)
r0 = np.linalg.norm(gt.apply(T, Lm[use][ok]) - X[ok], axis=1) * 1000
print(f"  triangulated from {len(sel)} views (median reprojection {med:.1f} px); first T: landmark residual {r0.mean():.1f} mm; free scale {Ts[0]:.4f}")

# ---- 2. silhouettes ---------------------------------------------------------------------------------------------------
ctr_rig = X[[19, 28, 31, 37]].mean(0)       # ~ between eyes and mouth (indices into `use`: 36, 45, 48, 54)
cand = [n for n in names if C[n]["f35"] > 120]
if len(cand) < 12:          # a shoot without the long setting: every camera that holds the head
    cand = list(names)
PPM, SIZE = 1500.0, (640, 800)
views = []
for n in cand:
    c = C[n]
    p, z = hsrd.project(c, ctr_rig[None], sizes[n])
    if not (0.1 * sizes[n][0] < p[0, 0] < 0.9 * sizes[n][0] and 0.1 * sizes[n][1] < p[0, 1] < 0.9 * sizes[n][1] and z[0] > 0):
        continue
    mk = hsrd.mask_path(c["image"])
    if mk is None:
        continue
    hv = hsrd.head_view(c, sizes[n], ctr_rig + np.array([0, 0, -0.03]), out_size=SIZE, px_per_m=PPM)
    m = np.asarray(Image.open(mk).convert("L"))
    mm, inside = hsrd.resample(np.repeat(m[..., None], 3, 2), hv["map"])
    views.append({"name": n, "hv": hv, "mask": mm[..., 0] > 127, "inside": inside, "cam": hsrd.pipeline_cam(hv, (1.0, np.eye(3), np.zeros(3)))})
if kw.get("n"):
    views = views[::max(1, len(views) // int(kw["n"]))]
if len(views) > 28:
    views = views[::int(np.ceil(len(views) / 28))]
if not views:
    raise SystemExit(f"{pose}: no head camera holds the triangulated head: the first guess is wrong (detections: {sorted(det)}, used {sel})")
print(f"  {len(views)} head cameras for the silhouettes; mask foreground share {np.mean([v['mask'].mean() for v in views]):.2f}")
V, F = scan["V"], scan["F"]
zcut = V[:, 2].max() - 0.33                    # the scan's lower part (shoulders, the cut) makes no silhouette here
from hifipushie import humanfit


def contour(mask):
    er = ndimage.binary_erosion(mask, iterations=1, border_value=1)
    return mask & ~er


for v in views:
    cm = contour(v["mask"]) & ndimage.binary_erosion(v["inside"], iterations=6)
    ys, xs = np.nonzero(cm)
    v["cpts"] = np.c_[xs + 0.5, ys + 0.5]
    v["tree"] = cKDTree(v["cpts"])
    g = ndimage.gaussian_filter(v["mask"].astype(float), 2.0)
    v["grad"] = np.stack([ndimage.sobel(g, 1), ndimage.sobel(g, 0)], -1)


def residuals(T, want_J=True):
    Vr = gt.apply(T, V)
    o = gt.apply(T, np.nanmean(Lm[use][ok], 0))
    R, Jm, npts = [], [], 0
    for v in views:
        cam = v["cam"]
        vis = rast.visibility(Vr, F, cam)
        m = vis["fid"] >= 0
        cm = contour(m)
        ys, xs = np.nonzero(cm)
        z = vis["z"][ys, xs]
        Rc = humanfit._cam_rot(cam)
        w, h = cam["size"]
        xc = np.c_[(xs + 0.5 - w / 2) * z / cam["f"], (ys + 0.5 - h / 2) * z / cam["f"], z]
        Xw = (xc - np.asarray(cam["t"])) @ Rc
        Xs = gt.apply(gt.inverse(T), Xw)
        keep = Xs[:, 2] > zcut
        d, j = v["tree"].query(np.c_[xs + 0.5, ys + 0.5])
        keep &= d < 40
        q = v["cpts"][j]
        gr = v["grad"][np.clip(q[:, 1].astype(int), 0, h - 1), np.clip(q[:, 0].astype(int), 0, w - 1)]
        gn = np.linalg.norm(gr, axis=1)
        keep &= gn > 1e-3
        nn = gr / np.maximum(gn, 1e-9)[:, None]
        r = ((np.c_[xs + 0.5, ys + 0.5] - q) * nn).sum(1)
        keep &= np.abs(r) < 40
        r, nn, xc, Xw = r[keep], nn[keep], xc[keep], Xw[keep]
        # d pixel / d world point
        f = cam["f"]
        Jpx = np.zeros((len(r), 2, 3))
        Jpx[:, 0, 0], Jpx[:, 0, 2] = f / xc[:, 2], -f * xc[:, 0] / xc[:, 2] ** 2
        Jpx[:, 1, 1], Jpx[:, 1, 2] = f / xc[:, 2], -f * xc[:, 1] / xc[:, 2] ** 2
        Jw = np.einsum("nij,jk->nik", Jpx, Rc)                        # (n, 2, 3) wrt world
        g = np.einsum("ni,nik->nk", nn, Jw)                           # (n, 3)
        p = Xw - o
        Jm.append(np.c_[np.cross(p, g), g])                           # d r / d (omega, tau)
        R.append(r)
        v["last"] = (m, float(np.sqrt((r ** 2).mean())) if len(r) else np.nan, len(r))
    return np.concatenate(R), np.vstack(Jm), o


for it in range(12):
    r, J, o = residuals(T)
    w = np.where(np.abs(r) < 6, 1.0, 6 / np.maximum(np.abs(r), 1e-9))
    dx = -np.linalg.solve((J * w[:, None]).T @ J + 1e-9 * np.eye(6), (J * w[:, None]).T @ r)
    Rd = gt.rotvec(dx[:3])
    T = gt.compose((1.0, Rd, o - Rd @ o + dx[3:]), T)
    print(f"  {it:2d} silhouette rms {np.sqrt((r ** 2).mean()):.2f} px ({np.sqrt((r ** 2).mean()) / PPM * 1000:.2f} mm), median |r| {np.median(np.abs(r)):.2f} px, {len(r)} points; step {np.degrees(np.linalg.norm(dx[:3])):.3f} deg {np.linalg.norm(dx[3:]) * 1000:.2f} mm")
    if np.linalg.norm(dx[3:]) < 2e-5 and np.linalg.norm(dx[:3]) < 2e-5:
        break
r, J, o = residuals(T)
rms = float(np.sqrt((r ** 2).mean()))
ang = np.degrees(np.arctan2(T[1][1, 0], T[1][0, 0]))
gt.save_sim(gt.WORK / pose / "T_rig.json", T, rms_px=rms, rms_mm=rms / PPM * 1000, median_px=float(np.median(np.abs(r))), views=[v["name"] for v in views],
            landmark_first_mm=float(r0.mean()), free_scale_landmarks=float(Ts[0]))
print(f"  T: turned {ang:.2f} deg about the vertical (tilt {np.degrees(np.arccos(np.clip(T[1][2, 2], -1, 1))):.2f} deg), moved {np.round(T[2], 4)}; silhouette rms {rms:.2f} px = {rms / PPM * 1000:.2f} mm")
# the look
rows = []
pick = sorted(views, key=lambda v: v["name"])[:: max(1, len(views) // 6)][:6]
Vr = gt.apply(T, V)
for v in pick:
    im = Image.open(C[v["name"]]["image"]).convert("RGB")
    pic, _ = hsrd.resample(np.asarray(im), v["hv"]["map"])
    cl = np.asarray(draw.clay(Vr, F, v["cam"], ss=1))
    edge = contour(rast.visibility(Vr, F, v["cam"])["fid"] >= 0)
    ov = pic.copy()
    ov[ndimage.binary_dilation(edge)] = (0, 255, 0)
    rows.append(draw.label(draw.hstack([Image.fromarray(pic), Image.fromarray(cl), Image.fromarray(ov)]), f"{v['name']}: photo | scan through the rig camera | the scan's outline on the photo", sz=22))
draw.vstack([draw.hstack(rows[:3]), draw.hstack(rows[3:])] if len(rows) > 3 else rows).save(gt.OUT / f"register_{pose}.png")
print(gt.OUT / f"register_{pose}.png")
