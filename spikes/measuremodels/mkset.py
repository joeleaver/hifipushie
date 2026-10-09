"""The measurement-model test set: the refstudy truth heads (same cameras as their clay pictures) and calibration
heads (other seeds), rendered SKINNED AND LIT by Blender (EEVEE: subsurface skin, pores, tones from light to dark,
stubble on some, a hair stand-in on some, sun + sky, coloured backgrounds), with everything a score needs kept:
the head's vertices, the camera, which pixels the hair covers.

  MM/set/<id>.png, <id>.json (cam, look), <id>.npz (V as pictured incl. expression, hair mesh | none)
  ids: <truth subject>_<front|tq|profile|tq2>, C<nn>_<front|tq|profile|tq2>

run.sh mkset.py jobs   -> MM/set/jobs.npz files          run.sh mkset.py render -> Blender
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

import rs
import subjects

MM = Path(os.environ.get("MM", "/mnt/data/hifipushie/measuremodels"))
SET = MM / "set"
N_CAL = 20
TONES = [[226, 190, 168], [205, 165, 144], [176, 128, 100], [141, 96, 70], [112, 74, 54], [85, 51, 28], [215, 178, 150], [190, 146, 118]]
BACK = [[0.55, 0.57, 0.6], [0.72, 0.7, 0.66], [0.25, 0.3, 0.38], [0.8, 0.82, 0.85], [0.4, 0.36, 0.33], [0.6, 0.66, 0.6]]


def srgb_lin(c):
    c = np.asarray(c, float) / 255.0
    return np.where(c < 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def albedo(tone, stubble, rng):
    g = rs.gnm()
    gr = g["gr"]
    A = np.tile(np.asarray(tone, float), (len(g["V0"]), 1))
    A[gr["scleras"]] = [232, 226, 220]
    iris = [[80, 62, 48], [70, 96, 120], [92, 104, 70], [52, 38, 30]][int(rng.integers(4))]
    A[gr["irises"]] = iris
    A[gr["pupils"]] = [18, 14, 12]
    A[gr["teeth"]] = [225, 220, 205]
    A[gr["mouth_sock"] | gr["tongue"] | gr["gums"]] = [120, 60, 60]
    lips = gr["upper_lip"] | gr["lower_lip"]
    A[lips] = np.asarray(tone) * [0.86, 0.62, 0.62] + [18, 6, 8]
    if stubble:
        low = (gr["chin_region"] | gr["left_parotid_region"] | gr["right_parotid_region"] | gr["upper_lip_region"]) & g["ext"] & ~lips
        A[low] = A[low] * [0.74, 0.76, 0.8]
    A[g["brow"]] = np.asarray(tone) * 0.28 + [10, 6, 4]
    gloss = np.zeros(len(A))
    gloss[gr["scleras"] | gr["irises"] | gr["pupils"]] = 1.0
    gloss[lips] = 0.4
    return srgb_lin(np.clip(A, 0, 255)), gloss


def hair_cap(V, rng, thick):
    """A hair stand-in: the scalp behind a hairline pushed out by `thick` m (uneven), tapering to the hairline."""
    g = rs.gnm()
    L = rs.landmarks(V)
    T = g["T"]
    z_brow, z_top = L[17:27, 2].max(), V[g["regions"]["head"], 2].max()
    y_ear = L[[0, 16], 1].mean()
    # the scalp: above a line that rises from behind the ears to a hairline on the forehead
    hl = z_brow + (0.55 + 0.1 * rng.random()) * (z_top - z_brow)
    lvl = np.where(V[:, 1] < y_ear, hl + (V[:, 1] - y_ear) * 0.0, hl - 0.9 * np.clip(V[:, 1] - y_ear, 0, 0.05))
    lvl = np.where(V[:, 1] < y_ear - 0.02, hl, np.minimum(lvl, hl))
    side = np.clip((V[:, 1] - (y_ear - 0.03)) / 0.06, 0, 1)        # behind the temples the hair comes down to ear height
    lvl = lvl - side * (hl - (L[[0, 16], 2].mean() + 0.02))
    m = g["ext"] & ~g["gr"]["ears"] & (V[:, 2] > lvl)
    F = T[m[T].all(1)]
    vn = np.zeros_like(V)
    fn = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    for c in range(3):
        np.add.at(vn, T[:, c], fn)
    vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)
    taper = np.clip((V[:, 2] - lvl) / 0.03, 0.08, 1.0)
    lump = 1.0 + 0.35 * np.sin(V[:, 0] * 90 + rng.random() * 6) * np.cos(V[:, 1] * 70 + rng.random() * 6)
    H = V + vn * (thick * taper * lump)[:, None]
    used = np.unique(F)
    remap = -np.ones(len(V), int)
    remap[used] = np.arange(len(used))
    return H[used], remap[F]


def cal_heads():
    out = {}
    for s in range(N_CAL):
        c = np.random.default_rng(5000 + s).normal(0, 1.0, rs.K_TRUE)
        if s % 3 == 2:   # some out of GNM's basis, as the truth set's O subjects
            r = np.random.default_rng(900 + s)
            V = rs.head(0.5 * c, extra=rs.mh_field(float(r.uniform(20, 70)), float(r.integers(2)), float(r.uniform(0.3, 0.9))))
        else:
            V = rs.head(c)
        out[f"C{s:02d}"] = V
    return out


def jobs():
    SET.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(77)
    g = rs.gnm()
    quads = np.asarray(g["raw"]["quads"])
    gr = g["gr"]
    clear = gr["eye_exteriors"] & ~(gr["scleras"] | gr["irises"] | gr["pupils"])   # the cornea shell hides the iris
    quads = quads[~clear[quads].any(1)]
    items = []
    for name in subjects.names():
        sub = subjects.load(name)
        for vn, vw in sub["views"].items():
            V = sub["V"] + (sub["e"] if (sub["e"] is not None and vw["expression"]) else 0.0)
            items.append((f"{name}_{vn}", name, vn, V, vw["cam"]))
    crng = np.random.default_rng(7)
    for name, V in cal_heads().items():
        for vn, yaw in (("front", 0.0), ("tq", 40.0), ("profile", 88.0), ("tq2", -38.0)):   # sides as the truth set's
            sgn = 1.0
            cam = rs.make_cam(V, yaw=sgn * yaw + crng.normal(0, 4), pitch=crng.normal(0, 5), roll=crng.normal(0, 2.5),
                              lens=float(crng.choice([35, 50, 70, 85, 105])), fill=crng.uniform(0.5, 0.68))
            items.append((f"{name}_{vn}", name, vn, V, cam))
    looks = {}
    job = []
    for iid, name, vn, V, cam in items:
        if name not in looks:
            k = len(looks)
            looks[name] = {"tone": TONES[k % len(TONES)], "stubble": bool(k % 3 == 1), "hair": float([0.0, 0.012, 0.0, 0.025][k % 4]),
                           "seed": k}
        lk = looks[name]
        A, gloss = albedo(lk["tone"], lk["stubble"], np.random.default_rng(lk["seed"]))
        hair = hair_cap(V, np.random.default_rng(lk["seed"]), lk["hair"]) if lk["hair"] else None
        Rc = rs.humanfit._cam_rot(cam)
        pos = np.asarray(cam["centre"]) - Rc.T @ np.asarray(cam["t"])
        M = np.eye(4)
        M[:3, 0], M[:3, 1], M[:3, 2], M[:3, 3] = Rc.T @ [1, 0, 0], Rc.T @ [0, -1, 0], Rc.T @ [0, 0, -1], pos
        lc = np.array([-0.35 + rng.normal(0, 0.45), -0.45 + rng.normal(0, 0.2), -0.82])   # the sun's travel, camera frame
        sun = Rc.T @ (lc / np.linalg.norm(lc))
        look = {**lk, "sun": sun.tolist(), "sun_w": float(rng.uniform(1.5, 4.5)), "sky": float(rng.uniform(0.35, 1.1)),
                "soft": float(rng.uniform(2, 25)), "back": BACK[int(rng.integers(len(BACK)))]}
        np.savez(SET / f"{iid}.npz", V=V.astype(np.float32), quads=quads, col=A.astype(np.float32), gloss=gloss.astype(np.float32),
                 hairV=(hair[0] if hair else np.zeros((0, 3))).astype(np.float32), hairF=hair[1] if hair else np.zeros((0, 3), int),
                 cam=M, lens=cam["f"] / cam["size"][0] * 36.0, size=np.asarray(cam["size"]))
        (SET / f"{iid}.json").write_text(json.dumps({"id": iid, "subject": name, "view": vn, "cam": cam, "look": look}, indent=1))
        job.append(iid)
    (SET / "jobs.json").write_text(json.dumps(job))
    print(len(job), "jobs in", SET)


def render(only=None):
    ids = json.loads((SET / "jobs.json").read_text())
    ids = [i for i in ids if not (SET / f"{i}.png").exists() and (not only or any(o in i for o in only))]
    if not ids:
        return
    lst = SET / "todo.json"
    lst.write_text(json.dumps(ids))
    here = Path(__file__).parent
    subprocess.run(["blender", "-b", "--factory-startup", "-P", str(here / "bl_skin.py"), "--", str(SET), str(lst)], check=True)


if __name__ == "__main__":
    if sys.argv[1] == "jobs":
        jobs()
    else:
        render(sys.argv[2:])
