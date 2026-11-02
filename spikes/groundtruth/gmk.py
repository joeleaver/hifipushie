"""gmk.py <tag> [fit=p1b3]: the PIPELINE benchmark's pictures and models for one scan (as spikes/solvecams/mk.py does
for a known GNM head, here for a REAL head whose surface is known):
  gt_<k>_T        the "truth" model: a GNM-native block-in start whose identity is the Part 1 DIRECT FIT (the ceiling: the
                  best GNM can do for this head), with every view and its TRUE camera (human_refs.json)
  pictures        lps: the textured scan drawn by us (rast.py: two lights, plain backdrop) through known cameras
                  f / q23 / q45 / s72 / s90 / fu (the benchmark's jitter); hsrd: the rig's REAL photos, each camera's
                  head view (hsrd.head_view: undistorted, turned onto the head, 3500 px / m, 1152 x 1536) with its
                  calibrated camera carried into the model's world (register.py's T, the Part 1 similarity)
  gt_<k>_<set>T / gt_<k>_<set>00   per set (A = f q45 s90, B = f q23 s72, P = fu q45 s90): the truth with the set's
                  views, and block_in_start on the pictures alone (class mean, cameras fitted, 8 clicks on 72 / 90 views)
k = lps | h40 | h112 (short names: the models live in the workspace). Pictures -> $HIFIPUSHIE_GROUNDTRUTH/pics/."""
import copy
import json
import sys
import numpy as np
from PIL import Image
import gt, rast, hsrd
from hifipushie import blockin as bi, face_ruler as fr, humanfit, store

Image.MAX_IMAGE_PIXELS = None
SHORT = {"lps": "lps", "HSR0040-Body-023": "h40", "HSR0112-Body-018": "h112", "HSR0042-Body-045": "h42"}
VIEWS = {"f": (0, 0, 85), "q23": (23, 0, 85), "q45": (45, 0, 85), "s72": (72, 0, 85), "s90": (90, 0, 85), "fu": (0, 8, 85)}
SETS = {"A": ("f", "q45", "s90"), "B": ("f", "q23", "s72"), "P": ("fu", "q45", "s90")}
SIZE, PXM = (1152, 1536), 3500.0
CL = {"nose_tip": 30, "nose_base": 33, "nose_bridge": 27, "lip_upper": 51, "lip_lower": 57, "chin": 8, "eye_outer.L": 45, "mouth_corner.L": 54}
PICS = gt.ROOT / "pics"


def canon(cam, ctr):
    """A camera dict re-expressed with `centre` = ctr and its turn about the vertical in "yaw" (the pipeline's own
    decomposition R = rotvec(r) CAM0 Rz(yaw)): the same camera."""
    from scipy.spatial.transform import Rotation
    from scipy.optimize import minimize_scalar
    R = humanfit._cam_rot(cam)
    t = np.asarray(cam["t"], float) + R @ (np.asarray(ctr, float) - np.asarray(cam["centre"], float))

    def rv(y):
        a = np.radians(y)
        Rz = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
        return Rotation.from_matrix(R @ (humanfit._CAM0 @ Rz).T).as_rotvec()
    ys = np.linspace(-180, 180, 73)
    y0 = ys[np.argmin([np.linalg.norm(rv(y)) for y in ys])]
    y = minimize_scalar(lambda y: np.linalg.norm(rv(y)), bounds=(y0 - 6, y0 + 6), method="bounded").x
    out = {"r": [float(x) for x in rv(y)], "t": [float(x) for x in t], "f": float(cam["f"]), "size": list(cam["size"]), "centre": [float(x) for x in ctr], "yaw": float(y)}
    assert np.allclose(humanfit._cam_rot(out), R, atol=1e-8)
    return out


if __name__ == "__main__":
    tag = sys.argv[1]
    kw = dict(a.split("=", 1) for a in sys.argv[2:])
    k = SHORT[tag]
    scan = gt.load_scan(tag)
    fj = json.loads((gt.WORK / tag / f"fit_{kw.get('fit', 'p1b3')}.json").read_text())
    cstar = np.asarray(fj["c"])
    S = (fj["S"]["s"], np.asarray(fj["S"]["R"]), np.asarray(fj["S"]["t"]))
    sex, age = scan["info"]["sex"], float(scan["info"].get("age", 35))
    T = f"gt_{k}_T"
    bi.start(T, [], sex=sex, age=age, replace=True)
    sp = store.load(T)
    bi.set_identity(sp, cstar)
    (store.HOME / T / "spec.json").write_text(json.dumps(sp))
    sp = store.load(T)
    L = np.asarray(humanfit.state(sp["base"])["L"], float)[:68]
    G = gt.gnm()
    M = gt.umeyama(G["WL"] @ gt.verts(cstar), L, scale=True)          # GNM world -> the model's world
    resid = np.linalg.norm(gt.apply(M, G["WL"] @ gt.verts(cstar)) - L, axis=1).max() * 1000
    print(f"{T}: GNM world -> model world: scale {M[0]:.4f}, landmark residual max {resid:.2f} mm")
    SM = gt.compose(M, S)                                             # scan -> model world
    ctr = L.mean(0)
    w, h = SIZE
    PICS.mkdir(exist_ok=True)
    rng = np.random.default_rng(4242 + sum(map(ord, k)))
    cams, views, names = [], [], []
    if tag == "lps":
        Vm = gt.apply(SM, scan["V"])
        tex = np.asarray(Image.open(gt.ROOT / scan["info"]["texture"]).convert("RGB"))
        for vn, (yaw, pitch, lens) in VIEWS.items():
            j = rng.uniform(-1, 1, 5)
            f = lens / 36.0 * w
            z = f / PXM
            cam = {"r": [0.0, 0.0, float(np.radians(1.5 * j[2]))], "t": [float(40 * j[3] * z / f - 0.075 * np.sin(np.radians(yaw))), float((40 * j[4] - 60) * z / f), float(z)],
                   "f": float(f), "size": [w, h], "centre": ctr.tolist(), "yaw": float(-(yaw + 2 * j[0]))}
            cam = fr.cam_moved(cam, pitch=pitch + 2 * j[1])
            cam["r"] = [float(x) for x in cam["r"]]
            fn = PICS / f"{k}_{vn}.png"
            vis = rast.visibility(Vm, scan["F"], cam, ss=2)
            im = rast.shade(vis, Vm, scan["F"], rast.texture_lookup(vis, scan["FUV"], tex), gamma=True, bg=(128, 130, 134),
                            lights=(((-0.50, -0.45, -0.74), 1.35), ((0.80, -0.10, -0.59), 0.55)), ambient=0.30)
            im.save(fn)
            cams.append(cam)
            names.append((vn, yaw, fn, None))
    else:
        Trig = gt.load_sim(gt.WORK / tag / "T_rig.json")              # scan -> rig
        RM = gt.compose(SM, gt.inverse(Trig))                         # rig -> model world
        C = hsrd.cams(tag)
        rig = json.loads((gt.WORK / tag / "rig.json").read_text())
        # which side is "+yaw" for the pipeline: the benchmark's camera at yaw +45, as an azimuth round the head
        c45 = rast.look_cam(ctr, yaw=45.0)
        pos = -humanfit._cam_rot(c45).T @ np.asarray(c45["t"]) + ctr - ctr
        side = float(np.sign(np.arctan2(pos[0], -pos[1])))             # model world: left = +X, forward = -Y
        ctr_rig = gt.apply(gt.inverse(RM), ctr[None])[0]
        chosen = {}
        box = ctr_rig + 0.095 * np.array([[a, b, c_] for a in (-1, 1) for b in (-1, 1) for c_ in (-1, 1)])
        upv = np.asarray(gt.inverse(RM)[1]) @ np.array([0.0, 0.0, 1.0])
        whole = {}
        for n in rig:               # the WHOLE head inside the photo, and most of the head view's frame too
            if C[n]["image"] is None:
                continue
            with Image.open(C[n]["image"]) as im_:
                sz = im_.size
            Pb, zb = hsrd.project(C[n], box, sz)
            ok_ = bool((zb > 0).all() and (Pb[:, 0] > 0).all() and (Pb[:, 0] < sz[0]).all() and (Pb[:, 1] > 0).all() and (Pb[:, 1] < sz[1]).all())
            if ok_:
                mp = hsrd.head_view(C[n], sz, ctr_rig, out_size=(115, 154), px_per_m=350.0, up=upv)["map"]
                ok_ = float(((mp[..., 0] >= 0) & (mp[..., 0] < sz[0]) & (mp[..., 1] >= 0) & (mp[..., 1] < sz[1])).mean()) > 0.8
            whole[n] = ok_
        for vn, (yaw, pitch, _) in VIEWS.items():
            best = None
            for n, r in rig.items():
                if not r["inside"] or not whole.get(n) or r["px_per_m"] < PXM or n in chosen.values():
                    continue
                cost = abs(r["az"] - side * yaw) + 1.5 * abs(r["el"] - (10.0 if pitch else 0.0))
                if best is None or cost < best[0]:
                    best = (cost, n)
            chosen[vn] = best[1]
        for a in [a for a in kw.get("cams", "").split(",") if a]:      # cams=f:A05,s90:B03: chosen by eye (the head whole in the photo)
            chosen[a.split(":")[0]] = a.split(":")[1]
        print("  rig cameras:", {v: (n, round(rig[n]["az"], 1), round(rig[n]["el"], 1), round(rig[n]["px_per_m"])) for v, n in chosen.items()}, "side", side)
        for vn, (yaw, pitch, _) in VIEWS.items():
            c = C[chosen[vn]]
            im = Image.open(c["image"]).convert("RGB")
            # the head a little above the picture's middle on turned views, as a portrait is framed
            tgt = ctr_rig + np.asarray(gt.inverse(RM)[1]) @ np.array([0.0, 0.075 * np.sin(np.radians(yaw)) * 0.6, 0.015]) / RM[0]
            hv = hsrd.head_view(c, im.size, tgt, out_size=SIZE, px_per_m=PXM, up=np.asarray(gt.inverse(RM)[1]) @ np.array([0.0, 0.0, 1.0]))
            pic, inside = hsrd.resample(np.asarray(im), hv["map"])
            fn = PICS / f"{k}_{vn}.png"
            Image.fromarray(pic).save(fn)
            cam = canon(hsrd.pipeline_cam(hv, RM), ctr)
            cams.append(cam)
            names.append((vn, yaw, fn, {"rig": chosen[vn], "az": rig[chosen[vn]]["az"], "el": rig[chosen[vn]]["el"], "dist_m": hv["dist"], "native_px_per_m": hv["native_px_per_m"],
                                         "lens_true_mm": cam["f"] / w * 36.0, "outside_px_share": float(1 - inside.mean())}))
    for (vn, yaw, fn, extra), cam in zip(names, cams):
        pts = {}
        ty = abs(fr.view_yaw(cam))
        if yaw >= 70:
            P = humanfit.project(cam, L[list(CL.values())]) + 2.0 * rng.standard_normal((len(CL), 2))
            pts = {kk: [round(float(p[0]), 1), round(float(p[1]), 1)] for kk, p in zip(CL, P)}
        nominal = yaw if extra is None else int(5 * round(ty / 5))       # a real photo's turn is told as a person would: to 5 deg
        views.append({"image": str(fn), "size": [w, h], "yaw": (nominal if nominal < 70 else -nominal), "points": pts, "name": vn, **({"truth": extra} if extra else {})})
        print(f"  {vn:4s} turn {ty:5.1f} pitch {fr.view_pitch(cam):+5.1f} dist {cam['t'][2]:.2f} m lens {cam['f'] / w * 36:.0f} mm  {extra or ''}")
    views = bi.with_anchor_points(views)
    for v in views:
        n = sum(1 for kk in v["points"] if kk.startswith("lm"))
        print(f"  {v['name']:4s} detector points {n}; clicks {len(v['points']) - n}")
    rj = {"views": views, "cameras": cams, "blockin": {"root": T, "attach": "native", "truth": {"scan": tag, "fit": fj["name"]}}}
    (store.HOME / T / "human_refs.json").write_text(json.dumps(rj))
    (gt.WORK / tag / "model_world.json").write_text(json.dumps({"M": {"s": M[0], "R": M[1].tolist(), "t": M[2].tolist()}}))
    for s, vs in SETS.items():
        ii = [list(VIEWS).index(v) for v in vs]
        ST = f"gt_{k}_{s}T"
        store._dir(ST).mkdir(parents=True, exist_ok=True)
        (store.HOME / ST / "spec.json").write_text(json.dumps(sp))
        (store.HOME / ST / "human_refs.json").write_text(json.dumps({"views": [views[i] for i in ii], "cameras": [cams[i] for i in ii],
                                                                     "blockin": {"root": ST, "attach": "native", "placement": list(bi._placement(sp["base"]))}}))
        for lens in ((False, True) if tag != "lps" else (False,)):
            S0 = f"gt_{k}_{s}{'L' if lens else ''}00"
            vv = [copy.deepcopy(views[i]) for i in ii]
            if lens:        # the variant that TELLS the pipeline each picture's lens (a head cropped out of a full-figure photo is a long lens)
                for v in vv:
                    v["lens_mm"] = round(v["truth"]["lens_true_mm"])
            e = bi.start(S0, vv, sex=sex, age=age, cameras="refit", replace=True)
            print(f"start {S0}: {e['start']['cameras']}")
    print("done", tag)
