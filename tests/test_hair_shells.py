"""hair.export.style "shells" (sh1): hair_cap.combed traces strands along the chart's lay and builds shell maps that
thin outward; hair_cards.atlas stacks the shells' block under the tiles / bake block."""
import numpy as np

from hifipushie import hair_cap, hair_cards as hc


def _chart(n=256, e0=-40.0):
    H = W = n
    el = 90.0 - (np.arange(H) + 0.5) / H * (90.0 - e0)
    cov = np.repeat((el > 0).astype(np.float32)[:, None], W, 1) * 0.7
    lay = np.zeros((H, W, 2), np.float32)
    lay[..., 1] = -1.0  # combed straight down (up component -1)
    grid = lambda v: {"az0": 0.0, "el0": e0, "step": 4.0, "h": np.full((int(np.ceil((90 - e0) / 4)), 90), v, np.float32)}  # noqa: E731
    return {"alpha": cov.copy(), "cover": cov, "base": (cov > 0).astype(np.float32), "grey": cov * 0.2,
            "lay": lay, "length": grid(0.02), "lift": grid(0.01), "R": 0.095, "e0": e0}


def test_combed_shells_thin_out_and_follow_the_lay():
    ch = _chart()
    out = hair_cap.combed(ch, heights=(0.62, 0.85), base=0.4, seed=1, cover=3.0)
    hair = ch["cover"] > 0
    cap, s1, s2 = out["cap"]["alpha"], out["shells"][0]["alpha"], out["shells"][1]["alpha"]
    assert cap[hair].mean() > 0.95  # the cap is opaque over the hair (base + strands)
    c1, c2 = s1[hair].mean(), s2[hair].mean()
    assert 0.05 < c2 < c1 < 0.9, (c1, c2)  # outer shells are sparser strand bits, never a copy of the cap
    f = out["shells"][0]["flow"]
    m = s1 > 0.5
    assert np.mean(np.abs(f[..., 1][m]) > np.abs(f[..., 0][m])) > 0.8  # strands run along the lay (up / down)


def test_atlas_shell_block():
    ch = _chart(128)
    out = hair_cap.combed(ch, heights=(0.62, 0.85), base=0.4, seed=1, cover=2.0)
    S = {**hc.STRANDS, "atlas": 128}
    cap = {**out["cap"]}
    at = hc.atlas(S, {"grey_share": 0.2}, cap=cap, key="t_shells", shells=out["shells"])
    sb = at["shells"]
    assert sb["n"] == 2 and sb["row0"] == 128 and sb["rows"] == 64 and at["rows_total"] == 192
    a = at["color"][..., 3]
    blk = a[128:, :64]
    assert blk.mean() > 0.02 and a[128:, 128:].max() == 0  # slot 0 drawn, unused slots empty
    plain = hc.atlas(S, {"grey_share": 0.2}, cap=cap, key="t_shells0")
    assert plain["rows_total"] == 128 and np.allclose(plain["color"], at["color"][:128])  # tiles / cap untouched


if __name__ == "__main__":
    test_combed_shells_thin_out_and_follow_the_lay()
    test_atlas_shell_block()
    print("ok")


def test_base_edge_fades_the_base_at_the_hairline():
    """(sh2) BASE_EDGE: the cap's opaque base fades in from the hair's edge (the hairline is strands over skin, not
    the base's dark rim); deep inside the hair the cap stays opaque."""
    ch = _chart(512)  # (texels ~0.4 mm: strands narrower than a texel saturate coarser charts)
    old = hair_cap.BASE_EDGE
    try:
        hair_cap.BASE_EDGE = 0.0
        a0 = hair_cap.combed(ch, heights=(0.62,), base=0.4, seed=1, cover=0.3)["cap"]["alpha"]
        hair_cap.BASE_EDGE = 0.006
        a1 = hair_cap.combed(ch, heights=(0.62,), base=0.4, seed=1, cover=0.3)["cap"]["alpha"]
    finally:
        hair_cap.BASE_EDGE = old
    rows = np.nonzero((ch["cover"] > 0).any(1))[0]
    edge, deep = rows.max(), rows.max() - 120  # the hair's lower edge row and a row well inside
    e0_, e1_ = a0[edge - 2:edge + 1].mean(), a1[edge - 2:edge + 1].mean()  # (sparse strands: the base shows between)
    assert e0_ > 0.95 and e1_ < 0.8, (e0_, e1_)
    assert a1[deep].mean() > 0.95
