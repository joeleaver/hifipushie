"""mk.py <head tag> [shots=0] [sets=A,B,..]: one known GNM-native head of the solvecams benchmark (common.HEADS): the
truth model sc_<h>_T, its nine pictures through KNOWN cameras (common.VIEWS: nominal yaw / pitch / lens, each jittered
by a seeded +-2 deg yaw, +-2 pitch, +-1.5 roll, +-40 px off centre, turned views shifted so the whole skull is in the frame: the jittered camera IS the truth), then per set its
truth model sc_<h>_<set>T (true cameras) and its block-in start sc_<h>_<set>00 (block_in_start on the pictures alone:
class mean, detector points, 8 clicks +-2 px on the 72 / 90 views, cameras refit)."""
import copy, json, os, sys
import numpy as np
import stage
from hifipushie import blockin as bi, face_ruler as fr, gnm_mm, humanfit, resources, store
import common as C

tag = sys.argv[1]
kw = dict(a.split("=", 1) for a in sys.argv[2:])
sex, seed, sd, moves = C.HEADS[tag]
T = f"sc_{tag}_T"
rng = np.random.default_rng(1000 + seed)
if not (store.HOME / T / "spec.json").exists():
    bi.start(T, [], sex=sex, age=35, replace=True)
    sp = store.load(T)
    c = bi.identity(sp) + sd * np.random.default_rng(seed).standard_normal(170)
    for x in [x for x in moves.split(",") if x]:
        c = c + gnm_mm.direction(x.split(":")[0]) * float(x.split(":")[1])
    bi.set_identity(sp, c)
    (store.HOME / T / "spec.json").write_text(json.dumps(sp))
sp = store.load(T)
L = np.asarray(humanfit.state(sp["base"])["L"], float)
ctr = L[:68].mean(0)
w, h = C.SIZE
cams, views = [], []
CL = {"nose_tip": 30, "nose_base": 33, "nose_bridge": 27, "lip_upper": 51, "lip_lower": 57, "chin": 8, "eye_outer.L": 45, "mouth_corner.L": 54}
for vn, (yaw, pitch, lens) in C.VIEWS.items():
    j = rng.uniform(-1, 1, 5)
    f = lens / 36.0 * w
    z = f / C.PXM
    cam = {"r": [0.0, 0.0, float(np.radians(1.5 * j[2]))], "t": [float(40 * j[3] * z / f - 0.075 * np.sin(np.radians(yaw))), float((40 * j[4] - 60) * z / f), float(z)], "f": float(f),
           "size": [w, h], "centre": ctr.tolist(), "yaw": float(-(yaw + 2 * j[0]))}
    cam = fr.cam_moved(cam, pitch=pitch + 2 * j[1])
    cam["r"] = [float(x) for x in cam["r"]]
    cams.append(cam)
    fn = f"{C.S}/synth/sc_{tag}_{vn}.png"
    if not os.path.exists(fn):
        lt = copy.deepcopy(stage.FRONT_LIGHT)
        with resources.heavy(f"solvecams reference {T} {vn}", gb=6):
            im = stage.shoot(T, [stage.fitted_frame(cam, [w / 2 - h / 2, 0.0, w / 2 + h / 2, float(h)], vn)], lt, size=int(h), hair_on=False)[vn]
        x0 = int(round((h - w) / 2))
        im.convert("RGB").crop((x0, 0, x0 + w, h)).save(fn)
        print("shot", fn, "turn", round(abs(fr.view_yaw(cam)), 2), flush=True)
    pts = {}
    if yaw >= 70:
        P = humanfit.project(cam, L[list(CL.values())]) + 2.0 * rng.standard_normal((len(CL), 2))
        pts = {k: [round(float(p[0]), 1), round(float(p[1]), 1)] for k, p in zip(CL, P)}
    views.append({"image": fn, "size": [w, h], "yaw": (yaw if yaw < 70 else -yaw), "points": pts, "name": vn})
views = bi.with_anchor_points(views)
rj = {"views": views, "cameras": cams, "blockin": {"root": T, "attach": "native", "truth": {"head": C.HEADS[tag]}}}
C.write_refs(T, rj)
for s in (kw.get("sets") or ",".join(C.SETS)).split(","):
    ii = [list(C.VIEWS).index(v) for v in C.SETS[s]]
    ST = f"sc_{tag}_{s}T"
    store._dir(ST).mkdir(parents=True, exist_ok=True)
    (store.HOME / ST / "spec.json").write_text(json.dumps(sp))
    C.write_refs(ST, {"views": [views[i] for i in ii], "cameras": [cams[i] for i in ii],
                      "blockin": {"root": ST, "attach": "native", "placement": list(bi._placement(sp["base"]))}})
    S0 = f"sc_{tag}_{s}00"
    if not (store.HOME / S0 / "spec.json").exists():
        e = bi.start(S0, [copy.deepcopy(views[i]) for i in ii], sex=sex, age=35, cameras="refit", replace=True)
        r0 = C.refs(S0)
        L0 = C.landmarks(S0)
        print(f"start {S0}: {e['start']['cameras']}")
        for i, cam in zip(ii, r0["cameras"]):
            print(f"   {list(C.VIEWS)[i]:4s} " + C.cam_text(C.cam_err(cam, cams[i], L[:68])), flush=True)
print("done", tag)
