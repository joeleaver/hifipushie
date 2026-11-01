"""gchain.py <start model> <prefix> <n calls> truth=<truth model> [key=value ..]: blockin.solve_step calls in a row
on a groundtruth set (gmk.py), every call scored against the truth model = the Part 1 DIRECT FIT's identity (cameras:
solvecams' cam_err against the TRUE cameras; shape: chinread's errmap after a similarity; the solvecams acceptance
measures jaw_width / gonial_width / chin_width). The scan itself is scored afterwards (gscore.py). solvecams/chain.py
with the records under $HIFIPUSHIE_GROUNDTRUTH/out/chains/<prefix>.json. Keys: cameras=free|trust|refit, dense=1,
start=true (the TRUE cameras as the start), pert=<view>:<yaw|pitch|dist>:<amount>,.. (the true start moved)."""
import copy, json, sys, time
import numpy as np
from hifipushie import blockin as bi, face_ruler as fr, store
import common as C
import errmap
import gt

src, pre, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
kw = dict(a.split("=", 1) for a in sys.argv[4:])
truth = kw.pop("truth")
cams_mode = kw.pop("cameras", "free")
first = kw.pop("first", cams_mode)
dense = kw.pop("dense", "0") == "1"
start, pert = kw.pop("start", ""), kw.pop("pert", "")
fr.DENSE = dense
if kw.pop("noiris", "0") == "1":        # a scan taken with the eyes SHUT (the Lee Perry-Smith head): the iris reads are of nothing
    fr.SIG["iris"] = 50.0
    fr.SIG_IRIS_3Q = 50.0
if kw.get("distsd"):                    # the dense solve's distance prior (%, face_ruler.PHOTO_CAM_DIST_DENSE: 40)
    fr.PHOTO_CAM_DIST_DENSE = float(kw.pop("distsd"))
expression = kw.pop("expression", None)
ct = bi.identity(store.load(truth))
rt = C.refs(truth)
Lt = C.landmarks(truth)
names = [v["name"] for v in rt["views"]]
MEAS = ("jaw_width", "gonial_width", "chin_width", "cheekbone_width", "chin_length", "chin_forward", "eyes_forward", "mouth_width", "nose_width", "pupils_apart")
OUT = gt.OUT / "chains"
OUT.mkdir(exist_ok=True)


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


if start == "true" or pert:
    m0 = f"{pre}00"
    bi.fork(src, m0, replace=True)
    rj = C.refs(m0)
    cams = copy.deepcopy(rt["cameras"]) if start == "true" else rj["cameras"]
    for p in [p for p in pert.split(",") if p]:
        vn, what, deg = p.split(":")
        i = names.index(vn)
        if what == "yaw":
            c1 = fr.cam_moved(cams[i], yaw=float(deg))
            if abs(abs(fr.view_yaw(c1)) - abs(fr.view_yaw(cams[i])) - float(deg)) > 0.5:
                c1 = fr.cam_moved(cams[i], yaw=-float(deg))
        elif what == "dist":
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
print(f"== {src} -> {pre}NN x{n}: cameras {first} / {cams_mode} dense {dense} start {start!r} pert {pert!r}")
rec = {"args": sys.argv[1:], "calls": [score(src)]}
show(rec["calls"][0])
for i in range(1, n + 1):
    out = f"{pre}{i:02d}"
    t = time.time()
    try:
        rep = bi.solve_step(src, out=out, cameras=first if i == 1 else cams_mode, dense=dense, **({"expression": expression} if expression else {}))
    except Exception as err:        # a refused step is a RESULT here (a real head may break a guard): recorded, the chain ends
        rec["error"] = {"call": i, "text": str(err)[:2000]}
        print(f"-- {out}: REFUSED / FAILED: {str(err)[:1500]}")
        json.dump(rec, open(OUT / f"{pre}.json", "w"))
        break
    so = rep["solve"]
    s = score(out)
    s.update(n=so["n"], dc=so["dc"], relax=so["relax"], damped=so.get("damped", 1), sig_scale=so["sig_scale"], kinds=so["kinds"],
             cam_done=so["cameras"], held=so.get("held"), camera_lines=so.get("camera_lines"),
             notes=[x for x in so.get("notes") or []], bound=so.get("bound"), disagree=so.get("disagree"),
             report=(so.get("report") or {}).get("text", ""), seconds=time.time() - t,
             rows=[{k: (r[k] if not isinstance(r[k], (np.floating, np.bool_)) else r[k].item()) for k in ("measure", "moved", "moved_sd", "read", "by", "unread") if k in r}
                   for r in ((so.get("report") or {}).get("rows") or []) if any(x in str(r.get("measure")) for x in ("nose", "mouth", "lip", "tip", "philtrum"))],
             expressions=C.refs(out).get("expressions"))
    rec["calls"].append(s)
    print(f"-- {out} ({time.time() - t:.0f} s): reads {so['n']} {so['kinds']}; |dc| {so['dc']:.2f}; relax x{so['relax']:.2f}{' DAMPED' if so.get('damped', 1) < 1 else ''}; adapt {so['sig_scale']}")
    for x in s["notes"] + (s.get("camera_lines") or []):
        print("   " + str(x)[:400])
    show(s)
    src = out
    json.dump(rec, open(OUT / f"{pre}.json", "w"))
