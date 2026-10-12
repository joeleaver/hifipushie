"""skin_read / skin_folds on synthetic input (`uv run python tests/test_skin_read.py`; no Blender): the hand-made head
of test_skin stands in for a base body; the "picture's albedo" is our own albedo model run with other parameters."""
import copy
import pathlib
import tempfile

import numpy as np

from hifipushie import paint, skin, skin_folds as sf, skin_marks as mk, skin_read as sr, store
from hifipushie.spec import SpecError
from test_skin import head_spec


def _tmp(fn):
    def run():
        with tempfile.TemporaryDirectory() as d:
            home, store.HOME = store.HOME, pathlib.Path(d)
            mk._MESH.clear()
            sf._SURF.clear()
            skin._LAYERS.clear()
            try:
                fn()
            finally:
                store.HOME = home
    run.__name__ = fn.__name__
    return run


def test_valley_lab_and_specks():
    u = np.arange(-9, 9.01, 0.25)
    flat = 0.01 * u                                           # a slope: no valley
    assert sr._valley(flat, u, 5.0, 4.0)[0] == 0.0
    v = flat - 0.1 * np.exp(-0.5 * ((u - 1.5) / 1.0) ** 2)
    d, at = sr._valley(v, u, 5.0, 4.0)
    assert 0.07 < d < 0.11 and abs(at - 1.5) < 0.3, (d, at)
    edge = flat - 0.1 * np.exp(-0.5 * ((u - 6.0) / 1.0) ** 2)   # a valley beside the search window: not this fold's
    assert sr._valley(edge, u, 5.0, 4.0)[0] == 0.0
    lin = np.array([[0.5, 0.3, 0.2], [0.1, 0.05, 0.04]])
    assert np.allclose(sr._lab_scale(sr.lab(lin), 0.6), sr.lab(lin * 0.6), atol=1e-6)
    # dark specks per cm2: 40 dots of 1 mm on 4 cm x 4 cm of 0.25 mm pixels
    rng = np.random.default_rng(0)
    img = np.full((160, 160), 0.5)
    yy, xx = np.mgrid[:160, :160]
    for cx, cy in rng.uniform(12, 148, (40, 2)):
        img = img * (1 - 0.25 * np.exp(-0.5 * (((xx - cx) ** 2 + (yy - cy) ** 2) / 2.0 ** 2)))
    where = np.ones((160, 160), bool)
    n = sr._specks(img, where, 0.25)
    assert 1.5 < n < 4.5, n                                   # 40 on ~13 cm2 of eroded area, a few merged
    assert sr._specks(np.full((160, 160), 0.5), where, 0.25) == 0.0


def test_get_set_and_fold_options():
    sk = {"tone": {"fitzpatrick": 2}, "features": {"flush": {"amount": 0.3, "where": ["cheek"]}}}
    assert abs(sr._get(sk, "tone.melanin") - 0.14) < 1e-9 and sr._get(sk, "features.flush") == 0.3
    assert sr._get(sk, "zones.periorbital") == 0.0 and sr._get(sk, "zones.perioral_red") == 1.0 and sr._get(sk, "lips.lower.blood") == 1.0
    s2 = copy.deepcopy(sk)
    sr._set(s2, "features.flush", 0.6); sr._set(s2, "lips.lower.melanin", 1.4); sr._set(s2, "zones.nose_red", 2.0)
    assert s2["features"]["flush"] == {"amount": 0.6, "where": ["cheek"]} and s2["lips"]["lower"]["melanin"] == 1.4
    sr._unset(s2, sk, "lips.lower.melanin"); sr._unset(s2, sk, "zones.nose_red")
    assert "lips" not in s2 and "zones" not in s2
    skin.params({"skin": {"lips": {"lower": {"blood": 1.5}}, "zones": {"perioral_red": 0.5, "periorbital": 1.0}}})
    o = sf.options({"nasolabial": 0.8, "tear_trough": {"amount": 1.0, "L": {"shift": [1, 2, 1], "extent": [0.1, 0.8]}}, "lid_fold": 0})
    assert set(o) == {"nasolabial", "tear_trough"} and o["tear_trough"]["sides"][".L"]["extent"] == [0.1, 0.8]
    assert o["tear_trough"]["sides"][".R"]["shift"] == [] and o["nasolabial"]["width"] == sf.FOLDS["nasolabial"]["width"]
    for bad in ({"nose": 1}, {"nasolabial": {"deep": 1}}, {"nasolabial": {"roll": 5}}, {"nasolabial": {"L": {"extent": [0.8, 0.2]}}}, {"nasolabial": 3}):
        try:
            sf.options(bad)
            assert False, bad
        except SpecError:
            pass
    assert sf.sided("nasolabial") and not sf.sided("mentolabial")


@_tmp
def test_beard_zones_partition_and_weights():
    spec = head_spec(hair={"stubble": {"style": "short"}})
    J = skin._joints(spec)
    V, N, _ = mk.head_mesh(spec, "body", J)
    V, N = V.astype(float), N.astype(float)
    z = mk.beard_zones(J)(V)
    assert set(z) == set(mk.BEARD_ZONES) and np.allclose(sum(z.values()), 1.0, atol=1e-9) and all((v >= -1e-12).all() for v in z.values())
    from hifipushie.skin_features import stubble_options
    full = mk.beard_density(J, stubble_options({"amount": 1.0, "style": "short"}))(V, N)
    goat = mk.beard_density(J, stubble_options({"amount": 1.0, "style": "short", "zones": {"cheeks": 0.0, "jaw": 0.0, "neck": 0.0}}))(V, N)
    ch, ck = z["chin"] > 0.8, (z["cheeks"] > 0.8) & (full > 0.2)
    assert ck.sum() > 20 and goat[ck].mean() < 0.3 * full[ck].mean(), (ck.sum(), full[ck].mean(), goat[ck].mean())
    assert (goat[ch] >= 0.79 * full[ch] - 1e-9).all() and (goat <= full + 1e-9).all(), "the chin keeps its beard"
    assert "zones" not in stubble_options({"amount": 1.0, "zones": {"chin": 1.0}}), "all-ones weights leave the map's key alone"


@_tmp
def test_fold_map_and_layers():
    spec = head_spec(age=30, folds={"nasolabial": {"amount": 1.0, "L": {"shift": [3.0] * 5}}, "tear_trough": 0.8})
    J = skin._joints(spec)
    ps0 = sf.paths(spec, "body", J, None, names=["nasolabial"])
    ps1 = sf.paths(spec, "body", J, sf.options(spec["skin"]["folds"]), names=["nasolabial"])
    q0, q1 = ps0[("nasolabial", ".L")], ps1[("nasolabial", ".L")]
    moved = ((q1["P"] - q0["P"]) * q0["across"]).sum(1) * 1000
    assert 2.0 < np.median(moved) < 4.0, np.median(moved)        # 3 mm toward the fold's plus side, on the skin
    assert np.abs(((ps1[("nasolabial", ".R")]["P"] - ps0[("nasolabial", ".R")]["P"]) * 1000)).max() < 0.5, "the right side stays on its landmarks"
    assert float((q0["across"] @ np.array([1.0, 0, 0.3])).mean()) > 0, "plus is out toward the cheek"
    L = paint.layers(spec)
    assert "skin:folds_shade" in L and "skin:folds_groove" not in L, "relief as geometry: the map carries the colour only"
    spec["skin"]["fold_relief"] = "paint"
    L = paint.layers(spec)
    assert {"skin:folds_shade", "skin:folds_groove", "skin:folds_roll"} <= set(L)
    assert L["skin:folds_groove"]["height"] < 0 < L["skin:folds_roll"]["height"] and L["skin:folds_shade"]["mix"] == "multiply"
    from PIL import Image
    a = np.asarray(Image.open(L["skin:folds_groove"]["mask"][0]["image"]["file"]).convert("RGB"), float) / 255
    assert a[..., 0].max() > 0.4 and a[..., 1].max() > 0.2 and a[..., 2].max() > 0.15 and (a[..., 0] > 0.05).mean() < 0.05, (a[..., 0].max(), a[..., 1].max(), a[..., 2].max(), (a[..., 0] > 0.05).mean())
    assert "skin:folds_groove" not in paint.layers(head_spec(age=30)), "no folds, no layers (the default skin is unchanged)"


@_tmp
def test_folds_are_geometry():
    """skin.folds reshape the FIELD (skinfolds): a groove and a roll where asked, nothing elsewhere, nothing at amount
    0, the build key untouched without folds, the displacement off the lid margins and clear of the eyeball."""
    from hifipushie import images, sdf
    from hifipushie.spec import compile_prims, geometry
    plain = head_spec(age=30)
    assert "tissue" not in geometry(plain) and "tissue" not in geometry(head_spec(age=30, folds={"nasolabial": 0}))
    assert "tissue" not in geometry(head_spec(age=30, folds={"nasolabial": 1.0}, fold_relief="paint"))
    assert not [p for p in compile_prims(plain) if p.kind == "tissue"], "no folds: no primitive, no cost"
    spec = head_spec(age=30, folds={"nasolabial": {"amount": 1.0, "R": {"amount": 0.0}}, "tear_trough": 1.0, "lid_fold": 1.0})
    assert geometry(spec)["tissue"]["folds"].keys() == {"nasolabial", "tear_trough", "lid_fold"}
    prims = compile_prims(spec)
    tis = {p.name for p in prims if p.kind == "tissue"}
    assert tis == {"fold_nasolabial.L", "fold_tear_trough.L", "fold_tear_trough.R", "fold_lid_fold.L", "fold_lid_fold.R"}, tis
    J = skin._joints(spec)
    S = sf.surface(spec, "body", J)
    body = [p for p in prims if p.part == "body"]
    ps = sf.paths(spec, "body", J, sf.options(spec["skin"]["folds"]))
    def move(name, sd, u_mm):          # the skin's move along its normal (mm, + out) at u mm across the path's middle
        q = ps[(name, sd)]
        i = len(q["P"]) // 2
        X = S.seat(q["P"][i] + 0.001 * np.asarray(u_mm, float)[:, None] * q["across"][i])
        return -sdf.field_at(body, X) * 1000
    n = move("nasolabial", ".L", [-9, 0, 5, 14])
    assert abs(n[0]) < 0.05 and abs(n[3]) < 0.1, n                       # local
    assert -0.5 < n[1] < -0.25 and 0.9 < n[2] < 1.5, n                 # the groove, the cheek's pad beside it
    assert np.abs(move("nasolabial", ".R", [0, 5])).max() < 0.02        # the side that is off
    t = move("tear_trough", ".L", [0, 4.6])
    assert t[0] < -0.3 and t[1] > 0.9, t                               # the trough and the bag over it
    # the keep-out: nothing moves at the lid's margin or on the lips
    keep = sf.keep_lines(J)
    assert len(keep) > 20
    assert np.abs(sdf.field_at(body, keep) - sdf.field_at(images.prims_on(sf.without(spec), ["body"]), keep)).max() < 1e-5
    # profile: a fold with a roll is a step (steep under the roll, a long wall on the other side)
    pr = {"G": np.array([0.001]), "sg": np.array([0.001]), "O": np.array([0.001]), "Pl": np.array([0.0]), "lee": 2.2, "has_roll": True,
          "r0": 0.004, "so": 0.002, "sh": 0.002, "has_plat": False, "ph": 0.001}
    j = np.zeros(4, int)
    v = sf.profile(np.array([-0.002, 0.0, 0.002, 0.004]), pr, j)
    assert v[1] == -0.001 and v[0] < sf.profile(np.array([0.002]), {**pr, "has_roll": False}, j[:1])[0] and v[3] > 0.0009, v
    # the eyeball: a fold pushed in over it stops BALL outside
    c = np.array([0.0, 0.0, 0.0])
    q = np.array([[0.0, -0.0121, 0.0], [0.0, -0.014, 0.0]])
    tree = __import__("scipy.spatial", fromlist=["cKDTree"]).cKDTree(np.array([[0.0, -0.0125, 0.0], [0.001, -0.0125, 0.0]]))
    mp = {"pts": tree.data, "nrm": np.array([[0, -1.0, 0]] * 2), "up": np.array([[0, 0, 1.0]] * 2), "along": np.array([[1.0, 0, 0]] * 2),
          "taper": np.ones(2), "sa": 0.001, "wfull": 2.0, "reach": 0.004, "G": np.array([0.002] * 2), "sg": np.array([0.002] * 2), "O": np.zeros(2),
          "Pl": np.zeros(2), "lee": 1.0, "has_roll": False, "r0": 0.0, "so": 0.001, "sh": 0.001, "has_plat": False, "ph": 0.001,
          "keep": np.zeros((0, 3)), "keep_key": "none", "balls": np.array([[0, 0, 0, 0.012]]), "radius": 0.01, "k": 2, "tree": tree}
    cur = np.array([-0.0004, 0.0015])           # a lid 0.5 mm thick over a 12 mm ball: the skin at 12.5 mm
    new = sf.mod_tissue(cur.copy(), q, mp)
    assert new[1] > cur[1] and new[0] <= 0.0, new       # pushed in outside, but the point 0.1 mm off the ball stays inside the skin


class _Fake(sr.Context):
    pass


@_tmp
def test_colour_read_and_fit_recover_zones():
    """The picture's albedo = our model with other zone strengths and lip colours: the region reads see the
    differences and the fit brings the parameters back (no anchor: the tone is left alone)."""
    truth = {"age": 30, "eyes": False, "zones": {"midface_red": 2.2, "forehead_yellow": 0.2, "nose_red": 2.0}, "lips": {"blood": 0.5, "melanin": 2.0}}
    spec = head_spec(age=30, eyes=False)
    J = skin._joints(spec)
    V, N, _ = mk.head_mesh(spec, "body", J)
    front = N[:, 1] < -0.2
    V, N = V[front].astype(float), N[front].astype(float)
    c = _Fake()
    c.name, c.spec, c.st, c.frames, c.mesh = "t", spec, spec, [], None
    c.anchor = {"kind": "none", "gain": {}, "note": ""}
    c.views = [{"view": 0, "weight": 1.0}]
    c.X, c.n, c.w, c.view, c.pix = V, N, np.ones(len(V)), np.zeros(len(V), int), np.arange(len(V))
    c.alb = sr.Albedo(spec, V, N)
    c.A0 = c.alb()
    c.T = c.alb(truth)
    c.rho = c.T / c.A0
    c.dlab = sr.lab(c.T) - sr.lab(c.A0)
    c.J = J
    R = sr.regions(c)
    rows = {k: sr._region(c, w) for k, w in R.items()}
    assert rows["cheek"]["read"] and rows["cheek"]["d"][1] > 0.4 and rows["forehead"]["d"][2] < -0.5, (rows["cheek"], rows["forehead"])
    lips_read = rows["lip_lower"]["read"]            # (the hand-made head's lips are a few vertices)
    assert not lips_read or rows["lip_lower"]["d"][1] < -1.0, rows["lip_lower"]
    r = {"ctx": c, "regions": rows, "freckles": {"read": False, "have": 0.0, "views": {}}, "brows": {"read": False}, "eyes": {}}
    f = sr.fit(r, groups=("zones", "lips"), log=lambda s: None)
    g = lambda p: sr._get(f["skin"], p)  # noqa: E731
    # (overlapping layers are not unique: more mid-face red may come back as some flush; the ALBEDO is what is recovered)
    assert g("zones.midface_red") > 1.3 and g("zones.forehead_yellow") < 0.6, f["text"]
    assert not lips_read or abs(g("lips.blood") - 0.5) < 0.2, f["text"]
    assert "tone" not in f["skin"], "no anchor: the tone is not touched"
    err0 = np.abs(sr.lab(c.A0) - sr.lab(c.T)).mean(0)
    err1 = np.abs(sr.lab(c.alb(f["skin"])) - sr.lab(c.T)).mean(0)
    assert err1[1] < 0.4 * err0[1] and err1[2] < 0.6 * err0[2], (err0, err1)
    # the null: the picture's albedo = ours -> nothing changes
    c.T = c.A0.copy(); c.dlab = np.zeros_like(c.A0)
    rows = {k: sr._region(c, w) for k, w in R.items()}
    f0 = sr.fit({**r, "regions": rows}, groups=("zones", "lips"), log=lambda s: None)
    assert not f0["changes"], f0["text"]


def test_fold_fit_rules():
    side = lambda **kw: {"present": False, "absent_in_picture": False, "picture": 0.0, "ours": 0.0, "diff": 0.0, "excess": 0.0,  # noqa: E731
                         "share": 0.0, "confidence": 0.0, "views": [0], **kw}
    hit = side(present=True, picture=0.15, diff=0.15, share=0.9, extent=[0.0, 0.7], shift=[1.0] * 9, confidence=1.0)
    fr = {"folds": {"nasolabial": {"readable": True, "sides": {".L": hit, ".R": side()}},
                    "lid_fold": {"readable": False, "why": "cannot tell", "sides": {}},
                    "tear_trough": {"readable": True, "sides": {".L": side(), ".R": side()}}},
          "fields": {"forehead": {"readable": True, "picture": 1.5, "ours": 0.8, "diff": 0.7},
                     "crows_feet": {"readable": False, "why": "cannot tell"}}}
    sk = {"age": 30, "wrinkles": {"nasolabial": 0.6}}
    ch = sr.fold_fit(sk, fr, True)
    n = sk["folds"]["nasolabial"]
    assert 0.9 < n["amount"] <= 1.5 and n["L"]["shift"] == [1.0] * 9 and n["L"]["extent"] == [0.0, 0.7] and n["R"]["amount"] == 0.0, n
    assert sk["wrinkles"]["nasolabial"] == 0.0, "the legacy landmark line is replaced by the measured fold"
    assert "tear_trough" not in sk["folds"] and "lid_fold" not in sk["folds"], "absent and unreadable folds are left out"
    assert "forehead" not in sk["wrinkles"] and "crows_feet" not in sk["wrinkles"], "fine-line fields are reported, not fitted (failed their null)"
    assert any(c_[0] == "folds.nasolabial" for c_ in ch)
    # ours has it, the picture does not: taken off
    gone = side(absent_in_picture=True, ours=0.15, excess=0.15)
    sk2 = {"age": 30, "folds": {"tear_trough": 1.0}}
    sr.fold_fit(sk2, {"folds": {"tear_trough": {"readable": True, "sides": {".L": gone, ".R": gone}}}, "fields": {}}, True)
    assert "folds" not in sk2 or sk2["folds"].get("tear_trough", {"amount": 0})["amount"] < 0.45, sk2
    # the null: nothing present, nothing in excess -> untouched
    sk3 = {"age": 30, "folds": {"tear_trough": 0.7}}
    assert sr.fold_fit(sk3, {"folds": {"tear_trough": {"readable": True, "sides": {".L": side(), ".R": side()}}}, "fields": {}}, True) == []
    assert sk3["folds"] == {"tear_trough": 0.7}


def test_step_and_tone_bound():
    """The side-lit STEP detector's sign rule, and the fit's amount by how a fold was read."""
    side = lambda **kw: {"present": False, "absent_in_picture": False, "picture": 0.0, "ours": 0.0, "diff": 0.0, "excess": 0.0,  # noqa: E731
                         "share": 0.0, "confidence": 0.0, "views": [0], **kw}
    st = side(present=True, by="step", step=0.5 * sr.STEP_REF["nasolabial"], step_share=0.8, confidence=0.9, extent=[0.1, 0.9], shift=[2.0] * 9)
    lash = side(present=True, by="lash line", amount=0.8, confidence=0.9, extent=[0.0, 1.0], shift=[-1.5] * 9, picture=0.3, ours=0.1, diff=0.2)
    sk = {"age": 50}
    sr.fold_fit(sk, {"folds": {"nasolabial": {"readable": True, "sides": {".L": st, ".R": side()}},
                               "lid_fold": {"readable": True, "sides": {".L": lash, ".R": lash}}}, "fields": {}}, True)
    assert abs(sk["folds"]["nasolabial"]["amount"] - 0.5) < 0.02 and sk["folds"]["nasolabial"]["L"]["shift"] == [2.0] * 9, sk
    assert abs(sk["folds"]["lid_fold"]["amount"] - 0.8) < 0.02 and sk["folds"]["lid_fold"]["L"]["shift"] == [-1.5] * 9, sk
    assert sr.TONE_BOUND <= 3.0 < sr.TONE_BOUND_WHITE


if __name__ == "__main__":
    for t in (test_valley_lab_and_specks, test_get_set_and_fold_options, test_beard_zones_partition_and_weights, test_fold_map_and_layers,
              test_folds_are_geometry, test_step_and_tone_bound,
              test_colour_read_and_fit_recover_zones, test_fold_fit_rules):
        t0 = __import__("time").time()
        t()
        print("ok", t.__name__, f"{__import__('time').time() - t0:.0f} s")
