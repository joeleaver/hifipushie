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


if __name__ == "__main__":
    for k, fn in list(globals().items()):
        if k.startswith("test_"):
            fn()
            print("ok", k)
