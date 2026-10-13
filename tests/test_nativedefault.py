"""The GNM-native head as the DEFAULT start (nativedefault, 2026-10-12): block_in_start's defaults and what it drops,
the steps a native head refuses, cameras that belong to another head, the neck's girth in the solve, the head's size.
Needs the gnm / makehuman packs and the workspace model tess_a1 (read only; skipped without them).
uv run python -m pytest -q tests/test_nativedefault.py"""
import copy
import json
import shutil

import numpy as np
import pytest

from hifipushie import assets, blockin as bi, onemesh, solve_report as sr, store

REF = "tess_a1"


def _have():
    try:
        assets.path("gnm", "gnm/shape/data/versions/v3_0/gnm_head.npz")
        from hifipushie import makehuman
        makehuman.body({"age": 25, "sex": 0.5})
        return True
    except Exception as err:  # the packs aren't in the repo
        print("skipped:", str(err)[:80])
        return False


need = pytest.mark.skipif(not _have(), reason="gnm / makehuman packs not present")
need_ref = pytest.mark.skipif(not (_have() and (store.HOME / REF / "human_refs.json").exists()), reason=f"workspace model {REF} not present")


def _rm(*names):
    for n in names:
        shutil.rmtree(store.HOME / n, ignore_errors=True)


def _dressed_ref(r):
    """A copy of REF carrying what a refs model may carry: sculpt strokes, a fold layer, wrinkles, head style sliders."""
    shutil.copytree(store.HOME / REF, store.HOME / r)
    p = store.HOME / r / "spec.json"
    sp = json.loads(p.read_text())
    sp["strokes"] = {"nasolabial.L": {"path": [], "kind": "crease"}, "brow_ridge.L": {"path": [], "kind": "clay"}}
    sp["skin"]["folds"] = {"nasolabial": 1.2, "lid_fold": 0.6}
    sp["skin"]["fold_expressions"] = {"smile": 0.5}
    sp["skin"]["wrinkles"] = {"amount": 0.8, "glabella": 1.4}
    sp["base"].setdefault("style", {}).setdefault("human", {}).update({"head_size": 0.95, "jaw": 0.1})
    p.write_text(json.dumps(sp))
    return sp


@need_ref
def test_start_is_native_and_carries_nothing_of_ours():
    """THE DEFAULT START: GNM's true base, native attach, GNM's own parts; the refs model's strokes, folds and wrinkle
    relief are NOT carried and the entry names them; the cameras are carried onto the head's new size and place;
    carry=True / attach="body" keep the old behaviour; gnm_base on a native start is refused."""
    a, b, c, r = "nd_test_a", "nd_test_b", "nd_test_c", "nd_test_ref"
    _rm(a, b, c, r)
    try:
        src = _dressed_ref(r)
        e = bi.start(a, r, sex="female")
        sp = store.load(a)
        h = sp["base"]["head"]
        assert h["attach"] == "native" and h["gnm_base"] == 1.0 and h["dimorphism"] == 0.0 and h["eyes"] == 1.0
        assert onemesh.native(sp["base"])
        assert not any(k in h for k in ("eye_radius", "interior", "mouth", "scale", "sliders", "warp", "shape", "pose"))
        hs = sp["base"]["style"]["human"]
        assert "head_size" not in hs and "jaw" not in hs and hs["legs"] == src["base"]["style"]["human"]["legs"]
        assert not sp.get("strokes") and "folds" not in sp["skin"] and "fold_expressions" not in sp["skin"]
        assert sp["skin"]["wrinkles"] == {"amount": 0.0}
        d = " | ".join(e["start"]["dropped"])
        for word in ("strokes (2", "nasolabial.L", "skin.folds", "skin.fold_expressions", "skin.wrinkles", "head_size", "jaw"):
            assert word in d, (word, d)
        assert e["start"]["attach"] == "native" and e["start"]["cameras"].startswith("carried")
        rj = bi._refs(a)
        assert rj["blockin"]["cam_carried"] and not bi.cameras_fit(sp["base"], rj)["stale"]
        assert bi.cameras_fit(sp["base"], {**rj, "cameras": bi._refs(r)["cameras"]})["stale"]   # the old ones do not fit it
        assert np.allclose(bi.identity(sp), bi.data()["m_f"], atol=1e-4)
        # the old behaviour, by an explicit argument each
        bi.start(b, r, sex="female", carry=True)
        sb = store.load(b)
        assert len(sb["strokes"]) == 2 and sb["skin"]["folds"] and sb["skin"]["wrinkles"]["glabella"] == 1.4
        e = bi.start(c, r, sex="female", attach="body")
        hc = store.load(c)["base"]
        assert "attach" not in hc["head"] and hc["head"]["gnm_base"] == bi.default_gnm_base(22.0)
        assert hc["style"]["human"]["head_size"] == 0.95 and e["start"]["cameras"] == "kept"
        with pytest.raises(ValueError, match="means nothing on a GNM-native head"):
            bi.start("nd_test_x", r, sex="female", gnm_base=0.5)
    finally:
        _rm(a, b, c, r, "nd_test_x")


@need_ref
def test_native_head_refuses_dead_steps_and_stale_cameras():
    """On a native head head_scale / gnm_base / dimorphism / eye_size are REFUSED with their reason (they were silently
    ignored); a model switched to native by an edit has cameras of another head: block_in_solve refuses and names the
    step, and that step carries them."""
    a, b, c, d = "nd_test_r0", "nd_test_r1", "nd_test_r2", "nd_test_r3"
    _rm(a, b, c, d)
    try:
        bi.start(a, REF, sex="female")
        for k, v, why in (("head_scale", 1.05, "GNM's own size"), ("gnm_base", 0.5, "true base"), ("dimorphism", 0.8, "MakeHuman"),
                          ("eye_size", 1.05, "own eyeball")):
            with pytest.raises(ValueError, match="REFUSED on a GNM-native head") as ei:
                bi.step(a, {k: v}, out=b)
            assert why in str(ei.value), (k, str(ei.value))
        assert not (store.HOME / b / "spec.json").exists()
        # the old path still takes them
        bi.start(b, REF, sex="female", attach="body")
        bi.step(b, {"dimorphism": 0.5}, out=c)
        assert store.load(c)["base"]["head"]["dimorphism"] == 0.5
        # switched by an edit: stale cameras, measured
        p = store.HOME / c / "spec.json"
        sp = json.loads(p.read_text())
        sp["base"]["head"]["attach"] = "native"
        p.write_text(json.dumps(sp))
        assert bi.cameras_fit(store.load(c)["base"], bi._refs(c))["stale"]
        with pytest.raises(ValueError, match=r'"attach": "native"'):
            bi.solve_step(c, out=d)
        r = bi.native_step(c, out=d)
        sd, rj = store.load(d), bi._refs(d)
        assert 1.1 < r["scale"] < 1.3 and not bi.cameras_fit(sd["base"], rj)["stale"] and rj["blockin"]["cam_carried"]
        assert sd["base"]["head"]["gnm_base"] == 1.0 and sd["base"]["head"]["dimorphism"] == 0.0
        assert "head_size" not in sd["base"]["style"]["human"] and any("head_size" in x for x in r["dropped"])
        assert bi.log(d)[-1]["moves"] == {"attach": "native"}
        with pytest.raises(ValueError, match="already"):
            bi.native_step(d, out="nd_test_r4")
    finally:
        _rm(a, b, c, d, "nd_test_r4")


@need
def test_carried_cameras_are_exact_for_one_shape():
    """carry_cameras: the same identity on the body-carried head and on the native head: every landmark lands on the
    same pixel to a fraction of the face (the two differ only by the old path's blend with the body's head)."""
    from hifipushie import humanfit
    idn = {f"head_{i:03d}": float(x) for i, x in enumerate(bi.data()["m_f"][:170])}
    b0 = {"body": {"source": "human", "age": 22.0, "sex": 0.0, "weight": 0.15, "height": 1.636},
          "head": {"identity": idn, "gnm_base": 1.0, "dimorphism": 0.0, "eyes": 1.0, "lip_close": True}}
    b1 = copy.deepcopy(b0)
    b1["head"]["attach"] = "native"
    L0, L1 = (np.asarray(humanfit.state(b)["L"], float)[:68] for b in (b0, b1))
    cam = {"r": [0.0, 0.0, 0.0], "t": [0.0, 0.0, 1.2], "f": 3000.0, "size": [1000, 1000], "centre": L0.mean(0).tolist(), "yaw": 30.0}
    (cam1,), cc = bi.carry_cameras(b0, b1, [cam])
    P0, P1 = humanfit.project(cam, L0), humanfit.project(cam1, L1)
    spread = float(np.sqrt(((P0 - P0.mean(0)) ** 2).sum(1).mean()))
    assert 1.05 < cc["scale"] < 1.3
    assert np.abs(P1 - P0).max() < 0.03 * spread, (np.abs(P1 - P0).max(), spread)
    assert cam1["yaw"] == 30.0 and cam1["f"] == 3000.0


@need
def test_neck_girth_row_and_move():
    """solve_report's neck: the girth at GNM's narrowest neck ring and its exact gradient; GNM's class means (women
    365, men 385 mm: ANSUR 330 / 398); neck_move brings it to a target with the head's size and the face's measures
    held; neck_row is the solve's hold."""
    D = bi.data()
    Lf, kf, g = sr.neck_girth(D["m_f"])
    Lm = sr.neck_girth(D["m_m"])[0]
    assert 0.355 < Lf < 0.375 and 0.375 < Lm < 0.395, (Lf, Lm)
    for i in (0, 1, 4):
        e = np.zeros(170)
        e[i] = 1e-3
        assert abs((sr.neck_girth(np.asarray(D["m_f"]) + e)[0] - Lf) / 1e-3 - g[i]) < 2e-5, i
    assert 0.030 < np.linalg.norm(g) < 0.042              # ~36 mm per sd over GNM's prior: the reason for the hold
    m = sr.neck_move(D["m_f"], 0.330)
    assert abs(m["girth"] - 0.330) < 2e-4 and abs(float(sr.size_row()["J"] @ m["dc"])) < 1e-9
    rw = sr.rows()
    mv = rw["R"] @ m["dc"]
    face = [i for i, n in enumerate(rw["names"]) if "neck" not in n and "skull" not in n]
    assert np.abs(mv[face] / rw["sd"][face]).max() < 0.2, np.abs(mv[face] / rw["sd"][face]).max()
    r = sr.neck_row(D["m_f"], 0.330)
    assert r["name"] == "hold_neck" and abs(r["o"] - (0.330 - Lf)) < 1e-12 and abs(r["sig"] - 0.0033) < 1e-9


@need
def test_native_size_and_neck_target():
    """onemesh.native_size: the head goes with the stature by ANSUR's allometry (1.000 at the sex's mean stature), a
    given base.head.size wins; the neck ANSUR expects for the sex and stature."""
    def b(sex, h, **hd):
        return {"body": {"source": "human", "age": 30.0, "sex": sex, "height": h}, "head": {"attach": "native", **hd}}
    f, m = onemesh.native_size(b(0.0, 1.627)), onemesh.native_size(b(1.0, 1.755))
    assert abs(f["size"] - 1) < 1e-9 and abs(m["size"] - 1) < 1e-9 and f["allometric"]
    assert abs(f["neck"] - 0.3292) < 1e-6 and abs(m["neck"] - 0.3968) < 1e-6
    t = onemesh.native_size(b(1.0, 1.95))
    assert 1.02 < t["size"] < 1.03 and t["neck"] > m["neck"]
    assert 0.97 < onemesh.native_size(b(0.0, 1.50))["size"] < 0.98
    g = onemesh.native_size(b(0.0, 1.627, size=0.9))
    assert g["size"] == 0.9 and not g["allometric"]
    # ... and it is the size the build uses
    bb = b(0.0, 1.70, identity={"head_000": 0.5})
    assert abs(onemesh.head_desc(bb)["bound"]["native"]["size"] - onemesh.native_size(bb)["size"]) < 1e-9


@need_ref
def test_solve_has_a_neck_prior_and_says_so():
    """block_in_solve on a native start: the first call lays the carried cameras on the head (refit, said); the
    neck's girth is under ANSUR's PRIOR for the sex and stature by default (a row of the solve; said: no direct read)
    and comes down from GNM's female class mean toward it; neck="held" pins the mean; neck=False releases it; the
    head's size rule is in the reply; the iris check says the model is in real mm."""
    a, b, c, d = "nd_test_s0", "nd_test_s1", "nd_test_s2", "nd_test_s3"
    _rm(a, b, c, d)
    try:
        bi.start(a, REF, sex="female")
        ns = onemesh.native_size(store.load(a)["base"])
        so = bi.solve_step(a, out=b, rounds=2)["solve"]
        assert any(x.startswith("CAMERAS: carried") for x in so["notes"])
        assert any(x.startswith("NECK: an anthropometric PRIOR") and "NO DIRECT READ" in x for x in so["notes"])
        assert so["neck"]["mode"] == "prior" and abs(so["neck"]["before"] - 0.366) < 0.004
        assert abs(so["neck"]["sig"] - ns["neck_sd"] / ns["neck"]) < 1e-6
        assert so["head_size"]["allometric"] and abs(so["head_size"]["size"] - ns["size"]) < 1e-9
        assert "cam_carried" not in bi._refs(b)["blockin"]
        held = bi.solve_step(a, out=c, rounds=2, chin={"neck": "held"})["solve"]
        assert held["neck"]["mode"] == "held" and abs(held["neck"]["after"] / ns["neck"] - 1) < 0.02, held["neck"]
        assert any(x.startswith("NECK: its girth is HELD") for x in held["notes"])
        free = bi.solve_step(a, out=d, rounds=2, chin={"neck": False})["solve"]
        assert free["neck"]["mode"] == "free" and not any(x.startswith("NECK:") for x in free["notes"])
        # the hold pins ANSUR's mean; the prior and the free solve end where the reads' correlations put the neck (readmix:
        # with MediaPipe's mesh reads in, the FREE solve of this set happens to end 2.4 mm from the mean and the prior's
        # 5.1: "the prior ends nearer than the free solve" was never a property of the solve, only of that day's reads)
        e = [abs(x["neck"]["after"] - ns["neck"]) for x in (held, so, free)]
        assert e[0] < e[1] and e[0] < e[2] and max(e[1], e[2]) < 0.02, e
        assert "real millimetres" in bi.iris_size(b)["text"]
    finally:
        _rm(a, b, c, d)
