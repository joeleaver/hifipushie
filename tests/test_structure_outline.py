"""T15 (C299): the outline check: traces validated at step 2, the build's outline vs the trace at step 6."""
import numpy as np
import pytest
from PIL import Image

from hifipushie import structure_outline as so


def _notch():  # a stepped CF notch (mm, view plane: a right, b down), corners at 1..4
    return np.array([[-150, 100], [-60, 100], [-50, 10], [50, 10], [60, 100], [150, 100]], float)


def _dense(P, step=2.0):
    return so._resample(P, step)[0]


def _arc():
    a = np.linspace(-150, 150, 151)
    return np.c_[a, 10 + 90 * (a / 150) ** 2]


def test_arc_vs_notch_fails_at_the_step():
    r = so.compare(_notch(), [_arc()], edge_mm=5.0, mm_per_px=1.0, corners=[1, 2, 3, 4])
    assert r["status"] == "FAIL"
    assert r["p95_mm"] > r["tol_mm"] and r["max_mm"] > 2 * r["tol_mm"]
    worst = np.array(r["worst_mm"])
    steps = _notch()[1:5]
    assert np.min(np.linalg.norm(steps - worst, axis=1)) < 20  # the worst place is at a step corner
    assert sum(c["kept"] is False for c in r["corners"]) >= 2


def test_matching_outline_passes_with_corners_kept():
    rng = np.random.default_rng(0)
    built = _dense(_notch(), 3.0) + rng.normal(0, 0.8, (len(_dense(_notch(), 3.0)), 2))
    r = so.compare(_notch(), [built], edge_mm=3.0, mm_per_px=1.0, corners=[1, 2, 3, 4])
    assert r["status"] == "PASS", r["fails"]
    assert all(c["kept"] for c in r["corners"])


def test_shifted_outline_reports_the_shift():
    r = so.compare(_notch(), [_dense(_notch(), 3.0) + [0, 60]], edge_mm=3.0, mm_per_px=1.0, corners=[1, 2, 3, 4])
    assert r["p95_mm"] <= r["tol_mm"]  # the shape is right ...
    assert abs(r["shift_mm"][1] + 60) < 3 and r["status"] == "FAIL"  # ... set 60 mm off: a length, said
    assert any(f.startswith("placed") for f in r["fails"])


def test_rounded_corner_is_lost():
    P = _dense(_notch(), 1.0)
    from scipy.ndimage import uniform_filter1d
    R = np.c_[uniform_filter1d(P[:, 0], 41, mode="nearest"), uniform_filter1d(P[:, 1], 41, mode="nearest")]  # 40 mm round
    r = so.compare(_notch(), [R], edge_mm=3.0, mm_per_px=1.0, corners=[1, 2, 3, 4])
    assert any(c["kept"] is False for c in r["corners"]) and r["status"] == "FAIL"


def test_crossing_edge_is_not_counted():
    """A CF edge rising off the hem (crossing the trace steeply) is another edge, not a fault of this one."""
    hem = np.array([[-100, 0], [-30, 0], [30, 0], [100, 0]], float)
    built = _dense(hem, 3.0)
    riser = np.c_[np.zeros(20), np.linspace(-60, 0, 20)]
    r = so.compare(hem, [built, riser], edge_mm=3.0, mm_per_px=1.0)
    assert r["status"] == "PASS", r["fails"]


def test_placement_fits_the_scale_from_body_marks():
    at = {"hps.L": [0.06, 0, 1.55], "shoulder.L": [0.21, 0, 1.47]}
    s, u0, v0 = 1.1, 400.0, 1400.0
    px = lambda x, z: [u0 + x * 1000 / s, v0 - z * 1000 / s]  # noqa: E731
    marks = {"hps.L": px(0.06, 1.55), "hps.R": px(-0.06, 1.55), "shoulder.L": px(0.21, 1.47), "shoulder.R": px(-0.21, 1.47)}
    pl = so.placement({"view": "front", "scale": {"mm_per_px": 1.3, "from": "a guess"}}, marks, at)
    assert abs(pl["s"] - s) < 1e-6 and pl["residual_mm"] < 0.1 and pl["step0_mm_per_px"] == 1.3
    one = so.placement({"view": "front", "scale": {"mm_per_px": 1.1, "from": "x"}}, {"hps.L": marks["hps.L"]}, at)
    assert abs(one["u0"] - u0) < 1e-6 and "step 0" in one["how"]


def _read(tmp_path):
    p = tmp_path / "ref.png"
    Image.new("RGB", (200, 300), "white").save(p)
    return {"views": [{"image": str(p), "view": "front"}]}


def _trace(**kw):
    t = dict(id="hem", what="hem", view=0, points=[[10, 250], [60, 260], [100, 200], [190, 250]], corners=[2],
             source="the hem on view 0")
    t.update(kw)
    return t


MARKS = [dict(view=0, at={"hps.L": [120, 40], "hps.R": [80, 40], "shoulder.L": [170, 60]}, source="view 0")]


def test_trace_validation_names_each_fault(tmp_path):
    read = _read(tmp_path)
    bad = []
    so.check_plan({"traces": [_trace()], "body_marks": MARKS}, read, bad)
    assert bad == []
    for kw, word in ((dict(what="hemline"), "what"), (dict(points=[[1, 1], [2, 2]]), "at least"),
                     (dict(points=[[10, 250], [60, 260], [100, 200], [250, 250]]), "outside the image"),
                     (dict(corners=[0]), "corners"), (dict(source=""), "source"), (dict(view=3), "view")):
        bad = []
        so.check_plan({"traces": [_trace(**kw)], "body_marks": MARKS}, read, bad)
        assert any(word in b for b in bad), (kw, bad)
    bad = []
    so.check_plan({"traces": [_trace()], "body_marks": [dict(view=0, at={"hps.L": [1, 1]}, source="x")]}, read, bad)
    assert any("two landmarks" in b for b in bad)
    bad = []
    so.check_plan({"traces": [_trace()], "body_marks": [dict(view=0, at={"navel": [1, 1], "hps.L": [2, 2]}, source="x")]},
                  read, bad)
    assert any("unknown landmark" in b for b in bad)


def test_border_loops_and_facing_pieces():
    n = 6  # two flat grid pieces: one in front of the body (y < 0), one behind
    g = np.array([[i, j] for j in range(n) for i in range(n)], float) / (n - 1)
    F = [[j * n + i, j * n + i + 1, (j + 1) * n + i] for j in range(n - 1) for i in range(n - 1)] + \
        [[j * n + i + 1, (j + 1) * n + i + 1, (j + 1) * n + i] for j in range(n - 1) for i in range(n - 1)]
    X = np.r_[np.c_[g[:, 0] * 0.3, np.full(len(g), -0.1), 1 + g[:, 1] * 0.5],
              np.c_[g[:, 0] * 0.3, np.full(len(g), 0.1), 1 + g[:, 1] * 0.5]]
    M = {"F": np.r_[F, np.array(F) + n * n], "piece": np.r_[np.zeros(n * n, int), np.ones(n * n, int)],
         "names": ["front.L", "back.L"], "roles": {}}
    loops = so.border_loops(M, [0])
    assert len(loops) == 1 and len(loops[0][1]) == 4 * (n - 1)
    assert so.matching_pieces(M, "hem", "front", X) == [0]
    assert so.matching_pieces(M, "hem", "back", X) == [1]
    with pytest.raises(KeyError):
        so.matching_pieces(M, "nope", "front", X)
