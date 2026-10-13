"""hmk.py <pose> <short> [classes=pooled,white,..] : solve-ready models for one HSRD-100 pose (groundtruth's hsrdset set; the
held-out subjects are for SCORING only), as groundtruth's gmk.py makes them from its own work dirs:
  rm_<k>_T   truth: a GNM-native block-in start whose identity is the pose's Part 1 direct fit (fit.json "identity"),
             with set A's views (front / ~45 / ~90 deg) and their TRUE cameras (the rig's calibration, undistorted and
             turned onto the head: an exact pinhole picture, 3,500 px / m, 1152 x 1536)
  rm_<k>_L<c>00  block_in_start on those pictures, the lens TOLD on the diagonal (f / diag x 43.27), the start's identity =
             class <c> ("pooled" = the sex's pooled mean; a GNM class; "blend" = the simplex blend nearest the TRUE identity:
             an oracle, for measuring only)
Pictures -> /mnt/data/hifipushie/readmix/pics/<k>_<view>.png (never the repo). Models in main's workspace."""
import json, sys
from pathlib import Path
import numpy as np
from PIL import Image
G_ = "/home/joe/dev/hifipushie/.claude/worktrees/groundtruth/spikes/groundtruth"
sys.path.insert(0, G_)
import gt, hsrd, hsrdset as H
from gmk import canon, CL, SIZE, PXM
from hifipushie import blockin as bi, face_ruler as fr, humanfit, store

pose, k = sys.argv[1], sys.argv[2]
kw = dict(a.split("=", 1) for a in sys.argv[3:])
P = H.Pose(pose)
subj = H.index()["subjects"][pose.split("-")[0]]
sex, age = subj["sex"].lower(), float(subj["age"])
fj = P.fit()["identity"]
cstar = np.asarray(fj["c"])
S = (fj["S"]["s"], np.asarray(fj["S"]["R"]), np.asarray(fj["S"]["t"]))       # scan -> GNM world
Tj = P.cams["T_scan_to_rig"]
Trig = (1.0, np.asarray(Tj["R"]), np.asarray(Tj["t"]))                       # scan -> rig
T = f"rm_{k}_T"
bi.start(T, [], sex=sex, age=age, replace=True)
sp = store.load(T)
bi.set_identity(sp, cstar)
(store.HOME / T / "spec.json").write_text(json.dumps(sp))
sp = store.load(T)
L = np.asarray(humanfit.state(sp["base"])["L"], float)[:68]
Gm = gt.gnm()
M = gt.umeyama(Gm["WL"] @ gt.verts(cstar), L, scale=True)
RM = gt.compose(gt.compose(M, S), gt.inverse(Trig))                          # rig -> model world
ctr = L.mean(0)
ctr_rig = gt.apply(gt.inverse(RM), ctr[None])[0]
upv = np.asarray(gt.inverse(RM)[1]) @ np.array([0.0, 0.0, 1.0])
fwd_rig = np.asarray(gt.inverse(RM)[1]) @ np.array([0.0, -1.0, 0.0])
left_rig = np.asarray(gt.inverse(RM)[1]) @ np.array([1.0, 0.0, 0.0])
cams_ = P.cams["cameras"]


def az_of(c):        # where the camera stands round the MODEL's head: 0 = in front, + = its left (+X)
    d = np.asarray(c["C"]) - ctr_rig
    return float(np.degrees(np.arctan2(d @ left_rig, d @ fwd_rig))), float(np.degrees(np.arcsin((d @ upv) / np.linalg.norm(d))))


def head_view(c, target, out_size=SIZE, px_per_m=PXM, up=None):
    Rc, Cc = np.asarray(c["R"]), np.asarray(c["C"])
    z = target - Cc
    dist = float(np.linalg.norm(z))
    z = z / dist
    y = -(up - (up @ z) * z)
    y /= np.linalg.norm(y)
    x = np.cross(y, z)
    Rv = np.stack([x, y, z])
    f = px_per_m * dist
    w, h = out_size
    uu, vv = np.meshgrid(np.arange(w) + 0.5, np.arange(h) + 0.5)
    rays = np.stack([(uu - w / 2) / f, (vv - h / 2) / f, np.ones_like(uu)], -1) @ Rv
    rc = rays @ Rc.T
    xn = rc[..., :2] / rc[..., 2:3]
    r2 = (xn ** 2).sum(-1, keepdims=True)
    kk = c["k"]
    xd = xn * (1 + kk[0] * r2 + kk[1] * r2 ** 2 + kk[2] * r2 ** 3)
    mp = np.stack([c["f"] * xd[..., 0] + c["cx"], c["f"] * xd[..., 1] + c["cy"]], -1)
    return {"R": Rv, "C": Cc, "f": f, "size": [w, h], "dist": dist, "map": mp}


VIEWS = {"f": 0.0, "q45": 45.0, "s90": 90.0}
side = None
chosen = {}
for vn, yaw in VIEWS.items():
    best = None
    for n, c in cams_.items():
        a, e = az_of(c)
        if c["px_per_mm"] < 5.0 or abs(e) > 15 or n in chosen.values():
            continue
        sd = side if side is not None else (1.0 if a >= 0 else -1.0)
        cost = abs(abs(a) - yaw) + (0 if (yaw == 0 or np.sign(a) == sd) else 30) + 0.5 * abs(e)
        if best is None or cost < best[0]:
            best = (cost, n, a)
    chosen[vn] = best[1]
    if yaw and side is None:
        side = float(np.sign(best[2]))
print("cameras:", {v: (n, [round(x, 1) for x in az_of(cams_[n])]) for v, n in chosen.items()})
cams, views = [], []
rng = np.random.default_rng(4242 + sum(map(ord, k)))
for vn, yaw in VIEWS.items():
    c = cams_[chosen[vn]]
    im = np.asarray(P.image(chosen[vn]))
    tgt = ctr_rig + np.asarray(gt.inverse(RM)[1]) @ np.array([0.0, 0.075 * np.sin(np.radians(yaw)) * 0.6, 0.015]) / RM[0]
    hv = head_view(c, tgt, up=upv)
    pic, inside = hsrd.resample(im, hv["map"])
    fn = Path("/mnt/data/hifipushie/readmix/pics") / f"{k}_{vn}.png"
    Image.fromarray(pic).save(fn)
    cam = canon(hsrd.pipeline_cam(hv, RM), ctr)
    w, h = SIZE
    ty = abs(fr.view_yaw(cam))
    pts = {}
    if yaw >= 70:
        Pp = humanfit.project(cam, L[list(CL.values())]) + 2.0 * rng.standard_normal((len(CL), 2))
        pts = {kk: [round(float(p[0]), 1), round(float(p[1]), 1)] for kk, p in zip(CL, Pp)}
    nominal = int(5 * round(ty / 5))
    views.append({"image": str(fn), "size": [w, h], "yaw": (nominal if nominal < 70 else -nominal), "points": pts, "name": vn,
                  "truth": {"rig": chosen[vn], "dist_m": hv["dist"], "lens_diag_mm": round(cam["f"] / float(np.hypot(w, h)) * 43.27, 1),
                            "outside_px_share": float(1 - inside.mean())}})
    cams.append(cam)
    print(f"  {vn} {chosen[vn]} turn {ty:.1f} pitch {fr.view_pitch(cam):+.1f} dist {cam['t'][2]:.2f} m outside {100 * (1 - inside.mean()):.1f} %")
views = bi.with_anchor_points(views)
(store.HOME / T / "human_refs.json").write_text(json.dumps({"views": views, "cameras": cams, "blockin": {"root": T, "attach": "native", "truth": {"pose": pose}}}))
D = bi.data()
en = [str(x) for x in D["eth_names"]]
for cls in [c_ for c_ in kw.get("classes", "pooled").split(",") if c_]:
    vv = [dict(v, lens_mm=v["truth"]["lens_diag_mm"]) for v in views]
    S0 = f"rm_{k}_L{cls}00"
    if cls == "pooled":
        bi.start(S0, vv, sex=sex, age=age, cameras="refit", replace=True)
    elif cls == "blend":
        from scipy.optimize import minimize
        E = np.asarray(D["eth_means"][int(sex == "male")])
        w = minimize(lambda w: np.sum((E.T @ w - cstar) ** 2), np.ones(4) / 4, bounds=[(0, 1)] * 4,
                     constraints={"type": "eq", "fun": lambda w: w.sum() - 1}).x
        bl = {e: round(float(x), 3) for e, x in zip(en, w) if x > 1e-3}
        print("oracle blend", bl)
        bi.start(S0, vv, sex=sex, age=age, ethnicity=bl, cameras="refit", replace=True)
    else:
        bi.start(S0, vv, sex=sex, age=age, ethnicity=cls, cameras="refit", replace=True)
    print("start", S0)
