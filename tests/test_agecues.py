"""Age cues (agecues.py) and the age step's arithmetic (blockin_age.py) on synthetic inputs; the shipped statistics'
shape (agestats.json, from the Wikimedia age set). uv run python -m pytest -q tests/test_agecues.py"""
import numpy as np
from PIL import Image

from hifipushie import agecues, blockin_age as ba


def test_canonical_levels_and_scales_the_pupils():
    P = np.zeros((478, 2))
    P[468] = [300.0, 420.0]   # subject's right pupil (picture left)
    P[473] = [380.0, 380.0]   # tilted 26.6 deg, 89 px apart
    im = Image.new("RGB", (800, 800), (128, 128, 128))
    _, Q = agecues.canonical(im, P)
    a, b = Q[468], Q[473]
    assert abs(a[1] - agecues.EYE_Y) < 1e-6 and abs(b[1] - agecues.EYE_Y) < 1e-6
    assert abs((b[0] - a[0]) - agecues.CANON_IPD) < 1e-6
    assert abs(0.5 * (a[0] + b[0]) - agecues.CANON_W / 2) < 1e-6


def test_valley_depth():
    xs = np.arange(-8.0, 8.01, 0.25)
    flat = np.ones_like(xs)
    assert agecues._valley(flat, xs, 4.0, 4.0)[0] == 0.0
    dip = 1.0 - 0.1 * np.exp(-(xs - 1.0) ** 2 / 0.5)
    d, x = agecues._valley(dip, xs, 4.0, 4.0)
    assert abs(d - 0.1) < 0.01 and abs(x - 1.0) < 0.3


def test_solve_recovers_levers():
    cues = ("a", "b", "c")
    levers = {"l1": 1.0, "l2": 1.0}
    J = np.array([[1.0, 0.0], [0.0, 2.0], [1.0, 1.0]])
    truth = np.array([0.5, -0.25])
    change = {q: (float(J[i] @ truth), 1.0, 5.0) for i, q in enumerate(cues)}
    r = ba.solve(J, np.ones(2), cues, change, lam=1e-8, levers=levers)
    assert abs(r["moves"]["l1"] - 0.5) < 1e-3 and abs(r["moves"]["l2"] + 0.25) < 1e-3


def test_shipped_statistics():
    S = ba.stats()
    assert S["n"] >= 200
    for k in ("lip_lower", "nl_len", "lid_tps"):
        c = S["cues"][k]
        assert len(c["b"]) == 7 and c["resid_sd"] > 0
    ch = ba.population_change(25, 65, "male", min_z=0.0)
    assert ch["lip_lower"][0] < 0          # lips thin with age


def test_plan_on_a_synthetic_head():
    """GNM's mean head (fs_ge3's body and camera, identity 0, nothing saved): the solved levers move the landmark mass
    cues the population's way between 25 and 65 (lips thinner, philtrum longer, nose wider)."""
    import copy

    import pytest

    from hifipushie import blockin as bi, store
    if not (store.HOME / "fs_ge3" / "human_refs.json").exists():
        pytest.skip("workspace model fs_ge3 not present")
    sp = copy.deepcopy(store.load("fs_ge3"))
    bi.set_identity(sp, np.zeros(len(bi.identity(sp))))
    cam = bi._refs("fs_ge3")["cameras"][0]
    res = ba.plan(sp, cam, 25, 65, "male")
    chk = ba.check(sp, cam, res)
    for k in ("lip_lower", "lip_upper", "philtrum", "nose_w"):
        t, _, got = chk[k]
        assert np.sign(got) == np.sign(t) and abs(got) > 0.4 * abs(t), (k, chk[k])
