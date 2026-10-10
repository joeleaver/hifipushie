"""Macro sliders for the one human mesh's head, as CALIBRATED DIRECTIONS in GNM's statistical identity space
(prototype from the reference-modelling study, CLAUDE.md "Reference modelling study").

Why: a local warp moves one feature and leaves a head no person has (a square jaw under a narrow skull, a strong
chin from the front that is weak in profile). GNM's identity components are a population model: a direction in it
moves everything that goes with a feature in real heads, in every view. So a macro here is

  a MEASURE  an artist's word made a number on the head's own geometry (jaw_square, chin_projection, nose_upturn..)
  its DIRECTION  the least unusual change of the identity that moves that measure: for components c ~ N(0, 1) and a
             measure f ~ f0 + a . c, the conditional mean E[c | f] moves along a / |a|. One unit along it is ONE
             STANDARD DEVIATION of that measure in the population, so macros are set in sigmas: "square jaw +1.5".
  `held`     the same with every other macro held (the pseudo-inverse's column): an independent slider, a less
             natural head per unit; `solve` uses it to meet several asked values at once with the least change.

`table()` calibrates everything by sampling heads (cached); `read(c)` gives a head's macros in sigmas; `apply`,
`solve`; `prior_rows` turns a character read ({"jaw_square": +1.5} with a tolerance) into evidence rows for a fit;
`fit_map` is the fit the study found to work: a MAP estimate with the identity's own prior, the detector's points
at their calibrated places and noise, and the read as soft evidence. What the identity space CANNOT express is in
`table()["weak"]` (their population sd is under what an eye sees): those need a shape op on top (base.head.shape).

Frame: world as the repo's (Z up, facing -Y, left +X), GNM's template size (interocular 61.7 mm); identity = GNM's
head components in order (headfit's first 120 are the ones every fit in the repo solves).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

K = 120          # identity components the macros live in (headfit.N: what base.head.identity fits use)
SAMPLES = 2500   # heads sampled for the calibration
_C = {}


def space() -> dict:
    """GNM's head in the world frame: {"V0" (V, 3), "IB" (170, V, 3), "T" triangles, "W" (70, V) landmark weights
    (the 68 + eye centres, 68 = the subject's left), "L0", "LB", "gr" vertex groups, "ext" exterior skin, "sets"}."""
    if "sp" in _C:
        return _C["sp"]
    from . import base
    g = base._gnm_data()
    names = [str(n) for n in g["identity_names"]]
    comps = [i for i, n in enumerate(names) if n.startswith("head")]
    w = lambda X: np.stack([X[..., 0], -X[..., 2], X[..., 1]], -1)  # noqa: E731
    V0 = w(g["template_vertex_positions"].astype(float))
    IB = w(np.asarray(g["vertex_identity_basis"])[comps].astype(np.float32))
    q = np.asarray(g["quads"])
    T = np.r_[q[:, [0, 1, 2]], q[:, [0, 2, 3]]].astype(np.int64)
    gr = {k: np.asarray(v, float) > 0.5 for k, v in g["groups"].items()}
    W = np.zeros((70, len(V0)))
    for i, r in enumerate(g["lm68"]):
        for v, x in zip(r[0::2], r[1::2]):
            W[i, int(v)] += float(x)
    le, re = gr["left_eye"], gr["right_eye"]
    if V0[le, 0].mean() < V0[re, 0].mean():
        le, re = re, le
    W[68, le] = 1.0 / le.sum()
    W[69, re] = 1.0 / re.sum()
    sp = {"V0": V0, "IB": IB, "T": T, "W": W, "gr": gr, "ext": gr["skin_exterior"], "names": [names[i] for i in comps],
          "L0": W @ V0, "LB": np.einsum("ln,cnd->cld", W, IB)}
    sp["sets"] = _sets(sp)
    _C["sp"] = sp
    return sp


def _sets(sp) -> dict:
    """Fixed vertex sets the measures read (chosen on the template, so every measure is a smooth function of V)."""
    V0, L, gr, ext = sp["V0"], sp["L0"], sp["gr"], sp["ext"]
    fwd = -V0[:, 1]
    chin = gr["chin_region"] & ext
    zc = V0[chin & (np.abs(V0[:, 0]) < 0.008), 2]
    pog_z = float(V0[chin][np.argmax(fwd[chin]), 2])
    band = chin & (np.abs(V0[:, 2] - pog_z) < 0.008) & (fwd > fwd[chin].max() - 0.012)
    two = lambda n: gr[f"left_{n}_region"] | gr[f"right_{n}_region"]  # noqa: E731
    used = np.zeros(len(V0), bool)
    for k, m in gr.items():
        if k.endswith("_region"):
            used |= m
    rest = ext & ~used & ~gr["ears"]
    mid = ext & (np.abs(V0[:, 0]) < 0.0015) & (fwd > -L[[0, 16], 1].mean())
    fz = L[27, 2] + 0.045
    # orbit rings (faces6): around each eye centre in the face plane (x, z), radius bands, upper / lower halves
    rings = {}
    for side, ec in (("L", L[68]), ("R", L[69])):
        dx, dz = V0[:, 0] - ec[0], V0[:, 2] - ec[2]
        rr = np.hypot(dx, dz)
        front = ext & (fwd > fwd[ext].max() - 0.06) & ~gr["ears"]
        for nm, lo, hi in (("rim", 0.016, 0.020), ("lid", 0.006, 0.0095)):
            for half, sel in (("up", dz > 0.004), ("lo", dz < -0.004)):
                rings[f"{nm}_{half}_{side}"] = np.flatnonzero(front & (rr > lo) & (rr < hi) & sel & (np.abs(dx) < 0.012))
    rad = ext & (np.abs(V0[:, 2] - L[28, 2]) < 0.002) & (np.abs(V0[:, 0]) < 0.016) & (fwd > fwd[ext].max() - 0.05)
    s = {**rings, "radix_band": np.flatnonzero(rad), "pog": np.flatnonzero(chin & (np.abs(V0[:, 0]) < 0.008))[np.argsort(-fwd[chin & (np.abs(V0[:, 0]) < 0.008)])[:8]],
         "cleft_mid": np.flatnonzero(band & (np.abs(V0[:, 0]) < 0.002)),
         "cleft_side": np.flatnonzero(band & (np.abs(V0[:, 0]) > 0.004) & (np.abs(V0[:, 0]) < 0.010)),
         "cheek_L": np.flatnonzero(gr["left_cheek_region"] & ext), "cheek_R": np.flatnonzero(gr["right_cheek_region"] & ext),
         "zyg": np.flatnonzero(two("zygomatic") & ext),
         "neck": np.flatnonzero(rest & (V0[:, 2] < L[8, 2] - 0.025) & (V0[:, 2] > L[8, 2] - 0.045)),
         "ear_L": np.flatnonzero(gr["ears"] & ext & (V0[:, 0] > 0)), "ear_R": np.flatnonzero(gr["ears"] & ext & (V0[:, 0] < 0)),
         "cranium": np.flatnonzero(rest & (V0[:, 2] > L[27, 2] - 0.01)),
         "forehead": np.flatnonzero(mid & (np.abs(V0[:, 2] - fz) < 0.004)),
         "under_chin": np.flatnonzero(mid & (V0[:, 2] < L[8, 2] - 0.004) & (V0[:, 2] > L[8, 2] - 0.02) & (fwd < -L[8, 1] - 0.015))}
    if V0[s["cheek_L"], 0].mean() < 0:
        s["cheek_L"], s["cheek_R"] = s["cheek_R"], s["cheek_L"]
    del zc
    return s


def head(c=None) -> np.ndarray:
    sp = space()
    V = sp["V0"].copy()
    if c is not None:
        c = np.asarray(c, float)
        if "IBf" not in sp:   # (float64 once: casting the float32 basis on every call was most of a head's cost)
            sp["IBf"] = sp["IB"][:K].reshape(K, -1).astype(float)
        V += (c[:K] @ sp["IBf"][:len(c)]).reshape(-1, 3)
    return V


# ---- the measures ----------------------------------------------------------------------------------------------------
# name: (unit, what an artist calls it, + direction's meaning)
MACROS = {
    "face_length": ("io", "long face (+) / short face (-): nasion to the chin's bottom"),
    "face_width": ("io", "wide (+) / narrow (-) face at the ears' fronts"),
    "cheekbone_width": ("io", "wide, prominent (+) / narrow (-) cheekbones"),
    "jaw_width": ("io", "wide (+) / narrow (-) jaw at its angles"),
    "jaw_square": ("ratio", "square jaw (+): the jaw as wide low down as high up / tapered, V-shaped (-)"),
    "jaw_angle": ("deg", "the jaw line's turn at its angle: an L, crisp corner (+) / one diagonal (-)"),
    "chin_width": ("io", "broad (+) / narrow, pointed (-) chin"),
    "chin_height": ("io", "tall (+) / short (-) chin under the lower lip"),
    "chin_projection": ("io", "strong, forward (+) / weak, receding (-) chin, against the nose's base"),
    "chin_cleft": ("mm", "cleft chin: the mid-line groove's depth"),
    "under_chin": ("io", "a clean jaw-to-neck angle (+) / full under the chin, double chin (-)"),
    "nose_length": ("io", "long (+) / short (-) nose, nasion to its base"),
    "nose_projection": ("io", "the tip stands out (+) / flat nose (-)"),
    "nose_width": ("io", "wide (+) / narrow (-) nose at the wings"),
    "nose_upturn": ("deg", "upturned tip (+) / drooping, hooked tip (-)"),
    "bridge_height": ("io", "high (+) / low, flat (-) bridge between the eyes"),
    "bridge_hump": ("mm", "a hump on the dorsum (+) / scooped (-)"),
    "brow_ridge": ("io", "heavy brow ridge (+) / flat brow (-), ahead of the eyes"),
    "brow_height": ("io", "high (+) / low, heavy (-) brows over the eyes"),
    "eye_depth": ("io", "deep-set (+) / prominent (-) eyes behind the nasion"),
    "eye_width": ("io", "large (+) / small (-) eye openings, corner to corner"),
    "eye_height": ("io", "open, round (+) / narrow, hooded (-) eye openings"),
    "eye_spacing": ("io", "wide-set (+) / close-set (-) eyes (inner corners)"),
    "eye_tilt": ("deg", "outer corners up (+) / down (-)"),
    "mouth_width": ("io", "wide (+) / small (-) mouth"),
    "lip_fullness": ("io", "full (+) / thin (-) lips"),
    "philtrum": ("io", "long (+) / short (-) upper lip under the nose"),
    "lip_projection": ("io", "lips forward of the nose-chin line (+) / behind it (-)"),
    "cheek_fullness": ("mm", "full, chunky cheeks (+) / gaunt, hollow (-)"),
    "forehead_slope": ("deg", "sloping back (+) / upright, bulging (-) forehead"),
    "cranium_width": ("io", "wide (+) / narrow (-) skull over the ears"),
    "cranium_height": ("io", "tall (+) / low (-) skull over the brows"),
    "head_depth": ("io", "long (+) / short (-) head front to back"),
    "neck_width": ("io", "thick (+) / thin (-) neck"),
    "ear_size": ("io", "big (+) / small (-) ears"),
    "ear_out": ("io", "ears standing out (+) / flat to the head (-)"),
    "head_size": ("mm", "interocular distance: the head's absolute size"),
    # (faces6: the artist block-in's vocabulary gaps)
    "gonial_height": ("io", "high (+) / low (-) jaw angles: the gonial corners' height over the chin's bottom"),
    "orbital_rim": ("mm", "a defined socket (+): the brow-orbital rim standing ahead of the upper lid's plane / flat (-)"),
    "lower_orbit": ("mm", "a defined lower orbital rim (+) ahead of the lower lid / a flat or hollow under-eye (-)"),
}
# (radix width, the bridge's width between the eyes: read in spikes/facesliders/newdirs.py, not a macro: held-out R2
# 0.90 (below this table's near-linear bar) and a population sd of only ~0.6 mm: GNM barely varies it)


def measures(V: np.ndarray) -> dict:
    """Every macro's measure on a head (world vertices, GNM topology)."""
    sp = space()
    s = sp["sets"]
    L = sp["W"] @ V
    io = L[68, 0] - L[69, 0]
    f = lambda p: -p[..., 1]  # noqa: E731  forward
    pog = V[s["pog"]].mean(0)
    eyes = 0.5 * (L[68] + L[69])
    ang = lambda a, b: float(np.degrees(np.arccos(np.clip(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)), -1, 1))))  # noqa: E731
    out = {}
    out["face_length"] = (L[27, 2] - L[8, 2]) / io
    out["face_width"] = (L[16, 0] - L[0, 0]) / io
    out["cheekbone_width"] = float(np.ptp(V[s["zyg"], 0])) / io
    out["jaw_width"] = (L[12, 0] - L[4, 0]) / io
    out["jaw_square"] = (L[11, 0] - L[5, 0]) / (L[14, 0] - L[2, 0])
    out["jaw_angle"] = 0.5 * (ang(L[4] - L[2], L[7] - L[4]) + ang(L[12] - L[14], L[9] - L[12]))
    out["chin_width"] = (L[10, 0] - L[6, 0]) / io
    out["chin_height"] = (L[57, 2] - L[8, 2]) / io
    out["chin_projection"] = (f(pog) - f(L[33])) / io
    out["chin_cleft"] = (f(V[s["cleft_side"]]).mean() - f(V[s["cleft_mid"]]).mean()) * 1000
    out["under_chin"] = (V[s["under_chin"], 2].mean() - L[8, 2]) / io if len(s["under_chin"]) else 0.0
    out["nose_length"] = (L[27, 2] - L[33, 2]) / io
    out["nose_projection"] = (f(L[30]) - f(L[33])) / io
    out["nose_width"] = (L[35, 0] - L[31, 0]) / io
    out["nose_upturn"] = float(np.degrees(np.arctan2(L[30, 2] - L[33, 2], f(L[30]) - f(L[33]))))
    out["bridge_height"] = (f(L[28]) - 0.5 * (f(L[39]) + f(L[42]))) / io
    d = np.array([f(L[30]) - f(L[27]), L[30, 2] - L[27, 2]])
    p = np.array([f(L[29]) - f(L[27]), L[29, 2] - L[27, 2]])
    out["bridge_hump"] = float((p[0] * d[1] - p[1] * d[0]) / np.linalg.norm(d)) * -1000
    out["brow_ridge"] = (f(L[[19, 20, 23, 24]]).mean() - f(eyes)) / io
    out["brow_height"] = (L[[19, 24], 2].mean() - eyes[2]) / io
    out["eye_depth"] = (f(L[27]) - f(eyes)) / io
    out["eye_width"] = 0.5 * (np.linalg.norm(L[45] - L[42]) + np.linalg.norm(L[39] - L[36])) / io
    out["eye_height"] = 0.5 * ((L[[43, 44], 2].mean() - L[[47, 46], 2].mean()) + (L[[37, 38], 2].mean() - L[[41, 40], 2].mean())) / io
    out["eye_spacing"] = (L[42, 0] - L[39, 0]) / io
    out["eye_tilt"] = float(np.degrees(0.5 * (np.arctan2(L[45, 2] - L[42, 2], L[45, 0] - L[42, 0]) + np.arctan2(L[36, 2] - L[39, 2], L[39, 0] - L[36, 0]))))
    out["mouth_width"] = (L[54, 0] - L[48, 0]) / io
    out["lip_fullness"] = (L[51, 2] - L[57, 2]) / io
    out["philtrum"] = (L[33, 2] - L[51, 2]) / io
    out["lip_projection"] = (0.5 * (f(L[51]) + f(L[57])) - 0.5 * (f(L[33]) + f(pog))) / io
    ch = 0.0
    for side, a, b, c_ in (("cheek_L", 15, 54, 11), ("cheek_R", 1, 48, 5)):
        n = np.cross(L[b] - L[a], L[c_] - L[a])
        n /= np.linalg.norm(n)
        if n[0] * (1 if side == "cheek_L" else -1) < 0:
            n = -n
        ch += float(((V[s[side]] - L[a]) @ n).mean()) * 500
    out["cheek_fullness"] = ch
    F = V[s["forehead"]].mean(0)
    out["forehead_slope"] = float(np.degrees(np.arctan2(f(L[27]) - f(F), F[2] - L[27, 2])))
    out["cranium_width"] = float(np.ptp(V[s["cranium"], 0])) / io
    out["cranium_height"] = (V[s["cranium"], 2].max() - L[27, 2]) / io
    out["head_depth"] = float(np.ptp(V[s["cranium"], 1])) / io
    out["neck_width"] = float(np.ptp(V[s["neck"], 0])) / io
    out["ear_size"] = 0.5 * (np.ptp(V[s["ear_L"], 2]) + np.ptp(V[s["ear_R"], 2])) / io
    out["ear_out"] = 0.5 * ((V[s["ear_L"], 0].max() - L[16, 0]) + (L[0, 0] - V[s["ear_R"], 0].min())) / io
    out["head_size"] = io * 1000
    out["gonial_height"] = (L[[3, 4, 5, 11, 12, 13], 2].mean() - L[8, 2]) / io
    orb, lorb = 0.0, 0.0
    for sd_ in ("L", "R"):
        orb += (f(V[s[f"rim_up_{sd_}"]]).mean() - f(V[s[f"lid_up_{sd_}"]]).mean()) * 500
        lorb += (f(V[s[f"rim_lo_{sd_}"]]).mean() - f(V[s[f"lid_lo_{sd_}"]]).mean()) * 500
    out["orbital_rim"] = orb
    out["lower_orbit"] = lorb
    return {k: float(v) for k, v in out.items()}


NAMES = list(MACROS)
# what an eye sees: a macro whose population sd is under this (in its unit) can't be reached in the identity space
VISIBLE = {"mm": 0.6, "deg": 2.0, "io": 0.012, "ratio": 0.012}


def table(samples: int = SAMPLES, seed: int = 0) -> dict:
    """The calibration (cached on disk by this file's hash): for each macro the mean f0, the linear map a (K,) from
    the components, its population sd, how linear it is (r2), and between macros the population correlation
    (what goes with what). "weak" lists macros the identity space barely moves."""
    if "tab" in _C:
        return _C["tab"]
    from . import store
    key = hashlib.sha1(Path(__file__).read_bytes() + f"{samples}{seed}{K}".encode()).hexdigest()[:16]
    d = store.HOME / "_cache"
    d.mkdir(parents=True, exist_ok=True)
    fpath = d / f"humanmacro_{key}.npz"
    if fpath.exists():
        z = np.load(fpath)
        tab = {k: z[k] for k in z.files}
    else:
        rng = np.random.default_rng(seed)
        C = rng.normal(0, 1, (samples, K))
        row = lambda m: [m[k] for k in NAMES]  # noqa: E731
        F = np.array([row(measures(head(c))) for c in C])
        f0 = np.array(row(measures(head())))
        A = np.linalg.lstsq(C, F - F.mean(0), rcond=None)[0].T   # (M, K)
        pred = C @ A.T + F.mean(0)
        r2 = 1 - ((F - pred) ** 2).sum(0) / np.maximum(((F - F.mean(0)) ** 2).sum(0), 1e-30)
        tab = {"A": A, "f0": f0, "fm": F.mean(0), "sd": F.std(0), "r2": r2, "corr": np.corrcoef(F.T)}
        np.savez(fpath, **tab)
    tab = dict(tab)
    tab["names"] = NAMES
    tab["weak"] = [k for i, k in enumerate(NAMES) if tab["sd"][i] < VISIBLE[MACROS[k][0]]]
    _C["tab"] = tab
    return tab


def released(name: str) -> list[str]:
    """The macros a HELD move of `name` must let go: those in an exact linear relation with it over the identity (the
    table's near-null left singular vectors: a length that is the sum of others)."""
    t = table()
    An = t["A"] / t["sd"][:, None]
    U, S, _ = np.linalg.svd(An, full_matrices=True)
    i = NAMES.index(name)
    out = set()
    for k in range(len(NAMES)):
        s = S[k] if k < len(S) else 0.0
        if s > 1e-6 * S[0]:
            continue
        u = U[:, k]
        if abs(u[i]) > 0.05:   # a part lets go of the whole (chin_height -> face_length); the whole of its parts
            top = int(np.argmax(np.abs(u)))
            out |= ({NAMES[j] for j in np.flatnonzero(np.abs(u) > 0.05) if j != i} if top == i else {NAMES[top]})
    return sorted(out)


def direction(name: str, held: bool = False) -> np.ndarray:
    """The change of the components per +1 population sd of the macro. held=False: with what goes with it in the
    population (the conditional mean); held=True: every other macro held."""
    t = table()
    i = NAMES.index(name)
    A = t["A"]
    if held:
        # every other macro held EXCEPT those tied to this one by definition: face_length is nasion -> chin = nose_length
        # + philtrum + lips + chin_height (an exact null combination of the table's rows, blockin 2026-10-10); holding
        # them all asks the impossible, and the pseudo-inverse then split the change (chin_height! +1 gave chin +0.81,
        # face_length +0.30)
        An = A / t["sd"][:, None]
        rel = released(name)
        rows = [i] + [j for j in range(len(NAMES)) if j != i and NAMES[j] not in rel]
        P = np.linalg.pinv(An[rows], rcond=1e-3)
        return P[:, 0]
    a = A[i]
    return a * t["sd"][i] / (a @ a)


def read(c=None, V=None) -> dict:
    """A head's macros in population sigmas (0 = GNM's mean head): {"macro": z}. From its components c, or from any
    head in GNM's topology V (then the measures are taken on the mesh itself: out-of-basis shape counts too)."""
    t = table()
    if V is None:
        V = head(np.asarray(c, float)[:K])
    m = measures(V)
    return {k: float((m[k] - t["fm"][i]) / t["sd"][i]) for i, k in enumerate(NAMES)}


def apply(c, macros: dict, held: bool = False) -> np.ndarray:
    """c with each macro moved by the given sigmas (a relative move along its direction)."""
    c = np.zeros(K) if c is None else np.asarray(c, float)[:K].copy()
    for k, z in macros.items():
        c = c + float(z) * direction(k, held)
    return c


def apply_coupled(c, macros: dict, hold=(), within: bool = True) -> np.ndarray:
    """The macros in the face sliders' framework (faceatlas.direction): each macro moved by the given sigmas as ONE
    conditioning (the macros asked hold each other), the attributes named in `hold` kept, everything else as the
    population couples it, within the head's sex by default. The free mode (`apply(held=False)`) is this for one
    macro on the pooled prior; `held=True` is this with every other macro held."""
    from . import faceatlas
    c = np.zeros(K) if c is None else np.asarray(c, float)[:K].copy()
    t = faceatlas.table()
    change = {k: float(z) * float(t["sd"][t["index"][k]]) for k, z in macros.items()}
    return c + faceatlas.direction(change, hold, within=within)


def solve(c, want: dict, hold: bool = True, tol: float = 0.05, rounds: int = 6) -> tuple:
    """(c', report): the least change of the components (in sigma) that brings each asked macro TO its value (in
    sigmas), every macro not asked for held softly where it is (hold). The measures are re-read each round (they are
    not exactly linear). Report: asked -> got, what else moved by more than 0.3 sigma, how unusual the head is."""
    t = table()
    c0 = np.zeros(K) if c is None else np.asarray(c, float)[:K].copy()
    c1 = c0.copy()
    z0 = read(c0)
    An = t["A"] / t["sd"][:, None]
    ia = [NAMES.index(k) for k in want]
    ih = [i for i in range(len(NAMES)) if i not in ia and NAMES[i] not in t["weak"]] if hold else []
    for _ in range(rounds):
        z = read(c1)
        r = np.array([want[NAMES[i]] - z[NAMES[i]] for i in ia])
        if np.abs(r).max() < tol:
            break
        rows = [An[ia] / tol, 0.5 * An[ih], np.eye(K) * 0.15]
        rhs = [r / tol, 0.5 * np.array([z0[NAMES[i]] - z[NAMES[i]] for i in ih]), 0.15 * (c0 - c1) * 0.0]
        dc = np.linalg.lstsq(np.vstack(rows), np.concatenate(rhs), rcond=None)[0]
        c1 = c1 + dc
    z1 = read(c1)
    rep = {"asked": {k: {"want": float(want[k]), "was": round(z0[k], 2), "got": round(z1[k], 2)} for k in want},
           "also_moved": {k: (round(z0[k], 2), round(z1[k], 2)) for k in NAMES if k not in want and abs(z1[k] - z0[k]) > 0.3},
           "rms_sigma": float(np.sqrt((c1 ** 2).mean())), "step_sigma": float(np.linalg.norm(c1 - c0))}
    return c1, rep


def prior_rows(read_: dict, c_ref=None, sd: float = 0.7) -> tuple:
    """Evidence rows (A (m, K), y (m,)) for a least-squares fit of c from a character read: {"macro": z | (z, sd)}
    = "this head's macro is about z population sigmas, give or take sd". Linearised about c_ref (default the mean)."""
    t = table()
    c_ref = np.zeros(K) if c_ref is None else np.asarray(c_ref, float)[:K]
    z = read(c_ref)
    A, y = [], []
    for k, v in read_.items():
        zz, s = (v if isinstance(v, (tuple, list)) else (v, sd))
        i = NAMES.index(k)
        a = t["A"][i] / t["sd"][i]
        A.append(a / s)
        y.append((zz - z[k] + a @ c_ref) / s)
    return np.array(A), np.array(y)


def identity_dict(c) -> dict:
    """The components as base.head.identity wants them."""
    sp = space()
    return {sp["names"][i]: round(float(v), 4) for i, v in enumerate(np.asarray(c, float)) if abs(v) > 1e-6}


def from_identity(idn: dict | None) -> np.ndarray:
    sp = space()
    c = np.zeros(K)
    for k, v in (idn or {}).items():
        if k in sp["names"] and sp["names"].index(k) < K:
            c[sp["names"].index(k)] = float(v)
    return c


def soundness(c) -> dict:
    """A cheap check of a head made by components alone: triangles of the exterior skin turned over against the
    mean head's, the shortest edge against the mean's (a squeeze), how unusual (rms / max sigma)."""
    sp = space()
    T = sp["T"][sp["ext"][sp["T"]].all(1)]
    V = head(c)
    n0 = np.cross(sp["V0"][T[:, 1]] - sp["V0"][T[:, 0]], sp["V0"][T[:, 2]] - sp["V0"][T[:, 0]])
    n1 = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    cs = (n0 * n1).sum(1) / np.maximum(np.linalg.norm(n0, axis=1) * np.linalg.norm(n1, axis=1), 1e-30)
    E = np.r_[T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]]
    l0 = np.linalg.norm(sp["V0"][E[:, 0]] - sp["V0"][E[:, 1]], axis=1)
    l1 = np.linalg.norm(V[E[:, 0]] - V[E[:, 1]], axis=1)
    k = l0 > 0.0008
    c = np.asarray(c, float)
    return {"flipped": int((cs < 0).sum()), "squeeze": float((l1[k] / l0[k]).min()), "stretch": float((l1[k] / l0[k]).max()),
            "rms_sigma": float(np.sqrt((c ** 2).mean())), "max_sigma": float(np.abs(c).max())}


def text(z: dict, top: int = 12) -> str:
    """A head's macros as words, strongest first."""
    out = []
    for k, v in sorted(z.items(), key=lambda kv: -abs(kv[1]))[:top]:
        out.append(f"  {k:16s} {v:+5.2f} sigma   {MACROS[k][1]}")
    return "\n".join(out)
