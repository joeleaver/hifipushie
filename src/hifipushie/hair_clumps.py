"""Hair cards cut by CLUMPS and textured from their own strands, the way shipped card pipelines do it.

The lock cut (hair_cards.clump_cards) gives one card per groom lock: a 38 mm lock with 9-16 cards' worth of waves became
one flat ribbon, and a generic strand tile on it. Card artists and Epic's Hair Card Generator work the other way round:
  1. group the strands into visual CLUMPS ("strands that converge, creating a distinct volume"), per layer: a few wide
     coverage cards (Epic's tutorial: 50 clumps / 2k triangles), more mid cards (200 / 7.5k), many thin top cards,
     and flyaways as one card per single strand;
  2. fit each card to its clump: the centre line is the clump's mean path at the same distance from the root (so it
     bends with the wave), the width its strands' spread there;
  3. bake each card's picture from ITS strands, projected along the card normal into the card's own (across, along)
     frame: coverage (alpha), strand id, depth in the clump, root-to-tip, and the strands' direction (flow). The card
     then carries the clump's real waves, separation, tip taper and variation (Epic: Depth / Coverage / Tangent /
     Attributes; FiberBake does the same in Blender).
The part: top cards are clustered PER SIDE of the part (a side key in the clustering), so no card spans it, and every
card's root fades in over its first millimetres (roots crossing at the part read as a criss-cross). The cap under the
cards carries the part's own picture (hair_strands.cap_chart).

Everything is numpy + PIL: `cut` returns card dicts like hair_cards' (P, X, N, hw, u, s, kind, layer, prio, ...) with an
"island" key, and `bake` draws the islands into one block that hair_cards.atlas puts under its tiles.
"""

from __future__ import annotations

import hashlib

import numpy as np

STEP = 0.004  # m between stations along a clump (absolute distance from the root)
# per class of hair: its layers as (share of the cards' triangles, max card half width m, share of the clump's strands
# drawn). Epic's Hair Card Generator tutorial (a 54k hero updo): coverage 4 %, mid 14 %, top 46 %, flyaways 18 %,
# short hairs 18 %; a 25k hero can't afford a top layer that fine, so coverage and mid carry more here
LAYERS = {
    "head": [(0.11, 0.024, 1.0), (0.17, 0.013, 0.8), (0.13, 0.008, 0.45)],
    "tail": [(0.08, 0.03, 1.0), (0.13, 0.016, 0.8), (0.10, 0.009, 0.45)],
    "face": [(0.0, 0.006, 1.0)],  # (half width 3.5 mm: 1/4 of the groom's wisp area at 1 m, wispL g4)  # one clump per face-framing lock (they frame the face: never merged)
}
HEAD_SN_MAX = 0.003  # m: a head clump's spread along its normal used for its layer offsets is capped at this (layers
# stand 0.6 x spread apart: crown clumps with frizz / loops, std 6-15 mm, stood their top card 4-18 mm over the one
# under it, b15: the backdrop showed through as white slivers along the crown at 1 m, g1_b15)
CROWN_LOOP = 0.6  # (gb19c at 1 m: the 3/4 crown knob gone, front arc remains, ear width kept 191 mm; 0 = off); a head strand rooted over the crown (FLY_CROWN up) whose chord is under this share of its length (a
# frizz loop) is left out of the head cards: clumps holding loops bent their mid-layer card up into a flap standing 4-17
# mm over the cards round it (b15 / b18: crown rays with a gap > 4 mm, layer1 over layer0 / layer2; white backdrop
# slivers and a "looped flap" at 1 m). The groom's crown halo is below what a 25k hero shows (as FLY_CROWN).
FLY_TRIS = 0.05  # share of the cards' triangles for flyaway cards (one strand each)
FLY_W = 0.0015  # m: a single strand's card half width
FLY_SHARE = 0.12  # share of the single-hair locks (halo, strays) that get a card each (silhouette ones first)
ROOT_FADE = 0.004  # m: a card's picture fades in over this from its root (no hard root edge at the part)
TIP_TAPER = 0.15  # share of a clump card's length over which its width tapers to TIP_FLOOR (0 = square ends, before b17)
TIP_FLOOR = 0.12
TIP_TAPER_TAIL = 0.3  # the same for tail (hanging) cards (b21 review at 1 / 3 m: "flat paddle", "blunt comb ends")
TIP_FADE_TAIL = 0.3  # share of a tail card's picture at its tip over which the alpha fades to 0 (under the game's cutoff
# the hairs end one by one, not at the quad's end); 0 = off (before b22)
TINT_TOP = (0.85, 1.35)  # b25: the top layer may run LIGHTER than its tile (the groom's light streaks are top strands;
# the tiles average them away); not darker (striping). b24's (0.93, 1.07) did not touch the striping (layerband)
# (was (0.93, 1.07)  # the same for the TOP head layer (b23 layerband: layer2 striped most, 8.05 | 6.43 vs 4.8-5.2)
TINT_RANGE = (0.85, 1.15)  # per-card tint on a shared tile (head / tail cards): 0.7-1.4 drew hard light / dark bands
# between stacked cards from temple to tie (c9 + g1 reviews: "side banding", "flat painted bands"; band L* std 5.8-7.0
# at 1 m vs the photo's 4.8-5.2); face wisps and flyaways keep the wide range (their own colour matters)
EDGE_FADE = 0.12  # share of a card's half width over which its picture fades out at the sides
PART_SPLIT = 0.04  # m: strands rooted within this of the part are clustered per side (no card spans the part)
MIN_STRANDS = 4
FACE_HAIRS = 8  # a face-framing lock of this many hairs+ is a bundle (Tess's tk / tw: 9-16 hairs); fewer: flyaways
HL_SOFT = 0.010  # m: a hairline card's (its clump's lock rooted at the hairline) first HL_SOFT from the root fades in
HL_ALPHA = 0.45  # from this share of its alpha (sparser: the thin hairs fall under the game's alpha cutoff),
HL_LIFT = 0.5  # (0.8 in b23 / b24: pale blotches at the left forehead, review gg9)  this much lighter in tone, without the depth shade (0.35 before b23: rim-inner +3.6 L* at 1 m vs the
# groom's +19, hairline.py g1v1 on b22, after card_gain 2.10 darkened the roots)
FACE_ALPHA = 0.55  # a face-framing card's picture is this opaque
TAIL_TONE = 0.75  # (round 24; 1.0 before) tail (hanging) cards' tone x this: the tail alone was +9 L* (back) / +3 (3/4) over gSc, 0.75: +2.4 / -3.9, head cards unchanged
TONE_CONTRAST = 2.2  # (round 25) head / tail card pictures: each hair's tone spread about its island's median x this (the
# groom's light / dark strands: gSc hair boxes p10..p90 span ~25-30 L*, b32's ~13-16 at the same mean; t25/hl.py)
TONE_CONTRAST_DARK = 1.3  # the stretch below the median (0 = the same k): c22's front crown p10 fell 12.3 -> 7.1 (gSc 19.9)
TONE_CONTRAST_TAIL = 3.5  # the same for tail (hanging) cards (0 = TONE_CONTRAST)
TAIL_ROOT_LIFT = 0.6  # (round 25) tail cards' first TAIL_ROOT_LEN from the root (under the tie): tone x (1 + this), depth
TAIL_ROOT_LEN = 0.04  # shade off there (b32 g1backl: dark angular shards under the tie where gSc's gathered locks are lit)
WISP_LIFT = 0.5  # a face-framing card's tone x (1 + this), depth shade off (lit hair in the open)
FACE_YO = 0.5  # a face-framing card's layer offset from its clump's centre x this (1 = the head cards'; b22's stood off
# the cheek as stiff planks, 1 m review g7)
WISP_KIDS_FACE = 4  # (10 before round 24: the temple face cards read as broad opaque pale sheets, t24/temple_f2_zoom.png) tiles: hairs per face-framing card's picture (6 drew 1/4 of the groom's wisp area at 1 m)
FACE_PER = 6  # (4 before b23: fewer, fuller face cards) hairs a face-framing card pictures (a whole 9-16 hair bundle on one card, splayed over 2-3 cm, was a
# wide flat ribbon across the brow, review c5)
BASE_IN = 0.012  # m: a coverage card's opaque core starts this far from its root (strands only before it: the soft
# hairline and nape; from the root it was a hard opaque edge, a notch at the part, a dark wedge at the nape)
PART_GAP = 0.006  # (0.016 in b28 / b29: the part band stood bare and the crown sat ~15-20 mm low at the front; round 22 q1: top-band figure deficit -26% front, -31% profile) m: a head card's root stays this far off the part line (roots crossing at the part: the criss-cross;
# round 20 flat g1v0 part dip 4 mm 1.93, 8 mm 2.70, 12 mm 3.16, 16 mm 3.52 vs the groom 3.5, but NO V reads in the crops)
FLY_CROWN = 0.02  # m over the head's centre: single hairs rooted on the head above this get no cards
FLY_CROWN_FREE = 0.06  # m: the same for free halo hairs (rooted in the mass, not the scalp): three over the crown drew
# dark coils standing 1.5 cm over it (the crest of reviews c6-c7)
FLY_STRAIGHT = 0.6  # a flyaway strand gets a card only if its chord is this share of its length (loops read as arcs)
IN_SHARE = 0.6  # a strand is drawn on a card only if this share of its points lies inside the card (strands leaving the card
# at its sides were drawn as short fragments: the side of the head read as brush strokes, b10)
SIDEWAYS = 0.5  # a strand segment running more across a card than this (|along| / length below it) is not drawn (a
# strand looping across its card's flow: dark horizontal scratches at the temple, c6)
FLY_FAR = 0.02  # m: single hairs standing further than this off the rest are not given cards  # a clump with fewer strands is drawn as a fly card


def _ss(x):
    x = np.clip(np.asarray(x, float), 0.0, 1.0)
    return x * x * (3 - 2 * x)


def _unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def classify(lk: dict) -> str:
    """Which kind of card a lock's strands become: head (lying, gathered), tail (hanging off a tie / free hair), face
    (face-framing wisps), single (halo, strays, baby hairs: flyaway cards)."""
    if lk.get("face") and int(lk.get("hairs") or 0) >= FACE_HAIRS:
        return "face"
    if int(lk.get("hairs") or 0) > 0:
        return "single"
    return "tail" if float(lk.get("free", 0.0)) > 0.5 else "head"


def strands(D: dict, locks: list, stations: int = 160) -> dict:
    """The groom's lock strands (not the scalp layer) at fixed STEP stations of distance from their root: Q (n, stations,
    3) with NaN past each strand's end; len, lock, rand, cls, root."""
    names = [str(x) for x in D["names"]]
    first = np.r_[0, np.cumsum(D["counts"])]
    keep = [j for j in range(len(D["counts"])) if names[int(D["obj"][j])] != "hair_under" and D["counts"][j] >= 2
            and int(D["lock"][j]) < len(locks)]
    Q = np.full((len(keep), stations, 3), np.nan, np.float32)
    ln = np.zeros(len(keep))
    S_ = np.arange(stations) * STEP
    for i, j in enumerate(keep):
        P = D["pts"][first[j]:first[j + 1]].astype(float)
        s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
        ln[i] = s[-1]
        ok = S_ <= s[-1]
        Q[i, ok] = np.stack([np.interp(S_[ok], s, P[:, c]) for c in range(3)], 1)
    lock = np.asarray([int(D["lock"][j]) for j in keep], int)
    return {"Q": Q, "len": ln, "lock": lock, "rand": np.asarray([float(D["rand"][j]) for j in keep]),
            "cls": np.asarray([classify(locks[li]) for li in lock]), "root": Q[:, 0].astype(float),
            "radius": np.asarray([float(D["radius"][j]) for j in keep]) if "radius" in D else np.full(len(keep), 4e-5)}


def features(St: dict, idx, fr=(0.0, 0.15, 0.35, 0.6, 0.85, 1.0), side=None, side_w: float = 0.08) -> np.ndarray:
    """A strand as a point to cluster: its positions at fractions of its length (so a clump is strands that run
    together all the way: a wave's phase, not only the root), + its length, + its side of the part (scaled so the
    two sides never share a clump near the part)."""
    Q, ln = St["Q"][idx], St["len"][idx]
    k = np.clip((np.asarray(fr)[None] * ln[:, None] / STEP).round().astype(int), 0, Q.shape[1] - 1)
    F = np.concatenate([Q[np.arange(len(idx))[:, None], k].reshape(len(idx), -1), 0.5 * ln[:, None]], 1)
    F = np.nan_to_num(F)
    if side is not None:
        F = np.concatenate([F, side_w * np.asarray(side, float)[:, None]], 1)
    return F


def kmeans(F: np.ndarray, k: int, seed: int = 0, iters: int = 20) -> np.ndarray:
    """Labels of k clusters (k-means++ seeding kept incremental: scipy's re-measures every centre each pick, O(k^2 n),
    half an hour for Tess's 2,300 tail clumps)."""
    from scipy.spatial import cKDTree
    F = np.asarray(F, float)
    k = int(np.clip(k, 1, len(F)))
    if k == len(F):
        return np.arange(len(F))
    rng = np.random.default_rng(seed)
    cen = [int(rng.integers(len(F)))]
    d2 = ((F - F[cen[0]]) ** 2).sum(1)
    for _ in range(k - 1):
        i = int(rng.choice(len(F), p=d2 / d2.sum())) if d2.sum() > 0 else int(rng.integers(len(F)))
        cen.append(i)
        d2 = np.minimum(d2, ((F - F[i]) ** 2).sum(1))
    M = F[cen].copy()
    lab = np.zeros(len(F), int)
    for _ in range(iters):
        lab_new = cKDTree(M).query(F)[1]
        if (lab_new == lab).all() and _ > 0:
            break
        lab = lab_new
        cnt = np.bincount(lab, minlength=k)
        for c_ in range(F.shape[1]):
            M[:, c_] = np.where(cnt > 0, np.bincount(lab, F[:, c_], minlength=k) / np.maximum(cnt, 1), M[:, c_])
    return np.unique(lab, return_inverse=True)[1]


def _cen_of(C, core):
    if core is None or len(core) < 2:
        return lambda P: np.asarray(C, float)[None]
    K = np.asarray(core, float)

    def f(P):
        a, b = K[:-1], K[1:]
        ab = b - a
        tt = np.clip(((P[:, None] - a[None]) * ab[None]).sum(-1) / np.maximum((ab * ab).sum(-1), 1e-12)[None], 0, 1)
        near = a[None] + tt[..., None] * ab[None]
        return near[np.arange(len(P)), np.linalg.norm(P[:, None] - near, axis=-1).argmin(1)]
    return f


def along_reference(Q: np.ndarray) -> np.ndarray:
    """A clump's strands re-sampled on ONE reference strand's stations (its longest: for hair gathered into a tie, the
    one rooted furthest upstream): each strand point goes to the reference station nearest it, so strands rooted
    further down the flow join the clump where they join it. At the same distance from their roots, strands rooted at
    the hairline and at the crown were averaged into a centre line starting mid-scalp: the front of Tess's head bare."""
    from scipy.spatial import cKDTree
    ln = np.isfinite(Q[..., 0]).sum(1)
    ref = int(np.argmin(np.abs(ln - np.percentile(ln, 95))))
    R = Q[ref][np.isfinite(Q[ref][:, 0])].astype(float)
    tree = cKDTree(R)
    n = len(R)
    out = np.full((len(Q), n, 3), np.nan)
    for i in range(len(Q)):
        q = Q[i][np.isfinite(Q[i][:, 0])].astype(float)
        if len(q) < 2:
            continue
        k = tree.query(q)[1]
        sm = np.zeros((n, 3))
        ct = np.zeros(n)
        np.add.at(sm, k, q)
        np.add.at(ct, k, 1)
        hit = np.nonzero(ct)[0]
        lo, hi = hit.min(), hit.max()
        st = np.arange(lo, hi + 1)
        out[i, lo:hi + 1] = np.stack([np.interp(st, hit, sm[hit, c] / ct[hit]) for c in range(3)], 1)
    return out


HW_PER_STRAND = 0.0006  # m of half width a card may have per strand still running along it (0 = off, before b25)
TWIST_HANG = 6.0  # (10 in b25: tail card 201 kept 6 folded pairs) deg per station (STEP): the most a hanging (tail / face) card's frame turns about the hair (0 = off, before b25)
BEND_HW = 0.0  # (0.6 in b25 = the front-top "cat ears": narrowed layer-0 head cards at their bends left cap vertices with no card in reach, which kept the mass height and stood up as two points; cap flats b24 / b25 / b25 BEND_HW 0, round 18. It never touched the tail flap.) a card's half width <= this x its in-plane bend radius (0 = off, before b25)


def fit(Q: np.ndarray, cen_of, end_share: float = 0.2, max_hw: float = 0.03, start_share: float = 0.04,
        spread: float = 90.0, reference: bool = True, tip_taper=None, medoid: float = 0.0, per_strand: float = 0.0) -> dict | None:
    """One card on a clump's strands Q (m, stations, 3, NaN past their ends), along its reference strand
    (along_reference): hair_cards._clump's centre line and frame, from where its first strands start to where only
    `end_share` of them still run (ragged ends are the picture's), its half width the strands' spread across it (90th
    percentile, capped)."""
    from .hair_cards import _clump
    # (`reference`: hair converging from many roots (into a tie) is aligned along its longest strand; hair hanging from
    # one place (a tail) by distance from the root: mapped to a wavy reference's nearest station, strands of another
    # phase folded back and forth and the picture smeared)
    A = along_reference(Q) if (reference and len(Q) > 1) else Q[:, :int(np.isfinite(Q[..., 0]).sum(1).max())].astype(float)
    U = np.arange(A.shape[1]) * STEP
    c = _clump(A, U, cen_of, min_share=0.5, start_share=start_share, end_share=end_share, medoid=medoid,
               twist=0.0 if reference else np.radians(TWIST_HANG))
    if c is None:
        return None
    sl = slice(c["i0"], c["i0"] + len(c["P"]))
    d = A[:, sl] - c["P"][None]
    with np.errstate(invalid="ignore"), __import__("warnings").catch_warnings():
        __import__("warnings").simplefilter("ignore")
        ax = np.nanpercentile(np.abs((d * c["X"][None]).sum(-1)), spread, axis=0)
        on = np.nanpercentile((d * c["N"][None]).sum(-1), SIDE_OUT_PCT, axis=0)  # the clump's outer strands along N
    ax = np.nan_to_num(ax, nan=0.002)
    from scipy.ndimage import gaussian_filter1d
    c["out"] = np.clip(gaussian_filter1d(np.nan_to_num(on, nan=0.0), 2.0), 0.0, SIDE_OUT_MAX)
    hw = np.clip(gaussian_filter1d(ax, 2.0) * 1.15 + 0.0015, 0.0015, max_hw)
    # narrower where few of its strands are left (a card as wide as its clump to the last strand's tip was a torn,
    # blocky end)
    hw = hw * np.clip(gaussian_filter1d(np.asarray(c["share"], float), 2.0) / 0.5, 0.35, 1.0)
    s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(c["P"], axis=0), axis=1))]
    if s[-1] < 0.01:
        return None
    if per_strand > 0:  # (tail cards: HW_PER_STRAND) no wider than its running strands can fill (a few outer frizz strands as an 18 mm ribbon
        # wearing a dense tile: b24 review "wide separate ribbon strands flare off the ponytail")
        run = np.asarray(c["share"], float) * len(Q)
        hw = np.minimum(hw, np.maximum(0.0015, gaussian_filter1d(run, 2.0) * per_strand))
    if BEND_HW > 0 and len(s) > 4:  # a card bent in its own plane tighter than its half width folds its inner edge
        # back over itself (b24: hanging/L0 card 201 at the tail's curl, 11 folded triangle pairs = the "folded flap
        # at the end"): half width <= BEND_HW x the bend radius there
        from scipy.ndimage import minimum_filter1d
        T_ = np.gradient(c["P"], s, axis=0)
        T_ = T_ / np.maximum(np.linalg.norm(T_, axis=1), 1e-9)[:, None]
        kx = np.abs((np.gradient(T_, s, axis=0) * c["X"]).sum(-1))
        lim = BEND_HW / np.maximum(gaussian_filter1d(kx, 1.0), 1e-6)
        hw = np.minimum(hw, np.maximum(0.0015, minimum_filter1d(lim, 5)))
    # the card's GEOMETRY tapers to a point over its last TIP_TAPER: square-cut card ends read as a sawtooth comb at game
    # distance (g1_b15 review, 1 m: "blunt, comb-like" tail ends, "chunky blunt ends"); the picture's feathered tip alone
    # can't hide the quad's square end
    tt = TIP_TAPER if tip_taper is None else tip_taper
    if tt > 0:
        u = (s[-1] - s) / max(tt * s[-1], 1e-6)
        hw = hw * (TIP_FLOOR + (1 - TIP_FLOOR) * _ss(np.clip(u, 0.0, 1.0)))
    return {**c, "hw": hw, "s": s}


ENV_FALLBACK = 1.0  # 1: envelope() falls back to uniform sphere cells where a 3-deg bin is thin (b25); 0 = off (A/B, round 18)


def envelope(St: dict, C, deg: float = 3.0, pct: float = 97.0):
    """The head hair's outer surface seen from the head's centre: a function points -> the strands' `pct` radius in
    their (azimuth, elevation) bin (NaN where too few strands)."""
    C = np.asarray(C, float)
    Q = St["Q"][St["cls"] == "head"][:, ::2].reshape(-1, 3)
    Q = Q[np.isfinite(Q[:, 0])].astype(float)

    def key(P):
        v = np.asarray(P, float) - C
        r = np.linalg.norm(v, axis=1)
        az = np.degrees(np.arctan2(v[:, 0], -v[:, 1]))
        el = np.degrees(np.arcsin(np.clip(v[:, 2] / np.maximum(r, 1e-9), -1, 1)))
        return np.floor(az / deg).astype(np.int64) * 100000 + np.floor(el / deg).astype(np.int64), r
    kq, rq = key(Q)
    o = np.argsort(kq)
    u, st, cnt = np.unique(kq[o], return_index=True, return_counts=True)
    env = {int(k): (float(np.percentile(rq[o][a:a + c], pct)) if c >= 20 else np.nan) for k, a, c in zip(u, st, cnt)}
    # fallback where an (azimuth, elevation) bin is empty or thin: near the pole those bins shrink to slivers (under 20
    # strand points), the envelope was NaN there and a card crossing the crown was never held under it (b24's crown
    # "plate": layer-1 card 133 arched front -> back over the top, 37% of its vertices on NaN bins, 1.5 cm2 standing
    # 3+ mm off, crownx.py). Uniform cells on the unit sphere (~6, then ~12 deg) have the same size everywhere.
    rad = np.maximum(np.linalg.norm(Q - C, axis=1), 1e-9)
    Uq = (Q - C) / rad[:, None]
    coarse = []
    for cells in (10.0, 5.0):
        kc = np.floor(Uq * cells).astype(np.int64) @ np.array([1, 1000, 1000000], np.int64)
        oc = np.argsort(kc)
        uc, sc_, cc = np.unique(kc[oc], return_index=True, return_counts=True)
        coarse.append((cells, {int(k): float(np.percentile(rad[oc][a:a + c], pct)) for k, a, c in zip(uc, sc_, cc) if c >= 20}))

    def f(P):
        k, r = key(P)
        e = np.array([env.get(int(x), np.nan) for x in k])
        bad = ~np.isfinite(e)
        if bad.any() and ENV_FALLBACK:
            Pb = np.asarray(P, float)[bad] - C
            Ub = Pb / np.maximum(np.linalg.norm(Pb, axis=1), 1e-9)[:, None]
            eb = np.full(len(Ub), np.nan)
            for cells, tab in coarse:
                kb = np.floor(Ub * cells).astype(np.int64) @ np.array([1, 1000, 1000000], np.int64)
                eb = np.where(np.isfinite(eb), eb, np.array([tab.get(int(x), np.nan) for x in kb]))
            e[bad] = eb
        return e, r
    return f


SIDE_EL = (60.0, 80.0)  # (20, 40 before round 21b: the crown sat on its clumps' means, a 10-20 mm band of the groom's
# figure missing over the whole top; 60-80: top-band deficit 8058 -> 6543 px at 1 m, cardsil; 85-90 the same) deg over the head's centre: under the first a head card is on the SIDES (fully), over the second
# on the top; between, a smoothstep. On the sides the outer cards are the head's silhouette at ear height:
SIDE_OUT_PCT = 90.0  # there the top head layer lies on its clump's outer strands (this percentile of their offsets along
# the clump's normal) instead of 0.6 x its spread (capped at HEAD_SN_MAX for the crown): at the clump's mean the
# cards' head was 10-20 mm narrower than its groom at ear height (front, 1 m: 187-191 vs 199-206 mm; silhgeo g0), and
# the envelope cap was not the cause (uncapped: +2-3 mm)
SIDE_OUT_MAX = 0.012  # m: at most this far out
TAIL_END = 0.03  # a hanging (tail / face) card runs on to where this share of its clump's strands still run
MEDOID_TAIL = 1.0  # a tail card's centre line follows its clump's medoid long strand (hair_cards._medoid_line): the wave
MEDOID_FACE = 0.5  # (1.0 in b24: wisp area 1314 -> 1004 px vs the groom's 2175, the face cards on one strand) and curl (b23: straight sheets, back edge -33 mm at the curl); the same for face-framing cards (stiff strips)
MEDOID_TAIL_TOP = 0.5  # (1.0 = MEDOID_TAIL before; 0.5: layer-2 area > 5 mm off every strand 10.96 -> 2.30 cm2, > 8 mm
# 0.77 -> 0, figure deficit +0.7%; 0.0: 0.92 cm2 but back 3/4 deficit +190 px) round 21b: the same for the TOP tail layer (narrowest cards, 45% of the strands): on its few
# strands the medoid can be an escaped strand arcing off the tie, and the 18 mm card followed it (b28 back 3/4: dark
# ribbons arching out right of the tail at 1 and 3 m; card 345 lay 0.77 cm2 > 8 mm off every strand)
FACE_END = 0.0  # a face-framing card runs on to its longest strand's tip (b23 review vs the groom: wisps stop at the jaw,
# the groom's fall past it)
TAIL_END_JIT = 0.15  # + a random share up to this per tail card: staggered ends (all at 0.03 + tapered to a point
# drew a comb of aligned teeth at 3 m, review g7: "cut square, jagged comb-tooth"); 0 = off (before b23)
NAPE_LIFT = 0.8  # (0.6 in b23-b25: wedge 29.8 vs the groom 33.5 once only tail L1 kept the lift) head cards rooted low at the back (the nape, under a tie) tinted x (1 + this): their strands lie
# deep under the gathered hair, so their tint (strands' tone with the depth shade) drew a dark serrated block behind
# the ear in the FLAT pass (b22 nape blob L* 19.7 vs the groom's 33.5, wedge.py g1backl); 0 = off (before b23)
NAPE_BAND = (0.0, 0.035)  # m under the head's centre: the lift ramps in over this (smoothstep), times a ramp
NAPE_Y = (-0.025, 0.01)  # m behind the head's centre (y): from beside the ear (the dark serrated marks behind the ear
# in b23's flat pass sit at y ~ 0: a ramp from the centre back left them out, b23n = b23 there)
TAIL_OUT = 1.0  # share of the way a tail card's layers move out toward its clump's SIDE_OUT_PCT outer strands (the
# tail beside the neck, front at 140 mm under the top: cards +97 vs strands +111 mm, silhgeo b19)
SIDE_ENV_PCT = 99.0  # and its envelope cap is this percentile of the strands' radius (ENV_PCT 90 over the top)
ENV_PCT = 90.0  # head cards stay under this percentile of the head strands' radius (97: the cards' tops sat at the frizz,
# the 99.5th percentile, and their pictures of frizz drew dark arcs standing over the crown, b12)
ENV_UNDER = 0.001  # m: a head card (and its edges) stays this far under the strands' outer surface (cards standing
# 6-8 mm over it at the part read as a crest of combed strips along the crown, review c6)


def side_weight(P, C) -> np.ndarray:
    """1 on the head's sides (elevation over its centre under SIDE_EL[0]), 0 over the top (SIDE_EL[1]), smoothstep."""
    v = np.asarray(P, float) - np.asarray(C, float)
    el = np.degrees(np.arcsin(np.clip(v[:, 2] / np.maximum(np.linalg.norm(v, axis=1), 1e-9), -1, 1)))
    return _ss(np.clip((SIDE_EL[1] - el) / (SIDE_EL[1] - SIDE_EL[0]), 0.0, 1.0))


def _under_envelope(c: dict, env, C, env_side=None) -> None:
    """Moves a head card's stations in toward the head's centre where it or its edges stand over the envelope (on the
    sides `env_side`, blended by side_weight)."""
    P, X, hw = c["P"], c["X"], np.asarray(c["hw"])
    over = np.zeros(len(P))
    for E in (P, P - X * hw[:, None], P + X * hw[:, None]):
        e, r = env(E)
        if env_side is not None:
            es, _ = env_side(E)
            w = side_weight(E, C)
            e = np.where(np.isfinite(es), (1 - w) * e + w * es, e)
        over = np.maximum(over, np.nan_to_num(r - (e - ENV_UNDER), nan=0.0))
    if over.max() <= 0:
        return
    from scipy.ndimage import maximum_filter1d, gaussian_filter1d
    over = gaussian_filter1d(maximum_filter1d(over, 5), 1.5)
    c["P"] = P - _unit(P - np.asarray(C, float)) * over[:, None]


def crown_loops(St: dict, C) -> np.ndarray:
    """Strands rooted over the crown (FLY_CROWN over the head's centre) that loop: chord < CROWN_LOOP x length."""
    out = np.zeros(len(St["len"]), bool)
    if CROWN_LOOP <= 0:
        return out
    for j in np.nonzero(St["root"][:, 2] > float(np.asarray(C)[2]) + FLY_CROWN)[0]:
        q = St["Q"][j][np.isfinite(St["Q"][j][:, 0])]
        out[j] = len(q) >= 3 and np.linalg.norm(q[-1] - q[0]) < CROWN_LOOP * St["len"][j]
    return out


def layer_offset(sn, la: int, cls: str) -> np.ndarray:
    """A card's offset along its normal from its clump's centre line (m), per station: coverage under, mid at the
    clump, top over it (by the clump's spread `sn` along its normal; a head clump's spread capped at HEAD_SN_MAX)."""
    sn = np.asarray(sn, float)
    if cls == "tail":
        return sn * (-0.6, 0.4, 1.0)[min(la, 2)] + 0.0004 * la
    return np.minimum(sn, HEAD_SN_MAX) * (-0.6 + 0.6 * la) + 0.0004 * la


def card_offset(c: dict, la: int, n_layers: int, cls: str, C) -> np.ndarray:
    """layer_offset, and on the head's sides (side_weight) the head's layers moved out TOGETHER until the top one lies
    on the clump's outer strands (c["out"]: the top layer alone moved out stood off the one under it, crownprobe: rays
    with a gap > 4 mm 13.8 -> 15.3%, backdrop between cards at the silhouette; together 14.3%)."""
    yo = layer_offset(c["sn"], la, cls)
    if cls == "head" and SIDE_OUT_PCT > 0 and "out" in c:
        top_ = layer_offset(c["sn"], n_layers - 1, cls)
        yo = yo + side_weight(c["P"], C) * np.maximum(0.0, np.asarray(c["out"], float) - top_)
    elif cls == "tail" and TAIL_OUT > 0 and "out" in c:  # the tail's layers out together toward its outer strands
        top_ = layer_offset(c["sn"], n_layers - 1, cls)
        yo = yo + TAIL_OUT * np.maximum(0.0, np.asarray(c["out"], float) - top_)
    return yo


PART_FROM_STRANDS = 1.0  # round 18: the part is read from the strands themselves (strand_part; a tied groom's part is
# emergent: hair_flow combs the top strands left / right of a line), the spec's line only where they show none; 0 = off
# (b25: the cards split at the default line 3 cm off centre, part dip 2.5 at col 285 vs the groom's 3.5 at 245)
PART_REACH = 0.03  # m along a strand from its root over which its sideways sweep is read
PART_EL = 35.0  # deg over the head's centre: only roots above this decide a side (on the sides every strand runs down)
PART_SIDEWAYS = 0.35  # a root decides a side only if its sweep's x share is at least this


PART_ROOT_REACH = 0.03  # m: a head card rooted within this of the part starts at the part (PART_GAP off it) and leaves
# it sideways, then turns into its own line (round 19: the cards' roots sat 1-2 cm off the line, the cap between them,
# so the part read as no part: part dip 1.1 vs the groom's 3.5); 0 = off


def _part_root(c: dict, side_of, C) -> None:
    """A head card whose root lies within PART_ROOT_REACH of the part gets a lead-in: from the part's edge (PART_GAP
    off the line, at the root's height over the head) out sideways (away from the part), curving into the card's own
    start (Hermite). The per-station keys are extended with the root station's values."""
    P = np.asarray(c["P"], float)
    sd, dp = side_of(P[:1])
    sd, dp = float(sd[0]), float(dp[0])
    if sd == 0 or not np.isfinite(dp) or dp > PART_ROOT_REACH or dp < PART_GAP + 0.003:
        return
    C = np.asarray(C, float)
    r0 = P[0] - C
    rad = np.linalg.norm(r0)
    nr = r0 / max(rad, 1e-9)
    e = np.array([sd, 0.0, 0.0]) - nr * sd * nr[0]
    if np.linalg.norm(e) < 0.2:
        return
    e /= np.linalg.norm(e)
    R = P[0] - e * (dp - PART_GAP)
    R = C + (R - C) / np.linalg.norm(R - C) * rad
    L = float(np.linalg.norm(P[0] - R))
    m = int(np.ceil(L / STEP))
    if m < 1:
        return
    T0 = np.asarray(c["T"], float)[0]
    t = np.arange(m)[:, None] / m
    h00, h10, h01, h11 = 2 * t ** 3 - 3 * t ** 2 + 1, t ** 3 - 2 * t ** 2 + t, -2 * t ** 3 + 3 * t ** 2, t ** 3 - t ** 2
    Q = h00 * R + h10 * e * L + h01 * P[0] + h11 * T0 * L
    Pn = np.concatenate([Q, P])
    Tn = np.gradient(Pn, axis=0)
    Tn /= np.maximum(np.linalg.norm(Tn, axis=1, keepdims=True), 1e-12)
    N0 = np.asarray(c["N"], float)[0]
    X0 = np.asarray(c["X"], float)[0]
    Xq = np.cross(np.repeat(N0[None], m, 0), Tn[:m])
    Xq /= np.maximum(np.linalg.norm(Xq, axis=1, keepdims=True), 1e-12)
    Xq *= np.sign((Xq @ X0)[:, None] + 1e-12)
    n = len(P)
    for k_ in ("N", "bend", "hw", "sn", "u", "share", "out", "rad"):
        v = c.get(k_)
        if np.ndim(v) and len(v) == n:
            v = np.asarray(v)
            c[k_] = np.concatenate([np.repeat(v[:1], m, 0), v])
    c["P"], c["T"] = Pn, Tn
    c["X"] = np.concatenate([Xq, np.asarray(c["X"], float)])
    seg = np.linalg.norm(np.diff(Pn, axis=0), axis=1)
    c["s"] = np.concatenate([[0.0], np.cumsum(seg)])
    c["i0"] = max(0, int(c["i0"]) - m)
    c["part_root"] = m


def strand_part(St: dict, C):
    """The parting as the strands show it: head strands rooted over the top whose first PART_REACH runs sideways (x
    share >= PART_SIDEWAYS) vote their side (sign of x); a function points -> (side, distance m to the part) like
    hair.part_side_of: side = the nearest voting roots' majority, distance = half the gap between the nearest root of
    the other side and the nearest of its own; points far from every voting root get side 0, distance inf."""
    from scipy.spatial import cKDTree
    C = np.asarray(C, float)
    head = np.nonzero(St["cls"] == "head")[0]
    Q = St["Q"][head].astype(float)
    k = max(1, int(round(PART_REACH / STEP)))
    p0 = Q[:, 0]
    fin = np.isfinite(Q[..., 0])
    last = np.minimum(k, fin.sum(1) - 1)
    pk = Q[np.arange(len(Q)), np.maximum(last, 0)]
    d = pk - p0
    v = p0 - C
    el = np.degrees(np.arcsin(np.clip(v[:, 2] / np.maximum(np.linalg.norm(v, axis=1), 1e-9), -1, 1)))
    xs = d[:, 0] / np.maximum(np.linalg.norm(d, axis=1), 1e-9)
    ok = np.isfinite(xs) & (el > PART_EL) & (np.abs(xs) >= PART_SIDEWAYS) & (last > 0)
    if ok.sum() < 20 or (xs[ok] > 0).sum() < 10 or (xs[ok] < 0).sum() < 10:
        return None
    R, sd = p0[ok], np.sign(xs[ok])
    tp, tn = cKDTree(R[sd > 0]), cKDTree(R[sd < 0])
    print(f"strand part: {int((sd > 0).sum())} roots sweep +x, {int((sd < 0).sum())} -x (of {len(head)} head strands)",
          flush=True)

    def f(P):
        P = np.asarray(P, float)
        dp, _ = tp.query(P)
        dn, _ = tn.query(P)
        side = np.where(dp < dn, 1.0, -1.0)
        dist = np.abs(dn - dp) / 2
        far = np.minimum(dp, dn) > 0.02
        return np.where(far, 0.0, side), np.where(far, np.inf, dist)
    return f


def cut(D: dict, locks: list, C, S: dict, side_of=None, seed: int = 0, layers: dict | None = None,
        triangles: int = 20000) -> list:
    """Cards cut by clumps, per class and layer (see LAYERS). `side_of(points) -> (side -1/0/+1, distance to the
    part m)` for strand roots, or None. Each card: hair_cards' card keys + "strands" (indices into `St` = the
    module-level strands this cut used, kept on the first card as "_St") and "draw" (share of its strands drawn)."""
    St = strands(D, locks)
    env = envelope(St, C, pct=ENV_PCT)
    env_side = envelope(St, C, pct=SIDE_ENV_PCT) if SIDE_ENV_PCT != ENV_PCT else None
    layers = layers or LAYERS
    rng = np.random.default_rng(seed + 31)
    out = []
    side = np.zeros(len(St["len"]))
    if PART_FROM_STRANDS:  # the strands' own part first: the spec's default line (x = 3 cm) sat 3 cm off a tied
        # groom's emergent centre part (b25 part dip at col 285, the groom's at 245; top roots sweep -x left of x = 0,
        # +x right of it, t18/partprobe.py)
        side_of = strand_part(St, C) or side_of
    if side_of is not None:
        sd, dist = side_of(St["root"])
        side = np.where(dist < PART_SPLIT, sd, 0.0)
    loop = crown_loops(St, C)
    for cls in ("head", "tail", "face"):
        idx = np.nonzero((St["cls"] == cls) & ~(loop & (cls == "head")))[0]
        if not len(idx):
            continue
        F = features(St, idx)
        per_card = max(4.0, 2.0 * float(np.median(St["len"][idx])) / float(S.get("segment", 0.008)))
        # strands rooted near the part are clustered per side: no card spans the part (a soft side key in the
        # features still let k-means mix them)
        # a tail's clumps never mix its locks: each wavy lock is a visible S-clump, and averaged with a neighbour of
        # another phase its wave cancelled (the tail read as one flat sheet, reviews c5-c6)
        grp = side[idx] if cls == "head" else St["lock"][idx].astype(float) if cls == "tail" else np.zeros(len(idx))
        for la, (tshare, max_hw, share) in enumerate(layers[cls]):
            if cls == "face":  # each face-framing lock: its own clumps of FACE_PER hairs (they frame the face)
                lab = np.zeros(len(idx), int)
                off = 0
                for li in np.unique(St["lock"][idx]):
                    sel = St["lock"][idx] == li
                    k_ = max(1, int(round(int(locks[li].get("hairs") or 4) / FACE_PER)))
                    lab[sel] = kmeans(F[sel], k_, seed + 13) + off
                    off = int(lab[sel].max()) + 1
            else:
                k_all = max(1, int(round(tshare * triangles / per_card)))
                lab = np.zeros(len(idx), int)
                off = 0
                for gv in np.unique(grp):
                    sel = grp == gv
                    lab[sel] = kmeans(F[sel], max(1, int(round(k_all * sel.mean()))), seed + 7 * la) + off
                    off = int(lab[sel].max()) + 1
            for g in np.unique(lab):
                mem = idx[lab == g]
                lk = locks[int(np.bincount(St["lock"][mem]).argmax())]
                # (hanging hair runs on to its longest strands' tips: ended where a quarter were left, Tess's tail
                # ended in a straight cut 3 cm short)
                # (and is its outline: a tail's outer strands spread past the 90th percentile; at it the cards' tail
                # was 0.8 of the strands' width)
                end_ = TAIL_END + (TAIL_END_JIT * rng.uniform() if cls == "tail" else 0.0)
                c = fit(St["Q"][mem], _cen_of(C, lk.get("core")), end_share=(FACE_END if cls == "face" else end_) if cls != "head" else 0.35,
                        max_hw=max_hw, spread=97.0 if cls == "tail" else 90.0, reference=cls == "head",
                        tip_taper=TIP_TAPER_TAIL if cls == "tail" else TIP_TAPER,
                        medoid=(MEDOID_TAIL_TOP if la == len(LAYERS["tail"]) - 1 else MEDOID_TAIL) if cls == "tail"
                        else MEDOID_FACE if cls == "face" else 0.0,
                        per_strand=HW_PER_STRAND if cls == "tail" else 0.0)
                if c is None:
                    continue
                if cls == "head" and side_of is not None:  # its root stays PART_GAP off the part
                    _, dpart = side_of(c["P"])
                    near = np.nonzero(dpart >= PART_GAP)[0]
                    k0 = int(near[0]) if len(near) else len(c["P"])
                    if k0 > 0:
                        if len(c["P"]) - k0 < 4:
                            continue
                        for k_ in ("P", "T", "N", "X", "bend", "hw", "sn", "u", "share", "out", "rad"):
                            if np.ndim(c.get(k_)):
                                c[k_] = np.asarray(c[k_])[k0:]
                        c["i0"] += k0
                        c["s"] = c["s"][k0:] - c["s"][k0]
                    if PART_ROOT_REACH > 0:  # its root brought back to the part, leaving it sideways
                        _part_root(c, side_of, C)
                # coverage under, mid at the clump, top over it (the clump's spread along its normal)
                # (a tail's upper layers stand out round its core: at the clump's mean the cards' tail was 0.75 of the
                # strands' width in profile, a slab)
                yo = card_offset(c, la, len(layers[cls]), cls, C) * (FACE_YO if cls == "face" else 1.0)
                P = c["P"] + c["N"] * yo[:, None]
                if cls in ("head", "face"):
                    cc_ = {"P": P, "X": c["X"], "hw": c["hw"]}
                    _under_envelope(cc_, env, C, env_side if cls == "head" else None)
                    P = cc_["P"]
                kind = "baked"
                u = (c["i0"] * STEP + c["s"]) / max(float(np.percentile(St["len"][mem], 95)), 0.02)
                out.append({"P": P, "X": c["X"], "N": c["N"], "T": c["T"], "bend": c["bend"], "hw": c["hw"],
                            "rad": np.asarray(c["rad"], float) + yo, "u": u, "s": c["s"], "kind": kind, "layer": la, "cls": cls,
                            "prio": la + (-0.8 if cls == "face" else -0.4 if cls == "tail" else 0.0)
                            + 0.1 * rng.uniform(),
                            "cval": 1.0, "value": 1.0, "lock": lk["name"], "sn": c["sn"],
                            "strands": mem, "draw": share, "s0": c["i0"] * STEP, "wisp": cls == "face",
                            "edge": bool(lk.get("at_hairline")) or cls == "face"})
    # flyaways: single strands that break the outline, a card each (Epic: one card per flyaway strand)
    idx = np.nonzero(St["cls"] == "single")[0]
    if len(idx):
        far = np.zeros(len(idx))
        others = St["Q"][St["cls"] != "single"][:, ::4].reshape(-1, 3)
        others = others[np.isfinite(others[:, 0])]
        if len(others):
            from scipy.spatial import cKDTree
            tr = cKDTree(others[:: max(1, len(others) // 200000)])
            for i, j in enumerate(idx):
                q = St["Q"][j]
                q = q[np.isfinite(q[:, 0])]
                far[i] = float(tr.query(q)[0].max()) if len(q) else 0.0
        far = np.where(far > FLY_FAR, 0.0, far)  # (hairs standing 2 cm+ off the head read as spikes on cards)
        for i, j in enumerate(idx):
            lk_ = locks[int(St["lock"][j])]
            if St["root"][j][2] > float(np.asarray(C)[2]) + (FLY_CROWN_FREE if lk_.get("off_head") else FLY_CROWN):
                far[i] = 0.0  # (the halo over the crown as cards: a crest of thin strips, reviews c5-c6; a few single
                # hairs there are below what a 25k card hero can show: left to the strands' look)
        for i, j in enumerate(idx):  # (looping hairs read as stiff arcs over the crown as cards, review c5)
            q = St["Q"][j][np.isfinite(St["Q"][j][:, 0])]
            if len(q) < 3 or np.linalg.norm(q[-1] - q[0]) < FLY_STRAIGHT * St["len"][j]:
                far[i] = 0.0
        n = max(1, min(int(FLY_SHARE * len(idx)),
                       int(FLY_TRIS * triangles / max(4.0, 2.0 * float(np.median(St["len"][idx])) / float(S.get("segment", 0.008))))))
        for j in idx[np.argsort(-far)[:n]]:
            lk = locks[int(St["lock"][j])]
            c = fit(St["Q"][j:j + 1], _cen_of(C, None), end_share=1.0, max_hw=FLY_W)
            if c is None:
                continue
            c["hw"] = FLY_W * (1 - 0.6 * _ss(c["s"] / max(c["s"][-1], 1e-6)))  # (tapers to its tip)
            out.append({"P": c["P"], "X": c["X"], "N": c["N"], "T": c["T"], "bend": c["bend"], "hw": c["hw"],
                        "u": (c["i0"] * STEP + c["s"]) / max(float(St["len"][j]), 0.02), "s": c["s"], "kind": "baked", "layer": 3, "cls": "fly", "prio": 3.0,
                        "cval": 1.0, "value": 1.0, "lock": lk["name"], "sn": 0.0, "strands": np.array([j]),
                        "draw": 1.0, "s0": c["i0"] * STEP, "fly": True})
    if out:
        out[0]["_St"] = St
    return out


def card_hash(c: dict) -> int:
    return int(hashlib.md5(np.asarray(c["P"], np.float32).tobytes()).hexdigest()[:8], 16)


# ----------------------------------------------------------------------------------------------- the strand bake

DENSITY = {"head": {0: 0.55}, "tail": {0: 0.55}}  # x texel density per class / layer (others 1)
ANISO = 2.0  # a texel spans this many times more along the hair than across it (Epic: "Texture Compression" along the
# strand direction: hair changes slowly along its length; at 3 strands crossing the rows at an angle stair-stepped:
# dark scratchy bars across the flow, review c6)
TONE_HEAD = 1.5  # the baked tone is stored / (peak x this): a strand's tone passes the model's peak (strand contrast, the
# lock drift) and clipped at 1, a tenth of the strands lost their variation
KID_TIP = 0.3  # a child hair ends up to this share of its strand's length early (bake "kids")
RIBBON_W = 0.004  # m: highlight RIBBONS in the tile pictures (round 19). The groom's light streaks are its highlight
# ribbons (blender_strands: cells ~4 mm across, ~40% of them, half their hairs +60% value, coming and going along the
# length), COHERENT over several mm: the tile tone pool lit single hairs (0.2 mm), which a 1 mm pixel averages away
# (b26tp0 = b26 to 0.01). Here a tile's hairs in a ribbon band (RIBBON_W across, RIBBON_SHARE of the bands) lighten
RIBBON_SHARE = 0.0  # share of a card's across-bands that are ribbons (0 = off; round 19: 0.4 at gain 0.6 lifted the mass, flat g1v1 p50 +1.5, spread 11.3 -> 10.6: not kept)
RIBBON_GAIN = 0.6  # value gain at the ribbon's peak (x highlight_contrast / 0.6; tails at half, as the groom's)
TILE_TONE_POOL = 1.0  # round 18: a tile's child hairs take their tone ratio from the per-strand mean tones of ALL the
# cards wearing that tile (/ their mean, x this), not U(0.88, 1.12) around the medoid card's strands: the groom's light
# strands (b25 streak spread p95 - p50 13.2 vs the groom's 21.9 at g1v1) were averaged out of the tiles. 0 = off.
TILES = 24  # shared card pictures (bake_tiles); 0 = every card its own picture
TILE_ANISO = 1.0  # tiles: square texels (fine strands cross the rows at an angle)
KID_WISP = 0.7  # tiles: the same for face-framing / flyaway tiles (a see-through bundle of a few hairs)
WISP_ALPHA = 0.7  # (0.9 before round 24, with WISP_KIDS_FACE 4: see-through temple wisps like gSc) tiles: face / fly pictures' opacity (FACE_ALPHA / 0.45 are for unique islands at ~1 texel/mm)
KID_COVER = 1.4  # tiles: children drawn until the hairs' widths add up to this many times the card's width
FILL = 0.82  # share of the bake block the islands may cover (the rest is packing waste)
PAD = 2  # px between islands


def _skyline(sizes, W: int, H: int):
    """Bottom-left skyline packing (few boxes: the shared tiles): short islands stack under the tall ones' shelf."""
    from numpy.lib.stride_tricks import sliding_window_view
    sky = np.zeros(W, int)
    pos = [None] * len(sizes)
    for i in np.argsort([-h for _, h in sizes], kind="stable"):
        w, h = sizes[i]
        w_ = w + PAD
        if w > W:
            return None
        top = sliding_window_view(np.r_[sky, np.zeros(PAD, int)], w_).max(1)[:W - w + 1]
        x = int(np.argmin(top))
        if top[x] + h > H:
            return None
        pos[i] = (x, int(top[x]))
        sky[x:x + w_] = top[x] + h + PAD
    return pos


def _pack(sizes, W: int, H: int):
    """Shelf packing of (w, h) boxes into W x H, tallest first: [(x, y)] or None if they don't fit."""
    if len(sizes) <= 64:
        return _skyline(sizes, W, H)
    order = np.argsort([-h for _, h in sizes], kind="stable")
    pos = [None] * len(sizes)
    x = y = shelf = 0
    for i in order:
        w, h = sizes[i]
        if x + w > W:
            x, y, shelf = 0, y + shelf + PAD, 0
        if y + h > H or w > W:
            return None
        pos[i] = (x, y)
        x += w + PAD
        shelf = max(shelf, h)
    return pos


def _density(c: dict) -> float:
    """Texel density of a card's island relative to the rest: coverage cards lie under two layers (Epic's tutorial:
    the coverage layer repeats few textures, the budget goes to the visible layers)."""
    return DENSITY.get(c.get("cls"), {}).get(int(c["layer"]), 1.0)


def layout(cards: list, W: int, H: int, aniso: float | None = None) -> tuple[list, float]:
    """Each baked card's island (x, y, w, h) px in a W x H block, at the finest texel that fits (per card x its
    _density)."""
    ANISO_ = ANISO if aniso is None else float(aniso)
    dens = [_density(c) for c in cards]
    area = sum(float(c["s"][-1]) * 2 * float(np.max(c["hw"])) * d * d for c, d in zip(cards, dens))
    ra = np.sqrt(area / (ANISO_ * FILL * W * H))  # m across a texel
    for _ in range(60):
        sizes = [(int(np.clip(np.ceil(2 * float(np.max(c["hw"])) * d / ra), 4, W)),
                  int(np.clip(np.ceil(float(c["s"][-1]) * d / (ANISO_ * ra)), 8, H))) for c, d in zip(cards, dens)]
        pos = _pack(sizes, W, H)
        if pos is not None:
            return [(p[0], p[1], s[0], s[1]) for p, s in zip(pos, sizes)], float(ra)
        ra *= 1.04
    raise ValueError("hair bake: the islands do not fit the block")


def _card_coords(c: dict, q: np.ndarray, smooth: bool = False):
    """Points q (k, 3) in a card's own frame: (across m, along m from the card's start, depth m over its plane)."""
    P = np.asarray(c["P"], float)
    from scipy.spatial import cKDTree
    i = cKDTree(P).query(q)[1]
    d = q - P[i]
    ax, al, dp = (d * c["X"][i]).sum(-1), c["s"][i] + (d * c["T"][i]).sum(-1), (d * c["N"][i]).sum(-1)
    if smooth and len(q) > 4:  # one strand's points in order: its coordinates jump where its nearest station switches
        # (off-centre points at a bend; ~40% of the tail's strands had one, drawn as stair steps across the flow)
        from scipy.ndimage import gaussian_filter1d, median_filter
        ax, al = (gaussian_filter1d(median_filter(v, 5, mode="nearest"), 1.0, mode="nearest") for v in (ax, al))
    return ax, al, dp


def _cells(P: np.ndarray, size: float, salt: int, lo: float, hi: float) -> np.ndarray:
    """A random number per `size` m cell of a point (the strand look's per-lock numbers come from where a strand
    roots: blender_strands.cells_group): neighbours alike, in patches the size of a lock."""
    k = np.floor(np.asarray(P, float) / size).astype(np.int64) @ np.array([73, 7919, 104729], np.int64) + salt * 1000003
    r = ((k * 2654435761) % 4294967296) / 4294967296.0
    return lo + (hi - lo) * r


def _outward(P: np.ndarray, C, core=None) -> np.ndarray:
    """Unit directions out of the hair mass at points P: from the head's centre, or from a tail's core line."""
    return _unit(np.asarray(P, float) - _cen_of(C, core)(np.asarray(P, float)))


def strand_shade(St: dict, C, locks: list | None = None, every: int = 3, steps=(0.003, 0.006, 0.010),
                 r: float = 0.0025) -> np.ndarray:
    """How deep each strand point lies in the hair (0 on top .. 1 under the most hair): strand points counted round
    3 / 6 / 10 mm outward of it (from the head's centre, or a tail's core). The strand look darkens deep hair (its
    `depth`: x (1 - 0.75 depth shade)); without it the baked cards were one flat light taupe, no dark between the
    waves (review c6). (n, stations), NaN-free (0 past a strand's end)."""
    from scipy.spatial import cKDTree
    Q = St["Q"]
    n, m = Q.shape[:2]
    allp = Q[:, ::2].reshape(-1, 3)
    allp = allp[np.isfinite(allp[:, 0])].astype(float)
    tree = cKDTree(allp[:: max(1, len(allp) // 600000)])
    cols = np.arange(0, m, every)
    P = Q[:, cols].reshape(-1, 3).astype(float)
    ok = np.isfinite(P[:, 0])
    owner = np.repeat(np.arange(n), len(cols))
    out_dir = np.zeros_like(P)
    lk_of = St["lock"][owner]
    for li in np.unique(lk_of[ok]):
        sel = ok & (lk_of == li)
        core = (locks[int(li)].get("core") if locks is not None else None)
        out_dir[sel] = _outward(P[sel], C, core if (core is not None and len(core) >= 2 and St["cls"][owner[np.nonzero(sel)[0][0]]] == "tail") else None)
    cnt = np.zeros(len(P))
    for st_ in steps:
        q = P[ok] + out_dir[ok] * st_
        cnt[ok] += tree.query_ball_point(q, r, return_length=True)
    full = max(float(np.percentile(cnt[ok], 90)), 1.0) if ok.any() else 1.0
    sh = np.clip(cnt / full, 0, 1).reshape(n, len(cols))
    out = np.zeros((n, m))
    for c_ in range(m):  # (stations between the sampled ones: linear)
        k = c_ / every
        k0 = min(int(np.floor(k)), len(cols) - 1)
        k1 = min(k0 + 1, len(cols) - 1)
        f = k - k0
        out[:, c_] = sh[:, k0] * (1 - f) + sh[:, k1] * f
    return out


def strand_tones(St: dict, look: dict, locks: list | None = None, shade=None) -> np.ndarray:
    """Each strand's tone at each station (hair_colour.strand_tone: lock lightness, broad / thin highlight ribbons,
    strand contrast, sun by age), / peak: (n, stations) in 0..1. Baked into the cards' pictures, so a card carries
    its strands' own ribbons (a vertex colour per card made the tail a patchwork of light and dark blocks)."""
    from . import hair_colour as hcol
    R = St["root"]
    lv, cb = _cells(R, 0.012, 19, -1, 1), _cells(R, 0.015, 22, 1e-4, 1)
    ch, cm = _cells(R, 0.004, 18, 1e-4, 1), _cells(R, 0.0015, 23, -1, 1)
    a0 = np.where(St["cls"] == "tail", hcol.TAIL_AGE, 0.0)
    age = a0[:, None] + np.arange(St["Q"].shape[1])[None] * STEP
    n = len(R)
    t = hcol.strand_tone(look, age.ravel(), np.repeat(lv, age.shape[1]),
                         np.zeros(age.size) if shade is None else np.asarray(shade, float).ravel(),
                         np.repeat(np.maximum(ch, cb * 0.9), age.shape[1]), np.repeat(cm, age.shape[1]), 0.0,
                         np.repeat((St["cls"] == "face").astype(float), age.shape[1]))
    return np.clip(np.asarray(t).reshape(n, -1) / (TONE_HEAD * hcol.peak(look)), 0, 1)


def bake(cards: list, St: dict, W: int, H: int, ss: int = 2, seed: int = 0, look: dict | None = None,
         C=None, locks: list | None = None, tones=None, aniso: float | None = None) -> dict:
    """The baked cards' pictures in one W x H block: every card's own strands projected along its normal into its
    island (rows = along the card, root at the top; columns = across, the card's centre line in the middle).
    {"alpha", "id", "depth", "root", "flow" (H, W, 2: across / along in -1..1), "nohl" (no highlights: fly islands),
    "islands": [(x, y, w, h)] per card, "texel": m across a texel}."""
    from PIL import Image, ImageDraw
    from scipy import ndimage
    isl, ra = layout(cards, W, H, aniso)
    A = np.zeros((H, W), np.float32)
    ID, DP, RT, FX, FY, TN = (np.zeros((H, W), np.float32) for _ in range(6))
    if tones is None:
        tones = strand_tones(St, look or {}, shade=strand_shade(St, C, locks) if C is not None else None)
    NOHL = np.zeros((H, W), bool)
    rng = np.random.default_rng(seed + 101)
    for c, (x0, y0, w, h) in zip(cards, isl):
        mem = np.asarray(c["strands"], int)
        if c.get("draw", 1.0) < 1.0 and len(mem) > MIN_STRANDS:
            mem = mem[St["rand"][mem] < c["draw"]] if (St["rand"][mem] < c["draw"]).sum() >= MIN_STRANDS else mem
        hwm = float(np.max(c["hw"]))
        L = float(c["s"][-1])
        W2, H2 = w * ss, h * ss
        ims = [Image.new("L", (W2, H2), 0) for _ in range(7)]
        dr = [ImageDraw.Draw(i) for i in ims]
        segs = []
        lw = max(1, int(round(ss * max(1.0, 1.2 * 8e-5 / ra))))  # (a flyaway drawn 2 texels wide was a 1 mm dark wire)
        if c.get("kid_cover"):  # children until the drawn hairs' widths add up to kid_cover x the card's width
            c = {**c, "kids": int(np.clip(np.ceil(c["kid_cover"] * 2 * hwm / (max(len(mem), 1) * lw / ss * ra)), 1, c.get("kid_max", 12)))}
        for j in mem:
            q = St["Q"][j]
            ok = np.isfinite(q[:, 0])
            q = q[ok].astype(float)
            if len(q) < 2:
                continue
            ax, al, dp = _card_coords(c, q, smooth=True)
            inside = (np.abs(ax) <= hwm) & (al >= 0) & (al <= L)
            if not c.get("fly") and inside.mean() < IN_SHARE:
                continue
            frac = np.nonzero(ok)[0] * STEP / max(float(St["len"][j]), 1e-6)
            for k_ in range(int(c.get("kids", 1))):  # a groom strand stands for many real hairs: at a fine texel each
                # is drawn as `kids` hairs offset across (filling the gaps a sparse groom leaves), each ending at its own
                # length (the tip a feathered fringe in alpha, not a cut block) with its own tone
                if k_ == 0:
                    segs.append((float(np.median(dp)), ax, al, dp, frac, float(St["rand"][j]), tones[j][ok]))
                    continue
                end = 1.0 - KID_TIP * rng.random() ** 0.7
                n_ = max(2, int(np.searchsorted(frac, end)))
                sh = rng.normal(0.0, c.get("kid_spread", 0.001))
                dd = rng.normal(0.0, 0.0008)
                segs.append((float(np.median(dp)) + dd, ax[:n_] + sh, al[:n_], dp[:n_] + dd, frac[:n_] / max(end, 1e-3),
                             float((St["rand"][j] + 0.618 * k_) % 1.0), tones[j][ok][:n_] * (
                                 float(rng.choice(c["tone_ratio"])) if c.get("tone_ratio") is not None
                                 else rng.uniform(0.88, 1.12))))
        if not segs:
            continue
        dps = np.concatenate([s_[3] for s_ in segs])
        lo, hi = np.percentile(dps, 5), np.percentile(dps, 95)
        fly = bool(c.get("fly"))
        rib = None
        if RIBBON_SHARE > 0 and not c.get("fly") and c.get("cls") in ("head", "tail"):  # highlight RIBBONS (see RIBBON_W)
            nb = max(1, int(np.ceil(2 * hwm / RIBBON_W)))
            rrng = np.random.default_rng(seed + 7919 + int(c.get("_tile_seed", len(segs))))
            rib = (rrng.random(nb) < RIBBON_SHARE, rrng.random(nb) * 6.283, nb,
                   RIBBON_GAIN * float((look or {}).get("highlight_contrast", 0.6)) / 0.6 * (0.5 if c.get("cls") == "tail" else 1.0))
        for _, ax, al, dp, frac, rnd, tn_ in sorted(segs, key=lambda t: t[0]):  # deeper strands first
            if rib is not None and rnd < 0.5:  # (half the hairs of a ribbon: all of them was pale tape, th_V74)
                bi = int(np.clip((float(np.median(ax)) + hwm) / (2 * hwm) * rib[2], 0, rib[2] - 1))
                if rib[0][bi]:  # comes and goes along its length on its own rhythm (th_V73)
                    tn_ = np.clip(tn_ * (1 + rib[3] * (0.58 + 0.42 * np.sin(al * 38.0 + rib[1][bi]))
                                         * np.clip((al - 0.01) / 0.06, 0, 1)), 0, 1)
            X = (ax / (2 * hwm) + 0.5) * W2
            Y = al / L * H2
            pts = list(zip(X.tolist(), Y.tolist()))
            dn = np.clip((dp - lo) / max(hi - lo, 1e-6), 0, 1)
            tx, ty = np.gradient(X), np.gradient(Y)
            tn = np.maximum(np.hypot(tx, ty), 1e-9)
            dX, dY = np.diff(ax), np.diff(al)  # (in metres: the island's texels are not square)
            keep = np.abs(dY) >= SIDEWAYS * np.hypot(dX, dY)
            for k in range(len(pts) - 1):
                if not (keep[k] or fly):
                    continue
                seg_ = [pts[k], pts[k + 1]]
                lw_ = lw if frac[k] < 0.8 else max(1, lw // 2)  # (uncut hair ends in a point)
                dr[0].line(seg_, fill=255, width=lw_)
                dr[1].line(seg_, fill=int(1 + 254 * rnd), width=lw_)
                dr[2].line(seg_, fill=int(1 + 254 * dn[k]), width=lw_)
                dr[3].line(seg_, fill=int(255 * (1 - min(frac[k], 1.0))), width=lw_)
                dr[4].line(seg_, fill=int(127.5 + 127 * tx[k] / tn[k]), width=lw_)
                dr[5].line(seg_, fill=int(127.5 + 127 * ty[k] / tn[k]), width=lw_)
                dr[6].line(seg_, fill=int(1 + 254 * tn_[k]), width=lw_)
        a, idm, dep, rt, fx, fy, tn2 = (np.asarray(i.resize((w, h), Image.BOX), np.float32) / 255 for i in ims)
        cov = np.maximum(a, 1e-3)
        idm, dep, rt, fx, fy, tn2 = (np.clip(m / cov, 0, 1) for m in (idm, dep, rt, fx, fy, tn2))
        drawn = a > 0.15
        if drawn.any() and not drawn.all():  # texels between strands carry the nearest strand's tone / root / flow
            # (the coverage core is opaque there: with tone 0 it showed as dark dashes, the side of the head as brush
            # strokes, b10)
            ix = ndimage.distance_transform_edt(~drawn, return_distances=False, return_indices=True)
            rt, fx, fy, tn2 = (m[ix[0], ix[1]] for m in (rt, fx, fy, tn2))
        if fly or c.get("cls") == "face":  # (face wisps: a few hairs a card drawn a texel wide each read as solid pale
            # ribbons, review c7; a real hair is ~1/8 of a texel)
            a = a * c.get("alpha_k", 0.45 if fly else FACE_ALPHA)  # a single hair in the open: soft (alpha-to-coverage / dither keep it a hair, not a wire)
        xx = (np.arange(w) + 0.5) / w
        yy = (np.arange(h)[:, None] + 0.5) / h
        if c.get("edge") and HL_SOFT > 0:  # a hairline card's roots: sparse, lighter hair the skin shows through
            # (the groom's hairline is +18 L* over the hair behind it, these cards' +1.5: alpha-tested roots drawn at
            # the deep tone were a hard dark rim, hairline.py g1v0 / g1v1). Thin hairs drop under the cutoff, those
            # left are lit (no depth shade) and lighter, as hair over skin at 1 m
            rr = _ss(np.clip((float(c.get("s0", 0.0)) + yy * L) / HL_SOFT, 0.0, 1.0))  # 0 at the root .. 1 past HL_SOFT
            a = a * (HL_ALPHA + (1 - HL_ALPHA) * rr)
            dep = np.maximum(dep, 1.0 - rr * (1.0 - dep))
            tn2 = np.clip(tn2 * (1.0 + HL_LIFT * (1.0 - rr)), 0, 1)
        if c.get("cls") == "face" and WISP_LIFT > 0:  # a face-framing wisp hangs in the open over skin: lit, no depth
            # shade, lighter (wispL.py g1v1 at 1 m: groom wisps L* 54 over 2175 px, the cards' 38.6 over 560 px: dark
            # stiff strings in front of the ear, g2_b17 / g3_b18)
            dep = np.ones_like(dep)  # (dep is 1 - depth: 1 = on top, unshaded)
            tn2 = np.clip(tn2 * (1.0 + WISP_LIFT), 0, 1)
        if c.get("cls") == "tail" and TAIL_TONE != 1.0:  # (round 24) the tail cards' tone x this: against gSc (the groom
            # with its own shadow) the tail was +8.9 L* at the back (g1backl) and +3.0 at 3/4 front, the head cards ~+2 / 0
            tn2 = np.clip(tn2 * TAIL_TONE, 0, 1)
        if TONE_CONTRAST != 1.0 and not fly and c.get("cls") in ("head", "tail") and (a > 0.15).any():
            m_ = float(np.median(tn2[a > 0.15]))  # (round 25) strand contrast about the island's median
            k_ = TONE_CONTRAST_TAIL if (c.get("cls") == "tail" and TONE_CONTRAST_TAIL > 0) else TONE_CONTRAST
            kd_ = TONE_CONTRAST_DARK if TONE_CONTRAST_DARK > 0 else k_
            tn2 = np.clip(m_ + np.where(tn2 > m_, k_, kd_) * (tn2 - m_), 0, 1)
        if c.get("cls") == "tail" and TAIL_ROOT_LIFT > 0:
            rr_ = 1.0 - _ss(np.clip((float(c.get("s0", 0.0)) + yy * L) / TAIL_ROOT_LEN, 0.0, 1.0))  # 1 at the root
            dep = np.maximum(dep, rr_ + (1.0 - rr_) * dep)
            tn2 = np.clip(tn2 * (1.0 + TAIL_ROOT_LIFT * rr_), 0, 1)
        if c.get("cls") == "tail" and TIP_FADE_TAIL > 0:  # the tail's hairs end one by one under the cutoff
            a = a * (1.0 - _ss(np.clip((yy - (1.0 - TIP_FADE_TAIL)) / TIP_FADE_TAIL, 0.0, 1.0)))
        if c["layer"] == 0 and c.get("cls") in ("head", "tail"):  # coverage: an opaque core under the strands where they are (no scalp between)
            # (not into the tips: an opaque core to the card's end was a straight cut with a dark band, Tess's tail)
            base = np.clip(ndimage.gaussian_filter(a, 1.5) * 2.2, 0, 1) * 0.92 * (1 - _ss((yy - 0.6) / 0.3)) \
                * _ss((yy * L - BASE_IN) / 0.008)
            under = a < base
            idm = np.where(under, a * idm + (1 - a) * rng.uniform(0.3, 0.7), idm)
            dep = np.where(under, a * dep + (1 - a) * 0.3, dep)
            a = np.maximum(a, base)
        # the picture fades out at the card's sides and in from its root (no hard card edge, no root line at the part)
        # (over at least a texel and a half: a 6-texel flyaway island kept its full edge column)
        a = a * (_ss((0.5 - np.abs(xx - 0.5)) / max(0.5 * EDGE_FADE, 1.5 / w)))[None] \
            * _ss(yy / max(ROOT_FADE / L, 1.5 / h))
        A[y0:y0 + h, x0:x0 + w] = a
        ID[y0:y0 + h, x0:x0 + w], DP[y0:y0 + h, x0:x0 + w], RT[y0:y0 + h, x0:x0 + w] = idm, dep, rt
        FX[y0:y0 + h, x0:x0 + w], FY[y0:y0 + h, x0:x0 + w] = fx * 2 - 1, fy * 2 - 1
        TN[y0:y0 + h, x0:x0 + w] = np.where(a > 0.02, tn2, float(np.median(tn2[a > 0.5])) if (a > 0.5).any() else 0.5)
        NOHL[y0:y0 + h, x0:x0 + w] = fly
    solid = A > 0.5
    if solid.any():  # values carried past each strand's edge (no dark fringe under filtering)
        ix = ndimage.distance_transform_edt(~solid, return_distances=False, return_indices=True)
        ID, DP, RT, FX, FY, TN = (m[ix[0], ix[1]] for m in (ID, DP, RT, FX, FY, TN))
    return {"alpha": A, "id": ID, "depth": DP, "root": RT, "flow": np.stack([FX, FY], -1), "nohl": NOHL, "tone": TN,
            "islands": isl, "texel": ra}


def _tile_groups(cards: list) -> list:
    """Card groups that may share a picture: class (head / tail / face / fly), coverage vs upper layers."""
    def g(c):
        cls = "fly" if c.get("fly") else str(c.get("cls"))
        return (cls, 0 if (int(c["layer"]) == 0 and cls in ("head", "tail")) else 1)
    keys = [g(c) for c in cards]
    return keys


def bake_tiles(cards: list, St: dict, W: int, H: int, n: int = TILES, ss: int = 2, seed: int = 0,
               look: dict | None = None, C=None, locks: list | None = None) -> dict:
    """Shared card pictures, as studios do (Epic's Hair Card Generator: "Num Textures" far fewer than cards, a texture
    group per layer; a library of clump tiles): cards are grouped by class / layer and clustered on length and width,
    each cluster's medoid card is baked at a fine texel (one 2048 shared by ~500 unique islands gave ~1 texel/mm:
    smeared bands, no strands), every card of the cluster wears that picture, and its own strands' tone ratio is its
    tint (bake "tint", x tone_k). Returns bake()'s dict with "islands" per CARD, "tint", "tile" (per card)."""
    tones = strand_tones(St, look or {}, shade=strand_shade(St, C, locks) if C is not None else None)
    keys = _tile_groups(cards)
    L = np.array([float(c["s"][-1]) for c in cards])
    Wd = np.array([2 * float(np.max(c["hw"])) for c in cards])
    area = L * Wd * np.array([_density(c) for c in cards])
    gk = sorted(set(keys))
    ga = {k: float(area[[i for i, x in enumerate(keys) if x == k]].sum()) for k in gk}
    tot = sum(ga.values())
    # tiles per group by sqrt of its area (small groups still get one), at least 1
    raw = {k: np.sqrt(ga[k] / tot) for k in gk}
    kn = {k: max(1, int(round(n * raw[k] / sum(raw.values())))) for k in gk}
    reps, tile = [], np.zeros(len(cards), int)
    for k in gk:
        idx = np.array([i for i, x in enumerate(keys) if x == k])
        kk = min(kn[k], len(idx))
        F = np.stack([np.log(L[idx]) * 3.0, np.log(Wd[idx])], 1)
        lab = kmeans(F, kk, seed=seed) if kk > 1 else np.zeros(len(idx), int)
        for q in np.unique(lab):
            mem = idx[lab == q]
            f = F[lab == q]
            # the medoid among the cards with the most strands (a sparse card's picture would be a sparse tile)
            ns = np.array([len(cards[i]["strands"]) for i in mem])
            ok = ns >= np.percentile(ns, 50)
            d = np.linalg.norm(f - np.median(f, 0), axis=1) + np.where(ok, 0.0, 1e3)
            r = int(mem[int(np.argmin(d))])
            tile[mem] = len(reps)
            reps.append(r)
    R = []
    for r in reps:
        c = dict(cards[r])
        ns = max(len(c["strands"]), 1)
        hw = float(np.max(c["hw"]))
        if not c.get("fly") and c.get("cls") != "face":
            c["kid_cover"], c["kid_spread"] = KID_COVER, 2 * hw / ns
        else:  # face wisps and flyaways: at a fine texel one hair is ~0.2 mm at 0.45-0.55 alpha, invisible (c9: "wisps
            # missing", 7-9 MAJOR mentions); a few hairs each, drawn near opaque (the soft alpha was for 1 mm texels)
            c["kid_cover"], c["kid_spread"] = KID_WISP, max(2 * hw / ns, 0.0006)
            c["alpha_k"], c["kid_max"] = WISP_ALPHA, (3 if c.get("fly") else WISP_KIDS_FACE)
        R.append(c)
    if TILE_TONE_POOL > 0:  # the tile's child hairs wear the tone spread of EVERY strand its cards stand for
        sm = np.array([float(np.nanmean(t)) if np.isfinite(t).any() else np.nan for t in tones])
        for q, r in enumerate(reps):
            if R[q].get("fly") or R[q].get("cls") == "face":
                continue
            pool = np.concatenate([np.asarray(cards[i]["strands"], int) for i in np.nonzero(tile == q)[0]])
            v = sm[pool][np.isfinite(sm[pool])]
            if len(v) < 4:
                continue
            ratio = np.clip(1.0 + TILE_TONE_POOL * (v / max(float(np.mean(v)), 1e-3) - 1.0), 0.4, 2.5)
            R[q]["tone_ratio"] = ratio
        _rr = [R[q]["tone_ratio"] for q in range(len(R)) if R[q].get("tone_ratio") is not None]
        if _rr:
            _a = np.concatenate(_rr)
            print(f"tile tone pool: {len(_rr)} tiles, ratio p5 / p50 / p95 / p99 = "
                  f"{' / '.join(f'{x:.2f}' for x in np.percentile(_a, [5, 50, 95, 99]))}", flush=True)
    B = bake(R, St, W, H, ss=ss, seed=seed, look=look, C=C, locks=locks, tones=tones, aniso=TILE_ANISO)
    # tint: a card's strands' mean tone / its tile's
    def mt(c):
        m = np.asarray(c["strands"], int)
        t = tones[m] if len(m) else np.full((1, 1), 0.5)
        return float(np.nanmean(t)) if np.isfinite(t).any() else 0.5
    rt = [max(mt(cards[r]), 1e-3) for r in reps]
    tint = np.array([np.clip(mt(c) / rt[tile[i]], *((0.7, 1.4) if (c.get("fly") or c.get("cls") == "face")
                                                      else TINT_TOP if (c.get("cls") == "head" and c.get("layer") == 2)
                                                      else TINT_RANGE)) for i, c in enumerate(cards)])
    if NAPE_LIFT > 0 and C is not None:  # the nape's head cards out of the depth shade (see NAPE_LIFT)
        R0 = np.asarray(St["root"], float)
        for i, c in enumerate(cards):
            # (tail cards too: b23's dark serrated marks behind the ear are HANGING layer-1 cards, flat passes per
            # range: tris 13668-17114 alone draw them, head cards none; the head-only lift changed nothing)
            if c.get("cls") not in ("head", "tail") or not len(c["strands"]):
                continue
            if c.get("cls") == "tail" and c.get("layer") != 1:  # only the range the trace named (hanging layer 1):
                continue  # b24 lifted every tail card in the band, 1 m hair L* overshot the groom's (k 0.83-0.89)
            r_ = R0[np.asarray(c["strands"], int)].mean(0) - np.asarray(C, float)
            w_ = _ss(np.clip((-r_[2] - NAPE_BAND[0]) / (NAPE_BAND[1] - NAPE_BAND[0]), 0, 1)) \
                * _ss(np.clip((r_[1] - NAPE_Y[0]) / (NAPE_Y[1] - NAPE_Y[0]), 0, 1))
            tint[i] *= 1.0 + NAPE_LIFT * float(w_)
    B["tile_islands"] = B["islands"]
    B["islands"] = [B["tile_islands"][t] for t in tile]
    B["tint"], B["tile"], B["reps"] = tint, tile, reps
    return B
