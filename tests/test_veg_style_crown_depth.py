"""Styled trees (Braynard's storybook oak, 2026-11-17): leaf cards stay on the shell, styled trunks carry the spec's
`roots`, and `crown.down_to` hangs the crown down its sides. uv run python -m pytest tests/test_veg_style_crown_depth.py"""
import numpy as np
from scipy.spatial import ConvexHull

from hifipushie import veg_cloud, veg_style as vs
from hifipushie import veg_style_crown, veg_style_dress, veg_style_small, veg_style_wood
from hifipushie import vegetation_grow

BASE = {"species": "birch", "age": 22}


def _sphere(c, r, n=600):
    P = veg_cloud._fib(n)
    F = ConvexHull(P).simplices
    fn = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
    flip = np.einsum("ij,ij->i", fn, P[F].mean(1)) < 0
    F[flip] = F[flip][:, ::-1]
    return np.asarray(c) + r * P, F, P.copy()


def test_cards_stay_on_a_shell_over_the_grown_height():
    """A shell standing 4 m over the grown height, cards 3 m across: no card sinks into the shell (the clamp was the
    grown height: cards on the crown's top sank metres inside and left bald, smooth shell lumps)."""
    c, R = np.array([0, 0, 10.0]), 2.0
    V, F, N = _sphere(c, R)
    tree = {"height": 8.0, "spec": {"seed": 1, "season": "summer", "leaves": {"shape": "lobed", "length": 0.1}}}
    st = {"crown": {"cards": {"leaf": 4.5, "count": 14, "length": 0.15, "out": [0.0, 0.12], "cover": 12.0}}}
    K = veg_cloud.shell_cards(tree, st, V, F, N, 20000)
    assert K is not None and K["card_m"] > 2.5
    mid = K["pos"]
    assert len(mid) > 20 and (np.linalg.norm(mid - c, axis=1) > R - 0.02).all(), np.linalg.norm(mid - c, axis=1).min()
    assert (mid[:, 2] > c[2] + 0.7 * R).sum() >= 2  # (and the crown's top keeps its cards)


def test_card_size_in_the_report():
    """The report says how big a card is in metres, and warns when cards are huge against the crown's clumps:
    `cards.count` reads like a count of cards but is the leaves in one card's picture."""
    info = {"style": "pixar", "match": {"iou": 0.9, "height_m": [8, 8], "width_m": [8, 8], "azimuths": [0], "iou_by_azimuth": [0.9]},
            "limbs_kept": 4, "limbs": 4, "axes_kept": 5, "axes": 50, "wood_m": 10, "wood_m_grown": 100, "masses": 12, "twigs": 900,
            "cards": 400, "card_m": 5.9, "clump_m": 1.6, "card_vs_clump": 3.69, "card_leaves": 110, "cards_triangles": 2000, "leaf_cover": 2.0}
    assert any("5.9 m across" in l for l in veg_style_small.lines(info))
    w = veg_style_small.warnings(info)
    assert any("5.9 m across" in x and "ONE card" in x for x in w), w
    assert not any("ONE card" in x for x in veg_style_small.warnings({**info, "card_vs_clump": 0.3}))


def _ground_reach(st, spec):
    T = vegetation_grow.grow(spec)
    mini = veg_style_wood.wood(T, st)
    W = veg_style_wood.wood_dense(mini, st)
    g = W["V"][(W["V"][:, 2] > 0.0) & (W["V"][:, 2] < 0.15)]
    return mini, W, float(np.linalg.norm(g[:, :2] - mini["pos"][0, :2], axis=1).max())


def test_roots_on_styled_trunks():
    """The spec's `roots` on a styled trunk: one buttress per root, joined into the trunk, reaching out over the
    ground well past the flared foot (they were ignored: a smooth round foot only)."""
    for sheet in ("pixar", "cartoon"):
        spec0 = {**BASE, "style": sheet}
        st = vs.sheet(spec0)
        mini0, _, r0 = _ground_reach(st, spec0)
        mini1, W1, r1 = _ground_reach(st, {**spec0, "roots": {"count": 5, "spread": 2.2, "height": 0.8}})
        segs = veg_style_wood._segments(mini1, (0, 1))
        roots = [s for s in segs if len(s) > 5]
        assert len(roots) == 5 and not [s for s in veg_style_wood._segments(mini0, (0, 1)) if len(s) > 5]
        r_b = float(np.interp(0.8, mini1["pos"][1:, 2], mini1["radius"][1:]))
        assert r1 > r0 + 0.6 * r_b, (sheet, r0, r1, r_b)
        assert W1["V"][:, 2].min() < -0.1  # (they run into the ground)
        assert not veg_style_wood._segments(mini1, (2,)) or all(len(s) == 5 for s in veg_style_wood._segments(mini1, (2,)))


def test_skirt_points():
    """`crown.down_to`: points hung under the crown's outer twigs, down to that share of the height, drawn in a little
    at the bottom; none when unset, none under the crown's middle."""
    rng = np.random.default_rng(3)
    a = rng.uniform(0, 2 * np.pi, 2000)
    r = 3.0 * np.sqrt(rng.uniform(0, 1, 2000))
    X = np.c_[r * np.cos(a), r * np.sin(a), rng.uniform(6.5, 8.0, 2000)]
    assert veg_style_crown.skirt(X, 8.0, {"down_to": None}) is X
    Y = veg_style_crown.skirt(X, 8.0, {"down_to": 0.35, "skirt_rim": 0.6, "skirt_curl": 0.25, "skirt_max": 2.0})
    new = Y[len(X):]
    assert len(new) > 500 and new[:, 2].min() >= 0.35 * 8.0 - 1e-9 and new[:, 2].min() < 3.3
    low = new[new[:, 2] < 4.0]
    assert np.linalg.norm(low[:, :2], axis=1).min() > 1.2  # (a skirt round the outside, not a column in the middle)


def test_crown_reaches_down():
    """A styled crown with `down_to` reaches lower down its sides than the twigs alone take it, and the report says so
    when that costs outline IoU."""
    spec = {**BASE, "style": {"sheet": "pixar", "crown": {"down_to": 0.3}}}
    T = vegetation_grow.grow(spec)
    H = T["height"]
    st0 = vs.sheet({**BASE, "style": "pixar"})
    st1 = vs.sheet(spec)
    X, _ = veg_style_crown.leaf_points(T)
    D0 = veg_style_dress.dress(T, st0)
    D1 = veg_style_dress.dress(T, st1)
    z0, z1 = D0["crown"]["V"][:, 2].min(), D1["crown"]["V"][:, 2].min()
    assert z1 < z0 - 0.05 * H and z1 < np.percentile(X[:, 2], 2), (z0, z1, H)
    assert D1["info"]["down_to"] == 0.3 and D1["info"]["skirt_points"] > 0
