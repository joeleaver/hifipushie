"""The artist block-in (blockin.py, the block_in_* tools): registration at the eyes, held / free steps, the target
table on a known model, the step log, the tools through server.* (the running MCP has old code).
Needs the workspace model fs_ge3 (Garrett, fitted references) for the model tests; they are skipped without it.
uv run python -m pytest -q tests/test_blockin.py"""
import json
import shutil

import numpy as np
import pytest

from hifipushie import blockin as bi, humanmacro as hm, store

REF = "fs_ge3"
has_ref = (store.HOME / REF / "human_refs.json").exists()
need_ref = pytest.mark.skipif(not has_ref, reason=f"workspace model {REF} not present")


def _rm(*names):
    for n in names:
        shutil.rmtree(store.HOME / n, ignore_errors=True)


def test_held_step_holds_the_other_macros():
    d = bi.direction("chin_height!")
    r0, r1 = hm.read(np.zeros(hm.K)), hm.read(d[:hm.K])
    assert abs((r1["chin_height"] - r0["chin_height"]) - 1.0) < 0.05
    # face_length = nose + philtrum + lips + chin by definition: a taller chin makes the face longer, nothing else moves
    assert hm.released("chin_height") == ["face_length"]
    others = [abs(r1[k] - r0[k]) for k in hm.NAMES if k not in ("chin_height", "face_length")]
    assert max(others) < 0.1, max(others)
    assert set(hm.released("face_length")) >= {"chin_height", "nose_length", "philtrum"}
    assert hm.released("eye_spacing") == []


def test_free_step_moves_its_couplings():
    d = bi.direction("face_length")
    r0, r1 = hm.read(np.zeros(hm.K)), hm.read(d[:hm.K])
    assert abs((r1["face_length"] - r0["face_length"]) - 1.0) < 0.1
    moved = sorted((abs(r1[k] - r0[k]), k) for k in hm.NAMES if k != "face_length")
    assert moved[-1][0] > 0.2, moved[-3:]   # the population moves neighbours with it (philtrum, chin ...)
    # ... but not the head's size (the interocular distance): that is head_scale's job; `~` is the raw coupling
    for n in ("cheek_fullness", "face_length", "nd:orbital_rim"):
        assert abs(hm.read(bi.direction(n)[:hm.K])["head_size"] - r0["head_size"]) < 0.05, n
    raw = hm.read(bi.direction("cheek_fullness~")[:hm.K])
    assert abs(raw["head_size"] - r0["head_size"]) > 0.1


def test_vocabulary():
    for n in ("sex", "eth0", "nd:radix_width", "radix_width", "nd:orbital_rim|hold_brow_ridge_eye_depth"):
        assert np.linalg.norm(bi.direction(n)) > 0, n
    D = bi.data()
    assert np.allclose(bi.direction("sex"), D["m_m"] - D["m_f"])
    with pytest.raises(ValueError, match="Vocabulary"):
        bi.direction("nose_size_please")
    assert bi.default_gnm_base(20) == 0.5 and bi.default_gnm_base(60) == 0.0 and 0.2 < bi.default_gnm_base(37.5) < 0.3


def test_registration_lands_eyes_on_eyes():
    """The anchor on a picture whose detector points ARE the model's projected eye corners + nasion: zero shift; a
    picture moved by (7, -3) px: that shift."""
    Lm = np.random.default_rng(1).uniform(100, 400, (70, 2))
    P = np.zeros((478, 2))
    for i, j in zip([33, 133, 263, 362, 168], [36, 39, 45, 42, 27]):
        P[i] = Lm[j]
    a, b = bi._eye_anchor({"yaw": 0}, P, Lm)
    assert np.allclose(a - b, 0)
    a, b = bi._eye_anchor({"yaw": 0}, P + [7, -3], Lm)
    assert np.allclose(a - b, [7, -3])


@need_ref
def test_start_step_table_log_and_registration():
    a, b, c = "bi_test_00", "bi_test_01", "bi_test_02"
    _rm(a, b, c)
    try:
        e = bi.start(a, REF, sex="male")
        sp = store.load(a)
        h = sp["base"]["head"]
        assert not any(k in h for k in ("sliders", "warp", "fold", "pose", "shape"))
        assert np.allclose(bi.identity(sp), bi.data()["m_m"], atol=1e-4)
        assert h["gnm_base"] == bi.default_gnm_base(sp["base"]["body"]["age"])
        assert h["eye_radius"] == 0.012   # every new human: an adult eyeball
        assert e["start"]["cameras"] == "kept"
        with pytest.raises(ValueError, match="exists"):
            bi.start(a, REF, sex="male")
        # the table on a known model: the picture's reads don't depend on the head (Garrett's concept: pupils ~65.9 mm)
        t = bi.table(a)
        pd = next(r for r in t["eye placement"] if r["id"] == "pupil_distance")
        assert abs(pd["photo"] - 65.9) < 1.0, pd
        assert all("flag" in r for g in t.values() for r in g if r["id"] == "jaw_angle_height")
        assert "brow_eye" not in json.dumps(t)
        assert bi.passes(t)["eye placement"].endswith("/3")
        # registration on the real sheet: the eyes land within a few pixels
        r = bi.look(a, str(store.HOME / a / "look.png"), views=[0])
        assert np.hypot(*r["views"][0]["shift_px"]) < 6, r
        # a held step moves its macro by its amount; the log names it; a step from the start again marks a revert
        rep = bi.step(a, {"chin_height!": 0.5, "head_scale": 1.15}, seen="chin short", why="test")
        assert rep["entry"]["to"] == b and abs(rep["entry"]["read"]["chin_height"][1] - rep["entry"]["read"]["chin_height"][0] - 0.5) < 0.05
        assert store.load(b)["base"]["style"]["human"]["head_size"] == 1.15
        pd1 = next(r for r in bi.table(b)["eye placement"] if r["id"] == "pupil_distance")
        assert pd1["model"] > pd["model"] * 1.1, (pd, pd1)   # head_scale really scales the one mesh's head
        assert "chin short" in json.dumps(bi.log(b))
        r2 = bi.step(a, {"jaw_width": 0.3, "shape:age_nasolabial": 0.5, "shape:lips_thin": 0.2}, out=c)
        hc = store.load(c)["base"]["head"]
        assert hc["sliders"]["age_nasolabial"] == 0.5 and hc["shape"]["lips_thin"] == 0.2
        assert "DESIGNED" in bi.step_text(r2) and r2["entry"]["designed"] == ["shape:age_nasolabial", "shape:lips_thin"]
        with pytest.raises(ValueError, match="shape: one of"):
            bi.step(a, {"shape:nose_width": 1}, out="bi_test_never")
        lg = bi.log(c)
        assert [x["to"] for x in lg] == [a, b, c] and "reverted" in lg[1]
        assert "items that changed" in bi.step_text(rep) or rep["delta"] == []
        lr = bi.lid_read(a)
        assert set(lr["model"]) == {"L", "R"} and 0 < lr["model"]["L"]["upper"] < 2
    finally:
        _rm(a, b, c)


@need_ref
def test_brows_seated_and_focus():
    """The brows are painted ON the surface (only on the clay's skin pixels, in a turned view too); the focus sheet
    registers at the feature's own landmarks; a zoom-out read is logged on the step that made the model."""
    from hifipushie import humanfit, likeness
    a, b = "bi_test_f0", "bi_test_f1"
    _rm(a, b)
    try:
        bi.start(a, REF, sex="male")
        rj = bi._refs(a)
        mesh = bi.presented_mesh(store.load(a)["base"])
        assert bi.brow_source(mesh, rj) is not None
        for vi in range(len(rj["views"])):
            cam = rj["cameras"][vi]
            L2 = humanfit.project(cam, mesh["state"]["L"])
            c, s = 0.5 * (L2.min(0) + L2.max(0)), 1.4 * float(np.max(L2.max(0) - L2.min(0)))
            box = (c[0] - s / 2, c[1] - s / 2, c[0] + s / 2, c[1] + s / 2)
            im, k, ps = likeness.render(mesh, cam, box, px=500, brows=False, passes=True)
            out = np.asarray(bi.seat_brows(im, ps, cam, box, k, bi.brow_source(mesh, rj)), float)
            changed = np.abs(out - np.asarray(im.convert("RGB"), float)).sum(-1) > 1
            assert changed.sum() > 50, vi
            assert (ps["part"][changed] == 0).all(), vi   # never past the silhouette, never on the eyes
        r = bi.focus(a, "nose", str(store.HOME / a / "f.png"), views=[0])
        assert r["views"][0]["registered"] == "the feature's own landmarks"
        assert any(x["id"] == "alar_width" for x in bi.feature_table(a, "nose")["nose"])
        bi.step(a, {"nose_width!": -0.3}, out=b, seen="tip wide", feature="nose")
        e = bi.note(b, "whole face unchanged, nose narrower", keep=True)
        assert e["kept"] and e["feature"] == "nose" and len(e["feature_passes"]) == 2
    finally:
        _rm(a, b)


@need_ref
def test_tools_through_server():
    from hifipushie import server
    a = "bi_test_s0"
    _rm(a, "bi_test_s1")
    try:
        out = server.block_in_start(a, REF, sex="male", save=str(store.HOME / a / "s.png"))
        assert len(out) == 2 and "started" in out[1] and "== head shape" in out[1]
        txt = server.block_in_step(a, {"jaw_width": 0.3}, out="bi_test_s1", look=False)
        assert "bi_test_s1" in txt and "targets before -> after" in txt
        assert "lid margins" in server.lid_read(a)
        assert server.guide("block_in_step").startswith("### `block_in_step`")
        assert "artist block-in" in server.guide("block_in") and "ZOOM IN" in server.guide("block_in")
        assert len(server.block_in_look(a, focus="eyes", views=[0], save=str(store.HOME / a / "e.png"))) == 2
    finally:
        _rm(a, "bi_test_s1")


@need_ref
def test_fixed_eyeball_radius():
    """head.eye_radius (blockin2): an absolute eyeball, not GNM's 14.6 mm eye x the head's scale; head_scale doesn't
    change it, eye size does; the ball still rests under the lid rims; without the key nothing changes."""
    import copy
    from hifipushie import humanfit
    b0 = store.load(REF)["base"]
    r0 = float(humanfit.state(b0)["head"]["eye_r"])
    assert r0 > 0.0135   # Garrett's body-scaled GNM eye (14.6 mm)
    for hs, ke, want in ((1.0, 1.0, 0.012), (1.1, 1.0, 0.012), (1.0, 1.05, 0.0126)):
        b = copy.deepcopy(b0)
        b["head"]["eye_radius"] = 0.012
        b["head"]["eyes"] = ke
        b.setdefault("style", {}).setdefault("human", {})["head_size"] = hs
        h = humanfit.state(b)["head"]
        assert abs(float(h["eye_r"]) - want) < 1e-6, (hs, ke, h["eye_r"])
        L = np.asarray(h["lm68"], float)
        for e in h["eyes"]:   # seated: every rim landmark just outside the ball, the nearest at the seat clearance
            rim = L[42:48] if e[0] > 0 else L[36:42]
            d = np.linalg.norm(rim - np.asarray(e), axis=1).min() - float(h["eye_r"])
            assert 0.0007 < d < 0.0010, d


def test_new_human_eye_radius():
    from hifipushie import humans
    assert humans.eye_radius(40) == 0.012 and 0.0083 < humans.eye_radius(0) < 0.0085
    assert humans.spec(age=30, sex=1, source="human")["base"]["head"]["eye_radius"] == 0.012
    assert "eye_radius" not in humans.spec(age=30, sex=1)["base"]["head"]   # the grafted head: unchanged


def test_region_pcs():
    """pc:<GNM region><i>: GNM's own principal directions of a region (nose PC0 = a higher, projecting bridge)."""
    V = bi.region_pcs("nose_region")
    assert V.shape == (8, 170) and np.allclose(V @ V.T, np.eye(8), atol=1e-6)
    r0, r1 = bi._macro_read(np.zeros(170)), bi._macro_read(bi.direction("pc:nose_region0"))
    assert r1["bridge_height"] - r0["bridge_height"] > 0.5 and r1["nose_projection"] - r0["nose_projection"] > 0.5
    assert abs(r1["head_size"] - r0["head_size"]) < 0.02   # size kept
    with pytest.raises(ValueError, match="no GNM region"):
        bi.direction("pc:elbow0")


@need_ref
def test_eye_readers():
    """blockin_eyes.Reader on the shipped head: lid margins near the render-based lid_read, a crease profile read; the
    solve's expression keys are GNM's eye-region pairs."""
    from hifipushie import blockin_eyes as be, onemesh
    b = store.load(REF)["base"]
    ht = onemesh.head_template(b)
    q = be.Reader(ht).read(ht)
    assert -1 < q["up"] < 2 and 0 < q["lo"] < 2 and np.isfinite(q["hsoft"]) and q["r_iris_mm"] > 5   # (fs_ge3: its lid pose puts the upper lid past the pole)
    Ln, Rn, names = be._names()
    assert Ln[0] in names and Rn[0] in names and len(Ln) == be.NE
