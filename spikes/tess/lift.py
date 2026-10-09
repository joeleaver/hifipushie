"""lift.py <model> <trace json> <view index> [h m]: the trace's strokes lifted to 3D through the model's fitted camera
(human_refs.json view <index>): each stroke point's ray hits the hair's surface (the scalp + h, default 10 mm);
points whose ray misses the head (a tail in the air) are put in the plane through the head centre facing the camera,
offset to the last hit's depth. Prints and writes <trace>_lift<index>.json: {stroke: [[x, y, z], ...],
stroke + "_azel": [[az, el], ...] (head points only)}."""
import json, sys

import numpy as np

from hifipushie import hair, humanfit, store

name, tj, vi = sys.argv[1], sys.argv[2], int(sys.argv[3])
h = float(sys.argv[4]) if len(sys.argv) > 4 else 0.010
refs = json.loads((store.HOME / name / "human_refs.json").read_text())
cam = refs["cameras"][vi]
R = humanfit._cam_rot(cam)
eye = np.asarray(cam["centre"], float) - R.T @ np.asarray(cam["t"], float)
w, hh = cam["size"]
sc = hair.scalp(name)
tr = json.load(open(tj))


def ray(u, v):
    d = R.T @ np.array([(u - w / 2) / cam["f"], (v - hh / 2) / cam["f"], 1.0])
    return d / np.linalg.norm(d)


def hit(u, v):
    d = ray(u, v)
    ts = np.linspace(0.2, 3.0, 2800)
    P = eye + ts[:, None] * d
    az, el, hp = sc.coords(P)
    inside = hp < h
    if inside.any():  # the first point inside the hair's surface (scalp + h)
        i = int(np.argmax(inside))
    else:  # grazing the hair outside the scalp + h: the ray's closest approach to the scalp, if within 4 cm
        i = int(np.argmin(hp))
        if hp[i] > 0.04:
            return None, None
    return P[i], (float(az[i]) % 360, float(el[i]))


out = {}
fwd = R.T @ np.array([0.0, 0.0, 1.0])
for group in ("part", "flow", "wisps"):
    items = {"part": tr["part"]} if group == "part" and tr.get("part") else (tr.get(group) or {}) if group != "part" else {}
    for k, pts in items.items():
        P3, AE = [], []
        last = None
        for u, v in pts:
            p, ae = hit(u, v)
            if p is None:  # in the air: the plane facing the camera at the last hit's depth (or the head centre's)
                ref = last if last is not None else sc.C
                d = ray(u, v)
                t = float(np.dot(ref - eye, fwd) / np.dot(d, fwd))
                p = eye + t * d
            else:
                last = p
                AE.append([round(ae[0], 1), round(ae[1], 1)])
            P3.append([round(float(x), 4) for x in p])
        out[k] = P3
        out[k + "_azel"] = AE
if tr.get("tie"):  # the tie sits off the scalp: on the plane through the head centre facing the camera
    d = ray(*tr["tie"])
    t = float(np.dot(sc.C - eye, fwd) / np.dot(d, fwd))
    p = eye + t * d
    az, el, hp = sc.coords(p[None])
    out["tie_azel"] = [round(float(az[0]) % 360, 1), round(float(el[0]), 1)]
    out["tie_out"] = round(float(hp[0]), 4)  # m off the scalp
    out["tie_xyz"] = [round(float(x), 4) for x in p]
op = tj.replace(".json", f"_lift{vi}.json")
json.dump(out, open(op, "w"), indent=1)
for k, v in out.items():
    if k.endswith("_azel") or k.startswith("tie"):
        print(k, v)
print("head centre", sc.C.round(4), "saved", op)
