"""Macro sliders as calibrated directions in GNM's identity space (humanmacro.py) and the MAP image fit
(humanfit_map.py): uv run python tests/test_humanmacro.py (needs the gnm pack; the fit test the makehuman pack too).
The first call calibrates the macros (a minute, cached in <HOME>/_cache)."""
import numpy as np

from hifipushie import assets, humanmacro as hm


def have(mh=False):
    try:
        assets.path("gnm", "gnm/shape/data/versions/v3_0/gnm_head.npz")
        if mh:
            from hifipushie import makehuman
            makehuman.body({"age": 25, "sex": 0.5})
        return True
    except Exception as err:
        print("skipped:", str(err)[:80])
        return False


def test_macros_follow_their_sliders():
    t = hm.table()
    assert np.isfinite(t["A"]).all() and (t["r2"] > 0.95).all(), "a macro's measure is not near linear in the identity"
    assert "chin_cleft" in t["weak"], "the identity space was expected not to hold a cleft chin"
    assert len(t["weak"]) <= 3, t["weak"]
    for k in hm.NAMES:
        if k in t["weak"]:
            continue
        z = hm.read(hm.apply(None, {k: 2.0}))[k]
        assert 1.5 < z < 2.5, (k, z)
        s = hm.soundness(hm.apply(None, {k: 2.0}))
        assert s["flipped"] == 0, (k, s)
    assert abs(hm.read(np.zeros(hm.K))["jaw_square"]) < 0.2   # the mean head reads ~0


def test_what_goes_with_it_and_held():
    t = hm.table()
    # a square jaw alone brings a broad chin with it (the population's correlation); held, it does not
    free = hm.read(hm.apply(None, {"jaw_square": 2.0}))
    held = hm.read(hm.apply(None, {"jaw_square": 2.0}, held=True))
    assert free["chin_width"] > 0.6 and abs(held["chin_width"]) < 0.35, (free["chin_width"], held["chin_width"])
    others = [abs(held[k]) for k in hm.NAMES if k != "jaw_square" and k not in t["weak"]]
    assert max(others) < 0.5, max(others)
    assert np.linalg.norm(hm.direction("jaw_square")) < np.linalg.norm(hm.direction("jaw_square", held=True))


def test_solve_meets_asked_macros():
    c = np.random.default_rng(4).normal(0, 0.6, hm.K)
    c1, rep = hm.solve(c, {"jaw_square": 1.5, "chin_projection": 1.0, "nose_upturn": 1.0})
    z = hm.read(c1)
    assert abs(z["jaw_square"] - 1.5) < 0.12 and abs(z["chin_projection"] - 1.0) < 0.12 and abs(z["nose_upturn"] - 1.0) < 0.12, rep["asked"]
    z0 = hm.read(c)
    moved = [abs(z[k] - z0[k]) for k in hm.NAMES if k not in ("jaw_square", "chin_projection", "nose_upturn", "chin_cleft")]
    assert np.median(moved) < 0.3, np.median(moved)
    assert hm.soundness(c1)["flipped"] == 0
    assert hm.from_identity(hm.identity_dict(c1)).round(3).tolist() == np.round(c1, 4).round(3).tolist()


def test_read_as_evidence():
    # a read alone (rows + the unit prior) moves the head toward what was said, by less than was said (a prior, not a pin)
    A, y = hm.prior_rows({"jaw_square": 1.5, "cheek_fullness": 1.5}, sd=0.8)
    c = np.linalg.solve(A.T @ A + np.eye(hm.K), A.T @ y)
    z = hm.read(c)
    assert 0.5 < z["jaw_square"] < 1.5 and 0.5 < z["cheek_fullness"] < 1.5, (z["jaw_square"], z["cheek_fullness"])
    assert np.sqrt((c ** 2).mean()) < 0.5


def test_map_fit_recovers_a_known_head():
    """A one-mesh head with a known identity, seen as the detector would see it (its 478 points at their calibrated
    places, 1.5 mm of noise, front + three-quarter): the MAP fit from a fresh head ends nearer the truth, stays a
    plausible head and keeps the mesh sound; a read of the truth's strongest macros helps further."""
    from hifipushie import humanfit as hf, humanfit_map as fm, onemesh
    fresh = {"body": {"source": "human", "age": 34, "sex": 1.0}, "head": {}}
    rng = np.random.default_rng(8)
    ct = rng.normal(0, 1.0, hm.K)
    truth = hf._with_identity(fresh, ct)
    st = hf.state(truth)
    views = []
    for yaw in (0.0, 40.0):
        ev = fm._evidence(st, [{"mp478": np.zeros((478, 2)), "size": [900, 900], "yaw": yaw}])[0]
        cam = {"r": [0.05, 0.0, 0.02], "t": [0.0, 0.0, 1.1], "f": 1700.0, "size": [900, 900], "centre": st["L"][:68].mean(0).tolist(), "yaw": yaw + 3}
        P = np.zeros((478, 2))
        P[ev["mp_idx"]] = hf.project(cam, ev["X"]) + rng.normal(0, 1.5 / (1.1 / 1700 * 1000), (len(ev["X"]), 2))
        views.append({"mp478": P, "size": [900, 900], "yaw": yaw})

    def err(b):
        tp = hf.state(b)["tpl"]
        gid = np.asarray(onemesh.asset()["gnm_id"], int)[np.asarray(tp["fid"])]
        f = np.flatnonzero((gid >= 0) & (np.asarray(onemesh.asset()["g_fade"])[np.maximum(gid, 0)] > 0.99))[::7]
        X, Y = np.asarray(tp["P"])[f], np.asarray(st["tpl"]["P"])[f]   # after a similarity alignment (pictures give no size)
        A, B = X - X.mean(0), Y - Y.mean(0)
        U, S, Vt = np.linalg.svd(B.T @ A)
        Dm = np.diag([1, 1, np.sign(np.linalg.det(U @ Vt))])
        R, sc = U @ Dm @ Vt, (S * np.diag(Dm)).sum() / (A ** 2).sum()
        return float(np.linalg.norm(sc * A @ R.T - B, axis=1).mean() * 1000)
    b1, rep = fm.fit(fresh, views)
    assert not rep.get("refused") and rep["integrity"]["ok"], hf.verdict(rep["integrity"])
    assert rep["plausibility"]["rms_sigma"] < 1.0
    e0, e1 = err(fresh), err(b1)
    assert e1 < 0.75 * e0, (e0, e1)
    zt = hm.read(ct)
    strong = dict(sorted(((k, float(np.sign(v) * 1.5)) for k, v in zt.items() if abs(v) > 1.0 and k != "chin_cleft"), key=lambda kv: kv[0])[:8])
    b2, rep2 = fm.fit(fresh, views, read=strong)
    assert rep2["integrity"]["ok"] and err(b2) < e1 + 0.05, (e1, err(b2))


if __name__ == "__main__":
    if have():
        test_macros_follow_their_sliders()
        test_what_goes_with_it_and_held()
        test_solve_meets_asked_macros()
        test_read_as_evidence()
        print("macros ok")
    if have(mh=True):
        test_map_fit_recovers_a_known_head()
        print("map fit ok")
