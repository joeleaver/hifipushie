"""Strand grooms and the game cards cut from them (hair_strands.py, hair_cards.clump_cards, hair_checks.py).

The incidents these reproduce (2026-10-06): a path tracer drew 30k strands at 0.08 mm as a pale haze; card tiers
"corrupted": a dark band where layer 0 showed, baby-hair cards as brown stamps under an alpha test, the tail as a
lattice of thin ribbons, budgets that kept baby hairs and dropped coverage, wisps as dark slashes that started on
bare skin. `uv run python tests/test_hair_strands.py`; the last test needs Blender and the workspace model hs_tess.
"""

import os

import numpy as np

from hifipushie import hair_cards as hc
from hifipushie import hair_checks as hk
from hifipushie import hair_strands as hs


def _lock(name, P, width=0.03, free=1.0, core=None):
    return {"name": name, "pts": np.asarray(P, float).tolist(), "handles": None, "radius": None, "tilt": None,
            "inputs": {"Width": width, "Thickness": 0.005, "Cup": 0.0, "Taper": 0.3, "Belly": 0.3, "Root": 0.8,
                       "Twist": 0.0, "Flip": 0.0}, "free": free, "core": core}


def _strands(locks, per=60, subs=4, spread=0.012, wave=0.0, seed=0, n=24):
    """Fake evaluated strands: per lock `per` strands in `subs` sub clumps side by side (x), ragged tips."""
    rng = np.random.default_rng(seed)
    pts, counts, lock, sub, rand, obj = [], [], [], [], [], []
    for li, lk in enumerate(locks):
        P, *_ = hc.spine(lk, n)
        s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
        for k in range(per):
            sb = k % subs
            x = ((sb + 0.5) / subs - 0.5) * 2 * spread + rng.normal(0, spread / subs / 4)
            m = int(n * rng.uniform(0.75, 1.0))
            Q = P[:m] + np.array([x, 0.0, 0.0]) + np.array([1.0, 0, 0]) * wave * np.sin(2 * np.pi * s[:m] / 0.08)[:, None]
            Q = Q + np.array([0.0, rng.normal(0, 0.001), 0.0])
            pts.append(Q)
            counts.append(m)
            lock.append(li)
            sub.append(sb)
            rand.append(rng.uniform())
            obj.append(0)
    return {"pts": np.concatenate(pts).astype(np.float32), "counts": np.asarray(counts, np.int32),
            "lock": np.asarray(lock, np.int32), "sub": np.asarray(sub, np.float32), "rand": np.asarray(rand, np.float32),
            "radius": np.zeros(len(counts), np.float32), "obj": np.asarray(obj, np.int32),
            "names": np.asarray(["hair_guides_free"])}


def _hanging(n=3):
    return [_lock(f"l{i}", [[0.05 * i, 0.12, 0.0], [0.05 * i, 0.12, -0.1], [0.05 * i, 0.12, -0.2], [0.05 * i, 0.12, -0.3]])
            for i in range(n)]


def test_radius_by_count():
    """Fewer strands are drawn wider, so the head stays covered at true widths (a path tracer has no 1 px floor)."""
    S = dict(hc.STRANDS)
    r30, r100 = hs.physical({**S, "count": 30000})["radius"], hs.physical({**S, "count": 100000})["radius"]
    assert abs(r100 - hs.STRAND_RADIUS) < 1e-9, r100
    assert 2.0 < r30 / r100 < 3.0, (r30, r100)
    assert 30000 * r30 > 0.7 * 100000 * r100  # covers nearly as much
    ph = hs.physical({**S, "frizz": 5.0, "flyaway": 9.0})
    assert ph["frizz"] <= hs.SAFE["frizz_m"] and ph["flyaway"] <= hs.SAFE["flyaway"]  # dials can't reach a cloud


def test_lock_grey_reaches_the_strands():
    """A lock's own grey (greying temples, sideburns) is the share of grey strands it grows (hp_gr per guide)."""
    locks = _hanging(2)
    locks[0]["inputs"]["Grey"] = 0.4
    G = hs.lock_guides(locks, np.zeros(3), hc.strands_of({}))
    assert np.allclose(G["free"]["gr"], [0.4, 0.0])


def test_grey_share_in_the_card_atlas():
    """The cards' pictures draw the look's share of grey strands (a threshold on the strand id: no speckle), and
    none without a share."""
    S = {**hc.strands_of({}), "atlas": 256, "source": "drawn"}
    look = {"gap": "#201810", "lit": "#402818", "grey": "#c0c0c0", "vary": 0.0}
    a0 = hc.atlas(S, look)
    a1 = hc.atlas(S, {**look, "grey_share": 0.5})
    m = a0["color"][..., 3] > 0.5
    b0 = a0["color"][..., 2][m]
    b1 = a1["color"][..., 2][m]
    assert b1.mean() > b0.mean() + 0.05 and (b1 > b0.max() + 0.1).mean() > 0.1  # grey strands are there
    assert (b1 <= b0 + 1e-6).mean() > 0.2  # and dark ones stay


def test_join_of_nothing_is_an_empty_mesh():
    """A far tier of a short cut has no cards (no hair off the head): joining nothing gives the empty mesh back."""
    S = hc.strands_of({})
    e = hc.mesh([], S, {}, hc.atlas({**S, "atlas": 256, "source": "drawn"}, {})["tiles"])
    assert len(hc.join(None, e, e)["tris"]) == 0


def test_short_hair_is_drawn_on_the_cap():
    """A short cut's own strands (hair off its locks, lying on the head) are drawn in the scalp chart when the cut
    is short: the cap carries the look; otherwise only the scalp layer is."""
    from hifipushie import hair
    A = np.arange(0.0, 360.0, hair.Scalp.STEP)
    E = np.arange(hair.Scalp.EL[0], hair.Scalp.EL[1] + 1e-6, hair.Scalp.STEP)
    sc = hair.Scalp([0.0, 0.0, 1.7], np.full((len(A), len(E)), 0.09), {})
    g = hair.groom_params({"hair": {"groom": {"parting": {"side": "none"}}}})
    line = np.full(360, -20.0)
    P = sc.point(np.linspace(80.0, 100.0, 12), np.full(12, 30.0), np.full(12, 0.006))  # a strand 6 mm over the scalp
    D = {"pts": P.astype(np.float32), "counts": np.array([12], np.int32), "lock": np.array([0], np.int32),
         "sub": np.zeros(1, np.float32), "rand": np.array([0.9], np.float32), "radius": np.zeros(1, np.float32),
         "obj": np.array([0], np.int32), "names": np.array(["hair_guides_free"])}
    S = {**hc.strands_of({}), "soft": 0.008}
    c0 = hs.cap_chart(sc, g, line, S, D, float(hair.Scalp.EL[0]), 256)
    c1 = hs.cap_chart(sc, g, line, S, D, float(hair.Scalp.EL[0]), 256, short=True)
    assert np.abs(c1["id"] - c0["id"]).max() > 0.2  # the strand's own id is in the short chart only
    assert (np.abs(c1["id"] - 0.9) < 0.05).sum() >= 8 and (np.abs(c0["id"] - 0.9) < 0.05).sum() == 0


def _ball_scalp():
    from hifipushie import hair
    A = np.arange(0.0, 360.0, hair.Scalp.STEP)
    E = np.arange(hair.Scalp.EL[0], hair.Scalp.EL[1] + 1e-6, hair.Scalp.STEP)
    sc = hair.Scalp([0.0, 0.0, 1.7], np.full((len(A), len(E)), 0.09), {})
    g = hair.groom_params({"hair": {"groom": {"parting": {"side": "none"}}}})
    return sc, g, np.full(360, -20.0), float(hair.Scalp.EL[0])


def _crop(sc, n=4000, length=0.02, seed=0, lean=(1.0, 0.0), h=(0.001, 0.008)):
    """Short strands all over the ball above el 0: each runs `length` along `lean` (east, up) rising from h[0] to
    a height up to h[1]. The D dict a strands dump gives."""
    rng = np.random.default_rng(seed)
    az0, el0 = rng.uniform(0, 360, n), np.degrees(np.arcsin(rng.uniform(0.0, 0.95, n)))
    k = 8
    t = np.linspace(0, 1, k)[None]
    R = 0.09
    az = az0[:, None] + np.degrees(lean[0] * length * t / (R * np.cos(np.radians(el0))[:, None]))
    el = el0[:, None] + np.degrees(lean[1] * length * t / R)
    top = rng.uniform(h[0], h[1], n)[:, None]
    hh = h[0] + (top - h[0]) * t
    P = sc.point(az.ravel(), el.ravel(), hh.ravel())
    return {"pts": P.astype(np.float32), "counts": np.full(n, k, np.int32), "lock": rng.integers(0, 2, n).astype(np.int32),
            "sub": np.zeros(n, np.float32), "rand": rng.uniform(0, 1, n).astype(np.float32),
            "radius": np.zeros(n, np.float32), "obj": np.zeros(n, np.int32), "names": np.array(["hair_guides_free"])}


def test_baked_cap_is_hair_mass():
    """The short cut's cap chart (hair_cap): opaque wherever the groom is dense (no skin between the strands of a
    full head), bare where there is no hair; the top strand of a texel wins; a strand keeps its width in METRES up
    the head; the hair's own height comes back as the cap's lift."""
    from hifipushie import hair_cap
    sc, g, line, e0 = _ball_scalp()
    S = {**hc.strands_of({}), "soft": 0.008}
    D = _crop(sc, n=30000)
    c = hair_cap.chart(sc, g, line, S, D, [{"name": "a", "grey": 0.0}, {"name": "b", "grey": 0.0}], e0, 512)
    H = 512
    row = lambda el: int((1 - (el - e0) / (90.0 - e0)) * H)  # noqa: E731
    assert c["alpha"][row(60):row(10)].min() > 0.98, c["alpha"][row(60):row(10)].min()  # a full head: no hole in it
    assert c["alpha"][row(-30):].max() < 0.02  # under the hair's lower edge (el 0 - soft) nothing
    assert c["cover"][row(60):row(10)].mean() > 0.9  # ...and it is strands, not only the base
    assert 0.2 < c["depth"][row(60):row(10)].mean() < 0.9 and c["depth"][row(60):row(10)].std() > 0.03  # shade between hairs
    lift = hair_cap.lift_at(c["lift"], np.array([10.0, 200.0]), np.array([40.0, 40.0]))
    assert (lift > 0.002).all() and (lift < 0.009).all(), lift  # the hair stands 1-8 mm: its upper middle
    ch = hair_cap.cap_height(c["lift"], np.array([0.05, 0.0]), np.array([10.0, 10.0]), np.array([40.0, 40.0]))
    assert ch[0] > 0.001 and ch[1] == 0.0  # the cap stands in the hair, and comes down to the skin at the hairline
    # one strand low and one high, crossing: the high one's id is what shows where they cross
    lo = sc.point(np.linspace(80.0, 100.0, 12), np.full(12, 30.0), np.full(12, 0.002))
    hi = sc.point(np.full(12, 90.0), np.linspace(25.0, 35.0, 12), np.full(12, 0.008))
    D2 = {"pts": np.r_[lo, hi].astype(np.float32), "counts": np.array([12, 12], np.int32), "lock": np.zeros(2, np.int32),
          "sub": np.zeros(2, np.float32), "rand": np.array([0.1, 0.9], np.float32), "radius": np.zeros(2, np.float32),
          "obj": np.zeros(2, np.int32), "names": np.array(["hair_guides_free"])}
    c2 = hair_cap.chart(sc, g, line, S, D2, [{"name": "a"}], e0, 1024, width=0.002)
    y, x = int((1 - (30.0 - e0) / (90.0 - e0)) * 1024), int(90.0 / 360.0 * 1024)
    assert abs(c2["id"][y, x] - 0.9) < 0.05, c2["id"][y, x]
    # the same strand low on the head and high on it covers the same AREA of scalp (its texels differ 2x)
    areas = []
    for el in (10.0, 60.0):
        w_ = np.degrees(0.02 / (0.09 * np.cos(np.radians(el))))
        P = sc.point(np.linspace(90.0, 90.0 + w_, 12), np.full(12, el), np.full(12, 0.004))
        D3 = {**D2, "pts": P.astype(np.float32), "counts": np.array([12], np.int32), "lock": np.zeros(1, np.int32),
              "sub": np.zeros(1, np.float32), "rand": np.array([0.5], np.float32), "radius": np.zeros(1, np.float32),
              "obj": np.zeros(1, np.int32)}
        c3 = hair_cap.chart(sc, g, line, S, D3, [{"name": "a"}], e0, 1024, width=0.002)
        mu = 2 * np.pi * 0.09 * np.cos(np.radians(el)) / 1024
        mv = np.radians(90.0 - e0) * 0.09 / 1024
        areas.append(float(c3["cover"].sum() * mu * mv))
    assert abs(areas[0] / areas[1] - 1) < 0.2 and abs(areas[0] / (0.02 * 0.002) - 1) < 0.35, areas


def test_baked_cap_flow_and_grey():
    """The flow map is the strands' direction (east / up in the chart's tangent space), and a lock's grey share is
    its own strands' (per region), scaled by look.card_grey."""
    from hifipushie import hair_cap
    sc, g, line, e0 = _ball_scalp()
    S = {**hc.strands_of({}), "soft": 0.008}
    locks = [{"name": "a", "grey": 0.0}, {"name": "b", "grey": 1.0}]
    for lean, want in (((1.0, 0.0), 0), ((0.0, 1.0), 1)):
        D = _crop(sc, n=20000, lean=lean)
        c = hair_cap.chart(sc, g, line, S, D, locks, e0, 512, {"card_grey": 1.0})
        fl = c["flow"][120:300]
        assert np.abs(fl[..., want]).mean() > 0.9 and fl[..., 2].mean() > 0.8, (lean, np.abs(fl[..., :2]).mean((0, 1)))
        n = c["normal"][120:300]
        assert n[..., 2].min() > 0.5 and abs(np.linalg.norm(n, axis=-1) - 1).max() < 1e-3  # a relief, never a cliff
    D["lock"][:] = (np.arange(len(D["lock"])) % 2)  # half the strands in the all-grey lock
    full = hair_cap.chart(sc, g, line, S, D, locks, e0, 512, {"card_grey": 1.0})["grey"][120:300].mean()
    half = hair_cap.chart(sc, g, line, S, D, locks, e0, 512, {"card_grey": 0.5})["grey"][120:300].mean()
    assert 0.35 < full < 0.65 and 0.15 < half < 0.35, (full, half)


def test_strands_key_is_the_content():
    """The same strands job written twice (its npz files carry the time they were zipped) has ONE key: the groom is
    evaluated once for a look and every tier of an export, not once each."""
    import tempfile, time
    from pathlib import Path
    keys = []
    for i in range(2):
        d = Path(tempfile.mkdtemp())
        for nm in ("g", "s", "c"):
            np.savez(d / f"{nm}.npz", pts=np.arange(30, dtype=np.float32).reshape(10, 3), n=np.arange(4))
        sd = {"scalp": str(d / "s.npz"), "collide": str(d / "c.npz"), "look": {"lit": "#%06x" % i}, "physical": {"count": 5},
              "groups": [{"name": "hair_guides", "guides": str(d / "g.npz"), "stack": [["x", {"a": 1.0}]]}], "e0": -70.0}
        keys.append(hs.key(sd))
        time.sleep(2.1)
    assert keys[0] == keys[1], keys


def test_short_tiles_are_few_thick_strands():
    """A short cut's card tiles: a few strands several texels thick (they survive as strands 3-4 mips down), not a
    hundred 1-texel hairs that average to a film."""
    S = {**hc.strands_of({}), "atlas": 512}
    lk = {"lit": "#54463c", "gap": "#3a312b", "grey": "#cfc7bd"}
    a0 = hc.atlas(S, lk, key="t0")
    a1 = hc.atlas({**S, "short": True}, lk, key="t1")
    t0 = next(t_ for t_ in a0["tiles"] if t_["kind"] == "medium")
    x0, x1 = int(t0["u0"] * 512), int(t0["u1"] * 512)
    cov = lambda at: float((at["color"][100:300, x0:x1, 3] > 0.5).mean())  # noqa: E731
    c0, c1 = cov(a0), cov(a1)
    assert 0.05 < c1 < 0.5 and c1 < 0.75 * c0, (c0, c1)  # open: the cap shows between a card's strands
    assert a1["flow"].shape[2] == 3 and abs(float(a1["flow"][5, 5, 1]) - 1.0) < 1e-6  # a card's hair runs down its picture


def test_gather_reaches_the_tie():
    assert hs.is_gather({"name": "tg0_12"}) and hs.is_gather({"name": "t1g2_3"})
    assert not hs.is_gather({"name": "tt4"}) and not hs.is_gather({"name": "sweep1"})


def test_clump_cards_follow_the_strands():
    """A card's centre line is its clump's strands' mean: it waves with them; a coarser group = fewer, wider cards."""
    locks = _hanging(3)
    D = _strands(locks, wave=0.01)
    S = {**hc.STRANDS, "layers": 2, "card_width": 0.012, "segment": 0.01, "group": "sub"}
    sub = hc.clump_cards(D, locks, np.zeros(3), S)
    lock = hc.clump_cards(D, locks, np.zeros(3), {**S, "group": "lock", "layers": 1, "card_width": 0.04})
    assert len(sub) > 2 * len(lock) >= 6, (len(sub), len(lock))
    w = lambda cs: float(np.median([2 * c["hw"].max() for c in cs if c["layer"] == 0]))  # noqa: E731
    assert w(lock) > 1.5 * w(sub), (w(lock), w(sub))
    c = next(c for c in lock if c["lock"] == "l0")
    x = c["P"][:, 0]
    assert np.ptp(x) > 0.012, np.ptp(x)  # the strands' 1 cm swing is in the card (a straight plank has none)
    # every strand's root region is covered: the card starts where its first strands do
    assert c["P"][0, 2] > -0.03, c["P"][0]


def test_budget_drops_coverage_last():
    locks = _hanging(3)
    D = _strands(locks)
    S = {**hc.STRANDS, "layers": 3, "card_width": 0.012, "segment": 0.01, "group": "sub", "fly": 2}
    cards = hc.clump_cards(D, locks, np.zeros(3), S)
    full = hc.triangles(cards, S)
    kept, seg, info = hc.fit_budget(cards, S, full // 3)
    assert info["triangles"] <= full // 3 and seg <= S["segment"] * 1.5 + 1e-9, info
    n0 = lambda cs: sum(c["layer"] == 0 for c in cs)  # noqa: E731
    assert n0(kept) >= 0.9 * n0(cards) or all(c["layer"] == 0 for c in kept), (n0(kept), n0(cards))
    assert max(c["layer"] for c in kept) <= max(c["layer"] for c in cards)


def test_tail_core_inside_the_strands():
    core = [[0.0, 0.12, 0.0], [0.0, 0.12, -0.3]]
    locks = []
    for i in range(8):
        a = 2 * np.pi * i / 8
        x, y = 0.02 * np.cos(a), 0.12 + 0.02 * np.sin(a)
        locks.append(_lock(f"tt{i}", [[x, y, 0.0], [x, y, -0.1], [x, y, -0.2], [x, y, -0.3]], core=core))
    D = _strands(locks, per=40, spread=0.006)
    tc = hc.tail_cores(D, locks, sides=8)
    assert tc is not None and len(tc["tris"]) > 100
    r = np.hypot(tc["verts"][:, 0], tc["verts"][:, 1] - 0.12)
    assert 0.008 < np.median(r) < 0.024, np.median(r)  # inside the ring of locks, not a thread and not outside
    m = hc.core_mesh(tc, [{"kind": "dense", "u0": 0.0, "u1": 0.1}])
    assert m["uv"][:, 0].min() >= 0 and m["uv"][:, 0].max() <= 0.1 + 1e-6


class _Ball:
    """A head as the scalp's rays see it: a sphere of 0.1 m."""
    EL = np.array([-60.0, 90.0])

    def coords(self, P):
        r = np.linalg.norm(P, axis=1)
        return (np.degrees(np.arctan2(P[:, 0], -P[:, 1])) % 360, np.degrees(np.arcsin(np.clip(P[:, 2] / np.maximum(r, 1e-9), -1, 1))),
                r - 0.1)

    def point(self, az, el, h):
        a, e = np.radians(az), np.radians(el)
        d = np.stack([np.sin(a) * np.cos(e), -np.cos(a) * np.cos(e), np.sin(e)], -1)
        return d * (0.1 + np.asarray(h))[..., None]


def test_cards_kept_out_of_the_head():
    from hifipushie import hair
    sc = _Ball()
    V = np.array([[0.0, -0.095, 0.02], [0.0, -0.11, 0.02], [0.05, -0.08, 0.03]], np.float32)  # 1st and 3rd inside
    M = {"verts": V, "card": np.array([0, 0, 1])}
    r = hair.card_clearance(sc, M, ["wisp", "side"], fix=0.0015)
    assert r["under"] == 2 and r["deepest_mm"] > 2 and "wisp" in r["locks"], r
    assert (np.linalg.norm(M["verts"], axis=1) >= 0.1 + 0.0014).all()
    assert hk.mesh_verdict({**r, "deepest_mm": 5.0})[0].startswith("WARNING")
    assert "detached wisp ts1" in hk.mesh_verdict({"detached": {"ts1": -4.0}})[0]


def test_checks_see_stamps_and_planks():
    """The measures fire on what was called corrupted: a quad on the skin, a silhouette of straight edges."""
    bald = np.full((200, 200, 3), 200, np.uint8)
    yy, xx = np.mgrid[:200, :200]
    blob = ((xx - 100) ** 2 + (yy - 70) ** 2 < 45 ** 2) & (np.sin(xx * 0.9) * np.cos(yy * 0.7) > -0.6 + ((xx - 100) ** 2 + (yy - 70) ** 2) / 45 ** 2 * 0.55)
    strands = bald.copy()
    strands[blob] = (120, 70, 40)
    tier = strands.copy()
    tier[150:165, 30:52] = (120, 70, 40)  # a card's rectangle on bare skin
    tier[170:171, 20:120] = (120, 70, 40)  # a single long hair: not a stamp
    st = hk.stamps(hk.hair_mask(tier, bald))
    assert st["stamps"] == 1 and st["worst"] > 0.8, st
    assert hk.stamps(hk.hair_mask(strands, bald))["stamps"] == 0
    square = bald.copy()
    square[40:160, 40:160] = (120, 70, 40)
    assert hk.straight_share(hk.hair_mask(square, bald)) > 0.8
    assert hk.straight_share(blob) < 0.5
    same = hk.compare(strands, strands, bald)
    assert same["iou"] == 1.0 and same["missing"] == 0.0 and abs(same["value"] - 1) < 1e-6
    dark = strands.copy()
    dark[blob] = (60, 35, 20)
    views = {"front": hk.compare(strands, dark, bald)}
    assert any("value" in w for w in hk.verdict(views)), hk.verdict(views)
    half = strands.copy()
    half[:, 100:] = bald[:, 100:]
    assert any("bare" in w for w in hk.verdict({"front": hk.compare(strands, half, bald)}))


def test_tiers_are_fewer_and_wider():
    from hifipushie import hair
    T = hair.CARD_TIERS
    order = ["hero", "main", "npc", "far"]
    assert [T[k]["triangles"] for k in order] == sorted((T[k]["triangles"] for k in order), reverse=True)
    assert [T[k]["card_width"] for k in order] == sorted(T[k]["card_width"] for k in order)
    assert T["far"]["group"] == "free" and T["hero"]["group"] == "sub"


def test_export_tier_as_an_engine_gets_it():
    """With Blender and the workspace model: one tier exported, re-imported, judged against the strands."""
    from hifipushie import hair, store
    name = os.environ.get("HIFIPUSHIE_HAIR_TEST_MODEL", "hs_tess")
    try:
        store.load(name)
    except Exception:  # noqa: BLE001
        print("  (skipped: no workspace model", name + ")")
        return
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        rep = hair.export_hair(name, tmp, tiers=("npc",), groom=False, check=True)
        t = rep["tiers"]["npc"]
        assert t["triangles"] <= hair.CARD_TIERS["npc"]["triangles"], t["triangles"]
        ch = rep["checks"]["npc"]
        for mode in ("test", "dither"):
            for v, r in ch[mode].items():
                assert r["stamps"] == 0, (mode, v, r)
                assert r["missing"] < 0.35 and r["iou"] > 0.65, (mode, v, r)
                assert 0.7 < r["value"] < 1.25, (mode, v, r)
        assert not (t["clearance"] or {}).get("detached") or len(t["clearance"]["detached"]) <= 1, t["clearance"]


def test_atlas_edges_are_padded_not_black():
    """Transparent and anti-aliased texels carry the strands' own colour (edge padding): black or dark RGB under
    the alpha bleeds in through filtering and mips as a dark fringe round every card (Godot)."""
    S = {**hc.strands_of({}), "atlas": 512, "short": True}
    lk = {"lit": "#54463c", "gap": "#3a312b", "grey": "#cfc7bd"}
    at = hc.atlas(S, lk, key="edges")
    c = at["color"]
    a = c[..., 3]
    lum = c[..., :3] @ np.array([0.2126, 0.7152, 0.0722])
    core, rim, clear = a > 0.8, (a > 0.03) & (a < 0.5), a < 0.03
    assert core.any() and rim.any() and clear.any()
    assert np.median(lum[clear]) > 0.5 * np.median(lum[core]), (np.median(lum[clear]), np.median(lum[core]))
    assert np.median(lum[rim]) > 0.85 * np.median(lum[core]), (np.median(lum[rim]), np.median(lum[core]))


def test_wisp_opens_and_is_sparse():
    """A thin free lock (a face-framing wisp) is a few strands drifting apart, not a comb strip: its section opens
    toward the tip and goes round, and it gets fewer strands for its section than a ribbon would (Tess, 2026-10-09)."""
    S = {**hc.STRANDS, "wave": 0.0}
    wisp = _lock("tf0", [[0.06, -0.08, 0.0], [0.06, -0.08, -0.04], [0.06, -0.08, -0.08], [0.06, -0.08, -0.12]], width=0.005)
    G = hs.lock_guides([wisp], np.zeros(3), S)["free"]
    side = np.linalg.norm(np.asarray(G["side"], float).reshape(-1, 3), axis=1)
    out = np.linalg.norm(np.asarray(G["out"], float).reshape(-1, 3), axis=1)
    assert side[-1] > 2.0 * side[0], (side[0], side[-1])  # opens toward the tip
    assert out[-1] > 0.8 * side[-1]  # round, not a ribbon
    hs.WISP_FAN, old = 0.0, hs.WISP_FAN
    try:
        G0 = hs.lock_guides([wisp], np.zeros(3), S)["free"]
    finally:
        hs.WISP_FAN = old
    assert float(np.sum(G["weight"])) < 0.5 * float(np.sum(G0["weight"]))  # sparser than the old comb


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)


def test_lock_density_scales_its_strand_share():
    """strands.density on a lock: x its strands, absolute (an airy region), 1 = unchanged; kept apart from the share."""
    S = {**hc.STRANDS, "wave": 0.0}
    P = [[0.0, -0.09, 0.05], [0.0, -0.06, 0.08], [0.0, -0.02, 0.1], [0.0, 0.03, 0.1]]
    a = _lock("a", P, free=0.0)
    b = dict(_lock("b", P, free=0.0), strands={"density": 0.5})
    G = hs.lock_guides([a, b], np.zeros(3), S)["head"]
    w, d = np.asarray(G["weight"], float), np.asarray(G["density"], float)
    assert abs(w[1] / w[0] - 1.0) < 1e-6 and d.tolist() == [1.0, 0.5], (w, d)
