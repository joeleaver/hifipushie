"""(c14, Garrett) the baked cards' tone must not clip at the vertex colour's 1.0: a third of c11L's card vertices sat at
the ceiling, so lightening levers (tone_back, the flow top's lit) did nothing on the back. hair.export.headroom moves a
factor of the cards' tone into the atlas's bake block."""
import numpy as np

from hifipushie import hair_cards as hc
from hifipushie import hair_colour as hcol

S = {"atlas": 256, "clump": 0.5, "frizz": 0.0, "curl": 0.0, "tips": 0.5}
LOOK = {"gap": "#221310", "lit": "#56352d", "vary": 0.25}


def _bake(W, Hb=32, seed=0):
    r = np.random.default_rng(seed)
    a = np.zeros((Hb, W), np.float32)
    a[4:28, 8:W - 8] = 1.0
    return {"alpha": a, "id": r.uniform(0, 1, (Hb, W)).astype(np.float32),
            "depth": r.uniform(0.4, 1, (Hb, W)).astype(np.float32),
            "tone": r.uniform(0.15, 0.35, (Hb, W)).astype(np.float32),
            "flow": np.dstack([np.zeros((Hb, W)), -np.ones((Hb, W))]).astype(np.float32),
            "root": np.tile(np.linspace(1, 0, Hb)[:, None], (1, W)).astype(np.float32), "key": f"t{seed}"}


def _lin(c):
    c = np.asarray(c, np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def test_headroom_keeps_the_picture_and_frees_the_back_cards_tone():
    W = hc.atlas(S, LOOK)["color"].shape[1]
    B = _bake(W)
    a1 = hc.atlas(S, {**LOOK}, bake=B, key="h1")
    a2 = hc.atlas(S, {**LOOK, "headroom": 2.0}, bake=B, key="h2")
    Ht = a1["rows"]
    m = B["alpha"] > 0.5
    H = a1["bake_k"] / a2["bake_k"]
    assert 1.5 < H <= 2.0 + 1e-6
    # the picture a card shows = atlas x its vertex colour (tone_k = bake_k x tint): the same where nothing clipped
    p1 = _lin(a1["color"][Ht:, :, :3])[m] * a1["bake_k"]
    p2 = _lin(a2["color"][Ht:, :, :3])[m] * a2["bake_k"]
    assert np.allclose(p1, p2, rtol=0.03, atol=2e-3)
    # a back card lifted by tone_back 1.0 over 0.85 (x 1.18), its vertex colour scaled so 0.85 sits at the ceiling (c11L)
    g = 1.0 / (a1["bake_k"] * 0.85)
    back = {}
    for name, a in (("plain", a1), ("headroom", a2)):
        v = [np.clip(a["bake_k"] * t * g, 0, 1) for t in (0.85, 1.0)]
        back[name] = (_lin(a["color"][Ht:, :, :3])[m] * v[1]).mean() / (_lin(a["color"][Ht:, :, :3])[m] * v[0]).mean()
    assert back["plain"] < 1.01  # the old path: the lift is eaten by the clip
    assert back["headroom"] > 1.15  # with headroom the back cards are lighter by tone_back's own ratio
