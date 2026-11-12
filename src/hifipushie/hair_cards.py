"""Hair cards: a lock drawn as layered strips of polygons carrying pictures of strands, the way game hair is made.

`spec["hair"]["style"] = "cards"` turns every lock (hair.py: a spine with a width, a thickness and a shape along it,
still a Bezier curve a person edits in Blender) into a small stack of cards inside the lock's own lens: dense cards
underneath, clumped ones over them, wisps on top, a few fly-aways standing off it. The pictures come from one strand
atlas made here (`atlas`): tiles of strands running root (top) to tip, from an opaque base tile to single stray
hairs, each with colour, alpha, a normal map and an aux map (root gradient, strand id, depth, alpha: what engine hair
shaders ask for). `spec["hair"]["strands"]` holds the numbers (STRANDS): wave, wavelength, curl, random, clump, frizz,
flyaway, layers, card_width...; a lock may carry its own `"strands": {...}` over them.

Everything is numpy: `build` returns the card mesh (positions, per-corner uv, bent normals, tangents along the hair,
a colour per vertex = the root-to-tip ramp x the lock's own value) both for the Blender scene (blender_hair.cards) and
for the export, so what the look shows is what the GLB holds.

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at hair_cards.NAME: C422). hair_cards_atlas: the strand tiles and the atlas: drawn lines, a tile, `atlas`,
remap_v, write_atlas. hair_cards_mesh: cards from locks: the spine, frames, a lock's cards, and `mesh`.
hair_cards_clumps: cards from the strands themselves: the strand grid, a clump, clump_cards, far flyaways, pooled
singles. hair_cards_mass: mass under the cards: tail cores and their mesh, the mass shell, the shadow proxy.
hair_cards_budget: levers and the budget: lever matches, bend rows, segments, triangles, fit_budget, join.
"""
from __future__ import annotations

import numpy as np
from . import moved

STRANDS = {
    "wave": 0.0,  # m: how far a lock swings side to side
    "wavelength": 0.07,  # m along the lock per swing
    "curl": 0.0,  # 0..1: how much of the wave also leaves the lock's plane (1 = a helix: ringlets)
    "random": 0.45,  # 0..1: how far the cards of a lock (and locks) differ in phase, amplitude and length
    "clump": 0.5,  # 0..1: strands in the pictures gather into pointed sub clumps toward the tips
    "frizz": 0.2,  # 0..1: single strands wander in the pictures
    "flyaway": 0.15,  # stray cards per card (single hairs standing off the lock)
    "layers": 2,  # card layers per lock: 1 = dense only (far LODs), 2, 3 (hero)
    "card_width": 0.022,  # m: the widest a card gets
    "segment": 0.012,  # m of card per segment (a triangle budget coarsens it)
    "round": 0.55,  # 0..1: card normals bent toward the hair volume's own (soft, even shading)
    "tips": 0.5,  # 0..1: how ragged the ends are (cards and strands of different lengths)
    "atlas": 1024,  # px across the strand atlas
    "baby": 1.0,  # baby hairs along the hairline: cards per cm x this (0 = none)
    "soft": 0.008,  # m: the hairline fades over this width (the cap's edge breaks up into strands)
    "flow_top": None,  # clumps cut (hair_clumps.FLOW_TOP): true / {options}: a top layer of long cards along the flow (c9)
    "hairline_row": None,  # clumps cut (hair_clumps.HAIRLINE_ROW): true / {options}: short cards along the temple band (c9)
    # --- strand grooms (hair_strands.py: Blender Hair Curves); the cards above are cut from the same groom
    "source": "groom",  # the cards' pictures: "groom" = this groom's own strands (Blender), "drawn" = made up here
    "count": 30000,  # strands in a look (the export's atlas bake and video renders may ask for more)
    "taper": 0.9,  # 0..1: strands thin toward their tips (uncut hair ends in a point; 0 = blunt, freshly cut)
    "thickness": 1.0,  # x the strand's width (a real hair's 0.08 mm at 100k strands; fewer strands are drawn wider: 0.2 mm at 30k)
    "clump_size": 0.007,  # m between the sub clumps strands gather into inside a lock (0.004 fine .. 0.02 chunky)
    "clump_shape": 0.6,  # 0..1: where along a strand the gathering happens (0 = all along: ropes, 1 = only the tips)
    "tip_spread": 0.3,  # 0..1: tips open out of their clump again (a brushed, airy end)
    "loose": 0.3,  # 0..1: strands wander together off the lock's line (0 = combed flat, 1 = unbrushed)
    "stray": 0.5,  # 0..1: how many strands only half join their clump (0 = every clump a tight rope with air between)
    "roots": 0.3,  # 0..1: strands of a lock start at different places along its root (no cut line at a root)
    "under": 1.0,  # x the scalp layer's density (hair rooted all over the scalp under the locks; 0 = none)
    "under_length": 0.04,  # m: how far the scalp layer's hairs run before they are under the locks
    "flat": 1.0,  # x a lock's thickness for its strands (1 = the lock's own lens; 2 = a rounder, fuller lock)
    "free": None,  # {dial: value}: the strand dials of hair that has LEFT the head (a tail, loose lengths) where they
    # differ from the hair on it (a tousled top with a tail of defined wavy locks: loose 0.7 on the head, 0.2 free)
    "wisp": None,  # {dial: value}: the dials of the locks of single hairs (lock["hairs"]: wisps, escaped hairs) over
    # the free hair's (frizz, loose, wave, wavelength, tips, taper, thickness)
    "halo": 0.0,  # 0..1: short broken hairs that stand up off the hair on the head and curl (the fine fuzz round a
    # loose updo against the light); `flyaway` strands only drift a few mm off their own lock and end where it ends
    "even": 0.0,  # 0..1: the share of strands grown from ONE EVEN sampling of the hair-bearing scalp, shaped by the
    # nearest lock guides (locks only steer: a part / sweep / whorl is the comb, never a gap between locks; hair-heads);
    # 1 = every strand (the locks are dense guides only)
    "even_guides": 0,  # guides a child of the even layer takes its shape from (0 = auto: 1 at even 1, else 3). One: at
    # a split in the comb (a part, a tuck behind the ear) children averaging both sides took the middle path
    "wave_from": 0.0,  # m along a lock where its waves start (long hair straight on top, wavy below the ear: ~0.10-0.14);
    # 0 = from the first 3 cm
    "halo_soft": 0.0,  # 0..1: the halo DENSE AND SOFT (rule 4, hair-garrett3): many more halo hairs, shorter and closer
    # to the hair (a fuzz a few mm deep along the silhouette, not a few single hairs standing off); pair with a low
    # look.fine_alpha (0.2-0.3) so each reads faint
}
# (kind, px wide at a 1024 atlas): what the cards choose from. Two of each so neighbours differ.
TILES = [("dense", 136), ("dense", 136), ("medium", 136), ("medium", 136), ("sparse", 104), ("sparse", 104),
         ("hairline", 144), ("fly", 64), ("baby", 48), ("band", 16)]
KIND = {  # n strands per 160 px, sub clumps, how hard they gather, strand length range, px thick, opaque base share
    "dense": {"n": 260, "clumps": 6, "cl": 0.3, "len": (0.8, 1.0), "thick": 1.5, "base": 0.62},
    "medium": {"n": 120, "clumps": 4, "cl": 0.7, "len": (0.6, 1.0), "thick": 1.4, "base": 0.0},
    "sparse": {"n": 44, "clumps": 3, "cl": 0.85, "len": (0.45, 1.0), "thick": 1.2, "base": 0.0},
    "fly": {"n": 14, "clumps": 0, "cl": 0.0, "len": (0.5, 1.0), "thick": 1.0, "base": 0.0, "wander": 3.0},
    "baby": {"n": 150, "clumps": 0, "cl": 0.0, "len": (0.2, 0.75), "thick": 1.3, "base": 0.0, "wander": 2.5},
    # the hair's edge on the skin: strands that start one by one over the first third (thin at the line, a full
    # head of hair behind it), then opaque like a dense tile
    "hairline": {"n": 330, "clumps": 6, "cl": 0.25, "len": (0.85, 1.0), "thick": 1.4, "base": 0.62, "start": 0.34},
    "band": {},  # a plain opaque tile in the look's `band` colour: the tie
}
_ATLAS: dict = {}


def strands_of(spec: dict) -> dict:
    h = spec.get("hair") or {}
    s = h.get("strands") or {}
    bad = set(s) - set(STRANDS)
    if bad:
        raise ValueError(f"hair strands: unknown keys {sorted(bad)} (have {', '.join(sorted(STRANDS))})")
    tied = (h.get("groom") or {}).get("tied")
    if tied is not None:  # a tied style brings its own strand dials (neatness: strays, halo, frizz); the spec's own win
        from . import hair_flow_style
        st = hair_flow_style.style(tied)["strands"]
        s = {**st, **s, **({"free": {**(st.get("free") or {}), **(s.get("free") or {})}} if (st.get("free") or s.get("free")) else {}),
             **({"wisp": {**(st.get("wisp") or {}), **(s.get("wisp") or {})}} if (st.get("wisp") or s.get("wisp")) else {})}
    out = {**STRANDS, **s}
    for k_ in ("free", "wisp"):
        if out.get(k_):
            bad = set(out[k_]) - set(STRANDS)
            if bad:
                raise ValueError(f"hair strands.{k_}: unknown keys {sorted(bad)}")
    if out["source"] not in ("groom", "drawn"):
        raise ValueError('hair strands: source is "groom" or "drawn"')
    return out


def _ss(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def _unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def _lin(hexc: str):
    c = hexc.lstrip("#")
    v = np.array([int(c[i:i + 2], 16) / 255 for i in (0, 2, 4)])
    return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)


def _srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, 12.92 * c, 1.055 * np.power(c, 1 / 2.4) - 0.055)


SHORT_TILE = {"medium": (56, 2.2), "sparse": (34, 2.0), "baby": (9, 3.0), "fly": (5, 4.0)}  # strands per 272 px, px thick
FLY_HAIR = 0.07  # share of the fly tile's width one of its hairs is drawn: ~0.35 mm on a 5 mm wisp card, about a pixel at a
# hero's close-up (Tess's W18 face wisps: drawn 3 texels of 128 = 0.12 mm they fell under the alpha cutoff and vanished,
# where EEVEE draws every strand at least a pixel wide)
EDGE_SOLID = 0.5  # texels under this alpha take the colour / depth of the nearest texel over it (edge padding): at
# 0.03 the anti-aliased rim of every strand kept its own low depth = a dark outline round each strand and card (Godot)
SHORT_DEPTH = 0.45  # a short cut's card strands: the least of the depth shade (they lie over the cap, which is the shade)

GREY_QUANTILE = 1  # (c3) a tile's grey share is drawn as that share of its strand pixels (quantile of their ids)
HUE_CLIP = 0.0  # (round 41, opt-in) 1 = over-range atlas texels scaled down by their max channel (hue kept); 0 = per-channel clip
GREY_LIFT = 1.0  # (c5) the cards' grey hairs' colour x this (the strand look's grey #6a6764 x (0.6 + 0.4 shade) drew
# mid-grey hairs; the groom's grey strands read silver under the hair BSDF's highlight: 3/4 sides 39.5 L* vs the groom's 50)
GREY_SPREAD = 2.0  # (c4) shared tiles' grey shares x this about their median (1 = as baked, before c4)
GREY_DEP0, GREY_DEPW = 0.32, 0.2  # (c3) shared tiles' grey hairs: only strands deeper than this (ramp width) may be grey
# (the opaque base under the strands sits at ~0.3 depth: the shadow between hairs, never grey)

TAIL_AXIS_N = 1.0  # (round 43 default: blind A/B r42c vs r41c NEW 2 / SAME 2, the back's black blotch gone; round 42 opt-in) tied-tail (hanging, not wisp / fly) card vertex normals turned this share toward
# outward from the tail's own axis (horizontal, per 1 cm height band of the tail's vertices). With ONE normal for both faces
# (the shading contract), r41c's tail from behind showed a black patch at its right edge (a front-side card seen past the
# edge, normal away from eye and light; flat pass clean, shadow=0 still black) and dark tips; 35.7 % of tail verts faced INTO
# the tail axis (t42/tailn.py)
WIND_TO_NORMAL = 1  # (c4) every card triangle wound to face along its vertex normals (0 = as built, before c4)

# ------------------------------------------------------------------------------------------ cards from the strands
GRID = 40  # stations along a lock at which its strands are compared
FINE_SPARSE = 0.5  # a lock whose strands are drawn at least this fine (strands.fine: see-through) is cut on the sparse tile
TAIL_ROOT_HW = 0.0  # (round 31; opt-in, try 0.008: r31a root corners past LOD0 fewer, but the spikes over the tie at 3/4 unchanged and the band showed more at g2backl) m: a tied tail's card half width at its root (the tie), eased to full over
TAIL_ROOT_TAPER = 0.05  # m along it (0 = off)
TAIL_SPLIT_CW = 0.0  # (round 32; opt-in) a hanging (free, not wisp) clump at a coarse tier (card_width > TAIL_SPLIT_MIN) is cut
# into slices no wider than this many card widths ACROSS ITS OUTLINE (FREE_SPREAD sigmas: the split counted 1.7 sigma, so
# a far-tier tail card came out 132-200 mm wide, and its flat corners stood off the round tail as the LOD1-3 spikes
# over the tie, round 31 tiespk2); 0 = off
TAIL_SPLIT_MIN = 0.05  # m: only tiers whose card width is over this (the far tier: main / npc tail cards are capped at ~73 mm
# by FREE_CLIP already and the split only added cards standing off, t32/tw_s1.txt)
FREE_SPREAD, FREE_CLIP = 3.2, 1.3  # hanging cards' half width in the clump's sigmas, and its cap in card widths
FREE_END = 0.06  # hanging hair's cards run on until only this share of their strands is left (at 0.3 Tess's tail ended ~5 cm short)

PCA_FRAME = 1.0  # (0 before round 22) hanging (tail / face) cards: share of the turn toward the clump's flat cross-section (0 = off, the
# outward frame only, before round 22)
PCA_MAX = 60.0  # deg (round 23; 90 = unlimited, round 22): the PCA turn is held to this angle from the outward frame. A card turned
# past ~60 deg is seen from its BACK from outside the tail, and a double-sided card's back is shaded with the flipped
# (inward) normal: b30's dark leaf-shaped shards between the tail cards near the tie (lit only; flat albedo and shadow=0
# both still had them; round 23)

FLY_FAR_TIERS = True  # (round 30) the hero's FLY_FAR at every tier: fly cards (pooled halo hairs, few-hair wisps) standing
# further than hair_clumps.FLY_FAR off the rest of the hair get no card. Without it LOD1-3 had thin spikes standing
# sideways off the tail by the tie, 35-80 mm past LOD0's hair (round 29's standoff / t30/tiespk.py)

EDGE_ROUND = 0.0  # share of a card's across-curvature given to its edge normals (mesh; 0 = one normal across). b20 at
# 1.0: lock band 6.25 -> 6.38 front, 6.16 -> 6.23 3/4, nape wedge L* 7.6 -> 7.5, tail still "flat": no gain, off
HIGHLIGHT_W = 0.008  # m: cards wider than this carry no highlight of their own (a ribbon is a few mm)
SINGLES_PER_CARD = 8  # single-hair locks (a halo, escaped hairs) pooled onto one fly card: a card of the fly tile pictures
# a few hairs; 420 halo hairs cut as 3 cards each (Tess's W18) were 7k triangles, all of them cut by any game budget

CORE_SHARE = 0.5  # a tail core runs while this share of its strands still run (b22: it ends inside the cards; 0.2 before: its square end showed mid-tail)
CORE_TAPER = 0.25  # share of the core's length over which its radius closes to a point (b22; 0 = square cut, before)

MASS_CELL = 0.007  # m: the voxel the hair's density is counted on

BEND_ROWS = 0.0  # (round 45; opt-in) deg: a card gets at least one segment per this much turning of its path / its
# across axis (0 = off: segments by length alone). Under a far tier's 5-7.5 cm segments a tail card that turns ~90 deg
# at the tie was cut into 2-3 straight panels: the crumpled, faceted LOD3 tail (t43 / t45 lod3 sheets)
# (round 46: on EVERY card with the across axis counted, r46a's LOD3 face cards cost 332 -> 1208 tris and the tail kept 20
# of 195 cards, a small dark cone: hence the class filter, the path-only turning and the extra-segment cap)
BEND_CLS = ("tail",)  # classes BEND_ROWS applies to (empty = all)
BEND_PATH = True  # turning of the path tangent only (the across axis' twist left out)
BEND_MAX = 2  # at most this many segments over the length rule (0 = no cap)
# (round 47) r46g's tail-only BEND_ROWS matched ZERO cards for a whole round: the LOD1-3 tiers cut cards with
# clump_cards, which set no "cls" (hair.cards_job now stamps it from the lock), and nothing said the filter was empty.
# Every card-selecting lever reports its count through lever_matched; a lever switched ON that selects 0 of a non-empty
# population raises (STRICT_LEVERS) instead of silently building r45a again.
STRICT_LEVERS = True
LEVER_MATCHES: dict = {}  # lever name -> [(matched, population), ...] of the run (the export report / tests read it)

FIT_FLOOR: dict = {}  # (round 40) {card cls: share}: that share of a class's cards (its own prio order) is kept before
# any other card under a budget (S["fit_floor"] per groom / tier); {} = off (the drop order is prio alone)

# ------------------------------------------------------------------------------------------------ shadow proxy
SHADOW_PROXY = {"voxel": 0.004, "close": 4, "inset": 0.004, "smooth": 1.2, "step": 2}  # (round 19: the cards' own
# shadow was a dithered shadow map over many transparent sheets: grain on the skin (std 0.42 vs the groom's 0.31) and
# -4.5 L*. Engines give card hair a separate opaque, smooth caster: shading.py hair_cards "shadows")


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("hair_cards_atlas", "hair_cards_mesh", "hair_cards_clumps", "hair_cards_mass", "hair_cards_budget")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C427)
