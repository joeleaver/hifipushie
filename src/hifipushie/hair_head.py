"""The head a groom sits on: the scalp and its measures. Part of hair (hair.py has the overview)."""
from __future__ import annotations

import hashlib
import json

import numpy as np

from . import hair
from . import store
from .hair import HairError, _unit, az_el, dirs

# ------------------------------------------------------------------------------------------------ the head
class Scalp:
    """The head as rays from its centre: r(az, el) = where the body's surface is (a 2 degree grid, cached per body
    geometry), plus the face landmarks."""
    STEP = 2.0
    EL = (-70.0, 90.0)

    def __init__(self, C, R, lm):
        self.C = np.asarray(C, float)
        self.R = R  # (180, n_el)
        self.lm = lm
        self.A = np.arange(0.0, 360.0, self.STEP)
        self.E = np.arange(self.EL[0], self.EL[1] + 1e-6, self.STEP)

    def r(self, az, el):
        az = np.asarray(az, float) % 360
        el = np.clip(np.asarray(el, float), self.EL[0], self.EL[1])
        fa, fe = az / self.STEP, (el - self.EL[0]) / self.STEP
        ia, ie = np.floor(fa).astype(int), np.minimum(np.floor(fe).astype(int), len(self.E) - 2)
        ta, te = fa - ia, fe - ie
        ia0, ia1 = ia % len(self.A), (ia + 1) % len(self.A)
        R = self.R
        return ((1 - ta) * (1 - te) * R[ia0, ie] + ta * (1 - te) * R[ia1, ie] + (1 - ta) * te * R[ia0, ie + 1]
                + ta * te * R[ia1, ie + 1])

    def point(self, az, el, h):
        return self.C + (self.r(az, el) + np.asarray(h, float))[..., None] * dirs(az, el)

    def coords(self, P):
        """(az, el, h) of world points."""
        Q = np.asarray(P, float) - self.C
        az, el = az_el(Q)
        return az, el, np.linalg.norm(Q, axis=-1) - self.r(az, el)

    def normal(self, az, el, d=1.0):
        """The scalp's outward normal (finite differences on the grid)."""
        p = self.point(az, el, 0.0)
        ea = self.point(az + d, el, 0.0) - self.point(az - d, el, 0.0)
        ee = self.point(az, el + d, 0.0) - self.point(az, el - d, 0.0)
        n = _unit(np.cross(ea, ee))
        out = _unit(p - self.C)
        return np.where((n * out).sum(-1, keepdims=True) < 0, -n, n)


def _geometry_key(spec: dict) -> str:
    from .spec import geometry
    g = {k: v for k, v in geometry(spec).items() if k != "hair"}
    return hashlib.sha1(json.dumps(g, sort_keys=True, default=float).encode()).hexdigest()[:16]


def scalp(name: str, spec: dict | None = None) -> Scalp:
    """The model's Scalp (cached in memory and on disk by the body's geometry: hair edits never recompute it)."""
    spec = store.load(name) if spec is None else spec
    key = _geometry_key(spec)
    if key in hair._SCALPS:
        return hair._SCALPS[key]
    f = store._dir(name) / f"hair_scalp_{key}.npz"
    if f.exists():
        z = np.load(f, allow_pickle=False)
        sc = Scalp(z["C"], z["R"], json.loads(str(z["lm"])))
    else:
        sc = _measure(spec)
        for old in store._dir(name).glob("hair_scalp_*.npz"):
            old.unlink()
        np.savez(f, C=sc.C, R=sc.R, lm=json.dumps(sc.lm))
    sc.human = bool(spec.get("base"))  # (a base body: a human head, with or without face landmarks)
    hair._SCALPS[key] = sc
    return sc


def _measure(spec: dict) -> Scalp:
    from . import hair
    from . import sdf
    from .spec import compile_prims, expand_mirror, geometry
    g = {k: v for k, v in geometry(spec).items() if k != "hair"}
    J = expand_mirror(g)["joints"]
    need = ("lm_brow_mid.L", "lm_nose_base", "lm_jaw_0.L", "lm_brow_outer.L", "lm_nose_bridge")
    lm = {n: [float(x) for x in J[n]["pos"]] for n in J if n.startswith("lm_")}
    if all(n in J for n in need):
        j0 = np.array(lm["lm_jaw_0.L"])
        C = np.array([0.0, j0[1] + 0.01, lm["lm_brow_mid.L"][2] + 0.008])
    else:  # no base head (a kit-built creature): the head joint is the centre, the hairline by elevation angles
        cen = ((spec.get("hair") or {}).get("groom") or {}).get("centre", "head")
        if isinstance(cen, str):
            if cen not in J:
                raise HairError(f"hair needs the face landmarks {need} (a base head gives them) or a centre "
                                f"joint (groom.centre, default 'head')")
            C = np.asarray(J[cen]["pos"], float)
        else:
            C = np.asarray(cen, float)
        lm = {}
    streams = {ps[0].part: ps for ps in sdf.streams(compile_prims(g))}
    body = streams["body"]
    sc = Scalp(C, None, lm)
    AA, EE = np.meshgrid(sc.A, sc.E, indexing="ij")
    U = dirs(AA.ravel(), EE.ravel())
    ts = np.arange(0.02, 0.26, 0.003)
    F = sdf.field_at(body, (C + ts[None, :, None] * U[:, None, :]).reshape(-1, 3)).reshape(len(U), len(ts))
    if np.any(F[:, 0] >= 0):
        raise HairError(f"hair: the head centre {np.round(C, 3).tolist()} isn't inside the head")
    out = F >= 0
    i = np.argmax(out, 1)
    if ((spec.get("base") or {}).get("body") or {}).get("source") == "human":  # (one mesh) GNM's ear canals and
        # inner surfaces are pockets inside the head: a ray from the centre came out into one 4 cm in (behind the
        # ear), and the locks rooted there hung down the neck. The first crossing into air that STAYS air for
        # POCKET m (the outermost crossing instead sent rays under the ear on to the shoulders: curtains of hair)
        k = max(1, int(round(hair.POCKET / (ts[1] - ts[0]))))
        pad = np.concatenate([out, np.ones((len(out), k), bool)], 1)
        run = np.ones_like(out)
        for j in range(k + 1):
            run &= pad[:, j:j + out.shape[1]]
        i = np.where(run.any(1), np.argmax(run, 1), i)
    miss = ~out.any(1)
    lo, hi = ts[np.maximum(i - 1, 0)], ts[i]
    for _ in range(10):
        mid = (lo + hi) / 2
        fm = sdf.field_at(body, C + mid[:, None] * U)
        lo, hi = np.where(fm < 0, mid, lo), np.where(fm < 0, hi, mid)
    r = np.where(miss, ts[-1], hi)
    sc.R = r.reshape(AA.shape)
    return sc
