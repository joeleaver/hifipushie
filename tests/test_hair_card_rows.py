"""(c9) Card placement rows in the clumps cut: the flow top layer (hair_clumps.FLOW_TOP) and the hairline row
(hair_clumps.HAIRLINE_ROW). Both off by default."""
import numpy as np

from hifipushie import hair_clumps as hk
from test_hair_clumps import C, S, _groom


def _cut(**opts):
    D, locks = _groom()
    return hk.cut(D, locks, C, {**S, **opts}, None, 0, triangles=4000)


def test_flow_top_is_off_by_default():
    assert not any(c.get("flow") or c.get("hrow") for c in _cut())


def test_flow_top_lays_long_cards_over_the_other_cards_ends():
    cards = _cut(flow_top={"cards": 2, "tuck": 0.0015})
    fl = [c for c in cards if c.get("flow")]
    rest = [c for c in cards if c.get("cls") == "head" and not c.get("flow")]
    assert fl and rest
    assert all(c["layer"] == len(hk.LAYERS["head"]) - 1 for c in fl)
    # long: as long as the longer half of the other head cards
    assert np.median([c["s"][-1] for c in fl]) >= np.median([c["s"][-1] for c in rest])
    # on top: other head cards' stations within a flow card's width lie under it
    FP = np.concatenate([np.asarray(c["P"], float) for c in fl])
    FH = np.concatenate([np.asarray(c["hw"], float) for c in fl])
    FR = np.linalg.norm(FP - C, axis=1)
    FU = (FP - C) / FR[:, None]
    over = 0
    n = 0
    for c in rest:  # (radially: seen from the head's centre)
        for p in np.asarray(c["P"], float):
            r = np.linalg.norm(p - C)
            d = np.linalg.norm(FU * r - (p - C), axis=1)
            j = int(np.argmin(d))
            if d[j] < 0.5 * FH[j]:
                n += 1
                over += r > FR[j] + 1e-4
    assert n > 0 and over / n < 0.05, (over, n)


def _sideburn_groom(n=80, length=0.010, seed=0):
    """Short hairs (10 mm) rooted on a sphere round C in the temple band (az ~70, el ~-20) lying down and back."""
    rng = np.random.default_rng(seed)
    pts, counts = [], []
    for k in range(n):
        az, el = np.radians(rng.uniform(60, 80)), np.radians(rng.uniform(-30, -10))
        u = np.array([np.sin(az) * np.cos(el), -np.cos(az) * np.cos(el), np.sin(el)])
        R = C + 0.08 * u
        dn = np.array([0.0, 0.3, -1.0]) - u * (u @ np.array([0.0, 0.3, -1.0]))
        dn /= np.linalg.norm(dn)
        t = np.linspace(0.0, length, 12)
        P = R[None] + t[:, None] * dn[None] + (0.001 + 0.0005 * rng.uniform()) * u[None]
        pts.append(P)
        counts.append(len(P))
    D = {"names": np.array(["hair_even"]), "pts": np.concatenate(pts).astype(np.float32),
         "counts": np.array(counts, np.int32), "lock": np.zeros(n, np.int32), "sub": np.zeros(n, np.float32),
         "rand": rng.uniform(size=n).astype(np.float32), "radius": np.full(n, 4e-5, np.float32), "obj": np.zeros(n, np.int32)}
    return D, [{"name": "tg0_1"}]


def test_hairline_row_gives_short_temple_hairs_cards():
    D, locks = _sideburn_groom()
    base = hk.cut(D, locks, C, dict(S), None, 0, triangles=4000)
    rows = hk.cut(D, locks, C, {**S, "hairline_row": {"cards": 6}}, None, 0, triangles=4000)
    hr = [c for c in rows if c.get("hrow")]
    assert len(hr) >= 2
    assert len([c for c in base if c.get("cls") == "head"]) < len(hr)  # (MIN_STATIONS 4 drops most of these 10 mm hairs)
    az, el, _ = hk._azel(np.array([np.asarray(c["P"], float)[0] for c in hr]), C)
    assert np.all((np.abs(az) > 45) & (el < 10))


def test_rows_skip_tiers_under_their_min_triangles():
    D, locks = _groom()
    cards = hk.cut(D, locks, C, {**S, "flow_top": {"cards": 2, "min_triangles": 5000}}, None, 0, triangles=4000)
    assert not any(c.get("flow") for c in cards)


def test_every_tier_fits_its_drawn_budget_back_faces_counted():
    """(c13, coordinator 2026-10-19) a tier's budgets.json hair_cards DEFAULT (tier_triangles) counts CARD FACES (one
    side); its DRAWN triangles (the cap once, every other triangle twice when cards export their back faces) stay within
    the tier's role's RANGE maximum (hero 50k, main_npc 20k, secondary_npc 8k, crowd 1.5k). Both hold for the cards
    fitted to card_allowance, and the binding one is met within a card's triangles when cards are plentiful."""
    from hifipushie import hair, hair_cards as hc
    assert {t: hair.tier_drawn_max(t) for t in hair.CARD_TIERS} == {"hero": 50000, "main": 20000, "npc": 8000, "far": 1500}
    D, locks = _groom()
    for tier in hair.CARD_TIERS:
        budget, dmax = hair.tier_triangles(tier), hair.tier_drawn_max(tier)
        S_ = {**hc.STRANDS, **S, **{k: v for k, v in hair.tier_settings(tier).items() if k not in ("triangles", "cap_step", "cap")}}
        cards = hk.cut(D, locks, C, S_, None, 0, triangles=budget)
        assert cards, tier
        for bf in (True, False):
            cap, other = budget // 10, 40
            f, fixed, allow = hair.card_allowance(budget, cap, other, back_faces=bf, drawn_max=dmax)
            assert f == (2 if bf else 1)
            # the arithmetic: the allowance meets the tighter of the two limits exactly
            assert allow == max(min(budget - cap - other, (dmax - cap - f * other) // f), 200), (tier, bf, allow)
            keep, seg, info = hc.fit_budget(cards, S_, allow)
            n = hc.triangles(keep, S_, seg)
            faces, drawn = cap + other + n, cap + f * (other + n)
            assert faces <= budget, (tier, bf, faces, budget)
            assert drawn <= dmax, (tier, bf, drawn, dmax)
    # legacy (drawn_max None): the budget itself counts drawn triangles (c10 / c11 callers)
    assert hair.card_allowance(25000, 2000, 100, back_faces=True) == (2, 2200, 11400)
