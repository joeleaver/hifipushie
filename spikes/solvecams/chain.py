"""chain.py <start model> <prefix> <n calls> truth=<truth model> [key=value ..]: blockin.solve_step calls in a row on a
solvecams benchmark set, every call scored against the truth (cameras: common.cam_err; shape: chinread's errmap after
a similarity). Records -> /mnt/data/hifipushie/solvecams/out/<prefix>.json (+ a log on stdout). Keys:
  cameras=free|trust|refit (every call), first=<the first call's> (default = cameras; block_in_start's own flag makes a
    first "free" a "refit" as in the tool)
  dense=1                 the dense-landmark read on
  start=true              the start's cameras replaced by the TRUE ones (then pert), not laid on the head again
  pert=<view>:<yaw|pitch|dist>:<deg>,..   true-camera start moved: yaw = the head's turn changed by deg (- = toward the
                          front), pitch = nodded by deg, dist = the camera that many % further away with the lens to
                          match; the head's centre stays where it is in the picture
  freeze=all|rot          camera freedoms off: all six, or yaw and pitch only (shift / scale / roll as `cameras`)
  anything else           -> solve_step (anchors=none ..)"""
import copy, json, sys, time
import numpy as np
from hifipushie import blockin as bi, face_ruler as fr, store
import common as C
import errmap

src, pre, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
kw = dict(a.split("=", 1) for a in sys.argv[4:])
truth = kw.pop("truth")
cams_mode = kw.pop("cameras", "free")
first = kw.pop("first", cams_mode)
dense = kw.pop("dense", "0") == "1"
start, pert, freeze = kw.pop("start", ""), kw.pop("pert", ""), kw.pop("freeze", "")
kw_refit = kw.pop("refit", "0") == "1"      # the start's cameras fitted again by blockin.fit_cameras (today's code), as block_in_start would
extra = {a: (b if a in ("anchors", "parse") else (None if b == "none" else float(b))) for a, b in kw.items()}
fr.DENSE = dense
if freeze == "all":
    fr.PHOTO_CAM_SD6 = {k: (1e-4,) * 6 for k in fr.PHOTO_CAM_SD6}
elif freeze == "rot":
    fr.PHOTO_CAM_SD6 = {k: tuple(v[:4]) + (1e-4, 1e-4) for k, v in fr.PHOTO_CAM_SD6.items()}
if hasattr(fr, "PHOTO_CAM_SD7") and freeze:
    fr.PHOTO_CAM_SD7 = {k: ((1e-4,) * 7 if freeze == "all" else tuple(v[:4]) + (1e-4, 1e-4, 1e-4)) for k, v in fr.PHOTO_CAM_SD7.items()}
ct = bi.identity(store.load(truth))
rt = C.refs(truth)
Lt = C.landmarks(truth)
names = [v["name"] for v in rt["views"]]
MEAS = ("jaw_width", "gonial_width", "chin_width", "cheekbone_width", "chin_length", "chin_forward", "eyes_forward", "mouth_width")


def score(m):
    c = bi.identity(store.load(m))
    r = errmap.rms(c, ct)
    a, b = errmap.measures(c, r["scale"]), errmap.measures(ct)
    rj = C.refs(m)
    return {"model": m, "size": 100 * (1 / r["scale"] - 1), **{k: r[k] for k in ("face", "low", "chin", "jaw body", "jaw angle", "cheeks")},
            "meas": {k: a[k] - b[k] for k in MEAS}, "dct": float(np.linalg.norm(c - ct)), "c": float(np.linalg.norm(c)), "cmax": float(np.abs(c).max()),
            "cams": {nm: C.cam_err(cam, tc, Lt) for nm, cam, tc in zip(names, rj["cameras"], rt["cameras"])}}


def show(s):
    print(f"   SHAPE size {s['size']:+.1f} % face {s['face']:.2f} low {s['low']:.2f} chin {s['chin']:.2f} jaw body {s['jaw body']:.2f} jaw angle {s['jaw angle']:.2f} cheeks {s['cheeks']:.2f} mm | "
          + " ".join(f"{k} {v:+.1f}" for k, v in s["meas"].items()) + f" | |c-ct| {s['dct']:.2f} |c| {s['c']:.2f} max {s['cmax']:.2f}")
    for nm, e in s["cams"].items():
        print(f"   CAM {nm:4s} turn {e['view_yaw']:5.1f} " + C.cam_text(e))
    sys.stdout.flush()


refit = kw_refit
if start == "true" or pert or refit:
    m0 = f"{pre}00"
    bi.fork(src, m0, replace=True)
    rj = C.refs(m0)
    cams = copy.deepcopy(rt["cameras"]) if start == "true" else rj["cameras"]
    if refit:
        cams = bi.fit_cameras(store.load(m0)["base"], rj["views"])
        rj["blockin"]["cam_carried"] = True
    for p in [p for p in pert.split(",") if p]:
        vn, what, deg = p.split(":")
        i = names.index(vn)
        if what == "yaw":
            c1 = fr.cam_moved(cams[i], yaw=float(deg))
            if abs(abs(fr.view_yaw(c1)) - abs(fr.view_yaw(cams[i])) - float(deg)) > 0.5:
                c1 = fr.cam_moved(cams[i], yaw=-float(deg))
        elif what == "dist":      # the camera deg % further away with the lens to match: the same picture scale at the head's centre
            k_ = 1 + 0.01 * float(deg)
            c1 = {**cams[i], "t": [cams[i]["t"][0], cams[i]["t"][1], cams[i]["t"][2] * k_], "f": cams[i]["f"] * k_}
        else:
            c1 = fr.cam_moved(cams[i], pitch=float(deg))
        cams[i] = {k: (np.asarray(v).tolist() if hasattr(v, "tolist") or isinstance(v, (list, tuple)) else v) for k, v in c1.items()}
    rj["cameras"] = cams
    if start == "true":
        rj["blockin"].pop("cam_carried", None)
    rj["blockin"]["root"] = rj["blockin"].get("root") or src
    C.write_refs(m0, rj)
    src = m0
print(f"== {src} -> {pre}NN x{n}: cameras {first} / {cams_mode} dense {dense} start {start!r} pert {pert!r} freeze {freeze!r} {extra}")
rec = {"args": sys.argv[1:], "calls": [score(src)]}
show(rec["calls"][0])
for i in range(1, n + 1):
    out = f"{pre}{i:02d}"
    t = time.time()
    rep = bi.solve_step(src, out=out, cameras=first if i == 1 else cams_mode, dense=dense, **extra)
    so = rep["solve"]
    s = score(out)
    s.update(n=so["n"], dc=so["dc"], relax=so["relax"], damped=so.get("damped", 1), sig_scale=so["sig_scale"], kinds=so["kinds"],
             cam_done=so["cameras"], held=so.get("held"), camera_lines=so.get("camera_lines"), notes=[x for x in so.get("notes") or [] if x[:4] in ("VIEW", "INCO", "NOIS", "DISA", "AT T")], bound=so.get("bound"), disagree=so.get("disagree"),
             report=(so.get("report") or {}).get("text", ""), seconds=time.time() - t)
    rec["calls"].append(s)
    print(f"-- {out} ({time.time() - t:.0f} s): reads {so['n']}; |dc| {so['dc']:.2f}; relax x{so['relax']:.2f}{' DAMPED' if so.get('damped', 1) < 1 else ''}; adapt {so['sig_scale']}")
    print(f"   cam_done {so['cameras']}")
    for x in s["notes"] + (s.get("camera_lines") or []):
        print("   " + x[:400])
    show(s)
    src = out
    json.dump(rec, open(f"{C.S}/out/{pre}.json", "w"))
