"""The solve: landmark, skull and cheek bases, `solve`, `nudge`. Part of humanfit (humanfit.py has the overview)."""
from __future__ import annotations

import copy

import numpy as np

from . import humanfit
from .humanfit import _gnm_normals, _points, face_gradient, identity, plausibility, state, value
from .humanfit_integrity import _guarded, integrity, side_effects

def _lm_basis(st: dict) -> np.ndarray:
    """d(L, world) / d(identity component): (120, 70, 3). The landmarks are linear in the components; the head stays
    hung on its eye midpoint."""
    from . import headfit
    g = headfit._gnm()
    c = st["head"]["carry"]
    R, s = np.asarray(c["R"], float), float(c["s"])
    LB = np.concatenate([g["LB"][:, :68], g["JB"]], axis=1)  # (120, 70, 3), GNM's frame
    if g["J0"][0][0] < g["J0"][1][0]:
        LB[:, [humanfit.EYE_L, humanfit.EYE_R]] = LB[:, [humanfit.EYE_R, humanfit.EYE_L]]
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


def _cheek_basis(st: dict) -> np.ndarray:
    """d(cheek front points, world) / d(identity component): (120, n, 3) for GNM's cheek-region vertices facing
    forward (subsampled)."""
    from . import base_identity
    from . import headfit
    g = headfit._gnm()
    gd = base_identity._gnm_data()
    c = st["head"]["carry"]
    R, s_ = np.asarray(c["R"], float), float(c["s"])
    key = "_cheek_idx"
    idx = humanfit._CHEEK.get(key)
    if idx is None:
        Vg = np.asarray(gd["template_vertex_positions"], float)
        soft = np.asarray(gd["groups"]["left_cheek_region"], float) + np.asarray(gd["groups"]["right_cheek_region"], float)
        sk = np.asarray(gd["skin"], bool)
        idx = np.flatnonzero(sk & (soft > 0.5) & (_gnm_normals(Vg)[:, 2] > 0.35))
        idx = idx[np.linspace(0, len(idx) - 1, min(len(idx), 80)).astype(int)]
        humanfit._CHEEK[key] = idx
    VB = np.asarray(gd["vertex_identity_basis"], float)[g["comps"]][:, idx]
    return s_ * (VB - g["JB"].mean(1, keepdims=True)) @ R.T


def _with_identity(base: dict, c: np.ndarray) -> dict:
    from . import headfit
    g = headfit._gnm()
    out = copy.deepcopy(base)
    hd = out.setdefault("head", {})
    # everything the head's identity is made of is written out (the seed and features are in it already)
    from . import onemesh_head
    cur = onemesh_head.head_desc(base)
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
    return humanfit.TOL_MM if name in humanfit.FACE else max(abs(v) * 0.005, 0.05)


def solve(base: dict, want: dict, free=("identity",), hold: bool = True, force: bool = False, rounds: int = 5,
          release=()) -> tuple:
    """(new base, report). want: {measure or "a/b": value | "+2" | "-1.5" | "x1.1"}. free: "identity" (the face),
    "body" (weight, muscle, height; and hips / waist / shoulders / chest / bust (makehuman.MEASURES, BODY_SHAPE) when a
    measure they shape is asked). release: measures let go (not held). See the module docstring."""
    st0 = state(base)
    m0 = st0["measures"]
    tgt = _parse(m0, want)
    asked = set(tgt)
    asked_parts = {p.strip() for k in asked for p in k.split("/")}
    cur = copy.deepcopy(base)
    clip = humanfit.CLIP_FORCE if force else humanfit.CLIP
    use_id = "identity" in free and any(p in humanfit.FACE for p in asked_parts)
    use_body = "body" in free
    bkeys = [k for k in humanfit.BODY_FREE if k != "height" or any(p in ("stature", "heads") for p in asked_parts)] if use_body else []
    if use_body:
        bkeys += [k for k, ms in humanfit.BODY_SHAPE.items() if any(p in ms for p in asked_parts)
                  and (k != "bust" or float(base["body"].get("sex", 1.0)) < 1.0)]
    c0 = identity(base)
    c = c0.copy()
    L0 = st0["L"]
    held = [k for k in m0 if hold and k not in asked_parts and k not in release]
    pts = sorted({i for p in asked_parts if p in humanfit.FACE for i in _points(p)})
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
            jf = jac_face(name) if name in humanfit.FACE else np.zeros(len(c) if use_id else 0)
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
            w = humanfit.HOLD / (1.0 if k in humanfit.FACE else max(abs(m0[k]) * 0.01, 1e-3))
            A.append(jac(k) * w)
            y.append(-(m[k] - m0[k]) * w)
        if use_id and hold:  # landmarks far from the asked ones stay in place
            W = (humanfit.HOLD_LM * 1000.0 * far)[None, :, None]
            A.extend(list(np.c_[(B * W).reshape(len(c), -1).T, np.zeros((210, len(bkeys)))]))
            y.extend(list(-((L - L0) * W[0]).reshape(-1)))
        if use_id and hold:  # ... and the skull, which no face measure sees
            S = _skull_basis(st)
            Sm = (S * (humanfit.HOLD_SKULL * 1000.0)).reshape(len(c), -1).T
            A.extend(list(np.c_[Sm, np.zeros((Sm.shape[0], len(bkeys)))]))
            y.extend(list(-(Sm @ (c - c0))))
        for i in range(nv):  # each step is ridged toward the current state; components also toward what they were
            e = np.zeros(nv)
            e[i] = humanfit.RIDGE if i < (len(c) if use_id else 0) else 2.0
            A.append(e)
            y.append((humanfit.RIDGE * (c0[i] - c[i])) * 0.5 if i < (len(c) if use_id else 0) else 0.0)
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
            if k in humanfit.FACE:
                worst = max(worst, abs(float((face_gradient(k, L0) * dL).sum())) / humanfit.UNINTENDED_MM)
        if worst > humanfit.COLLATERAL:
            held_back = humanfit.COLLATERAL / worst
            c = c0 + held_back * (c - c0)
            cur = _with_identity(cur, c)
    st1 = state(cur)
    m1 = st1["measures"]
    resid = {k: {"asked": round(tgt[k], 3), "got": round(value(m1, k), 3), "was": round(value(m0, k), 3),
                 "met": bool(abs(value(m1, k) - tgt[k]) <= _tol(k, tgt[k]) * 1.5)} for k in tgt}
    rep = {"asked": resid, "rounds": len(log), "plausibility": plausibility(cur), "held_back": round(held_back, 3),
           "limited": bool(use_id and (np.abs(c) >= clip - 1e-6).any() and not all(r["met"] for r in resid.values())),
           "side_effects": side_effects(st0, st1, asked_parts), "integrity": integrity(cur, st1, st0)}
    return _guarded(base, cur, rep, force)


def nudge(base: dict, landmark: str | int, move=None, to=None, radius: float = 0.015, force: bool = False) -> tuple:
    """(new base, report): one landmark moved by `move` [x, y, z] m (or to a world point), every other landmark held.
    The identity components take what they can within the plausible range; the rest is a smooth correction at that
    landmark (base.head.shape.push_more) and reported as what the sliders can't do."""
    st0 = state(base)
    i = humanfit.LANDMARKS[landmark] if isinstance(landmark, str) else int(landmark)
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
        w = 20.0 if j in (i, mir) else humanfit.HOLD_LM * 8 * far[j]
        t = mv if j == i else mv * [-1, 1, 1] if j == mir else np.zeros(3)
        for a in range(3):
            A.append(B[:, j, a] * w * 1000)
            y.append(t[a] * w * 1000)
    Sm = (_skull_basis(st0) * (humanfit.HOLD_SKULL * 1000.0)).reshape(len(c0), -1).T
    A.extend(list(Sm))
    y.extend([0.0] * Sm.shape[0])
    for k in range(len(c0)):
        e = np.zeros(len(c0))
        e[k] = humanfit.RIDGE * 2
        A.append(e)
        y.append(0.0)
    dc = np.linalg.lstsq(np.array(A), np.array(y), rcond=None)[0]
    clip = humanfit.CLIP_FORCE if force else humanfit.CLIP
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
    asked = float(np.linalg.norm(mv))
    if not force and (corr > humanfit.NUDGE_CORR * float(radius) or asked > humanfit.NUDGE_MAX):
        # size guards of its own: a Gaussian bump taller than about a third of its radius is a knob on the head, and
        # one landmark moved centimetres with every other held is not a nudge, whatever the edge lengths say
        # (integrity passes a 3 cm chin drop once slivers stopped counting)
        why = (f"a {asked * 1000:.0f} mm move of one landmark with the rest held (limit {humanfit.NUDGE_MAX * 1000:.0f} mm)" if asked > humanfit.NUDGE_MAX else
               f"a correction bump of {corr * 1000:.1f} mm, taller than {humanfit.NUDGE_CORR:.2f} x its radius ({radius * 1000:.0f} mm): a knob, not a feature")
        rep["refused"] = (f"not returned (the input is): {why}. The sliders reach {rep['by_sliders_mm']} mm. Ask for less, use a measure "
                          "(solve) or a base.head.shape control, or force=True.")
        return base, rep
    return _guarded(base, cur, rep, force)
