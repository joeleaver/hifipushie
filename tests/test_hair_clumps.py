"""hair_clumps: cards cut by visual clumps and textured from their own strands (synthetic grooms, no Blender)."""

import numpy as np

from hifipushie import hair_cards as hc
from hifipushie import hair_clumps as hk


def _groom(n_per=60, waves=True, seed=0):
    """Two locks of wavy strands lying side by side over a 'scalp' (z = 0), combed along -y, roots either side of a
    part at x = 0; plus a few single hairs. D like hair_strands.strands_of_model's."""
    rng = np.random.default_rng(seed)
    pts, counts, lock, sub, rand, obj = [], [], [], [], [], []
    for li, x0 in enumerate((-0.02, 0.02)):
        for k in range(n_per):
            y0 = rng.uniform(0.0, 0.03)
            x = x0 + rng.normal(0, 0.006)
            t = np.linspace(0.0, 0.15, 40)
            ph = 0.0 if li == 0 else 1.3
            P = np.stack([x + (0.008 * np.sin(2 * np.pi * t / 0.06 + ph) if waves else 0.0) + np.sign(x0) * 0.2 * t,
                          y0 - t, 0.01 + 0.002 * rng.uniform(size=40)], 1)
            pts.append(P)
            counts.append(len(P))
            lock.append(li)
            sub.append(k % 4)
            rand.append(rng.uniform())
            obj.append(0)
    for k in range(6):  # single hairs standing off
        t = np.linspace(0.0, 0.08, 20)
        P = np.stack([np.full(20, 0.0 + 0.004 * k), -t, 0.012 + 0.1 * t], 1)
        pts.append(P)
        counts.append(20)
        lock.append(2)
        sub.append(0)
        rand.append(rng.uniform())
        obj.append(1)
    D = {"names": np.array(["hair_guides", "hair_guides_wisp"]), "pts": np.concatenate(pts).astype(np.float32),
         "counts": np.array(counts, np.int32), "lock": np.array(lock, np.int32), "sub": np.array(sub, np.float32),
         "rand": np.array(rand, np.float32), "radius": np.full(len(counts), 4e-5, np.float32),
         "obj": np.array(obj, np.int32)}
    locks = [{"name": "tg0_1"}, {"name": "tg0_2"}, {"name": "th1", "hairs": 1, "free": 1.0}]
    return D, locks


S = {"segment": 0.008}
C = np.array([0.0, 0.0, -0.08])


def side_of(R):
    R = np.asarray(R, float)
    return np.sign(R[:, 0]), np.abs(R[:, 0])


def test_kmeans_separates_two_blobs():
    rng = np.random.default_rng(1)
    F = np.r_[rng.normal(0, 0.01, (50, 3)), rng.normal(1, 0.01, (50, 3))]
    lab = hk.kmeans(F, 2)
    assert len(set(lab[:50])) == 1 and len(set(lab[50:])) == 1 and lab[0] != lab[-1]


def test_no_card_spans_a_part_the_groom_shows():
    # (round 37: cards are judged against their source) the test groom's part line is bare (the two locks lie either
    # side of x = 0): a visible part, so no card spans it or roots on it
    D, locks = _groom()
    cards = hk.cut(D, locks, C, S, side_of=side_of, triangles=600)
    St = cards[0]["_St"]
    vis = hk.part_visible(St, C, side_of)
    P0 = np.array([[0.0, y, 0.01] for y in (0.01, 0.0, -0.01)])
    assert np.all(vis.dip(P0) >= hk.PART_DIP), vis.dip(P0)
    head = [c for c in cards if c["cls"] == "head"]
    assert head and any(c.get("arch") for c in head)
    for c in head:
        sides = np.sign(St["root"][c["strands"], 0])
        assert len(set(sides.tolist())) == 1, "a card's strands come from both sides of the part"
        assert abs(c["P"][0, 0]) >= hk.PART_GAP - 1e-6, "a card's root on the part line"


def _covered_groom():
    """_groom plus a lock combed straight back over the part line (roots x -12..+12 mm, at the side locks' height):
    the part has no dip in this groom's surface."""
    D, locks = _groom()
    rng = np.random.default_rng(5)
    pts, n = [], 60
    for k in range(n):
        x, y0 = rng.uniform(-0.012, 0.012), rng.uniform(0.0, 0.03)
        t = np.linspace(0.0, 0.15, 40)
        pts.append(np.stack([np.full(40, x), y0 - t, 0.01 + 0.002 * rng.uniform(size=40)], 1))
    D = dict(D)
    D["pts"] = np.concatenate([D["pts"], np.concatenate(pts).astype(np.float32)])
    D["counts"] = np.r_[D["counts"], np.full(n, 40, np.int32)].astype(np.int32)
    D["lock"] = np.r_[D["lock"], np.full(n, 3, np.int32)].astype(np.int32)
    D["sub"] = np.r_[D["sub"], np.arange(n) % 4].astype(np.float32)
    D["rand"] = np.r_[D["rand"], rng.uniform(size=n)].astype(np.float32)
    D["radius"] = np.r_[D["radius"], np.full(n, 4e-5)].astype(np.float32)
    D["obj"] = np.r_[D["obj"], np.zeros(n, np.int32)].astype(np.int32)
    return D, locks + [{"name": "tg0_3"}]


def test_cover_row_may_span_a_part_the_groom_does_not_show(monkeypatch):
    # where the source groom's surface shows no part (no dip, no gap) the top cover row may run over it (Tess: the
    # groom's part is a soft line under fuzz; the part-safe arch of round 36 cut a V notch the groom doesn't have)
    monkeypatch.setattr(hk, "ARCH", 1)
    D, locks = _covered_groom()
    cards = hk.cut(D, locks, C, S, side_of=side_of, triangles=600)
    St = cards[0]["_St"]
    vis = hk.part_visible(St, C, side_of)
    P0 = np.array([[0.0, y, 0.01] for y in (0.01, 0.0, -0.01)])
    assert np.all(vis.dip(P0) < hk.PART_DIP), vis.dip(P0)
    arch = [c for c in cards if c.get("arch")]
    assert any(len(set(np.sign(St["root"][c["strands"], 0]).tolist())) == 2 for c in arch)
    # the round-36 rule (every part distance counts) keeps them to one side each
    monkeypatch.setattr(hk, "PART_VISIBLE", 0)
    cards = hk.cut(D, locks, C, S, side_of=side_of, triangles=600)
    St = cards[0]["_St"]
    for c in (c for c in cards if c.get("arch")):
        assert len(set(np.sign(St["root"][c["strands"], 0]).tolist())) == 1


def test_card_follows_its_clumps_wave_and_starts_at_its_first_roots():
    D, locks = _groom()
    cards = hk.cut(D, locks, C, S, side_of=side_of, triangles=600)
    St = cards[0]["_St"]
    c = max((c for c in cards if c["cls"] == "head" and c["layer"] == 0), key=lambda c: len(c["strands"]))
    # the centre line keeps the wave: its sideways swing (minus the drift) is most of the strands' own 8 mm
    P = c["P"]
    side = P[:, 0] - np.polyval(np.polyfit(P[:, 1], P[:, 0], 1), P[:, 1])
    assert np.ptp(side) > 0.008, np.ptp(side)
    # it starts within a few mm of its most upstream root (fitted at the same distance from each root, the card
    # started mid-way between the roots)
    roots = St["root"][c["strands"]]
    assert P[0, 1] > roots[:, 1].max() - 0.012, (P[0, 1], roots[:, 1].max())


def test_flyaways_are_single_strand_cards():
    D, locks = _groom()
    cards = hk.cut(D, locks, C, S, triangles=600)
    fly = [c for c in cards if c["cls"] == "fly"]
    assert fly and all(len(c["strands"]) == 1 for c in fly)
    assert all(float(np.max(c["hw"])) <= hk.FLY_W + 1e-9 for c in fly)


def test_bake_draws_each_cards_strands_into_its_island():
    D, locks = _groom()
    cards = hk.cut(D, locks, C, S, side_of=side_of, triangles=600)
    St = cards[0].pop("_St")
    B = hk.bake(cards, St, 256, 128)
    assert B["alpha"].shape == (128, 256) and B["tone"].shape == (128, 256)
    for c, (x, y, w, h) in zip(cards, B["islands"]):
        assert 0 <= x and x + w <= 256 and 0 <= y and y + h <= 128
        isl = B["alpha"][y:y + h, x:x + w]
        assert isl.max() > 0.2, "an island with nothing drawn"
        # the picture fades in at the root and out at the sides: no hard card edge
        assert isl[0].max() < 0.35 and isl[:, 0].max() < 0.35 and isl[:, -1].max() < 0.35
    # islands don't overlap
    occ = np.zeros((128, 256), int)
    for x, y, w, h in B["islands"]:
        occ[y:y + h, x:x + w] += 1
    assert occ.max() == 1


def test_shared_tiles_are_finer_than_unique_islands_and_every_card_wears_one():
    D, locks = _groom()
    cards = hk.cut(D, locks, C, S, side_of=side_of, triangles=600)
    St = cards[0].pop("_St")
    U = hk.bake(cards, St, 256, 128)
    B = hk.bake_tiles(cards, St, 256, 128, n=4)
    assert len(B["reps"]) < len(cards) and len(B["islands"]) == len(cards) == len(B["tint"])
    assert B["texel"] < U["texel"], "shared pictures should get more texels per mm than one island per card"
    for i, isl in enumerate(B["islands"]):
        assert isl == B["tile_islands"][B["tile"][i]]
    occ = np.zeros((128, 256), int)
    for x, y, w, h in B["tile_islands"]:
        assert 0 <= x and x + w <= 256 and 0 <= y and y + h <= 128
        occ[y:y + h, x:x + w] += 1
    assert occ.max() == 1
    assert np.all((B["tint"] >= 0.7) & (B["tint"] <= 1.4))


def test_atlas_stacks_the_bake_and_remaps_tile_uvs():
    D, locks = _groom()
    cards = hk.cut(D, locks, C, S, side_of=side_of, triangles=600)
    St = cards[0].pop("_St")
    Sx = {**hc.STRANDS, "atlas": 256, "source": "drawn"}
    top = hc.atlas(Sx, {})
    W = top["color"].shape[1]
    B = hk.bake(cards, St, W, 128)
    at = hc.atlas(Sx, {}, bake={**B, "key": "t"})
    assert at["color"].shape[0] == top["color"].shape[0] + 128 and at["rows"] == top["color"].shape[0]
    m = {"uv": np.array([[0.1, 0.0], [0.2, 1.0]], np.float32)}
    r = hc.remap_v(m, at)
    vb = 128 / at["rows_total"]
    assert np.allclose(r["uv"][:, 1], [vb, 1.0])
    # a baked card's uv lands in its island
    Ht, Hall = at["rows"], at["rows_total"]
    x, y, w, h = B["islands"][0]
    c = dict(cards[0])
    c["island"] = ((x + 0.5) / W, (x + w - 0.5) / W, 1 - (Ht + y + 0.5) / Hall, 1 - (Ht + y + h - 0.5) / Hall)
    c["tone_k"] = at["bake_k"]
    mm = hc.mesh([c], Sx, {}, at["tiles"])
    assert mm["baked"].all()
    assert mm["uv"][:, 0].min() >= x / W - 1e-6 and mm["uv"][:, 0].max() <= (x + w) / W + 1e-6
    assert mm["uv"][:, 1].min() >= 1 - (Ht + y + h) / Hall - 1e-6 and mm["uv"][:, 1].max() <= 1 - (Ht + y) / Hall + 1e-6


def test_head_cards_stay_under_the_strands_outer_surface():
    D, locks = _groom()
    St = hk.strands(D, locks)
    env = hk.envelope(St, C, deg=6.0)
    P = np.nanmean(St["Q"][:60, :30], 0) + np.array([0.0, 0.0, 0.02])  # a card lifted 2 cm over its strands
    c = {"P": P, "X": np.tile([1.0, 0, 0], (len(P), 1)), "hw": np.full(len(P), 0.002)}
    hk._under_envelope(c, env, C)
    e, r = env(c["P"])
    ok = np.isfinite(e)
    assert ok.sum() > 5 and (r[ok] <= e[ok] + 1e-4).all()


def test_shade_is_deeper_under_more_hair():
    D, locks = _groom()
    # a second sheet of the same strands 3 mm above the first: the lower one is under hair
    D2 = dict(D)
    up = D["pts"].copy()
    up[:, 2] += 0.003
    D2["pts"] = np.concatenate([D["pts"], up])
    for k in ("counts", "lock", "sub", "rand", "radius", "obj"):
        D2[k] = np.concatenate([D[k], D[k]])
    St = hk.strands(D2, locks)
    sh = hk.strand_shade(St, C, locks)
    n = len(D["counts"]) - 6  # (the lock strands of the lower sheet)
    lower, upper = sh[:n, 2:20].mean(), sh[len(D["counts"]):len(D["counts"]) + n, 2:20].mean()
    assert lower > upper + 0.1, (lower, upper)


def test_centre_line_does_not_kink_where_strands_end():
    """Staggered strand ends at different offsets made the clump mean jump (crumpled tail ends, b12)."""
    from hifipushie.hair_cards import _clump
    rng = np.random.default_rng(1)
    m, n = 12, 60
    A = np.full((m, n, 3), np.nan)
    for i in range(m):
        k = int(rng.integers(25, 60))
        off = rng.normal(0, 0.008, 2)
        A[i, :k] = np.stack([np.full(k, off[0]), np.full(k, off[1]), -np.arange(k) * 0.004], 1)
    c = _clump(A, np.arange(n) * 0.004, lambda P: P * 0 + np.array([0.0, -1.0, 0.0]), min_share=0.5, end_share=0.2)
    d = np.diff(c["P"], axis=0)
    T = d / np.linalg.norm(d, axis=1)[:, None]
    turn = np.degrees(np.arccos(np.clip((T[1:] * T[:-1]).sum(1), -1, 1)))
    assert turn.max() < 30, turn.max()


def test_clump_cards_taper_to_a_point_not_a_square_end():
    # g1_b15 (game distance, 1 m): square-cut card ends read as a sawtooth comb along the tail; the geometry tapers
    D, locks = _groom()
    cards = hk.cut(D, locks, C, S, side_of=side_of, triangles=600)
    for c in [c for c in cards if c["cls"] == "head" and not c.get("fly")][:10]:
        hw, s = np.asarray(c["hw"]), np.asarray(c["s"])
        mid = hw[(s > 0.3 * s[-1]) & (s < 0.7 * s[-1])].max()
        assert hw[-1] <= 0.2 * mid, (hw[-1], mid)


def test_head_layers_lie_close_over_frizzy_clumps():
    """A frizzy crown clump (spread along its normal 12 mm) keeps its head layers within ~2 mm of each other (b15: top
    cards 4-18 mm over the layer under them, the backdrop showing through along the crown); a tail keeps its volume."""
    from hifipushie import hair_clumps as hc
    sn = np.full(10, 0.012)
    gaps = [float(np.max(hc.layer_offset(sn, la + 1, "head") - hc.layer_offset(sn, la, "head"))) for la in (0, 1)]
    assert max(gaps) <= 0.0025, gaps
    assert float(np.max(hc.layer_offset(sn, 2, "tail") - hc.layer_offset(sn, 0, "tail"))) > 0.015


def test_side_head_layers_reach_clump_outer_strands():
    """On the head's sides the top head card lies on its clump's outer strands (silhgeo g0: cards 10-20 mm narrower than
    the groom at ear height, front at 1 m), the layers moving out together (gaps unchanged); over the crown nothing moves."""
    from hifipushie import hair_clumps as hc
    rng = np.random.default_rng(3)
    z = np.linspace(0.0, -0.08, 21)
    off = rng.normal(0, 0.005, 60)  # the clump's strands spread 5 mm along its normal (+x, out of the head's side)
    Q = np.stack([np.stack([np.full_like(z, 0.09 + o), np.zeros_like(z) + 0.002 * rng.normal(), z], 1) for o in off])
    Q = np.concatenate([Q, np.full((60, 160 - len(z), 3), np.nan)], 1)
    c = hc.fit(Q, hc._cen_of(np.array([0.0, 0.0, 0.03]), None), reference=True)
    assert c is not None and "out" in c
    mid = slice(len(c["P"]) // 4, len(c["P"]) // 2)
    assert np.all(np.abs(c["N"][mid, 0]) > 0.9), c["N"][mid]
    o90 = float(np.percentile(off - off.mean(), 90)) * float(np.sign(c["N"][mid, 0].mean()))
    assert abs(float(np.median(c["out"][mid])) - o90) < 0.002, (np.median(c["out"][mid]), o90)
    yo = [hc.card_offset(c, la, 3, "head", np.array([0.0, 0.0, 0.03])) for la in range(3)]
    assert float(np.median(yo[2][mid])) > o90 - 0.002  # the top layer at the outer strands
    for la in (0, 1):  # gaps between layers as layer_offset's
        g0 = hc.layer_offset(c["sn"], la + 1, "head") - hc.layer_offset(c["sn"], la, "head")
        assert np.allclose(yo[la + 1] - yo[la], g0)
    crown = {**c, "P": c["P"] + [-0.09, 0.0, 0.2]}  # the same clump over the crown: layer_offset alone
    assert np.allclose(hc.card_offset(crown, 2, 3, "head", np.zeros(3)), hc.layer_offset(c["sn"], 2, "head"))
    # a tail's layers move out together to its outer strands too (the tail beside the neck: cards +97 vs strands +111 mm)
    yt = [hc.card_offset(crown, la, 3, "tail", np.zeros(3)) for la in range(3)]
    top_t = hc.layer_offset(c["sn"], 2, "tail")
    want = top_t + hc.TAIL_OUT * np.maximum(0.0, c["out"] - top_t)
    assert np.allclose(yt[2], want) and np.all(yt[2] >= top_t - 1e-12)
    assert np.allclose(yt[1] - yt[0], hc.layer_offset(c["sn"], 1, "tail") - hc.layer_offset(c["sn"], 0, "tail"))


def test_face_wisp_cards_are_lit_and_lighter():
    """Face-framing wisps are drawn lighter and without the depth shade (wispL.py g1v1: the cards' wisps L* 38.6 vs the
    groom's 54, a quarter of its area), with more hairs per picture."""
    from hifipushie import hair_clumps as hc
    # (round 24: 10 hairs at alpha 0.9 drew the temple wisps as broad opaque pale sheets; 4 at 0.7 see-through, gSc-like)
    assert hc.WISP_LIFT > 0 and hc.WISP_KIDS_FACE >= 4 and hc.WISP_ALPHA < 0.9


def test_crown_loops_found_straight_hair_kept(monkeypatch=None):
    """A looping strand rooted on the crown is a crown loop (left out of head cards); a straight one and a loop rooted low are not."""
    from hifipushie import hair_clumps as hk_
    old = hk_.CROWN_LOOP
    hk_.CROWN_LOOP = 0.6
    a = np.linspace(0, 1.8 * np.pi, 40)
    loop = np.stack([0.02 * np.sin(a), 0.02 * (1 - np.cos(a)), 0.1 + 0.01 * a], 1)
    straight = np.stack([np.zeros(40), np.linspace(0, 0.1, 40), np.full(40, 0.1)], 1)
    low = loop - [0, 0, 0.1]
    Q = np.stack([loop, straight, low])
    St = {"Q": Q, "root": Q[:, 0], "len": np.array([np.linalg.norm(np.diff(q, axis=0), axis=1).sum() for q in Q])}
    try:
        assert hk_.crown_loops(St, np.zeros(3)).tolist() == [True, False, False]
    finally:
        hk_.CROWN_LOOP = old


def _dome_part_groom(n_per=90, seed=0):
    """Strands rooted along a centre part (x = 0) over a dome (radius 0.08 about the origin), each leaving the part
    sideways and rising 6 mm off the scalp over its first 2 cm, then lying on the dome down the side (a tied groom's
    top)."""
    rng = np.random.default_rng(seed)
    R = 0.08
    pts, counts, lock = [], [], []
    for li, sx in enumerate((-1.0, 1.0)):
        for k in range(n_per):
            y0 = rng.uniform(-0.05, 0.05)
            x0 = rng.uniform(0.001, 0.012)
            t = np.linspace(0.0, 0.12, 40)
            phi = np.arcsin(x0 / R) + t / R
            h = 0.006 * hk._ss(np.clip(t / 0.02, 0, 1)) + 0.0005 * rng.uniform()
            ry = np.sqrt(max(R * R - y0 * y0, 1e-6))
            P = np.stack([sx * np.sin(phi) * (ry + h), np.full(40, y0), np.cos(phi) * (ry + h)], 1)
            pts.append(P)
            counts.append(40)
            lock.append(li)
    n = len(counts)
    D = {"names": np.array(["hair_guides"]), "pts": np.concatenate(pts).astype(np.float32),
         "counts": np.array(counts, np.int32), "lock": np.array(lock, np.int32), "sub": np.zeros(n, np.float32),
         "rand": rng.uniform(size=n).astype(np.float32), "radius": np.full(n, 4e-5, np.float32),
         "obj": np.zeros(n, np.int32)}
    return D, [{"name": "tg0_1"}, {"name": "tg0_2"}]


def test_part_cover_row_arches_over_the_part_with_soft_tips(monkeypatch):
    D, locks = _dome_part_groom()
    C0 = np.zeros(3)
    monkeypatch.setattr(hk, "PART_FROM_STRANDS", 0.0)
    monkeypatch.setattr(hk, "ARCH", 0)  # (round 36: the arch row is on by default; its cards are "cover" too)

    def part_top(cards):
        P = np.concatenate([c["P"] for c in cards if c["cls"] == "head"])
        return float(P[np.abs(P[:, 0]) < 0.004, 2].max(initial=0.0))
    plain = hk.cut(D, locks, C0, S, side_of=side_of, triangles=1500)
    assert not any(c.get("cover") for c in plain)
    monkeypatch.setattr(hk, "PART_COVER", 4)
    cards = hk.cut(D, locks, C0, S, side_of=side_of, triangles=1500)
    St = cards[0]["_St"]
    cov = [c for c in cards if c.get("cover")]
    for sx in (-1.0, 1.0):  # a row on each side, front to back
        row = [c for c in cov if np.sign(St["root"][c["strands"], 0]).mean() * sx > 0.9]
        assert len(row) >= 3, f"side {sx}: {len(row)} cover cards"
        ys = sorted(float(np.mean(St["root"][c["strands"], 1])) for c in row)
        assert ys[-1] - ys[0] > 0.04, "the row runs along the part, front to back"
    for c in cov:
        P = np.asarray(c["P"], float)
        assert abs(P[0, 0]) < hk.COVER_OVER + 0.002, "a cover card starts on the part line"
        assert c["layer"] == len(hk.LAYERS["head"]) - 1
        hw = np.asarray(c["hw"], float)
        assert hw[-1] < 0.3 * hw.max(), "its tip tapers (a soft end on the side cards, not a cut)"
        assert float(np.asarray(c["s"])[-1]) < hk.COVER_LEN + 0.02
    # over the part the outline is the cover's arch (the strands rise 6 mm off the scalp), not the side cards' seated
    # roots
    assert part_top(cards) > part_top(plain) + 0.002
    r = np.linalg.norm(np.concatenate([c["P"] for c in cov]), axis=1)
    assert r.max() < 0.08 + 0.0065, "the cover stays under the strands"


def test_even_strands_take_the_nearest_scalp_locks_class():
    """An even groom's strands (hair_even, lock 0 for all) must not inherit lock 0's class: Garrett's G88a came out
    100% "tail" cards (lock 0 is a free stray) until each took its nearest scalp-rooted lock (c1, 2026-10-18)."""
    locks = [{"name": "stray", "free": 1.0, "pts": [[0.0, 0.0, 0.1], [0.0, 0.0, 0.0]]},
             {"name": "top", "pts": [[0.0, 0.0, 0.1], [0.0, 0.02, 0.1]]},
             {"name": "side", "pts": [[0.08, 0.0, 0.0], [0.08, 0.0, -0.02]]}]
    P = np.array([[0.001, 0.0, 0.1], [0.001, 0.02, 0.1], [0.079, 0.0, 0.0], [0.079, 0.0, -0.02]], float)
    D = {"names": np.array(["hair_even"]), "pts": P, "counts": np.array([2, 2]), "lock": np.array([0, 0]),
         "obj": np.array([0, 0]), "rand": np.array([0.1, 0.2]), "radius": np.array([4e-5, 4e-5])}
    St = hk.strands(D, locks)
    assert list(St["lock"]) == [1, 2]
    assert list(St["cls"]) == ["head", "head"]


def test_even_groom_is_cut_by_clumps_at_every_tier():
    """An even groom (strands.even) has no per-lock guide strands: below the hero tier clump_cards found none and the
    lifted cap alone stood as a pompadour (Garrett main / npc / far, c2 2026-10-18). Every tier cuts it by clumps."""
    from hifipushie import hair
    for t in hair.CARD_TIERS:
        assert hair.tier_settings(t, short=False, even=True).get("cut") == "clumps"
    assert hair.tier_settings("main").get("cut") != "clumps"  # a guide-strand groom keeps its per-lock cut


def test_cap_without_cards_keeps_its_height_when_asked():
    """cap_under_cards: a vertex with no card near lies at the floor (CAP_BARE_FLOOR), unless bare_floor=False (an even
    groom's cap at the hair's mid height: on the floor it was bare scalp, c1d); under a card it never stands over it."""
    from hifipushie import hair
    sc = hair.Scalp.__new__(hair.Scalp)
    sc.C = np.zeros(3)
    sc.r = lambda az, el: np.full(np.shape(az), 0.1)
    d = np.array([[0, 0, 1.0], [1.0, 0, 0]])
    V = d * 0.115  # 15 mm over the scalp
    card = {"P": np.array([[0, -0.01, 0.11], [0, 0.01, 0.11]]), "X": np.array([[1.0, 0, 0]] * 2), "hw": np.array([0.005, 0.005])}
    h0 = np.linalg.norm(hair.cap_under_cards(sc, V, [card], 0.002, bare_floor=True), axis=1) - 0.1
    h1 = np.linalg.norm(hair.cap_under_cards(sc, V, [card], 0.002, bare_floor=False), axis=1) - 0.1
    assert h0[0] < 0.0085 and h1[0] < 0.0085  # under the card (its edges ~10.3 mm up, less CAP_UNDER)
    assert h0[1] < 0.0025 and abs(h1[1] - 0.015) < 1e-4  # the side vertex: floor vs kept


def test_card_grey_follows_its_locks():
    """Cards' grey-hair share comes from their strands' locks (Garrett's silver sides, c2): tiles are clustered on it and
    each draws its own share, not the head's one."""
    locks = [{"name": "top", "inputs": {"Grey": 0.2}}, {"name": "side", "inputs": {"Grey": 0.7}}]
    St = {"lock": np.array([0, 0, 1, 1])}
    cards = [{"strands": [0, 1]}, {"strands": [2, 3]}, {"strands": [1, 2]}]
    g = hk.card_grey(cards, St, locks, {"grey_locks": 1.0})
    assert np.allclose(g, [0.2, 0.7, 0.45])
    assert hk.card_grey(cards, St, [{"name": "a"}, {"name": "b"}], {}) is None


def test_no_card_spans_the_part():
    D, locks = _groom()
    cards = hk.cut(D, locks, C, S, side_of=side_of, triangles=600)
    St = cards[0]["_St"]
    head = [c for c in cards if c["cls"] == "head"]
    assert head
    for c in head:
        sides = np.sign(St["root"][c["strands"], 0])
        assert len(set(sides.tolist())) == 1, "a card's strands come from both sides of the part"
        assert abs(c["P"][0, 0]) >= hk.PART_GAP - 1e-6, "a card's root on the part line"


def test_envelope_grade_spreads_a_back_step():
    """(c13) GRADE_SLOPE: a 6 mm step in the strands' radius on the back (elev 30) is spread down over GRADE_BAND at the
    slope; the front (|az| < GRADE_AZ) and everything above the step are untouched."""
    import numpy as np
    from hifipushie import hair_clumps as hk
    C = np.zeros(3)
    rng = np.random.default_rng(0)
    pts = []
    for az in (0.0, 180.0):
        for el in np.arange(0.5, 60, 1.0):
            r = 0.100 + (0.006 if el >= 30 else 0.0)
            a, e = np.radians(az + rng.uniform(-1, 1, 400)), np.radians(el + rng.uniform(-0.4, 0.4, 400))
            pts.append(np.stack([r * np.cos(e) * np.sin(a), -r * np.cos(e) * np.cos(a), r * np.sin(e)], 1))
    Q = np.concatenate(pts)
    St = {"Q": Q[:, None, :].repeat(2, 1), "cls": np.array(["head"] * len(Q))}
    plain, graded = hk.envelope(St, C, pct=90), hk.envelope(St, C, pct=90, grade=0.0003)

    def at(az, el):
        a, e = np.radians(az), np.radians(el)
        return np.array([[np.cos(e) * np.sin(a), -np.cos(e) * np.cos(a), np.sin(e)]]) * 0.1
    for el, want in ((40, 0.0), (28.5, 0.006 - 0.0003 * 3), (19.5, 0.006 - 0.0003 * 12), (4.5, 0.0)):
        d = float(graded(at(179, el))[0][0] - plain(at(179, el))[0][0])
        assert abs(d - max(want, 0.0)) < 6e-4, (el, d, want)
    assert abs(float(graded(at(1, 20))[0][0] - plain(at(1, 20))[0][0])) < 1e-9  # the front: no grade
