"""gk.py: GNM identities' upper-lid crease, measured (gnmcrease). Shared readers.

geo(c, e=None)   the eye step's Reader (blockin_eyes, subject's left eye, 3 sagittal columns) on the head as it ships
                 (onemesh.head_template of a block-in base with the identity swapped, expression / lid pose cleared),
                 plus profile extras per column (mean over the 3): hidden (skin arclength hidden from a level front
                 view, mm), hidden10 (camera 10 deg above), narrow (local depth on a +-0.75 mm chord), krad (the
                 crease valley's least radius of curvature, mm), lip (the fold edge's convexity above the crease,
                 1/mm), and the mid column's profile resampled (for later).
clay(c)          lidgnm's clay crop (raw GNM head, calibrated detector points) + lidfold.read_lid: mid columns of
                 both eyes: tps, dark, width.
macro(c)         humanmacro z-scores (the eye-region ones and the rest).
"""
import copy
import numpy as np

from hifipushie import blockin as bi, blockin_eyes as be, humanmacro as hm, store

_B = {}
LN, RN, _ = be._names()
_CAP = []
_orig_profile = be._profile


def _cap_profile(P, *a, **k):
    _CAP.append(np.asarray(P, float).copy())
    return _orig_profile(P, *a, **k)


be._profile = _cap_profile


def base(model="gd_T12"):
    if model not in _B:
        b = copy.deepcopy(store.load(model)["base"])
        b["head"].pop("expression", None)
        p = dict(b["head"].get("pose") or {})
        p.pop("lid_upper", None)
        p.pop("lid_lower", None)
        b["head"]["pose"] = p
        if not p:
            b["head"].pop("pose")
        _B[model] = b
    return _B[model]


_RD = {}


def head(c, e=None, model="gd_T12"):
    ht, _ = be._head(base(model), np.asarray(c, float), np.zeros(be.NE) if e is None else np.asarray(e, float), LN, RN)
    return ht


def extras(P):
    """P: (forward, up) m, margin first."""
    d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    s = np.arange(0, d[-1], 0.00005)
    Q = np.c_[np.interp(s, d, P[:, 0]), np.interp(s, d, P[:, 1])] * 1000     # mm
    h = Q[:, 1] - Q[0, 1]
    band = (h > 1.0) & (h < 12.0)
    out = {}
    for nm, el in (("hidden", 0.0), ("hidden10", np.radians(10))):
        # view direction: from the camera toward the face = -forward rotated up by el (camera above looks down)
        # screen height coordinate: u = h*cos(el) + f*sin(el)... a point is hidden if another point has the same
        # screen coordinate and is nearer the camera
        u = Q[:, 1] * np.cos(el) - Q[:, 0] * np.sin(el)
        depth = Q[:, 0] * np.cos(el) + Q[:, 1] * np.sin(el)     # larger = nearer the camera
        o = np.argsort(u)
        us, ds = u[o], depth[o]
        hid = np.zeros(len(Q), bool)
        # bin by screen coordinate (0.02 mm): within a bin, all but the nearest are hidden
        b = np.floor(us / 0.02).astype(int)
        ub, inv = np.unique(b, return_inverse=True)
        mx = np.full(len(ub), -np.inf)
        np.maximum.at(mx, inv, ds)
        hid[o] = ds < mx[inv] - 0.05
        out[nm] = float(hid[band].sum() * 0.05)
    # local depth on a narrow chord
    def local(k):
        dep = np.full(len(Q), np.nan)
        a, b2 = Q[:-2 * k], Q[2 * k:]
        ab = b2 - a
        Ln = np.linalg.norm(ab, axis=1)
        nrm = np.c_[ab[:, 1], -ab[:, 0]] / np.maximum(Ln, 1e-9)[:, None]
        dep[k:-k] = -((Q[k:-k] - a) * nrm).sum(1)
        return dep
    dn = local(15)            # +-0.75 mm
    dw = local(50)            # +-2.5 mm
    ok = band & np.isfinite(dw)
    i = np.flatnonzero(ok)[np.nanargmax(dw[ok])] if ok.any() else None
    out["narrow"] = float(np.nanmax(dn[ok])) if ok.any() else 0.0
    # curvature: turning of the tangent per mm, smoothed over 0.3 mm (signed: concave (valley) positive)
    t = np.gradient(Q, axis=0)
    ang = np.unwrap(np.arctan2(t[:, 1], t[:, 0]))
    k = np.gradient(ang) / 0.05
    w = 6
    ks = np.convolve(k, np.ones(w) / w, mode="same")
    # sign: walking up the lid from the margin, the face's outside is +forward; a valley turns the tangent toward +forward
    # first then back... use the local depth's sign: concave where dn > 0
    if i is not None:
        win = (np.abs(h - h[i]) < 1.5)
        kv = np.abs(ks[win & (dn > 0)])
        out["krad"] = float(1.0 / kv.max()) if kv.size and kv.max() > 1e-6 else 99.0
        up = (h > h[i]) & (h < h[i] + 3.0) & (dn < 0)
        out["lip"] = float(np.abs(ks[up]).max()) if up.any() else 0.0
        out["h_crease"] = float(h[i])
    else:
        out.update(krad=99.0, lip=0.0, h_crease=np.nan)
    return out


def geo(c, e=None, model="gd_T12"):
    ht = head(c, e, model)
    key = model
    if key not in _RD:
        _RD[key] = be.Reader(ht)
    _CAP.clear()
    q = _RD[key].read(ht)
    ex = [extras(P) for P in _CAP]
    out = {k: float(v) for k, v in q.items()}
    for k in ex[0] if ex else []:
        out["x_" + k] = float(np.nanmean([x[k] for x in ex]))
    out["x_hidden_max"] = float(max([x["hidden"] for x in ex], default=0.0))
    prof = None
    if _CAP:
        P = _CAP[len(_CAP) // 2]
        d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
        s = np.linspace(0, min(d[-1], 0.02), 200)
        prof = np.c_[np.interp(s, d, P[:, 0]), np.interp(s, d, P[:, 1])]
    return out, prof, ht


def clay(c):
    import lidgnm, perc
    cc = np.zeros(len(perc.ID_NAMES))
    cc[lidgnm.HC] = c
    im, P, r = lidgnm.read(perc.verts(cc))
    mids = [eye[1] for eye in r]
    cols = [col for eye in r for col in eye]
    f = lambda k, L: float(np.nanmean([x.get(k, np.nan) for x in L]))  # noqa: E731
    return {"tps": f("tps", mids), "dark": f("dark", mids), "width": f("width", mids),
            "dark_all": f("dark", cols), "dark_max": float(max(x["dark"] for x in cols))}, im, P, r


def macro(c):
    z = hm.read(V=hm.head(np.asarray(c, float)))
    return {k: float(v) for k, v in z.items()}
