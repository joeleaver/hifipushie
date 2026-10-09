"""Snags and limbs in the streams (terrain_snags; pushieworld note 119, for a 0.25 m water pass's wakes and pile-ups):
clutter rows of kinds snag / limb with a capsule (two axis ends + diameter) in csv_version 3's last columns, placed on
outer bends, steep wooded reaches, boulders' upstream sides, bar heads and wedged across narrow channels; each end
resting on what holds it (the bed, a bank) and nothing of the axis inside the ground, the rock or a boulder.
uv run python tests/test_snags.py"""
import json
import tempfile
import time
from pathlib import Path

import numpy as np

from hifipushie import terrain, terrain_mesh as tm, terrain_snags, terrain_stream

SPEC = {"world": {"kind": "farmland", "base": 40}, "extent": [[0, 0], [256, 320]], "cell": 1.0,
        "rivers": {"beck": {"source": [128, 310, 62], "through": [[100, 230], [150, 170], [110, 100]],
                            "mouth": [128, 10, 20], "water": 3, "valley": {"profile": "V", "floor": 20}}},
        "cover": [{"type": "meadow", "in": "everywhere"}, {"type": "deciduous", "in": "everywhere"}]}


def _load(spec):
    d = Path(tempfile.mkdtemp())
    (d / "spec.json").write_text(json.dumps(spec))
    return terrain.load(d / "spec.json")


def test_snags(T):
    cfg = dict(tm.DEFAULTS)
    base, vols, notes, caves = tm.build_field(T, cfg)
    mats = tm.Materials(T, base)
    C = terrain_stream.all_clutter(T, mats, base)
    kinds = list(terrain_stream.KINDS)
    assert C.shape[1] == terrain_stream.COLS == 18
    cap = np.isin(C[:, 3], [kinds.index("snag"), kinds.index("limb")])
    assert (~np.isnan(C[cap, 11:18])).all() and np.isnan(C[~cap, 11:18]).all()
    S = C[cap]
    n_snag, n_limb = int((S[:, 3] == kinds.index("snag")).sum()), int((S[:, 3] == kinds.index("limb")).sum())
    assert n_snag >= 3 and n_limb >= 3, (n_snag, n_limb)
    p0, z0, p1, z1, d = S[:, 11:13], S[:, 13], S[:, 14:16], S[:, 16], S[:, 17]
    assert (z0 <= z1 + 1e-9).all()  # (end 0 the lower)
    # each end rests on the ground at its column: no floating end, no end in the ground
    h0, _ = base.column(p0[:, 0], p0[:, 1])
    h1, _ = base.column(p1[:, 0], p1[:, 1])
    assert np.abs(z0 - 0.5 * d - h0).max() < 1e-6 and np.abs(z1 - 0.5 * d - h1).max() < 1e-6
    # nothing of the axis in the ground or the rock between
    t = np.linspace(0.05, 0.95, 19)
    P = p0[:, None] + (p1 - p0)[:, None] * t[None, :, None]
    Z = z0[:, None] + (z1 - z0)[:, None] * t[None]
    hz, _ = base.column(P[..., 0].ravel(), P[..., 1].ravel())
    assert ((Z - 0.5 * d[:, None]).ravel() >= hz - terrain_snags.CLEAR - 1e-6).all()
    # nor through a boulder placed beside it
    rk = C[(C[:, 3] == kinds.index("river_rock"))]
    _, _, ok = terrain_snags.rest(base, rk, p0, p1, d)
    assert ok.all()
    # snags: one end in the water (under the river's level), sloping up out of it onto the bank
    sn = S[:, 3] == kinds.index("snag")
    lv = mats.streams.sample(p0[sn])["level"]
    assert (z0[sn] - 0.5 * d[sn] < lv).mean() > 0.9, (z0[sn] - lv)
    assert (z1[sn] - z0[sn] > 0).all()
    # the row's own columns agree with its capsule: middle, length, yaw from end 0 to end 1
    mid = 0.5 * (p0 + p1)
    assert np.abs(S[:, :2] - mid).max() < 1e-6
    assert np.abs(S[:, 4] - np.linalg.norm(p1 - p0, axis=1)).max() < 1e-6
    yaw = np.degrees(np.arctan2(p1[:, 1] - p0[:, 1], p1[:, 0] - p0[:, 0])) % 360
    assert np.abs((S[:, 5] - yaw + 180) % 360 - 180).max() < 1e-6
    # the manifest says what they are and how to stamp them
    m = terrain_stream.manifest(mats.streams, C)
    assert m["csv_version"] == 3 and m["columns"].endswith("x0,y0,z0,x1,y1,z1,diameter")
    assert m["kinds"]["snag"]["footprint"]["shape"] == "capsule" and "capsule" in m["how"]
    return n_snag, n_limb


def test_rest_rejects_a_hump():
    """A capsule whose straight axis would pass through the ground between its ends is dropped, not lifted."""
    class F:
        def column(self, x, y):
            x = np.asarray(x, float)
            return np.where(np.abs(x - 5.0) < 1.0, 1.0, 0.0), np.ones_like(x)

        def value(self, p):
            return p[:, 2] - self.column(p[:, 0], p[:, 1])[0]
    p0, p1 = np.array([[0.0, 0.0], [0.0, 0.0]]), np.array([[10.0, 0.0], [3.0, 0.0]])
    z0, z1, ok = terrain_snags.rest(F(), None, p0, p1, np.array([0.2, 0.2]))
    assert list(ok) == [False, True] and np.allclose(z0, 0.1), (ok, z0)


if __name__ == "__main__":
    test_rest_rejects_a_hump()
    t = time.time()
    T = _load(SPEC)
    n_snag, n_limb = test_snags(T)
    print(f"ok: {n_snag} snags, {n_limb} limbs, {time.time() - t:.0f} s")
