"""MakeHuman as a body source for the base (spec base {"body": {"source": "makehuman", "age", "weight", "muscle",
"height", "race"}}): its CC0 base mesh (13,380 quads, closed) shaped by its CC0 macro targets, read with our own loader (the
MakeHuman program is AGPL and isn't used). Files in the assets pack "makehuman" (assets.py: `hifipushie-assets fetch`; SOURCE.txt: URL, commit, licence).

Macro targets are blended as MakeHuman blends them: the universal-male-<age>-<muscle>muscle-<weight>weight targets,
each weighted by the product of its age, muscle and weight weights. Age (years) maps to MakeHuman's slider (1 -> 0,
11 -> 0.1875, 25 -> 0.5, 90 -> 1) and blends the two nearest of baby/child/young/old; muscle and weight in 0..1 (0.5
average) blend min/average and average/max. "sex" is MakeHuman's gender slider, continuous: 1 male (default), 0
female, anything between a blend of the male and female targets. Height scales the result uniformly (m).
Under 25 years (`grows`; "growth": false for MakeHuman's own straight lines) the age slider is solved so the shape
has that age's measured head-to-stature proportion and the body is scaled to its measured median stature
(anthro.py: WHO, Snyder 1977): MakeHuman's baby is a one-year-old's shape at 60 cm, its child a ten-year-old.
"nipples": 0..1 (1 as modelled) smooths them off the chest (under clothes). The skeleton is MakeHuman's default.mhskel: each joint the mean of a helper cube's vertices, which ride the
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
    # only what every body needs: the pack grew (female targets, the hand-made weights), and a machine holding the
    # older copy must still open a male body. The later files are checked where they are read.
    return assets.pack("makehuman", CORE)  # says how to fetch it when missing


CORE = ["3dobjs/base.obj", "rigs/default.mhskel"]
WEIGHTS = "rigs/default_weights.mhw"


def weights_note() -> str | None:
    """None when the hand-made weights are in the pack; else the WARNING for whoever rigs (the rig falls back to
    distance weights: fingers and thighs drag their neighbours)."""
    from . import assets
    if (root() / WEIGHTS).exists():
        return None
    return ("WARNING: MakeHuman's hand-made skin weights are not on this machine, so this rig uses DISTANCE weights "
            "(worse: neighbouring fingers and the two thighs drag each other). "
            + assets.missing("makehuman", WEIGHTS, "the template weights, needed only to rig / export with rig=True"))


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
        p = root() / WEIGHTS
        _CACHE["weights"] = None
        if p.exists():
            w = json.loads(p.read_text())["weights"]
            _CACHE["weights"] = {b: (np.array([r[0] for r in rows], np.int64), np.array([r[1] for r in rows], float))
                                 for b, rows in w.items() if rows}
    return _CACHE["weights"]


def _target(name: str, group: str = "macrodetails") -> tuple[np.ndarray, np.ndarray]:
    if name not in _CACHE:
        p = root() / "targets" / group / name
        if not p.exists():
            from . import assets
            if group != "macrodetails":
                raise FileNotFoundError(assets.missing("makehuman", f"targets/{group}/{name}", "a bust / nipple / measure / neck target: needed "
                                        "because base.body has bust, firmness or nipples"))
            why = ("a female target: needed because base.body.sex is under 1, or base.head.follow_body is set (its "
                   "reference head is sex 0.5); a body with sex 1 (the default) and no follow_body loads without it"
                   if "-female-" in name else "a body target")
            raise FileNotFoundError(assets.missing("makehuman", f"targets/macrodetails/{name}", why))
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


GROWN = 25.0  # years: from here MakeHuman's own shapes and sizes are used as they are


def grows(params: dict) -> bool:
    """Whether a body takes the measured growth (age under 25 unless "growth": false). MakeHuman blends baby (1 y)
    -> child (10 y) -> young (25 y) in straight lines of age: its 3-year-old stood 74 cm (measured median 96), its
    16-year-old 1.49 m (1.73), with a third of a child's shape left at 20."""
    g = params.get("growth")
    return float(params.get("age", 25)) < GROWN and (g is None or bool(g))


def table_age(params: dict) -> float:
    """The age at which MakeHuman's OWN straight-line blend has this body's shape (the body's age itself from 25, or
    with "growth": false). headfit's head tables were sampled along those ages: a head that follows a grown
    11-year-old is looked up at ~13."""
    age = float(params.get("age", 25))
    if not grows(params):
        return age
    a, _ = _growth_slider(params, age, float(np.clip(params.get("sex", 1.0), 0, 1)))
    return float(np.interp(a, [0.0, 0.1875, 0.5], [1.0, 11.0, 25.0]))


def _shaped(params: dict, slider: float, sex: float) -> np.ndarray:
    """MakeHuman's vertices (m, Z up, facing -Y; not yet stood on the ground) for an age slider value."""
    V0, faces, joints = _raw()
    V = V0.copy()
    wa = _age_weights(slider)
    wm = _three(float(params.get("muscle", 0.5)), "min", "average", "max")
    ww = _three(float(params.get("weight", 0.5)), "min", "average", "max")
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
    _bust(V, params, wa, wm, ww, 1 - sex)
    _measures(V, params)
    return np.c_[V[:, 0], -V[:, 2], V[:, 1]] * 0.1  # dm, Y up, facing +Z -> m, Z up, facing -Y


# MakeHuman's measure modifiers (targets/measure, CC0): base.body key -> target stem. 0..1, 0.5 = none (the macro
# body's own), 0 / 1 = the decr / incr target whole (MakeHuman's -1 / +1). Fit-solvable (humanfit.BODY_FREE).
MEASURES = {"hips": "measure-hips-circ", "waist": "measure-waist-circ", "shoulders": "measure-shoulder-dist",
            "chest": "measure-bust-circ", "neck_circ": "measure-neck-circ"}


# MakeHuman's neck modifiers (targets/neck, CC0), same 0..1 convention: "neck_double" = the soft fullness under the
# chin and at the front of the neck (a double chin at 1), "neck_depth" = the neck's front-to-back depth. The one mesh's
# GNM head reaches only to its stitch under the chin; the neck front below it is this body (lt19, 2026-10-10).
NECK = {"neck_double": "neck-double", "neck_depth": "neck-scale-depth"}


def _measures(V, params: dict) -> None:
    for group, table in (("measure", MEASURES), ("neck", NECK)):
        for key, stem in table.items():
            v = params.get(key)
            if v is None or abs(float(v) - 0.5) < 1e-6:
                continue
            s = 2.0 * (float(v) - 0.5)
            idx, d = _target(f"{stem}-{'incr' if s > 0 else 'decr'}.target", group)
            V[idx] += abs(s) * d


def _bust(V, params: dict, wa: dict, wm: dict, ww: dict, female: float) -> None:
    """MakeHuman's breast modifiers, applied only when asked: "bust" (cup size) and "firmness", 0..1 with 0.5 the
    macro targets' own breast (no target at average cup + average firmness), weighted by how female, and by age,
    muscle and weight as MakeHuman does (child / young / old targets: a baby has none); "nipples" 0..1 (1 as
    modelled) flattens them with MakeHuman's own nipple targets (any sex or age)."""
    cup, firm = params.get("bust"), params.get("firmness")
    if (cup is not None or firm is not None) and female > 1e-6:
        wc = _three(0.5 if cup is None else float(cup), "min", "average", "max")
        wf = _three(0.5 if firm is None else float(firm), "min", "average", "max")
        for age, a in wa.items():
            if age == "baby":
                continue
            for mus, m in wm.items():
                for wt, w in ww.items():
                    for c, cw in wc.items():
                        for f, fw in wf.items():
                            k = female * a * m * w * cw * fw
                            if k <= 1e-6 or (c == "average" and f == "average"):
                                continue
                            idx, d = _target(f"female-{age}-{mus}muscle-{wt}weight-{c}cup-{f}firmness.target", "breast")
                            V[idx] += k * d
    nip = params.get("nipples")
    if nip is not None and float(nip) < 1:
        # (the targets are an adult's millimetres: on a baby's chest, a third the size, they turned the skin inside out)
        k = float(np.ptp(V[:, 1]) / np.ptp(_raw()[0][:, 1]))
        for n in NIPPLE_TARGETS:
            idx, d = _target(n, "breast")
            V[idx] += (1 - float(nip)) * min(k, 1.0) * d


NIPPLE_TARGETS = ("nipple-point-decr.target", "nipple-size-decr.target")


def _heads(V: np.ndarray) -> tuple:
    """(stature, stature in head heights) of shaped vertices: the head from the crown to the chin landmark."""
    from . import headfit
    _, faces, _ = _raw()
    used = _CACHE.setdefault("used", np.unique(np.concatenate(faces)))
    chin = V[used[headfit.table()["lm68"][8]], 2]  # (the table indexes the body's own vertices, as body()["P"])
    top, lo = V[used, 2].max(), V[used, 2].min()
    return float(top - lo), float((top - lo) / (top - chin))


def _growth_slider(params: dict, age: float, sex: float) -> tuple:
    """The age slider whose SHAPE has the measured head-to-stature proportion of that age and sex (anthro.heads:
    WHO stature over Snyder's head height), and the measured median stature to scale it to. Statures are WHO's x
    (MakeHuman's own adult / WHO's at 19), so a 19-24-year-old is MakeHuman's adult, as at 25. Under ~1 year the
    shape stays MakeHuman's baby (its proportions are a one-year-old's)."""
    from . import anthro
    key = ("slider", json.dumps([{k: params.get(k) for k in ("weight", "muscle", "race")}, age, sex], sort_keys=True))
    if key not in _CACHE:
        want = anthro.heads(age, sex)
        lo, hi = 0.0, 0.5
        f = lambda a: _heads(_shaped(params, a, sex))[1]  # noqa: E731
        if want <= f(lo):
            a = lo
        elif want >= f(hi):
            a = hi
        else:
            for _ in range(16):
                a = 0.5 * (lo + hi)
                lo, hi = (a, hi) if f(a) < want else (lo, a)
            a = 0.5 * (lo + hi)
        adult = _heads(_shaped(params, 0.5, sex))[0] / anthro.stature(anthro.ADULT, sex)
        _CACHE[key] = (a, {"stature": anthro.stature(age, sex) * adult, "heads_wanted": want, "slider": a})
    return _CACHE[key]


def _smooth_nipples(V, faces, used, breast, amount: float, wide: bool = False):
    """What MakeHuman's nipple targets leave (a nub that prints through cloth as a stud) taken off: round the nipple's
    tip the skin within 1.2% of the stature (the nipple itself: at 4% this scooped a crater out of each of a woman's
    breasts, the "dented ring") is moved, along the chest's normal only, onto a quadratic sheet fitted through the
    ring of skin just outside it. (Relaxing the vertices instead puckered the mesh: a pole of small dense rings.)"""
    V = V.copy()
    H = float(V[used, 2].max() - V[used, 2].min())
    body = np.zeros(len(V), bool)
    body[used] = True
    r = max(0.012 * H, 0.011)  # (a baby's mesh has few vertices within 9 mm)
    if wide:  # a child's chest: MakeHuman models a small mound under each nipple, which printed through a vest
        r = 0.04 * H
    E = _CACHE.get("edges")
    if E is None:
        E = np.array(sorted({(min(f[k], f[(k + 1) % len(f)]), max(f[k], f[(k + 1) % len(f)])) for f in faces for k in range(len(f))}))
        _CACHE["edges"] = E
    deg = np.bincount(E.ravel(), minlength=len(V)).astype(float)
    ln = np.linalg.norm(V[E[:, 0]] - V[E[:, 1]], axis=1)
    el = np.zeros(len(V))
    np.add.at(el, E[:, 0], ln)
    np.add.at(el, E[:, 1], ln)
    el = np.where(deg > 0, el / np.maximum(deg, 1), np.inf)  # each vertex's mean edge length
    for sgn in (1.0, -1.0):
        c0 = breast * [sgn, 1, 1]
        near = body & (np.linalg.norm(V - c0, axis=1) < 0.056 * H)
        if near.sum() < 12:
            continue
        c = V[np.flatnonzero(near)[np.argmin(el[near])]]  # the nipple's tip: where the mesh's rings are smallest
        d = np.linalg.norm(V - c, axis=1)
        ring = body & (d > r) & (d < 1.9 * r)
        inner = body & (d <= r)
        if ring.sum() < 6 or not inner.any():
            continue
        Q = V[ring] - V[ring].mean(0)
        n = np.linalg.svd(Q, full_matrices=False)[2][2]
        n = -n if n[1] > 0 else n  # out of the chest (the figure faces -y)
        e1 = np.cross(n, [0, 0, 1.0])
        e1 /= np.linalg.norm(e1)
        e2 = np.cross(n, e1)

        def uvh(X):
            Y = X - c
            return Y @ e1, Y @ e2, Y @ n
        u, v, h = uvh(V[ring])
        A = np.c_[np.ones_like(u), u, v, u * u, u * v, v * v]
        coef = np.linalg.lstsq(A, h, rcond=None)[0]
        u, v, h = uvh(V[inner])
        fit = np.c_[np.ones_like(u), u, v, u * u, u * v, v * v] @ coef
        t = np.clip((r - d[inner]) / ((0.5 if wide else 0.9) * r), 0, 1)  # (wide: whole within half the radius)
        w = amount * t * t * (3 - 2 * t)
        V[inner] += (w * (fit - h))[:, None] * n
    return V


def body(params: dict) -> dict:
    """A shaped MakeHuman body as a template dict (as retopo.load_template): {"name", "P" (metres, Z up, facing -Y,
    feet at z = 0), "L", "S", "J", "face": {"landmarks": {"eye.L"}}, "chin_z"}."""
    grow = grows(params)
    key = json.dumps({k: params.get(k) for k in ("age", "weight", "muscle", "height", "race", "sex", "nipples", "bust", "firmness", *MEASURES, *NECK)} | ({"growth": True} if grow else {}), sort_keys=True)
    if ("body", key) in _CACHE:
        return _CACHE[("body", key)]
    V0, faces, joints = _raw()
    sex = float(np.clip(params.get("sex", 1.0), 0, 1))  # MakeHuman's gender slider: 0 female .. 1 male, any mix
    age = float(params.get("age", 25))
    used = np.unique(np.concatenate(faces))
    if grow:  # the shape and size of that age as children are measured (anthro.py), not MakeHuman's straight lines
        slider, info = _growth_slider(params, age, sex)
    else:
        slider, info = _age_slider(age), None
    V = _shaped(params, slider, sex)
    lo = V[used, 2].min()
    V[:, 2] -= lo
    if params.get("height"):
        top = V[used, 2].max()
        V *= float(params["height"]) / top
    elif grow:
        V *= info["stature"] / V[used, 2].max()
    jp = lambda n: V[joints[n]].mean(0)
    if params.get("nipples") is not None and float(params["nipples"]) < 1:
        V = _smooth_nipples(V, faces, used, jp("breast.L____tail"), 1 - float(params["nipples"]), wide=age < 11)
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
