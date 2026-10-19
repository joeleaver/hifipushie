"""Hair / lash LODs in the character export (round 28): every hair tier's uv must index the atlas its GLB wears
(asset's LOD1-3 hair read LOD0's 2048 x 2048 atlas with uv made for a 2048 x 1024 one: a bald crown, a torn tail),
and the lash ribbons are thinned by whole ribbons per LOD."""
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

from hifipushie import hair, lods


def _atlas(d: Path, img: np.ndarray) -> dict:
    d.mkdir(parents=True, exist_ok=True)
    f = {}
    for k in ("basecolor", "normal", "aux"):
        f[k] = d / f"hair_{k}.png"
        Image.fromarray(img).save(f[k])
    f["specular"] = d / "hair_specular_gltf.png"
    Image.fromarray(np.full((4, 4, 4), 255, np.uint8)).save(f["specular"])
    return f


def _alpha_at(img: np.ndarray, uv: np.ndarray) -> np.ndarray:  # glTF-style lookup of uv made with v up
    H, W = img.shape[:2]
    x = np.clip((uv[:, 0] * W).astype(int), 0, W - 1)
    y = np.clip(((1 - uv[:, 1]) * H).astype(int), 0, H - 1)
    return img[y, x, 3]


def test_share_atlas():
    rng = np.random.default_rng(0)
    tiles = rng.integers(0, 255, (64, 128, 4), dtype=np.uint8)
    bake = rng.integers(0, 255, (64, 128, 4), dtype=np.uint8)
    hero = np.concatenate([tiles, bake], 0)  # the hero tier: tiles over the baked block
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        f0, f1 = _atlas(t / "hero", hero), _atlas(t / "main", tiles)
        uv = rng.random((500, 2)).astype(np.float32)
        want = _alpha_at(tiles, uv)
        part = {"uv": uv.copy()}
        assert not np.array_equal(_alpha_at(hero, uv), want)  # the round-27 fault: tier uv on LOD0's atlas
        assert hair.share_atlas(part, f1, f0)
        assert np.array_equal(_alpha_at(hero, part["uv"]), want), "tier uv must land on the same texels"
        same = {"uv": uv.copy()}
        assert hair.share_atlas(same, f0, f0) and np.array_equal(same["uv"], uv)
        other = _atlas(t / "other", rng.integers(0, 255, (64, 128, 4), dtype=np.uint8))
        keep = {"uv": uv.copy()}
        assert not hair.share_atlas(keep, other, f0) and np.array_equal(keep["uv"], uv)  # different pictures: own maps


def test_ribbon_lod():
    seg, n = 4, 40
    V, T = [], []
    for i in range(n):  # n ribbons of seg quads, across-pairs (2j, 2j + 1)
        b = len(V)
        for j in range(seg + 1):
            V += [[i * 0.01, 0.0, j * 0.002], [i * 0.01 + 0.0002, 0.0, j * 0.002]]
        for j in range(seg):
            a0, b0, a1, b1 = b + 2 * j, b + 2 * j + 1, b + 2 * j + 2, b + 2 * j + 3
            T += [[a0, b0, b1], [a0, b1, a1]]
    V, T = np.array(V, np.float32), np.array(T)
    c = T.ravel()
    p = {"verts": V, "corner_vert": c, "uv": np.zeros((len(c), 2), np.float32), "normal": np.zeros((len(c), 3)),
         "tangent": np.zeros((len(c), 3)), "sign": np.ones(len(c))}
    q, r = lods.ribbon_lod(p, 0.25)
    assert r["ribbons"] == 10 and r["triangles"] == 10 * 2 * seg, r
    assert len(q["uv"]) == len(q["corner_vert"]) and len(q["verts"]) == len(V)
    Tq = q["corner_vert"].reshape(-1, 3)
    w = np.linalg.norm(q["verts"][Tq[::2, 1]] - q["verts"][Tq[::2, 0]], axis=1).max()  # (a0, b0: across)
    assert abs(w - 0.0002 * lods.RIBBON_WIDEN) < 1e-6, w  # widened (capped) for coverage
    xs = np.unique(np.round(q["verts"][np.unique(Tq)][:, 0], 3))
    assert xs.min() == 0.0 and xs.max() == round((n - 1) * 0.01, 3)  # spread along the lid, not the first ten
    q1, r1 = lods.ribbon_lod(p, 1.0)
    assert r1["triangles"] == len(T)

def _ribbons(n, seg=4):
    V, T = [], []
    for i in range(n):
        b = len(V)
        for j in range(seg + 1):
            V += [[i * 0.01, 0.0, j * 0.002], [i * 0.01 + 0.0002, 0.0, j * 0.002]]
        for j in range(seg):
            a0, b0, a1, b1 = b + 2 * j, b + 2 * j + 1, b + 2 * j + 2, b + 2 * j + 3
            T += [[a0, b0, b1], [a0, b1, a1]]
    c = np.array(T).ravel()
    return {"verts": np.array(V, np.float32), "corner_vert": c, "uv": np.zeros((len(c), 2), np.float32),
            "normal": np.zeros((len(c), 3)), "tangent": np.zeros((len(c), 3)), "sign": np.ones(len(c))}


def test_lash_budget_fit():
    """Round 29: Tess's eyes_mouth_lashes was 5,699 of the hero's 5,000. The lashes fit what the eyes / teeth / tongue
    leave (asset.lash_cap + lods.ribbon_fit), whole lashes, widened; under the cap nothing changes; the lower lid's
    lashes are 2 segments (lashes.triangles counts per lid)."""
    from hifipushie import asset, lashes
    rb = {"parts": {"eyes_mouth_lashes": {"default": 5000}}}
    rep = {"eyes": {"triangles": 795}, "teeth_lower": {"triangles": 24}, "body": {"triangles": 30000}}
    cap = asset.lash_cap(rb, rep)
    assert cap == 5000 - 819, cap
    assert asset.lash_cap({"parts": {}}, rep) is None
    p = _ribbons(300)  # 2400 triangles
    q, r = lods.ribbon_fit(p, 2000)
    assert r["triangles"] <= 2000 and r["triangles"] >= 2000 - 8, r  # as many whole lashes as fit
    assert r["widen"] > 1.0 and len(q["verts"]) == len(p["verts"])
    q2, r2 = lods.ribbon_fit(p, 5000)
    assert q2 is p and r2["triangles"] == 2400
    cfg = lashes.wanted({"base": {"body": {"source": "human", "sex": 0.0}, "head": {"x": 1}, "lashes": {}}})
    n = lashes.triangles({"base": {"body": {"source": "human", "sex": 0.0}, "head": {"x": 1}, "lashes": {}}})
    assert cfg["lower"]["segments"] == 2 and n == 4 * (cfg["upper"]["count"] * cfg["segments"] + cfg["lower"]["count"] * 2), n
    assert n == 4280, n  # (4880 before round 29)


def test_halo_card_rules():
    """Round 29: lower tiers' pooled halo cards stood 1-3 cm over the crown (LOD1-3 only): the hero's rules apply to
    every tier: no card for a single hair rooted over the crown, or one that loops."""
    from hifipushie import hair_cards, hair_clumps
    C = np.array([0.0, 0.0, 1.5])
    up = np.linspace(0, 1, 6)[:, None]
    low = {"pts": C + [0.08, 0, 0] + up * [0, -0.05, -0.05]}  # rooted at the side, below the crown line
    crown = {"pts": C + [0, 0, hair_clumps.FLY_CROWN + 0.03] + up * [0, -0.05, 0]}
    loop = {"pts": C + [0.08, 0, 0] + 0.01 * np.c_[np.cos(up[:, 0] * 6), np.sin(up[:, 0] * 6), 0 * up[:, 0]]}
    assert hair_cards.halo_card_ok(low, C)
    assert not hair_cards.halo_card_ok(crown, C)
    assert not hair_cards.halo_card_ok(loop, C)


def test_far_fly_dropped():
    """Round 30: LOD1-3 had thin fly cards standing 35-80 mm off the tail by the tie: the hero's FLY_FAR at every
    tier (a fly card further than that off the hair that isn't few single hairs gets none; face-framing ones stay)."""
    from hifipushie import hair_cards, hair_clumps
    t = np.linspace(0, 0.2, 41)  # (strand_grid: GRID stations a lock)
    A = np.stack([np.c_[t, 0 * t + k * 0.002, 0 * t] for k in range(4)])  # lock 0: a mass of 4 strands along x
    G = {"A": A, "lock": np.zeros(4, int)}
    locks = [{"name": "mass"}, {"name": "wisp", "hairs": 2}, {"name": "cheek", "hairs": 2, "face": True}]
    near = {"P": np.c_[t, 0 * t + 0.01, 0 * t], "kind": "fly", "lock": "wisp"}
    far = {"P": np.c_[t, 0 * t + hair_clumps.FLY_FAR + 0.02, 0 * t], "kind": "fly", "lock": "wisp"}
    face = {"P": np.c_[t, 0 * t + 0.08, 0 * t], "kind": "fly", "lock": "cheek"}
    dense = {"P": np.c_[t, 0 * t + 0.08, 0 * t], "kind": "dense", "lock": "mass"}
    kept = hair_cards.drop_far_fly([near, far, face, dense], G, locks)
    assert [c["lock"] + c["kind"] for c in kept] == ["wispfly", "cheekfly", "massdense"]


if __name__ == "__main__":
    for f in (test_share_atlas, test_ribbon_lod, test_lash_budget_fit, test_halo_card_rules):
        f()
        print("ok", f.__name__)
