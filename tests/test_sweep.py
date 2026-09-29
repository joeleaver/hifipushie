"""The sweep blob (sdf.sd_sweep): a band along a straight path is a rounded box; mirror makes both sides; a collar
profile has its stand and fall where the numbers put them.

Run: uv run python tests/test_sweep.py   (or pytest)."""

from __future__ import annotations

import numpy as np

from hifipushie import sdf
from hifipushie.spec import _sweep


def _band(**kw):
    path = [[0.0, 0.0, 0.0], [0.0, 0.0, 0.1]]
    bl = {"shape": "sweep", "path": path, "N": [[1, 0, 0]] * 2, "U": [[0, -1, 0]] * 2, "profile": "band",
          "values": {"n0": -0.01, "n1": 0.01, "u0": 0.0, "u1": 0.004, "round": 0.0}, "lip": 1.0, **kw}
    return _sweep("b", bl, 0.0)


def test_band_is_a_box():
    p = _band()
    box = {"c": np.array([0.0, -0.002, 0.05]), "size": np.array([0.01, 0.002, 0.05]), "rot": np.eye(3), "round": 0.0}
    rng = np.random.default_rng(1)
    q = rng.uniform([-0.03, -0.03, -0.02], [0.03, 0.03, 0.12], (2000, 3))
    a = sdf.sd_sweep(q, p.params)
    b = sdf.sd_box(q, box)
    assert np.abs(a - b).max() < 1e-9, np.abs(a - b).max()


def test_mirror():
    path = [[0.02, 0.0, 0.0], [0.02, 0.0, 0.1]]
    p = _band(path=path, mirror=True)  # a path off the mirror plane: both ends capped
    q = np.array([[0.02, -0.002, 0.05], [-0.02, -0.002, 0.05], [0.0, -0.002, 0.05]])
    d = sdf.sd_sweep(q, p.params)
    assert d[0] < 0 and d[1] < 0 and d[2] > 0, d
    assert p.lo[0] < -0.02 and p.hi[0] > 0.02


def test_collar_profile():
    # a straight "neckline" along x, outward -y, up z: stand to 0.03 up, fall hanging straight down (phi 0)
    bl = {"shape": "sweep", "path": [[-0.1, 0, 0], [0.1, 0, 0]], "N": [[0, -1, 0]] * 2, "U": [[0, 0, 1]] * 2,
          "profile": "collar", "values": {"t": 0.0015, "stand": 0.03, "lean": 0.0, "fall": 0.035, "phi": 0.0,
                                          "sink": 0.0, "point": 0.0}, "lip": 1.0}
    p = _sweep("c", bl, 0.0)
    q = np.array([[0, 0, 0.015],        # in the stand
                  [0, -0.0025, 0.015],  # in the fall, in front of it
                  [0, -0.0025, -0.004], # the fall reaches below the neckline
                  [0, -0.008, 0.015]])  # outside both
    d = sdf.sd_sweep(q, p.params)
    assert d[0] < 0 and d[1] < 0 and d[2] < 0 and d[3] > 0, d


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
