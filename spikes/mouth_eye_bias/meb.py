"""meb.py: the mouth / eye measures read the SAME way at every stage (docs/notes/mouth_eye_bias.md).

Stages of one head at its front reference camera (all in the reference picture's pixels, mm at the face's depth,
on the PHOTO's face axes):
  photo   MediaPipe on the reference picture
  geom    the model's mesh at MediaPipe's learned GNM correspondence (mp_gnm.json, + its learned bias): the shape
  clay    MediaPipe on the numba clay render (likeness.render) through the same camera
  flat    MediaPipe on the dressed Blender render, unlit albedo (skin_read stage)
  lit     MediaPipe on the dressed Blender render under the photo's fitted light
"""
from __future__ import annotations

import copy
import json
import sys

import numpy as np

OUT = "/mnt/data/hifipushie/mouthbias/out"
NAMES = ("mouth_w", "upper", "lower", "bow_depth", "open_R", "open_L", "fiss_R", "fiss_L", "intercanth", "outer_canth")


def frame_of(P):
    from hifipushie import likeness_eyes as le
    return le.frame(P)


def measures(P, ex, ey, mmpx) -> dict:
    P = np.asarray(P, float)
    y = lambda i: float(P[i] @ ey)  # noqa: E731
    d = lambda a, b: float(np.linalg.norm(P[a] - P[b])) * mmpx  # noqa: E731
    return {"mouth_w": d(61, 291), "upper": (y(13) - y(0)) * mmpx, "lower": (y(17) - y(14)) * mmpx,
            "bow_depth": (y(0) - 0.5 * (y(37) + y(267))) * mmpx,
            "open_R": (y(145) - y(159)) * mmpx, "open_L": (y(374) - y(386)) * mmpx,
            "fiss_R": d(33, 133), "fiss_L": d(263, 362), "intercanth": d(133, 362), "outer_canth": d(33, 263)}


def setup(refname: str):
    from hifipushie import blockin, likeness
    rj = likeness._refs(refname)
    vi = blockin._front(rj)
    ph = likeness.photo_sides({"views": [rj["views"][vi]], "cameras": [rj["cameras"][vi]]})[0]
    return rj, vi, ph


def geom_points(spec: dict, cam: dict, mmpx: float, bias: bool = True) -> np.ndarray:
    """(478, 2) picture px: each correspondence point of the model's surface projected (+ its learned bias); NaN
    where the table has none."""
    from hifipushie import face_ruler as fr, mpread
    head = fr.model_head(spec)
    g2m = fr._gnm_to_model(head)
    V = np.asarray(head["V"], float)
    yaw = mpread.cam_yaw(cam)
    P = np.full((478, 2), np.nan)
    for pt in mpread.table()["points"]:
        idx = [g2m.get(int(g), -1) for g in pt["tri"]]
        if min(idx) < 0:
            continue
        X = np.asarray(pt["w"], float) @ V[idx]
        _, q = fr._cam_points(cam, X[None])
        b = mpread.bias(pt, yaw)[0] if bias else np.zeros(2)
        P[int(pt["mp"])] = q[0] + b / mmpx
    return P


def clay_points(spec: dict, ph: dict):
    from hifipushie import likeness
    md = likeness.model_sides(spec["base"], [ph], refit=False)[0]
    return md["side"].P, md


def run(refname: str, models: list) -> dict:
    from hifipushie import store
    rj, vi, ph = setup(refname)
    cam, mmpx = ph["cam"], ph["mmpx"]
    Pp = ph["side"].P
    ex, ey = frame_of(Pp)
    rows = {"photo": measures(Pp, ex, ey, mmpx)}
    for m in models:
        spec = store.load(m)
        Pg = geom_points(spec, cam, mmpx)
        Pg_full = np.where(np.isfinite(Pg), Pg, Pp)
        rows[f"geom:{m}"] = measures(Pg_full, ex, ey, mmpx)
        Pc, _ = clay_points(spec, ph)
        if Pc is not None:
            rows[f"clay:{m}"] = measures(Pc, ex, ey, mmpx)
            np.save(f"{OUT}/P_clay_{m}.npy", Pc)
        np.save(f"{OUT}/P_geom_{m}.npy", Pg)
    np.save(f"{OUT}/P_photo_{refname}.npy", Pp)
    return {"ref": refname, "view": vi, "mmpx": mmpx, "rows": rows}


def text(res: dict) -> str:
    rows = res["rows"]
    cols = list(rows)
    s = f"{res['ref']} view {res['view']} ({res['mmpx']:.3f} mm/px)\n{'':12s}" + "".join(f"{c[:18]:>19s}" for c in cols) + "\n"
    for k in NAMES:
        r0 = rows["photo"][k]
        s += f"{k:12s}" + "".join(f"{rows[c][k]:10.2f}" + (f" ({rows[c][k] - r0:+5.2f})" if c != "photo" else " " * 8)
                                  for c in cols) + "\n"
    return s


if __name__ == "__main__":
    ref, models = sys.argv[1], sys.argv[2:] or [sys.argv[1]]
    r = run(ref, models)
    json.dump(r, open(f"{OUT}/meb_{ref}.json", "w"), indent=1)
    print(text(r))
