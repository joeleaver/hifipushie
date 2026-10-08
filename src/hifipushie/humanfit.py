"""Measuring and fitting the one human mesh (onemesh.py) without wrecking what wasn't asked about.

Sliders are ambiguous, and an agent that hits one number blind breaks the rest of the face. So the interface is:
state evidence (named measures, landmark moves), a SOLVER finds the parameters, and every change comes back with what
ELSE moved and whether the mesh is still sound.

- `measures(base)`: a named vocabulary read off the mesh: body (cm: stature, heads tall, breadths, girths, limb
  lengths; anthro.measure) and face (mm, from the 68 landmarks and the eye centres: FACE below), plus ratios the
  agent asks for as "a/b".
- `solve(base, {"measure": value | "+2" | "x1.1", "a/b": ratio}, free=("identity",))`: minimal change. Gauss-Newton
  on GNM's identity components (the landmarks are linear in them: headfit's tables) and, with "body" in `free`, on
  MakeHuman's macros (finite differences); every measure NOT asked for is held as a soft constraint, every landmark
  far from the asked ones is held in place, the step is ridged toward the CURRENT state, and components stop at the
  plausible range (CLIP sigma; `force` widens it). What the parameters can't reach is reported as the residual, not
  obeyed.
- `nudge(base, landmark, move)`: move one landmark; the parameters take what they can, the rest becomes a small smooth
  correction (a Gaussian push at that landmark, base.head.shape.push_more: it survives later changes) and is REPORTED:
  that is a slider the model lacks.
- `side_effects(before, after, asked)`: all measures before -> after sorted by how far they moved, UNINTENDED flags,
  where the vertices moved and how many outside the region asked.
- `integrity(base)`: gates cheap enough to run on every change: folded faces, edge stretch per named region (lids,
  lips, nose, ears, neck bridge) against the same body with a neutral head, lids over the eyeballs, lips not crossed,
  symmetry, plausibility (sigma). `verdict` leads with INTEGRITY: ok / BROKEN: ...
"""
from __future__ import annotations

import copy
import json

import numpy as np

CLIP = 2.6       # sigma: an identity component past this is outside the plausible range (headfit's)
CLIP_FORCE = 4.0
TOL_MM = 0.5     # a face measure counts as met within this
UNINTENDED_MM = 1.0   # a face measure that wasn't asked for and moved more is flagged
FOLD_LIMIT = 6    # faces an edit may turn over before the mesh counts as broken
COLLATERAL = 2.0  # a solve stops where a measure that wasn't asked for would move this many times its tolerance
UNINTENDED_BODY = 0.01  # ... a body measure: 1%
HOLD = 0.35      # weight of holding the measures that weren't asked for (x 1 / mm)
HOLD_SKULL = 0.25  # weight of holding the skull's own points (crown, back, neck) in image fits and solves (x 1 / mm)
HOLD_LM = 0.12   # weight of holding landmarks far from the asked ones (x 1 / mm)
RIDGE = 0.25     # weight of each component's step (per sigma)
EYE_L, EYE_R = 68, 69  # the eye centres, after the 68 landmarks

# name: (points a, points b, axis): the distance from the mean of a to the mean of b along x (across), z (up),
# y (depth, + = a behind b) or None (straight). mm. Mirrored pairs are averaged ("pairs": [(a, b), ...]).
FACE = {
    "interocular": ([EYE_L], [EYE_R], "x"),
    "face_width": ([16], [0], "x"),
    "jaw_width": ([12], [4], "x"),
    "chin_width": ([10], [6], "x"),
    "face_height": ([27], [8], "z"),
    "eye_width": {"pairs": [([45], [42], None), ([39], [36], None)]},
    "eye_height": {"pairs": [([43, 44], [47, 46], "z"), ([37, 38], [41, 40], "z")]},
    "eye_spacing": ([42], [39], "x"),
    "eye_to_chin": ([EYE_L, EYE_R], [8], "z"),
    "brow_height": ([19, 24], [EYE_L, EYE_R], "z"),
    "nose_length": ([27], [33], "z"),
    "nose_width": ([35], [31], "x"),
    "nose_projection": ([33], [30], "y"),
    "philtrum": ([33], [51], "z"),
    "mouth_width": ([54], [48], "x"),
    "lip_height": ([51], [57], "z"),
    "mouth_to_eye": ([EYE_L, EYE_R], [62, 66], "z"),
    "chin_height": ([57], [8], "z"),
}
BODY = ("stature", "heads", "head_height", "sitting_height", "biacromial", "hip_breadth", "trochanter_height",
        "hand_length", "foot_length", "chest_circ", "waist_circ", "neck_circ")
BODY_FREE = ("weight", "muscle", "height")
AX = {"x": 0, "y": 1, "z": 2}
LANDMARKS = {"chin": 8, "nose_tip": 30, "nose_base": 33, "nose_bridge": 27, "lip_upper": 51, "lip_lower": 57,
             "mouth_corner.L": 54, "mouth_corner.R": 48, "jaw.L": 12, "jaw.R": 4, "jaw_back.L": 15, "jaw_back.R": 1,
             "brow.L": 24, "brow.R": 19, "brow_inner.L": 22, "brow_inner.R": 21, "eye_outer.L": 45, "eye_outer.R": 36,
             "eye_inner.L": 42, "eye_inner.R": 39, "lid_upper.L": 43, "lid_upper.R": 38, "lid_lower.L": 47,
             "lid_lower.R": 40, "ala.L": 35, "ala.R": 31, "chin.L": 10, "chin.R": 6}


def _one(spec, L):
    a, b, ax = spec
    d = L[a].mean(0) - L[b].mean(0)
    return float(np.linalg.norm(d) if ax is None else d[AX[ax]]) * 1000.0


def _grad(spec, L):
    """d(measure, mm) / d(L, m): (70, 3)."""
    a, b, ax = spec
    G = np.zeros_like(L)
    d = L[a].mean(0) - L[b].mean(0)
    u = d / max(np.linalg.norm(d), 1e-12) if ax is None else np.eye(3)[AX[ax]]
    G[a] += u / len(a)
    G[b] -= u / len(b)
    return G * 1000.0


def face_measures(L) -> dict:
    out = {}
    for k, sp in FACE.items():
        out[k] = float(np.mean([_one(p, L) for p in sp["pairs"]])) if isinstance(sp, dict) else _one(sp, L)
    return out


def face_gradient(name: str, L):
    sp = FACE[name]
    if isinstance(sp, dict):
        return np.mean([_grad(p, L) for p in sp["pairs"]], axis=0)
    return _grad(sp, L)


def _points(name: str) -> list:
    sp = FACE[name]
    pr = sp["pairs"] if isinstance(sp, dict) else [sp]
    return sorted({i for a, b, _ in pr for i in a + b})


def state(base: dict) -> dict:
    """The mesh and what is read off it: {"tpl", "head", "L" (68 landmarks + 2 eye centres, world, template pose),
    "measures"}."""
    from . import anthro, onemesh
    if not onemesh.applies(base):
        raise ValueError('humanfit: the model\'s base is not the one human mesh (base.body.source "human"; make one with '
                         'the human tool, source="human")')
    tpl = onemesh.template(base)
    ht = onemesh.head_rest(base)
    L = np.r_[np.asarray(ht["lm68"], float), np.asarray(ht["eyes"], float)]
    if L[EYE_L, 0] < L[EYE_R, 0]:
        L[[EYE_L, EYE_R]] = L[[EYE_R, EYE_L]]
    m = anthro.measure(np.asarray(tpl["P"], float), tpl["J"], float(tpl["chin_mh"]))
    m["neck_circ"] = _neck_girth(tpl)
    body = {k: float(m[k]) * (1.0 if k == "heads" else 100.0) for k in BODY if k in m}
    return {"tpl": tpl, "head": ht, "L": L, "measures": {**body, **face_measures(L)}, "base": base}


HOLLOW_FROM = 0.4  # the cheek hollow is read from this share of the way from the nose's wing to the jaw contour


def cheek_hollow(st: dict) -> dict:
    """mm per side: the hollow under the cheekbone, read on HORIZONTAL sections of the head (between the nose's base
    and the mouth's corners, three levels): the face's outer contour on that side (from the nose's wing out to the
    jaw contour) against its convex hull, the deepest point inside the hull. A lean face with hollow cheeks reads a
    few mm, a full or jowly one ~0 (its contour is convex). The head faces -y."""
    from scipy.spatial import ConvexHull
    P = np.asarray(st["tpl"]["P"], float)
    T = np.array([(f[0], f[j], f[j + 1]) for f in _faces(st["tpl"]) for j in range(1, len(f) - 1)])
    L = st["L"]
    mid = 0.5 * (L[EYE_L] + L[EYE_R])
    out = {"right": 0.0, "left": 0.0}
    for zc in np.linspace(L[33, 2], 0.5 * (L[48, 2] + L[54, 2]), 3):
        dz = P[T, 2] - zc
        cr = (dz.min(1) < 0) & (dz.max(1) > 0)
        pts = []
        for t, d_ in zip(T[cr], dz[cr]):
            for a_, b_ in ((0, 1), (1, 2), (2, 0)):
                if (d_[a_] < 0) != (d_[b_] < 0):
                    u = d_[a_] / (d_[a_] - d_[b_])
                    pts.append((P[t[a_]] + u * (P[t[b_]] - P[t[a_]]))[:2])
        S = np.array(pts)
        if len(S) < 10:
            continue
        c = np.array([mid[0], 0.5 * (L[2, 1] + L[14, 1])])  # a centre inside the face, level with the jaw contour
        ang = np.arctan2(S[:, 0] - c[0], c[1] - S[:, 1])  # 0 = straight ahead (-y): no wrap on either side
        rad = np.linalg.norm(S - c, axis=1)
        for side, sgn, wing, jaw in (("right", -1, 31, 2), ("left", 1, 35, 14)):
            a0 = np.arctan2(L[wing, 0] - c[0], c[1] - L[wing, 1])
            a1 = np.arctan2(L[jaw, 0] - c[0], c[1] - L[jaw, 1])
            a0 = a0 + HOLLOW_FROM * (a1 - a0)  # the outer cheek only: nearer the nose the deepest point is the
            # nasolabial fold, which every face has (3-4 mm on the plain heads)
            lo, hi = min(a0, a1), max(a0, a1)
            bins = np.linspace(lo, hi, 40)
            cont = []
            for b0, b1 in zip(bins[:-1], bins[1:]):
                k = (ang >= b0) & (ang < b1)
                if k.any():
                    cont.append(S[k][np.argmax(rad[k])])  # the outer contour: the farthest crossing at that angle
            cont = np.array(cont)
            if len(cont) < 8:
                continue
            h = ConvexHull(np.r_[cont, c[None]])
            dmin = np.full(len(cont), np.inf)
            for eq in h.equations:  # distance inside each hull facet's line; the deficit is the least of them
                dmin = np.minimum(dmin, -(cont @ eq[:2] + eq[2]))
            out[side] = max(out[side], round(float(dmin.max()) * 1000, 2))
    return out


NECK_AT = 0.35  # the neck's girth is taken this share of the way from the neck joint up to the body's chin


def _neck_girth(tpl: dict) -> float:
    """The neck's girth at ONE level (NECK_AT of the way from the neck joint to the body's own chin vertex), on the
    body's and the bridge's vertices only. (anthro's minimum over the levels up to the chin took the jaw in whenever
    a fit moved the chin: "neck_circ -9 cm" UNINTENDED in every face fit.)"""
    from scipy.spatial import ConvexHull
    P = np.asarray(tpl["P"], float)[: int(tpl["n_body"])]
    zn = float(np.asarray(tpl["J"]["neck"])[2])
    zl = zn + NECK_AT * (float(tpl["chin_mh"]) - zn)
    sh = abs(float(np.asarray(tpl["J"]["shoulder.L"])[0]))
    s = P[(np.abs(P[:, 2] - zl) < 0.004) & (np.abs(P[:, 0]) < 0.6 * sh)][:, :2]
    if len(s) < 4:
        return float("nan")
    h = ConvexHull(s)
    q = s[h.vertices]
    return float(np.linalg.norm(q - np.roll(q, 1, 0), axis=1).sum())


def measures(base: dict) -> dict:
    return state(base)["measures"]


def value(m: dict, name: str) -> float:
    """A measure, or a ratio "a/b"."""
    if "/" in name:
        a, b = name.split("/")
        return m[a.strip()] / m[b.strip()]
    if name not in m:
        raise ValueError(f"humanfit: no measure {name!r} (have {', '.join(m)}; ratios as \"a/b\")")
    return m[name]


def identity(base: dict) -> np.ndarray:
    """The head's GNM identity components as the solver sees them (headfit's 120, sigma units)."""
    from . import headfit, onemesh
    g = headfit._gnm()
    idn = onemesh.head_desc(base).get("identity") or {}
    return np.array([float(idn.get(g["names"][i], 0.0)) for i in g["comps"]])


def plausibility(base: dict) -> dict:
    c = identity(base)
    return {"rms_sigma": float(np.sqrt((c ** 2).mean())), "max_sigma": float(np.abs(c).max()),
            "over": int((np.abs(c) > CLIP + 1e-6).sum())}


def _lm_basis(st: dict) -> np.ndarray:
    """d(L, world) / d(identity component): (120, 70, 3). The landmarks are linear in the components; the head stays
    hung on its eye midpoint."""
    from . import headfit
    g = headfit._gnm()
    c = st["head"]["carry"]
    R, s = np.asarray(c["R"], float), float(c["s"])
    LB = np.concatenate([g["LB"][:, :68], g["JB"]], axis=1)  # (120, 70, 3), GNM's frame
    if g["J0"][0][0] < g["J0"][1][0]:
        LB[:, [EYE_L, EYE_R]] = LB[:, [EYE_R, EYE_L]]
    LB = LB - g["JB"].mean(1, keepdims=True)
    return s * LB @ R.T


def _skull_basis(st: dict) -> np.ndarray:
    """d(skull points, world) / d(identity component): (120, n, 3), for headfit's cranium points and its dense pairs
    more than 4 cm from every face landmark (crown, back of the head, neck). The 68 landmarks don't see these: an
    image fit that isn't told to hold them moves the skull by centimetres unseen."""
    from . import headfit
    g = headfit._gnm()
    c = st["head"]["carry"]
    R, s_ = np.asarray(c["R"], float), float(c["s"])
    L0 = g["L0"]
    d = np.linalg.norm(L0[68:, None] - L0[None, :68], axis=-1).min(1)
    sel = 68 + np.flatnonzero((d > 0.04) | (np.arange(len(L0) - 68) < 4))
    LB = g["LB"][:, sel] - g["JB"].mean(1, keepdims=True)
    return s_ * LB @ R.T


def _with_identity(base: dict, c: np.ndarray) -> dict:
    from . import headfit
    g = headfit._gnm()
    out = copy.deepcopy(base)
    hd = out.setdefault("head", {})
    # everything the head's identity is made of is written out (the seed and features are in it already)
    from . import onemesh
    cur = onemesh.head_desc(base)
    idn = dict(cur.get("identity") or {})
    for i, v in zip(g["comps"], c):
        idn[str(g["names"][i])] = round(float(v), 4)
    hd["identity"] = idn
    return out


def _parse(m0: dict, want: dict) -> dict:
    out = {}
    for k, v in want.items():
        cur = value(m0, k)
        if isinstance(v, str):
            v = v.strip()
            out[k] = cur * float(v[1:]) if v[0] in "x*" else cur + float(v) if v[0] in "+-" else float(v)
        else:
            out[k] = float(v)
    return out


def _tol(name: str, v: float) -> float:
    if "/" in name:
        return max(abs(v) * 0.01, 1e-4)
    return TOL_MM if name in FACE else max(abs(v) * 0.005, 0.05)


def solve(base: dict, want: dict, free=("identity",), hold: bool = True, force: bool = False, rounds: int = 5,
          release=()) -> tuple:
    """(new base, report). want: {measure or "a/b": value | "+2" | "-1.5" | "x1.1"}. free: "identity" (the face),
    "body" (weight, muscle, height). release: measures let go (not held). See the module docstring."""
    st0 = state(base)
    m0 = st0["measures"]
    tgt = _parse(m0, want)
    asked = set(tgt)
    asked_parts = {p.strip() for k in asked for p in k.split("/")}
    cur = copy.deepcopy(base)
    clip = CLIP_FORCE if force else CLIP
    use_id = "identity" in free and any(p in FACE for p in asked_parts)
    use_body = "body" in free
    bkeys = [k for k in BODY_FREE if k != "height" or any(p in ("stature", "heads") for p in asked_parts)] if use_body else []
    c0 = identity(base)
    c = c0.copy()
    L0 = st0["L"]
    held = [k for k in m0 if hold and k not in asked_parts and k not in release]
    pts = sorted({i for p in asked_parts if p in FACE for i in _points(p)})
    far = np.ones(70)
    if pts:
        dmin = np.linalg.norm(L0[:, None] - L0[pts][None], axis=-1).min(1)
        far = np.clip(dmin / 0.05, 0, 1)
    log = []
    for it in range(rounds):
        st = state(cur) if it else st0
        m, L = st["measures"], st["L"]
        res = np.array([(value(m, k) - tgt[k]) / _tol(k, tgt[k]) for k in tgt])
        log.append(float(np.abs(res).max()))
        if np.abs(res).max() < 1.0 and it:
            break
        cols, rows, rhs = [], [], []
        B = _lm_basis(st) if use_id else np.zeros((0, 70, 3))

        def jac_face(name):  # d measure / d components
            G = face_gradient(name, L)
            return np.tensordot(B, G, axes=([1, 2], [0, 1])) if use_id else np.zeros(0)
        Jb = {}
        if bkeys:  # the body's macros by finite differences (each a body build)
            for bk in bkeys:
                b2 = copy.deepcopy(cur)
                v0 = float(b2["body"].get(bk) or (st["measures"]["stature"] / 100 if bk == "height" else 0.5))
                h = 0.01 if bk == "height" else 0.04
                b2["body"][bk] = v0 + h
                m2 = state(b2)["measures"]
                Jb[bk] = {k: (m2[k] - m[k]) / h for k in m}

        def jac(name):
            if "/" in name:
                a, b = (p.strip() for p in name.split("/"))
                ja, jb = jac(a), jac(b)
                return ja / m[b] - m[a] / m[b] ** 2 * jb
            jf = jac_face(name) if name in FACE else np.zeros(len(c) if use_id else 0)
            return np.r_[jf, [Jb[bk][name] for bk in bkeys]]
        nv = (len(c) if use_id else 0) + len(bkeys)
        if nv == 0:
            raise ValueError(f"humanfit: nothing free can move {sorted(asked)} (free = {list(free)}; face measures need "
                             '"identity", body measures "body")')
        A, y = [], []
        for k in tgt:
            A.append(jac(k) / _tol(k, tgt[k]))
            y.append(-(value(m, k) - tgt[k]) / _tol(k, tgt[k]))
        for k in held:  # what wasn't asked for stays where it WAS (not where it is after the last step)
            w = HOLD / (1.0 if k in FACE else max(abs(m0[k]) * 0.01, 1e-3))
            A.append(jac(k) * w)
            y.append(-(m[k] - m0[k]) * w)
        if use_id and hold:  # landmarks far from the asked ones stay in place
            W = (HOLD_LM * 1000.0 * far)[None, :, None]
            A.extend(list(np.c_[(B * W).reshape(len(c), -1).T, np.zeros((210, len(bkeys)))]))
            y.extend(list(-((L - L0) * W[0]).reshape(-1)))
        if use_id and hold:  # ... and the skull, which no face measure sees
            S = _skull_basis(st)
            Sm = (S * (HOLD_SKULL * 1000.0)).reshape(len(c), -1).T
            A.extend(list(np.c_[Sm, np.zeros((Sm.shape[0], len(bkeys)))]))
            y.extend(list(-(Sm @ (c - c0))))
        for i in range(nv):  # each step is ridged toward the current state; components also toward what they were
            e = np.zeros(nv)
            e[i] = RIDGE if i < (len(c) if use_id else 0) else 2.0
            A.append(e)
            y.append((RIDGE * (c0[i] - c[i])) * 0.5 if i < (len(c) if use_id else 0) else 0.0)
        dx = np.linalg.lstsq(np.array(A, float), np.array(y, float), rcond=None)[0]
        if use_id:
            c = np.clip(c + dx[:len(c)], -max(clip, np.abs(c0).max()), max(clip, np.abs(c0).max()))
            cur = _with_identity(cur, c)
        for j, bk in enumerate(bkeys):
            v0 = float(cur["body"].get(bk) or (m["stature"] / 100 if bk == "height" else 0.5))
            v = v0 + float(dx[(len(c) if use_id else 0) + j])
            cur["body"][bk] = round(float(v if bk == "height" else np.clip(v, 0.0, 1.0)), 4)
    held_back = 1.0
    if use_id and hold and not force and held:
        # the guard rail: the step is cut back to where no measure that WASN'T asked for moves more than COLLATERAL x
        # its tolerance (the landmarks are linear in the components, so this is read off the first Jacobian). A
        # request the face can't meet without wrecking the rest comes back partly met, with the residual.
        B0 = _lm_basis(st0)
        dL = np.tensordot(c - c0, B0, axes=(0, 0))
        worst = 0.0
        for k in held:
            if k in FACE:
                worst = max(worst, abs(float((face_gradient(k, L0) * dL).sum())) / UNINTENDED_MM)
        if worst > COLLATERAL:
            held_back = COLLATERAL / worst
            c = c0 + held_back * (c - c0)
            cur = _with_identity(cur, c)
    st1 = state(cur)
    m1 = st1["measures"]
    resid = {k: {"asked": round(tgt[k], 3), "got": round(value(m1, k), 3), "was": round(value(m0, k), 3),
                 "met": bool(abs(value(m1, k) - tgt[k]) <= _tol(k, tgt[k]) * 1.5)} for k in tgt}
    rep = {"asked": resid, "rounds": len(log), "plausibility": plausibility(cur), "held_back": round(held_back, 3),
           "limited": bool(use_id and (np.abs(c) >= clip - 1e-6).any() and not all(r["met"] for r in resid.values())),
           "side_effects": side_effects(st0, st1, asked_parts), "integrity": integrity(cur, st1, st0)}
    return cur, rep


def nudge(base: dict, landmark: str | int, move=None, to=None, radius: float = 0.015, force: bool = False) -> tuple:
    """(new base, report): one landmark moved by `move` [x, y, z] m (or to a world point), every other landmark held.
    The identity components take what they can within the plausible range; the rest is a smooth correction at that
    landmark (base.head.shape.push_more) and reported as what the sliders can't do."""
    st0 = state(base)
    i = LANDMARKS[landmark] if isinstance(landmark, str) else int(landmark)
    L0 = st0["L"]
    mv = np.asarray(move, float) if move is not None else np.asarray(to, float) - L0[i]
    c0 = identity(base)
    B = _lm_basis(st0)
    far = np.clip(np.linalg.norm(L0 - L0[i], axis=1) / 0.04, 0, 1)
    mir = None
    if abs(L0[i, 0]) > 0.004:  # a side landmark: its mirror moves the mirrored way (asymmetry must be asked for)
        mir = int(np.argmin(np.linalg.norm(L0[:68] - L0[i] * [-1, 1, 1], axis=1)))
        far[mir] = 0.0
    A, y = [], []
    for j in range(70):
        w = 20.0 if j in (i, mir) else HOLD_LM * 8 * far[j]
        t = mv if j == i else mv * [-1, 1, 1] if j == mir else np.zeros(3)
        for a in range(3):
            A.append(B[:, j, a] * w * 1000)
            y.append(t[a] * w * 1000)
    Sm = (_skull_basis(st0) * (HOLD_SKULL * 1000.0)).reshape(len(c0), -1).T
    A.extend(list(Sm))
    y.extend([0.0] * Sm.shape[0])
    for k in range(len(c0)):
        e = np.zeros(len(c0))
        e[k] = RIDGE * 2
        A.append(e)
        y.append(0.0)
    dc = np.linalg.lstsq(np.array(A), np.array(y), rcond=None)[0]
    clip = CLIP_FORCE if force else CLIP
    c = np.clip(c0 + dc, -max(clip, np.abs(c0).max()), max(clip, np.abs(c0).max()))
    cur = _with_identity(base, c)
    st1 = state(cur)
    rest = mv - (st1["L"][i] - L0[i])
    corr = float(np.linalg.norm(rest))
    if corr > 0.0003:  # what the components couldn't: a Gaussian push at the landmark, along what is left
        sh = cur["head"].setdefault("shape", {})
        on_centre = abs(st1["L"][i, 0]) < 0.004  # (a centre-line landmark a hair off x = 0 was pushed twice: itself and
        # its "mirror")
        sh["push_more"] = list(sh.get("push_more") or []) + [{"lm": [i if i < 68 else 30], "radius": round(float(radius), 4),
                                                                  **({"offset": [round(-float(st1["L"][i, 0]), 6), 0, 0]} if on_centre else {}),
                                                                  "amount": round(corr, 5), "dir": [round(float(x), 4) for x in rest / corr],
                                                                  "note": f"nudge {landmark}: beyond the identity sliders"}]
        st1 = state(cur)
    got = st1["L"][i] - L0[i]
    rep = {"landmark": landmark, "asked_mm": (mv * 1000).round(2).tolist(), "got_mm": (got * 1000).round(2).tolist(),
           "by_sliders_mm": round(float(np.linalg.norm(mv - rest)) * 1000, 2), "by_correction_mm": round(corr * 1000, 2),
           "plausibility": plausibility(cur), "side_effects": side_effects(st0, st1, set(), near=L0[[i] + ([mir] if mir is not None else [])]),
           "integrity": integrity(cur, st1, st0)}
    return cur, rep


def side_effects(st0: dict, st1: dict, asked: set, near=None) -> dict:
    """What changed between two states: every measure before -> after (sorted by how far it moved, in units of its
    own tolerance), those that moved without being asked flagged, and where the vertices went."""
    m0, m1 = st0["measures"], st1["measures"]
    rows = []
    for k in m0:
        d = m1[k] - m0[k]
        lim = UNINTENDED_MM if k in FACE else max(abs(m0[k]) * UNINTENDED_BODY, 1e-6)
        rows.append({"measure": k, "was": round(m0[k], 2), "now": round(m1[k], 2), "moved": round(d, 2),
                     "unit": "mm" if k in FACE else ("" if k == "heads" else "cm"),
                     "flag": "asked" if k in asked else "UNINTENDED" if abs(d) > lim else "", "rel": abs(d) / lim})
    rows.sort(key=lambda r: -r["rel"])
    P0, P1 = np.asarray(st0["tpl"]["P"]), np.asarray(st1["tpl"]["P"])
    out = {"measures": rows, "unintended": [r["measure"] for r in rows if r["flag"] == "UNINTENDED"]}
    if P0.shape == P1.shape:
        d = np.linalg.norm(P1 - P0, axis=1)
        nb = st0["tpl"]["n_body"]
        pts = near
        if pts is None:
            ids = sorted({i for p in asked if p in FACE for i in _points(p)})
            pts = st0["L"][ids] if ids else None
        outside = np.zeros(len(d), bool)
        if pts is not None and len(pts):
            dm = np.linalg.norm(P0[:, None] - np.asarray(pts)[None], axis=-1).min(1)
            outside = dm > 0.05
        out["moved"] = {"max_mm": round(float(d.max()) * 1000, 2), "head_mean_mm": round(float(d[nb:].mean()) * 1000, 3),
                        "body_max_mm": round(float(d[:nb].max()) * 1000, 3),
                        "over_1mm_share": round(float((d > 0.001).mean()), 4),
                        "outside_region_over_1mm": int(((d > 0.001) & outside).sum()),
                        "outside_region_share": round(float(((d > 0.001) & outside).sum() / max(len(d), 1)), 4)}
    return out


def _regions(tpl: dict) -> dict:
    """Named regions of the template's vertices (bool masks)."""
    from . import base as basemod
    from . import onemesh
    a = onemesh.asset()
    g = basemod._gnm_data()
    gid = a["gnm_id"][tpl["fid"]]
    G = {k: (np.asarray(v) > 0.5) for k, v in g["groups"].items()}
    pick = lambda *names: np.where(gid >= 0, np.any([G[n][np.maximum(gid, 0)] for n in names], axis=0), False)  # noqa: E731
    n0 = int(a["bridge"][0])
    return {"lids": pick("left_orbital_region", "right_orbital_region", "eye_sockets"), "lips": pick("upper_lip", "lower_lip"),
            "nose": pick("nose_region"), "ears": pick("ears"),
            "neck bridge": (tpl["fid"] >= n0) | np.isin(tpl["fid"], np.r_[a["loop_a"], a["loop_c"]]),
            "face": pick("hockey_mask"), "head": gid >= 0, "body": a["mh_id"][tpl["fid"]] >= 0}


def integrity(base: dict, st: dict | None = None, prev: dict | None = None) -> dict:
    """{"ok", "broken": [...], "warnings": [...], "numbers"}: see the module docstring. Compared against the same body
    with a plain head (no identity, features, pose or style), so a child's small head isn't 'compressed'."""
    from . import onemesh
    st = st or state(base)
    tpl, ht = st["tpl"], st["head"]
    key = ("integrity_ref", json.dumps(onemesh.body_params(base), sort_keys=True, default=float))
    ref = onemesh._CACHE.get(key)
    if ref is None:
        ref = onemesh._CACHE[key] = onemesh.template({"body": dict(base["body"]), "head": {"dimorphism": 0}})
    if ht.get("lips_zipped"):  # closed lips are zipped, and the weld depends on the shape: both heads unzipped here
        tpl = onemesh.template({**base, "head": {**(base.get("head") or {}), "zip_lips": False}})
        key = key + (base["head"].get("mouth_gap"),)
        ref = onemesh._CACHE.get(key)
        if ref is None:
            ref = onemesh._CACHE[key] = onemesh.template({"body": dict(base["body"]), "head": {
                "dimorphism": 0, "mouth_gap": base["head"].get("mouth_gap"), "zip_lips": False}})
    P, P0 = np.asarray(tpl["P"], float), np.asarray(ref["P"], float)
    Lf, Sf = np.asarray(tpl["L"]), np.asarray(tpl["S"])
    st_ = np.r_[0, np.cumsum(Sf)[:-1]]
    F = np.stack([Lf[st_], Lf[st_ + 1], Lf[st_ + 2], Lf[st_ + Sf - 1]], 1)  # (a triangle: its last corner twice)
    broken, warn, num = [], [], {}
    same = P.shape == P0.shape and np.array_equal(np.asarray(ref["L"]), np.asarray(tpl["L"]))
    reg = _regions(tpl)
    if not np.isfinite(P).all():
        broken.append("the mesh has NaNs")
    if same:
        def fn(X):
            return np.cross(X[F[:, 2]] - X[F[:, 0]], X[F[:, 3]] - X[F[:, 1]])
        n1, n0 = fn(P), fn(P0)
        dot = (n1 * n0).sum(1) / np.maximum(np.linalg.norm(n1, axis=1) * np.linalg.norm(n0, axis=1), 1e-30)
        flip = dot < 0.0
        num["turned_faces"] = int(flip.sum())

        def where_(mask):
            w_ = {k: int(mask[v[F].any(1)].sum()) for k, v in reg.items() if k not in ("head", "body", "face")}
            return ", ".join(f"{k} {v}" for k, v in w_.items() if v) or "head"
        Pp = None
        if prev is not None:
            ptpl = prev["tpl"] if not ht.get("lips_zipped") else onemesh.template(
                {**prev["base"], "head": {**(prev["base"].get("head") or {}), "zip_lips": False}})
            if np.asarray(ptpl["P"]).shape == P.shape:
                Pp = np.asarray(ptpl["P"], float)
        if Pp is not None:
            # an EDIT's folds: faces that turned over against the state before it
            np_ = fn(Pp)
            new = (n1 * np_).sum(1) < 0
            num["folded_faces"] = int(new.sum())
            if new.sum() >= FOLD_LIMIT:
                broken.append(f"{int(new.sum())} faces folded over by this change ({where_(new)})")
            elif new.any():  # (one or two tiny faces inside the lips or lids turn with any change of shape)
                warn.append(f"{int(new.sum())} small faces turned over by this change ({where_(new)})")
        elif flip.sum() > 40:  # against the plain head lids and lips legitimately turn a few faces (an open lid rolls)
            warn.append(f"{int(flip.sum())} faces face the other way than on the plain head ({where_(flip)})")
        E = np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 3]], F[:, [3, 0]]]
        l1 = np.linalg.norm(P[E[:, 0]] - P[E[:, 1]], axis=1)
        l0 = np.maximum(np.linalg.norm(P0[E[:, 0]] - P0[E[:, 1]], axis=1), 1e-9)
        r = l1 / l0
        hsel = reg["head"][E].all(1)
        if hsel.any():  # a style's bigger head is a scale, not a distortion: stretch is read against the head's own size
            num["head_scale"] = round(float(np.median(r[hsel])), 3)
            r = np.where(hsel, r / max(float(np.median(r[hsel])), 1e-6), r)
        num["stretch"] = {}
        for k in ("lids", "lips", "nose", "ears", "neck bridge", "face"):
            sel = reg[k][E].all(1)
            if sel.any():
                lo, hi = float(r[sel].min()), float(np.percentile(r[sel], 99.5))
                num["stretch"][k] = [round(lo, 2), round(hi, 2)]
                if hi > 3.0 or lo < 0.25:
                    broken.append(f"{k}: edges stretched x{hi:.1f} / squeezed x{lo:.2f} against the plain head")
                elif hi > 1.8 or lo < 0.45:
                    warn.append(f"{k}: edges stretched x{hi:.1f} / squeezed x{lo:.2f}")
    else:
        warn.append("this head's topology differs from the plain head's: stretch and folds not compared")
    L = st["L"]
    r_eye = float(ht["eye_r"])
    for side, c, rim in (("left", L[EYE_L], L[42:48]), ("right", L[EYE_R], L[36:42])):
        d = np.linalg.norm(rim - c, axis=1)
        if d.min() < r_eye - 0.0005:
            broken.append(f"{side} eyeball through its lids by {1000 * (r_eye - d.min()):.1f} mm")
        if d.max() > r_eye + 0.006:
            warn.append(f"{side} lids stand {1000 * (d.max() - r_eye):.1f} mm off the eyeball")
    num["mouth_gap_mm"] = round(float(L[62, 2] - L[66, 2]) * 1000, 2)
    if L[62, 2] - L[66, 2] < -0.0008:
        broken.append(f"the lips cross by {-num['mouth_gap_mm']:.1f} mm")
    if st["measures"]["eye_height"] < 2.0:
        warn.append(f"the eyes are nearly shut ({st['measures']['eye_height']:.1f} mm)")
    asym = float(np.abs(L[:68] - L[_mirror68()] * [-1, 1, 1]).max()) * 1000
    num["asymmetry_mm"] = round(asym, 2)
    pl = plausibility(base)
    num["plausibility"] = pl
    if pl["max_sigma"] > CLIP + 1e-6:
        warn.append(f"identity components up to {pl['max_sigma']:.1f} sigma ({pl['over']} past {CLIP}): outside the plausible range")
    if pl["rms_sigma"] > 1.6:
        warn.append(f"the identity is {pl['rms_sigma']:.2f} sigma rms from the mean (a seed at spread 1 is 1.0)")
    return {"ok": not broken, "broken": broken, "warnings": warn, "numbers": num}


def _mirror68() -> np.ndarray:
    m = np.arange(68)
    for a, b in ([(i, 16 - i) for i in range(8)] + [(17 + i, 26 - i) for i in range(5)] + [(31, 35), (32, 34), (36, 45), (37, 44),
                 (38, 43), (39, 42), (40, 47), (41, 46), (48, 54), (49, 53), (50, 52), (59, 55), (58, 56), (60, 64), (61, 63), (67, 65)]):
        m[a], m[b] = b, a
    return m


def verdict(integ: dict) -> str:
    lines = ["INTEGRITY: ok" if integ["ok"] else "BROKEN: " + "; ".join(integ["broken"])]
    lines += ["WARNING: " + w for w in integ["warnings"]]
    return "\n".join(lines)


def table(m: dict, ref: dict | None = None) -> str:
    body = "  ".join(f"{k} {m[k]:.1f}" for k in BODY if k in m)
    face = "  ".join(f"{k} {m[k]:.1f}" for k in FACE)
    r = lambda a, b: m[a] / m[b]  # noqa: E731
    ratios = (f"eye_width/face_width {r('eye_width', 'face_width'):.3f}  eye_to_chin/face_width {r('eye_to_chin', 'face_width'):.3f}  "
              f"interocular/face_width {r('interocular', 'face_width'):.3f}  nose_width/mouth_width {r('nose_width', 'mouth_width'):.3f}  "
              f"jaw_width/face_width {r('jaw_width', 'face_width'):.3f}  chin_height/philtrum {r('chin_height', 'philtrum'):.2f}")
    return f"body (cm; heads = stature / head height): {body}\nface (mm): {face}\nratios: {ratios}"


def effects_text(se: dict, top: int = 12) -> str:
    rows = [r for r in se["measures"] if abs(r["moved"]) > 1e-9][:top]
    lines = []
    if se["unintended"]:
        lines.append("UNINTENDED: " + ", ".join(f"{r['measure']} {r['moved']:+.1f} {r['unit']}".strip() for r in se["measures"]
                                                 if r["flag"] == "UNINTENDED"))
    lines.append("what moved (was -> now): " + ("; ".join(f"{r['measure']} {r['was']:g} -> {r['now']:g}{' (' + r['flag'] + ')' if r['flag'] else ''}"
                                                           for r in rows) or "nothing"))
    mv = se.get("moved")
    if mv:
        lines.append(f"vertices: max {mv['max_mm']} mm, head mean {mv['head_mean_mm']} mm, body max {mv['body_max_mm']} mm, "
                     f"{100 * mv['over_1mm_share']:.1f}% moved over 1 mm, {mv['outside_region_over_1mm']} of them "
                     f"({100 * mv['outside_region_share']:.1f}% of the mesh) more than 5 cm from what was asked")
    return "\n".join(lines)


# ---- reference images: cameras and the face fitted together on named 2D points --------------------------------------

def point_index(name) -> int:
    if isinstance(name, (int, np.integer)):
        return int(name)
    if name in LANDMARKS:
        return LANDMARKS[name]
    if name in ("eye.L", "eye_centre.L"):
        return EYE_L
    if name in ("eye.R", "eye_centre.R"):
        return EYE_R
    if str(name).startswith("lm") and str(name)[2:].isdigit():
        return int(str(name)[2:])
    raise ValueError(f"humanfit: no landmark {name!r} (have {', '.join(LANDMARKS)}, eye.L, eye.R, lm0..lm67 = the 68-point "
                     "face convention)")


def _rotvec(r):
    th = float(np.linalg.norm(r))
    if th < 1e-12:
        return np.eye(3)
    k = np.asarray(r, float) / th
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + np.sin(th) * K + (1 - np.cos(th)) * K @ K


_CAM0 = np.array([[1.0, 0, 0], [0, 0, -1.0], [0, 1.0, 0]])  # world -> camera for a camera in front (looking +Y)


def _cam_rot(cam: dict) -> np.ndarray:
    return _rotvec(np.asarray(cam["r"], float)) @ _CAM0 @ _rotvec([0, 0, np.radians(cam.get("yaw", 0.0))])


def project(cam: dict, X: np.ndarray) -> np.ndarray:
    """World points -> pixels (u right, v down) through a fitted camera {"r", "t", "f", "size", "centre", "yaw"}."""
    Xc = (np.asarray(X, float) - np.asarray(cam["centre"], float)) @ _cam_rot(cam).T + np.asarray(cam["t"], float)
    w, h = cam["size"]
    return np.stack([cam["f"] * Xc[:, 0] / Xc[:, 2] + w / 2, cam["f"] * Xc[:, 1] / Xc[:, 2] + h / 2], 1)


OUTLINE_W = 0.6  # weight of an outline point against a landmark


def _silhouette(st: dict, cam: dict, outline: np.ndarray, skip_ears: bool = True) -> dict | None:
    """The head's silhouette through a camera matched to a reference outline: for each outline point (pixels) the
    nearest silhouette vertex of the head (edges between faces turned toward and away from the camera; GNM's own
    vertices above the stitch), its world position, how it moves per identity component (as the landmarks:
    _lm_basis) and the outline's normal there. None if nothing matched."""
    from . import base as basemod
    from . import headfit, onemesh
    from scipy.spatial import cKDTree
    tpl, c = st["tpl"], st["head"]["carry"]
    P = np.asarray(tpl["P"], float)
    gid = np.asarray(onemesh.asset()["gnm_id"], int)[np.asarray(tpl["fid"])]
    fade = np.asarray(onemesh.asset()["g_fade"], float)
    head = (gid >= 0) & (fade[np.maximum(gid, 0)] > 0.3)
    if skip_ears:  # an ear's rim is silhouette too, and no face outline follows it
        ears = np.asarray(basemod._gnm_data()["groups"]["ears"], float) > 0.5
        head &= ~ears[np.maximum(gid, 0)]
    T = np.array([(f[0], f[j], f[j + 1]) for f in _faces(tpl) for j in range(1, len(f) - 1)])
    T = T[head[T].all(1)]
    Rc = _cam_rot(cam)
    Xc = (P - np.asarray(cam["centre"], float)) @ Rc.T + np.asarray(cam["t"], float)
    n = np.cross(Xc[T[:, 1]] - Xc[T[:, 0]], Xc[T[:, 2]] - Xc[T[:, 0]])
    front = (n * Xc[T].mean(1)).sum(1) < 0
    edges = {}
    for t, f in zip(T, front):
        for k in range(3):
            e = (min(t[k], t[(k + 1) % 3]), max(t[k], t[(k + 1) % 3]))
            edges.setdefault(e, []).append(bool(f))
    sv = np.unique([v for e, fs in edges.items() if len(fs) == 2 and fs[0] != fs[1] for v in e])
    if not len(sv):
        return None
    uv = project(cam, P[sv])
    o = np.asarray(outline, float)
    tan = np.gradient(o, axis=0)
    nrm = np.c_[-tan[:, 1], tan[:, 0]]
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)
    d, j = cKDTree(uv).query(o)
    ok = d < 0.06 * max(cam["size"])
    if not ok.any():
        return None
    vs = sv[j[ok]]
    g = headfit._gnm()
    Bv = np.asarray(basemod._gnm_data()["vertex_identity_basis"], float)[g["comps"]][:, gid[vs]]
    Bv = float(c["s"]) * (Bv - g["JB"].mean(1, keepdims=True)) @ np.asarray(c["R"], float).T
    Bv = Bv * fade[gid[vs]][None, :, None]
    return {"X": P[vs], "B": Bv, "p": o[ok], "n": nrm[ok]}


STRUCTURE_SOFT = 0.25  # weight of an outline target on the soft mid-cheek (structure mode)
STRUCTURE_HOLD = 1.0   # weight of holding the cheeks' fronts (structure mode)


def _gnm_normals(Vg: np.ndarray) -> np.ndarray:
    """Vertex normals of GNM's mesh at positions Vg (GNM's frame: facing +z, y up)."""
    from . import base as basemod
    from . import retopo
    q = np.asarray(basemod._gnm_data()["quads"])
    T = np.r_[q[:, [0, 1, 2]], q[:, [0, 2, 3]]]
    return retopo._vnormals(Vg, T)


OUTLINE_SIGMA = 0.022   # GNM units: the outline warp's reach (a jaw, a cheekbone: no single feature)
OUTLINE_STEP = 0.004    # m: the most an outline point is moved in one round
OUTLINE_HOLD = 0.6      # weight of the features held where they are (eyes, nose, lips, brows) against the outline


def fit_outline(base: dict, views: list, cameras: list, rounds: int = 3, symmetric: bool = True,
                structure: bool = True) -> tuple:
    """(new base, report): the head's silhouette through each fitted camera (`cameras`, from fit_views) pulled onto
    each view's `outline` ([[u, v], ...]: the face's edge in the picture, e.g. jaw and cheeks) by a smooth warp in
    GNM's frame (base.head.warp, appended), the features held (eyes, nose, lips, brows: their landmarks stay, so an
    outline can't drag the mouth). Each silhouette vertex's 2D miss along the outline's normal becomes a 3D move in
    the camera's image plane at its depth. Identity components are left to fit_views (the points).
    A view may carry "outline_axis": "y" (only the outline's up / down misses count: a painting's camera is too loose
    for widths, its jaw angle's and cheekbone's heights still read) and "outline_weight".
    structure: width is BONE (cheekbones, jaw angles, temples, chin): targets on the soft mid-cheek count
    STRUCTURE_SOFT, and the cheek's front (GNM's cheek regions, facing forward) is held where it is, so the warp
    widens the head's sides instead of filling the cheeks (pass 2 without it: a pear-shaped, jowly face)."""
    from . import base as basemod
    from . import onemesh
    g = basemod._gnm_data()
    cur = copy.deepcopy(base)
    names = [str(n) for n in g["identity_names"]]
    rep = {"rounds": []}
    for rnd in range(rounds):
        st = state(cur)
        hd = onemesh.head_desc(cur)
        c = st["head"]["carry"]
        Rh, s = np.asarray(c["R"], float), float(c["s"])
        idn = dict(basemod.fit_identity(hd["fit"])) if hd.get("fit") else {}
        idn.update(hd.get("identity") or {})
        call = np.array([float(idn.get(n, 0.0)) for n in names])
        Vg = np.asarray(g["template_vertex_positions"], float) + np.tensordot(call, np.asarray(g["vertex_identity_basis"], float), 1)
        gid = np.asarray(onemesh.asset()["gnm_id"], int)[np.asarray(st["tpl"]["fid"])]
        fade = np.asarray(onemesh.asset()["g_fade"], float)
        tgt_g, tgt_d, tgt_w, miss = [], [], [], []
        soft = np.zeros(len(Vg))
        if structure:
            soft = np.clip(np.asarray(g["groups"]["left_cheek_region"], float) + np.asarray(g["groups"]["right_cheek_region"], float), 0, 1)
        for v, cam in zip(views, cameras):
            if not v.get("outline"):
                continue
            sl = _silhouette(st, cam, np.asarray(v["outline"], float))
            if sl is None:
                continue
            uv = project(cam, sl["X"])
            r = ((uv - sl["p"]) * sl["n"]).sum(1)  # px past the outline along its normal
            Rc = _cam_rot(cam)
            Xc = (sl["X"] - np.asarray(cam["centre"], float)) @ Rc.T + np.asarray(cam["t"], float)
            m = r * Xc[:, 2] / cam["f"]  # m in the image plane at the vertex's depth
            nn = sl["n"].copy()
            if v.get("outline_axis") == "y":  # heights only: the miss along the image's vertical
                m = m * nn[:, 1]
                nn = np.c_[np.zeros(len(nn)), np.sign(nn[:, 1]) + (nn[:, 1] == 0)]
            w = nn[:, :1] * Rc[0] + nn[:, 1:] * Rc[1]  # the outline's normal as a world direction
            dW = -np.clip(m, -OUTLINE_STEP, OUTLINE_STEP)[:, None] * w  # (a round moves no point further: a silhouette
            # vertex matched across a gap the first round would throw the warp)
            P = np.asarray(st["tpl"]["P"], float)
            vs = np.array([int(np.argmin(np.linalg.norm(P - x, axis=1))) for x in sl["X"]])
            for k, vi in enumerate(vs):
                gi = gid[vi]
                if gi < 0 or fade[gi] < 0.3:
                    continue
                dg = (dW[k] @ Rh) / s / fade[gi]
                dg[0] /= float(c["narrow"])
                tgt_g.append(Vg[gi])
                tgt_d.append(dg)
                tgt_w.append(float(v.get("outline_weight", 1.0)) * (1.0 - (1.0 - STRUCTURE_SOFT) * soft[gi]))
            miss.append(float(np.sqrt((m ** 2).mean()) * 1000))
        if not tgt_g:
            break
        if symmetric:  # each target also on the other side, mirrored (GNM's template is symmetric about x = 0): one
            # view's outline alone warped only its own side, a lump on one jaw
            tgt_g = tgt_g + [x * [-1, 1, 1] for x in tgt_g]
            tgt_d = tgt_d + [x * [-1, 1, 1] for x in tgt_d]
            tgt_w = tgt_w + tgt_w
        hold = []
        for row in g["lm68"][17:]:  # brows, nose, eyes, lips stay
            hold.append(sum(float(wt) * Vg[int(vi)] for vi, wt in zip(row[0::2], row[1::2])))
        # and the rest of the head where it is: skin vertices farther than two reaches from every target
        skin = np.flatnonzero(np.asarray(g["skin"], bool))
        far = skin[np.min(np.linalg.norm(Vg[skin][:, None] - np.array(tgt_g)[None], axis=2), 1) > 2 * OUTLINE_SIGMA]
        far = far[np.linspace(0, len(far) - 1, min(len(far), 160)).astype(int)] if len(far) else far
        hold += list(Vg[far])
        hw = [OUTLINE_HOLD] * len(hold)
        if structure:  # the cheeks' fronts stay
            front = skin[(soft[skin] > 0.5) & (_gnm_normals(Vg)[skin][:, 2] > 0.35)]
            front = front[np.linspace(0, len(front) - 1, min(len(front), 120)).astype(int)] if len(front) else front
            hold += list(Vg[front])
            hw += [STRUCTURE_HOLD] * len(front)
        A = np.r_[np.array(tgt_g), np.array(hold)]
        Dt = np.r_[np.array(tgt_d), np.zeros((len(hold), 3))]
        wt = np.r_[np.array(tgt_w), np.array(hw)]
        sig = float((cur.get("head") or {}).get("warp", {}).get("sigma", OUTLINE_SIGMA))
        K = np.exp(-((A[:, None] - A[None]) ** 2).sum(-1) / (2 * sig ** 2))
        coef = np.linalg.solve((K * wt[:, None]).T @ K + 2e-2 * np.eye(len(A)), (K * wt[:, None]).T @ Dt)
        h = cur.setdefault("head", {})
        old = h.get("warp")
        if old:  # (a head has one warp: its centres appended, at its sigma)
            A, coef = np.r_[np.asarray(old["at"], float), A], np.r_[np.asarray(old["coef"], float), coef]
        h["warp"] = {"at": np.round(A, 6).tolist(), "coef": np.round(coef, 7).tolist(), "sigma": sig}
        rep["rounds"].append({"miss_mm": [round(x, 2) for x in miss], "targets": len(tgt_g)})
    st1 = state(cur)
    rep["integrity"] = integrity(cur, st1, state(base))
    rep["side_effects"] = side_effects(state(base), st1, set(FACE))
    return cur, rep


HOOD_MAX = 0.005   # m: the most a hooded fold comes down
HOOD_LIDS = (37, 38, 43, 44)  # the upper lids' landmarks: what the hood moves and is fitted on


def _hood_amount(base: dict) -> float:
    h = ((base.get("head") or {}).get("shape") or {}).get("hood") or 0.0
    return float(h["amount"] if isinstance(h, dict) else h)


def _with_hood(base: dict, a: float) -> dict:
    b = copy.deepcopy(base)
    sh = b.setdefault("head", {}).setdefault("shape", {})
    if isinstance(sh.get("hood"), dict):
        sh["hood"]["amount"] = round(float(a), 6)
    elif a > 0:
        sh["hood"] = round(float(a), 6)
    else:
        sh.pop("hood", None)
    return b


def fit_hood(base: dict, views: list, cameras: list) -> tuple:
    """(new base, report): hooded upper lids (base.head.shape.hood) fitted on the upper lids' points (37, 38, 43, 44)
    through each fitted camera (`cameras`, from fit_views): a picture's upper lid line is where the fold hangs over
    the lid, which the identity components can't reach without squeezing the lids. One number, solved linearly
    (the hood moves those landmarks in proportion), clamped to [0, HOOD_MAX] and halved until integrity holds."""
    st0 = state(base)
    a0 = _hood_amount(base)
    step = 0.002 if a0 + 0.002 <= HOOD_MAX else -0.002
    st1 = state(_with_hood(base, a0 + step))
    J, r = [], []
    for v, cam in zip(views, cameras):
        for j in HOOD_LIDS:
            p = v["points"].get(f"lm{j}")
            if p is None:
                continue
            u0, u1 = project(cam, st0["L"][j:j + 1])[0], project(cam, st1["L"][j:j + 1])[0]
            J.append((u1 - u0) / step)
            r.append(np.asarray(p, float) - u0)
    rep = {"amount_before": round(a0 * 1000, 2), "points": len(r)}
    if not r:
        rep.update(amount=rep["amount_before"], note="no upper-lid points in the views")
        return base, rep
    J, r = np.array(J).ravel(), np.array(r).ravel()
    da = float(J @ r / max(J @ J, 1e-12))
    a = float(np.clip(a0 + da, 0.0, HOOD_MAX))
    rep["asked_mm"] = round((a0 + da) * 1000, 2)
    rep["rms_px_before"] = round(float(np.sqrt((r ** 2).mean())), 2)
    while True:
        cur = _with_hood(base, a)
        st = state(cur)
        it = integrity(cur, st, st0)
        if it["ok"] or abs(a - a0) < 1e-4:
            break
        a = a0 + 0.5 * (a - a0)
    rr = r - J * (a - a0)
    rep.update(amount=round(a * 1000, 2), rms_px_after=round(float(np.sqrt((rr ** 2).mean())), 2), integrity=it,
               side_effects=side_effects(st0, st, {"eye_height"}))
    if a0 + da > HOOD_MAX:
        rep["note"] = f"the picture asks {1000 * (a0 + da):.1f} mm of hood, the most is {1000 * HOOD_MAX:.1f}"
    elif a0 + da < 0:
        rep["note"] = "the picture's upper lids are HIGHER than the hood-free face's: open the eyes (pose lid_upper) instead"
    return cur, rep


def fit_views(base: dict, views: list, free=("identity",), force: bool = False, rounds: int = 3, focal: float | None = None) -> tuple:
    """(new base, report). views: [{"points": {landmark: [u, v]}, "size": [w, h], "yaw": deg (a hint: 0 front, 45
    three-quarter from its left, 90 its left side)}]: one camera per view (pose + focal; all views share the face) and,
    with "identity" free, the identity components, solved together on the reprojection error, ridged toward the
    current face. A single frontal view says nothing about depth: profile measures stay as they were."""
    from scipy.optimize import least_squares
    st0 = state(base)
    L0 = st0["L"]
    c0 = identity(base)
    use_id = "identity" in free
    clip = CLIP_FORCE if force else CLIP
    ctr = L0[:68].mean(0)
    obs = []
    for v in views:
        ids = [point_index(k) for k in v["points"]]
        obs.append((np.array(ids), np.array([v["points"][k] for k in v["points"]], float)))
    cams = []
    for v, (ids, uv) in zip(views, obs):
        w, h = v["size"]
        f0 = float(focal or v.get("focal") or 2.2 * max(w, h))
        z0 = f0 * np.ptp(L0[ids], axis=0).max() / max(np.ptp(uv, axis=0).max(), 1.0)
        uc = uv.mean(0)
        cams.append({"r": [0.0, 0.0, 0.0], "t": [(uc[0] - w / 2) / f0 * z0, (uc[1] - h / 2) / f0 * z0, z0], "f": f0,
                     "size": [w, h], "centre": ctr.tolist(), "yaw": float(v.get("yaw", 0.0))})
    cur, c = copy.deepcopy(base), c0.copy()
    outl = [np.asarray(v["outline"], float) if v.get("outline") else None for v in views]
    if any(o is not None for o in outl):
        rounds = max(rounds, 4)  # (the silhouette is found again each round)
    for it in range(rounds if use_id else 1):
        st = state(cur) if it else st0
        L, B = st["L"], (_lm_basis(st) if use_id else None)
        S = _skull_basis(st) if use_id else None
        nc = len(c) if use_id else 0
        # outlines (view["outline"]: [[u, v], ...] along the face's edge in the picture, e.g. the jaw and cheeks): each
        # point pulled onto the model's silhouette through that view's camera, along the outline's own normal (the
        # silhouette vertex nearest it, found again each round; they move with the identity like the landmarks)
        sil = [_silhouette(st, cam, o) if (o is not None and use_id) else None for cam, o in zip(cams, outl)]

        def unpack(x):
            out = []
            for k, cam in enumerate(cams):
                p = x[7 * k:7 * k + 7]
                out.append({**cam, "r": p[:3], "t": p[3:6], "f": float(focal) if focal else p[6]})
            return out, x[7 * len(cams):]

        def resid(x):
            cs, dc = unpack(x)
            Lc = L + (np.tensordot(dc, B, axes=(0, 0)) if use_id else 0.0)
            r = [(project(cam, Lc[ids]) - uv).ravel() / max(cam["size"]) * 400.0 for cam, (ids, uv) in zip(cs, obs)]
            for cam, sl in zip(cs, sil):
                if sl is not None:
                    X = sl["X"] + np.tensordot(dc, sl["B"], axes=(0, 0))
                    d = ((project(cam, X) - sl["p"]) * sl["n"]).sum(1)
                    r.append(OUTLINE_W * d / max(cam["size"]) * 400.0)
            if use_id:
                r.append(RIDGE * 1.5 * dc)
                r.append(0.4 * RIDGE * (c + dc - c0))
                r.append(HOLD_SKULL * 1000.0 * (np.tensordot(c + dc - c0, S, axes=(0, 0))).ravel())  # the skull stays
            return np.concatenate(r)
        x0 = np.concatenate([np.r_[cam["r"], cam["t"], cam["f"]] for cam in cams] + [np.zeros(nc)])
        sol = least_squares(resid, x0, x_scale=np.r_[np.tile([0.1, 0.1, 0.1, 0.05, 0.05, 0.3, 500.0], len(cams)), np.ones(nc)])
        cs, dc = unpack(sol.x)
        cams = [{**cam, "r": [float(v) for v in cam["r"]], "t": [float(v) for v in cam["t"]], "f": float(cam["f"])} for cam in cs]
        if use_id:
            c = np.clip(c + dc, -max(clip, np.abs(c0).max()), max(clip, np.abs(c0).max()))
            cur = _with_identity(cur, c)
    st1 = state(cur)
    per = []
    for cam, (ids, uv), v in zip(cams, obs, views):
        e = np.linalg.norm(project(cam, st1["L"][ids]) - uv, axis=1)
        Xc = (st1["L"][ids] - ctr) @ _cam_rot(cam).T + cam["t"]
        mm = e * Xc[:, 2] / cam["f"] * 1000
        names = list(v["points"])
        worst = np.argsort(-mm)[:3]
        per.append({"points": len(ids), "rms_px": round(float(np.sqrt((e ** 2).mean())), 2), "rms_mm": round(float(np.sqrt((mm ** 2).mean())), 2),
                    "worst": [(str(names[i]), round(float(mm[i]), 1)) for i in worst], "focal": round(cam["f"], 1)})
    rep = {"views": per, "cameras": cams, "plausibility": plausibility(cur), "side_effects": side_effects(st0, st1, set(FACE)),
           "integrity": integrity(cur, st1, st0)}
    return cur, rep


# ---- pictures: before | after | where it moved ------------------------------------------------------------------

def _faces(tpl):
    Lf, Sf = np.asarray(tpl["L"]), np.asarray(tpl["S"])
    k, out = 0, []
    for n in Sf:
        out.append(Lf[k:k + n])
        k += n
    return out


def head_sheet(st0: dict, st1: dict | None = None, px: int = 420, focus=None, title: str = ""):
    """A PIL image, no Blender (a second or two): the head and neck in clay, front + three-quarter, before | after |
    where the vertices moved (blue 0 .. red 5 mm+), and with `focus` (a world point) a close-up row of it. The crop is
    the head and neck only (the body is the base's bare mesh: whole figures come dressed through `look`)."""
    from . import meshview
    from PIL import Image as PILImage
    from PIL import ImageDraw
    sts = [st0] + ([st1] if st1 is not None else [])
    cells = []
    for row, (cz, size, views) in enumerate([(None, None, ((0, 0), (50, 5)))] + ([(focus, 0.09, ((0, 0), (55, 5)))] if focus is not None else [])):
        for k, st in enumerate(sts):
            P = np.asarray(st["tpl"]["P"], float)
            F = _faces(st["tpl"])
            L = st["L"]
            hh = float(P[:, 2].max() - L[8, 2])
            c = np.array(cz, float) if cz is not None else np.array([0.0, float(L[30, 1]) + 0.08, float(L[8, 2]) + 0.42 * hh])
            sz = size or 1.3 * hh
            keep = [f for f in F if P[f, 2].min() > c[2] - 0.75 * sz]
            for az, el in views:
                cells.append(meshview.view(P, keep, c, sz, az=az, el=el, px=px, line=0,
                                           title=(title + " " if title and not cells else "") + ("before" if k == 0 and st1 is not None else "after" if k else "")))
        if st1 is not None:
            P0, P1 = np.asarray(st0["tpl"]["P"], float), np.asarray(st1["tpl"]["P"], float)
            F = _faces(st1["tpl"])
            if P0.shape == P1.shape:
                d = np.linalg.norm(P1 - P0, axis=1) * 1000
                L = st1["L"]
                hh = float(P1[:, 2].max() - L[8, 2])
                c = np.array(cz, float) if cz is not None else np.array([0.0, float(L[30, 1]) + 0.08, float(L[8, 2]) + 0.42 * hh])
                sz = size or 1.3 * hh
                keep = [f for f in F if P1[f, 2].min() > c[2] - 0.75 * sz]
                t = np.clip(np.array([d[f].mean() for f in keep]) / 5.0, 0, 1)[:, None]
                col = (1 - t) * np.array([150, 170, 215]) + t * np.array([235, 60, 40])
                for az, el in views:
                    cells.append(meshview.view(P1, keep, c, sz, az=az, el=el, px=px, line=0, colors=col,
                                               title=f"moved (blue 0 .. red 5 mm+; max {d.max():.1f} mm)" if az == views[0][0] else ""))
    cols = 2 * (len(sts) + (1 if st1 is not None else 0))
    rows = (len(cells) + cols - 1) // cols
    out = PILImage.new("RGB", (cols * px, rows * px), (236, 236, 238))
    for i, im in enumerate(cells):
        out.paste(im, ((i % cols) * px, (i // cols) * px))
    ImageDraw.Draw(out)
    return out


def report_text(rep: dict) -> str:
    """A solve / nudge / image-fit report as the tool prints it: integrity first, then what was asked and what came
    of it, then everything else that moved."""
    lines = [verdict(rep["integrity"])]
    if "asked" in rep:
        for k, r in rep["asked"].items():
            lines.append(f"{k}: asked {r['asked']:g}, was {r['was']:g}, now {r['got']:g}" + ("" if r["met"] else "  NOT MET"))
        if rep.get("held_back", 1.0) < 1.0:
            lines.append(f"held back to {100 * rep['held_back']:.0f}% of the step: further, measures that were not asked for move "
                         f"more than {COLLATERAL:g}x their tolerance. Ask for those too, release them (release=[...]), or force.")
        if rep.get("limited"):
            lines.append(f"limited by the plausible range (identity components stop at {CLIP} sigma): the rest is a style, not an "
                         "identity (style sliders, or force=True).")
    if "landmark" in rep:
        lines.append(f"{rep['landmark']}: asked {rep['asked_mm']} mm, moved {rep['got_mm']} mm; {rep['by_sliders_mm']} mm by the identity "
                     f"sliders, {rep['by_correction_mm']} mm by a correction layer" +
                     (" (the sliders can't do this: a slider / target the model lacks)" if rep["by_correction_mm"] > 1.0 else ""))
    if "views" in rep:
        for i, v in enumerate(rep["views"]):
            lines.append(f"view {i}: {v['points']} points, reprojection {v['rms_px']} px rms = {v['rms_mm']} mm on the face; worst "
                         + ", ".join(f"{n} {mm} mm" for n, mm in v["worst"]) + f"; focal {v['focal']} px")
    p = rep["plausibility"]
    lines.append(f"plausibility: identity {p['rms_sigma']:.2f} sigma rms, largest {p['max_sigma']:.2f}")
    lines.append(effects_text(rep["side_effects"]))
    return "\n".join(lines)
