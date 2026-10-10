"""Waterfalls (terrain_falls): `rivers.<r>.falls: [{"at", "drop", "width"?}]`: a hard rock lip, a near-vertical face,
a plunge pool, the water's level stepping at the lip, meta for the game's sheet and spray; a river falling off a sea
cliff into the sea. uv run python tests/test_falls.py"""
import copy
import json
import tempfile
import time
from pathlib import Path

import numpy as np

from hifipushie import terrain

SPECS = {
    "inland": {"world": {"kind": "farmland", "base": 40}, "extent": [[0, 0], [256, 320]], "cell": 1.0,
               "rivers": {"beck": {"source": [128, 310, 62], "through": [[120, 200], [136, 110]], "mouth": [128, 10, 20],
                                   "water": 3, "valley": {"profile": "V", "floor": 20},
                                   "falls": [{"at": 0.3, "drop": 3}, {"at": 0.62, "drop": 12, "width": 5}]}},
               "cover": [{"type": "meadow", "in": "everywhere"}]},
    "sea": {"world": {"kind": "coast", "base": 32}, "extent": [[0, 0], [300, 300]], "cell": 1.0,
            "zones": {"land": {"polygon": [[-10, 70], [310, 70], [310, 310], [-10, 310]]}},
            "sea": {"level": 0, "land": "land", "depth": 20, "shore": "cliffs", "cliffs": {"height": [28, 32]}},
            "rivers": {"spout": {"source": [150, 295, 50], "through": [[160, 200]], "mouth": [150, 70, 0], "water": 3,
                                 "valley": {"profile": "V", "floor": 16}, "falls": [{"at": 1.0, "drop": 30}]}},
            "cover": [{"type": "meadow", "in": "everywhere"}]},
}


def _load(spec):
    d = Path(tempfile.mkdtemp())
    (d / "spec.json").write_text(json.dumps(spec))
    return terrain.load(d / "spec.json")


def _section(T, f, u):
    c = np.mean(np.array(f["lip"])[:, :2], 0)
    return T.sample(c + np.asarray(u)[:, None] * np.array(f["flow"]))


def test_inland(T):
    assert len(T.falls) == 2, T.falls
    small, big = T.falls
    for f, asked in ((small, 3), (big, 12)):
        assert abs(f["drop"] - asked) < 0.25 * asked + 0.5, f
        assert f["into"] == "river"
        # the lip stands at its water level, the pool's water below
        u = np.arange(-6, -1, 0.5)  # (the bed upstream of the lip: under its water by the channel's depth at most)
        assert _section(T, f, u).min() > f["lip"][0][2] - 1.5, (_section(T, f, u), f)
        assert f["pool"]["xyz"][2] < f["lip"][0][2] - 0.75 * asked
        # the plunge pool: deeper than the river just downstream
        pc = np.array(f["pool"]["xyz"][:2])
        assert T.sample(pc[None])[0] < f["pool"]["xyz"][2] - 0.8, (T.sample(pc[None])[0], f["pool"])
    assert big["width"] == 5
    from hifipushie import terrain_falls
    m = {f["at"]: f for f in terrain_falls.measure(T)}
    assert m[big["at"]]["face_deg"] > 70, m  # (one-metre cells: a 12 m face stands)
    # the water's level steps at each lip and falls everywhere else
    lv = np.asarray(T.river_water_lines["beck"]["level"])
    steps = np.sort(-np.diff(lv))[::-1]
    assert steps[0] > 9 and steps[1] > 2, steps[:4]
    assert steps[2] < 1.0, steps[:4]
    assert (np.diff(lv) <= 1e-6).all()
    # hard rock at the lip and face (erosion leaves it)
    lip = np.array(big["lip"])[:, :2].mean(0)
    iy, ix = int(round((lip[1] - T.ys[0]) / T.cell)), int(round((lip[0] - T.xs[0]) / T.cell))
    assert T.hard[iy - 2:iy + 3, ix - 2:ix + 3].any()
    rep = T.report()
    assert "fall on beck at 0.62" in rep, rep[-2000:]
    print("ok inland falls:", [(f["drop"], terrain_falls.measure(T)[k]["face_deg"]) for k, f in enumerate(T.falls)])


def test_sea(T):
    assert len(T.falls) == 1, T.falls
    f = T.falls[0]
    assert f["into"] == "sea", f
    assert f["pool"]["xyz"][2] == 0 and f["pool"]["depth"] is None
    assert f["drop"] > 20, f
    print("ok sea cliff fall:", f["drop"], "m into the sea")


def _cliff_field(T, tile=32):
    from hifipushie import terrain_cliffs as tc, terrain_mesh as tm
    cfg = {**tm.DEFAULTS, "tile": tile}
    base, vols, *_ = tm.build_field(T, cfg)
    G = tm.Grid(T, cfg)
    R = tc.Region(T, base, G, cfg)
    return tc.CliffField(base, R), R, G, vols, cfg


def _frame(f):
    c = np.mean(np.array(f["lip"])[:, :2], 0)
    t_ = np.array(f["flow"], float)
    return c, t_, np.array([-t_[1], t_[0]])


def test_sea_face(T, field=None):
    """A sea-cliff fall in the 3D cliff field (pushieworld note 120): the lip stands to the lip line, the face drops
    vertically there, and no rock stands in the sheet's path above the sea: the grid's own face was a 75-80 deg ramp
    3.5 m long starting upstream of the lip, and the sheet drawn from the lip fell onto it."""
    from hifipushie import terrain_corridors as co, terrain_falls as tf
    cf, R, *_ = field or _cliff_field(T)
    f = T.falls[0]
    c, t_, n = _frame(f)
    up, dn, wl = f["lip"][0][2], f["pool"]["xyz"][2], f["width"]
    throw = tf.Faces(T).items[0]["throw"]
    u = np.arange(-4.0, throw + 0.01, 0.25)
    for v in np.linspace(-0.4, 0.4, 5) * wl:
        xy = c + u[:, None] * t_ + v * n
        top = co.top(cf, R, xy[:, 0], xy[:, 1])
        lip = (u >= -3.0) & (u <= -0.5)
        assert top[lip].min() > up - 1.5, (v, u[lip], top[lip])  # (the lip's bed, under its water)
        out = (u >= 0.5) & (u <= throw)
        assert top[out].max() < dn + 0.3, (v, u[out], top[out])  # (nothing over the sea under the sheet)
    # no rock anywhere in the sheet's path: from the lip plane out to its throw, across the water, sea to lip
    uu, vv, zz = np.meshgrid(np.arange(0.3, throw, 0.25), np.linspace(-0.5, 0.5, 9) * wl,
                             np.arange(dn + 0.3, up + 1.0, 0.25), indexing="ij")
    xy = c + uu.ravel()[:, None] * t_ + vv.ravel()[:, None] * n
    P = np.c_[xy, zz.ravel()]
    assert (cf.value(P) > 0).all(), P[cf.value(P) <= 0][:5]
    print(f"ok sea fall in the cliff field: lip to the lip line, sheet clear {throw:.1f} m out, {len(P)} points air")


def test_clutter(T):
    from hifipushie import terrain_mesh as tm, terrain_stream as ts
    base = tm.build_field(T)[0]
    field = getattr(base, "base", base)
    mats = tm.Materials(T, base)
    C = ts.clutter(T, mats, field)
    kinds = {k: i for i, k in enumerate(ts.KINDS)}
    big = T.falls[1]
    pc, R = np.array(big["pool"]["xyz"][:2]), big["pool"]["radius"]
    lip = np.mean(np.array(big["lip"])[:, :2], 0)
    d = np.hypot(C[:, 0] - pc[0], C[:, 1] - pc[1])
    rocks = (C[:, 3] == kinds["river_rock"]) & (d < 1.6 * R)
    slabs = (C[:, 3] == kinds["slab"]) & (np.hypot(C[:, 0] - lip[0], C[:, 1] - lip[1]) < 0.35 * big["drop"] + 6)
    assert rocks.sum() >= 3, rocks.sum()
    assert slabs.sum() >= 1, slabs.sum()
    print(f"ok clutter at the 12 m fall: {rocks.sum()} boulders round the pool, {slabs.sum()} blocks at the foot")


def test_errors():
    s = copy.deepcopy(SPECS["inland"])
    s["rivers"]["beck"]["falls"] = [{"at": 0.5, "drop": 60}]
    try:
        _load(s)
    except ValueError as e:
        assert "90%" in str(e), e
    else:
        raise AssertionError("a fall taller than the river's fall was accepted")
    print("ok errors")


def test_meta(T):
    out = Path(tempfile.mkdtemp())
    T.export(out) if hasattr(T, "export") else None
    mj = out / "meta.json"
    if mj.exists():
        m = json.loads(mj.read_text())
        assert len(m["falls"]) == 2 and "falls_note" in m
        print("ok meta.json falls")


if __name__ == "__main__":
    t = time.time()
    test_errors()
    T = _load(SPECS["inland"])
    test_inland(T)
    test_meta(T)
    test_clutter(T)
    Ts = _load(SPECS["sea"])
    test_sea(Ts)
    test_sea_face(Ts)
    print(f"all ok {time.time() - t:.0f} s")
