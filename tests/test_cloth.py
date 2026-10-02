"""Cloth checks that need no Blender: validation, coarse -> fine transfer, the clean-up pass, detail maps.
Run: uv run python tests/test_cloth.py"""
import numpy as np

from hifipushie import cloth, pattern


def _tablecloth(h):
    g = {"pieces": {"cloth": {"rect": [1.2, 0.8],
                              "wrap": {"to": "flat", "at": [0, 0, 0.8]}}}, "state": "draped"}
    B = cloth.pieces(g, {})
    return g, B, cloth.mesh(B, h)


def test_validate():
    ok = {"base": {"body": {"source": "makehuman"}}, "cloth": {"shirt": {"pattern": {"from": "simon"}}}}
    cloth.validate(ok)
    for bad, word in (({"pattern": {"from": "nope"}}, "pattern"), ({"pattern": {"from": "simon"}, "fabric": "x"}, "fabric"),
                      ({"pattern": {"from": "simon"}, "state": "hung"}, "hang"),
                      ({"pattern": {"from": "simon"}, "colour": "#fff"}, "unknown keys"),
                      ({"pattern": {"from": "simon", "ease": {"chestt": 0.1}}}, "ease")):
        try:
            cloth.validate({"base": ok["base"], "cloth": {"g": bad}})
        except cloth.ClothError as e:
            assert word in str(e), (word, str(e))
        else:
            raise AssertionError(f"not rejected: {bad}")
    # a tablecloth needs no body; a wrapped piece on a model without one is refused
    cloth.validate({"cloth": {"t": _tablecloth(0.05)[0]}})
    try:
        cloth.validate({"cloth": {"s": {"pattern": {"from": "simon"}}}})
    except cloth.ClothError as e:
        assert "base" in str(e)
    else:
        raise AssertionError("a shirt on a model without a body")


def test_transfer():
    _, B, Mc = _tablecloth(0.08)
    _, _, Mf = _tablecloth(0.03)
    # a curved sheet: z = f(u, v); the fine mesh carried from the coarse lies on the coarse triangles
    f = lambda uv: np.c_[uv, 0.1 * np.sin(3 * uv[:, 0]) + 0.05 * uv[:, 1] ** 2]
    Vf = cloth.transfer(Mc, f(Mc["uv"]), Mf)
    err = np.abs(Vf - f(Mf["uv"])).max()
    assert err < 0.01, err  # linear interpolation of a smooth surface at 8 cm
    assert np.allclose(Vf[:, :2], Mf["uv"], atol=1e-3)


def test_cleanup_keeps_folds():
    _, B, M = _tablecloth(0.01)
    uv = M["uv"]
    rng = np.random.default_rng(1)
    fold = 0.02 * np.sin(uv[:, 0] * 2 * np.pi / 0.25)  # 25 cm folds, 2 cm deep
    V = np.c_[uv, fold + 0.002 * rng.standard_normal(len(uv))]  # + 2 mm crinkle
    body = cloth.Body({"V": np.zeros((0, 3)), "F": np.zeros((0, 3), int), "J": {}})
    X, info = cloth.cleanup(V, M, body, {"clear": 0})
    s0, s1 = cloth.shape_numbers(V, M), cloth.shape_numbers(X, M)
    assert s1["crinkle_mm"] < 0.6 * s0["crinkle_mm"], (s0, s1)
    inner = ~M["border"]
    assert np.abs(X[inner, 2] - fold[inner]).mean() < 0.0025  # the folds stay


def test_detail_maps():
    g, B, M = _tablecloth(0.05)
    uv, side = cloth.atlas_uv(M)
    dm = cloth.detail_maps(M, uv, side, g, texture=512)
    assert dm["normal"].shape == (512, 512, 3)
    assert dm["thread"].max() > 0.5  # a topstitch line along the hem
    assert dm["height"].max() > 0  # the turned hem stands proud


def test_marks_make_no_slivers():
    # a notch on the outline and two marks 1 mm apart: the outline vertex / one vertex, not sub-mm edges
    h = 0.01
    g = {"pieces": {"p": {"rect": [0.3, 0.2], "marks": {"notch": [0.0003, 0.0997], "a": [0.05, 0.0], "b": [0.051, 0.0]},
                          "wrap": {"to": "flat"}}}}
    M = cloth.mesh(cloth.pieces(g, {}), h)
    F, uv = M["F"], M["uv"]
    E = np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]
    assert np.linalg.norm(uv[E[:, 0]] - uv[E[:, 1]], axis=1).min() > 0.3 * h
    assert M["border"][M["marks"]["p:notch"]] and M["marks"]["p:a"] == M["marks"]["p:b"]


def test_straight_arms():
    # a bent arm (a box of points along shoulder -> elbow -> wrist) straightened, then posed back exactly
    sh, el = np.array([0.2, 0, 1.4]), np.array([0.45, 0, 1.2])
    d1 = (el - sh) / np.linalg.norm(el - sh)
    wr = el + 0.25 * np.array([0.3, -0.7, -0.65]) / np.linalg.norm([0.3, -0.7, -0.65])
    t = np.linspace(0, 1, 40)[:, None]
    V = np.r_[sh + t * (el - sh), el + t * (wr - el)] + [0, 0, 0.0]
    body = cloth.Body({"V": V, "F": np.zeros((0, 3), int), "J": {"shoulder.L": sh, "elbow.L": el, "wrist.L": wr}})
    body._m = {"mm": {}, "at": {}}
    sb, pose = body.straight_arms()
    w = sb.J["wrist.L"]
    assert np.allclose((w - el) / np.linalg.norm(w - el), d1, atol=1e-6)  # in line with the upper arm
    far = np.r_[(V[:40] - el) @ ((d1 + (wr - el) / np.linalg.norm(wr - el)) / 2) < -0.045, np.zeros(40, bool)]
    assert far.sum() > 20 and np.allclose(sb.V[far], V[far])  # the upper arm (outside the band) doesn't move
    assert np.abs(pose(sb.V) - V).max() < 2e-3  # posed back (the blend band read from the bent side)


def test_piece_crossings():
    _, B, M = _tablecloth(0.1)
    X = np.c_[M["uv"], np.zeros(len(M["uv"]))]
    assert cloth._piece_crossings(X, M) == set()
    Y = X.copy()  # fold the cloth's right half down through its left half
    r = M["uv"][:, 0] > 0.1
    Y[r] = np.c_[0.1 - (M["uv"][r, 0] - 0.1), M["uv"][r, 1], 0.05 * np.sin(8 * M["uv"][r, 1])]
    assert ("cloth", "cloth") in cloth._piece_crossings(Y, M)


if __name__ == "__main__":
    for k, fn in list(globals().items()):
        if k.startswith("test_"):
            fn()
            print("ok", k)
