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
HOOK_RISE = 0.0  # (round 26) m: a head card that comes down from its highest point and rises again by more than this ends at
# its low point (0 = off)
HOOK_LAYER_MIN = 1  # HOOK_RISE only on head layers from this up (round 26: on layer 0 it cut 70 nape cards rising to the tie)
TONE_BACK = 0.85  # (round 26) head cards rooted behind the head's centre: tint x this (b33 back head p50 +8 L* over gSc)
TONE_FRONT = 0.85  # (round 26) head cards rooted at the front top: tint x this (b33 front crown p50 23 vs gSc 32)
TONE_POS_Y = (-0.02, 0.02)  # m from the head's centre along y (front -y .. back): TONE_FRONT -> TONE_BACK, smoothstep
GREY_TILES = 1.0  # (c2, Garrett) tiles are clustered on their cards' grey share too (x this vs log length / width) and
# each tile draws ITS cards' share of grey hairs (B["gshare"], per atlas pixel): the atlas drew one share everywhere
# (look.grey_share by strand id), so G88a's silver sides / temples (locks' grey .65, top .22) came out the head's tone
GREY_TINT = 0.0  # (c1, Garrett) head / tail cards: tint x (1 + this x (the card's locks' grey - the median card's)); 0 = off
TAIL_TONE = 0.62  # (round 24; 1.0 before) tail (hanging) cards' tone x this: the tail alone was +9 L* (back) / +3 (3/4) over gSc, 0.75: +2.4 / -3.9, head cards unchanged
TONE_CONTRAST = 2.2  # (round 25) head / tail card pictures: each hair's tone spread about its island's median x this (the
# groom's light / dark strands: gSc hair boxes p10..p90 span ~25-30 L*, b32's ~13-16 at the same mean; t25/hl.py)
TONE_CONTRAST_DARK = 1.3  # the stretch below the median (0 = the same k): c22's front crown p10 fell 12.3 -> 7.1 (gSc 19.9)
TONE_CONTRAST_TAIL = 4.5  # the same for tail (hanging) cards (0 = TONE_CONTRAST)
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
    if lk.get("lies"):  # a short loose cut's scalp-rooted lock (hair.cards_job): free (not tied) but lying on the head
        return "head"
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
    # an EVEN groom's strands (hair_even*: one field over the scalp, not grown per lock; Garrett's G88a) all carry
    # lock 0, so every one took lock 0's class (a free lock: 100% "tail", the ponytail's knobs on a short cut, c1b).
    # They are scalp-rooted lying hair: each takes the nearest scalp-rooted lock's id (class, grey, hairline flags)
    ev = np.asarray([names[int(D["obj"][j])].startswith("hair_even") for j in keep], bool)
    if ev.any():
        from scipy.spatial import cKDTree
        cand = [li for li, k in enumerate(locks) if float(k.get("free", 0.0)) <= 0.5 and not int(k.get("hairs") or 0)
                and len(k.get("pts") or [])] or [li for li, k in enumerate(locks) if not int(k.get("hairs") or 0)
                                                 and len(k.get("pts") or [])]  # (a loose groom: every lock is free)
        if cand:
            R_ = np.asarray([np.asarray(locks[li]["pts"][0], float) for li in cand])
            _, ki = cKDTree(R_).query(np.nan_to_num(Q[ev, 0].astype(float)))
            lock[ev] = np.asarray(cand, int)[ki]
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
        spread: float = 90.0, reference: bool = True, tip_taper=None, medoid: float = 0.0, per_strand: float = 0.0,
        min_stations: int | None = None, min_len: float | None = None) -> dict | None:
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
               twist=0.0 if reference else np.radians(TWIST_HANG),
               min_stations=MIN_STATIONS if min_stations is None else int(min_stations))
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
    if s[-1] < (FIT_MIN_LEN if min_len is None else min_len):
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


MIN_STATIONS = 4  # (c6 A/B: 3 lost, OLD 5-0) fewest STEP stations a clump's card may have (4 = 12 mm: Garrett's 9-11 mm side / nape hairs, 42.8k of
# 192k strands, got no card; the c6 lever is 3 with FIT_MIN_LEN .006)
SPLIT_DEPTH = 0  # (c6 lever, off: part of the build that lost the A/B; 4 = on) a clump that fit() can't make a card of is split in two, up to this many times (0 = off: dropped, before c6)
SPLIT_MIN = 6  # strands: the smallest clump that is split again
ENV_FALLBACK = 1.0  # 1: envelope() falls back to uniform sphere cells where a 3-deg bin is thin (b25); 0 = off (A/B, round 18)


GRADE_SLOPE = 0.0  # (c13, Garrett) m per deg: the head cards' envelope GRADED down the back: no bin's radius drops more
# than this per degree of elevation below a higher bin's (a downward dilation over GRADE_BAND), and the head cards are
# raised onto that graded surface where it stands over the plain one (_grade_fill). The long top hair's ends over the
# short back made a 5-7 mm step in ONE 6 deg bin at elev 30-36 on the back midline (the strands' median; c12 ledge.py),
# the cards copied it; Garrett's photo shows no ledge, the groom's own 98th-percentile tips grade it over ~20 deg
# (0.3 mm / deg). 0 = off
GRADE_BAND = 20.0  # deg of elevation the grade reaches down
GRADE_AZ = 100.0  # deg: only where |azimuth| (0 = the face, 180 = the back) is over this (the back of the head)
_GRADED = []  # (c13) per head card: its largest raise by the grade (m), printed after the cut
GRADE_SEAT = 0.015  # m: the raise eases in over a card's first this-many m from its root (seated roots stay seated)


def envelope(St: dict, C, deg: float = 3.0, pct: float = 97.0, grade: float = 0.0):
    """The head hair's outer surface seen from the head's centre: a function points -> the strands' `pct` radius in
    their (azimuth, elevation) bin (NaN where too few strands). `grade` (m / deg, GRADE_SLOPE): behind GRADE_AZ each
    bin is raised to max over the GRADE_BAND above it of (their radius - grade x the elevation between)."""
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
    if grade > 0:
        g_ = dict(env)
        for k, v in env.items():
            ia, ie = k // 100000, k % 100000
            if ie > 50000:  # (negative elevation bins: python floor division keeps ia, ie consistent; ie wraps)
                ia, ie = ia + 1, ie - 100000
            if abs((ia + 0.5) * deg) <= GRADE_AZ:
                continue
            best = v if np.isfinite(v) else -np.inf
            for j in range(1, int(np.ceil(GRADE_BAND / deg)) + 1):
                w_ = env.get(int(ia * 100000 + ie + j), np.nan)
                if np.isfinite(w_):
                    best = max(best, w_ - grade * j * deg)
            if np.isfinite(best):
                g_[k] = float(best)
        env = g_
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


HEAD_LIFT = 0.0  # m (c12): every head layer moved out along its normal by this (still under the envelope, the root
# seated by ROOT_SEAT). The head cards' outer surface sat 3-4 mm (p90) under the groom's in every region (c12 vol.py:
# temple p90 5.9 vs 9.7 mm), and HEAD_SN_MAX was a dead lever there (clump spreads under its 3 mm cap: c12v1 = c11L)


def layer_offset(sn, la: int, cls: str) -> np.ndarray:
    """A card's offset along its normal from its clump's centre line (m), per station: coverage under, mid at the
    clump, top over it (by the clump's spread `sn` along its normal; a head clump's spread capped at HEAD_SN_MAX)."""
    sn = np.asarray(sn, float)
    if cls == "tail":
        return sn * (-0.6, 0.4, 1.0)[min(la, 2)] + 0.0004 * la
    return np.minimum(sn, HEAD_SN_MAX) * (-0.6 + 0.6 * la) + 0.0004 * la + (HEAD_LIFT if cls == "head" else 0.0)


HEAD_END = 0.35  # a head card runs on to where this share of its clump's strands still run (c5, Garrett: the hairline
# strands' last fifth lay off every card at the front / temples, 57-77 %: the cut at .35 left the edge band bare)
FIT_MIN_LEN = 0.01  # (c6 lever: .006 with MIN_STATIONS 3; lost the A/B)  # m: a card shorter than this is dropped (c5, Garrett: 64-68 % of the hairline strands behind the ears
# were in NO card, their short converging clumps' cards under 1 cm)
ROOT_SEAT = 0.03  # (round 27; default from round 28: b35, blind review won front + 3/4, back tie) m along a head card from its root over which it is eased down (smoothstep) to ROOT_SEAT_GAP
ROOT_SEAT_GAP = 0.003  # over its strands' roots' radius: top cards started 88-92 mm out over a ~76 mm cap at the front
# crown (the layer offsets + lifted roots), each a straight-cut root edge 10-15 mm in the air: the two hooked flaps on
# the front outline (round 27 hooktr.py, cards L0 48 / 53, L1 125 / 126, L2 190 / 192); 0 = off


CROWN_FILL = 0.0  # (round 31) share of the way a head card is raised (only raised, never lowered) to the strands'
# ENV_PCT envelope less ENV_UNDER, less CROWN_GAP per layer under the top: each card sat at its OWN clump's mean (+0.6 x
# a spread capped at 3 mm), so over the crown the cards' shell was 5-9 mm (worst 17) under the groom's p99 radius and
# 7-10 mm under its p90 (t31/crownr.py), Joe: "the hair is chopped off at the top"; 0 = off
CROWN_GAP = 0.002  # m between the raised layers
CROWN_EL = 20.0  # deg over the head's centre: the raise ramps in from here (smoothstep over CROWN_EL..CROWN_EL + 25)


CROWN_END = 0.0  # m: the raise eases to nothing over a card's last this-many m (a raised free end stood as a flap); 0 = off
CROWN_SEAT = 0.0  # (round 32) m: the raise eases in over a card's first this-many m from its root (smoothstep), so the
# root ROOT_SEAT seated stays seated (r31: CROWN_FILL lifted the seated roots back up = the front-corner flaps); 0 = off
CROWN_SEAT_Y = 9.0  # (round 32) m: CROWN_SEAT only for cards rooted in front of the head's centre + this along y (Blender
# -y is the face): roots further back (the crown, behind the front outline) are raised from the root; 9 = everywhere
CROWN_LAYERS = ()  # (round 32) layers the raise applies to, counted from the top (0 = the top layer); () = all


def _crown_fill(P, la: int, n_layers: int, env, C, s=None) -> np.ndarray:
    """A head card raised toward the strands' envelope over the top of the head (see CROWN_FILL)."""
    P = np.asarray(P, float)
    d = P - np.asarray(C, float)
    r = np.linalg.norm(d, axis=1)
    e, _ = env(P)
    el = np.degrees(np.arcsin(np.clip(d[:, 2] / np.maximum(r, 1e-9), -1, 1)))
    w = CROWN_FILL * _ss(np.clip((el - CROWN_EL) / 25.0, 0.0, 1.0))
    if CROWN_LAYERS and (n_layers - 1 - la) not in CROWN_LAYERS:
        return P
    if CROWN_END > 0 and s is not None and len(s):
        s = np.asarray(s, float)
        w = w * _ss(np.clip((s[-1] - s) / CROWN_END, 0.0, 1.0))
    if CROWN_SEAT > 0 and s is not None and len(s) and P[0, 1] < float(np.asarray(C)[1]) + CROWN_SEAT_Y:
        w = w * _ss(np.clip(np.asarray(s, float) / CROWN_SEAT, 0.0, 1.0))
    tgt = np.nan_to_num(np.asarray(e, float), nan=0.0) - ENV_UNDER - CROWN_GAP * (n_layers - 1 - la)
    from scipy.ndimage import gaussian_filter1d
    up = gaussian_filter1d(np.maximum(0.0, tgt - r) * w, 1.5)
    return np.asarray(C, float) + d * ((r + up) / np.maximum(r, 1e-9))[:, None]


def _grade_fill(P, la: int, n_layers: int, env, env_g, C, s=None) -> np.ndarray:
    """(c13) A head card raised (never lowered) onto the GRADED envelope (GRADE_SLOPE) where it stands over the plain
    one, less ENV_UNDER and CROWN_GAP per layer under the top, eased in from the root over GRADE_SEAT."""
    P = np.asarray(P, float)
    d = P - np.asarray(C, float)
    r = np.linalg.norm(d, axis=1)
    e, _ = env(P)
    eg, _ = env_g(P)
    add = np.nan_to_num(np.asarray(eg, float) - np.asarray(e, float), nan=0.0)
    if add.max() <= 5e-4:
        return P
    w = np.clip(add / 0.002, 0.0, 1.0)
    if GRADE_SEAT > 0 and s is not None and len(s):
        w = w * _ss(np.clip(np.asarray(s, float) / GRADE_SEAT, 0.0, 1.0))
    tgt = np.nan_to_num(np.asarray(eg, float), nan=0.0) - ENV_UNDER - CROWN_GAP * (n_layers - 1 - la)
    from scipy.ndimage import gaussian_filter1d
    up = gaussian_filter1d(np.maximum(0.0, tgt - r) * w, 1.5)
    return np.asarray(C, float) + d * ((r + up) / np.maximum(r, 1e-9))[:, None]


def _root_seat(P, s, roots, C) -> np.ndarray:
    """A head card's stations within ROOT_SEAT of its root moved in toward the head's centre, the root itself to
    ROOT_SEAT_GAP over the median radius of its strands' roots (only ever lowered)."""
    P = np.asarray(P, float).copy()
    d = P - np.asarray(C, float)
    r = np.linalg.norm(d, axis=1)
    r0 = float(np.median(np.linalg.norm(np.asarray(roots, float) - np.asarray(C, float), axis=1))) + ROOT_SEAT_GAP
    w = 1.0 - _ss(np.clip(np.asarray(s, float) / ROOT_SEAT, 0.0, 1.0))
    rn = r - w * np.maximum(0.0, r - r0)
    return np.asarray(C, float) + d * (rn / np.maximum(r, 1e-9))[:, None]


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


def _part_root(c: dict, side_of, C, gap: float | None = None) -> None:
    """A head card whose root lies within PART_ROOT_REACH of the part gets a lead-in: from the part's edge (PART_GAP
    off the line, at the root's height over the head) out sideways (away from the part), curving into the card's own
    start (Hermite). The per-station keys are extended with the root station's values."""
    P = np.asarray(c["P"], float)
    sd, dp = side_of(P[:1])
    sd, dp = float(sd[0]), float(dp[0])
    gap = PART_GAP if gap is None else float(gap)
    if sd == 0 or not np.isfinite(dp) or dp > PART_ROOT_REACH or dp < gap + 0.003:
        return
    C = np.asarray(C, float)
    r0 = P[0] - C
    rad = np.linalg.norm(r0)
    nr = r0 / max(rad, 1e-9)
    e = np.array([sd, 0.0, 0.0]) - nr * sd * nr[0]
    if np.linalg.norm(e) < 0.2:
        return
    e /= np.linalg.norm(e)
    R = P[0] - e * (dp - gap)
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


PART_COVER = 0  # (round 33) cover cards per side of the part (0 = off). r32: from the front, the outline's top was the
# part's cards seen end-on (straight-cut root ends as slabs and notches) over a dip at the part, where the groom's
# strands rise off the part and arch over; moving the existing cards (fill, seat, cap) bought 3-4 of 21 px. A cover
# row is what an artist lays last: cards rooted ON the part, front to back, each following the strands that leave the
# part on its side, lifted to those strands' envelope (they rise off the part), tapering and fading to soft tips over
# the side cards, which leave the part under them
COVER_REACH = 0.015  # m: head strands rooted within this of the part feed the cover row
COVER_LEN = 0.07  # m: a cover card's length from the part (it ends on the side cards)
COVER_HW = 0.012  # m: its half width at most
COVER_TAPER = 0.5  # share of its length over which its width tapers to TIP_FLOOR
COVER_FADE = 0.45  # share of its picture at the tip over which the alpha fades out (hairs ending one by one)
COVER_OVER = 0.002  # m: its root starts this far PAST the part line (the two sides' covers meet: no dip at the part)
COVER_SEAT = 0.012  # m: from the root (on the scalp) it rises to the envelope over this (smoothstep)
COVER_UNDER = 0.0015  # m under the head strands' envelope (ENV_PCT)
COVER_DRAW = 1.0  # (0.6 before round 36: f1 adopted) share of its strands drawn on its picture
COVER_TILT = 0.0  # deg: the cover card's plane turned about its own line toward standing up off the head (r33 q97: the
# cover raised the mesh's top 7.6 mm and the front render's top 0 px: a card lying tangent at the top of the dome is seen
# EDGE-ON from the front, so the outline's top is whatever stands up, not the cover). Its across direction tilts toward
# the head's outward radial: from the front its width reads as height, the upper edge soft (tapered, faded)
COVER_SINK = 0.5  # share of the tilt's rise (hw x sin tilt) the line is moved in, so the lower edge tucks into the mass
COVER_PCT = 90.0  # percentile of the head strands' radius the cover is raised to (r33 p6 at ENV_PCT's 90: the cover sat
# with the other cards, the front outline's top unmoved; the groom's outline is its outer strands)


def part_cover(St: dict, C, side_of, env, idx, seed: int = 0) -> list:
    """The part's cover row (see PART_COVER): per side, the head strands `idx` rooted within COVER_REACH of the part
    (over PART_EL) split into PART_COVER runs along it (by root y, front to back); each run is one card fitted to its
    strands, cut to COVER_LEN, led in from COVER_OVER past the part line (_part_root), raised from its root to the
    strands' envelope less COVER_UNDER, tapered (COVER_TAPER). Cards are head cards of the top layer with "cover"."""
    if not PART_COVER or side_of is None or not len(idx):
        return []
    from scipy.ndimage import gaussian_filter1d
    C = np.asarray(C, float)
    if COVER_PCT != ENV_PCT:
        env = envelope(St, C, pct=COVER_PCT)
    root = St["root"][idx]
    sd, dp = side_of(root)
    v = root - C
    el = np.degrees(np.arcsin(np.clip(v[:, 2] / np.maximum(np.linalg.norm(v, axis=1), 1e-9), -1, 1)))
    ok = (sd != 0) & np.isfinite(dp) & (dp < COVER_REACH) & (el > PART_EL)
    top = len(LAYERS["head"]) - 1
    rng = np.random.default_rng(seed + 53)
    out = []
    for s_ in (-1.0, 1.0):
        mem_all = idx[ok & (sd == s_)]
        if len(mem_all) < MIN_STRANDS * 2:
            continue
        n_ = max(1, min(int(PART_COVER), len(mem_all) // MIN_STRANDS))
        y = St["root"][mem_all][:, 1]
        q = np.quantile(y, np.linspace(0, 1, n_ + 1))
        for b in range(n_):
            mem = mem_all[(y >= q[b]) & ((y < q[b + 1]) if b < n_ - 1 else (y <= q[b + 1]))]
            if len(mem) < MIN_STRANDS:
                continue
            c = fit(St["Q"][mem], _cen_of(C, None), end_share=0.35, max_hw=COVER_HW, spread=90.0, reference=True,
                    tip_taper=0.0)
            if c is None:
                continue
            n = len(c["P"])
            k1 = int(np.searchsorted(np.asarray(c["s"], float), COVER_LEN)) + 1
            if k1 < n:
                for k_ in ("P", "T", "N", "X", "bend", "hw", "sn", "u", "share", "out", "rad", "s"):
                    if np.ndim(c.get(k_)) and len(c[k_]) == n:
                        c[k_] = np.asarray(c[k_])[:k1]
            if len(c["P"]) < 4:
                continue
            _part_root(c, side_of, C, gap=-COVER_OVER)
            P = np.asarray(c["P"], float)
            P_fit = P  # (round 35) its picture baked on the fitted line, its share over its own length (r34's arch fix:
            # a 7 cm card over 30 cm strands drew no strand, an EMPTY tile)
            s = np.asarray(c["s"], float)
            d = P - C
            r = np.linalg.norm(d, axis=1)
            e, _ = env(P)
            tgt = np.nan_to_num(np.asarray(e, float), nan=0.0) - COVER_UNDER
            w = _ss(np.clip(s / COVER_SEAT, 0.0, 1.0))
            up = gaussian_filter1d(np.maximum(0.0, tgt - r), 1.5) * w
            P = C + d * ((r + up) / np.maximum(r, 1e-9))[:, None]
            X, N = np.asarray(c["X"], float), np.asarray(c["N"], float)
            if COVER_TILT:  # (see COVER_TILT) the across direction turned toward the outward radial
                Tn = np.asarray(c["T"], float)
                Ru = P - C
                Ru = Ru - (Ru * Tn).sum(1, keepdims=True) * Tn
                Ru /= np.maximum(np.linalg.norm(Ru, axis=1, keepdims=True), 1e-12)
                Xp = X - (X * Ru).sum(1, keepdims=True) * Ru
                Xp /= np.maximum(np.linalg.norm(Xp, axis=1, keepdims=True), 1e-12)
                ta = np.radians(COVER_TILT)
                X = np.cos(ta) * Xp + np.sin(ta) * Ru
                Nn = np.cross(Tn, X)
                N = Nn * np.sign((Nn * N).sum(1, keepdims=True) + 1e-12)
                P = P - Ru * (COVER_SINK * np.sin(ta) * np.asarray(c["hw"], float))[:, None]
            L = max(float(s[-1]), 1e-6)
            f = np.clip((s / L - (1.0 - COVER_TAPER)) / COVER_TAPER, 0.0, 1.0)
            hw = np.asarray(c["hw"], float) * (1.0 - (1.0 - TIP_FLOOR) * _ss(f))
            lk_ = int(np.bincount(St["lock"][mem]).argmax())
            u = (c["i0"] * STEP + s) / max(float(np.percentile(St["len"][mem], 95)), 0.02)
            out.append({"P": P, "X": X, "N": N, "T": c["T"], "bend": c["bend"], "hw": hw,
                        "rad": np.asarray(c["rad"], float) + up, "u": u, "s": s, "kind": "baked", "layer": top,
                        "cls": "head", "prio": top + 0.5 + 0.1 * rng.uniform(), "cval": 1.0, "value": 1.0,
                        "lock": lk_, "sn": c["sn"], "strands": mem, "draw": COVER_DRAW, "s0": c["i0"] * STEP,
                        "wisp": False, "edge": False, "cover": True, "P_fit": P_fit})
    return out


_FILL_BACK: list = []  # (round 35) root x (m from C) of head cards FILL let keep their root (diagnostics)
ARCH = 4  # (round 34; default 4 from round 36 = f1, 0 = off) crown arch cards across the dome (0 = off). r34 card-ID pass (t34/cardid.py, b37 front g1v0): the
# front outline's top is the scalp CAP (52 of 212 columns, the middle) and the ROOT ends (s 0.1-0.3) of crown cards
# rooted at el 60-70 just in front of / over the head centre running back to the tie (outline columns at s < 0.2 on
# their card: 45%). What an artist lays over the dome instead: long cards following the strands that cross the top,
# from under the front layers (roots tucked), arching over at the strands' outer envelope (their BODIES make the
# outline), tips tapered and faded behind the top (out of the front view)
# r34 a10 (strands CROSSING el 70 with the root in front): none; the groom's own front-outline top (t34/strtop.py) is
# strands ROOTED near the centre line (root x -10..+10 mm, el 62-73, 2-3.5 cm in front of C) standing 17-22 mm off the
# scalp 24-48 mm from their roots, then running back. Our cards leave that strip empty (PART_GAP: crown cards rooted at
# x +-27..37) and seat their roots (ROOT_SEAT): the cap is the outline there.
ARCH_EL = 55.0  # deg: head strands rooted over this elevation (over the head centre C) ...
ARCH_X = 0.03  # m: ... and within this of the centre line (|root x - C x|) feed the arch row
ARCH_ROWS = 2  # the strip split by root y into this many rows (front to back), each into ARCH runs by root x
ARCH_LEN = 0.09  # m: a card's length from its strands' roots (its tip tapered and faded behind the top)
ARCH_START = 0.0  # m: its first ARCH_START from the roots dropped
ARCH_SEAT = 0.035  # (0.02 before round 36) m: from its start it rises to the envelope over this (smoothstep; the strands stand 17-22 mm off
# the scalp 24-48 mm from the root)
ARCH_HW = 0.018  # (0.014 before round 36) m: its half width at most
ARCH_PCT = 94.0  # (97 before round 36) percentile of the head strands' radius it is raised to
ARCH_UNDER = 0.001  # m under that
ARCH_FILL = 1  # (round 35; default on from round 36 = f1; needs ARCH; named FILL in round 35, which collided with the bake's FILL = 0.82
# below, so it was on by default and hk.FILL=1 also set the packing share to 1.0) fill the mass UNDER the arch row (r34: the arch read as a crest over air: it
# stood at the strands' p97 over cards that stay at <= p90, a cap at the scalp in the centre strip, and a front row
# rising steeply off its roots). One change, three parts: (a) a head card whose root end runs BACK (x share of its
# first PART_REACH under PART_SIDEWAYS: no visible part there) keeps its root (no PART_GAP cut, no part lead-in), so
# crown cards root in the centre strip as the groom's top strands do (x +-10 mm); (b) the cap under the arch cards is
# raised to their height less FILL_UNDER (hair.cap_fill_arch); (c) the arch's front row eases up over ARCH_SEAT_FRONT
# (its root lies at its strands' own height, under the hairline layer, for longer).
FILL_UNDER = 0.004  # m: the cap under the arch stands this far under the arch cards
FILL_REACH = 8.0  # deg: cap vertices within this of an arch card's surface are raised (fully within hair.CAP_REACH)
ARCH_SEAT_FRONT = 0.05  # m: the front row's rise (ARCH_FILL only)
ARCH_PART_GAP = 0.0  # m (round 36): arch cards in front of the part's back end start this far off it (0 = PART_GAP)
ARCH_ROOT_TAPER = 0.0  # m (round 36): the front arch row's root end narrows to a point over this (0 = off, square)
ARCH_PART_KEEP = 0.0  # (round 36) in front of the part's back end, arch strands rooted within this x PART_GAP of the part
# are dropped (1 = r36d: 605 of Tess's 1106 dropped, a V notch at the part); the cards still start PART_GAP off the part


def arch_row(St: dict, C, idx, seed: int = 0, side_of=None) -> list:
    """The crown arch row (see ARCH): head strands `idx` rooted over ARCH_EL within ARCH_X of the centre line, split by
    root y into ARCH_ROWS rows and each by root x into ARCH runs; each run one card fitted to its strands, from
    ARCH_START to ARCH_LEN from their roots, raised to the strands' ARCH_PCT envelope less
    ARCH_UNDER (eased in over ARCH_SEAT), tapered (COVER_TAPER) and faded (COVER_FADE, "cover")."""
    if not ARCH or not len(idx):
        return []
    from scipy.ndimage import gaussian_filter1d
    C = np.asarray(C, float)
    env = envelope(St, C, pct=ARCH_PCT)
    R = St["root"][idx].astype(float) - C
    el = np.degrees(np.arcsin(np.clip(R[:, 2] / np.maximum(np.linalg.norm(R, axis=1), 1e-9), -1, 1)))
    ok = (el >= ARCH_EL) & (np.abs(R[:, 0]) <= ARCH_X)
    mem_all = idx[ok]
    if len(mem_all) < MIN_STRANDS * 2:
        print(f"arch row: {len(mem_all)} strands in the strip: none", flush=True)
        return []
    yr, xr = R[ok, 1], R[ok, 0]
    # (r34 a4: a run by root x mixed strands sweeping +x and -x off the part: the card followed one, its picture's
    # strands lay 3-4 cm across it, an EMPTY tile) the way each strand leaves its root: +x, -x or back
    Qm = St["Q"][mem_all].astype(float)
    kk = min(Qm.shape[1] - 1, int(round(0.025 / STEP)))
    dv = Qm[:, kk] - Qm[:, 0]
    dv = np.where(np.isfinite(dv), dv, 0.0)
    sx = dv[:, 0] / np.maximum(np.linalg.norm(dv, axis=1), 1e-9)
    way = np.where(sx > 0.5, 1, np.where(sx < -0.5, -1, 0))
    if side_of is not None:  # (round 36) part-safe: the centre strip is used as one only behind the part's back end
        # (side_of's distance inf: no strand there shows a part); in front of it a run takes one side's strands, kept
        # PART_GAP off the part and not sweeping across it (a run over the part line spanned it: test_no_card_spans_the_part)
        sd_, dp_ = side_of(St["root"][mem_all])
        fr_ = np.isfinite(dp_)
        keep_ = ~fr_ | ((sd_ != 0) & (sx * sd_ > -0.5) & (dp_ >= ARCH_PART_KEEP * PART_GAP))
        way = np.where(fr_, 3 * np.asarray(sd_, int) + way, way)  # a run per side AND sweep (back-running
        # strands by the part get their own run on each side: r36e grouped by side alone and the cards bent away, a V notch)
        print(f"arch row: {int(fr_.sum())} strands in front of the part's back end ({int((fr_ & ~keep_).sum())} at or "
              f"across the part dropped)", flush=True)
        mem_all, yr, xr, way = mem_all[keep_], yr[keep_], xr[keep_], way[keep_]
        if len(mem_all) < MIN_STRANDS * 2:
            return []
    way_of = dict(zip(mem_all.tolist(), way.tolist()))
    way_of = np.array([way_of.get(i, 0) for i in range(int(mem_all.max()) + 1)]) if len(mem_all) else np.zeros(1, int)
    nr = max(1, int(ARCH_ROWS))
    qy = np.quantile(yr, np.linspace(0, 1, nr + 1))
    groups = []
    for a_ in range(nr):
        iy = (yr >= qy[a_]) & ((yr < qy[a_ + 1]) if a_ < nr - 1 else (yr <= qy[a_ + 1]))
        for w_ in range(-4, 5):
            iw = iy & (way == w_)
            if iw.sum() < MIN_STRANDS * 2:
                continue
            n_ = max(1, min(int(ARCH), int(iw.sum()) // (MIN_STRANDS * 4)))
            qx = np.quantile(xr[iw], np.linspace(0, 1, n_ + 1))
            for b in range(n_):
                groups.append((a_, mem_all[iw & (xr >= qx[b]) & ((xr < qx[b + 1]) if b < n_ - 1 else (xr <= qx[b + 1]))]))
    top = len(LAYERS["head"]) - 1
    rng = np.random.default_rng(seed + 59)
    out = []
    for row_, mem in groups:
        if len(mem) < MIN_STRANDS:
            continue
        c = fit(St["Q"][mem], _cen_of(C, None), end_share=0.35, max_hw=ARCH_HW, spread=90.0, reference=True,
                tip_taper=0.0)
        if c is None:
            continue
        P = np.asarray(c["P"], float)
        s = np.asarray(c["s"], float)
        st0 = c["i0"] * STEP
        k0 = int(np.searchsorted(s + st0, ARCH_START))
        if side_of is not None and abs(int(np.median(way_of[mem]))) >= 2:  # (round 36) in front of the part's back
            # end: the card starts PART_GAP off the part (its strands' roots by the part line are cut, as head cards')
            _, dc_ = side_of(P)
            ok_ = np.nonzero(dc_ >= (ARCH_PART_GAP if ARCH_PART_GAP > 0 else PART_GAP))[0]
            k0 = max(k0, int(ok_[0]) if len(ok_) else len(P))
        k1 = int(np.searchsorted(s + st0, ARCH_LEN)) + 1
        if k1 - k0 < 6:
            continue
        n = len(P)
        for k_ in ("P", "T", "N", "X", "bend", "hw", "sn", "u", "share", "out", "rad"):
            if np.ndim(c.get(k_)) and len(c[k_]) == n:
                c[k_] = np.asarray(c[k_])[k0:k1]
        c["i0"] += k0
        s = s[k0:k1] - s[k0]
        P = np.asarray(c["P"], float)
        d = P - C
        r_ = np.linalg.norm(d, axis=1)
        e, _ = env(P)
        tgt = np.nan_to_num(np.asarray(e, float), nan=0.0) - ARCH_UNDER
        seat_ = ARCH_SEAT_FRONT if (ARCH_FILL and row_ == 0) else ARCH_SEAT
        w = _ss(np.clip(s / seat_, 0.0, 1.0))
        up = gaussian_filter1d(np.maximum(0.0, tgt - r_), 1.5) * w
        P_fit = P
        P = C + d * ((r_ + up) / np.maximum(r_, 1e-9))[:, None]
        L = max(float(s[-1]), 1e-6)
        f = np.clip((s / L - (1.0 - COVER_TAPER)) / COVER_TAPER, 0.0, 1.0)
        hw = np.asarray(c["hw"], float) * (1.0 - (1.0 - TIP_FLOOR) * _ss(f))
        if ARCH_ROOT_TAPER > 0 and row_ == 0:  # (round 36) the front row's root end narrowed to a point over its first
            # ARCH_ROOT_TAPER: its square root ends, seen end-on at 3/4, were a blocky ridged lump at the crown's front (f1)
            hw = hw * (TIP_FLOOR + (1.0 - TIP_FLOOR) * _ss(np.clip(s / ARCH_ROOT_TAPER, 0.0, 1.0)))
        lk_ = int(np.bincount(St["lock"][mem]).argmax())
        u = (c["i0"] * STEP + s) / max(float(np.percentile(St["len"][mem], 95)), 0.02)
        out.append({"P": P, "X": c["X"], "N": c["N"], "T": c["T"], "bend": c["bend"], "hw": hw,
                    "rad": np.asarray(c["rad"], float) + up, "u": u, "s": s, "kind": "baked", "layer": top,
                    "cls": "head", "prio": top + 0.6 + 0.1 * rng.uniform(), "cval": 1.0, "value": 1.0,
                    "lock": lk_, "sn": c["sn"], "strands": mem, "draw": COVER_DRAW, "s0": c["i0"] * STEP,
                    "wisp": False, "edge": False, "cover": True, "arch": True, "P_fit": P_fit, "row": row_})
    print(f"arch row: {len(mem_all)} strands in the strip -> {len(out)} cards", flush=True)
    return out


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


PART_VISIBLE = 1  # (round 37; coordinator: cards are judged against their source) the top cover rows (arch row, ARCH_FILL
# (a)'s kept roots) may span the part wherever the SOURCE groom shows no part there; they keep off it only where the
# groom's OUTLINE seen along the part has a notch at it (or a gap: no hair over it) (part_visible). 0 = every part
# distance counts (round 36: r36d-g, the V notch at Tess's part, which her groom's outline doesn't have)
PART_DIP = 0.003  # m: a shown part = the groom's outline across the part, seen along it, this far lower at the part line
# than PART_DIP_W either side (the mean of both); no strand points in the band over the part line = a gap = shown.
# (r37 dipprobe: Tess's groom SURFACE does dip at the part, 3-6 mm, 0.5 of the hair's depth there, more in front; 3 mm
# on the surface flagged half her part, r37a: 31 arch cards vs f1's 17. The outline the judge sees has no notch: the
# crown behind the part stands higher.)
PART_DIP_W = 0.012  # m: across the part, either side
PART_DIP_R = 0.002  # m: the outline's bands across the part (the highest head strand point in each)
PART_DIP_REACH = 0.03  # m: points farther than this from the part are never "at a shown part"
PART_DIP_WHOLE = 1  # (round 38) part_visible decides once per part (the median notch over its roots), not per root
PART_DUMP = ""  # (diagnostics) a path: cut saves the head strands and the part at their roots there (npz)


def part_visible(St: dict, C, side_of):
    """`side_of` limited to where the groom SHOWS its part: points -> (side, distance), the distance inf where the
    groom's outline seen ALONG the part (one view: up = the mean radial direction over the part-line roots, across = x
    in that plane; the highest head strand point in each PART_DIP_R band across) has no notch PART_DIP at the part line
    against PART_DIP_W either side. An empty band over the part line with hair either side is a gap: shown. Where
    nothing can be measured the part counts. `f.dip(points)` -> the notch m at the part-line points nearest them (inf =
    gap, NaN = off the part)."""
    C = np.asarray(C, float)
    Q = St["Q"][St["cls"] == "head"][:, ::2].reshape(-1, 3)
    Q = Q[np.isfinite(Q[:, 0])].astype(float) - C
    sd0, d0 = side_of(St["root"][St["cls"] == "head"])
    R0 = St["root"][St["cls"] == "head"][np.isfinite(d0) & (np.asarray(d0) < PART_GAP)].astype(float) - C
    up = R0.mean(0) if len(R0) else np.array([0.0, 0.0, 1.0])
    up /= max(float(np.linalg.norm(up)), 1e-9)
    xt = np.array([1.0, 0.0, 0.0]) - up[0] * up
    xt /= max(float(np.linalg.norm(xt)), 1e-9)
    a, h = Q @ xt, Q @ up
    lo = float(a.min()) if len(a) else 0.0
    nb = int((float(a.max()) - lo) / PART_DIP_R) + 1 if len(a) else 1
    top = np.full(nb, -np.inf)
    if len(a):
        np.maximum.at(top, ((a - lo) / PART_DIP_R).astype(int), h)
    top[~np.isfinite(top)] = np.nan

    def outline(x):
        k = np.floor((np.asarray(x, float) - lo) / PART_DIP_R).astype(int)
        return np.where((k >= 0) & (k < nb), top[np.clip(k, 0, nb - 1)], np.nan)

    def notch_at(ap):
        hc, ha, hb = outline(ap), outline(ap + PART_DIP_W), outline(ap - PART_DIP_W)
        hs = np.where(np.isfinite(ha) & np.isfinite(hb), 0.5 * (ha + hb), np.where(np.isfinite(ha), ha, hb))
        return np.where(np.isfinite(hc), hs - hc, np.where(np.isfinite(hs), np.inf, np.nan))
    tree, notch0 = None, None
    if len(R0):
        from scipy.spatial import cKDTree
        on0 = np.isfinite(d0) & (np.asarray(d0) < PART_GAP)
        notch0 = notch_at(R0 @ xt - np.asarray(sd0, float)[on0] * np.asarray(d0, float)[on0])
        if PART_DIP_WHOLE and (~np.isnan(notch0)).any():
            # (round 38) ONE notch for the whole part: the outline is a single view along it, so roots differ only by
            # where the part line sits across it (a few mm), and per root the notch was noise around the threshold
            # (Tess: p50 1-2 mm; >= 3 mm at 114 / 0 / 389 of 1129 roots for strand points every 2nd / 4th / 8th:
            # t38/np3.py). The median over the part-line roots is stable (1.8 / 1.2 / 2.3 mm).
            m_ = notch0[~np.isnan(notch0)]
            notch0 = np.full(len(notch0), float(np.median(m_)))
        tree = cKDTree(R0)

    def dip(P, sd=None, dist=None):
        P = np.asarray(P, float)
        if sd is None:
            sd, dist = side_of(P)
        sd, dist = np.asarray(sd, float), np.asarray(dist, float)
        out = np.full(len(P), np.nan)
        fin = np.isfinite(dist) & (dist <= PART_DIP_REACH)
        if not fin.any():
            return out
        if tree is not None:  # the notch at the nearest part-line root (side_of's distance is half a gap between
            # roots, not a length to step across: stepped from roots 2-3 cm off, r37a read notches beside the part)
            out[fin] = notch0[tree.query(P[fin] - C)[1]]
        else:
            out[fin] = notch_at((P[fin] - C) @ xt - sd[fin] * dist[fin])
        return out

    def f(P):
        P = np.asarray(P, float)
        sd, dist = side_of(P)
        dp = dip(P, sd, dist)
        shown = ~(np.isfinite(dp) & (dp < PART_DIP))  # unmeasured (bare both sides, off the reach) counts as shown
        return sd, np.where(shown, dist, np.inf)
    f.dip = dip
    f.view = (up, xt)
    return f


_HOOKS: list = []


def cut(D: dict, locks: list, C, S: dict, side_of=None, seed: int = 0, layers: dict | None = None,
        triangles: int = 20000) -> list:
    """Cards cut by clumps, per class and layer (see LAYERS). `side_of(points) -> (side -1/0/+1, distance to the
    part m)` for strand roots, or None. Each card: hair_cards' card keys + "strands" (indices into `St` = the
    module-level strands this cut used, kept on the first card as "_St") and "draw" (share of its strands drawn)."""
    St = strands(D, locks)
    _HOOKS.clear()
    _FILL_BACK.clear()
    env = envelope(St, C, pct=ENV_PCT)
    env_side = envelope(St, C, pct=SIDE_ENV_PCT) if SIDE_ENV_PCT != ENV_PCT else None
    env_g = envelope(St, C, pct=ENV_PCT, grade=GRADE_SLOPE) if GRADE_SLOPE > 0 else None
    _GRADED.clear()
    layers = layers or LAYERS
    rng = np.random.default_rng(seed + 31)
    out = []
    side = np.zeros(len(St["len"]))
    if PART_FROM_STRANDS and side_of is not None:  # (c2: never where the groom says "parting none": Garrett's G88a
        # swept back with no part, the strands' near-even vote (21.7k / 24.2k) made one at the centre front, cards
        # trimmed PART_GAP off it: the M-shaped notch in the hairline, hl.py notch +4.9 % vs the groom's -0.7)
        # the strands' own part first: the spec's default line (x = 3 cm) sat 3 cm off a tied
        # groom's emergent centre part (b25 part dip at col 285, the groom's at 245; top roots sweep -x left of x = 0,
        # +x right of it, t18/partprobe.py)
        side_of = strand_part(St, C) or side_of
    side_vis = side_of  # (round 37) the top cover rows' part: only where the groom shows one (PART_VISIBLE)
    if side_of is not None:
        sd, dist = side_of(St["root"])
        side = np.where(dist < PART_SPLIT, sd, 0.0)
        if PART_DUMP:  # (round 37, diagnostics) the head strands + the part at their roots, for part_visible probes
            hd_ = St["cls"] == "head"
            np.savez_compressed(PART_DUMP, Q=St["Q"][hd_][:, ::2].astype(np.float32), root=St["root"][hd_],
                                sd=sd[hd_], dist=dist[hd_], C=np.asarray(C, float))
        if PART_VISIBLE:
            side_vis = part_visible(St, C, side_of)
            on_ = np.isfinite(dist) & (dist < PART_GAP)
            if on_.any():
                dp_ = side_vis.dip(St["root"][on_], sd[on_], dist[on_])
                dp_ = dp_[np.isfinite(dp_)]
                if len(dp_):
                    print(f"part visible: {int((dp_ >= PART_DIP).sum())} of {len(dp_)} roots on the part show a >= "
                          f"{PART_DIP * 1000:.0f} mm notch in the outline along it (p10 / p50 / p90 "
                          f"{np.percentile(dp_, 10) * 1000:.1f} / {np.percentile(dp_, 50) * 1000:.1f} / "
                          f"{np.percentile(dp_, 90) * 1000:.1f} mm)", flush=True)
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
            todo = [(idx[lab == g], 0) for g in np.unique(lab)]
            while todo:
                mem, dep = todo.pop(0)
                lk = locks[int(np.bincount(St["lock"][mem]).argmax())]
                # (hanging hair runs on to its longest strands' tips: ended where a quarter were left, Tess's tail
                # ended in a straight cut 3 cm short)
                # (and is its outline: a tail's outer strands spread past the 90th percentile; at it the cards' tail
                # was 0.8 of the strands' width)
                end_ = TAIL_END + (TAIL_END_JIT * rng.uniform() if cls == "tail" else 0.0)
                c = fit(St["Q"][mem], _cen_of(C, lk.get("core")), end_share=(FACE_END if cls == "face" else end_) if cls != "head" else HEAD_END,
                        max_hw=max_hw, spread=97.0 if cls == "tail" else 90.0, reference=cls == "head",
                        tip_taper=TIP_TAPER_TAIL if cls == "tail" else TIP_TAPER,
                        medoid=(MEDOID_TAIL_TOP if la == len(LAYERS["tail"]) - 1 else MEDOID_TAIL) if cls == "tail"
                        else MEDOID_FACE if cls == "face" else 0.0,
                        per_strand=HW_PER_STRAND if cls == "tail" else 0.0)
                if c is None:  # (c6) no stretch where half its strands run: a clump spread ALONG the flow (behind the ears:
                    # short strands rooted in a row down the hair's run, 64-68 % of those hairline strands had no card):
                    # split it in two (k-means on the same features) and fit each half
                    if dep < SPLIT_DEPTH and len(mem) >= SPLIT_MIN:
                        sub = kmeans(features(St, mem), 2, seed + 17 * (dep + 1))
                        if 0 < int(sub.sum()) < len(sub):
                            todo += [(mem[sub == 0], dep + 1), (mem[sub == 1], dep + 1)]
                    continue
                if cls == "head" and HOOK_RISE > 0 and la >= HOOK_LAYER_MIN:  # (round 26) a head card that comes down and turns back UP (the two
                    # hooked top-layer flaps at the front crown's outline, t25/crown_layers.png) ends where it turned
                    z_ = np.asarray(c["P"], float)[:, 2]
                    ka = int(np.argmax(z_))
                    rm = np.minimum.accumulate(z_[ka:])
                    up = np.nonzero(z_[ka:] - rm > HOOK_RISE)[0]
                    if len(up):
                        k1 = ka + int(np.argmin(z_[ka:ka + int(up[0]) + 1])) + 1
                        if k1 < 4:
                            continue
                        n_ = len(c["P"])
                        for k_ in ("P", "T", "N", "X", "bend", "hw", "sn", "u", "share", "out", "rad", "s"):
                            if np.ndim(c.get(k_)) and len(c[k_]) == n_:
                                c[k_] = np.asarray(c[k_])[:k1]
                        _HOOKS.append((la, n_, k1))
                back_ = False
                if cls == "head" and ARCH_FILL and side_of is not None:  # (round 35, ARCH_FILL (a)) a root end running back:
                    # no visible part there, the card keeps its root in the centre strip
                    P_ = np.asarray(c["P"], float)
                    kk_ = min(len(P_) - 1, max(1, int(round(PART_REACH / STEP))))
                    dv_ = P_[kk_] - P_[0]
                    back_ = abs(dv_[0]) / max(float(np.linalg.norm(dv_)), 1e-9) < PART_SIDEWAYS
                    # (round 36) part-safe: only behind the part's back end (no voters near the root: distance inf)
                    # (round 37) ... or where the groom shows no part there (PART_VISIBLE: side_vis)
                    back_ = back_ and not bool(np.isfinite(side_vis(P_[:1])[1][0]))
                    if back_:
                        _FILL_BACK.append(float(P_[0, 0] - np.asarray(C, float)[0]))
                if cls == "head" and side_of is not None and not back_:  # its root stays PART_GAP off the part
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
                if cls == "head" and ROOT_SEAT > 0:  # (round 27) the card's root end eased down onto the scalp
                    P = _root_seat(P, c["s"], St["root"][mem], C)
                if cls == "head" and CROWN_FILL > 0:  # (round 31) the head's layers raised toward the strands' envelope (after
                    # the root seat: seated roots were most of the shortfall over the crown)
                    P = _crown_fill(P, la, len(layers[cls]), env, C, c["s"])
                if cls == "head" and env_g is not None:  # (c13) the back's step graded (GRADE_SLOPE)
                    P_ = _grade_fill(P, la, len(layers[cls]), env, env_g, C, c["s"])
                    _GRADED.append(float(np.max(np.linalg.norm(P_ - P, axis=1))) if len(P) else 0.0)
                    P = P_
                kind = "baked"
                u = (c["i0"] * STEP + c["s"]) / max(float(np.percentile(St["len"][mem], 95)), 0.02)
                out.append({"P": P, "X": c["X"], "N": c["N"], "T": c["T"], "bend": c["bend"], "hw": c["hw"],
                            "rad": np.asarray(c["rad"], float) + yo, "u": u, "s": c["s"], "kind": kind, "layer": la, "cls": cls,
                            "prio": la + (-0.8 if cls == "face" else -0.4 if cls == "tail" else 0.0)
                            + 0.1 * rng.uniform(),
                            "cval": 1.0, "value": 1.0, "lock": lk["name"], "sn": c["sn"],
                            "strands": mem, "draw": share, "s0": c["i0"] * STEP, "wisp": cls == "face",
                            "edge": bool(lk.get("at_hairline")) or cls == "face"})
    if PART_COVER and side_of is not None:  # (round 33) the part's cover row, over the side cards
        cov = part_cover(St, C, side_of, env, np.nonzero((St["cls"] == "head") & ~loop)[0], seed)
        for c_ in cov:
            c_["lock"] = locks[c_["lock"]]["name"]
        out.extend(cov)
        print(f"part cover: {len(cov)} cards", flush=True)
    if ARCH:  # (round 34) the crown arch row, over the dome
        arc = arch_row(St, C, np.nonzero((St["cls"] == "head") & ~loop)[0], seed, side_of=side_vis)
        if ARCH_FILL:
            fb_ = np.abs(np.asarray(_FILL_BACK))
            print(f"fill: {len(fb_)} head cards keep their back-running roots ({int((fb_ < 0.015).sum())} rooted within "
                  f"15 mm of the centre line)", flush=True)
        for c_ in arc:
            c_["lock"] = locks[c_["lock"]]["name"]
        out.extend(arc)
    ft = S.get("flow_top")
    ft = ft and {**FLOW_TOP, **(ft if isinstance(ft, dict) else {})}
    if ft and triangles >= float(ft["min_triangles"]):  # (c9) a top layer of a few long cards along the groom's flow, the others' ends tucked under it
        fl = flow_row(St, C, ft, len(layers["head"]) - 1, triangles, seed)
        tuck_under(out, fl, C, float(ft["tuck"]))
        out += fl
    hr = S.get("hairline_row")
    hr = hr and {**HAIRLINE_ROW, **(hr if isinstance(hr, dict) else {})}
    if hr and triangles >= float(hr["min_triangles"]):  # (c9) a dedicated row of short cards along the temple / sideburn hairline band
        out += hairline_row(St, C, hr, env, triangles, seed, env_side=env_side)
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
    if _HOOKS:
        print(f"hook cut: {len(_HOOKS)} head cards (layer, stations kept / of): "
              f"{', '.join(f'L{a} {k}/{n}' for a, n, k in _HOOKS[:12])}", flush=True)
    if out:
        out[0]["_St"] = St
    if _GRADED:
        g_ = np.asarray(_GRADED)
        print(f"grade: {int((g_ > 5e-4).sum())} of {len(g_)} head cards raised onto the graded back (max {1000 * g_.max():.1f} mm)", flush=True)
    return out


# (c9, Garrett; the coordinator: card PLACEMENT as hair artists layer cards, not more levers in the clump cut)
# FLOW TOP LAYER (spec hair.strands.flow_top: true or {options}): a few long cards per sweep side over the top of the
# head, each on a clump of the LONG head strands rooted over `el` (deg over the head's centre), its centre line the
# clump's medoid strand (it follows the groom's flow from the whorl / part), run on to where `end` of its strands
# still run, raised onto the strands' `pct` envelope (less ENV_UNDER) past `seat` m from the root, held under it.
# Every other head card's stations under a flow card are pulled in to `tuck` m under it (their ends tucked under the
# layer above: the surface shows long flowing cards, not many card ends). `cards` = clumps per sweep group at 20k
# triangles (sqrt-scaled with the tier's triangles, at least 2).
FLOW_TOP = {"cards": 8, "el": 30.0, "len_pct": 50.0, "hw": 0.012, "pct": 94.0, "seat": 0.015, "end": 0.15,
            "tuck": 0.0015, "reach": 1.0, "sweep_x": 0.35, "min_triangles": 3000, "lit": 0.0}
# (`lit` (c10): the flow cards' tiles baked out of the depth shade (they lie on top, in the light) and their tone x (1 +
# this): c9's flow tiles took the groom's depth shade though they are the top layer (darker flaps, c9a))
# (`min_triangles`: no row when the cut's triangles are fewer (the far / crowd tier: c9L's rows put far at 1716 index
# triangles, over the crowd range 300-1500; its 8 m tile was a TIE))
# HAIRLINE ROW (spec hair.strands.hairline_row): short cards on the head strands rooted in the temple / sideburn band
# (|az| in `az`, el in `el`, deg from the head's centre; az 0 = the front), `cards` per side at 20k triangles, fitted
# with `min_stations` / `min_len` (the clump cut's MIN_STATIONS 4 / FIT_MIN_LEN drop the 9-17 mm hairs there: no card
# below el ~-15 in front of the ear), half width up to `hw`, laid at layer 1's offset, held under the envelope.
HAIRLINE_ROW = {"cards": 24, "az": (50.0, 100.0), "el": (-40.0, 5.0), "min_stations": 3, "min_len": 0.006,
                "hw": 0.008, "layer": 1, "edge": False, "min_triangles": 3000, "lit": 0.0, "pass": False, "pass_el": 60.0,
                "pass_back": 0.012, "low_el": None, "low_cards": None, "low_hw": None,
                "rise": 0.0}
# (c11) `rise`: a row card's stations (past its root seat) raised this share of the way out to the SIDE envelope
# (SIDE_ENV_PCT, ENV_UNDER under it), and held under the side envelope instead of the top's ENV_PCT one: the groom's
# temple-to-ear sheet stands off the head (c10L front width 168 px vs 182 at 1 m), the row lay on it
# (c11) `low_el`: the band's strands whose entry (root, or a passing strand's first station in the band) lies under this
# el are clustered on their own (`low_cards` per side at 20k triangles, default `cards`; half width up to `low_hw`,
# default `hw`): c10's passing strands joined the band's 24 clusters a side and the clusters' cards followed the upper
# strands, so the groom's sheet in front of the ear (el ~-30..-10) stayed bare
# (c10) `pass`: also the head strands that PASS THROUGH the band (a station in it, rooted up to `pass_el`): Garrett's
# silver temple sheet is long hair from above lying down over the band, few roots in it. Such a strand's card starts
# `pass_back` m before it enters the band (cut there, not root-seated). `lit` as FLOW_TOP's (own tile group).
# (`edge`: wear the hairline tile (thin, HL_ALPHA-faded roots); False = the body tiles: c9b with edge on drew sparse thin
# strips in front of the ear, the groom's patch there is a solid sheet)


def _azel(P, C):
    v = np.asarray(P, float) - np.asarray(C, float)
    r = np.maximum(np.linalg.norm(v, axis=-1), 1e-9)
    return np.degrees(np.arctan2(v[..., 0], -v[..., 1])), np.degrees(np.arcsin(np.clip(v[..., 2] / r, -1, 1))), r


def _sweep(St: dict, idx, sx: float) -> np.ndarray:
    """-1 / 0 / +1: a strand's first PART_REACH runs to -x / back (or forward) / +x (|x share| >= sx)."""
    Q = St["Q"][idx]
    k = min(Q.shape[1] - 1, max(1, int(round(PART_REACH / STEP))))
    n = np.isfinite(Q[..., 0]).sum(1)
    kk = np.clip(np.minimum(k, n - 1), 0, None)
    d = Q[np.arange(len(idx)), kk].astype(float) - Q[:, 0].astype(float)
    xs = d[:, 0] / np.maximum(np.linalg.norm(d, axis=1), 1e-9)
    return np.where(xs >= sx, 1.0, np.where(xs <= -sx, -1.0, 0.0))


def _card(c, P, la, mem, St, lk, share, prio, **kw) -> dict:
    u = (c["i0"] * STEP + c["s"]) / max(float(np.percentile(St["len"][mem], 95)), 0.02)
    return {"P": P, "X": c["X"], "N": c["N"], "T": c["T"], "bend": c["bend"], "hw": c["hw"], "rad": np.asarray(c["rad"], float),
            "u": u, "s": c["s"], "kind": "baked", "layer": la, "cls": "head", "prio": prio, "cval": 1.0, "value": 1.0,
            "lock": lk["name"], "sn": c["sn"], "strands": mem, "draw": share, "s0": c["i0"] * STEP, "wisp": False,
            "edge": bool(lk.get("at_hairline")), **kw}


def _tier_n(n, triangles):
    return max(2, int(round(float(n) * np.sqrt(max(triangles, 1) / 20000.0))))


def flow_row(St: dict, C, o: dict, la: int, triangles: int, seed: int = 0, locks=None) -> list:
    """FLOW_TOP's cards (see there)."""
    C = np.asarray(C, float)
    _, el, _ = _azel(St["root"], C)
    idx = np.nonzero((St["cls"] == "head") & (el > float(o["el"])))[0]
    if len(idx) < MIN_STRANDS:
        return []
    idx = idx[St["len"][idx] >= np.percentile(St["len"][idx], float(o["len_pct"]))]
    grp = _sweep(St, idx, float(o["sweep_x"]))
    env = envelope(St, C, pct=float(o["pct"]))
    n = _tier_n(o["cards"], triangles)
    out = []
    for gv in np.unique(grp):
        sel = idx[grp == gv]
        if len(sel) < MIN_STRANDS:
            continue
        k_ = max(1, int(round(n * len(sel) / len(idx) * 3)))  # (n per group on an even three-way split)
        lab = kmeans(features(St, sel), k_, seed + 101)
        for g in np.unique(lab):
            mem = sel[lab == g]
            if len(mem) < MIN_STRANDS:
                continue
            c = fit(St["Q"][mem], _cen_of(C, None), end_share=float(o["end"]), max_hw=float(o["hw"]), spread=90.0,
                    reference=True, medoid=1.0)
            if c is None:
                continue
            P = np.asarray(c["P"], float)
            X, hw = np.asarray(c["X"], float), np.asarray(c["hw"], float)
            r = np.linalg.norm(P - C, axis=1)
            tg = []
            for E in (P, P - X * hw[:, None], P + X * hw[:, None]):  # (the card AND its edges on / under the surface)
                e, rE = env(E)
                tg.append(e - (rE - r))
            from scipy.ndimage import gaussian_filter1d
            with np.errstate(invalid="ignore"), __import__("warnings").catch_warnings():
                __import__("warnings").simplefilter("ignore")
                tgt = np.nanmin(np.stack(tg), axis=0) - ENV_UNDER
            ok_ = np.isfinite(tgt)
            if not ok_.any():
                continue
            tgt = gaussian_filter1d(np.interp(np.arange(len(r)), np.flatnonzero(ok_), tgt[ok_]), 1.5)
            w = _ss(np.clip(np.asarray(c["s"]) / max(float(o["seat"]), 1e-6), 0.0, 1.0)) * float(o["reach"])
            rn = r + w * (tgt - r)  # (onto the outer surface past the seat; the root stays seated)
            P = C + (P - C) * (rn / np.maximum(r, 1e-9))[:, None]
            cc_ = {"P": P}
            P = _root_seat(cc_["P"], c["s"], St["root"][mem], C) if ROOT_SEAT > 0 else cc_["P"]
            lk = {"name": f"flow{len(out)}"}
            out.append(_card(c, P, la, mem, St, lk, 1.0, la + 0.9 + 0.05 * (len(out) % 2), flow=True,
                             **({"lit": float(o["lit"])} if float(o["lit"]) > 0 else {})))
    print(f"flow top: {len(out)} cards (groups {dict(zip(*np.unique(grp, return_counts=True)))}, strands {len(idx)}, "
          f"length p50 {np.median([c['s'][-1] for c in out]) * 1000 if out else 0:.0f} mm)", flush=True)
    return out


def tuck_under(cards: list, flow: list, C, tuck: float) -> int:
    """Head cards' stations lying under a flow card (within its half width across, nearer than its station along)
    pulled in toward the head's centre to `tuck` m under it (only ever lowered). Returns stations moved."""
    if not flow or not cards:
        return 0
    from scipy.spatial import cKDTree
    C = np.asarray(C, float)
    FP = np.concatenate([np.asarray(f["P"], float) for f in flow])
    FH = np.concatenate([np.asarray(f["hw"], float) for f in flow])
    FT = np.concatenate([np.gradient(np.asarray(f["P"], float), axis=0) for f in flow])
    FT /= np.maximum(np.linalg.norm(FT, axis=1), 1e-12)[:, None]
    FR = np.linalg.norm(FP - C, axis=1)
    U = (FP - C) / FR[:, None]
    tr = cKDTree(U)
    moved = 0
    for c in cards:
        if c.get("cls") != "head" or c.get("fly"):
            continue
        P = np.asarray(c["P"], float)
        r = np.linalg.norm(P - C, axis=1)
        d, j = tr.query((P - C) / r[:, None])
        # across distance on the flow card's surface: the angular offset at its radius, less the along part
        off = (P - C) / r[:, None] * FR[j][:, None] - (FP[j] - C)
        off -= (off * FT[j]).sum(1)[:, None] * FT[j]
        under = (np.linalg.norm(off, axis=1) < FH[j]) & (r > FR[j] - tuck)
        if under.any():
            from scipy.ndimage import gaussian_filter1d
            dr = gaussian_filter1d(np.where(under, r - (FR[j] - tuck), 0.0), 1.0)
            dr = np.maximum(dr, 0.0)
            c["P"] = C + (P - C) * ((r - dr) / r)[:, None]
            moved += int(under.sum())
    print(f"flow top: {moved} stations of the other head cards tucked under it", flush=True)
    return moved


def hairline_row(St: dict, C, o: dict, env, triangles: int, seed: int = 0, env_side=None) -> list:
    """HAIRLINE_ROW's cards (see there)."""
    C = np.asarray(C, float)
    az, el, _ = _azel(St["root"], C)
    a0, a1 = o["az"]
    e0, e1 = o["el"]
    out = []
    n = _tier_n(o["cards"], triangles)
    for sgn in (-1.0, 1.0):
        idx = np.nonzero((St["cls"] == "head") & (sgn * az >= a0) & (sgn * az <= a1) & (el >= e0) & (el <= e1))[0]
        start, enter = {}, {}
        if o.get("pass"):  # (c10) strands that pass through the band: cut from just before they enter it
            Q_ = St["Q"]
            hd = np.nonzero((St["cls"] == "head") & (el > e1) & (el <= float(o["pass_el"])))[0]
            qa, qe, _ = _azel(Q_[hd], C)
            inb = np.isfinite(Q_[hd][..., 0]) & (sgn * qa >= a0) & (sgn * qa <= a1) & (qe >= e0) & (qe <= e1)
            hit = inb.any(1)
            first = np.argmax(inb, 1)
            back = int(round(float(o["pass_back"]) / STEP))
            for j, f in zip(hd[hit], first[hit]):
                start[int(j)] = max(0, int(f) - back)
                enter[int(j)] = int(f)
            idx = np.r_[idx, hd[hit]]
        if len(idx) < MIN_STRANDS:
            continue
        groups = [(idx, n, float(o["hw"]))]
        if o.get("low_el") is not None:  # (c11) the low band clustered on its own
            ent = np.array([el[j] if int(j) not in enter else float(_azel(St["Q"][j][enter[int(j)]], C)[1])
                            for j in idx])
            lo = ent < float(o["low_el"])
            groups = [(idx[~lo], n, float(o["hw"])),
                      (idx[lo], _tier_n(o.get("low_cards") or o["cards"], triangles), float(o.get("low_hw") or o["hw"]))]
        todo = []
        for gi_, (ix_, n_, hw_) in enumerate(groups):
            if len(ix_) < MIN_STRANDS:
                continue
            lab = kmeans(features(St, ix_), min(n_, max(1, len(ix_) // MIN_STRANDS)), seed + 211 + 7 * gi_)
            todo += [(ix_[lab == g], 0, hw_) for g in np.unique(lab)]
        while todo:
            mem, dep, hw_ = todo.pop(0)
            if len(mem) < MIN_STRANDS:
                continue
            Qm = St["Q"][mem]
            sh = np.array([start.get(int(j), 0) for j in mem])
            if sh.any():  # (passing strands: their stations from the cut on, the rest padded)
                Qm = np.full_like(Qm, np.nan)
                for i_, (j, k_) in enumerate(zip(mem, sh)):
                    Qm[i_, :Qm.shape[1] - k_] = St["Q"][j][k_:]
            c = fit(Qm, _cen_of(C, None), end_share=HEAD_END, max_hw=hw_, spread=90.0,
                    reference=True, min_stations=int(o["min_stations"]), min_len=float(o["min_len"]))
            if c is None:  # (short hairs rooted in a row down their own run: split, as the cut's SPLIT_DEPTH)
                if dep < 3 and len(mem) >= 2 * MIN_STRANDS:
                    sub = kmeans(features(St, mem), 2, seed + 223 + dep)
                    if 0 < int(sub.sum()) < len(sub):
                        todo += [(mem[sub == 0], dep + 1, hw_), (mem[sub == 1], dep + 1, hw_)]
                continue
            la = int(o["layer"])
            yo = layer_offset(c["sn"], la, "head")
            P = c["P"] + c["N"] * yo[:, None]
            rs_ = float(o.get("rise") or 0.0)
            if rs_ > 0 and env_side is not None:  # (c11) out toward the side envelope
                es_, r_ = env_side(P)
                up_ = np.clip(np.nan_to_num(es_ - ENV_UNDER - r_, nan=0.0), 0.0, None) * rs_
                up_ *= np.clip(np.asarray(c["s"], float) / 0.01, 0.0, 1.0)  # (not at the root)
                P = P + _unit(P - C) * up_[:, None]
            cc_ = {"P": P, "X": c["X"], "hw": c["hw"]}
            _under_envelope(cc_, env, C, env_side if rs_ > 0 else None)
            P = _root_seat(cc_["P"], c["s"], St["root"][mem], C) if (ROOT_SEAT > 0 and not sh.any()) else cc_["P"]
            out.append(_card(c, P, la, mem, St, {"name": f"hrow{len(out)}", "at_hairline": bool(o["edge"])}, 1.0, la + 0.05,
                             hrow=True, **({"lit": float(o["lit"])} if float(o["lit"]) > 0 else {})))
    print(f"hairline row: {len(out)} cards", flush=True)
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
    P = np.asarray(c.get("P_fit", c["P"]), float)  # (the arch row's picture: its strands, not the raised line)
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
            if c.get("arch") or c.get("cover"):  # (r34) the arch card covers its strands' first ARCH_LEN only: the share over that
                # (round 35: the part cover's COVER_LEN too)
                # (over the whole strand, IN_SHARE dropped every strand: an empty tile)
                m_ = al <= L
                if not m_.any() or inside[m_].mean() < IN_SHARE:
                    continue
            elif not c.get("fly") and inside.mean() < IN_SHARE:
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
        if c.get("lit"):  # (c10) a flow / hairline-row card on top, in the light: no depth shade, tone x (1 + lit)
            dep = np.ones_like(dep)
            tn2 = np.clip(tn2 * (1.0 + float(c["lit"])), 0, 1)
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
        elif c.get("cover") and COVER_FADE > 0:  # (round 33) the part cover's tips end soft on the side cards
            a = a * (1.0 - _ss(np.clip((yy - (1.0 - COVER_FADE)) / COVER_FADE, 0.0, 1.0)))
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
        cls = "fly" if c.get("fly") else "flow" if c.get("flow") else "hrow" if (c.get("hrow") and c.get("lit")) else str(c.get("cls"))
        if c.get("cover"):  # (round 33) the part cover keeps its own pictures (their tips fade: COVER_FADE)
            return (cls, 2)
        return (cls, 0 if (int(c["layer"]) == 0 and cls in ("head", "tail")) else 1)
    keys = [g(c) for c in cards]
    return keys


def card_grey(cards: list, St: dict, locks: list | None, look: dict) -> np.ndarray | None:
    """Each card's share of grey hairs, the strand look's rule (hair_cap.strand_grey): look.grey_amount + look.grey_locks
    x its strands' locks' grey (mean), or None when the locks carry no grey."""
    if not locks:
        return None
    gk = np.asarray([float((k.get("inputs") or {}).get("Grey", k.get("grey", 0.0)) or 0.0) for k in locks])
    if not (gk > 0).any():
        return None
    lk_ = np.asarray(St["lock"])
    g = np.asarray([float(gk[lk_[np.asarray(c["strands"], int)]].mean()) if len(c["strands"]) else float(gk.mean())
                    for c in cards])
    return np.clip(float(look.get("grey_amount", 0.0)) + float(look.get("grey_locks", 1.0)) * g, 0, 1)


TILE_REP_DRAWN = 0.5  # (c8, Garrett) a tile's picture is its medoid card's own strands that pass bake's IN_SHARE / fly rule:
# a medoid whose strands mostly leave its card (lying temple / sideburn hair crossing it) baked an EMPTY tile and every
# card of the cluster was invisible (c6M: 263 of 1501 cards, 10 % of the card area, 55 at the temples = the bare
# sideburn). The medoid is taken in order of closeness until one draws this share of its strands (the best of
# TILE_REP_TRY otherwise). 0 = off (the plain medoid, before c8)
TILE_REP_TRY = 24


def _drawn_share(c: dict, St: dict) -> float:
    """The share of a card's strands bake() draws on it (IN_SHARE of their points inside the card; fly cards: all)."""
    mem = np.asarray(c["strands"], int)
    if c.get("fly") or not len(mem):
        return 1.0 if len(mem) else 0.0
    hwm, L, n = float(np.max(c["hw"])), float(c["s"][-1]), 0
    for j in mem:
        q = St["Q"][j]
        q = q[np.isfinite(q[:, 0])].astype(float)
        if len(q) < 2:
            continue
        ax, al, _ = _card_coords(c, q, smooth=True)
        n += ((np.abs(ax) <= hwm) & (al >= 0) & (al <= L)).mean() >= IN_SHARE
    return n / len(mem)


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
    drawn_log = []
    cg = card_grey(cards, St, locks, look or {})
    for k in gk:
        idx = np.array([i for i, x in enumerate(keys) if x == k])
        kk = min(kn[k], len(idx))
        F = np.stack([np.log(L[idx]) * 3.0, np.log(Wd[idx])], 1)
        if cg is not None and GREY_TILES > 0:  # (grey shares 0..1: x 6 puts .2 apart about as far as 2x the length)
            F = np.concatenate([F, (6.0 * GREY_TILES * cg[idx])[:, None]], 1)
        lab = kmeans(F, kk, seed=seed) if kk > 1 else np.zeros(len(idx), int)
        for q in np.unique(lab):
            mem = idx[lab == q]
            f = F[lab == q]
            # the medoid among the cards with the most strands (a sparse card's picture would be a sparse tile)
            ns = np.array([len(cards[i]["strands"]) for i in mem])
            ok = ns >= np.percentile(ns, 50)
            d = np.linalg.norm(f - np.median(f, 0), axis=1) + np.where(ok, 0.0, 1e3)
            r = int(mem[int(np.argmin(d))])
            if TILE_REP_DRAWN > 0:  # (c8) the medoid's picture must DRAW: see TILE_REP_DRAWN
                best, bd = r, -1.0
                for i_ in mem[np.argsort(d)][:TILE_REP_TRY]:
                    dr_ = _drawn_share(cards[int(i_)], St)
                    if dr_ > bd:
                        best, bd = int(i_), dr_
                    if dr_ >= TILE_REP_DRAWN:
                        break
                drawn_log.append((_drawn_share(cards[r], St) if best != r else bd, bd, len(mem)))
                r = best
            tile[mem] = len(reps)
            reps.append(r)
    if drawn_log:
        print("tile reps' drawn share (medoid -> chosen, cards): " + ", ".join(f"{a:.2f}->{b:.2f}/{n_}" for a, b, n_ in drawn_log), flush=True)
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
    tf_, tb_ = float((look or {}).get("tone_front", TONE_FRONT)), float((look or {}).get("tone_back", TONE_BACK))
    # (c10: look tone_front / tone_back override the constants per model: Tess's 0.85 front left Garrett's front -3 L*)
    if (tb_ != 1.0 or tf_ != 1.0) and C is not None:  # (round 26) the head's tone by place (front / back)
        R0 = np.asarray(St["root"], float)
        for i, c in enumerate(cards):
            if c.get("cls") != "head" or c.get("fly") or not len(c["strands"]):
                continue
            r_ = R0[np.asarray(c["strands"], int)].mean(0) - np.asarray(C, float)
            w_ = _ss(np.clip((r_[1] - TONE_POS_Y[0]) / (TONE_POS_Y[1] - TONE_POS_Y[0]), 0, 1))
            tint[i] *= tf_ + (tb_ - tf_) * float(w_)
    if GREY_TINT > 0 and locks:  # (c1) a card's tone by its locks' grey (the groom's grey by region: Garrett's sides .65,
        # top .22): the tiles are shared, so a grey region's cards came out the head's one dark tone (g1v1 -16 L* p50)
        gk = np.asarray([float((k.get("inputs") or {}).get("Grey", k.get("grey", 0.0)) or 0.0) for k in locks])
        gc = np.asarray([float(gk[np.asarray(St["lock"])[np.asarray(c["strands"], int)]].mean()) if len(c["strands"])
                         else np.nan for c in cards])
        if np.isfinite(gc).any() and np.nanstd(gc) > 1e-3:
            gm = float(np.nanmedian(gc))
            tint = tint * np.clip(1.0 + GREY_TINT * np.nan_to_num(gc - gm), 0.6, 2.2)
    if cg is not None and GREY_TILES > 0:  # each tile's grey-hair share: the mean of its cards' (by their strands)
        G = np.full(B["alpha"].shape, np.nan, np.float32)
        for q, (x_, y_, w_, h_) in enumerate(B["islands"]):
            G[y_:y_ + h_, x_:x_ + w_] = float(np.mean(cg[tile == q]))
        B["gshare"] = G
        ts_ = np.array([float(np.mean(cg[tile == q])) for q in range(len(B["islands"]))])
        print(f"tile grey share: cards p5/50/95 {np.percentile(cg, [5, 50, 95]).round(2)}, tiles {np.percentile(ts_, [5, 50, 95]).round(2)}"
              f" ({len(ts_)} tiles)", flush=True)
    B["tile_islands"] = B["islands"]
    B["islands"] = [B["tile_islands"][t] for t in tile]
    B["tint"], B["tile"], B["reps"] = tint, tile, reps
    return B
