"""hairmesh.py: a model's groom as numpy triangles on its OWN scalp: the hand locks (hair.lock_meshes, their [az, el, h]
addresses re-seated by each head's scalp rays) and the underlayer (the groom's volume sunk by the locks' thickness:
hair.cap_mesh(mass=True, sunk=True)). Run as a script: model ... -> lock count, how far lock roots sit off the scalp."""
import sys
import numpy as np
from hifipushie import hair, store


def groom_mesh(name: str, spec: dict | None = None, n: int = 16, across: int = 5, step: float = 2.0):
    spec = store.load(name) if spec is None else spec
    if not spec.get("hair"):
        return None
    sc = hair.scalp(name, spec)
    g = hair.groom_params(spec)
    locks = hair.resolve(spec, sc)
    LV, LQ = hair.lock_meshes(sc, locks, n=n, across=across)
    UV, UQ = hair.cap_mesh(sc, g, 0.0, mass=True, sunk=True, step=step)
    UV, UQ = np.asarray(UV, float), np.asarray(UQ, int)
    V = np.r_[LV, UV]
    Q = np.r_[LQ, UQ + len(LV)]
    F = np.r_[Q[:, [0, 1, 2]], Q[:, [0, 2, 3]]]
    col = np.r_[np.tile([150, 140, 128], (2 * len(LQ), 1)), np.tile([95, 88, 80], (2 * len(UQ), 1))].astype(float)
    # (order of F: all first triangles then all second ones; colours follow the same order)
    col = np.r_[np.tile([150, 140, 128], (len(LQ), 1)), np.tile([95, 88, 80], (len(UQ), 1)),
                np.tile([150, 140, 128], (len(LQ), 1)), np.tile([95, 88, 80], (len(UQ), 1))].astype(float)
    return V, F, col, sc, locks


if __name__ == "__main__":
    for nm in sys.argv[1:]:
        out = groom_mesh(nm)
        if out is None:
            print(nm, "no hair")
            continue
        V, F, col, sc, locks = out
        roots = np.array([lk["pts"][0] for lk in locks])
        a, e, h = sc.coords(roots)
        print(nm, len(locks), "locks;", len(F), "triangles; root height over the scalp mm p5/p50/p95",
              np.round(np.percentile(h * 1000, [5, 50, 95]), 1), "centre", np.round(sc.C, 3))
