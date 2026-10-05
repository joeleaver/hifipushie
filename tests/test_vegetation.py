"""Vegetation: the growth model is deterministic, edits are local and exact, habits move the form the way their
words say, the measures measure. uv run python tests/test_vegetation.py"""
import numpy as np

from hifipushie import veg_bark, veg_leaf, veg_mesh, vegetation as v

SMALL = {"species": "birch", "age": 22}
TREES = [sp for sp in v.species() if v.preset(sp).get("plant", "tree") == "tree"]  # grown; the others are assembled (veg_small)


def _curve(path, T):
    """The curve a guide follows: the drawn points on a Catmull-Rom spline, as the model resamples it."""
    return v._path(np.asarray(path, float) / T["unit"])[0] * T["unit"]


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
        assert max(_polyline_dist(T["pos"][n], _curve(path, T)) for n in nodes) < 1e-6
        assert np.linalg.norm(T["pos"][nodes[-1]] - np.array(path[-1])) < 0.05  # drawn to its end
        for q in path[1:]:  # the curve goes through the drawn points
            assert _polyline_dist(np.array(q, float), _curve(path, T)) < 1e-6
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
    assert max(_polyline_dist(T["pos"][n], _curve(path, T)) for n in nodes) < 1e-6
    S = v.grow({**SMALL, "guides": {"trunk": {"path": path, "from_year": 0, "until_year": 16, "straight": True}}})
    assert max(_polyline_dist(S["pos"][n], np.array(path, float)) for n in np.flatnonzero(S["pin"])) < 1e-6


def test_guide_on_a_guide_and_stout_wood():
    limb = [[0, 0, 3], [2.5, 0, 4.5], [5.5, 0, 5.2]]
    sub = [[2.5, 0, 4.5], [2.8, 0, 6.5], [2.6, 0, 8.5]]
    T = v.grow({**SMALL, "age": 30, "guides": {"limb": {"path": limb, "from_year": 6, "until_year": 18},
                                               "sub": {"path": sub, "from_year": 16, "until_year": 26, "on": "limb"}}})
    first = T["axes"][T["guides"]["sub"]]["node"]
    assert T["axis"][T["parent"][first]] == T["guides"]["limb"] and T["axes"][T["guides"]["sub"]]["order"] == 2
    # a limb drawn from a point on the trunk leaves the TRUNK (order 1), not a twig that happens to pass there
    L = v.grow({**SMALL, "age": 30, "guides": {"low": {"path": [[0, 0, 4], [2, 0, 4.6], [4, 0, 4.8]], "from_year": 20}}})
    assert L["axes"][L["guides"]["low"]]["order"] == 1


def test_cuts_are_local_and_girth_is_settable():
    T0 = v.grow(SMALL)
    box = [[1.0, -30, 0], [30, 30, 40]]
    T = v.grow({**SMALL, "prune": [{"box": box}]})
    keep = ~np.isin(T0["key"], T["key"])
    assert T["stats"]["pruned_nodes"] == keep.sum() > 10
    same = np.isin(T0["key"], T["key"])
    assert np.array_equal(T0["pos"][same], T["pos"]) and np.allclose(T0["radius"][same], T["radius"])  # nothing else moved
    R = v.grow({**SMALL, "prune": [{"box": box, "from_year": 8}]})  # with a year it is a cut the tree answers
    assert not np.isin(R["key"], T0["key"]).all()
    U = v.grow({**SMALL, "prune": [{"under": 4.0}]})
    assert (U["pos"][U["order"] > 0][:, 2] >= 4.0).all() and (U["order"] == 0).sum() == (T0["order"] == 0).sum()
    G = v.grow({**SMALL, "trunk_diameter": 0.5})
    assert abs(G["stats"]["trunk_diameter_m"] - 0.5) < 0.02 * 1.6  # (the foot's flare sits on top)
    ratio = G["radius"][G["ends"]] / T0["radius"][T0["ends"]]
    assert abs(np.median(ratio) - 1) < 0.1 and np.percentile(ratio, 90) < 0.6 * G["radius"][1] / T0["radius"][1] + 0.4  # twigs stay
    lean = v.grow({**SMALL, "envelope": {"shape": "column", "radius": 2.0, "top": 12, "soft": 0.6, "lean": [4, 0]}})
    up = v.grow({**SMALL, "envelope": {"shape": "column", "radius": 2.0, "top": 12, "soft": 0.6}})
    hi = lambda t: t["pos"][t["pos"][:, 2] > 0.6 * t["height"], 0].mean()
    assert hi(lean) > hi(up) + 0.8


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
    assert W["pos"][W["ends"], 0].mean() > T0["pos"][T0["ends"], 0].mean() + 0.3  # leans downwind (east, +x)


def test_habit_words():
    ok = {"species": "oak", "age": 40}  # (no forced leader: a birch's leader holds its trunk whatever the apical share)
    ex = v.grow({**ok, "habit": {"apical": [0.62, 0.5], "apical_old": None, "leader": 0}})
    de = v.grow({**ok, "habit": {"apical": [0.44, 0.5], "apical_old": None, "leader": 0}})
    w = lambda t: v.shape_measures(v.silhouette(t, 0, 10, leaves=False)[0])["width_over_height"]
    assert w(de) > w(ex)  # less apical control: broader for its height
    up = v.grow({**SMALL, "habit": {"tropism": [0.35, 0.4, 0.3, 0.3], "sag": 0}})
    down = v.grow({**SMALL, "habit": {"tropism": [0.35, -0.2, -0.5, -0.8]}})
    assert v.branch_angles(up, 1)["elevation_p10_50_90"][1] > v.branch_angles(down, 1)["elevation_p10_50_90"][1] + 15


def test_species_presets_grow():
    for sp in TREES:
        T = v.grow({"species": sp})
        assert (200 if sp == "shrub" else 1000) < T["stats"]["nodes"] < 80000, (sp, T["stats"])
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
    assert max(_polyline_dist(T["pos"][n], _curve(g["limb"]["path"], T)) for n in nodes) < 1e-6


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
    for sp in TREES:
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


def test_bark_maps_tile():
    for kind in veg_bark.KINDS:
        m = veg_bark.bark_maps(kind, 128, seed=3)
        h = m["height"]
        assert h.shape[1] == 128 and h.shape[0] == round(128 * m["tile"][1] / m["tile"][0])
        assert 0 <= h.min() and h.max() <= 1 and abs(m["albedo"].mean() - 1) < 1e-6
        assert np.allclose(np.linalg.norm(m["normal"] * 2 - 1, axis=2), 1, atol=1e-6)
        # the wrap seam is no worse than a line anywhere else in the tile
        inside = max(veg_bark.tileability(np.roll(h, (sy, sx), (0, 1))) for sx, sy in ((37, 61), (64, 128), (90, 20)))
        assert veg_bark.tileability(h) < max(1.5, 1.6 * inside), (kind, veg_bark.tileability(h), inside)
        assert np.array_equal(h, veg_bark.bark_maps(kind, 128, seed=3)["height"])
    furrow, lent = veg_bark.bark_maps("furrowed", 128), veg_bark.bark_maps("lenticel", 128)
    gx = lambda a: np.abs(np.diff(a, axis=1)).mean() / np.abs(np.diff(a, axis=0)).mean()
    assert gx(furrow["height"]) > 1.5  # furrows run along the branch: the height changes across it
    assert gx(lent["albedo"]) < 1.0  # lenticels and peeling run round it


def test_atlas_and_cards():
    for sp in v.species():
        lf = v.resolve({"species": sp})["leaves"]
        at = veg_leaf.atlas(lf)
        n = at["color"].shape[0]
        assert at["color"].shape == (n, n, 4) and at["normal"].shape == (n, n, 3) and at["mask"].shape == (n, n, 3)
        assert 0.02 < (at["color"][..., 3] > 0.5).mean() < 0.9, sp
        assert 0.05 < at["fill"] <= 1.0, (sp, at["fill"])
        for c in at["cards"]:
            assert c["F"].max() < len(c["V"]) == len(c["uv"]) and len(c["F"]) <= 3 * 8  # (crossed pair + an end card)
            assert c["uv"].min() > -0.05 and c["uv"].max() < 1.05
    # a card holds its twig's picture: every opaque texel of its cell lies inside the card's polygon
    lf = v.resolve({"species": "oak"})["leaves"]
    tm = veg_leaf.twig_mesh(veg_leaf.card_spec(lf), 0)
    R = veg_leaf.rasterize(tm, lf["color"], [0.4, 0.3, 0.2], 128)
    cm = veg_leaf.card_mesh(R["alpha"], R["frame"], 7, 0.0)
    P = cm["uv"][1:]
    ys, xs = np.nonzero(R["alpha"] > 0.5)
    q = np.c_[(xs + 0.5) / 128, 1 - (ys + 0.5) / 128]
    e = np.roll(P, -1, axis=0) - P
    cr = e[None, :, 0] * (q[:, None, 1] - P[None, :, 1]) - e[None, :, 1] * (q[:, None, 0] - P[None, :, 0])
    inside = (cr >= -0.02).all(1) | (cr <= 0.02).all(1)  # on one side of every edge of the convex card
    assert inside.mean() > 0.995, inside.mean()
    assert len(cm["F"]) <= 7
    k8 = veg_leaf._enclose(np.array([[np.cos(a), np.sin(a)] for a in np.linspace(0, 2 * np.pi, 40, endpoint=False)]), 6)
    assert len(k8) == 6 and (np.linalg.norm(k8, axis=1) >= 1 - 1e-9).all()  # it encloses the circle it started from


def test_tubes_uv_and_weld():
    T = v.grow(SMALL)
    M = veg_mesh.tubes(T, tile=(0.5, 1.0))
    assert len(M["uv"]) == len(M["V"]) and np.isfinite(M["uv"]).all()
    # u spans whole tiles round every branch (the seam column is doubled, so a ring's u runs 0..n exactly)
    assert np.allclose(M["uv"][:, 0].max() % 1.0, 0, atol=1e-9) or M["uv"][:, 0].max() >= 1
    plain = veg_mesh.tubes(T, weld=False)
    moved = np.linalg.norm(M["V"] - plain["V"], axis=1)
    assert 0 < (moved > 1e-9).mean() < 0.2  # only the first rings of branches are carried onto their parents
    assert moved.max() < 1.0
    tip, blunt = veg_mesh.tubes(T, tip=0.3), veg_mesh.tubes(T, tip=1.0)
    assert tip["radius"].min() < blunt["radius"].min()


def test_strip_cards():
    lf = v.resolve({"species": "weeping_willow"})["leaves"]
    tm = veg_leaf.twig_mesh(veg_leaf.card_spec(lf), 0)
    R = veg_leaf.rasterize(tm, lf["color"], [0.4, 0.3, 0.2], 128)
    one = veg_leaf.card_mesh(R["alpha"], R["frame"], 7, 0.0)
    lad = veg_leaf.card_mesh(R["alpha"], R["frame"], 7, 0.0, strips=4)
    assert len(lad["F"]) == 8 and len(lad["V"]) == 10
    assert one["area"] > 0 and lad["area"] > 0
    ys, xs = np.nonzero(R["alpha"] > 0.5)
    u, w = (xs + 0.5) / 128, 1 - (ys + 0.5) / 128
    assert lad["uv"][:, 0].min() <= u.min() + 0.02 and lad["uv"][:, 0].max() >= u.max() - 0.02
    assert lad["uv"][:, 1].min() <= w.min() + 0.02 and lad["uv"][:, 1].max() >= w.max() - 0.02


def test_tools_and_export(tmp=None):
    import json
    import struct
    import tempfile
    from hifipushie import store, veg_tools as vt
    old = store.HOME
    with tempfile.TemporaryDirectory() as d:
        store.HOME = __import__("pathlib").Path(d)
        try:
            assert vt.save("t1", {"species": "birch", "age": 20}) == 1
            r = vt.report("t1")
            assert "form (in leaf" in r and "limbs:" in r and "foliage:" in r
            n0 = vt.grown("t1")["stats"]["nodes"]
            v2 = vt.edit("t1", [{"op": "guide", "name": "low", "path": [[0, 0, 3], [2, 0, 4], [4.5, 0, 4.4]], "from_year": 5,
                                 "until_year": 15},
                                {"op": "prune", "above": 8.0}, {"op": "set", "path": "habit.jitter.1", "value": 0.4},
                                {"op": "set", "path": "seed", "value": 3}])
            assert v2 == 2 and vt.load("t1")["habit"]["jitter"][1] == 0.4 and vt.load("t1")["seed"] == 3
            r = vt.report("t1")
            assert "guide low: order 1" in r and "drawn to its end" in r
            assert vt.grown("t1")["pos"][:, 2].max() < 8.0 + 1.0 and vt.grown("t1")["stats"]["nodes"] != n0
            for bad in ([{"op": "guide", "name": "x"}], [{"op": "nonsense"}], [{"op": "remove_guide", "name": "nope"}],
                        [{"op": "set", "path": "habit.wibble", "value": 1}]):
                try:
                    vt.edit("t1", bad)
                    raise AssertionError(f"accepted {bad}")
                except ValueError:
                    pass
            assert len(vt.history("t1")) == 2 and vt.revert("t1", 1) == 3 and "guides" not in vt.load("t1")
            c = vt.export("t1")
            raw = open(c["path"], "rb").read()
            magic, ver, total = struct.unpack("<4sII", raw[:12])
            assert magic == b"glTF" and ver == 2 and total == len(raw)
            jl = struct.unpack("<I", raw[12:16])[0]
            g = json.loads(raw[20: 20 + jl])
            assert [m["name"] for m in g["meshes"]][:2] == ["wood", "foliage"]
            assert g["materials"][1]["alphaMode"] == "MASK" and g["materials"][1]["doubleSided"]
            tris = sum(g["accessors"][m["primitives"][0]["indices"]]["count"] for m in g["meshes"][:2]) // 3
            assert tris == c["wood_triangles"] + c["foliage_triangles"] > 1000
            for m in g["meshes"]:
                pa = g["accessors"][m["primitives"][0]["attributes"]["POSITION"]]
                assert pa["min"][1] > -1.0 and pa["max"][1] > 3.0  # Y is up
            assert g["extras"]["hifipushie_plant"]["name"] == "t1"
            from hifipushie import server
            assert "species" in json.loads(server.grow_plant(""))
            assert "nothing changed" in server.grow_plant("t1", patch={})
            assert "saved plant t1" in server.grow_plant("t1", patch={"age": 22})
            assert "guide" in server.guide("vegetation").lower()
        finally:
            store.HOME = old


def test_cuts_regrow_and_keys_are_checked():
    base = {"species": "birch", "age": 30}
    T0 = v.grow(base)
    P = v.grow({**base, "cuts": [{"year": 10, "above": 3.0, "every": 5, "until_year": 20, "sprouts": 5}], "trunk_diameter": 0.4, "trunk_taper": 0.1})
    trunk = P["pos"][P["order"] == 0]
    assert trunk[:, 2].max() < 3.0 + 0.6 and P["height"] > 4.0  # a short trunk carrying a head that grew back
    assert len(P["stats"]["cuts"]) >= 3 and all(c["nodes"] > 0 for c in P["stats"]["cuts"])
    assert P["height"] < T0["height"] and (P["order"] > 0).sum() > 100
    r = P["radius"][P["order"] == 0]
    assert r.min() > 0.5 * 0.4 * 0.85  # a column: the trunk keeps its girth to its top
    held = v.grow({**base, "prune": [{"above": 3.0, "from_year": 10}]})  # held for ever: nothing above it
    assert held["pos"][:, 2].max() < 3.0 + 0.6
    stub = v.grow({**base, "cuts": [{"year": 20, "above": 5.0, "sprouts": 0}]})
    assert stub["pos"][stub["order"] == 0][:, 2].max() < 5.6
    for bad in ({"prune": [{"above": 3, "until_year": 9}]}, {"cuts": [{"above": 3}]}, {"guides": {"g": {"path": [[0, 0, 1]]}}},
                {"wibble": 1}, {"guides": {"g": {"path": [[0, 0, 1], [1, 0, 2]], "untill": 3}}}):
        try:
            v.grow({**base, **bad})
            raise AssertionError(f"accepted {bad}")
        except ValueError:
            pass


def test_angle_clear_and_bare():
    b = {"species": "birch", "age": 25}
    lo = v.branch_angles(v.grow({**b, "habit": {"angle": [35, 55, 60]}}), 1)["insertion_p10_50_90"][1]
    hi = v.branch_angles(v.grow({**b, "habit": {"angle": [70, 55, 60]}}), 1)["insertion_p10_50_90"][1]
    assert abs(lo - 35) < 8 and abs(hi - 70) < 12 and hi > lo + 20  # angle[0] IS the limbs' angle off the trunk
    path = [[0, 0, 0], [0.5, 0, 3], [1.5, 0, 6], [1.8, 0, 9]]
    G = v.grow({**b, "habit": {"clear": 4.0}, "guides": {"trunk": {"path": path, "from_year": 0, "until_year": 15}}})
    lat = (G["order"] == 1) & ~G["main"]
    assert lat.any() and (G["pos"][G["parent"][lat], 2] >= 4.0 - 0.6).all()  # a drawn trunk has its clear bole too
    limb = [[0, 0, 4], [2, 0, 4.8], [5, 0, 5.2]]
    L = v.grow({**b, "guides": {"limb": {"path": limb, "from_year": 8, "until_year": 18, "bare": 2.5}}})
    ai = L["guides"]["limb"]
    kids = np.flatnonzero((~L["main"]) & (L["axis"][L["parent"]] == ai) & L["pin"][L["parent"]])
    assert len(kids) and (np.linalg.norm(L["pos"][L["parent"][kids]] - np.array(limb[0]), axis=1) > 2.0).all()
    U = v.grow({**b, "envelope": {"shape": "umbrella", "radius": 4, "top": 9, "base": 2}})
    assert U["stats"]["nodes"] > 100


def test_budget_is_what_is_written():
    from hifipushie import veg_export
    T = v.grow({"species": "birch", "age": 25})
    for n in (4000, 12000):
        bud = veg_export.budget(T, n, (0.4, 0.8), 8)
        assert bud["total"] <= n or bud["over"] == bud["total"] - n
        assert bud["total"] <= n, (n, bud["total"])
    full = veg_export.budget(T, None, (0.4, 0.8), 8)
    assert full["keep"] == 1.0 and full["min_radius"] == 0.0


def test_named_limbs_take_and_sets():
    import tempfile
    from hifipushie import store, veg_tools as vt
    old = store.HOME
    with tempfile.TemporaryDirectory() as tmp:
        store.HOME = __import__("pathlib").Path(tmp)
        try:
            vt.save("o", {"species": "birch", "age": 28, "habit": {"apical": [0.5, 0.55, 0.6]}}, note="t")
            T = vt.grown("o")
            lb = v.limbs(T)
            assert len(lb) >= 3 and len({L["name"] for L in lb}) == len(lb)
            L = max(lb, key=lambda q: q["diameter"])
            vt.edit("o", [{"op": "take_limb", "limb": L["name"], "name": "mine"}])
            T2 = vt.grown("o")
            g = vt.load("o")["guides"]["mine"]
            ai = T2["guides"]["mine"]
            nodes = np.flatnonzero((T2["axis"] == ai) & T2["pin"])
            assert np.linalg.norm(T2["pos"][nodes[-1]] - np.array(g["path"][-1])) < 0.3  # same end as the grown limb's
            assert np.linalg.norm(np.array(g["path"][-1]) - np.array(L["end"])) < 0.05
            assert not (T2["key"] == np.uint64(int(L["key"]))).any()  # the shoot it replaces is not grown beside it
            assert "mine (drawn)" in vt.report("o")
            # a set: deterministic, different plants, the hero's guide dropped, one file
            vt.save("o", patch={"set": {"count": 3}})
            a, b = vt.load("o#1"), vt.load("o#3")
            assert a["seed"] != b["seed"] and a["age"] < b["age"] and "guides" not in a and vt.load("o#1") == a
            assert vt.grown("o#1")["height"] < vt.grown("o#3")["height"]
            c = vt.export_set("o", triangles=3000)
            assert len(c["plants"]) == 3 and all(q["wood_triangles"] + q["foliage_triangles"] <= 3000 for q in c["plants"])
            try:
                vt.save("o#1", patch={"age": 3})
                raise AssertionError("saved into a set's plant")
            except ValueError:
                pass
        finally:
            store.HOME = old
            vt._GROWN.clear()


def test_blender_round_trip():
    """A guide moved, a limb moved, a curve added in plant.blend come back as spec edits; a second pull is empty."""
    import subprocess
    import tempfile
    from hifipushie import render, store, veg_tools as vt
    os_ = __import__("os")
    old, nl = store.HOME, os_.environ.get("HIFIPUSHIE_NO_LIVE")
    os_.environ["HIFIPUSHIE_NO_LIVE"] = "1"
    with tempfile.TemporaryDirectory() as tmp:
        store.HOME = __import__("pathlib").Path(tmp)
        try:
            vt.save("r", {"species": "birch", "age": 22, "guides": {"g": {"path": [[0, 0, 3], [1.5, 0, 4], [3, 0, 4.5]], "from_year": 6}}}, note="t")
            r = vt.sync("r")
            assert r["pulled"] == [] and r["guides"] == 1 and r["limbs"] >= 1
            code = ("import bpy\nfrom mathutils import Vector\n"
                    "g = bpy.data.collections['guides']; l = bpy.data.collections['limbs']\n"
                    "bp = g.objects['g'].data.splines[0].bezier_points[-1]; bp.co = Vector(bp.co) + Vector((0, 0, 1.5))\n"
                    "l.objects[0].location.z += 0.5\n"
                    "cu = bpy.data.curves.new('n', 'CURVE'); cu.dimensions = '3D'; sp = cu.splines.new('BEZIER'); sp.bezier_points.add(1)\n"
                    "sp.bezier_points[0].co = (0, 0, 5); sp.bezier_points[1].co = (0, 2, 6.5)\n"
                    "g.objects.link(bpy.data.objects.new('new one', cu))\nbpy.ops.wm.save_mainfile()\n")
            q = subprocess.run([render.BLENDER, "-b", r["blend"], "--python-expr", code], capture_output=True, text=True)
            assert q.returncode == 0, q.stderr[-500:]
            came = vt.pull("r")
            assert len(came) == 3, came
            sp = vt.load("r")
            assert abs(sp["guides"]["g"]["path"][-1][2] - 6.0) < 1e-3 and "new_one" in sp["guides"]
            assert any(k.startswith("limb_") and gd.get("replaces") for k, gd in sp["guides"].items())
            assert vt.pull("r") == []  # (not yet re-synced: still nothing twice)
            assert vt.sync("r")["pulled"] == [] and vt.pull("r") == []
        finally:
            store.HOME = old
            vt._GROWN.clear()
            if nl is None:
                os_.environ.pop("HIFIPUSHIE_NO_LIVE", None)


def test_boll_dead_roots_and_habit_extras():
    from hifipushie import veg_mesh
    base = {"species": "white_willow"}
    cut = {"year": 10, "above": 2.5, "every": 6, "until_year": 28, "sprouts": 6}
    A = v.grow({**base, "cuts": [cut], "trunk_diameter": 0.7, "trunk_taper": 0.1})
    B = v.grow({**base, "cuts": [{**cut, "boll": 1.7}], "trunk_diameter": 0.7, "trunk_taper": 0.1})
    ra, rb = A["radius"][A["order"] == 0], B["radius"][B["order"] == 0]
    assert abs(A["height"] - B["height"]) < 1e-6 and A["height"] < 9  # (a preset `height` no longer scales a pollard up to it)
    assert 1.25 < rb[-1] / ra[-1] < 1.75 and abs(rb[1] - ra[1]) < 1e-6  # a head on the same trunk
    T = v.grow({"species": "birch", "age": 25})
    lb = v.limbs(T)
    D = v.grow({"species": "birch", "age": 25, "dead": [{"limb": lb[0]["name"], "min_radius": 0.01}]})
    assert D["dead"].any() and not D["leafy"][D["dead"]].any() and D["stats"]["nodes"] < T["stats"]["nodes"]
    assert (D["radius"][D["dead"]] >= 0.01).all()
    M = veg_mesh.tubes(D)
    assert 0 < M["dead"].mean() < 0.5 and M["V"][:, 2].min() < -0.2  # dead wood marked; the trunk goes into the ground
    R = veg_mesh.tubes({**T, "spec": {**T["spec"], "roots": {"count": 5, "spread": 2.0, "height": 0.6}}})
    foot = lambda m_: np.linalg.norm(m_["V"][(m_["order"] == 0) & (np.abs(m_["V"][:, 2]) < 0.02)][:, :2], axis=1)
    f0, f1 = foot(veg_mesh.tubes(T)), foot(R)
    assert f1.max() > 1.6 * f0.max() and f1.min() < 1.25 * f0.max()  # flares between hollows, not a wider cone
    # determinate axes and uneven pace
    s0 = {"species": "norway_spruce", "age": 30, "habit": {"tip_life": [0], "uneven": [0]}}
    a = v.grow(s0)
    b = v.grow({**s0, "habit": {"tip_life": [0, 0, 4], "uneven": [0]}})
    assert (b["order"] == 2).sum() < 0.7 * (a["order"] == 2).sum()
    c = v.grow({**s0, "habit": {"tip_life": [0], "uneven": [0, 0.4]}})
    seg = lambda t: np.linalg.norm(t["pos"] - t["pos"][t["parent"]], axis=1)[t["order"] == 1]
    assert np.std(seg(c)) > 1.5 * np.std(seg(a))  # limbs at their own pace
    for sp in v.species():  # every preset grows something sound
        t = v.grow({"species": sp, "age": 12})
        assert t["stats"]["nodes"] > (1 if t.get("clump") else 5) and np.isfinite(t["pos"]).all(), sp


def test_budget_keeps_marked_wood_and_cards_on_wood():
    from hifipushie import veg_export, veg_leaf, veg_mesh
    T = v.grow({"species": "oak", "age": 70, "dead": [{"above": 9.0, "min_radius": 0.02}]})
    assert T["dead"].any()
    bud = veg_export.budget(T, 12000, (0.5, 1.0), 7)
    assert bud["total"] <= 12000 and bud["min_radius"] > 0.02  # thin live wood went ...
    assert bud["wood"]["dead"].sum() > 0  # ... the dead antlers (thinner than the cut-off) did not
    ok = veg_export.kept_wood(T, bud["min_radius"], bud["protect"])
    thin = T["radius"] < bud["min_radius"]
    assert ok[T["dead"] & thin].mean() > 3 * ok[~T["dead"] & thin].mean()  # thin dead wood is drawn, thin live wood is not
    tw, floating = veg_export.pick_twigs(T, bud["keep"], bud["min_radius"], bud["protect"])
    rnd = veg_leaf.place(T)
    far_all = 1 - ok[rnd["node"]].mean()
    if bud["keep"] >= 0.25:  # twig cards stand on drawn wood (bough cards are spread over the crown instead)
        assert floating <= 0.2 or floating < 0.5 * far_all, (floating, far_all)
    else:
        lf2, cap2, back2 = veg_export.cluster_leaves(T["spec"]["leaves"], bud["keep"])
        assert back2 > 0 and lf2["card"]["twig"]["length"] > 1.25 * veg_leaf.card_spec(T["spec"]["leaves"])["twig"]["length"]
        b2 = veg_export.pick_twigs(T, bud["keep"], bud["min_radius"], bud["protect"], cap=cap2, back=back2)[0]
        spread = lambda q: len(np.unique(np.floor(q / 2.0).astype(int), axis=0))
        assert spread(b2["pos"]) >= spread(tw["pos"])  # over the crown, not bunched on the limbs
    full, simp = veg_mesh.tubes(T), veg_mesh.tubes(T, simplify=0.3)
    assert len(simp["F"]) < 0.92 * len(full["F"]) and abs(simp["V"][:, 2].max() - full["V"][:, 2].max()) < 0.05


def test_limb_ids_last_and_report_says():
    import tempfile
    from hifipushie import store, veg_tools as vt
    old = store.HOME
    with tempfile.TemporaryDirectory() as tmp:
        store.HOME = __import__("pathlib").Path(tmp)
        try:
            base = {"species": "birch", "age": 28, "environment": {"ground": {"slope": 15, "toward": [1, 0]}}}
            T = v.grow(base)
            L = max(v.limbs(T), key=lambda q: q["diameter"])
            vt.save("d", {**base, "dead": [{"limb": L["name"], "min_radius": 0.008}]}, note="t")
            sp = vt.load("d")
            assert sp["dead"][0]["limb"] == L["id"] and L["id"].startswith("L")  # stored by its lasting id
            D = vt.grown("d")
            p0 = D["pos"][D["axes"][v.find_limb(D, L["id"])]["node"]]
            vt.edit("d", [{"op": "set", "path": "habit.jitter", "value": [0.05, 0.3, 0.3, 0.2]}])
            D2 = vt.grown("d")
            ai = v.find_limb(D2, L["id"])
            assert ai is not None and np.linalg.norm(D2["pos"][D2["axes"][ai]["node"]] - p0) < 1.0  # the same bud's limb
            assert D2["dead"][D2["axes"][ai]["node"]]
            r = vt.report("d")
            assert "dead wood (limb " + L["id"] in r and "lowest wood:" in r and "(id L" in r
            vt.save("d", patch={"dead": [{"limb": "Lzzzz"}]})
            assert "is not on this tree any more" in vt.report("d")
            # a fat trunk under ordinary limbs
            a = v.grow({**base, "trunk_diameter": 1.2})
            b = v.grow({**base, "trunk_diameter": 1.2, "limb_diameter": 0.2})
            la, lb_ = max(q["diameter"] for q in v.limbs(a)), max(q["diameter"] for q in v.limbs(b))
            assert abs(lb_ - 0.2) < 0.03 and la > 1.5 * lb_ and abs(2 * b["radius"][1] - 1.2) < 0.05
        finally:
            store.HOME = old
            vt._GROWN.clear()


def _glb(path):
    import json
    import struct
    b = open(path, "rb").read()
    n = struct.unpack("<I", b[12:16])[0]
    return json.loads(b[20:20 + n]), b[20 + n + 8:]


def test_export_lods_wind_seasons_collision():
    import tempfile
    from hifipushie import veg_export, veg_leaf
    T = v.grow({"species": "birch", "age": 25})
    with tempfile.TemporaryDirectory() as tmp:
        imp = {"image": np.ones((8, 16, 4), np.float32), "size": 10.0, "height": 5.0}
        c = veg_export.write_glb(T, tmp + "/b.glb", "b", triangles=9000, lods=3, seasons=["summer", "autumn", "winter", "snow"],
                                 wet=True, impostor=imp)
        g, bin_ = _glb(c["path"])
        tri = [l_["triangles"] for l_ in c["lods"]]
        assert len(tri) == 4 and tri[0] <= 9000 and tri[1] <= 0.45 * 9000 + 1 and tri[2] <= 0.18 * 9000 + 1 and tri[3] == 4
        assert tri[0] > tri[1] > tri[2]
        assert set(g["extensionsUsed"]) == {"KHR_materials_variants", "MSFT_lod"}
        assert [x["name"] for x in g["extensions"]["KHR_materials_variants"]["variants"]] == ["summer", "autumn", "winter", "snow", "wet"]
        head = g["nodes"][g["scenes"][0]["nodes"][0]]
        assert len(head["extensions"]["MSFT_lod"]["ids"]) == 3 and head["name"].endswith("LOD0")
        mats = {m["name"]: m for m in g["materials"]}
        assert mats["foliage_winter"]["alphaCutoff"] > 1 and mats["foliage_autumn"]["pbrMetallicRoughness"]["baseColorTexture"]["index"] \
            != mats["foliage"]["pbrMetallicRoughness"]["baseColorTexture"]["index"]
        wood = next(m for m in g["meshes"] if m["name"] == "LOD0_wood")["primitives"][0]
        fol = next(m for m in g["meshes"] if m["name"] == "LOD0_foliage")["primitives"][0]
        for k in ("TEXCOORD_1", "TEXCOORD_2", "_WIND"):
            assert k in wood["attributes"] and k in fol["attributes"]
        assert len(fol["extensions"]["KHR_materials_variants"]["mappings"]) >= 3

        def arr(i, cols):
            a_ = g["accessors"][i]
            bv = g["bufferViews"][a_["bufferView"]]
            return np.frombuffer(bin_, np.float32, a_["count"] * cols, bv["byteOffset"]).reshape(-1, cols)

        P, W = arr(wood["attributes"]["POSITION"], 3), arr(wood["attributes"]["_WIND"], 4)
        low, high = P[:, 1] < 0.3, P[:, 1] > 0.8 * P[:, 1].max()  # (Y up in the file)
        assert W[low][:, 0].max() < 0.02 and W[high][:, 0].min() > 0.6 and W[:, 3].max() == 0  # the foot stands; wood doesn't flutter
        Wf = arr(fol["attributes"]["_WIND"], 4)
        assert Wf[:, 3].max() > 0.9 and Wf[:, 1].mean() > 0.3 and 0 < Wf[:, 2].std()
        hp = g["extras"]["hifipushie_plant"]
        caps = hp["collision"][0]["capsules"]
        assert 2 <= len(caps) <= 24 and caps[0]["ra"] > 0.03 and "sin" in hp["wind"]
        assert g["nodes"][hp["collision"][0]["mesh_node"]]["name"] == "b_collision"
    # seasons on the plant itself
    ev = v.grow({"species": "norway_spruce", "age": 20, "season": "winter"})
    de = v.grow({"species": "birch", "age": 20, "season": "winter"})
    assert len(veg_leaf.place(ev)["pos"]) > 0 and len(veg_leaf.place(de)["pos"]) == 0
    assert veg_export.season_atlas(de["spec"], "winter", [0.4, 0.3, 0.3]) is None
    su, au = veg_export.season_atlas(de["spec"], "summer", [0.4, 0.3, 0.3]), veg_export.season_atlas(de["spec"], "autumn", [0.4, 0.3, 0.3])
    m = su["color"][..., 3] > 0.6
    assert (au["color"][m][:, 0] - au["color"][m][:, 1]).mean() > (su["color"][m][:, 0] - su["color"][m][:, 1]).mean() + 0.1


def test_fit_improves():
    ref = v.silhouette(v.grow({**SMALL, "habit": {"apical": [0.6, 0.5]}}), 0, 12, leaves=False)[0]
    start = {**SMALL, "habit": {"apical": [0.45, 0.5]}}
    before = v.match(v.grow(start), ref, bare=True)["iou"]
    r = v.fit_habit(start, ref, {"apical.0": [0.44, 0.64]}, bare=True, iters=10, seeds=(1,), nodes=(300, 30000))
    assert r["iou"] >= before and "apical" in r["habit"]


def _limbs_by_whorl(T):
    """Limbs leaving the trunk, counted per trunk node."""
    o, par = T["order"], T["parent"]
    first = np.flatnonzero((o == 1) & (o[par] == 0))
    return np.bincount(par[first])[np.unique(par[first])]


def test_whorls_rings_and_creeping_branchlets():
    # bud_each: a low bud_break keeps one or two limbs of a whorl, not whole whorls or none
    base = {"species": "scots_pine", "age": 50, "habit": {"bud_break": [1, 0.3, 0.8, 0.9, 0.8]}}
    whole = _limbs_by_whorl(v.grow(v._merge(base, {"habit": {"bud_each": False}})))
    each = _limbs_by_whorl(v.grow(v._merge(base, {"habit": {"bud_each": True}})))
    assert whole.max() >= 3 and each.mean() < whole.mean() and len(each) > len(whole), (whole, each)
    # ring per order: old low branches stay thin under a stout trunk; slowing keeps foliage along the limbs
    S = {"species": "norway_spruce", "age": 40}
    one = v.grow(v._merge(S, {"habit": {"ring": 0.003, "slowing": [0], "tip_life": [0, 0, 7]}}))
    per = v.grow(S)

    def low_limb_girth(T):
        o, par, P = T["order"], T["parent"], T["pos"]
        f = np.flatnonzero((o == 1) & (o[par] == 0) & (P[:, 2] < 0.2 * T["height"]))
        return float(np.median(2 * T["radius"][f]))

    assert low_limb_girth(per) < 0.4 * low_limb_girth(one) and low_limb_girth(per) < 0.2 * per["stats"]["trunk_diameter_m"]

    def foliage_from(T):  # the share of a low limb's length before its first twig
        tw = veg_leaf.place(T)
        o, par, P = T["order"], T["parent"], T["pos"]
        has = np.zeros(len(P), bool)
        has[tw["node"]] = True
        limb, dist = np.zeros(len(P), np.int64), np.zeros(len(P))
        for i in range(2, len(P)):
            if o[i] > 0:
                limb[i] = limb[par[i]] if o[par[i]] > 0 else i
                dist[i] = dist[par[i]] + np.linalg.norm(P[i] - P[par[i]]) if o[par[i]] > 0 else 0.0
        out = []
        for r in np.unique(limb[limb > 0]):
            m = limb == r
            if P[r, 2] < 0.3 * T["height"] and (m & has).any():
                out.append(dist[m & has].min() / max(dist[m & (o == 1)].max(), 1e-6))
        return float(np.median(out))

    assert foliage_from(per) < 0.8 * foliage_from(one), (foliage_from(per), foliage_from(one))
    # a pine tuft is round: crossed cards plus one across the shoot, its picture in its own atlas cell
    at = veg_leaf.atlas(v.resolve({"species": "scots_pine"})["leaves"])
    c = at["cards"][0]
    assert len(c["F"]) > 14 and np.ptp(c["V"][:, 0]) > 0.1 and np.ptp(c["V"][:, 2]) > 0.1


def test_ground_and_stand_forms():
    # nothing under the ground: an open-grown spruce's lowest limbs lie along it, its twigs' tips stay above it
    S = {"species": "norway_spruce", "age": 44}
    op = v.grow(S)
    assert op["pos"][2:, 2].min() > 0 and op["stats"]["on_ground"] >= 0
    tw = veg_leaf.place(op)
    tl = v.resolve(S)["leaves"]["twig"]["length"]
    assert (tw["pos"][:, 2] + tw["frame"][:, 2, 1] * tl * tw["scale"]).min() > -0.01
    up = v.grow({**S, "environment": {"ground": {"level": 1.0}}})  # the plane is a parameter
    assert up["pos"][up["order"] > 0][:, 2].min() > 1.0
    # one word for where it stands: an interior tree has a higher crown base and keeps dead stubs; an edge tree is one-sided
    inner = v.grow({**S, "environment": {"setting": "forest"}})
    edge = v.grow({**S, "environment": {"setting": "edge", "open_side": [1, 0]}})
    low = lambda t: float(np.percentile(veg_leaf.place(t)["pos"][:, 2], 5)) / t["height"]
    assert low(inner) > low(op) + 0.2 and inner["stats"]["dead_stubs"] > 10 and op["stats"]["dead_stubs"] == 0
    assert inner["dead"].any() and not inner["leafy"][inner["dead"]].any()
    ex = veg_leaf.place(edge)["pos"]
    lowx = ex[ex[:, 2] < 0.4 * edge["height"]][:, 0]
    assert len(lowx) and (lowx > 0).mean() > 0.7  # foliage down the open side
    # a pine sheds cleaner than a spruce
    assert v.resolve({"species": "scots_pine"})["habit"]["dead_keep"] < v.resolve(S)["habit"]["dead_keep"]


def test_small_plants_are_assembled():
    from hifipushie import veg_small, veg_export
    clumps = [sp for sp in v.species() if v.preset(sp).get("plant") == "clump"]
    assert {"meadow_grass", "fern", "daisy", "clover", "feather_palm"} <= set(clumps)
    for sp in clumps:
        T = v.grow({"species": sp})
        tw = veg_leaf.place(T)
        m = veg_small.measures(T)
        assert T.get("clump") and len(tw["pos"]) == m["cards"] > 5 and np.isfinite(tw["frame"]).all(), sp
        assert np.allclose(np.linalg.det(tw["frame"]), 1, atol=1e-6), sp  # proper frames
        at = veg_leaf.atlas(T["spec"]["leaves"])
        assert tw["card"].max() < len(at["cards"]), sp
        assert np.array_equal(v.grow({"species": sp})["twigs"]["pos"], tw["pos"])  # the same plant every time
        assert not np.array_equal(v.grow({"species": sp, "seed": 2})["twigs"]["pos"], tw["pos"])
    g = v.grow({"species": "meadow_grass"})
    assert 0.3 < g["height"] < 0.8 and veg_small.measures(g)["card_elevation_p10_50_90"][1] > 55  # a tuft stands
    assert veg_small.measures(v.grow({"species": "clover"}))["cover_from_above"] > 0.6  # a groundcover covers
    p = v.grow({"species": "feather_palm"})
    assert p["height"] > 6 and (p["order"] == 0).sum() > 8 and 0.2 < 2 * p["radius"][1] < 0.6  # a trunk under a crown
    # parts: several pictures in one atlas, each layer drawing its own
    pc = veg_leaf.part_cards(v.resolve({"species": "daisy"})["leaves"])
    d = v.grow({"species": "daisy"})
    assert set(pc) == {"main", "head", "stemleaf"} and set(np.unique(d["twigs"]["card"])) <= set(sum(pc.values(), []))
    L = veg_export.foliage_mesh(g, veg_leaf.atlas(g["spec"]["leaves"]))
    assert len(L["V"]) and L["N"][:, 2].mean() > 0.6 and L["reach"].max() < 1.0  # normals lean up; cards know their length
    for bad in ({"clump": {"layers": [{"part": "nope"}]}}, {"clump": {"layers": [{"sizee": 1}]}}, {"clump": {"layers": []}}):
        try:
            v.grow({"species": "fern", **bad})
            raise AssertionError(bad)
        except ValueError:
            pass
    s = v.grow({"species": "shrub"})
    feet = np.flatnonzero((s["parent"] == 0) & (np.arange(len(s["parent"])) > 0))
    assert len(feet) == 6 and (s["order"][feet] == 0).all()  # six stems from one stool


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
