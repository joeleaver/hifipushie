"""Dense landmarks (denselm, 2026-10-12): the landmark set on GNM's topology, the eyeball points, the crop, and the
face ruler's "dense" observation (against a known identity change, with a made-up detector reading: no trained
network needed). The model tests need the workspace block-in tn_T00 and are skipped without it.
uv run python -m pytest -q tests/test_denselm.py"""
import numpy as np
import pytest

from hifipushie import assets, denselm, face_ruler as fr, store

try:
    assets.pack("gnm")
    HAVE = True
except Exception:  # noqa: BLE001
    HAVE = False
pytestmark = pytest.mark.skipif(not HAVE, reason="GNM asset pack not installed")
REF = "tn_T00"
need_ref = pytest.mark.skipif(not (store.HOME / REF / "human_refs.json").exists(), reason=f"workspace model {REF} not present")


def test_the_set_is_symmetric_covers_the_face_and_holds_the_68():
    L = denselm.landmarks()
    n, ns = L["n"], L["n_skin"]
    assert 500 <= ns <= 750 and n == ns + 2 * (1 + denselm.LIMBUS_N)
    assert len(set(L["gnm"].tolist())) == ns                                   # no vertex twice
    assert (L["mirror"][L["mirror"]] == np.arange(n)).all()                    # mirroring twice = the identity
    T, gr, present, _ = denselm._groups()
    P = T[L["gnm"]]
    assert np.abs(P[L["mirror"][:ns]] - P * [-1, 1, 1]).max() < 0.001          # the mirror landmark lies at the mirrored place
    assert (L["lm68"] >= 0).all() and len(set(L["lm68"].tolist())) >= 60       # the 68 standard landmarks are in it
    assert present[L["gnm"]].all() and gr["skin_exterior"][L["gnm"]].all()     # on skin the one mesh carries
    reg = L["region"][:ns]
    for r, least in (("lids", 12), ("lips", 30), ("nose", 40), ("chin", 20), ("cheeks", 50), ("ears", 16)):
        assert (reg == r).sum() >= least, r
    # denser where it matters: nearest-neighbour spacing at the lips under half the scalp's
    def spacing(m):
        Q = P[m]
        d = np.linalg.norm(Q[:, None] - Q[None], axis=2) + np.eye(len(Q))
        return np.median(d.min(1))
    assert spacing(reg == "lips") < 0.5 * spacing(reg == "scalp_neck")
    # eyeball points: L <-> R, and the ring's points swap left-right
    names = L["names"]
    assert names[L["mirror"][names.index("iris.L")]] == "iris.R"
    assert names[L["mirror"][names.index("limbus.L.0")]] == f"limbus.R.{denselm.LIMBUS_N // 2}"


def test_limbus_points_lie_on_the_ball_round_the_gaze_axis():
    c, a = np.array([0.03, -0.08, 1.6]), np.array([0.1, -1.0, 0.05])
    P = denselm.limbus_points(c, a, 0.012, 0.0059)
    assert P.shape == (1 + denselm.LIMBUS_N, 3)
    assert np.allclose(np.linalg.norm(P[1:] - c, axis=1), 0.012, atol=1e-9)
    assert np.allclose(np.linalg.norm(P[1:] - P[0], axis=1), 0.0059, atol=1e-9)
    an = a / np.linalg.norm(a)
    assert np.allclose((P[1:] - P[0]) @ an, 0, atol=1e-9)
    assert P[1, 0] > P[0, 0] and P[1 + denselm.LIMBUS_N // 4, 2] > P[0, 2]     # point 0 toward the subject's left (+x), a quarter on: up
    # mirrored eye, mirrored gaze: point k of one is the mirror image of point n/2 - k of the other
    M = np.array([-1.0, 1.0, 1.0])
    P2 = denselm.limbus_points(c * M, a * M, 0.012, 0.0059)
    k = np.arange(denselm.LIMBUS_N)
    assert np.allclose(P2[1 + (denselm.LIMBUS_N // 2 - k) % denselm.LIMBUS_N], P[1 + k] * M, atol=1e-9)


def test_crop_box_and_crop():
    from PIL import Image
    xy = np.array([[100.0, 200.0], [300.0, 260.0], [200.0, 420.0]])
    x0, y0, x1, y1 = denselm.box_of(xy)
    assert abs((x1 - x0) - (y1 - y0)) < 1e-9 and abs((x1 - x0) - denselm.BOX_SCALE * 220) < 1e-6
    assert abs((x0 + x1) / 2 - 200) < 1e-9 and abs((y0 + y1) / 2 - 310) < 1e-9
    im = Image.new("RGB", (400, 500), (10, 200, 30))
    c = denselm.take_crop(im, (x0, y0, x1, y1))
    assert c.size == (denselm.SIZE, denselm.SIZE)
    a = np.asarray(c)
    assert (np.abs(a.reshape(-1, 3).astype(int) - [10, 200, 30]).max(1) <= 2).all()       # outside the picture: its own colour


@pytest.fixture(scope="module")
def tess():
    from hifipushie import blockin as bi
    spec = store.load(REF)
    head = fr.model_head(spec)
    rj = bi._refs(REF)
    return spec, head, rj


@need_ref
def test_dense_obs_reads_a_known_change_and_nothing_on_the_head_itself(tess):
    spec, head, rj = tess
    cam = rj["cameras"][0]
    view = {"cam": cam, "kind": "front"}
    L = denselm.landmarks()
    assert fr._dense_obs(head, view, None) == []
    # the detector's reading, made up: the model's own vertices through the camera, sure everywhere
    pred0 = {"xy": np.zeros((L["n"], 2)), "sigma": np.full(L["n"], 0.5)}
    obs0 = fr._dense_obs(head, view, pred0)
    assert len(obs0) > 800 and {ob["type"] for ob in obs0} == {"dense"}
    Q = np.zeros((L["n"], 2))
    for ob in obs0:
        j = L["names"].index(ob["name"][:-2])
        Q[j] = ob["p"]
    obs = fr._dense_obs(head, view, {"xy": Q, "sigma": np.full(L["n"], 0.5)})
    assert max(abs(ob["o"]) for ob in obs) < 1e-6                                  # the head itself: nothing to read
    assert min(ob["sig"] for ob in obs) >= fr.DENSE_SIG_FLOOR
    # a known identity change: the reading of the changed head, against J dc
    r = np.random.default_rng(5).standard_normal(170)
    dc = 3.0 * r / np.linalg.norm(r)
    h2 = head["rebuild"](head["c"] + dc)
    Q2 = np.zeros((L["n"], 2))
    for ob in fr._dense_obs(h2, view, pred0):
        Q2[L["names"].index(ob["name"][:-2])] = ob["p"]
    obs = fr._dense_obs(head, view, {"xy": Q2, "sigma": np.full(L["n"], 0.5)})
    o = np.array([ob["o"] for ob in obs])
    pr = np.array([ob["J"][:170] for ob in obs]) @ dc
    assert np.corrcoef(o, pr)[0, 1] > 0.9
    assert np.sqrt(np.mean((o - pr) ** 2)) < 0.45 * np.sqrt(np.mean(o ** 2))
    # an unsure landmark is left out, a less sure one counts less
    sg = np.full(L["n"], 0.5)
    sg[:50] = 1e3
    assert len(fr._dense_obs(head, view, {"xy": Q, "sigma": sg})) < len(obs)
    regs = {ob["region"] for ob in fr._dense_obs(head, {**view, "chin": {"dense_regions": ("chin", "cheeks")}}, {"xy": Q, "sigma": np.full(L["n"], 0.5)})}
    assert regs == {"chin", "cheeks"}
