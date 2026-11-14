"""The body loose hair falls on: `Collider` and `collider` (the SDF body round the head, cached). Part of loose hair (hair_loose.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import hair_loose
from .hair_loose import _unit

# ------------------------------------------------------------------------------------------------ the body
class Collider:
    """The body's signed distance on a grid (m, + outside), read trilinearly."""

    def __init__(self, lo, step, phi):
        self.lo, self.step, self.phi = np.asarray(lo, float), float(step), np.asarray(phi, np.float32)
        self.g = None

    def _ix(self, P):
        return ((np.asarray(P, float) - self.lo) / self.step).T

    def at(self, P):
        from scipy.ndimage import map_coordinates
        return map_coordinates(self.phi, self._ix(P), order=1, mode="nearest")

    def grad(self, P):
        from scipy.ndimage import map_coordinates
        if self.g is None:
            self.g = [np.asarray(a, np.float32) for a in np.gradient(self.phi, self.step)]
        ix = self._ix(P)
        return _unit(np.stack([map_coordinates(a, ix, order=1, mode="nearest") for a in self.g], -1))

    def push(self, P, clear, rounds: int = 3):
        """Points moved out until they are `clear` m off the body."""
        P = np.array(P, float)
        for _ in range(rounds):
            need = np.asarray(clear, float) - self.at(P)
            m = need > 0
            if not m.any():
                break
            P[m] = P[m] + need[m, None] * self.grad(P[m])
        return P

    def mesh(self, every: int = 2) -> dict:
        """The body's surface as triangles (marching cubes on every `every`-th cell): Blender's collision proxy."""
        from skimage import measure
        ph = self.phi[::every, ::every, ::every]
        V, F, _, _ = measure.marching_cubes(ph, 0.0, spacing=(self.step * every,) * 3)
        return {"verts": (V + self.lo).astype(np.float32), "faces": F.astype(np.int32)}


def collider(name: str, spec: dict, sc) -> Collider:
    """The model's Collider (cached in memory and on disk by the body's geometry, like the scalp)."""
    from . import sdf, store
    from .hair_head import _geometry_key
    from .spec import compile_prims, geometry
    key = _geometry_key(spec)
    if key in hair_loose._COLL:
        return hair_loose._COLL[key]
    f = store._dir(name) / f"hair_body_{key}.npz"
    shared = store.HOME / "_cache" / f"hair_body_{key}.npz"  # (the same body under another name: a copy, a riff)
    if not f.exists() and shared.exists():
        f = shared
    if f.exists():
        z = np.load(f)
        c = Collider(z["lo"], float(z["step"]), z["phi"])
    else:
        from scipy import ndimage
        g = {k: v for k, v in geometry(spec).items() if k != "hair"}
        lo = sc.C + np.asarray(hair_loose.BOX[0])
        n = np.ceil((np.asarray(hair_loose.BOX[1]) - np.asarray(hair_loose.BOX[0])) / hair_loose.STEP).astype(int) + 1
        ax = [lo[i] + hair_loose.STEP * np.arange(n[i]) for i in range(3)]
        X = np.stack(np.meshgrid(*ax, indexing="ij"), -1).reshape(-1, 3)
        inside = np.zeros(len(X), bool)
        for ps in sdf.streams(compile_prims(g)):
            for i in range(0, len(X), 400000):
                inside[i:i + 400000] |= sdf.field_at(ps, X[i:i + 400000]) < 0
        ins = inside.reshape(n)
        phi = (ndimage.distance_transform_edt(~ins) - ndimage.distance_transform_edt(ins)) * hair_loose.STEP
        phi = phi - np.sign(phi) * 0.5 * hair_loose.STEP  # (the surface lies between an inside and an outside cell)
        phi = ndimage.gaussian_filter(phi, 0.8)
        c = Collider(lo, hair_loose.STEP, phi)
        for old in store._dir(name).glob("hair_body_*.npz"):
            old.unlink()
        np.savez_compressed(f, lo=c.lo, step=c.step, phi=c.phi)
        try:
            shared.parent.mkdir(exist_ok=True)
            for old in sorted(shared.parent.glob("hair_body_*.npz"), key=lambda q: q.stat().st_mtime)[:-7]:
                old.unlink()
            np.savez_compressed(shared, lo=c.lo, step=c.step, phi=c.phi)
        except OSError:
            pass
    hair_loose._COLL[key] = c
    return c
