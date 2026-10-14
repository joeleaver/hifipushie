"""skin_layers (the skin as a stack of layer maps) and the mesh-space lid fold, no Blender
(`uv run python tests/test_skin_layers.py`; the lid fold needs the gnm pack and skips without)."""
import numpy as np

from hifipushie import assets, skin, skin_layers as sl
from hifipushie.spec import SpecError


def test_axes_and_exact_decomposition():
    V = sl.axes({"fitzpatrick": 2})
    assert V.shape == (3, 3) and (V[:2] > 0).all()                 # more pigment absorbs in every channel
    assert V[0, 2] > V[0, 0] and V[1, 1] > V[1, 0]                 # melanin: blue most; haemoglobin: green over red
    rng = np.random.default_rng(0)
    A = np.abs(rng.normal(0, 0.3, (500, 3)))
    D = A @ V
    assert np.allclose(D @ np.linalg.inv(V), A, atol=1e-9)        # three amounts, three channels: exact


def test_ica_finds_the_axes():
    V = sl.axes({"fitzpatrick": 3})
    rng = np.random.default_rng(1)
    m, h = rng.exponential(0.2, 40000), rng.exponential(0.15, 40000)      # independent, non-Gaussian amounts
    shade = rng.normal(0, 0.2, 40000)                                     # shading: along (1, 1, 1), leaves the plane
    D = m[:, None] * V[0] + h[:, None] * V[1] + shade[:, None] * V[2]
    r = sl.ica_check(D, V)
    assert r["melanin_deg"] < 6 and r["haemoglobin_deg"] < 6, r
    assert r["model_axes_deg"] > 15


def test_stack_layers_and_edit():
    st = {"box": [0.56, 0.65, 1.0, 0.99], "base": [0.86, 0.76, 0.66], "coverage": "c" * 16,
          "layers": [{"name": "pigment", "image": "a" * 16, "opacity": 0.8}, {"name": "redness", "image": "b" * 16, "opacity": 0.8},
                     {"name": "beard", "image": "d" * 16, "opacity": 0.8}]}
    spec = {"skin": {"tone": {"fitzpatrick": 2}, "stack": st}}
    assert skin.params(spec)["stack"] is st
    out = {}
    sl.layers(spec, st, out, "body")
    assert list(out) == ["skin:stack_base", "skin:stack_pigment", "skin:stack_redness", "skin:stack_beard"]
    assert out["skin:stack_redness"]["mix"] == "multiply" and out["skin:stack_redness"]["color"] == "image"
    assert out["skin:stack_redness"]["image"]["wrap"] == "uv"
    st2 = {**st, "fine": "f" * 16}
    out3 = {}
    sl.layers({"skin": {"stack": st2}}, st2, out3, "body")
    assert "skin:stack_fine0" in out3 and out3["skin:stack_fine0"]["mask"][1]["image"]["channel"] == "luma" and out3["skin:stack_fine0"]["mix"] == "multiply"
    e = sl.edit(spec, "blush", "no_stubble")
    op = {l["name"]: l["opacity"] for l in e["skin"]["stack"]["layers"]}
    assert op["pigment"] == 0.8 and op["redness"] == 1.0 and op["beard"] == 0.0 and 0.7 < op["redness+"] < 0.8   # 2.2 x: a second pass
    out2 = {}
    sl.layers(e, e["skin"]["stack"], out2, "body")
    assert "skin:stack_beard" not in out2 and out2["skin:stack_redness"]["opacity"] == 1.0 and "skin:stack_redness+" in out2
    assert [l["name"] for l in sl.edit(e, "pale")["skin"]["stack"]["layers"]] == ["pigment", "redness", "beard"]   # an edit of an edit starts clean
    assert [l["opacity"] for l in spec["skin"]["stack"]["layers"]] == [0.8, 0.8, 0.8]    # the source is not touched
    # a layer's stored multiplier is exact at the default opacity
    od = np.array([[0.1, 0.2, 0.3]])
    c = sl._multiplier(od)
    assert np.allclose(1 - sl.P0 + sl.P0 * c, np.exp(-od))
    try:
        skin.params({"skin": {"stack": {"layers": "x"}}})
        raise AssertionError("a bad stack was accepted")
    except SpecError:
        pass


def test_lid_fold_is_local_and_unfolds():
    try:
        assets.pack("gnm")
    except Exception as err:  # noqa: BLE001
        print("skipped:", str(err)[:80])
        return
    from hifipushie import gnm_fold as gf
    V = gf.vertices() / 1000.0
    cfg = {"crease": [5.5, 7.0, 6.0], "overhang": [0.3, 1.0, 2.5]}
    d = gf.mesh_delta(V, None, cfg)
    t = gf.topo()
    ring = np.minimum(t["ring"], t["ring"][t["mir"]])
    moved = np.linalg.norm(d, axis=1) > 0
    assert 100 < moved.sum() < 1000
    assert set(ring[moved].tolist()) <= set(range(1, 13))          # rings 1..12 (the fold + its fade): the margin (0) and the brow stay
    T = gf.gc.gnm()["T"] * 1000.0
    J = gf.gc.gnm()["J"][2] * 1000.0
    up = (T[:, 1] > J[1] - 1.0) | (np.abs(T[:, 0]) - abs(J[0]) > 3.0)
    small = np.linalg.norm(d, axis=1) * 1000.0 < 0.5
    assert (up | small)[moved].all()            # nothing under the eye but the wrap round the OUTER corner and a < 0.5 mm fade
    lm = gf.gc.gnm().get("lm68")
    q = gf.read((V + d) * 1000.0)
    assert q["hang_max"] > 1.5 and gf.read(V * 1000.0)["hang_max"] == 0.0
    # L / R of their own: the right eye alone
    d_r = gf.mesh_delta(V, None, {"crease": 6.5, "overhang": 1.0, "L": {"amount": 0.0}})
    mv = np.linalg.norm(d_r, axis=1) > 0
    assert mv.any() and len(set(np.sign(V[mv, 0]).tolist())) == 1   # one side only
    # a blink unfolds it: the upper margin brought down its whole aperture
    r0 = np.flatnonzero(t["ring"] == 0)
    En = np.zeros_like(V)
    upm = r0[T[r0, 1] > J[1] + 0.5]
    for ids in (upm, t["mir"][upm]):
        En[ids, 1] -= 0.012
    assert np.abs(gf.mesh_delta(V, En, cfg)).max() == 0.0
    half = En * 0.3
    dh = gf.mesh_delta(V, half, cfg)
    assert 0 < np.abs(dh).max() < np.abs(d).max()
    del lm


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
