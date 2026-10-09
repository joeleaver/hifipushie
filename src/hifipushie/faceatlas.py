"""The GNM face atlas: what GNM's identity space expresses, and the face sliders as WHOLE-MODEL directions in it
(facesliders, 2026-10-09; Joe: "every hand-made slider we made should control the model as a whole ... we need to
comprehend the model"; the study: docs/notes/gnm_atlas.md).

- `attributes(V, J)` measures a head (GNM's raw vertices and joints, its frame) by every attribute a slider or a
  checklist item names: humanmacro's macros + lid / lip / nose / jaw / eye-depth / malar attributes (mm).
- `table()` (face_atlas.npz, built by `build(n)` from heads sampled from GNM's prior N(0, 1) over the 120 head
  components): per attribute its mean, its linear model in the components (B), its population sd and R2.
- `direction(change, hold)`: the identity move for an attribute change, the CONDITIONAL MEAN of the identity given
  it (Gaussian conditioning on the prior: dc = B_S^T (B_S B_S^T)^-1 da over the asked and held attributes S): one
  attribute changes by da and everything the population couples with it comes along, but what `hold` names stays.
  That is humanmacro's free direction for one attribute and its held mode generalised to named holds.
- `COUPLED`: the face sliders that ARE such directions (an attribute GNM expresses, R2 ~ 1); base.head.slider_mode
  "coupled" applies them through the identity (base.gnm_head), the rest stay local morphs for detail GNM lacks
  (the crease, lid margin, lower-lip taper, tip definition...). +1 = +1 population sd of the attribute.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

TABLE = Path(__file__).with_name("face_atlas.npz")
K = 120
_C: dict = {}
MM = 0.001
NOSE_DEPTH = 0.003  # m behind the nose section's crest its width is read at (faceatlas._nose_width)

# face slider -> the attribute it moves when coupled (+1 = +1 sd of it in GNM's population)
COUPLED = {
    "canthal_tilt": "eye_tilt", "brow_ridge": "brow_ridge", "eye_setback": "eye_setback", "malar_rise": "malar_rise",
    "lip_upper_height": "upper_vermilion", "lip_lower_height": "lower_vermilion", "lip_bow": "bow_depth",
    "lip_upper_roll": "upper_lip_proj", "lip_lower_roll": "lower_lip_proj", "nostril_show": "nostril_show",
    "eye_hood": "fold_overhang", "eye_opening": "lid_aperture", "gonion_height": "gonion_height",
    "ramus_angle": "ramus_angle",
}
# (the nose's widths stay local morphs: no geometric reader of them was smooth in the identity (R2 ~ 0 for the
# slope's turn and for a fixed depth behind the crest, 2000 heads); faceslide.nose_widths reads them by shading)
# sliders whose attribute the identity explains only partly: the coupled direction + the local morph for the rest
# (x the share the identity leaves, 1 - R2)
HYBRID = {"eye_hood"}


def _gnm():
    if "g" not in _C:
        from . import base as basemod
        g = basemod._gnm_data()
        names = [str(x) for x in g["identity_names"]]
        comps = [i for i, x in enumerate(names) if x.startswith("head")][:K]
        _C["g"] = {"comps": comps, "V0": g["template_vertex_positions"].astype(float),
                   "IB": np.asarray(g["vertex_identity_basis"])[comps].astype(np.float32).reshape(len(comps), -1),
                   "J0": g["template_joint_positions"].astype(float),
                   "JB": np.asarray(g["joint_identity_basis"])[comps].astype(float)}
    return _C["g"]


def head(c) -> tuple:
    """(V, J) of GNM's head at identity c (the 120 head components), its frame."""
    G = _gnm()
    c = np.asarray(c, float)
    return G["V0"] + (c @ G["IB"]).reshape(-1, 3), G["J0"] + np.tensordot(c, G["JB"], 1)


def _nose_width(X, n, ext, lm, y, ylo):
    """The nose's dorsal width at height y: across the face, the front-most surface per 0.5 mm of x (a horizontal
    section seen from the front), its slope; the dorsal lines are where the side walls turn past 35 degrees from
    the dorsum's own plane, nearest the middle on each side (mm). nan where the section has no clear dorsum."""
    s = ext & (np.abs(X[:, 1] - y) < 1.0 * MM) & (np.abs(X[:, 0]) < 0.018) & (X[:, 1] > ylo)
    if s.sum() < 20:
        return np.nan
    xs = np.arange(-18.0, 18.01, 0.5) * MM
    zf = np.full(len(xs), np.nan)
    for i, x in enumerate(xs):
        q = s & (np.abs(X[:, 0] - x) < 0.5 * MM)
        if q.any():
            zf[i] = X[q, 2].max()
    ok = np.isfinite(zf)
    if ok.sum() < 20:
        return np.nan
    zf = np.interp(xs, xs[ok], zf[ok])
    # the section's width DEPTH_W behind its crest (its slope's turn was noise to the identity: R2 ~ 0 over 2000
    # heads; a fixed depth is a smooth read of how broad the nose's top is there)
    c = int(np.argmax(zf))
    inside = zf >= zf[c] - NOSE_DEPTH
    l_, r = c, c
    while l_ > 0 and inside[l_ - 1]:
        l_ -= 1
    while r < len(xs) - 1 and inside[r + 1]:
        r += 1
    lo = xs[l_] - (xs[1] - xs[0]) * ((zf[c] - NOSE_DEPTH) - zf[l_ - 1]) / max(zf[l_] - zf[l_ - 1], 1e-9) if l_ > 0 else xs[l_]
    hi = xs[r] + (xs[1] - xs[0]) * (zf[r] - (zf[c] - NOSE_DEPTH)) / max(zf[r] - zf[r + 1], 1e-9) if r < len(xs) - 1 else xs[r]
    return float(hi - lo) * 1000


def attributes(V, J) -> dict:
    """Every attribute of a head (GNM's raw vertices V and joints J, its frame): humanmacro's macros and ours."""
    from . import faceslide, humanmacro
    w = np.stack([V[:, 0], -V[:, 2], V[:, 1]], -1)
    a = dict(humanmacro.measures(w))
    Th = faceslide.head_template(V)
    X, n, lm, ext = Th["X"], Th["n"], Th["lm"], Th["ext"]
    faceslide._left_fields(Th)
    Hc, H0, u, up = faceslide._CACHE["last_crease"]
    mid = up & (u > 0.35) & (u < 0.65)
    c_in, c_out = lm[42], lm[45]
    wd = float(np.linalg.norm(c_out - c_in))
    ex = (c_out - c_in) / wd
    uk = lambda p: float((p - c_in) @ ex / wd)  # noqa: E731
    ym = faceslide._quad(np.array([0.0, uk(lm[43]), uk(lm[44]), 1.0]), np.array([c_in[1], lm[43][1], lm[44][1], c_out[1]]))
    h = X[:, 1] - ym(np.clip(u, 0, 1))
    hc = float(np.median(np.broadcast_to(np.asarray(Hc, float), H0.shape)[mid]))
    zat = lambda hh: float(np.median(X[mid & (np.abs(h - hh) < 0.6 * MM), 2])) if (mid & (np.abs(h - hh) < 0.6 * MM)).any() else np.nan  # noqa: E731
    a["crease_height"] = hc * 1000
    a["fold_overhang"] = (zat(hc + 2 * MM) - zat(hc)) * 1000
    a["lid_aperture"] = float((0.5 * (lm[43] + lm[44]) - 0.5 * (lm[46] + lm[47]))[1]) * 1000
    a["upper_vermilion"] = float(lm[51][1] - lm[62][1]) * 1000
    a["lower_vermilion"] = float(lm[66][1] - lm[57][1]) * 1000
    a["bow_depth"] = float(0.5 * (lm[50][1] + lm[52][1]) - lm[51][1]) * 1000
    a["upper_lip_proj"] = float(lm[51][2] - lm[33][2]) * 1000
    a["lower_lip_proj"] = float(lm[57][2] - lm[8][2]) * 1000
    a["lower_lip_width"] = float(abs(lm[55][0] - lm[59][0]) / max(abs(lm[54][0] - lm[48][0]), 1e-6))
    a["nostril_show"] = float(0.5 * (lm[31][1] + lm[35][1]) - lm[33][1]) * 1000
    yb = lm[33][1]
    a["radix_width"] = _nose_width(X, n, ext, lm, lm[27][1] + 0.15 * (lm[30][1] - lm[27][1]), yb)
    a["dorsum_width"] = _nose_width(X, n, ext, lm, lm[27][1] + 0.5 * (lm[30][1] - lm[27][1]), yb)
    a["tip_width"] = _nose_width(X, n, ext, lm, lm[30][1] + 0.0015, yb)
    a["gonion_height"] = float(0.5 * (lm[4][1] + lm[12][1]) - lm[57][1]) * 1000
    d = lm[4] - lm[2]
    a["ramus_angle"] = float(np.degrees(np.arctan2(abs(d[0]), abs(d[1]))))
    eye = J[2] if J[2][0] > 0 else J[3]
    a["eye_setback"] = float(lm[27][2] - eye[2]) * 1000
    pm = 0.5 * (lm[46] + lm[47]) + np.array([0.004, -0.016, 0.0])
    cheek = ext & (np.linalg.norm(X - pm, axis=1) < 4 * MM)
    a["malar_rise"] = float(np.median(X[cheek, 2]) - 0.5 * (lm[42][2] + lm[45][2])) * 1000 if cheek.any() else np.nan
    return a


def build(n: int = 2000, seed: int = 0, log=print) -> dict:
    """Sample n heads from the prior, measure them, fit each attribute's linear model; writes face_atlas.npz."""
    rng = np.random.default_rng(seed)
    C = rng.normal(0, 1, (n, K))
    rows, names = [], None
    for i in range(n):
        a = attributes(*head(C[i]))
        names = names or list(a)
        rows.append([a[k] for k in names])
        if log and i % 250 == 0:
            log(f"atlas {i}/{n}")
    A = np.array(rows, float)
    X = np.c_[np.ones(n), C]
    a0, B, sd, r2 = [], [], [], []
    tr = np.arange(n) < int(0.8 * n)
    for j in range(A.shape[1]):
        ok = np.isfinite(A[:, j])
        beta = np.linalg.lstsq(X[ok & tr], A[ok & tr, j], rcond=None)[0]
        te = ok & ~tr
        r2.append(1 - np.mean((A[te, j] - X[te] @ beta) ** 2) / max(np.var(A[te, j]), 1e-30))
        a0.append(beta[0])
        B.append(beta[1:])
        sd.append(np.nanstd(A[:, j]))
    out = {"names": np.array(names), "a0": np.array(a0), "B": np.array(B), "sd": np.array(sd), "r2": np.array(r2),
           "corr": np.ma.corrcoef(np.ma.masked_invalid(A).T).filled(np.nan), "n": np.array(n)}
    np.savez(TABLE, **out)
    _C.pop("table", None)
    return out


def table() -> dict:
    if "table" not in _C:
        z = np.load(TABLE, allow_pickle=True)
        _C["table"] = {k: z[k] for k in z.files}
        _C["table"]["index"] = {str(k): i for i, k in enumerate(_C["table"]["names"])}
    return _C["table"]


def within_sex() -> np.ndarray:
    """(120, 120) GNM's identity covariance WITHIN one sex. GNM's prior pools both (its size couplings match ANSUR II
    pooled, not within-sex: docs/notes/gnm_atlas.md): two equal halves at +-delta/2, delta = the identity move that
    makes ANSUR II's male - female differences (bizygomatic, face height, head breadth / length, interpupillary, ear
    length), so within a sex the covariance is I - delta delta^T / 4."""
    t = table()
    d = np.asarray(t.get("delta_sex", np.zeros(K)), float)
    return np.eye(K) - np.outer(d, d) / 4


def direction(change: dict, hold=(), eps: float = 1e-6, within: bool = True) -> np.ndarray:
    """(120,) the identity move that changes the named attributes by `change` ({attribute: amount in its own units})
    and leaves the `hold` attributes put, everything else as the population couples it: the conditional mean
    dc = S B^T (B S B^T)^-1 da, S the identity covariance WITHIN the head's sex (within=True: a free direction never
    trades the change for a sex change) or the pooled prior (I)."""
    t = table()
    names = list(change) + [h for h in hold if h not in change]
    idx = [t["index"][k] for k in names]
    Bs = t["B"][idx]
    S = within_sex() if within else np.eye(K)
    da = np.array([float(change.get(k, 0.0)) for k in names])
    return S @ Bs.T @ np.linalg.solve(Bs @ S @ Bs.T + eps * np.eye(len(idx)), da)


def slider_identity(sliders: dict, hold=()) -> tuple:
    """(dc (120,), the morph sliders left) for base.head.sliders in "coupled" mode: each COUPLED slider (value in the
    attribute's sds; [right, left] pairs take their mean: an identity move is both sides) as one joint conditioning
    (sliders asked together hold each other); HYBRID ones also keep (1 - R2) of their local morph."""
    from . import faceslide
    t = table()
    vals = faceslide.values(sliders)
    change, rest = {}, {}
    for k, (r, l_) in vals.items():
        if k in COUPLED and COUPLED[k] in t["index"]:
            a = COUPLED[k]
            change[a] = change.get(a, 0.0) + 0.5 * (r + l_) * float(t["sd"][t["index"][a]])
            if k in HYBRID:
                share = max(0.0, 1.0 - float(t["r2"][t["index"][a]]))
                rest[k] = [r * share, l_ * share]
        else:
            rest[k] = [r, l_]
    dc = direction(change, hold) if change else np.zeros(K)
    return dc, rest
