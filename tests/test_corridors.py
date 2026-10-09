"""River-corridor heightmaps (terrain_corridors; pushieworld note 118, gdamp's nested 0.25 m water solve): rects of at
most 128 m covering every river's water path + 15 m, sampled from the export's field: the ground tiles' heightmap
(pushed under the cliffs) or the cliff mesh's rock where it stands higher. A river with a 12 m fall (its face meshed
as cliff). uv run python tests/test_corridors.py"""
import json
import tempfile
import time
from pathlib import Path

import numpy as np

from hifipushie import terrain, terrain_cliffs, terrain_corridors as co, terrain_mesh as tm

SPEC = {"world": {"kind": "farmland", "base": 40}, "extent": [[0, 0], [256, 320]], "cell": 1.0,
        "rivers": {"beck": {"source": [128, 310, 62], "through": [[120, 200], [136, 110]], "mouth": [128, 10, 20],
                            "water": 3, "valley": {"profile": "V", "floor": 20},
                            "falls": [{"at": 0.62, "drop": 12, "width": 5}]}},
        "cover": [{"type": "meadow", "in": "everywhere"}], "export": {"tiles": {"tile": 64}}}


def _load(spec):
    d = Path(tempfile.mkdtemp())
    (d / "spec.json").write_text(json.dumps(spec))
    return terrain.load(d / "spec.json")


def test_corridors(T):
    cfg = {**tm.DEFAULTS, **SPEC["export"]["tiles"], "corridors": True}
    base, vols, notes, caves = tm.build_field(T, cfg)
    G = tm.Grid(T, cfg)
    R = terrain_cliffs.Region(T, base, G, cfg)
    cf = terrain_cliffs.CliffField(base, R)
    c = co.config(cfg)
    rs = co.rects(T, c)
    assert rs and all(np.all(r["hi"] - r["lo"] <= 128.0 + 1e-9) for r in rs), rs
    # every point of the water's path, 15 m out either side, is in a rect
    w = T.river_water_lines["beck"]
    xy = np.asarray(w["xy"], float)[:, :2]
    for off in (np.array([15.0, 0.0]), np.array([-15.0, 0.0]), np.array([0.0, 0.0])):
        p = xy + off
        p = p[(p >= [T.xs[0], T.ys[0]]).all(1) & (p <= [T.xs[-1], T.ys[-1]]).all(1)]
        cov = np.zeros(len(p), bool)
        for r in rs:
            cov |= np.all((p >= r["lo"]) & (p <= r["hi"]), axis=1)
        assert cov.all(), p[~cov][:5]
    # the pushed heightmap on a grid equals Region.height
    xs = 100 + 0.25 * np.arange(60)
    ys = 140 - 0.25 * np.arange(50)
    X, Y = np.meshgrid(xs, ys)
    g = co.pushed_grid(R, xs, ys)
    assert np.abs(g.ravel() - R.height(X.ravel(), Y.ravel())).max() < 1e-9
    # written: float32, row 0 north, extent and shape agree; the top is the surface (air just over, rock or the
    # ground's heightmap just under)
    out = Path(tempfile.mkdtemp())
    t = time.time()
    m = co.write(T, cf, R, out, cfg, log=lambda *a: None)
    took = time.time() - t
    rng = np.random.default_rng(1)
    on_cliff = 0
    for e in m["rects"]:
        H = np.load(out / e["file"])
        assert H.dtype == np.float32 and H.shape == (e["rows"], e["cols"]), (H.shape, e)
        (x0, y0), (x1, y1) = e["extent"]
        assert abs(x0 + (e["cols"] - 1) * e["spacing"] - x1) < 1e-6 and abs(y0 + (e["rows"] - 1) * e["spacing"] - y1) < 1e-6
        r_, c_ = rng.integers(0, e["rows"], 300), rng.integers(0, e["cols"], 300)
        px, py, pz = x0 + c_ * e["spacing"], y1 - r_ * e["spacing"], H[r_, c_].astype(float)
        assert (cf.value(np.c_[px, py, pz + 0.05]) > 0).all()  # (air over the top: nothing of the cliff mesh above)
        gh = R.height(px, py)
        assert (pz >= gh - 1e-3).all()  # (never under the ground tile)
        cl = pz > gh + 0.01
        on_cliff += int(cl.sum())
        if cl.any():  # (where the cliff's rock is on top: rock just under it)
            assert (cf.value(np.c_[px[cl], py[cl], pz[cl] - 0.05]) <= 0).mean() > 0.97
    assert on_cliff > 0  # (the fall's face and lip are cliff mesh)
    return len(m["rects"]), sum(e["rows"] * e["cols"] for e in m["rects"]), took


if __name__ == "__main__":
    T = _load(SPEC)
    n, pts, took = test_corridors(T)
    print(f"ok: {n} rects, {pts / 1e6:.2f} M samples, {took:.1f} s")
