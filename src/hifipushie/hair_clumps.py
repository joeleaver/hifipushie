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

Where the code is (split by responsibility, C423): this module holds EVERY constant of the family (set at
hair_clumps.NAME by export scripts and hair_cards_job; the other modules read hair_clumps.NAME) and strands, features,
kmeans. hair_clumps_fit: a card fitted to a clump, the envelope, seating and offsets. hair_clumps_part: the part, its
cover, the arch row. hair_clumps_cut: `cut`, the flow and hairline rows. hair_clumps_layout: the atlas layout.
hair_clumps_bake: `bake`, `bake_tiles`.
"""
from __future__ import annotations

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
FACE_CONTRAST = 0.0  # (round 41, opt-in) face-framing cards' hair tone spread about their median x this (0 = off)
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
FLY_FRONT = 0.0  # (round 44, opt-in) m: single hairs rooted this far IN FRONT of the head's centre (y) are exempt from
# FLY_CROWN and from FLY_FAR up to FLY_FRONT_FAR, and get their cards first: the groom's fly-hair tuft standing over the
# forehead (what crowntop's RAGGED front column saw, round 43; the reviewer's "no flyaway outline"). 0 = off
FLY_FRONT_FAR = 0.04  # m
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
TAIL_LONG = 0.2  # (round 44; default after blind A/B r44d vs r44a NEW 3 / OLD 1; 0 = off) share of tail clumps that also get a LONG card: fitted on the clump's longest
# TAIL_LONG_TOP of strands and run to their longest tip (end share 0), so staggered narrow clumps hang below the mass as
# in the groom (Tess's tail ended in one blunt horizontal cut; TAIL_END_JIT / tip fades only SHORTEN cards, t43). 0 = off
TAIL_LONG_TOP = 0.5  # (0.3 in r44b: thin, grey long cards, A/B lost at 3/4) share of the clump's strands (by length) the long card is fitted on
TAIL_LONG_MIN = 4  # strands at least
NAPE_LIFT = 0.8  # (0.6 in b23-b25: wedge 29.8 vs the groom 33.5 once only tail L1 kept the lift) head cards rooted low at the back (the nape, under a tie) tinted x (1 + this): their strands lie
# deep under the gathered hair, so their tint (strands' tone with the depth shade) drew a dark serrated block behind
# the ear in the FLAT pass (b22 nape blob L* 19.7 vs the groom's 33.5, wedge.py g1backl); 0 = off (before b23)
NAPE_SHORT = 0.0  # (round 42, opt-in) m: cards shorter than this in the nape band take NAPE_LIFT whatever their class / layer
# (r41c g1v2: the dark tick marks behind the ear are 18-23 mm cards at the nape hairline, vertex colour .35-.40 vs the tail's .65)
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

HEAD_LIFT = 0.0  # m (c12): every head layer moved out along its normal by this (still under the envelope, the root
# seated by ROOT_SEAT). The head cards' outer surface sat 3-4 mm (p90) under the groom's in every region (c12 vol.py:
# temple p90 5.9 vs 9.7 mm), and HEAD_SN_MAX was a dead lever there (clump spreads under its 3 mm cap: c12v1 = c11L)

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

PART_FROM_STRANDS = 1.0  # round 18: the part is read from the strands themselves (strand_part; a tied groom's part is
# emergent: hair_flow combs the top strands left / right of a line), the spec's line only where they show none; 0 = off
# (b25: the cards split at the default line 3 cm off centre, part dip 2.5 at col 285 vs the groom's 3.5 at 245)
PART_REACH = 0.03  # m along a strand from its root over which its sideways sweep is read
PART_EL = 35.0  # deg over the head's centre: only roots above this decide a side (on the sides every strand runs down)
PART_SIDEWAYS = 0.35  # a root decides a side only if its sweep's x share is at least this


PART_ROOT_REACH = 0.03  # m: a head card rooted within this of the part starts at the part (PART_GAP off it) and leaves
# it sideways, then turns into its own line (round 19: the cards' roots sat 1-2 cm off the line, the cap between them,
# so the part read as no part: part dip 1.1 vs the groom's 3.5); 0 = off

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

_HOOKS: list = []

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

TILE_REP_DRAWN = 0.5  # (c8, Garrett) a tile's picture is its medoid card's own strands that pass bake's IN_SHARE / fly rule:
# a medoid whose strands mostly leave its card (lying temple / sideburn hair crossing it) baked an EMPTY tile and every
# card of the cluster was invisible (c6M: 263 of 1501 cards, 10 % of the card area, 55 at the temples = the bare
# sideburn). The medoid is taken in order of closeness until one draws this share of its strands (the best of
# TILE_REP_TRY otherwise). 0 = off (the plain medoid, before c8)
TILE_REP_TRY = 24


# The modules this one was split into (C423). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("hair_clumps_fit", "hair_clumps_part", "hair_clumps_cut", "hair_clumps_layout", "hair_clumps_bake")
