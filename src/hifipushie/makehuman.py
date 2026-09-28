"""MakeHuman as a body source for the base (spec base {"body": {"source": "makehuman", "age", "weight", "muscle",
"height", "race"}}): its CC0 base mesh (13,380 quads, closed) shaped by its CC0 macro targets, read with our own loader (the
MakeHuman program is AGPL and isn't used). Files in workspace/_templates/makehuman/ (SOURCE.txt: URL, commit, licence).

Macro targets are blended as MakeHuman blends them: the universal-male-<age>-<muscle>muscle-<weight>weight targets,
each weighted by the product of its age, muscle and weight weights. Age (years) maps to MakeHuman's slider (1 -> 0,
11 -> 0.1875, 25 -> 0.5, 90 -> 1) and blends the two nearest of baby/child/young/old; muscle and weight in 0..1 (0.5
average) blend min/average and average/max. Height scales the result uniformly (m). Only male targets are fetched so
far. The skeleton is MakeHuman's default.mhskel: each joint the mean of a helper cube's vertices, which ride the
targets, mapped to the template's joint names (pelvis, chest, neck, head, shoulder/elbow/wrist, hip/knee/ankle/toe,
fingerN_k / thumb_k), so `retopo._skeleton_warp` and `base` treat it like the template.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

_CACHE: dict = {}


def root() -> Path:
    from . import store
    return store.HOME / "_templates" / "makehuman"


def _raw():
    if "raw" not in _CACHE:
        r = root()
        if not (r / "3dobjs" / "base.obj").exists():
            raise FileNotFoundError(f"the MakeHuman body needs {r} (see SOURCE.txt there, or fetch the CC0 assets)")
        V, F, G, g = [], [], [], None
        for line in open(r / "3dobjs" / "base.obj"):
            if line.startswith("v "):
                V.append([float(x) for x in line.split()[1:4]])
            elif line.startswith("g "):
                g = line.split()[1]
            elif line.startswith("f "):
                F.append([int(t.split("/")[0]) - 1 for t in line.split()[1:]])
                G.append(g)
        skel = json.loads((r / "rigs" / "default.mhskel").read_text())
        body = [f for f, gg in zip(F, G) if gg == "body"]
        _CACHE["raw"] = (np.array(V), body, skel["joints"])
    return _CACHE["raw"]


def _target(name: str) -> tuple[np.ndarray, np.ndarray]:
    if name not in _CACHE:
        p = root() / "targets" / "macrodetails" / name
        if not p.exists():
            raise FileNotFoundError(f"MakeHuman target {name} isn't in {p.parent} (only male targets are fetched)")
        rows = [ln.split() for ln in p.read_text().splitlines() if ln.strip() and not ln.startswith("#")]
        _CACHE[name] = (np.array([int(r[0]) for r in rows], dtype=np.int64),
                        np.array([[float(x) for x in r[1:4]] for r in rows], dtype=float).reshape(-1, 3))
    return _CACHE[name]


def _age_slider(years: float) -> float:
    pts = [(1, 0.0), (11, 0.1875), (25, 0.5), (90, 1.0)]
    ys, ss = zip(*pts)
    return float(np.interp(years, ys, ss))


def _age_weights(a: float) -> dict:
    if a < 0.1875:
        t = a / 0.1875
        return {"baby": 1 - t, "child": t}
    if a < 0.5:
        t = (a - 0.1875) / (0.5 - 0.1875)
        return {"child": 1 - t, "young": t}
    t = (a - 0.5) / 0.5
    return {"young": 1 - t, "old": t}


def _three(v: float, lo: str, mid: str, hi: str) -> dict:
    v = float(np.clip(v, 0, 1))
    return {lo: 1 - 2 * v, mid: 2 * v} if v < 0.5 else {mid: 2 - 2 * v, hi: 2 * v - 1}


# the template's joint names from MakeHuman's joints (bone heads/tails; "head" a third of the way up its head bone:
# the template's head joint sits in the skull, not at the atlas)
JOINTS = {"pelvis": "root____tail", "chest": "spine02____head", "neck": "neck01____head",
          "shoulder.L": "upperarm01.L____head", "elbow.L": "lowerarm01.L____head", "wrist.L": "wrist.L____head",
          "hip.L": "upperleg01.L____head", "knee.L": "lowerleg01.L____head", "ankle.L": "foot.L____head",
          "toe.L": "toe3-1.L____head"}


def body(params: dict) -> dict:
    """A shaped MakeHuman body as a template dict (as retopo.load_template): {"name", "P" (metres, Z up, facing -Y,
    feet at z = 0), "L", "S", "J", "face": {"landmarks": {"eye.L"}}, "chin_z"}."""
    key = json.dumps({k: params.get(k) for k in ("age", "weight", "muscle", "height", "race")}, sort_keys=True)
    if ("body", key) in _CACHE:
        return _CACHE[("body", key)]
    V0, faces, joints = _raw()
    V = V0.copy()
    wa = _age_weights(_age_slider(float(params.get("age", 25))))
    wm = _three(float(params.get("muscle", 0.5)), "min", "average", "max")
    ww = _three(float(params.get("weight", 0.5)), "min", "average", "max")
    for age, a in wa.items():
        for mus, m in wm.items():
            for wt, w in ww.items():
                if a * m * w <= 1e-6:
                    continue
                idx, d = _target(f"universal-male-{age}-{mus}muscle-{wt}weight.target")
                V[idx] += a * m * w * d
    race = params.get("race") or {"african": 1 / 3, "asian": 1 / 3, "caucasian": 1 / 3}  # MakeHuman's default mix
    tot = sum(race.values())
    for r, rw in race.items():  # the race targets carry much of the sexed shape: without them the body read female
        for age, a in wa.items():
            if a * rw > 1e-6:
                idx, d = _target(f"{r}-male-{age}.target")
                V[idx] += a * rw / tot * d
    V = np.c_[V[:, 0], -V[:, 2], V[:, 1]] * 0.1  # dm, Y up, facing +Z -> m, Z up, facing -Y
    used = np.unique(np.concatenate(faces))
    lo = V[used, 2].min()
    V[:, 2] -= lo
    if params.get("height"):
        top = V[used, 2].max()
        V *= float(params["height"]) / top
    jp = lambda n: V[joints[n]].mean(0)
    J = {k: jp(v) for k, v in JOINTS.items()}
    h0, h1 = jp("head____head"), jp("head____tail")
    J["head"] = h0 + 0.35 * (h1 - h0)
    for k in range(1, 5):  # template finger k (index..pinky) = MakeHuman finger k+1
        for j in range(3):
            J[f"finger{k}_{j}.L"] = jp(f"finger{k + 1}-{j + 1}.L____head")
        J[f"finger{k}_3.L"] = jp(f"finger{k + 1}-3.L____tail")
    for j in range(3):
        J[f"thumb_{j}.L"] = jp(f"finger1-{j + 1}.L____head")
    J["thumb_3.L"] = jp("finger1-3.L____tail")
    J = {k: v for k, v in J.items()}
    for n, p in list(J.items()):
        if n.endswith(".L"):
            J[n[:-2] + ".R"] = p * [-1, 1, 1]
    # only the body's vertices, renumbered
    remap = -np.ones(len(V), int)
    remap[used] = np.arange(len(used))
    F = [[int(remap[v]) for v in f] for f in faces]
    eye = jp("eye.L____head")
    out = {"name": "makehuman", "P": V[used], "L": np.array([v for f in F for v in f]),
           "S": np.array([len(f) for f in F]), "J": J, "chin_z": float(jp("jaw____tail")[2]),
           "face": {"landmarks": {"eye.L": eye.tolist()}}}
    _CACHE[("body", key)] = out
    return out
