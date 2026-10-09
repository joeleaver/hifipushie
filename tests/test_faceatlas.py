"""faceatlas: the face sliders as whole-model directions (the conditional mean of GNM's identity given an attribute's
change). Their side effects follow the population's correlations, holds hold, no fold at the extremes, a coupled
slider is recovered from a render."""
import copy
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from hifipushie import assets, base, faceatlas, faceslide, gnmloops, humanfit, humans  # noqa: E402


def _ok():
    try:
        assets.path("gnm", base.GNM)
        return faceatlas.TABLE.exists()
    except Exception:
        return False


def _attrs(dc):
    return faceatlas.attributes(*faceatlas.head(dc))


def test_side_effects_follow_the_population():
    """A pooled (within=False) 1-sd change of an attribute moves it by ~1 sd, and every strongly coupled attribute
    (|r| > 0.6 in the sampled heads) by ~r sd: what the population does, not an isolated change."""
    if not _ok():
        return
    t = faceatlas.table()
    names = [str(n) for n in t["names"]]
    a0 = _attrs(np.zeros(faceatlas.K))
    for attr in ("eye_setback", "upper_vermilion", "eye_tilt", "lid_aperture"):
        i = t["index"][attr]
        dc = faceatlas.direction({attr: float(t["sd"][i])}, within=False)
        a1 = _attrs(dc)
        got = (a1[attr] - a0[attr]) / t["sd"][i]
        assert abs(got - 1.0) < 0.15, (attr, got)
        for j, b in enumerate(names):
            r = t["corr"][i, j]
            if b != attr and np.isfinite(r) and abs(r) > 0.6 and t["r2"][j] > 0.9:
                gb = (a1[b] - a0[b]) / t["sd"][j]
                assert abs(gb - r) < 0.2, (attr, b, round(float(gb), 2), round(float(r), 2))


def test_hold_keeps_the_named_attribute():
    """eye_setback +1 sd with brow_ridge held: the eyes go back, the brow ridge stays (Tess); free, the brow comes
    with it (r ~ 0.85 in GNM's faces)."""
    if not _ok():
        return
    t = faceatlas.table()
    sd = lambda a: float(t["sd"][t["index"][a]])  # noqa: E731
    a0 = _attrs(np.zeros(faceatlas.K))
    free = _attrs(faceatlas.direction({"eye_setback": sd("eye_setback")}))
    held = _attrs(faceatlas.direction({"eye_setback": sd("eye_setback")}, hold=("brow_ridge",)))
    assert abs((held["eye_setback"] - a0["eye_setback"]) / sd("eye_setback") - 1) < 0.15
    assert abs(held["brow_ridge"] - a0["brow_ridge"]) / sd("brow_ridge") < 0.1
    assert (free["brow_ridge"] - a0["brow_ridge"]) / sd("brow_ridge") > 0.5


def test_coupled_sliders_fold_nothing():
    """Every coupled slider at -1.5 / +1.5 (sds) on GNM's mean head: no skin quad turns over (the template's, with the
    lids' loops)."""
    if not _ok():
        return
    T = faceslide.template()
    Q = gnmloops.plan()["quads"]
    Q = Q[T["skin"][Q].all(1)]
    X0 = gnmloops.ext(faceatlas.head(np.zeros(faceatlas.K))[0])

    def nrm(X):
        n = np.cross(X[Q[:, 2]] - X[Q[:, 0]], X[Q[:, 3]] - X[Q[:, 1]])
        return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-18)
    n0 = nrm(X0)
    area = 0.5 * np.linalg.norm(np.cross(X0[Q[:, 2]] - X0[Q[:, 0]], X0[Q[:, 3]] - X0[Q[:, 1]]), axis=1)
    big = area > 1.5e-7  # (GNM's near-degenerate commissure quads turn with any change: left out, as elsewhere)
    for k in faceatlas.COUPLED:
        for v in (-1.5, 1.5):
            dc, _ = faceatlas.slider_identity({k: v})
            X1 = gnmloops.ext(faceatlas.head(dc)[0])
            turned = int(((np.einsum("ij,ij->i", n0, nrm(X1)) < 0) & big).sum())
            assert turned == 0, (k, v, turned)


def test_coupled_slider_recovered_from_a_render():
    """lip_upper_roll in coupled mode, read back from a render's depth (faceslide.read_mouth) by faceslide.fit."""
    if not _ok():
        return
    b = humans.spec(age=40, sex=1.0, seed=None, skin=False, source="human")["base"]
    b["head"]["slider_mode"] = "coupled"
    bt = copy.deepcopy(b)
    bt["head"]["sliders"] = {"lip_upper_roll": 0.6}
    m = faceslide.read_mouth(humanfit.state(bt))
    r = faceslide.fit(b, {"upper_proj": (m["upper_proj"], 0.1)}, ["lip_upper_roll"], read=faceslide.read_mouth)
    assert abs(r["sliders"]["lip_upper_roll"] - 0.6) < 0.1, r
