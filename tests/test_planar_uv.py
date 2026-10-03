"""parts.<p>.uv = "planar" (asset.planar_uvs): a swappable flat surface gets upright, unmirrored 0..1 UVs.
  uv run python tests/test_planar_uv.py"""
from __future__ import annotations

import numpy as np

from hifipushie import asset


def _uv(V, normal, at):
    V = np.asarray(V, float)
    n = len(V)
    r = asset.planar_uvs({"verts": V, "corner_vert": np.arange(n), "normal": np.tile(normal, (n, 1)),
                          "uv": np.zeros((n, 2), np.float32), "tangent": np.zeros((n, 3), np.float32),
                          "sign": np.ones(n, np.float32)})
    i = next(k for k in range(n) if np.allclose(V[k], at))
    return r, r["uv"][i]


def test_a_dial_reads_upright_from_its_front():
    """A clock dial facing -Y (the way props face): its top-right as seen from the front is u = 1, v = 1."""
    V = [[x, y, z] for x in (-0.5, 0.5) for y in (0.0, 0.01) for z in (0.0, 1.0)]
    r, uv = _uv(V, [0, -1, 0], [0.5, 0, 1])
    assert np.allclose(uv, [1, 1]), uv
    assert r["uv"].min() >= -1e-9 and r["uv"].max() <= 1 + 1e-9
    assert np.allclose(np.abs(r["tangent"]) @ [1, 0, 0], 1) and (r["sign"] == 1).all()
    _, uv = _uv(V, [0, 1, 0], [0.5, 0.01, 1])  # facing +Y: seen from behind, +X is on the left
    assert np.allclose(uv, [0, 1], atol=1e-9), uv


def test_aspect_is_kept_and_centred():
    """A 2 x 1 table top seen from above (back = up): the long side spans 0..1, the short one is centred."""
    V = [[x, y, z] for x in (0.0, 2.0) for y in (0.0, 1.0) for z in (0.0, 0.02)]
    r, uv = _uv(V, [0, 0, 1], [2, 1, 0.02])
    assert np.allclose(uv, [1, 0.75]), uv
    assert np.allclose(r["uv"].min(0), [0, 0.25]) and np.allclose(r["uv"].max(0), [1, 0.75])


if __name__ == "__main__":
    for name, f in list(globals().items()):
        if name.startswith("test_") and callable(f):
            f()
            print("ok", name)
