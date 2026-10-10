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


def _top_hit(P, F, xy):
    """The highest crossing of a vertical ray with the triangles (P, F) at each plan point (-inf: none)."""
    A, B, C = P[F[:, 0]], P[F[:, 1]], P[F[:, 2]]
    lo = np.minimum(np.minimum(A, B), C)[:, :2]
    hi = np.maximum(np.maximum(A, B), C)[:, :2]
    z = np.full(len(xy), -np.inf)
    for q, (x, y) in enumerate(xy):
        k = np.flatnonzero((lo[:, 0] <= x) & (hi[:, 0] >= x) & (lo[:, 1] <= y) & (hi[:, 1] >= y))
        if not len(k):
            continue
        a, b, c = A[k], B[k], C[k]
        v0, v1, w = b[:, :2] - a[:, :2], c[:, :2] - a[:, :2], np.array([x, y]) - a[:, :2]
        den = v0[:, 0] * v1[:, 1] - v0[:, 1] * v1[:, 0]
        ok = np.abs(den) > 1e-12
        s_ = np.where(ok, (w[:, 0] * v1[:, 1] - w[:, 1] * v1[:, 0]) / np.where(ok, den, 1), -1)
        t_ = np.where(ok, (v0[:, 0] * w[:, 1] - v0[:, 1] * w[:, 0]) / np.where(ok, den, 1), -1)
        inside = ok & (s_ >= -1e-9) & (t_ >= -1e-9) & (s_ + t_ <= 1 + 1e-9)
        if inside.any():
            z[q] = (a[:, 2] + s_ * (b[:, 2] - a[:, 2]) + t_ * (c[:, 2] - a[:, 2]))[inside].max()
    return z


def test_sea_fall_matches_mesh():
    """A river falling off a sea cliff (pushieworld note 120): the corridor along the fall is the cliff tile's LOD 0
    surface within cm (its dense mesh: marching cubes on the export's lattice, projected), the lip stands to the lip
    line and nothing stands over the sea in the sheet's path."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    import test_falls as tfa
    T = tfa._load(tfa.SPECS["sea"])
    cf, R, G, vols, cfg = tfa._cliff_field(T)
    f = T.falls[0]
    c, t_, n = tfa._frame(f)
    i, j = int((c[0] - G.origin[0]) // G.tile), int((c[1] - G.origin[1]) // G.tile)
    r = tm._tile_mc(cf, G, i, j, 0, vols)
    v = G.v(0)
    idx, F = r[0], r[1]
    P = np.c_[G.origin[0] + idx[:, 0] * v, G.origin[1] + idx[:, 1] * v, (idx[:, 2] + tm.ZOFF) * v]
    P, _ = tm.project(cf, P, v)
    lo, hi = G.origin + np.array([i, j]) * G.tile + 0.5, G.origin + np.array([i + 1, j + 1]) * G.tile - 0.5
    u = np.r_[np.arange(-6.0, -0.49, 0.25), np.arange(0.5, 8.01, 0.25)]  # (off the face itself: a vertical face has
    xy = np.concatenate([c + u[:, None] * t_ + s * n for s in np.linspace(-0.4, 0.4, 5) * f["width"]])  # any dz)
    uu = np.tile(u, 5)
    keep = np.all((xy >= lo) & (xy <= hi), axis=1)
    xy, uu = xy[keep], uu[keep]
    mesh = np.maximum(_top_hit(P, F, xy), R.height(xy[:, 0], xy[:, 1]))  # (the cliff tile, or the ground tile under it)
    cor = co.top(cf, R, xy[:, 0], xy[:, 1])
    dz = np.abs(cor - mesh)
    assert np.isfinite(mesh).all() and len(xy) > 100, len(xy)
    dry = mesh > f["pool"]["xyz"][2]
    assert np.median(dz) < 0.03 and np.percentile(dz[dry], 95) < 0.05 and dz[dry].max() < 0.15, \
        (np.median(dz), np.percentile(dz[dry], 95), dz[dry].max())
    # (under the sea the fallen blocks at the cliff's foot are sharper than the 0.5 m voxel: decimetres)
    assert np.percentile(dz[~dry], 95) < 0.4, np.percentile(dz[~dry], 95)
    up, dn = f["lip"][0][2], f["pool"]["xyz"][2]
    assert mesh[(uu >= -3) & (uu <= -0.5)].min() > up - 1.5  # (the lip stands to the lip line)
    assert mesh[(uu >= 0.5) & (uu <= 4.0)].max() < dn + 0.3  # (no rock over the sea under the sheet)
    print(f"ok sea fall: corridor vs the cliff tile's mesh, over the sea |dz| p50 {np.median(dz[dry]):.3f} p95 "
          f"{np.percentile(dz[dry], 95):.3f} max {dz[dry].max():.3f} m ({dry.sum()} points), under it p50 "
          f"{np.median(dz[~dry]):.3f} p95 {np.percentile(dz[~dry], 95):.3f} m ({(~dry).sum()})")


class _Slab:
    """A field with rock 25 m over its ground in a disc (a stack, rock built out over a sunk ground)."""
    rock = None

    def column(self, x, y):
        return np.zeros(len(x)), np.ones(len(x))

    def value(self, p):
        r = np.hypot(p[:, 0], p[:, 1])
        return np.where(r < 5.0, p[:, 2] - 25.0, p[:, 2])


def test_scan_starts_in_air():
    """Where the rock stands more than SCAN_UP over the column's ground, the scan starts higher (it found rock at its
    first point and fell back to the heightmap, metres under the mesh)."""
    z = co.top(_Slab(), None, np.array([0.0, 2.0, 20.0]), np.array([0.0, 0.0, 0.0]))
    assert abs(z[0] - 25.0) < 0.01 and abs(z[1] - 25.0) < 0.01 and abs(z[2]) < 0.01, z
    print("ok scan over rock 25 m up:", z.round(3))


if __name__ == "__main__":
    test_scan_starts_in_air()
    T = _load(SPEC)
    n, pts, took = test_corridors(T)
    print(f"ok: {n} rects, {pts / 1e6:.2f} M samples, {took:.1f} s")
    test_sea_fall_matches_mesh()
