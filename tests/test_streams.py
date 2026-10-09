"""Stream beds (terrain_stream; pushieworld note 110: the river's bed was meadow grass with nothing in it): the bed's
zone and layers under the water, the damp bank, the bed's shape only under the water, the clutter's rules, and
nothing at all on a terrain without rivers. A small synthetic meadow with a winding river and a ford.
uv run python tests/test_streams.py"""
import json
import tempfile
import time
from pathlib import Path

import numpy as np

from hifipushie import terrain, terrain_mesh as tm, terrain_stream as ts, terrain_style, terrain_swatch

SPEC = {"world": {"kind": "farmland", "base": 14}, "extent": [[0, 0], [256, 256]], "cell": 1.0,
        "rivers": {"brook": {"source": [20, 236, 13], "through": [[100, 190], [110, 120], [180, 90]],
                             "mouth": [240, 20, 3], "water": 5, "valley": {"profile": "open", "floor": 30}}},
        "fords": {"wade": {"on": "brook@0.5", "width": 6, "depth": 0.3}},
        "cover": [{"type": "meadow", "in": "everywhere"}],
        "export": {"tiles": {"tile": 64}}}


def _load(spec):
    d = Path(tempfile.mkdtemp())
    (d / "spec.json").write_text(json.dumps(spec))
    return terrain.load(d / "spec.json")


def _mats(T):
    base = tm.build_field(T)[0]
    field = getattr(base, "base", base)
    return field, tm.Materials(T, base)


def _channel(T, S, n=4000, seed=1):
    """Random points round the river with their columns."""
    rng = np.random.default_rng(seed)
    xy = np.asarray(T.river_water_lines["brook"]["xy"], float)
    p = xy[rng.integers(10, len(xy) - 10, n)] + rng.normal(0, 4.0, (n, 2))
    return p


def test_zone_and_layers(T, field, mats):
    S = mats.streams
    assert S is not None and S.any and S.names == ["brook"]
    # the stream's layers come last: the older layers keep their channels
    assert mats.layers[-3:] == list(ts.LAYERS) and "wet_rock" in mats.layers, mats.layers
    p = _channel(T, S)
    h, _ = field.column(p[:, 0], p[:, 1])
    P = np.c_[p, h]
    N = np.tile([0.0, 0.0, 1.0], (len(P), 1))
    W, c = mats.weights(P, N)
    g = S.sample(p)
    dep = g["level"] - h
    lw = lambda *nm: sum(W[:, mats.layers.index(k)] for k in nm)
    deep = (dep > 0.25) & (g["sd"] < -0.5)
    assert deep.sum() > 200
    bed = lw("gravel", "silt", "wet_rock", "rock")
    assert np.percentile(bed[deep], 5) > 0.9, np.percentile(bed[deep], 5)  # under the water: the bed, not meadow
    assert lw("grass")[deep].max() < 0.1
    dry = (dep < -1.2) | (g["sd"] > 8)
    assert lw("gravel", "silt", "bank")[dry].max() < 0.02  # away from the water: nothing of it
    # the damp bank: just above the water beside the channel
    foot = (dep < -0.05) & (dep > -0.2) & (g["sd"] < 1.5)
    assert foot.sum() > 20 and np.median(lw("bank")[foot]) > 0.4, (foot.sum(), np.median(lw("bank")[foot]))
    # shares sum to one, and the bed is darker than dry gravel but not black
    st = S.shares(P)
    assert np.allclose(st["gravel"] + st["silt"] + st["rock"], 1, atol=1e-6)
    lum = c @ np.array([0.3, 0.59, 0.11])
    assert 0.12 < np.median(lum[deep]) < 0.45, np.median(lum[deep])
    # pointwise: the same values whatever else is in the call (tiles and LODs agree)
    W2, c2 = mats.weights(P[:500], N[:500])
    assert np.array_equal(W2, W[:500]) and np.array_equal(c2, c[:500])
    return S


def test_bed_shape_only_under_water(T, field, mats):
    S = mats.streams
    p = _channel(T, S, 6000, 2)
    x, y = np.ascontiguousarray(p[:, 0]), np.ascontiguousarray(p[:, 1])
    h0, _ = field._column(x, y)  # the grid's own ground
    ed = field.edits
    h1 = h0 + ed.dz(x, y)  # (lips and bunkers: none here)
    dz = S.dz(x, y, h1)
    g = S.sample(p)
    dep0 = g["level"] - h1
    assert np.abs(dz).max() > 0.2, "no pools or riffles were shaped"
    # the banks: only their foot moves (a cut bank on the outer side, the bar's flat on the inner), only down, and
    # ground higher than the tallest cut keeps its height
    hb = -dep0
    assert np.all(dz[hb > 1.4] == 0), "ground above the banks' foot moved"
    assert dz[hb > 0].max() <= 1e-9, "a bank rose"
    outer, hc, inner, sdc = S.cut(p, g)
    cutb = (outer > 0.9) & (hb > 0.05) & (hb < hc - 0.35) & (g["sd"] < sdc - 1.0)
    assert cutb.sum() > 5 and np.all((h1 + dz)[cutb] < g["level"][cutb]), "no cut bank: the outer ramp still stands"
    rp = S.cfg["cut_riser"]
    keepb = (outer > 0.9) & ((hb > hc + 0.33 * rp + 0.02) | (g["sd"] > sdc + rp + 0.05))
    assert keepb.sum() > 5 and np.abs(dz[keepb]).max() < 1e-9, ("the turf above a cut bank moved", keepb.sum(), np.abs(dz[keepb]).max() if keepb.any() else 0, float(outer.max()), float(hb.max()))
    # the water never ends above ground it stood over, except on a bar's top (a few cm)
    new = h1 + dz
    wet = dep0 > 0.4
    over = new[wet] - g["level"][wet]
    assert over.max() <= S.cfg["bar"] + 1e-6, over.max()
    pool, riffle, bar = S.forms(p, g)
    nob = wet & (bar < 0.01)
    assert np.all(g["level"][nob] - new[nob] >= S.cfg["min_depth"] - 1e-6)
    # pools are deeper than riffles
    dp, dr = (g["level"] - new)[wet & (pool > 0.8)], (g["level"] - new)[wet & (riffle > 0.8)]
    assert len(dp) > 20 and len(dr) > 20 and np.median(dp) > np.median(dr) + 0.15, (np.median(dp), np.median(dr))
    # the ford keeps its ground
    f = g["ford"] > 0.9
    assert f.any() and np.abs(dz[f]).max() < 0.05
    # Field.column carries it (heightmaps, cliff meshes, collision, the bakes)
    hc, _ = field.column(x, y)
    assert np.allclose(hc, new)


def test_clutter_rules(T, field, mats):
    S = mats.streams
    C = ts.clutter(T, mats, field)
    assert np.array_equal(C, ts.clutter(T, mats, field)), "not deterministic"
    kinds = list(ts.KINDS)
    n = {k: int((C[:, 3] == i).sum()) for i, k in enumerate(kinds)}
    assert n["river_rock"] > 5 and n["cobbles"] > 20 and n["driftwood"] >= 1, n
    # a block of the level holds the same rows as the whole level does there
    box = [[64.0, 64.0], [192.0, 192.0]]
    Cb = ts.clutter(T, mats, field, box=box)
    ins = (C[:, 0] >= 64) & (C[:, 0] < 192) & (C[:, 1] >= 64) & (C[:, 1] < 192)
    grid_kinds = np.isin(C[:, 3], [kinds.index(k) for k in ("cobbles", "reeds", "litter")])  # (no thinning, no logs
    # caught on rocks: those look at neighbours across the box's edge)
    a = C[ins & grid_kinds]
    b = Cb[np.isin(Cb[:, 3], [kinds.index(k) for k in ("cobbles", "reeds", "litter")])]
    assert len(a) == len(b) and np.allclose(np.sort(a[:, 0]), np.sort(b[:, 0]))
    # sizes inside each kind's stated range, places valid, nothing at the ford
    for i, k in enumerate(kinds):
        r = C[C[:, 3] == i]
        if len(r):
            lo, hi = ts.KINDS[k]["scale"]
            assert r[:, 4].min() >= lo - 1e-6 and r[:, 4].max() <= hi + 1e-6, (k, r[:, 4].min(), r[:, 4].max())
            assert set(np.unique(r[:, 7]).astype(int)) <= {1, 2, 3, 4}
    fx, fy = T.fords["wade"]["xy"]
    assert not (np.hypot(C[:, 0] - fx, C[:, 1] - fy) < 5.0).any()
    # rocks don't stand inside each other, and aren't a comb: spacing varies
    rk = C[C[:, 3] == kinds.index("river_rock")]
    from scipy.spatial import cKDTree
    d, j = cKDTree(rk[:, :2]).query(rk[:, :2], k=2)
    assert np.all(d[:, 1] > 0.4 * (rk[:, 4] + rk[j[:, 1], 4]) - 1e-6)
    assert np.std(d[:, 1]) / np.mean(d[:, 1]) > 0.35, "evenly spaced rocks"
    assert np.std(rk[:, 4]) / np.mean(rk[:, 4]) > 0.2, "same-sized rocks"
    # in the water means under it; reeds stand at the water line
    g = S.sample(rk[:, :2])
    inw = rk[:, 7] == 1
    assert np.all((g["level"] - rk[:, 2])[inw] > 0)
    lines = ts.summary(S, C)
    assert any("brook" in ln and "river_rock" in ln for ln in lines), lines
    return n


def test_energy_sets_the_character(T, n_calm):
    spec = json.loads(json.dumps(T.source if hasattr(T, "source") else T.spec))
    spec["rivers"]["brook"]["bed"] = {"energy": 0.9}
    T.spec["rivers"]["brook"]["bed"] = {"energy": 0.9}
    try:
        field, mats = _mats(T)
        C = ts.clutter(T, mats, field)
        kinds = list(ts.KINDS)
        rocks = int((C[:, 3] == kinds.index("river_rock")).sum())
        reeds = int((C[:, 3] == kinds.index("reeds")).sum())
        assert rocks > 2.5 * n_calm["river_rock"], (rocks, n_calm)  # a torrent: boulders
        assert reeds == 0 and n_calm["reeds"] > 0, (reeds, n_calm)
        assert any("cascade" in ln for ln in mats.streams.report())
    finally:
        del T.spec["rivers"]["brook"]["bed"]


def test_off_and_no_rivers(T):
    T.spec["streams"] = False
    try:
        field, mats = _mats(T)
        assert field.streams is None and mats.streams is None and "gravel" not in mats.layers
        off_layers = list(mats.layers)
    finally:
        del T.spec["streams"]
    spec = {k: v for k, v in SPEC.items() if k not in ("rivers", "fords")}
    spec["peaks"] = {"knoll": {"at": [128, 128], "h": 30}}
    T2 = _load(spec)
    field, mats = _mats(T2)
    assert field.streams is None and field.edits.streams is None and mats.streams is None
    assert mats.layers == off_layers, (mats.layers, off_layers)


SHORE = {"world": {"kind": "coast", "base": 7}, "extent": [[0, 0], [256, 256]], "cell": 1.0,
         "tilt": {"down": "south", "grade": 0.1},
         "sea": {"level": 0, "shore": "beach"},
         "landforms": {"pond": {"type": "lake", "at": [128, 190], "radius": 18, "depth": 1.5}},
         "cover": [{"type": "meadow", "in": "everywhere"}, {"type": "sand", "in": "beach"}],
         "export": {"tiles": {"tile": 64}}}


def test_lake_shore_and_beach():
    """Lakes get a shore (bed, damp foot, margin clutter) with no bed shape; sea beaches get pebbles, a wrack line and
    driftwood where the maps paint sand above the water."""
    T = _load(SHORE)
    field, mats = _mats(T)
    S = mats.streams
    assert S is not None and S.names == ["lake pond"], S and S.names
    lk = T.lakes["pond"]
    rng = np.random.default_rng(3)
    a = rng.uniform(0, 2 * np.pi, 3000)
    r = lk["r"] * rng.uniform(0.2, 1.6, 3000)
    p = np.c_[lk["xy"][0] + r * np.cos(a), lk["xy"][1] + r * np.sin(a)]
    x, y = np.ascontiguousarray(p[:, 0]), np.ascontiguousarray(p[:, 1])
    h, _ = field.column(x, y)
    h0, _ = field._column(x, y)
    h0 = h0 + field.edits.dz(x, y)  # (turf lips, if any)
    assert np.allclose(h, h0, atol=1e-6), ("a lake's bed was shaped", float(np.abs(h - h0).max()), S.sample(p)["still"].min())
    W, c = mats.weights(np.c_[p, h], np.tile([0.0, 0.0, 1.0], (len(p), 1)))
    lw = lambda *nm: sum(W[:, mats.layers.index(k)] for k in nm)
    under = h < lk["level"] - 0.15
    assert under.sum() > 100 and np.percentile(lw("gravel", "silt")[under], 10) > 0.9
    g = S.sample(p)
    far_in = under & (g["sd"] < -5)
    assert far_in.sum() > 20 and np.median(lw("silt")[far_in]) > 0.8  # silt out in the lake, gravel by its shore
    foot = (h > lk["level"] + 0.05) & (h < lk["level"] + 0.3) & (g["sd"] < 2)
    assert foot.sum() > 5 and np.median(lw("bank")[foot]) > 0.3
    C = ts.all_clutter(T, mats, field)
    kinds = list(ts.KINDS)
    n = lambda k, sel=C: int((sel[:, 3] == kinds.index(k)).sum())
    lake = C[C[:, 8] == 0]
    assert n("reeds", lake) > 3 and n("cobbles", lake) + n("sedge", lake) > 5, {k: n(k, lake) for k in kinds}
    assert not n("slab", lake)
    beach = C[C[:, 8] == -1]
    assert n("pebbles", beach) > 10 and n("wrack", beach) > 3, {k: n(k, beach) for k in kinds}
    assert np.all(beach[:, 7] == ts.PLACES.index("shore")) and np.all(beach[:, 2] > 0.1)
    wr = beach[beach[:, 3] == kinds.index("wrack")]
    assert 0.6 < np.median(wr[:, 2]) < 2.0, np.median(wr[:, 2])  # along the high water mark
    lines = ts.summary(S, C)
    assert any("sea beaches" in ln for ln in lines) and any("lake pond" in ln for ln in lines), lines
    return {k: n(k) for k in kinds if n(k)}


def test_swatches_and_styles():
    for fn in (ts.cobble_swatch, ts.silt_swatch):
        S = fn()
        a = np.round(np.clip(0.5 * S["albedo"], 0, 1) * 255).astype(np.uint8)
        assert max(terrain_swatch.tileability(a)) < 1.5, (fn.__name__, terrain_swatch.tileability(a))
        assert abs(float(S["albedo"].mean()) - 1) < 0.02
    refs = {k: dict(v) for k, v in tm.LAYERS.items()}
    for name in ("realistic", "blobby", "anime", "cartoon", "pixar"):
        st = terrain_style.sheet(name)
        for layer in ts.LAYERS:
            assert layer in terrain_style.STYLE_LAYERS
            t = terrain_style.texture(st, layer, terrain_style.layer_colour(st, layer, refs), px=256)
            assert t["projection"] == "top" and np.isfinite(t["albedo"]).all()
        t = terrain_style.texture(st, "gravel", terrain_style.layer_colour(st, "gravel", refs), px=256)
        assert t["albedo"].std() > 0.01, name  # (stones: not a flat field)
    assert terrain_style.CONTRACT >= 5 and 5 in terrain_style.CONTRACT_LOG


if __name__ == "__main__":
    t0 = time.time()
    T = _load(SPEC)
    print("built", round(time.time() - t0), "s")
    field, mats = _mats(T)
    test_zone_and_layers(T, field, mats)
    print("zone and layers ok")
    test_bed_shape_only_under_water(T, field, mats)
    print("bed shape ok")
    n = test_clutter_rules(T, field, mats)
    print("clutter ok", n)
    test_energy_sets_the_character(T, n)
    print("energy ok")
    test_off_and_no_rivers(T)
    print("off / no rivers ok")
    print("lake shore and beach ok", test_lake_shore_and_beach())
    test_swatches_and_styles()
    print("swatches and styles ok")
    print("all ok", round(time.time() - t0), "s")
