"""hair.lift (a groom fuller or closer by region) and hair.lock_meshes (locks as numpy tubes), on a synthetic sphere
scalp: uv run python tests/test_hair_lift.py (no Blender, no packs)."""
import numpy as np

from hifipushie import hair


def _scalp():
    A = np.arange(0.0, 360.0, hair.Scalp.STEP)
    E = np.arange(hair.Scalp.EL[0], hair.Scalp.EL[1] + 1e-6, hair.Scalp.STEP)
    return hair.Scalp([0.0, 0.0, 1.7], np.full((len(A), len(E)), 0.09), {})


def _spec():
    side = {"pts": [[90.0, 40.0, 0.002], [95.0, 30.0, 0.004], [100.0, 20.0, 0.004]], "width": 0.04, "thickness": 0.006}
    top = {"pts": [[0.0, 70.0, 0.003], [90.0, 80.0, 0.006], [180.0, 70.0, 0.004]], "width": 0.05, "thickness": 0.006}
    return {"hair": {"locks": {"side": side, "top": top}, "groom": {"volume": {"sides": 0.006}}}}


def test_lift_by_region():
    sc = _scalp()
    spec = _spec()
    out, rep = hair.lift(spec, sc, {"sides": 0.01})
    s0 = np.asarray(spec["hair"]["locks"]["side"]["pts"])
    s1 = np.asarray(out["hair"]["locks"]["side"]["pts"])
    t0 = np.asarray(spec["hair"]["locks"]["top"]["pts"])
    t1 = np.asarray(out["hair"]["locks"]["top"]["pts"])
    assert np.allclose(s1[:, :2], s0[:, :2])  # only the height over the scalp moves
    assert (s1[:, 2] - s0[:, 2]).max() > 0.004 and (s1[:, 2] >= s0[:, 2]).all(), s1 - s0  # the side lock comes out
    assert np.abs(t1[:, 2] - t0[:, 2]).max() < 0.003  # the top lock hardly
    assert abs(out["hair"]["groom"]["volume"]["sides"] - 0.016) < 1e-9  # the underlayer with it
    assert rep["locks"] == 2 and spec["hair"]["locks"]["side"]["pts"][0][2] == 0.002  # the input is untouched
    try:
        hair.lift(spec, sc, {"temples": 0.01})
        raise AssertionError("an unknown region was accepted")
    except hair.HairError:
        pass


def test_lift_fill_thickens():
    """fill=True: a lock lifted by d grows 2 d thicker (its lens still reaches down where it lay: strands fill)."""
    sc = _scalp()
    spec = _spec()
    out, _ = hair.lift(spec, sc, {"sides": 0.01}, fill=True)
    s0 = np.asarray(spec["hair"]["locks"]["side"]["pts"])
    s1 = np.asarray(out["hair"]["locks"]["side"]["pts"])
    d = float(np.mean(s1[:, 2] - s0[:, 2]))
    assert abs(out["hair"]["locks"]["side"]["thickness"] - (0.006 + 2 * d)) < 1e-4


def test_trim_cuts_at_the_hairline():
    """trim: a back lock running down past the nape line is cut `below` m outside it; a lock inside is untouched."""
    sc = _scalp()
    spec = _spec()
    line = hair.hairline(sc, hair.groom_params(spec))
    e0 = float(line[180])
    spec["hair"]["locks"]["back"] = {"pts": [[180.0, e0 + 30, 0.003], [180.0, e0 + 10, 0.003], [180.0, e0 - 10, 0.003],
                                             [180.0, e0 - 25, 0.003]], "width": 0.03, "thickness": 0.004,
                                     "radius": [1.0, 1.0, 0.8, 0.6]}
    out, rep = hair.trim(spec, sc, 0.005)
    P = np.asarray(out["hair"]["locks"]["back"]["pts"])
    d = hair.inside(sc, line, P[:, 0], P[:, 1])
    assert rep["cut"] == 1 and abs(d[-1] + 0.005) < 0.002 and len(out["hair"]["locks"]["back"]["radius"]) == len(P)
    assert out["hair"]["locks"]["top"] == spec["hair"]["locks"]["top"]


def test_lock_meshes_are_tubes_round_the_spine():
    sc = _scalp()
    locks = hair.resolve(_spec(), sc)
    V, F = hair.lock_meshes(sc, locks, n=12, across=5)
    m = 5 + 3  # outer face points + inner face points between the edges
    assert len(V) == 2 * 12 * m and len(F) == 2 * 11 * m and F.max() < len(V)
    S = hair._catmull(locks[0]["pts"], 12)
    R = V[: 12 * m].reshape(12, m, 3)
    d = np.linalg.norm(R - S[:, None], axis=2)
    assert d.max() < 0.5 * 0.05 + 0.01  # within half the widest lock (+ the cup) of its spine


if __name__ == "__main__":
    for fn in (test_lift_by_region, test_lift_fill_thickens, test_trim_cuts_at_the_hairline, test_lock_meshes_are_tubes_round_the_spine):
        fn()
        print("ok", fn.__name__)
