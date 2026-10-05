"""MakeHuman as a body source for the base (spec base {"body": {"source": "makehuman", "age", "weight", "muscle",
"height", "race"}}): its CC0 base mesh (13,380 quads, closed) shaped by its CC0 macro targets, read with our own loader (the
MakeHuman program is AGPL and isn't used). Files in the assets pack "makehuman" (assets.py: `hifipushie-assets fetch`; SOURCE.txt: URL, commit, licence).

Macro targets are blended as MakeHuman blends them: the universal-male-<age>-<muscle>muscle-<weight>weight targets,
each weighted by the product of its age, muscle and weight weights. Age (years) maps to MakeHuman's slider (1 -> 0,
11 -> 0.1875, 25 -> 0.5, 90 -> 1) and blends the two nearest of baby/child/young/old; muscle and weight in 0..1 (0.5
average) blend min/average and average/max. "sex" is MakeHuman's gender slider, continuous: 1 male (default), 0
female, anything between a blend of the male and female targets. Height scales the result uniformly (m). The skeleton is MakeHuman's default.mhskel: each joint the mean of a helper cube's vertices, which ride the
targets, mapped to the template's joint names (pelvis, chest, neck, head, shoulder/elbow/wrist, hip/knee/ankle/toe,
fingerN_k / thumb_k), so `retopo._skeleton_warp` and `base` treat it like the template.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

_CACHE: dict = {}


def root() -> Path:
    from . import assets
    return assets.pack("makehuman")  # says how to fetch it when missing


def _raw():
    if "raw" not in _CACHE:
        r = root()
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


def skeleton() -> dict:
    """MakeHuman's default skeleton as it ships: {"bones": {name: {"head", "tail" (joint names), "parent"}},
    "joints": {joint: helper vertex ids}}."""
    if "skel" not in _CACHE:
        _CACHE["skel"] = json.loads((root() / "rigs" / "default.mhskel").read_text())
    return _CACHE["skel"]


def weights() -> dict | None:
    """MakeHuman's own hand-made skin weights for its default skeleton (rigs/default_weights.mhw, CC0): {bone:
    (vertex ids in base.obj's numbering, weights)}, or None if the file isn't in the pack."""
    if "weights" not in _CACHE:
        p = root() / "rigs" / "default_weights.mhw"
        _CACHE["weights"] = None
        if p.exists():
            w = json.loads(p.read_text())["weights"]
            _CACHE["weights"] = {b: (np.array([r[0] for r in rows], np.int64), np.array([r[1] for r in rows], float))
                                 for b, rows in w.items() if rows}
    return _CACHE["weights"]


def _target(name: str) -> tuple[np.ndarray, np.ndarray]:
    if name not in _CACHE:
        p = root() / "targets" / "macrodetails" / name
        if not p.exists():
            raise FileNotFoundError(f"MakeHuman target {name} isn't in {p.parent}: fetch the pack again "
                                    f"(`uv run hifipushie-assets fetch makehuman`; the female targets were added later)")
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
    key = json.dumps({k: params.get(k) for k in ("age", "weight", "muscle", "height", "race", "sex")}, sort_keys=True)
    if ("body", key) in _CACHE:
        return _CACHE[("body", key)]
    V0, faces, joints = _raw()
    V = V0.copy()
    wa = _age_weights(_age_slider(float(params.get("age", 25))))
    wm = _three(float(params.get("muscle", 0.5)), "min", "average", "max")
    ww = _three(float(params.get("weight", 0.5)), "min", "average", "max")
    sex = float(np.clip(params.get("sex", 1.0), 0, 1))  # MakeHuman's gender slider: 0 female .. 1 male, any mix
    ws = {g: s for g, s in (("male", sex), ("female", 1 - sex)) if s > 1e-6}
    for g, s in ws.items():
        for age, a in wa.items():
            for mus, m in wm.items():
                for wt, w in ww.items():
                    if s * a * m * w <= 1e-6:
                        continue
                    idx, d = _target(f"universal-{g}-{age}-{mus}muscle-{wt}weight.target")
                    V[idx] += (a * m * w * d) if s == 1.0 else (s * a * m * w * d)
    race = params.get("race") or {"african": 1 / 3, "asian": 1 / 3, "caucasian": 1 / 3}  # MakeHuman's default mix
    tot = sum(race.values())
    for r, rw in race.items():  # the race targets carry much of the sexed shape: without them the body read female
        for g, s in ws.items():
            for age, a in wa.items():
                if s * a * rw > 1e-6:
                    idx, d = _target(f"{r}-{g}-{age}.target")
                    V[idx] += (a * rw / tot * d) if s == 1.0 else (s * a * rw / tot * d)
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
    bones = {n: (jp(b["head"]), jp(b["tail"])) for n, b in skeleton()["bones"].items()}
    nk, hd = J["neck"], J["head"]
    f = float((bones["head"][0] - nk) @ (hd - nk) / ((hd - nk) @ (hd - nk)))
    # where the export rig's Neck and Head pivot (rig.humanoid): the "neck" joint here is the neck's base
    rig_hint = {"Neck": ["neck", "head", 0.0], "Head": ["neck", "head", round(f, 4)]}
    out = {"name": "makehuman", "vid": used, "bones": bones, "rig": rig_hint, "P": V[used], "L": np.array([v for f in F for v in f]),
           "S": np.array([len(f) for f in F]), "J": J, "chin_z": float(jp("jaw____tail")[2]),
           "face": {"landmarks": {"eye.L": eye.tolist()}}}
    _CACHE[("body", key)] = out
    return out
