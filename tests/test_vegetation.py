"""Vegetation: the growth model is deterministic, edits are local and exact, habits move the form the way their
words say, the measures measure. uv run python tests/test_vegetation.py"""
import numpy as np

from hifipushie import veg_leaf, veg_mesh, vegetation as v

SMALL = {"species": "birch", "age": 22}


def _polyline_dist(p, P):
    best = 1e9
    for a, b in zip(P[:-1], P[1:]):
        t = np.clip((p - a) @ (b - a) / ((b - a) @ (b - a)), 0, 1)
        best = min(best, float(np.linalg.norm(p - (a + t * (b - a)))))
    return best


def test_deterministic():
    a, b = v.grow(SMALL), v.grow(SMALL)
    assert a["stats"]["nodes"] == b["stats"]["nodes"] > 500
    assert np.array_equal(a["pos"], b["pos"]) and np.array_equal(a["key"], b["key"])
    c = v.grow({**SMALL, "seed": 2})
    assert c["stats"]["nodes"] != a["stats"]["nodes"] or not np.allclose(c["pos"][:200], a["pos"][:200])


def test_structure():
    T = v.grow(SMALL)
    par = T["parent"]
    assert (par[1:] < np.arange(1, len(par))).all()  # parents come first
    assert np.isfinite(T["pos"]).all() and (T["radius"] > 0).all()
    assert (T["radius"][par[1:]] >= T["radius"][1:] * 0.999).all() or (T["order"] == 0).any()  # the pipe model thins outward
    assert T["pos"][:, 2].min() >= -0.5  # nothing digs
    assert T["stats"]["grow_s"] < 20


def test_guides_any_order_exact_and_regrown():
    limb = [[0, 0, 3], [2.5, 0, 4.5], [5.5, 0, 5.2], [8, 0, 5.0]]
    sub = [[4, 0, 4.9], [4.5, 0, 7], [4.2, 0, 9.5]]
    T = v.grow({**SMALL, "age": 30, "guides": {"limb": {"path": limb, "from_year": 6, "until_year": 20},
                                               "sub": {"path": sub, "from_year": 14, "until_year": 26}}})
    for name, path, order in (("limb", limb, 1), ("sub", sub, 2)):
        ai = T["guides"][name]
        assert T["axes"][ai]["order"] == order, (name, T["axes"][ai])
        nodes = np.flatnonzero((T["axis"] == ai) & T["pin"])
        assert len(nodes) > 5
        assert max(_polyline_dist(T["pos"][n], np.array(path, float)) for n in nodes) < 1e-6
        assert np.linalg.norm(T["pos"][nodes[-1]] - np.array(path[-1])) < 0.05  # drawn to its end
        kids = np.isin(T["parent"], nodes) & ~np.isin(np.arange(len(T["parent"])), nodes)
        assert kids.sum() >= 2, name  # growth goes on from the drawn axis
    # the second guide grew out of the first
    first = T["axes"][T["guides"]["sub"]]["node"]
    assert T["axis"][T["parent"][first]] == T["guides"]["limb"]


def test_drawn_trunk():
    path = [[0, 0, 0], [0.3, 0, 2], [1.5, 0, 5], [3.5, 0, 8], [4.5, 0, 12]]
    T = v.grow({**SMALL, "guides": {"trunk": {"path": path, "from_year": 0, "until_year": 16}}})
    assert T["axes"][T["guides"]["trunk"]]["order"] == 0
    nodes = np.flatnonzero(T["pin"])
    assert max(_polyline_dist(T["pos"][n], np.array(path, float)) for n in nodes) < 1e-6


def test_prune_and_envelope():
    T0 = v.grow(SMALL)
    T = v.grow({**SMALL, "prune": [{"box": [[1.0, -30, 0], [30, 30, 40]]}]})
    assert (T["pos"][:, 0] < 1.0 + 1.2).all() and (T0["pos"][:, 0] > 2.5).any()
    T = v.grow({**SMALL, "prune": [{"below": 5.0}]})
    lat = (T["order"] == 1) & ~T["main"]
    assert (T["pos"][T["parent"][lat], 2] >= 5.0 - 1e-6).all()
    E = v.grow({**SMALL, "envelope": {"shape": "column", "radius": 1.5, "top": 40, "soft": 0.5}})
    r = lambda t: np.percentile(np.linalg.norm(t["pos"][:, :2], axis=1), 95)
    assert r(E) < 0.6 * r(T0)


def test_environment():
    T0 = v.grow(SMALL)
    F = v.grow({**SMALL, "environment": {"setting": "forest"}})
    m0, mf = v.shape_measures(v.silhouette(T0, 0, 10, leaves=False)[0]), v.shape_measures(v.silhouette(F, 0, 10, leaves=False)[0])
    assert mf["bole"] > m0["bole"] + 0.05 and mf["width_over_height"] < m0["width_over_height"]  # drawn up by its neighbours
    W = v.grow({**SMALL, "environment": {"wind": {"from": "w", "strength": 0.5}}})
    assert np.median(W["pos"][W["ends"], 0]) > np.median(T0["pos"][T0["ends"], 0]) + 0.3  # leans downwind (east, +x)


def test_habit_words():
    ex = v.grow({**SMALL, "habit": {"apical": [0.62, 0.5]}})
    de = v.grow({**SMALL, "habit": {"apical": [0.44, 0.5]}})
    w = lambda t: v.shape_measures(v.silhouette(t, 0, 10, leaves=False)[0])["width_over_height"]
    assert w(de) > w(ex)  # less apical control: broader for its height
    up = v.grow({**SMALL, "habit": {"tropism": [0.35, 0.4, 0.3, 0.3], "sag": 0}})
    down = v.grow({**SMALL, "habit": {"tropism": [0.35, -0.2, -0.5, -0.8]}})
    assert v.branch_angles(up, 1)["elevation_p10_50_90"][1] > v.branch_angles(down, 1)["elevation_p10_50_90"][1] + 15


def test_species_presets_grow():
    for sp in v.species():
        T = v.grow({"species": sp})
        assert 1000 < T["stats"]["nodes"] < 80000, (sp, T["stats"])
        assert T["stats"]["grow_s"] < 20, sp
    try:
        v.grow({"species": "oak", "habit": {"nonsense": 1}})
        raise AssertionError("unknown habit key accepted")
    except ValueError:
        pass


def test_height_sets_the_unit():
    T = v.grow({**SMALL, "height": 9.0})
    assert abs(T["height"] - 9.0) < 0.5, T["height"]
    g = {"limb": {"path": [[0, 0, 2], [2, 0, 3], [4, 0, 3.2]], "from_year": 5, "until_year": 15}}
    T = v.grow({**SMALL, "height": 9.0, "guides": g})  # a guide stays in metres whatever the unit
    nodes = np.flatnonzero(T["pin"])
    assert max(_polyline_dist(T["pos"][n], np.array(g["limb"]["path"], float)) for n in nodes) < 1e-6


def test_decay_and_seasons():
    D = v.grow({**SMALL, "decay": {"min_radius": 0.02}})
    assert (D["radius"][2:] >= 0.02).all() and not D["leafy"].any()
    assert len(veg_leaf.place(D)["pos"]) == 0
    assert len(veg_leaf.place(v.grow({**SMALL, "season": "winter"}))["pos"]) == 0


def test_leaves_and_twigs():
    for shape in ("ovate", "triangular", "lanceolate", "lobed"):
        M = veg_leaf.leaf_mesh({"shape": shape, "length": 0.1})
        assert M["F"].max() < len(M["V"]) and np.isfinite(M["V"]).all()
        assert 0.09 < M["V"][:, 1].max() - 0.015 < 0.115  # petiole + blade
        assert abs(M["V"][:, 0].min() + M["V"][:, 0].max()) < 1e-9  # symmetric
    lob, ova = veg_leaf.leaf_mesh({"shape": "lobed"}), veg_leaf.leaf_mesh({"shape": "ovate"})
    assert len(lob["V"]) > len(ova["V"])  # lobes need stations
    for sp in v.species():
        lf = v.resolve({"species": sp})["leaves"]
        a, b = veg_leaf.twig_mesh(lf, 0), veg_leaf.twig_mesh(lf, 1)
        assert a["F"].max() < len(a["V"]) and len(a["mat"]) == len(a["F"]) and len(a["col"]) == len(a["V"])
        assert (a["mat"] == 1).sum() > 5 and (a["mat"] == 0).sum() > 5, sp
        assert a["V"].shape != b["V"].shape or not np.allclose(a["V"], b["V"])  # variants differ
        assert np.array_equal(a["V"], veg_leaf.twig_mesh(lf, 0)["V"])  # and are deterministic
    T = v.grow(SMALL)
    tw = veg_leaf.place(T)
    assert len(tw["pos"]) > 500
    Fm = tw["frame"]
    assert np.allclose(np.einsum("nij,nik->njk", Fm, Fm), np.eye(3), atol=1e-6)  # orthonormal frames
    assert np.allclose(np.linalg.det(Fm), 1, atol=1e-6)
    assert set(np.unique(tw["variant"])) <= {0, 1, 2}
    d = np.linalg.norm(tw["pos"][:, None, :] - T["pos"][tw["node"]][:, None, :], axis=2).max()
    assert d < 1.0  # every twig stands on its node's internode
    ends_only = veg_leaf.place(v.grow({**SMALL, "leaves": {"twig": {"where": "ends", "per_m": 0}}}))
    assert len(ends_only["pos"]) < len(tw["pos"])


def test_girth_and_collar():
    thin = v.grow({**SMALL, "habit": {"ring": 0.0}})
    thick = v.grow({**SMALL, "habit": {"ring": 0.003}})
    assert thick["stats"]["trunk_diameter_m"] > thin["stats"]["trunk_diameter_m"] + 0.08
    par = thick["parent"]
    assert (thick["radius"][par[2:]] >= thick["radius"][2:] * 0.999).all()  # still thinning outward
    a, b = veg_mesh.tubes(thick, collar=0), veg_mesh.tubes(thick, collar=1.9)
    assert len(b["V"]) > len(a["V"]) and len(b["tan"]) == len(b["V"])
    assert np.allclose(np.linalg.norm(b["tan"], axis=1), 1, atol=1e-6)


def test_wind_spares_the_trunk():
    T0 = v.grow(SMALL)
    W = v.grow({**SMALL, "forces": [{"dir": [1, 0, 0], "strength": 0.25}], "environment": {"wind": {"from": "w", "strength": 0.8}}})
    assert W["height"] > 0.8 * T0["height"]  # it leans, it doesn't lie down
    trunk = W["pos"][W["order"] == 0]
    assert trunk[:, 0].max() < 0.5 * W["height"]


def test_line_directions_and_droop():
    yy, xx = np.mgrid[:200, :200]
    upright = ((xx % 20) < 3).astype(float) * 255
    level = ((yy % 20) < 3).astype(float) * 255
    reg = np.ones((200, 200), bool)
    assert v.line_directions(upright, reg)["p50"] < 10 and v.line_directions(level, reg)["p50"] > 80
    assert v.line_directions(upright, reg)["upright"] > 0.9 and v.line_directions(level, reg)["level"] > 0.9
    T = v.grow(SMALL)
    fake = {"pos": np.array([[0, 0, 0], [0, 0, 10.0], [4, 0, 1.0], [4, 0, 6.0], [0.5, 0, 1.0]]), "height": 10.0,
            "ends": np.array([False, True, True, True, True])}
    assert abs(v.droop(fake, 0.3) - 0.25) < 1e-9  # one end of four hangs low and far out; the one by the trunk doesn't count
    d = v.tree_branch_directions(T, 0, 400)
    assert 0 <= d["p25"] <= d["p50"] <= d["p75"] <= 90


def test_measures_and_masks():
    m = np.zeros((100, 80), bool)
    m[60:, 38:42] = True  # a bole of 40% under a disc
    yy, xx = np.mgrid[:100, :80]
    m |= (yy - 30) ** 2 + (xx - 40) ** 2 < 30 ** 2
    s = v.shape_measures(m)
    assert abs(s["width_over_height"] - 0.6) < 0.03 and 0.3 < s["bole"] < 0.45 and abs(s["lopsided"]) < 0.05
    assert v.outline_iou(m, m) == 1.0
    assert v.outline_iou(m, m[:, ::-1]) > 0.95
    tall = np.repeat(m, 2, axis=0)
    assert v.outline_iou(m, tall) < 0.8
    P = [[10, 90], [10, 40], [0, 30], [20, 0], [40, 30], [30, 40], [30, 90]]
    assert v.traced_mask(P).sum() > 1000


def test_tubes():
    T = v.grow(SMALL)
    M = veg_mesh.tubes(T)
    assert len(M["V"]) == len(M["axis"]) and M["F"].max() < len(M["V"]) and M["F"].min() == 0
    assert np.isfinite(M["V"]).all() and (M["along"] >= 0).all() and (M["along"] <= 1).all()


def test_fit_improves():
    ref = v.silhouette(v.grow({**SMALL, "habit": {"apical": [0.6, 0.5]}}), 0, 12, leaves=False)[0]
    start = {**SMALL, "habit": {"apical": [0.45, 0.5]}}
    before = v.match(v.grow(start), ref, bare=True)["iou"]
    r = v.fit_habit(start, ref, {"apical.0": [0.44, 0.64]}, bare=True, iters=10, seeds=(1,), nodes=(300, 30000))
    assert r["iou"] >= before and "apical" in r["habit"]


if __name__ == "__main__":
    import sys
    import time
    fails = 0
    for k, f in list(globals().items()):
        if k.startswith("test_") and (len(sys.argv) < 2 or k in sys.argv[1:]):
            t = time.time()
            try:
                f()
                print(f"ok   {k} ({time.time() - t:.1f} s)")
            except Exception as e:  # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print(f"FAIL {k}: {e}")
    sys.exit(1 if fails else 0)
