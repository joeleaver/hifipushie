"""Every slider as one field set: the nose's fields, `fields`, `values`, the head's fields, `delta`. Part of the face sliders (faceslide.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import faceslide
from .faceslide import _g, _ss, head_template, template, values
from .faceslide_eyes import _left_fields, _margin_fields
from .faceslide_mouth import _mouth_fields

def _nose_fields() -> dict:
    """The nose's sliders (whole nose, GNM frame, metres at +1). s along the dorsal line (lm 27 nasion = 0 .. lm 30 the
    tip = 1), x across from the midline: the widths move the side walls sideways in proportion to x (the dorsal line,
    x = 0, and the tip's position stay), held round the alar base (lm 31 / 35, the nostrils) and off the eyes' rims."""
    from scipy.spatial import cKDTree
    T = template()
    X, n, lm = T["X"], T["n"], T["lm"]
    mm = 0.001
    a, b = lm[27], lm[30]
    d = b - a
    L2 = float(d @ d)
    s = (X - a) @ d / L2
    x = X[:, 0] - 0.5 * (lm[31][0] + lm[35][0])
    ax = np.abs(x)
    hw_alar = 0.5 * abs(float(lm[35][0] - lm[31][0]))
    # the nose's own half-width along it: ~0.45 of the alar base at the root, 0.5 mid, 0.7 at the tip
    hw = hw_alar * np.interp(s, [0.0, 0.5, 0.85, 1.1], [0.45, 0.5, 0.65, 0.7])
    front = T["ext"] & (X[:, 2] > lm[27][2] - 0.02) & (s > -0.25) & (s < 1.2) & (ax < hw + 0.012)
    front &= X[:, 1] > lm[33][1] - 0.002  # (above the nostrils' floor)
    lat = _ss(ax / np.maximum(hw, 1e-4)) * (1 - _ss((ax - hw) / (6 * mm)))
    side = np.sign(x)[:, None] * np.array([1.0, 0.0, 0.0])
    alar = np.min([np.linalg.norm(X - lm[i], axis=1) for i in (31, 35, 32, 34)], axis=0)
    hold_alar = _ss((alar - 3.0 * mm) / (5.0 * mm))
    hold_eye = _ss((cKDTree(X[T["rim"]]).query(X)[0] - 4.0 * mm) / (5.0 * mm))
    F = {}
    F["nose_radix_width"] = (front * lat * _g(s, 0.1, 0.13) * hold_eye * hold_alar)[:, None] * side
    F["nose_dorsum_width"] = (front * lat * _g(s, 0.5, 0.15) * hold_alar * hold_eye)[:, None] * side
    # (held off the nostrils' insides: moving the rim's outside alone folded it against them)
    inner = T["skin"] & ~T["ext"] & (np.abs(x) < hw_alar + 0.005) & (X[:, 1] < lm[30][1]) & (X[:, 1] > lm[33][1] - 0.006)
    hold_nos = _ss((cKDTree(X[inner]).query(X)[0] - 1.5 * mm) / (3.5 * mm)) if inner.any() else 1.0
    tip = front * _g(s, 0.92, 0.1) * _ss(ax / (0.4 * hw_alar)) * (1 - _ss((ax - 0.75 * hw_alar) / (4 * mm)))
    F["nose_tip_width"] = (tip * hold_alar * hold_nos)[:, None] * side
    hump = front * _g(s, 0.45, 0.13) * _g(ax, 0, 0.6 * hw_alar)
    F["nose_dorsum_hump"] = hump[:, None] * np.array([0.0, 0.0, 1.0])[None]
    # nostril show: the alar rims (round lm 31 / 35, below the wings' middle) up, the columella (lm 33 up to the tip's
    # underside, the midline) down; the tip held
    up = np.array([0.0, 1.0, 0.0])
    rim = (front | (T["skin"] & (ax < hw_alar + 0.005))) & (X[:, 1] < lm[30][1])
    wing = np.min([np.linalg.norm(X - (lm[i] + np.array([0.0, -0.001, 0.0])), axis=1) for i in (31, 35)], axis=0)
    col = np.linalg.norm((X - 0.5 * (lm[33] + lm[30]))[:, [0, 1]] * [1.0, 0.6], axis=1)
    tipd = np.linalg.norm(X - lm[30], axis=1)
    hold_tip = _ss((tipd - 2.5 * mm) / (4 * mm))
    F["nostril_show"] = (rim * hold_tip)[:, None] * (_g(wing, 0, 3.0 * mm)[:, None] * up[None]
                                                    - 0.6 * (_g(col, 0, 2.0 * mm) * (ax < 3 * mm))[:, None] * up[None])
    # tip definition: a soft groove where the lobule meets each ala (from over the wing toward the domes), the
    # lobule's domes a little forward
    gp0 = lm[35] + np.array([-0.001, 0.0045, 0.002])
    gp1 = lm[30] + np.array([0.006, -0.002, -0.003])
    q = np.c_[np.abs(X[:, 0]), X[:, 1], X[:, 2]]
    seg = gp1 - gp0
    tt = np.clip((q - gp0) @ seg / float(seg @ seg), 0, 1)
    dseg = np.linalg.norm(q - (gp0 + tt[:, None] * seg), axis=1)
    groove = front * _g(dseg, 0, 1.3 * mm) * _ss(tt / 0.2) * _ss((1 - tt) / 0.25)
    domes = front * _g(np.linalg.norm(q - np.c_[np.full(len(X), 0.004), np.full(len(X), lm[30][1]), np.full(len(X), lm[30][2])], axis=1), 0, 2.5 * mm)
    F["tip_definition"] = -groove[:, None] * n + 0.35 * domes[:, None] * n
    mi = T["mirror"]  # (made exactly mirror symmetric: GNM's template is symmetric only to ~0.1 mm)
    return {k: 0.5 * (v + v[mi] * [-1.0, 1.0, 1.0]) * (faceslide.UNITS[k][0] * mm) for k, v in F.items()}


def fields() -> dict:
    """{name: ((n, 3) right side's, (n, 3) left side's)} metres at +1, GNM frame (n = GNM's + the loops' vertices).
    The eyes' are each eye's own (mirrored); the mouth's split at the centre line (smoothly)."""
    if "fields" not in faceslide._CACHE:
        T = template()
        mi = T["mirror"]
        out = {}
        for k, dL in _left_fields().items():
            dR = dL[mi] * [-1.0, 1.0, 1.0]
            out[k] = (dR, dL)
        for k, dL in _margin_fields().items():  # (eyedetail) the lid margins' thickness
            out[k] = (dL[mi] * [-1.0, 1.0, 1.0], dL)
        wl = _ss((T["X"][:, 0] + 0.002) / 0.004)[:, None]
        wl[mi == np.arange(len(mi))] = 0.5   # (faces4) a vertex that is its own mirror splits evenly: the nose's
        # fields are largest ON the centre line, where x ~ 0.1 mm put 3% of them on one side
        for k, d in {**_mouth_fields(), **_nose_fields()}.items():
            out[k] = (d * (1 - wl), d * wl)
        from pathlib import Path

        from . import gnmloops
        baked = Path(__file__).with_name("face_sliders_baked.npz")
        if baked.exists():  # (step 4: the older shape ops, baked by spikes/facesliders/bake_age.py)
            z = np.load(baked)
            # held off the lids' rims and the lips' contact (they were baked on a body's head, a few mm unlike the
            # template here: around those thin rolls the op's move turned the lips' border over, planes +1)
            from scipy.spatial import cKDTree
            X = T["X"]
            d_rim = cKDTree(X[T["rim"]]).query(X)[0]
            d_lip = cKDTree(T["lm"][48:68]).query(X)[0]
            hold = (T["ext"] * _ss((d_rim - 0.003) / 0.008) * _ss((d_lip - 0.003) / 0.005))[:, None]  # (exterior only)
            for k in faceslide.BAKED:
                if k in z.files:
                    d = gnmloops.ext(z[k].astype(float))
                    d = hold * 0.5 * (d + d[mi] * [-1.0, 1.0, 1.0])  # (baked on a body's head: made exactly mirror symmetric)
                    out[k] = (d * (1 - wl), d * wl)
        from . import faceext
        tab = faceext.table()
        for k in faceslide.EXT_SLIDERS:   # (the extensions: built by faceext.build into face_ext.npz)
            if k in tab:
                d = np.asarray(tab[k], float)
                out[k] = (d * (1 - wl), d * wl)
        faceslide._CACHE["fields"] = out
    return faceslide._CACHE["fields"]


def head_fields(V: np.ndarray, names=faceslide.HEAD_FIELDS) -> dict:
    """The HEAD_FIELDS on head V (GNM's raw vertices, its frame): ((n, 3) right, (n, 3) left), as fields()."""
    from . import gnmloops
    V = np.asarray(V, float)
    key = ("head_fields", hash(V.tobytes()), tuple(names))
    if key in faceslide._CACHE:
        return faceslide._CACHE[key]
    mi_raw = gnmloops._raw()["mirror"]
    mi = template()["mirror"]
    dL = _left_fields(head_template(V))
    dLm = _left_fields(head_template(V[mi_raw] * [-1.0, 1.0, 1.0]))  # the right eye as a left one
    out = {k: (dLm[k][mi] * [-1.0, 1.0, 1.0], dL[k]) for k in names}
    if len([k for k in faceslide._CACHE if isinstance(k, tuple) and k[0] == "head_fields"]) > 8:
        faceslide._CACHE.pop(next(k for k in faceslide._CACHE if isinstance(k, tuple) and k[0] == "head_fields"))
    faceslide._CACHE[key] = out
    return out


def delta(sliders: dict | None, V: np.ndarray | None = None) -> np.ndarray | None:
    """The sliders' sum, (n, 3) GNM frame, or None when none is set. V (the head's GNM vertices): HEAD_FIELDS are
    laid on its own shape (the crease on its own fold turn), not the template's."""
    vals = {k: v for k, v in values(sliders).items() if v != (0.0, 0.0)}
    if not vals:
        return None
    F = dict(fields())
    if V is not None and any(k in vals for k in faceslide.HEAD_FIELDS):
        F.update(head_fields(V, tuple(k for k in faceslide.HEAD_FIELDS if k in vals)))
    D = np.zeros_like(template()["X"])
    for k, (r, l_) in vals.items():
        if k not in F:  # (a coupled-only slider: faceatlas.COUPLED, nothing local to lay)
            continue
        D += r * F[k][0] + l_ * F[k][1]
    return D
