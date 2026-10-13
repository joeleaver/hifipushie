"""The joint solve's observations beyond outlines (refread, 2026-10-11): differential detector anchors, the parser's
outlines, the lids and lip borders inside the solve, the solve's guards (sigma adaptation, cmax, the camera prior on
the whole move) and blockin.solve_step. The model tests need the workspace block-in tn_T00 (Tess's class-mean start
with fitted references) and are skipped without it.  uv run python -m pytest -q tests/test_refread.py"""
import json
import shutil

import numpy as np
import pytest

from hifipushie import assets, face_ruler as fr, store

try:
    assets.pack("gnm")
    HAVE = True
except Exception:  # noqa: BLE001
    HAVE = False
pytestmark = pytest.mark.skipif(not HAVE, reason="GNM asset pack not installed")
REF = "tn_T00"
need_ref = pytest.mark.skipif(not (store.HOME / REF / "human_refs.json").exists(), reason=f"workspace model {REF} not present")


def _step(seed=5, size=3.0):
    r = np.random.default_rng(seed).standard_normal(170)
    return size * r / np.linalg.norm(r)


def _agree(obs, dc, corr=0.8, share=0.6):
    o = np.array([ob["o"] for ob in obs])
    pred = np.array([ob["J"] for ob in obs]) @ dc
    assert np.corrcoef(o, pred)[0, 1] > corr
    assert np.sqrt(np.mean((o - pred) ** 2)) < share * np.sqrt(np.mean(o ** 2))


# ---- the solve's guards (synthetic observations) ------------------------------------------------------------------------

def _synthetic(c_true, n=400, noise=0.3, seed=1, typ="outline"):
    rng = np.random.default_rng(seed)
    J = rng.standard_normal((n, 170)) * 0.5
    o = J @ c_true + noise * rng.standard_normal(n)
    return [{"type": typ, "view": "front", "o": float(o[i]), "J": J[i], "sig": 0.3} for i in range(n)]


def test_adapt_raises_the_sigma_of_reads_the_head_cannot_explain():
    head = fr.gnm_head(np.zeros(170))
    c = _step(2, 4.0)
    obs = _synthetic(c, 400, 0.3) + _synthetic(c, 60, 3.0, seed=7, typ="lip")      # lips: ten times noisier than claimed
    plain, ad = fr.solve(obs, head), fr.solve(obs, head, adapt=True)
    assert ad["sig_scale"][("lip", "front")] > 3.0
    assert ad["sig_scale"][("outline", "front")] < 1.5
    assert np.linalg.norm(ad["dc"] - c) <= np.linalg.norm(plain["dc"] - c) + 1e-6


def test_cmax_keeps_every_component_within_reach():
    head = fr.gnm_head(np.zeros(170))
    c = np.zeros(170)
    c[40] = 6.0                                     # the reads insist on a 6 sd component
    obs = _synthetic(c, 300, 0.3)
    free, held = fr.solve(obs, head), fr.solve(obs, head, cmax=3.0)
    assert np.abs(free["dc"]).max() > 4.0
    assert np.abs(held["dc"]).max() <= 3.0 + 1e-9
    assert held["bound"] == [40] and held["relax"] == 1.0      # (solvecams) held AT the bound; no read down-weighted
    ok = fr.solve(_synthetic(_step(3, 4.0), 300, 0.3), head, cmax=3.0)
    assert ok["bound"] == []                        # nothing forced: nothing held


def test_camera_prior_is_on_the_whole_move():
    head = fr.gnm_head(np.zeros(170))
    cam = fr.camera("front")
    view = {"cam": cam, "kind": "front"}
    X = head["L"][30]
    p = fr._cam_points(cam, X[None])[1][0]
    ob = {"type": "landmark", "view": "front", "name": "lm30.x", "o": 0.0, "J": np.zeros(170), "sig": 5.0, "p": p.tolist(),
          "q": p.tolist(), "X": X.tolist()}
    sd = (2.0, 2.0, 5.0, 1.2)
    first = fr.solve([ob], head, cam_sd=sd, views=[view])
    again = fr.solve([ob], head, cam_sd=sd, views=[view], cam_done=[[4.0, 0.0, 0.0, 0.0]])
    assert abs(first["cam"][0]) < 0.2               # a camera at its start with nothing to read stays
    assert again["cam"][0] < -2.0                   # one that already moved 4 mm (2 sd) is drawn back, not left to walk


def test_plain_backdrop():
    from PIL import Image
    rng = np.random.default_rng(0)
    plain = np.full((200, 160, 3), 215, np.uint8)
    plain[60:, 50:110] = (180, 140, 120)            # a figure that leaves through the bottom edge
    busy = rng.integers(0, 255, (200, 160, 3)).astype(np.uint8)
    assert fr.plain_backdrop(Image.fromarray(plain)) > 0.95
    assert fr.plain_backdrop(Image.fromarray(busy)) < 0.3


# ---- on a block-in model with fitted references ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def tess():
    spec = store.load(REF)
    A = fr.model_head(spec)
    dc = _step()
    return A, A["rebuild"](A["c"] + dc), dc


@need_ref
def test_lid_obs_reads_a_known_lid_change(tess):
    from hifipushie import blockin_eyes as be, onemesh
    A, B, dc = tess
    ht = onemesh.head_template(B["spec"]["base"])
    mg = be.Reader(ht).margins(ht)
    rv = {"up": mg["up"], "lo": mg["lo"] + be.LO_BIAS, "outer": [mg["ring_out"][0] - be.OUT_RING, 0.0], "inner": mg["inner"]}
    obs = fr._lid_obs(A, {}, rv)
    assert len(obs) >= 12 and all(ob["type"] == "lid" and ob["view"] == "eye frame" for ob in obs)
    _agree(obs, dc)
    same = fr._lid_obs(B, {}, rv)                   # the head the read came from: nothing left to read
    assert np.abs([ob["o"] for ob in same]).max() < 0.05


@need_ref
def test_lip_obs_reads_a_known_border_change(tess):
    from hifipushie import base as basemod, blockin as bi, blockin_lips as bl
    A, B, dc = tess
    rj = bi._refs(REF)
    view = {"cam": rj["cameras"][bi._front(rj)], "kind": "front"}
    sk = np.flatnonzero(np.asarray(basemod._gnm_data()["skin"]))
    g2m = fr._gnm_to_model(B)
    ev = {}
    for nm, rows in zip(("upper", "lower"), bl.border_loops()):
        mv = [g2m[int(sk[r])] for r in np.asarray(rows) if int(sk[r]) in g2m]
        ev[nm] = fr._cam_points(view["cam"], np.asarray(B["V"], float)[mv])[1]
    obs = fr._lip_obs(A, view, ev)
    assert len(obs) >= 12 and {ob["name"].split("_")[1] for ob in obs} == {"upper", "lower"}
    _agree(obs, dc)
    assert np.abs([ob["o"] for ob in fr._lip_obs(B, view, ev)]).max() < 0.05


@need_ref
def test_anchors_are_differential_and_carry_the_chin_and_the_3q_irises(tess):
    A, B, dc = tess
    # (chinread: with a side view in the set the detector's chin points are left out by default; asked for, they are in)
    head, views, notes = fr.reference_views(REF, parse=False, chin={"chin_lm": "xy"})
    front, tq = views[0], views[1]
    oa = front["extra"](A, front)
    lm = [ob for ob in oa if ob["type"] == "landmark"]
    assert lm and all(ob.get("diff") for ob in lm)                          # the detector on picture AND render
    assert {"lm7.x", "lm8.y", "lm9.x"} <= {ob["name"] for ob in lm}       # the chin's three
    dflt = fr.reference_views(REF, parse=False)[1][0]
    assert not {"lm7.x", "lm8.y", "lm9.x"} & {ob["name"] for ob in dflt["extra"](A, dflt)}     # Tess's set has a side view
    ob_ = [ob for ob in front["extra"](B, front) if ob["type"] == "landmark"]
    d = np.array([a["o"] - b["o"] for a, b in zip(lm, ob_)])                # the render moved with the head
    pred = np.array([a["J"] for a in lm]) @ dc
    assert np.corrcoef(d, pred)[0, 1] > 0.6
    ir = [ob for ob in tq["extra"](A, tq) if ob["type"] == "iris"]
    assert len(ir) == 4 and all(ob.get("diff") for ob in ir)                # both irises of the turned view
    absolute = fr.reference_views(REF, parse=False, anchors="absolute")[1][0]
    assert not any(ob.get("diff") for ob in absolute["extra"](A, absolute))


@need_ref
def test_parser_outline_agrees_with_the_plain_reader_on_a_studio_photo():
    from hifipushie import faceparse
    if not faceparse.available():
        pytest.skip("asset pack faceparse / the detector venv not installed")
    head, plain, _ = fr.reference_views(REF, parse=False)
    _, parsed, notes = fr.reference_views(REF, parse=True)
    assert any("face parser" in n for n in notes)
    v0, v1 = dict(plain[1], limbus=False), dict(parsed[1], limbus=False)   # the 3/4 picture
    a = {tuple(np.round(ob["p"], 1)): ob["o"] for ob in fr.observe(head, [v0], colour=False) if ob["type"] == "outline"}
    b = [ob for ob in fr.observe(head, [v1], colour=False) if ob["type"] == "outline"]
    assert len(b) >= 50 and all(ob["sig"] == fr.PARSE_SIG for ob in b)
    d = np.array([ob["o"] - a[tuple(np.round(ob["p"], 1))] for ob in b if tuple(np.round(ob["p"], 1)) in a])
    assert len(d) >= 40 and abs(d.mean()) < 0.4 and d.std() < 0.6        # mm


@need_ref
def test_solve_step_is_not_forced_and_keeps_the_cameras_whole_move():
    from hifipushie import blockin as bi
    root, a, b = "_t_refread_r", "_t_refread_a", "_t_refread_b"
    try:
        for n in (root, a, b):
            shutil.rmtree(store.HOME / n, ignore_errors=True)
        bi.fork(REF, root)                           # (its own log: the reference model is never written)
        r1 = bi.solve_step(root, out=a)
        so = r1["solve"]
        assert so["n"]["outline"] >= 150 and so["n"]["lid"] >= 10 and so["n"]["lip"] >= 10 and so["n"]["landmark"] >= 40
        assert so["max_sd"] <= 3.0 + 1e-6 and 6.0 < so["c"] < 14.0
        rj = json.loads((store.HOME / a / "human_refs.json").read_text())
        done = np.asarray(rj["blockin"]["cam_done"], float)
        assert done.shape == (3, 7) and np.allclose(done, so["cameras"], atol=0.01)     # (solvecams: + distance)
        lim = 4.0 * np.array([fr.PHOTO_CAM_SD7[k] for k in ("front", "3q", "profile")])   # a prior now, no clip: a good set stays well inside it
        assert (np.abs(done) <= lim + 1e-6).all() and len(so["camera_lines"]) == 3
        r2 = bi.solve_step(a, out=b)
        s2 = r2["solve"]
        assert np.allclose(np.asarray(s2["cameras"]), done + np.asarray(s2["camera_step"]), atol=0.02)
        assert (np.abs(np.asarray(s2["cameras"])) <= lim + 1e-6).all()      # the WHOLE move stays near its prior
        assert s2["dc"] < so["dc"]                                           # the second call is the smaller step
    finally:
        for n in (root, a, b):
            shutil.rmtree(store.HOME / n, ignore_errors=True)
