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
"""

from __future__ import annotations

import hashlib
import json

import numpy as np

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
        from . import hair_flow
        st = hair_flow.style(tied)["strands"]
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


# ------------------------------------------------------------------------------------------------ the strand atlas

def _drawn_lines(kind: str, w: int, S: dict, rng) -> list:
    """Strands made up for a tile: [(x across 0..1, v along 0..1, depth 0..1, id 0..1), ...]."""
    k = KIND[kind]
    n = max(3, int(k["n"] * w / 160))
    m = 0.06
    x0 = rng.uniform(m, 1 - m, n)
    nc = k["clumps"]
    if nc:
        cen = (np.arange(nc) + rng.uniform(0.25, 0.75, nc)) / nc * (1 - 2 * m) + m
        cid = np.argmin(np.abs(x0[:, None] - cen[None]), 1)
        xt = cen[cid] + rng.normal(0, 0.012, n)
        clen = rng.uniform(1 - 0.3 * S["tips"], 1.0, nc)[cid]
        cdep = rng.uniform(0, 1, nc)[cid]
        cph = rng.uniform(0, 1, nc)[cid]
    else:
        xt, clen, cdep, cph = x0, np.ones(n), rng.uniform(0, 1, n), rng.uniform(0, 1, n)
    cl = min(0.97, k["cl"] * (0.4 + 1.2 * S["clump"]))
    lo, hi = k["len"]
    L = rng.uniform(1 - (1 - lo) * (0.4 + 1.2 * S["tips"]), hi, n).clip(0.1, 1.0) * clen
    depth = 0.55 * rng.uniform(0, 1, n) + 0.45 * cdep
    ident = rng.uniform(0, 1, n)
    fz = S["frizz"] * k.get("wander", 1.0)
    tw, fw = 0.006 + 0.035 * S["curl"], 2.0 + 4.0 * S["curl"]
    ph = rng.uniform(0, 1, (n, 2))
    t = np.linspace(0, 1, 44)
    v0 = rng.uniform(0, 1, n) ** 1.6 * float(k.get("start", 0.0))  # where each strand's root is
    out = []
    for i in range(n):
        v = v0[i] + t * (L[i] - v0[i])
        x = x0[i] + (xt[i] - x0[i]) * cl * _ss(v / 0.75)
        env = _ss(v / 0.12)
        x = x + fz * 0.03 * (np.sin(2 * np.pi * (1.3 * v + ph[i, 0])) + 0.6 * np.sin(2 * np.pi * (3.1 * v + ph[i, 1]))) * env
        x = x + tw * np.sin(2 * np.pi * (v * fw + cph[i])) * env
        out.append((x, v, float(depth[i]), float(ident[i])))
    return out


SHORT_TILE = {"medium": (56, 2.2), "sparse": (34, 2.0), "baby": (9, 3.0), "fly": (5, 4.0)}  # strands per 272 px, px thick
FLY_HAIR = 0.07  # share of the fly tile's width one of its hairs is drawn: ~0.35 mm on a 5 mm wisp card, about a pixel at a
# hero's close-up (Tess's W18 face wisps: drawn 3 texels of 128 = 0.12 mm they fell under the alpha cutoff and vanished,
# where EEVEE draws every strand at least a pixel wide)
EDGE_SOLID = 0.5  # texels under this alpha take the colour / depth of the nearest texel over it (edge padding): at
# 0.03 the anti-aliased rim of every strand kept its own low depth = a dark outline round each strand and card (Godot)
SHORT_DEPTH = 0.45  # a short cut's card strands: the least of the depth shade (they lie over the cap, which is the shade)


def _tile(kind: str, w: int, H: int, S: dict, rng, ss: int = 3, lines: list | None = None, short: bool = False) -> dict:
    """One tile: strands drawn root (row 0) to tip, lower ones first. alpha, id (a value per strand), depth (0 deep ..
    1 on top), all (H, w) floats."""
    from PIL import Image, ImageDraw
    from scipy import ndimage
    if kind == "band":
        one = np.ones((H, w), np.float32)
        return {"alpha": one, "id": one * 0.5, "depth": one, "band": True}
    k = KIND[kind]
    W2, H2 = w * ss, H * ss
    ims = [Image.new("L", (W2, H2), 0) for _ in range(3)]
    da, di, dd = (ImageDraw.Draw(i) for i in ims)
    # fly: the tile of wisps and stray hairs, a few separate hairs drawn THICK (a wisp card is ~6 mm across 64 px:
    # at 3 texels a hair is 0.3 mm, a few hairs lying together, and still there after an alpha test at arm's length;
    # at one texel the whole wisp fell under the cutoff and vanished) from a root that starts at full strength (it
    # comes out of the hair, its root buried there: faded in, the wisp seemed to start on bare skin lower down)
    thick = (max(3.0 * ss, FLY_HAIR * w * ss) if kind == "fly" else max(k["thick"] * ss * w / 160, 1.15 * ss)) if kind in ("fly", "baby") else k["thick"] * ss
    if lines is None:  # drawn strands (no groom at hand); else `lines` = real strands of the groom's own clumps
        lines = _drawn_lines(kind, w, S, rng)
    if short and kind in SHORT_TILE:  # a short cut's card is ~1 cm wide and seen 3-4 mips down: a few strands, each
        # several texels thick (0.3-0.5 mm on the card), survive the minification as strands; a hundred 1-texel ones
        # average to a grey film that an alpha test turns into a solid flake or into sparkle
        n_, th_ = SHORT_TILE[kind]
        n_ = max(2, int(round(n_ * w / 272)))
        lines = [lines[i] for i in np.linspace(0, len(lines) - 1, min(n_, len(lines))).astype(int)]
        # (a tile's strands run 16 cm; a short cut's card is 2-3 cm of it: their waves, squeezed five times along,
        # were white squiggles over the cap. Straightened: each keeps a third of its wander)
        lines = [(float(np.mean(x_)) + 0.12 * (np.asarray(x_, float) - float(np.mean(x_))), v_, d_, i_) for x_, v_, d_, i_ in lines]
        thick = th_ * ss * w / 272
    for x, v, dp, idn in sorted(lines, key=lambda q: q[2]):
        x = np.clip(np.asarray(x, float), *((0.12, 0.88) if kind in ("fly", "baby") else (0.025, 0.975)))
        pts = list(zip((x * W2).tolist(), (np.asarray(v, float) * H2).tolist()))
        if len(pts) < 2:
            continue
        cut = int(len(pts) * 0.82)
        for seg, wd in ((pts[:cut + 1], max(1, int(round(thick)))), (pts[cut:], max(1, int(round(thick * 0.5))))):
            if len(seg) < 2:
                continue
            da.line(seg, fill=255, width=wd)
            di.line(seg, fill=int(1 + 254 * idn), width=wd)
            dd.line(seg, fill=int(1 + 254 * dp), width=wd)
    a, idm, dep = (np.asarray(i.resize((w, H), Image.BOX), np.float32) / 255 for i in ims)
    cov = np.maximum(a, 1e-3)
    idm, dep = np.clip(idm / cov, 0, 1), np.clip(dep / cov, 0, 1)
    if kind in ("fly", "baby"):  # single hairs in the open are lit, not deep in a clump: no depth shade
        dep = 0.8 + 0.2 * dep
    elif short and kind in SHORT_TILE:  # a few hairs over the cap: lit (the cap under them is the shade)
        dep = SHORT_DEPTH + (1 - SHORT_DEPTH) * dep
    if kind in ("fly", "baby"):  # nothing touches the quad's border: a card's rectangle must never show
        xx = (np.arange(w) + 0.5) / w
        vv_ = (np.arange(H)[:, None] + 0.5) / H
        a = a * (_ss(xx / 0.1) * _ss((1 - xx) / 0.1))[None] * _ss((1 - vv_) / 0.08)
    if k["base"] > 0:  # an opaque base under the strands, its end ragged per column: the cards that hide the scalp
        col = ndimage.gaussian_filter1d(rng.uniform(0, 1, w), 1.5, mode="wrap")
        col = (col - col.min()) / max(float(np.ptp(col)), 1e-9)
        vv = (np.arange(H)[:, None] + 0.5) / H
        floor = 1 - _ss((vv - (k["base"] - 0.2 + 0.3 * col[None])) / 0.2)
        if k.get("start"):  # no base at the line itself: it comes in behind the first roots
            floor = floor * _ss((vv - k["start"] * (0.75 + 0.5 * col[None])) / 0.14)
        streak = np.repeat(ndimage.gaussian_filter1d(rng.uniform(0, 1, w), 0.7, mode="wrap")[None], H, 0)
        under = a < floor
        idm = np.where(under, a * idm + (1 - a) * streak, idm)
        dep = np.where(under, a * dep + (1 - a) * 0.3, dep)
        a = np.maximum(a, floor)
    solid = a > EDGE_SOLID
    if solid.any():  # values carried past the alpha's edge and over its anti-aliased rim (no dark fringe under filtering)
        ix = ndimage.distance_transform_edt(~solid, return_distances=False, return_indices=True)
        idm, dep = idm[ix[0], ix[1]], dep[ix[0], ix[1]]
    return {"alpha": a, "id": idm, "depth": dep}


def atlas(S: dict, look: dict, lines: dict | None = None, cap: dict | None = None, key: str = "",
          bake: dict | None = None) -> dict:
    """The strand atlas: {"color" (H, W, 4) sRGB floats, straight alpha; "normal" (H, W, 3); "aux" (H, W, 4): root
    gradient, strand id, depth, alpha; "tiles": [{"kind", "u0", "u1"}] (v runs the whole height: 0 = the root, at the
    top of the picture)}. Colour = the look's gap colour deep down to its lit colour on top, a value per strand.
    `bake` (hair_clumps.bake: cards' own strands, a block as wide as the tiles + chart): stacked UNDER the tiles; the
    tiles' rows are then the top `rows` of `rows_total` (every tile / chart uv's v is remapped: remap_v)."""
    key = hashlib.sha1(json.dumps([{k: S.get(k) for k in ("clump", "frizz", "curl", "tips", "atlas", "short")},
                                   {k: look.get(k) for k in ("gap", "lit", "vary", "band", "card_band", "card_gain", "card_sat", "grey", "grey_share", "card_grey", "grey_locks", "grey_amount", "sun", "highlights", "highlight_contrast", "variation")}, key, sorted(SHORT_TILE.items()), SHORT_DEPTH, EDGE_SOLID, (bake or {}).get("key")], sort_keys=True).encode()).hexdigest()
    if key in _ATLAS:
        return _ATLAS[key]
    from scipy import ndimage
    size = int(S["atlas"])
    H = size
    rng = np.random.default_rng(11)
    cols, tiles, x = [], [], 0
    for kind, w0 in TILES:
        w = int(round(w0 * size / 1024))
        cols.append(_tile(kind, w, H, S, rng, lines=(lines or {}).get(len(cols)), short=bool(S.get("short"))))
        tiles.append({"kind": kind, "u0": (x + 2.0) / size, "u1": (x + w - 2.0) / size})
        x += w
    if cap is not None:  # the scalp's own chart beside the tiles (hair_strands.cap_chart): the atlas is 2 : 1
        from PIL import Image
        rs = lambda m: np.asarray(Image.fromarray((np.clip(m, 0, 1) * 255).astype(np.uint8)).resize(  # noqa: E731
            (size, H), Image.BILINEAR), np.float32) / 255
        cols.append({k: rs(cap[k]) for k in ("alpha", "id", "depth")})
        cap_x0 = sum(c["alpha"].shape[1] for c in cols[:-1])
        for t_ in tiles:
            t_["u0"], t_["u1"] = t_["u0"] / 2, t_["u1"] / 2
        tiles.append({"kind": "cap", "u0": 0.5, "u1": 1.0})
    a, idm, dep = (np.concatenate([c[k] for c in cols], 1) for k in ("alpha", "id", "depth"))
    Ht = H  # the tiles' rows (a bake block goes under them)
    bake_k = 1.0
    if bake is not None:
        if bake["alpha"].shape[1] != a.shape[1]:
            raise ValueError("hair atlas: the bake block must be as wide as the tiles")
        a, idm, dep = (np.concatenate([m, bake[k].astype(np.float32)], 0) for m, k in ((a, "alpha"), (idm, "id"), (dep, "depth")))
    gap, lit = _lin(look.get("gap", "#221310")), _lin(look.get("lit", "#56352d"))
    shade = (0.45 + 0.55 * dep ** 0.8)[..., None]
    # a value per strand: what makes a card read as hairs, not a painted sheet (strands: +-vary and more)
    val = (1 + float(look.get("vary", 0.25)) * 3.0 * (idm - 0.5))[..., None]
    hl_ = float(look.get("highlights") or 0.0)
    if hl_ > 0 and not S.get("short"):  # highlight RIBBONS as strands of the tiles (a share of the ids, lighter): a
        # card is 10-48 mm wide, a highlight a few mm; lit per card the tail was a patchwork of pale blocks
        hs_ = np.clip((idm - (1.0 - 0.22 * hl_)) / 0.03, 0.0, 1.0) * np.clip((dep - 0.32) / 0.2, 0.0, 1.0)
        xk_ = 0  # (not on the fly / baby tiles: of their 14 hairs two lit ones made a wisp card a silver-grey strip)
        for (kind_, _w), c_ in zip(TILES, cols):
            w_ = c_["alpha"].shape[1]
            if kind_ in ("fly", "baby"):
                hs_[:Ht, xk_:xk_ + w_] = 0.0
            xk_ += w_
        if bake is not None:  # (the baked strands carry their own ribbons in their tone)
            hs_[Ht:] = 0.0
        val = val * (1 + float(look.get("highlight_contrast", 0.6)) * hs_)[..., None]
    if bake is not None and bake.get("tone") is not None:  # the baked strands' own tone (hair_clumps.strand_tones,
        # / peak: the cards' vertex colours then carry only the root ramp)
        from . import hair_colour as hcol
        # (normalised by their mean: the atlas's 8 bits clip over 1, and at tone x peak the highlights went white-grey;
        # the cards' vertex colours carry the mean back: mesh(), card["tone_k"])
        from .hair_clumps import TONE_HEAD
        tb_ = bake["tone"].astype(np.float32) * hcol.peak(look) * TONE_HEAD
        bake_k = float(np.mean(tb_[bake["alpha"] > 0.5])) if (bake["alpha"] > 0.5).any() else 1.0
        val[Ht:] = (tb_ / max(bake_k, 1e-3))[..., None]
    gain = float(look.get("card_gain", 1.0))  # measured against the strand look (hair.match_cards)
    if S.get("colour_model", True) and not S.get("short"):  # (the cards' vertex colours carry tone / peak: mesh())
        from . import hair_colour as hcol
        gain = gain * hcol.peak(look)
    base = gap[None, None] * (1 - shade) + lit[None, None] * shade
    gs = float(look.get("grey_share") or 0.0) * (float(look.get("card_grey", 0.5)) if S.get("short") else 1.0)  # grey hairs: that share of the strands (by their id) in the grey colour
    if gs > 0:  # (the strand look's own rule: look.grey_amount + the locks' grey x look.grey_locks; cards_job sets it)
        grey = _lin(look.get("grey", "#9a948d"))
        # (the strands with the highest ids: a threshold on the id stays a strand's own through the picture's
        # anti-aliasing, and the opaque base under the strands (id 0) stays dark; a hash of the id speckled every
        # blended pixel and turned the cap's bare base grey)
        isg = (np.clip((idm - (1.0 - gs)) / 0.04, 0.0, 1.0) * np.clip((dep - 0.32) / 0.2, 0.0, 1.0))[..., None]  # (the
        # base under the strands sits at depth 0.3: it is the shadow between hairs, never grey)
        if cap is not None and cap.get("grey") is not None:  # a baked chart knows which of its strands are grey
            isg[:Ht, cap_x0:cap_x0 + size, 0] = rs(cap["grey"])  # (per region: the locks' own shares)
        base = base * (1 - isg) + grey[None, None] * (0.6 + 0.4 * shade) * isg
    lin = base * val * gain
    cs = float(look.get("card_sat", 1.0))  # x the colour's saturation (cards measured against the strand look)
    if cs != 1.0:
        yl = (lin @ np.array([0.2126, 0.7152, 0.0722]))[..., None]
        lin = yl + (lin - yl) * cs
    col = _srgb(np.clip(lin, 0, 1))
    x = 0
    # the tie: under strands the hair gathered into it hides the band; cards run INTO it and the look's band colour
    # (a dark elastic) showed as a black hole (Tess, review c2). It wears the hair's own median colour unless the
    # look names `card_band`
    hair_ = col[(a > 0.5)] if (a > 0.5).any() else None
    band_ = (np.array([int(look["card_band"].lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]) if look.get("card_band")
             else (np.median(hair_, 0) * 0.8 if hair_ is not None else
                   np.array([int(look.get("band", "#23252b").lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)])))
    for c in cols:  # the tie's own colour
        w = c["alpha"].shape[1]
        if c.get("band"):
            col[:Ht, x:x + w] = band_
        x += w
    hgt = ndimage.gaussian_filter(dep * (a > 0.1), 0.8)
    gx, gy = np.gradient(hgt, axis=1) * 2.2, np.gradient(hgt, axis=0) * 0.6
    nrm = _unit(np.stack([-gx, gy, np.ones_like(gx)], -1)) * 0.5 + 0.5
    # flow: the hair's direction in tangent space (east, up) + strength: a card's strands run down its picture; a
    # baked chart brings its own directions and its normals from the strands' heights
    flow = np.zeros(a.shape + (3,), np.float32)
    flow[..., 1], flow[..., 2] = 1.0, 1.0
    if cap is not None and cap.get("normal") is not None:
        rs3 = lambda m: np.stack([rs(m[..., i] * 0.5 + 0.5) * 2 - 1 for i in range(3)], -1)  # noqa: E731
        nrm[:Ht, cap_x0:cap_x0 + size] = _unit(rs3(cap["normal"])) * 0.5 + 0.5
        fl = rs3(np.concatenate([cap["flow"][..., :2], cap["flow"][..., 2:3] * 2 - 1], -1))
        flow[:Ht, cap_x0:cap_x0 + size, :2] = _unit(fl[..., :2])
        flow[:Ht, cap_x0:cap_x0 + size, 2] = np.clip(fl[..., 2] * 0.5 + 0.5, 0, 1)
    root = np.repeat(1 - (np.arange(Ht)[:, None] + 0.5) / Ht, a.shape[1], 1)
    if bake is not None:  # the baked strands' own directions (across, along: down the picture = -up) and root-to-tip
        fb = bake["flow"]
        nb = np.maximum(np.linalg.norm(fb, axis=-1, keepdims=True), 1e-6)
        flow[Ht:, :, 0], flow[Ht:, :, 1] = fb[..., 0] / nb[..., 0], -fb[..., 1] / nb[..., 0]
        flow[Ht:, :, 2] = np.clip(nb[..., 0], 0, 1)
        root = np.concatenate([root, bake["root"].astype(np.float32)], 0)
    out = {"color": np.concatenate([col, a[..., None]], -1).astype(np.float32), "normal": nrm.astype(np.float32),
           "aux": np.stack([root, idm, dep, a], -1).astype(np.float32), "tiles": tiles, "size": size,
           "flow": np.concatenate([flow[..., :2] * 0.5 + 0.5, flow[..., 2:]], -1).astype(np.float32),
           "coverage": {t["kind"]: round(float(c["alpha"].mean()), 2) for t, c in zip(tiles, cols)},
           "source": "groom" if lines else "drawn", "rows": Ht, "rows_total": a.shape[0], "bake_k": bake_k}
    if len(_ATLAS) > 6:
        _ATLAS.pop(next(iter(_ATLAS)))
    _ATLAS[key] = out
    return out


def remap_v(m: dict | None, at: dict, skip=None) -> dict | None:
    """A mesh's uv made for the tiles alone (v over the whole height) moved to the tiles' rows of an atlas with a bake
    block under them; `skip` (per vertex bool): already in the full atlas's coordinates (baked cards)."""
    if m is None or at.get("rows_total", at.get("rows")) == at.get("rows") or not len(m["uv"]):
        return m
    vb = 1.0 - at["rows"] / at["rows_total"]
    uv = np.array(m["uv"], np.float32)
    sel = np.ones(len(uv), bool) if skip is None else ~np.asarray(skip, bool)
    uv[sel, 1] = vb + uv[sel, 1] * (1.0 - vb)
    return {**m, "uv": uv}


def write_atlas(at: dict, stem: str) -> dict:
    """<stem>_color.png (RGBA), _normal.png, _aux.png (root, id, depth, alpha), _flow.png (direction east / up as
    0..1, strength: KHR_materials_anisotropy's texture)."""
    from PIL import Image
    out = {}
    for k in ("color", "normal", "aux", "flow"):
        out[k] = f"{stem}_{k}.png"
        Image.fromarray(np.clip(at[k] * 255 + 0.5, 0, 255).astype(np.uint8)).save(out[k])
    return out


# ------------------------------------------------------------------------------------------------ cards from locks

def spine(lk: dict, n: int = 64):
    """A resolved lock's spine as Blender draws it, evenly by arc length: points (n, 3), radius, tilt, the lock's
    own parameter u (0 root .. 1 tip) and arc length s (m). Free handles are honoured; auto ones are Catmull-Rom's."""
    P = np.asarray(lk["pts"], float)
    H = lk.get("handles") or [None] * len(P)
    rad = np.asarray(lk.get("radius") or [1.0] * len(P), float)
    tilt = np.asarray(lk.get("tilt") or [0.0] * len(P), float)
    Q = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
    out, par = [], []
    t = np.linspace(0, 1, 12, endpoint=False)[:, None]
    for i in range(len(P) - 1):
        p0, p3 = P[i], P[i + 1]
        p1 = np.asarray(H[i][3:], float) if H[i] else p0 + (Q[i + 2] - Q[i]) / 6
        p2 = np.asarray(H[i + 1][:3], float) if H[i + 1] else p3 - (Q[i + 3] - Q[i + 1]) / 6
        out.append((1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1 + 3 * (1 - t) * t ** 2 * p2 + t ** 3 * p3)
        par.append(i + t[:, 0])
    C = np.vstack(out + [P[-1:]])
    par = np.concatenate(par + [[len(P) - 1.0]])
    s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(C, axis=0), axis=1))]
    si = np.linspace(0, s[-1], n)
    Pn = np.stack([np.interp(si, s, C[:, k]) for k in range(3)], 1)
    pi = np.interp(si, s, par)
    k = np.arange(len(P))
    return Pn, np.interp(pi, k, rad), np.interp(pi, k, tilt), si / max(s[-1], 1e-9), si


def frames(P, C, ang, core=None):
    """Per spine point: tangent T, the lock's outward normal N (away from the head centre C, or from the nearest point
    of `core`, a polyline: a tail's own axis) turned by `ang` (radians) about T, and B = T x N (across the lock).
    Where "outward" runs along the lock (a tail leaving the head), the frame is carried on from the point before."""
    T = _unit(np.gradient(P, axis=0))
    if core is not None and len(core) >= 2:
        K = np.asarray(core, float)
        a, b = K[:-1], K[1:]
        ab = b - a
        tt = np.clip(((P[:, None] - a[None]) * ab[None]).sum(-1) / np.maximum((ab * ab).sum(-1), 1e-12)[None], 0, 1)
        near = a[None] + tt[..., None] * ab[None]
        d = np.linalg.norm(P[:, None] - near, axis=-1)
        cen = near[np.arange(len(P)), d.argmin(1)]
    else:
        cen = np.asarray(C, float)[None]
    out = _unit(P - cen)
    perp = out - (out * T).sum(-1, keepdims=True) * T
    N = np.zeros_like(P)
    prev = None
    for i in range(len(P)):
        v = perp[i]
        if prev is not None:
            pt = prev - (prev @ T[i]) * T[i]
            v = v + 0.25 * pt / max(np.linalg.norm(pt), 1e-9)
        if np.linalg.norm(v) < 1e-6:
            v = np.cross(T[i], [1.0, 0, 0]) if abs(T[i][0]) < 0.9 else np.cross(T[i], [0, 1.0, 0])
        N[i] = v / np.linalg.norm(v)
        prev = N[i]
    c, s = np.cos(ang)[:, None], np.sin(ang)[:, None]
    N = N * c + np.cross(T, N) * s
    return T, N, np.cross(T, N), cen


def _lock_cards(lk: dict, C, S: dict, rng, n: int = 72) -> list:
    """The cards of one resolved lock: each {"P" centre line, "X" across (unit), "N" normal, "hw" half width, "u"
    the lock's parameter, "s" m along, "kind", "layer", "bend" (the volume's outward direction there)}."""
    from .hair import lock_width
    inp = lk["inputs"]
    S = {**S, **(lk.get("strands") or {})}
    P, rad, tilt, u, s = spine(lk, n)
    ang = np.radians(inp.get("Flip", 0.0) + inp.get("Twist", 0.0) * u) + tilt
    T, N, B, cen = frames(P, C, ang, lk.get("core"))
    W, th = float(inp["Width"]), float(inp["Thickness"])
    lw = np.clip(lock_width(inp, u) * rad, 0.0, 4.0)
    cw = float(np.clip(W * 0.62, 0.006, S["card_width"]))
    na = 1 if W <= cw * 1.15 else int(np.ceil(W / (cw * 0.72)))
    L = max(1, int(S["layers"]))
    R = float(S["random"])
    hw0 = cw / 2 * np.maximum(lw, 0.2) ** 0.6
    span = np.maximum(W / 2 * lw - 0.55 * hw0, 0.0)
    lam = max(float(S["wavelength"]), 0.01)
    phi0 = rng.uniform(0, 2 * np.pi)
    env = _ss(s / 0.03)
    free = float(lk.get("free", 0.0))
    out = []

    def card(x, yo, kind, layer, u0=0.0, u1=1.0, hw=None, drift=None, amp=1.0):
        a = 0.35 * x + rng.normal(0, 0.12)
        if layer > 0 and drift is None:  # upper cards lift off the ones under them by their own amount: depth
            yo = yo + th * R * rng.uniform(0.0, 1.2) * np.sin(np.pi * np.clip(u, 0, 1)) ** 0.8
        X = _unit(B * np.cos(a) - N * np.sin(a))
        Nc = np.cross(X, T)
        # a lock lying on the head is held by the hair round it: it waves a little, in its own plane; free hair
        # swings fully and (curl) leaves its plane
        A = float(S["wave"]) * amp * (1 + R * rng.uniform(-0.5, 0.5)) * (0.3 + 0.7 * free)
        th_ = 2 * np.pi * s / lam + phi0 + R * rng.uniform(-1.2, 1.2)
        swing = A * env * np.sin(th_)
        lift = A * env * float(S["curl"]) * np.cos(th_) * free
        Pc = P + B * (x * span + swing)[:, None] + N * (yo + lift - inp.get("Cup", 0.0) * x * x)[:, None]
        if drift is not None:
            Pc = Pc + drift
        sel = (u >= u0 - 1e-9) & (u <= u1 + 1e-9)
        if sel.sum() < 3:
            return
        h = (hw0 if hw is None else np.full(len(u), hw))[sel]
        out.append({"P": Pc[sel], "X": X[sel], "N": Nc[sel], "hw": h, "u": u[sel], "s": s[sel], "kind": kind,
                    "prio": layer + 0.45 * min(abs(float(x)), 1.0) + (0.0 if free < 0.5 or W >= 0.016 else 0.3),
                    "cval": 1 + R * rng.uniform(-0.28, 0.28),
                    "layer": layer, "bend": _unit(P[sel] - (cen[sel] if len(cen) > 1 else cen[0])), "T": T[sel]})

    edge = bool(lk.get("at_hairline"))
    for la in range(L):
        kind = ("hairline" if edge else "dense") if la == 0 else ("medium" if la == 1 else "sparse")
        if free > 0.5:  # hair off the head has nothing to hide under it: no opaque base (a solid ribbon), and a
            kind = "sparse" if (W < 0.016 or la >= 2) else "medium"  # wisp is a few strands
            if L == 1 and W >= 0.016:  # (the far tier: one card a lock has to be the lock)
                kind = "dense"
        nl = na if la == 0 else max(1, na - (la % 2))
        for j in range(nl):
            x = ((j + 0.5 + R * rng.uniform(-0.25, 0.25)) / nl - 0.5) * 2 if nl > 1 else R * rng.uniform(-0.3, 0.3)
            yo = th * (-0.15 + 0.6 * la / max(L - 1, 1)) + th * rng.uniform(-0.05, 0.05)
            k2 = kind if (L > 1 or j % 2 == 0 or edge) else "medium"
            u1 = 1.0 - S["tips"] * R * rng.uniform(0.0, 0.22) if la > 0 else 1.0
            u0 = R * rng.uniform(0.0, 0.3) if la > 0 else 0.0  # (their roots staggered up the lock)
            if edge and la > 0:  # the line stays the thin layer's: upper cards start behind it
                u0 = max(u0, min(0.3, 0.02 / max(s[-1], 1e-6)))
            card(x, yo, k2, la, u0, u1)
    nf = rng.poisson(float(S["flyaway"]) * na * L)
    for _ in range(int(nf)):
        u0 = rng.uniform(0.0, 0.5)
        u1 = min(1.0, u0 + rng.uniform(0.3, 0.7))
        g = _ss((u - u0) / max(u1 - u0, 1e-6)) ** 1.5
        d = rng.normal(0, 1) * B + abs(rng.normal(0.6, 0.6)) * N
        drift = g[:, None] * d * rng.uniform(0.004, 0.018 + 0.03 * free)
        card(rng.uniform(-1.1, 1.1), th * rng.uniform(0.5, 1.3), "fly", L, u0, u1, hw=rng.uniform(0.005, 0.009),
             drift=drift, amp=1.4)
    return out


def _resample(c: dict, m: int) -> dict:
    """A card at m rows (evenly along it)."""
    s = c["s"]
    si = np.linspace(s[0], s[-1], m)
    o = dict(c)
    for k in ("P", "X", "N", "bend", "T"):
        o[k] = np.stack([np.interp(si, s, c[k][:, j]) for j in range(3)], 1)
    for k in ("hw", "u", "rad"):
        if k in c and np.ndim(c[k]):
            o[k] = np.interp(si, s, c[k])
    o["s"] = si
    return o


def mesh(cards: list, S: dict, look: dict, tiles: list, segment: float | None = None, seed: int = 0) -> dict:
    """Cards -> one triangle mesh: verts, tris, uv per vertex (Blender's way up: v = 1 at the root), normal (bent
    toward the volume's), tangent (along the hair), col (rgb multiplier: root to tip, a value per lock, lower layers
    darker; a = 1), plus per-vertex along / card / layer."""
    rng = np.random.default_rng(seed + 5)
    seg = float(segment or S["segment"])
    by = {}
    for i, t in enumerate(tiles):
        by.setdefault(t["kind"], []).append(i)
    V, F, UV, Nn, Tn, COL, AL, LAY, CID, BK = [], [], [], [], [], [], [], [], [], []
    off = 0
    rootd, rootl = (0.7 if S.get("short") else 0.62), (0.45 if S.get("short") else float(look.get("root", 0.12)))  # (a short cut's cards
    # root in the cap, which carries the shade: darkened roots were dark flakes on it)
    tip_amt = float(look.get("tip_amount", 0.0))
    rnd = float(S["round"])
    lam = max(float(S["wavelength"]), 0.01)
    for ci, c in enumerate(cards):
        length = float(c["s"][-1] - c["s"][0])
        per = seg if float(S["wave"]) <= 0 else min(seg, lam / 6)
        m = int(np.clip(np.ceil(length / max(per, 1e-4)), 2, 200)) + 1
        hwm = float(np.max(c["hw"]))
        c = _resample(c, m)
        vv = (c["s"] - c["s"][0]) / max(length, 1e-9)
        left, right = c["P"] - c["X"] * c["hw"][:, None], c["P"] + c["X"] * c["hw"][:, None]
        V.append(np.stack([left, right], 1).reshape(-1, 3))
        if c.get("island") is not None:  # its own baked picture (hair_clumps.bake): across = the clump's spread
            u0, u1, vt, vb = c["island"]
            fr = c["hw"] / max(2 * hwm, 1e-9)
            vi = vt - vv * (vt - vb)
            UV.append(np.stack([np.stack([u0 + (0.5 - fr) * (u1 - u0), vi], 1),
                                np.stack([u0 + (0.5 + fr) * (u1 - u0), vi], 1)], 1).reshape(-1, 2))
            BK.append(np.ones(2 * m, bool))
        else:
            t = tiles[by[c["kind"]][int(rng.integers(len(by[c["kind"]])))]]
            ua, ub = (t["u0"], t["u1"]) if rng.random() < 0.5 else (t["u1"], t["u0"])
            UV.append(np.stack([np.stack([np.full(m, ua), 1 - vv], 1), np.stack([np.full(m, ub), 1 - vv], 1)], 1).reshape(-1, 2))
            BK.append(np.zeros(2 * m, bool))
        nb = c["N"] * np.where((c["N"] * c["bend"]).sum(-1, keepdims=True) < 0, -1.0, 1.0)
        nb = _unit((1 - rnd) * nb + rnd * c["bend"])
        if EDGE_ROUND > 0 and np.ndim(c.get("rad")):
            # each edge its own normal: the volume's outward direction THERE (a card on a cylinder of radius R: n at the
            # edge = R n + / - hw X), so neighbouring cards shade as one rounded mass instead of flat planks, each with
            # its own tilt (lock-scale bands, a tail of flat sheets, dark wedges where a wide card's plane turns from the
            # light: g4_b19). Turned at most ~60 deg (R >= hw / 1.7)
            R_ = np.maximum(np.asarray(c["rad"], float), c["hw"] / 1.7)
            k_ = (EDGE_ROUND * c["hw"] / np.maximum(R_, 1e-6))[:, None]
            Nn.append(np.stack([_unit(nb - c["X"] * k_), _unit(nb + c["X"] * k_)], 1).reshape(-1, 3))
        else:
            Nn.append(np.repeat(nb, 2, 0))
        Tn.append(np.repeat(c["T"], 2, 0))
        ramp = rootd + (1 - rootd) * _ss(c["u"] / max(rootl, 1e-3))
        ramp = ramp * (1 + tip_amt * 0.35 * _ss((c["u"] - 0.55) / 0.45))
        lay = 1.0  # (lower layers were darkened here AND by the atlas's depth: a dark band wherever layer 0 showed)
        if S.get("colour_model", True) and not S.get("short"):
            # the look's colour model on the cards (tesshair7; hair_colour): each card is a ribbon: its lock's drift
            # and depth, lighter with the hair's age along it, a share of cards highlight ribbons. Stored / peak (a
            # vertex colour cannot brighten); the atlas is lifted by the same peak (atlas colour x col = the tone)
            from . import hair_colour as hcol
            import re as _re
            nm = str(c.get("lock", ""))
            hsh_ = int(hashlib.md5(nm.encode()).hexdigest()[:8], 16)
            age = (c["s"] - c["s"][0]) + (hcol.TAIL_AGE if _re.fullmatch(r"t\d*[ty]\d+", nm) else 0.0)
            # a highlight is a RIBBON of a few mm: on a card wider than HIGHLIGHT_W the whole card lit up, a pale
            # rectangle (Tess's tail at the 'lock' cut: a patchwork of light and dark blocks)
            hl_ = ((hsh_ // 1000 + ci * 7919) % 1000) / 999.0 + 1e-4 if 2 * float(np.median(c["hw"])) <= HIGHLIGHT_W else None
            tone = hcol.lock_tone(look, (hsh_ % 1000) / 999.0, float(c.get("shade", 0.0))) \
                * hcol.along_tone(look, age, hl_, float(c.get("sun", 0.0)))
            if c.get("island") is not None:  # its picture carries its strands' tone (hair_clumps.strand_tones)
                tone = np.full(np.shape(age), float(c.get("tone_k", 1.0)))
            if c.get("fine"):  # rows the strands draw FINE (see-through, light against the sky: the outline): half the lift;
                # at full tone the sparse tile's hairs were a hard dark wire rim round the head (review c2)
                tone = tone * (1 + 0.3 * hcol._k(look, "fly_light", 0.3))
            if c.get("wisp") and c.get("island") is None:  # face-framing bundles read lighter (the strands' fly_light; Tess's are near blonde). Not
                # every fly card: the halo's and the hairline's lying on the head were pale strips across the sweep
                tone = tone * (1 + 0.6 * hcol._k(look, "fly_light", 0.3))
            ramp = ramp * tone / hcol.peak(look)
        COL.append(np.repeat(np.clip(ramp * lay * c.get("value", 1.0) * c.get("cval", 1.0), 0, 1)[:, None]
                             * np.ones(3)[None], 2, 0))
        AL.append(np.repeat(c["u"], 2))
        LAY.append(np.full(2 * m, c["layer"], np.float32))
        CID.append(np.full(2 * m, ci, np.int32))
        i = np.arange(m - 1) * 2 + off
        F.append(np.concatenate([np.stack([i, i + 1, i + 3], 1), np.stack([i, i + 3, i + 2], 1)]))
        off += 2 * m
    if not V:
        z = np.zeros((0, 3), np.float32)
        return {"verts": z, "tris": np.zeros((0, 3), np.int32), "uv": np.zeros((0, 2), np.float32), "normal": z,
                "tangent": z, "col": z, "along": np.zeros(0, np.float32), "layer": np.zeros(0, np.float32),
                "card": np.zeros(0, np.int32), "baked": np.zeros(0, bool)}
    return {"verts": np.concatenate(V).astype(np.float32), "tris": np.concatenate(F).astype(np.int32),
            "uv": np.concatenate(UV).astype(np.float32), "normal": np.concatenate(Nn).astype(np.float32),
            "tangent": np.concatenate(Tn).astype(np.float32), "col": np.concatenate(COL).astype(np.float32),
            "along": np.concatenate(AL).astype(np.float32), "layer": np.concatenate(LAY),
            "card": np.concatenate(CID), "baked": np.concatenate(BK)}


def cards_of(locks: list, C, S: dict, look: dict | None = None) -> list:
    """Every resolved lock's cards (hair.resolve's list), each with its lock's name and value."""
    look = look or {}
    out = []
    vary = float(look.get("vary", 0.25))
    for lk in locks:
        seed = int(hashlib.md5(lk["name"].encode()).hexdigest()[:8], 16)
        rng = np.random.default_rng(seed)
        val = 1 + vary * 0.8 * (rng.uniform() - 0.5)
        for c in _lock_cards(lk, C, S, rng):
            c["lock"], c["value"] = lk["name"], val
            out.append(c)
    return out


# ------------------------------------------------------------------------------------------ cards from the strands

GRID = 40  # stations along a lock at which its strands are compared
FINE_SPARSE = 0.5  # a lock whose strands are drawn at least this fine (strands.fine: see-through) is cut on the sparse tile
FREE_SPREAD, FREE_CLIP = 3.2, 1.3  # hanging cards' half width in the clump's sigmas, and its cap in card widths
FREE_END = 0.06  # hanging hair's cards run on until only this share of their strands is left (at 0.3 Tess's tail ended ~5 cm short)


def strand_grid(D: dict, locks: list, n: int = GRID) -> dict:
    """The groom's lock strands (not the scalp layer) on a common grid: every strand resampled at `n` stations of
    its LOCK's parameter (NaN where the strand hasn't started or has ended: roots are staggered, tips ragged), so
    strands of one clump can be averaged station by station. {"A" (strands, n, 3), "lock", "sub", "rand", "free"}."""
    from scipy.spatial import cKDTree
    names = [str(x) for x in D["names"]]
    first = np.r_[0, np.cumsum(D["counts"])]
    U = np.linspace(0.0, 1.0, n)
    trees = {}
    A, LK, SUB, RND = [], [], [], []
    for j in range(len(D["counts"])):
        if names[int(D["obj"][j])] not in ("hair_guides", "hair_guides_free", "hair_guides_wisp") or D["counts"][j] < 2:
            continue
        li = int(D["lock"][j])
        if li >= len(locks):
            continue
        if li not in trees:
            P, *_ = spine(locks[li], 96)
            trees[li] = cKDTree(P)
        Q = D["pts"][first[j]:first[j + 1]].astype(float)
        _, k = trees[li].query(Q[[0, -1]])
        u0, u1 = k[0] / 95.0, k[1] / 95.0
        if u1 - u0 < 0.05:
            continue
        s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))]
        t = (U - u0) / (u1 - u0)
        ok = (t >= 0) & (t <= 1)
        a = np.full((n, 3), np.nan)
        if ok.sum() < 2:
            continue
        a[ok] = np.stack([np.interp(t[ok] * s[-1], s, Q[:, c]) for c in range(3)], 1)
        A.append(a)
        LK.append(li)
        SUB.append(int(D["sub"][j]))
        RND.append(float(D["rand"][j]))
    return {"A": np.asarray(A), "lock": np.asarray(LK, int), "sub": np.asarray(SUB, int), "rand": np.asarray(RND),
            "u": U}


def _transport(v, t0, t1):
    """v (normal to t0) carried to t1 by the smallest rotation taking t0 onto t1."""
    c = float(t0 @ t1)
    ax = np.cross(t0, t1)
    sn = float(np.linalg.norm(ax))
    if sn < 1e-9:
        return v if c > 0 else v
    ax = ax / sn
    return v * c + np.cross(ax, v) * sn + ax * float(ax @ v) * (1 - c)


def _nan_smooth(x, k: int = 2):
    out = x.copy()
    for i in range(len(x)):
        out[i] = np.nanmean(x[max(0, i - k):i + k + 1])
    return out


def _medoid_line(A, P, w: float):
    """P moved (share `w`) onto one of its clump's own long strands, the one nearest the mean: hanging hair's mean over
    strands of other phases is straight (a wavy tail's cards hung as straight sheets, its bottom curl lost: b23 back
    edge -33 mm at 150-180 mm, review "straight stringy sheets"); a real strand keeps the wave and the curl. Before the
    strand starts and past its end the offset is held (the line stays continuous)."""
    from scipy.ndimage import gaussian_filter1d
    fin = np.isfinite(A[..., 0])
    n = fin.sum(1)
    if not n.max():
        return P
    long_ = n >= np.percentile(n, 75)
    with np.errstate(invalid="ignore"), __import__("warnings").catch_warnings():
        __import__("warnings").simplefilter("ignore")
        dist = np.nanmean(np.linalg.norm(A - P[None], axis=-1), 1)
    dist = np.where(long_ & np.isfinite(dist), dist, np.inf)
    j = int(np.argmin(dist))
    f = fin[j]
    k = np.nonzero(f)[0]
    if len(k) < 4:
        return P
    D = np.zeros_like(P)
    D[k] = A[j, k] - P[k]
    D[:k[0]] = D[k[0]]
    D[k[-1] + 1:] = D[k[-1]]
    D = gaussian_filter1d(D, 1.0, axis=0)
    return P + w * D


PCA_FRAME = 1.0  # (0 before round 22) hanging (tail / face) cards: share of the turn toward the clump's flat cross-section (0 = off, the
# outward frame only, before round 22)
PCA_MAX = 60.0  # deg (round 23; 90 = unlimited, round 22): the PCA turn is held to this angle from the outward frame. A card turned
# past ~60 deg is seen from its BACK from outside the tail, and a double-sided card's back is shaded with the flipped
# (inward) normal: b30's dark leaf-shaped shards between the tail cards near the tie (lit only; flat albedo and shadow=0
# both still had them; round 23)


def _clump(A, U, cen_of, min_share: float = 0.3, start_share: float = 0.04, end_share: float | None = None,
           medoid: float = 0.0, twist: float = 0.0):
    """A set of strands (m, n, 3 with NaN) as one clump: its centre line, frame and spread, over the stations where
    at least `min_share` of its strands run (`end_share`: on to the last station where that share still runs: hanging
    hair's ragged ends). None if too short."""
    with np.errstate(invalid="ignore"):
        cnt = np.isfinite(A[..., 0]).sum(0)
    ok = cnt >= max(1, int(np.ceil(min_share * len(A))))
    idx = np.nonzero(ok)[0]
    if len(idx) < 4:
        return None
    if end_share is not None:
        last = np.nonzero(cnt >= max(1, int(np.ceil(end_share * len(A)))))[0]
        if len(last) and last[-1] > idx[-1]:
            idx = np.r_[idx, np.arange(idx[-1] + 1, last[-1] + 1)]
    # a clump starts where its FIRST strands do (roots are staggered: the card's picture fades its root in; started
    # where a third of them run, the front row stood as a ledge 1.5 cm behind the hairline) and ends where few are left
    first = np.nonzero(cnt >= max(1, int(np.ceil(start_share * len(A)))))[0]
    idx = np.r_[first[0], idx] if first[0] < idx[0] else idx
    sl = slice(idx[0], idx[-1] + 1)
    with np.errstate(invalid="ignore"), __import__("warnings").catch_warnings():
        __import__("warnings").simplefilter("ignore")
        P = np.nanmean(A[:, sl], 0)
    if not np.isfinite(P).all():
        good = np.isfinite(P[:, 0])
        k = np.arange(len(P))
        P = np.stack([np.interp(k, k[good], P[good, c]) for c in range(3)], 1)
    # the mean jumps wherever a strand starts or ends: smoothed more where few strands run (a hanging tail's last 20%
    # kinked by 45-130 deg a station: crumpled paper ends, b12; head cards hooked at their staggered roots)
    from scipy.ndimage import gaussian_filter1d
    few = np.clip(1.0 - cnt[sl] / max(min_share * len(A), 1.0), 0.0, 1.0)[:, None]
    if len(P) > 4:
        # padded by carrying each end straight on (mode "nearest" squashed the last stations together: tiny segments,
        # random tangents at the ends)
        n_ = 12
        t0, t1 = P[0] - P[min(3, len(P) - 1)], P[-1] - P[-1 - min(3, len(P) - 1)]
        st_ = np.arange(1, n_ + 1)[:, None] / 3.0
        Pp = np.r_[P[0] + t0 * st_[::-1], P, P[-1] + t1 * st_]
        P = (gaussian_filter1d(Pp, 1.0, axis=0) * (1 - np.r_[few[:1].repeat(n_, 0), few, few[-1:].repeat(n_, 0)])
             + gaussian_filter1d(Pp, 4.0, axis=0) * np.r_[few[:1].repeat(n_, 0), few, few[-1:].repeat(n_, 0)])[n_:-n_]
    if medoid > 0 and len(A) > 1 and len(P) > 4:
        P = _medoid_line(A[:, sl], P, medoid)
    T = _unit(np.gradient(P, axis=0))
    cen = cen_of(P)
    out = _unit(P - cen)
    perp = out - (out * T).sum(-1, keepdims=True) * T
    # where the hair runs straight away from the head (into a tie, off a crown) "outward" says nothing about which
    # way a card faces: the frame is carried on from where it was sure (cards stood on edge round the tie as flaps)
    N = np.zeros_like(P)
    i0 = int(np.argmax(np.linalg.norm(perp, axis=1)))
    prev = _unit(perp[i0])
    for rng_ in (range(i0, len(P)), range(i0 - 1, -1, -1)):
        prev_ = prev
        j_ = i0
        for i in rng_:
            w = float(np.clip((np.linalg.norm(perp[i]) - 0.35) / 0.4, 0.0, 1.0))
            # carried by the turn of the flow (a rotation-minimising frame), not projected: where the hair rises
            # straight off the part T turns INTO the old normal and the projection was ~0, a random way: the cards
            # stood on edge over the part as planks
            pt = prev_ if j_ is None else _transport(prev_, T[j_], T[i])
            j_ = i
            v = w * _unit(perp[i]) + (1 - w) * _unit(pt)
            N[i] = v / max(np.linalg.norm(v), 1e-9)
            prev_ = N[i]
    if twist > 0 and PCA_FRAME > 0 and len(A) > 2:  # hanging cards: turn the frame so the card's WIDTH lies along the
        # clump's widest spread (its cross-section's major axis) where that section is clearly flat. "Outward" from the core
        # made the tail's edge clumps face sideways, so from the back (and front) they were seen edge-on as thin dark
        # ribbons arching off the tie (round 22, b29 g1backl cards 230 / 299 / 345), where the groom shows a broad mass
        X0 = _unit(np.cross(T, N))
        with np.errstate(invalid="ignore"), __import__("warnings").catch_warnings():
            __import__("warnings").simplefilter("ignore")
            d_ = A[:, sl] - P[None]
            a_, b_ = (d_ * X0[None]).sum(-1), (d_ * N[None]).sum(-1)
            ok_ = np.isfinite(a_) & np.isfinite(b_)
            a_, b_ = np.where(ok_, a_, 0.0), np.where(ok_, b_, 0.0)
            n_ok = np.maximum(ok_.sum(0), 1)
            ma, mb = a_.sum(0) / n_ok, b_.sum(0) / n_ok
            caa = (a_ * a_).sum(0) / n_ok - ma * ma
            cbb = (b_ * b_).sum(0) / n_ok - mb * mb
            cab = (a_ * b_).sum(0) / n_ok - ma * mb
        tr_ = np.maximum(caa + cbb, 1e-12)
        an_ = np.sqrt((caa - cbb) ** 2 + 4 * cab ** 2) / tr_  # 0 round .. 1 flat
        w_ = np.clip((an_ - 0.3) / 0.4, 0.0, 1.0) * (ok_.sum(0) >= 3)
        c2, s2 = gaussian_filter1d((caa - cbb) / tr_ * w_, 2.0), gaussian_filter1d(2 * cab / tr_ * w_, 2.0)
        th = 0.5 * np.arctan2(s2, c2)  # the major axis' angle from X0 (axial, smoothed as a doubled angle)
        th = th * PCA_FRAME * np.clip(gaussian_filter1d(w_.astype(float), 2.0) / 0.5, 0.0, 1.0)
        th = np.clip(th, -np.radians(PCA_MAX), np.radians(PCA_MAX))
        Xn = X0 * np.cos(th)[:, None] + N * np.sin(th)[:, None]
        Nn = _unit(np.cross(Xn, T))
        Nn = np.where(((Nn * N).sum(-1) < 0)[:, None], -Nn, Nn)
        N = Nn
    if twist > 0:  # the frame turns about the hair by at most `twist` rad per station: hanging hair's "outward" swings
        # round where the line curls past its core, a 60 mm tail card twisted half a turn in ~30 mm (b24 / b25 hanging/L0
        # card 201: the "folded flap" at the tail's end, 10-11 folded triangle pairs, crownx.py)
        for rng_ in (range(i0 + 1, len(P)), range(i0 - 1, -1, -1)):
            for i in rng_:
                j = i - 1 if rng_.step == 1 else i + 1
                pt = _unit(_transport(N[j], T[j], T[i]))
                pt = _unit(pt - (pt @ T[i]) * T[i])
                a = float(np.arctan2(np.cross(pt, N[i]) @ T[i], pt @ N[i]))
                if abs(a) > twist:
                    b = np.sign(a) * twist
                    N[i] = pt * np.cos(b) + np.cross(T[i], pt) * np.sin(b)
    X = _unit(np.cross(T, N))
    with np.errstate(invalid="ignore"), __import__("warnings").catch_warnings():
        __import__("warnings").simplefilter("ignore")
        d = A[:, sl] - P[None]
        dx, dn = (d * X[None]).sum(-1), (d * N[None]).sum(-1)
        sx, sn = np.nanstd(dx, 0), np.nanstd(dn, 0)
        mx = np.nanmedian(dx, 1)  # each strand's side of the clump
    sx, sn = np.nan_to_num(sx), np.nan_to_num(sn)
    return {"P": P, "T": T, "N": N, "X": X, "sx": _nan_smooth(sx), "sn": _nan_smooth(sn), "u": U[sl], "mx": mx,
            "bend": out, "rad": np.linalg.norm(P - cen, axis=1), "share": cnt[sl] / max(len(A), 1), "i0": int(idx[0])}


def clump_cards(D: dict, locks: list, C, S: dict, look: dict | None = None, seed: int = 0) -> list:
    """Cards cut from the groom's own STRANDS (what the card tools do: cluster strands into clumps, a few cards a
    clump, layered by opacity): each card's centre line is the mean of its clump's strands, so cards wave, part and
    end where the strands do, and its width is their spread. `S["group"]`: how big a clump is: "sub" (the groom's
    sub clumps: a hero), "pair" (two sub clumps), "lock" (a whole lock: fewer, wider cards), "free" (locks off the
    head only: the cap carries the rest). A clump wider than `card_width` is cut across into slices, each its own
    card on its own strands. Layers: 0 = coverage (dense tile, just under the clump's middle), 1 = medium over it,
    2+ = sparse break-up; a hero also gets single fly-away strands. Card dicts as _lock_cards'."""
    from .hair_strands import is_gather
    look = look or {}
    G = strand_grid(D, locks)
    if not len(G["A"]):
        return []
    rng = np.random.default_rng(seed + 3)
    group = str(S.get("group", "sub"))
    L = max(1, int(S["layers"]))
    cw = float(S["card_width"])
    vary = float(look.get("vary", 0.25))
    Rr = float(S["random"])
    C = np.asarray(C, float)
    out = []
    pool = [int(li) for li in np.unique(G["lock"]) if is_single(locks[int(li)])] if S.get("pool_singles", True) else []
    for li in np.unique(G["lock"]):
        lk = locks[int(li)]
        free = float(lk.get("free", 0.0)) > 0.5
        if group == "free" and not free:
            continue
        if int(li) in pool:
            continue
        if int(lk.get("hairs") or 0) > 0 and not lk.get("face") and not halo_card_ok(lk, C):
            continue  # (a few single hairs rooted in the mass over the crown (off_head): cut as wisps they stood 2-3 cm
            # over it at LOD1-3, round 29; the hero gives them no card either)
        sel = G["lock"] == li
        A, sub = G["A"][sel], G["sub"][sel]
        core = lk.get("core")
        if core is not None and len(core) >= 2:
            K = np.asarray(core, float)

            def cen_of(P, K=K):
                a, b = K[:-1], K[1:]
                ab = b - a
                tt = np.clip(((P[:, None] - a[None]) * ab[None]).sum(-1) / np.maximum((ab * ab).sum(-1), 1e-12)[None], 0, 1)
                near = a[None] + tt[..., None] * ab[None]
                return near[np.arange(len(P)), np.linalg.norm(P[:, None] - near, axis=-1).argmin(1)]
        else:
            def cen_of(P):
                return C[None]
        lrng = np.random.default_rng(int(hashlib.md5(lk["name"].encode()).hexdigest()[:8], 16))
        val = 1 + vary * 0.8 * (lrng.uniform() - 0.5)
        if group == "sub":
            keys = sub
        elif group == "pair":
            keys = sub // 2
        else:
            keys = np.zeros(len(sub), int)
        edge = bool(lk.get("at_hairline"))
        gather = is_gather(lk)
        fine = not free and float((lk.get("strands") or {}).get("fine", 0.0) or 0.0) >= FINE_SPARSE  # (hanging hair
        # drawn fine, a tail, still has a body to cover)
        for kk in np.unique(keys):
            Ag = A[keys == kk]
            c0 = _clump(Ag, G["u"], cen_of, end_share=FREE_END if free else None)
            if c0 is None:
                continue
            width = 2 * 1.7 * float(np.percentile(c0["sx"], 75))
            na = max(1, int(np.ceil(width / cw)))
            order = np.argsort(c0["mx"])
            for j in range(na):
                part = Ag[order[j * len(order) // na:(j + 1) * len(order) // na]] if na > 1 else Ag
                if len(part) < 1:
                    continue
                c = _clump(part, G["u"], cen_of, end_share=FREE_END if free else None) if na > 1 else c0
                if c is None:
                    continue
                s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(c["P"], axis=0), axis=1))]
                if s[-1] < 0.01:
                    continue
                # (cards overlap their neighbours by a third: where they only met, every seam was a slit of shadow)
                # hanging hair is its OUTLINE: a tail's outer strands stand 3 sigma off the clump's mean (at 2.5 sigma,
                # clipped to 0.9 card widths, Tess's tail was 75 % of the strands' width)
                hw_full = np.clip((FREE_SPREAD if free else 2.5) * c["sx"], 0.003, (FREE_CLIP if free else 0.9) * cw)
                thin = free and float(lk["inputs"]["Width"]) < 0.016  # (a wisp: a lock of a few hairs off the head)
                # a wisp of 8+ hairs (Tess's face-framing locks: 9-16 hairs, 12-19 cm) reads as a light BUNDLE in the
                # strands: its first card wears the sparse tile (on the fly tile alone it was two or three grey wires)
                bundle = thin and int(lk.get("hairs") or 0) >= 8
                if thin:  # a wisp is a few hairs: a narrow card that runs out to a point (at full width an alpha
                    # test at any distance fills it: a brown slat down the cheek)
                    hw_full = (np.clip(1.4 * c["sx"], 0.002, 0.005) if bundle else np.clip(1.4 * c["sx"], 0.0012, 0.0025)) \
                        * (1 - 0.5 * _ss((s / s[-1] - 0.5) / 0.5))
                if gather:  # into the tie a card runs out to nothing (its square end stood over the crown)
                    hw_full = hw_full * (1 - 0.5 * _ss((s / s[-1] - 0.8) / 0.2))  # (to nothing, 0.85, the tie's band
                    # showed between them: a black blob the strands hide)
                off_c = abs((j + 0.5) / na - 0.5) * 2 if na > 1 else 0.0
                nl = (3 if L > 2 else 2) if thin else L
                for la in range(nl):
                    if thin:  # a wisp: two or three thin cards of separate hairs side by side, never a filled
                        kind = "sparse" if (bundle and la == 0) else "fly"  # ribbon (under an alpha test: a dark slash)
                    elif fine:  # a lock the strands draw FINE (part rows, the rim: see-through hair): never the dense
                        kind = "sparse"  # tile (Tess's part rows rose off the part as opaque planks: the "fan" at the part)
                    elif la == 0:
                        kind = "hairline" if (edge and not free) else "dense"
                    else:
                        # hair lying on the head is a combed, closed surface: its second layer is dense too (over a
                        # medium one the layer under it showed through as dark chop), on the tile whose ROOTS come in
                        # one by one (the dense tile starts as a cut edge: under an alpha test every staggered card
                        # root drew a line across the flow, a brick pattern); loose hair opens up sooner
                        kind = ("hairline" if (la == 1 and not free and L > 2) else "medium") if (la <= 2 - int(free) and not thin) else "sparse"
                    yo = c["sn"] * (-0.3 + 0.4 * la) + (0.0003 * la)  # (layers lie close: lifted, each cast a shadow line)
                    xo = (rng.uniform(-0.35, 0.35) * hw_full if la > 0 else 0.0)
                    if thin:  # (a bundle's cards spread as its hairs do: at 0.9 card widths apart its 9-16 hairs,
                        # splayed over 2-3 cm, were three wires side by side)
                        xo = (la - (nl - 1) / 2) * (np.maximum(0.9 * hw_full, 1.3 * c["sx"]) if bundle else 0.9 * hw_full) \
                            + rng.uniform(-0.2, 0.2) * hw_full
                    hw = hw_full * (1.0 if la == 0 else 0.9)
                    u0 = 0.0 if la == 0 else Rr * rng.uniform(0.0, 0.25)
                    u1 = 1.0 if (la == 0 or gather) else 1.0 - float(S["tips"]) * Rr * rng.uniform(0.0, 0.2)
                    if edge and la > 0:
                        u0 = max(u0, min(0.3, 0.02 / max(s[-1], 1e-6)))
                    f = (s / s[-1])
                    keep = (f >= u0 - 1e-9) & (f <= u1 + 1e-9)
                    if keep.sum() < 3:
                        continue
                    P = c["P"] + c["X"] * (np.zeros(len(s)) + xo)[:, None] + c["N"] * yo[:, None]
                    out.append({"P": P[keep], "X": c["X"][keep], "N": c["N"][keep], "hw": hw[keep], "u": c["u"][keep],
                                "s": s[keep], "kind": kind, "layer": la,
                                "prio": (0.3 * la if bundle else la) + 0.3 * off_c + (0.25 if (thin and la > 0) else 0.0),
                                "cval": 1 + Rr * rng.uniform(-0.2, 0.2), "bend": c["bend"][keep], "T": c["T"][keep],
                                "lock": lk["name"], "value": val, "sn": np.asarray(c["sn"])[keep] if np.ndim(c["sn"]) else c["sn"],
                                "wisp": bool(bundle), "fine": bool(fine)})
            nf = int(S.get("fly", 0))
            if nf and not gather and len(Ag) >= 6:  # single strands that stand off the clump: a card each
                with np.errstate(invalid="ignore"), __import__("warnings").catch_warnings():
                    __import__("warnings").simplefilter("ignore")
                    i0 = c0["i0"]
                    far = np.nanmax(np.linalg.norm(Ag[:, i0:i0 + len(c0["P"])] - c0["P"][None], axis=-1), 1)
                far = np.nan_to_num(far)
                lim = max(3.0 * float(np.median(c0["sx"])), 0.004)
                for i in np.argsort(-far)[:nf]:
                    if far[i] < lim:
                        break
                    Q = Ag[i]
                    okq = np.isfinite(Q[:, 0])
                    if okq.sum() < 5:
                        continue
                    Pq = Q[okq]
                    Tq = _unit(np.gradient(Pq, axis=0))
                    cq = cen_of(Pq)
                    oq = _unit(Pq - cq)
                    Nq = _unit(oq - (oq * Tq).sum(-1, keepdims=True) * Tq)
                    sq = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(Pq, axis=0), axis=1))]
                    out.append({"P": Pq, "X": _unit(np.cross(Tq, Nq)), "N": Nq, "hw": np.full(len(Pq), 0.004),
                                "u": G["u"][okq], "s": sq, "kind": "fly", "layer": L, "prio": L + 1.0,
                                "cval": 1.0, "bend": oq, "T": Tq, "lock": lk["name"], "value": val})
    if pool:
        out += pooled_singles(G, locks, pool, C, L, rng)
    if FLY_FAR_TIERS and out:
        out = drop_far_fly(out, G, locks)
    return out


FLY_FAR_TIERS = True  # (round 30) the hero's FLY_FAR at every tier: fly cards (pooled halo hairs, few-hair wisps) standing
# further than hair_clumps.FLY_FAR off the rest of the hair get no card. Without it LOD1-3 had thin spikes standing
# sideways off the tail by the tie, 35-80 mm past LOD0's hair (round 29's standoff / t30/tiespk.py)


def drop_far_fly(cards: list, G: dict, locks: list) -> list:
    """Fly cards (not face-framing) whose centre line stands further than hair_clumps.FLY_FAR off the strands of the
    locks that aren't few single hairs (the hero's rule for its single hairs: hair_clumps FLY_FAR)."""
    from scipy.spatial import cKDTree
    from .hair_clumps import FLY_FAR
    few = np.array([int(lk.get("hairs") or 0) > 0 and not lk.get("face") for lk in locks] + [False])
    rest = ~few[np.clip(np.asarray(G["lock"]).astype(int), 0, len(few) - 1)]
    Q = np.asarray(G["A"], float)[rest].reshape(-1, 3)
    Q = Q[np.isfinite(Q[:, 0])]
    if not len(Q):
        return cards
    tr = cKDTree(Q[:: max(1, len(Q) // 200000)])
    face = {lk["name"] for lk in locks if lk.get("face")}
    return [c for c in cards if c["kind"] != "fly" or c.get("lock") in face
            or float(tr.query(np.asarray(c["P"], float))[0].max()) <= FLY_FAR]


EDGE_ROUND = 0.0  # share of a card's across-curvature given to its edge normals (mesh; 0 = one normal across). b20 at
# 1.0: lock band 6.25 -> 6.38 front, 6.16 -> 6.23 3/4, nape wedge L* 7.6 -> 7.5, tail still "flat": no gain, off
HIGHLIGHT_W = 0.008  # m: cards wider than this carry no highlight of their own (a ribbon is a few mm)
SINGLES_PER_CARD = 8  # single-hair locks (a halo, escaped hairs) pooled onto one fly card: a card of the fly tile pictures
# a few hairs; 420 halo hairs cut as 3 cards each (Tess's W18) were 7k triangles, all of them cut by any game budget


def is_single(lk: dict) -> bool:
    """A lock of a few single hairs lying on the head hair (a halo, escaped hairs): not face-framing, not a tail's."""
    return int(lk.get("hairs") or 0) > 0 and not lk.get("face") and not lk.get("off_head")


def halo_card_ok(lk: dict, C) -> bool:
    """The hero's rules for which single hairs get a card (hair_clumps FLY_CROWN / FLY_CROWN_FREE / FLY_STRAIGHT), for
    every tier: none rooted over the crown (a few single hairs there stood 1-3 cm over it as dark strokes on LOD1-3
    only, round 29: the hero leaves them to the strands' look), none that loop (cards read them as stiff arcs)."""
    from .hair_clumps import FLY_CROWN, FLY_CROWN_FREE, FLY_STRAIGHT
    P = np.asarray(lk["pts"], float)
    if len(P) < 2 or P[0, 2] > float(np.asarray(C)[2]) + (FLY_CROWN_FREE if lk.get("off_head") else FLY_CROWN):
        return False
    L = float(np.linalg.norm(np.diff(P, axis=0), axis=1).sum())
    return L > 0 and float(np.linalg.norm(P[-1] - P[0])) >= FLY_STRAIGHT * L


def pooled_singles(G: dict, locks: list, pool: list, C, L: int, rng) -> list:
    """Single-hair locks clustered by where they run (root, middle, end), SINGLES_PER_CARD a cluster, each cluster ONE
    fly card along its hairs' mean path: the halo as a few cards standing where the hairs stand."""
    from scipy.cluster.vq import kmeans2
    C = np.asarray(C, float)
    pool = [li for li in pool if halo_card_ok(locks[li], C)]
    if not pool:
        return []
    feats = []
    for li in pool:
        P = np.asarray(locks[li]["pts"], float)
        feats.append(np.r_[P[0], P[len(P) // 2], P[-1]])
    feats = np.asarray(feats)
    k = max(1, int(np.ceil(len(pool) / SINGLES_PER_CARD)))
    if k < len(pool):
        _, lab = kmeans2(feats, k, minit="++", seed=int(rng.integers(1 << 30)))
    else:
        lab = np.arange(len(pool))
    out = []
    for g in np.unique(lab):
        lis = [pool[i] for i in np.nonzero(lab == g)[0]]
        A = G["A"][np.isin(G["lock"], lis)]
        if len(A) < 1:
            continue
        c = _clump(A, G["u"], lambda P: C[None], min_share=0.25)
        if c is None:
            continue
        s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(c["P"], axis=0), axis=1))]
        if s[-1] < 0.01:
            continue
        # narrow: the fly tile's hairs are a share of the card's width (FLY_HAIR), at 10 mm cards they were 0.7 mm
        # wide, a halo of brown leaves over the crown
        hw = np.clip(1.2 * c["sx"], 0.0012, 0.002) * (1 - 0.4 * _ss((s / s[-1] - 0.6) / 0.4))
        out.append({"P": c["P"], "X": c["X"], "N": c["N"], "hw": hw, "u": c["u"], "s": s, "kind": "fly", "layer": L,
                    "prio": L + 1.0, "cval": 1.0, "bend": c["bend"], "T": c["T"], "lock": locks[lis[0]]["name"],
                    "value": 1.0, "sn": c["sn"], "pooled": True})
    return out


CORE_SHARE = 0.5  # a tail core runs while this share of its strands still run (b22: it ends inside the cards; 0.2 before: its square end showed mid-tail)
CORE_TAPER = 0.25  # share of the core's length over which its radius closes to a point (b22; 0 = square cut, before)


def tail_cores(D: dict, locks: list, sides: int = 10, stations: int = 28, fill: float = 0.8) -> dict | None:
    """A solid surface inside each bundle of hair that hangs round a `core` line (a tied tail): the shape the tail's
    own strands make, a little inside them (`fill` of their radius per direction), so cards over it never show air
    between them and a far tier's tail is this shape alone. It follows the strands station by station (a tail that
    swings to one side swings the core with it). A mesh like hair_cards.mesh's (uv: u round the tail in dense tiles
    is set by the caller: "around" 0..1, "along" 0..1)."""
    G = strand_grid(D, locks, n=stations)
    if not len(G["A"]):
        return None
    groups: dict = {}
    for li in np.unique(G["lock"]):
        lk = locks[int(li)]
        core = lk.get("core")
        if core is None or len(core) < 2 or float(lk.get("free", 0.0)) <= 0.5:
            continue
        groups.setdefault(json.dumps(np.round(np.asarray(core, float), 4).tolist()), []).append(int(li))
    V, F, AR, AL, NR, TN = [], [], [], [], [], []
    off = 0
    for key_, lis in groups.items():
        if len(lis) < 3:
            continue
        A = G["A"][np.isin(G["lock"], lis)]
        with np.errstate(invalid="ignore"), __import__("warnings").catch_warnings():
            __import__("warnings").simplefilter("ignore")
            cnt = np.isfinite(A[..., 0]).sum(0)
            Pm = np.nanmean(A, 0)
        ok = np.nonzero(cnt >= max(3, CORE_SHARE * len(A)))[0]
        if len(ok) < 4:
            continue
        sl = slice(ok[0], ok[-1] + 1)
        Pm, A = Pm[sl], A[:, sl]
        T = _unit(np.gradient(Pm, axis=0))
        e1 = np.zeros_like(Pm)
        v = np.cross(T[0], [0.0, 0.0, 1.0])
        v = v if np.linalg.norm(v) > 1e-3 else np.cross(T[0], [1.0, 0.0, 0.0])
        for i in range(len(Pm)):  # parallel transport
            v = v - (v @ T[i]) * T[i]
            v = v / max(np.linalg.norm(v), 1e-9)
            e1[i] = v
        e2 = np.cross(T, e1)
        ang = np.linspace(0, 2 * np.pi, sides, endpoint=False)
        Rr = np.zeros((len(Pm), sides))
        with np.errstate(invalid="ignore"):
            d = A - Pm[None]
            x, y = (d * e1[None]).sum(-1), (d * e2[None]).sum(-1)
            th, rr = np.arctan2(y, x), np.hypot(x, y)
        for i in range(len(Pm)):
            good = np.isfinite(rr[:, i])
            if good.sum() < 3:
                continue
            base = float(np.percentile(rr[good, i], 60))
            for a_i, a in enumerate(ang):
                w = good & (np.abs(((th[:, i] - a + np.pi) % (2 * np.pi)) - np.pi) < 2 * np.pi / sides * 1.2)
                Rr[i, a_i] = float(np.percentile(rr[w, i], 75)) if w.sum() >= 3 else base
        for _ in range(2):  # smooth round and along
            Rr = (np.roll(Rr, 1, 1) + 2 * Rr + np.roll(Rr, -1, 1)) / 4
            Rr[1:-1] = (Rr[:-2] + 2 * Rr[1:-1] + Rr[2:]) / 4
        Rr = np.maximum(Rr * fill, 0.002)
        if CORE_TAPER > 0:  # the core closes over its last CORE_TAPER (a tube cut square was a dark ragged block showing
            # through the thinning tail cards: b21 review "dark crunchy patch mid-tail", traced by flat passes per range)
            sa = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(Pm, axis=0), axis=1))]
            uu = np.clip((sa[-1] - sa) / max(CORE_TAPER * sa[-1], 1e-6), 0.0, 1.0)
            Rr = np.maximum(Rr * (uu * uu * (3 - 2 * uu))[:, None], 0.0005)
        s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(Pm, axis=0), axis=1))]
        ns = len(Pm)
        ring = (np.cos(ang)[None, :, None] * e1[:, None] + np.sin(ang)[None, :, None] * e2[:, None])  # (ns, sides, 3)
        Vr = Pm[:, None] + ring * Rr[..., None]
        # a seam column (u = 1) so the tiles wrap
        Vr = np.concatenate([Vr, Vr[:, :1]], 1)
        nr = np.concatenate([ring, ring[:, :1]], 1)
        V.append(Vr.reshape(-1, 3))
        NR.append(nr.reshape(-1, 3))
        TN.append(np.repeat(T, sides + 1, 0))
        AR.append(np.tile(np.arange(sides + 1) / sides, ns))
        AL.append(np.repeat(s / max(s[-1], 1e-9), sides + 1))
        i, j = np.meshgrid(np.arange(ns - 1), np.arange(sides), indexing="ij")
        a = (i * (sides + 1) + j).ravel() + off
        b, c, d_ = a + 1, a + sides + 2, a + sides + 1
        F.append(np.concatenate([np.stack([a, b, c], 1), np.stack([a, c, d_], 1)]))
        off += ns * (sides + 1)
    if not V:
        return None
    return {"verts": np.concatenate(V).astype(np.float32), "tris": np.concatenate(F).astype(np.int32),
            "normal": np.concatenate(NR).astype(np.float32), "tangent": np.concatenate(TN).astype(np.float32),
            "around": np.concatenate(AR).astype(np.float32), "along": np.concatenate(AL).astype(np.float32)}


def core_mesh(core: dict, tiles: list, reps: int = 4) -> dict:
    """tail_cores' surface wearing the dense tile round it (mirrored every other repeat, so it has no seam), root at
    the tie, the tile's ragged end at the tail's end."""
    t = next(t for t in tiles if t["kind"] == "dense")
    tri = np.abs(((core["around"] * reps) % 2.0) - 1.0)
    n = len(core["verts"])
    return {"verts": core["verts"], "tris": core["tris"],
            "uv": np.stack([t["u0"] + (t["u1"] - t["u0"]) * tri, 1 - core["along"]], 1).astype(np.float32),
            "normal": core["normal"], "tangent": core["tangent"], "col": np.full((n, 3), 0.8, np.float32),
            "along": core["along"], "layer": np.full(n, -1.0, np.float32), "card": np.zeros(n, np.int32)}


MASS_CELL = 0.007  # m: the voxel the hair's density is counted on


def mass_shell(D: dict, locks: list, C, tiles: list, col=None, triangles: int = 3000, tier: str = "loose",
               level: float = 0.3, reps: int = 10) -> dict | None:
    """A solid surface INSIDE a loose mass of hair (what tail_cores is for a tied tail): the strands of the `tier`
    locks counted on a voxel grid, smoothed, meshed where the hair is `level` x as dense as its typical inside, cut
    down to `triangles`. Cards over it never show air or skin between them, and a far tier is little more than
    this. Faces turned toward the body close to it are dropped (nobody sees the inside of a head of hair). It
    wears the dense tile: v = how far along its strands the hair there is (root .. tip, so the tile's ragged end
    lies at the hair's ends), u round the head. `col`: hair_loose.Collider (the body)."""
    from scipy import ndimage
    from skimage import measure
    names = [str(n) for n in D["names"]]
    if "hair_guides_free" not in names:
        return None
    want = np.array([lk.get("tier") == tier for lk in locks] + [False])
    lock = np.asarray(D["lock"]).astype(int)
    sel = (np.asarray(D["obj"]) == names.index("hair_guides_free")) & want[np.clip(lock, 0, len(want) - 1)]
    if sel.sum() < 50:
        return None
    cnt = np.asarray(D["counts"])
    first = np.r_[0, np.cumsum(cnt)]
    idx = np.concatenate([np.arange(first[j], first[j + 1]) for j in np.nonzero(sel)[0]])
    u = np.concatenate([np.linspace(0, 1, cnt[j]) for j in np.nonzero(sel)[0]])
    P = np.asarray(D["pts"], float)[idx]
    T = np.gradient(np.asarray(D["pts"], float), axis=0)[idx]
    h = MASS_CELL
    lo = P.min(0) - 4 * h
    n = np.ceil((P.max(0) - lo) / h).astype(int) + 5
    ijk = np.floor((P - lo) / h).astype(int)
    flat = np.ravel_multi_index(ijk.T, n)
    size = int(np.prod(n))
    den = np.bincount(flat, minlength=size).astype(float).reshape(n)
    uu = np.bincount(flat, weights=u, minlength=size).reshape(n)
    tt = np.stack([np.bincount(flat, weights=T[:, k], minlength=size).reshape(n) for k in range(3)], -1)
    dn = ndimage.gaussian_filter(den, 1.0)
    us = ndimage.gaussian_filter(uu, 1.5) / np.maximum(ndimage.gaussian_filter(den, 1.5), 1e-9)
    ts = np.stack([ndimage.gaussian_filter(tt[..., k], 1.5) for k in range(3)], -1)
    ref = float(np.percentile(dn[den > 0], 60))
    if not (dn.max() > level * ref > 0):
        return None
    V, F, Nn, _ = measure.marching_cubes(dn, level * ref, spacing=(h, h, h))
    V = V + lo + 0.5 * h
    Nn = -_unit(Nn)  # (the gradient points into the hair: density rises inward)
    fn = _unit(np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]))
    if (fn * Nn[F].mean(1)).sum(-1).mean() < 0:
        F, fn = F[:, ::-1], -fn
    if col is not None:  # the faces toward the body, near it
        fc = V[F].mean(1)
        ph = col.at(fc)
        F = F[~((ph < 0.03) & ((fn * col.grad(fc)).sum(-1) < -0.2)) & (ph > -0.002)]
    if len(F) > triangles:
        import pyfqmr
        used = np.unique(F)
        re_ = -np.ones(len(V), int)
        re_[used] = np.arange(len(used))
        sm = pyfqmr.Simplify()
        sm.setMesh(V[used], re_[F])
        sm.simplify_mesh(target_count=int(triangles), aggressiveness=5, preserve_border=False, verbose=False)
        V, F, _ = sm.getMesh()
        V, F = np.asarray(V, float), np.asarray(F, int)
    if len(F) < 8:
        return None
    used = np.unique(F)
    re_ = -np.ones(len(V), int)
    re_[used] = np.arange(len(used))
    V, F = V[used], re_[F]
    q = ((V - lo - 0.5 * h) / h).T
    grad = np.stack([ndimage.map_coordinates(g_, q, order=1, mode="nearest") for g_ in np.gradient(dn)], -1)
    Nn = -_unit(grad)
    tan = _unit(np.stack([ndimage.map_coordinates(ts[..., k], q, order=1, mode="nearest") for k in range(3)], -1))
    tan = _unit(tan - (tan * Nn).sum(-1, keepdims=True) * Nn)
    along = np.clip(ndimage.map_coordinates(us, q, order=1, mode="nearest"), 0.02, 0.98)
    az = np.arctan2(V[:, 0] - C[0], -(V[:, 1] - C[1])) / (2 * np.pi) + 0.5
    t = next(t for t in tiles if t["kind"] == "dense")
    tri = np.abs(((az * reps) % 2.0) - 1.0)
    m = len(V)
    return {"verts": V.astype(np.float32), "tris": F.astype(np.int32),
            "uv": np.stack([t["u0"] + (t["u1"] - t["u0"]) * tri, 1 - 0.85 * along], 1).astype(np.float32),
            "normal": Nn.astype(np.float32), "tangent": tan.astype(np.float32), "col": np.full((m, 3), 0.8, np.float32),
            "along": along.astype(np.float32), "layer": np.full(m, -1.0, np.float32), "card": np.zeros(m, np.int32)}


def triangles(cards: list, S: dict, segment: float | None = None) -> int:
    seg = float(segment or S["segment"])
    lam = max(float(S["wavelength"]), 0.01)
    per = seg if float(S["wave"]) <= 0 else min(seg, lam / 6)
    return int(sum(2 * int(np.clip(np.ceil(float(c["s"][-1] - c["s"][0]) / per), 2, 200)) for c in cards))


def fit_budget(cards: list, S: dict, budget: int) -> tuple[list, float, dict]:
    """Cards and a segment length for a triangle budget: segments lengthen first (to 3 cm, or the tier's own
    segment), then cards go one by one, the least needed first (`prio`: fly-aways and the top layers' outer cards
    before the coverage layer's centre cards, so every lock keeps its middle card longest). Returns (cards,
    segment, what was dropped)."""
    info = {"asked": int(budget)}
    seg = float(S["segment"])
    seg_max = seg * 1.5  # (stretching every card to 3 cm segments first made a hero's cards straight planks)
    keep = list(cards)
    for _ in range(40):
        n = triangles(keep, S, seg)
        if n <= budget or seg >= seg_max:
            break
        seg = min(seg_max, seg * max(1.08, min(n / budget, 2.0)))
    if triangles(keep, S, seg) > budget:
        order = sorted(range(len(keep)), key=lambda i: keep[i].get("prio", keep[i]["layer"]))
        cost = np.cumsum([triangles([keep[i]], S, seg) for i in order])
        m = max(1, int(np.searchsorted(cost, budget, side="right")))
        kept = sorted(order[:m])
        info["dropped_cards"] = len(keep) - m
        keep = [keep[i] for i in kept]
    info["triangles"], info["segment"] = triangles(keep, S, seg), round(seg, 4)
    return keep, seg, info


def join(*meshes) -> dict:
    """Card meshes joined into one."""
    ms = [m for m in meshes if m is not None and len(m["verts"])]
    if not ms:  # nothing to join (a far tier of a short cut: no hair off the head, no baby hairs): an empty mesh
        return next(m for m in meshes if m is not None)
    out, off, nc = {}, 0, 0
    tris = []
    for m in ms:
        tris.append(m["tris"] + off)
        off += len(m["verts"])
    for k in ("verts", "uv", "normal", "tangent", "col", "along", "layer"):
        out[k] = np.concatenate([m[k] for m in ms])
    cards = []
    for m in ms:
        cards.append(m["card"] + nc)
        nc += int(m["card"].max()) + 1 if len(m["card"]) else 0
    out["card"] = np.concatenate(cards)
    out["tris"] = np.concatenate(tris)
    return out


# ------------------------------------------------------------------------------------------------ shadow proxy

SHADOW_PROXY = {"voxel": 0.004, "close": 4, "inset": 0.004, "smooth": 1.2, "step": 2}  # (round 19: the cards' own
# shadow was a dithered shadow map over many transparent sheets: grain on the skin (std 0.42 vs the groom's 0.31) and
# -4.5 L*. Engines give card hair a separate opaque, smooth caster: shading.py hair_cards "shadows")


def shadow_proxy(V, T, voxel: float | None = None, close: int | None = None, inset: float | None = None,
                 smooth: float | None = None, step: int | None = None) -> dict:
    """An opaque, smooth, low-poly hull of the cards' volume that casts the hair's shadow in place of the cards (a
    shadow-only mesh: invisible to the camera). The card triangles are sampled into a `voxel` grid, closed (dilate
    `close` voxels, fill holes, erode back), shrunk by `inset` (the outer cards stay lit, the hull sits under them),
    blurred (`smooth` voxels: a soft round body, not a voxel staircase) and meshed with marching cubes at `step` voxels.
    Returns {"verts", "tris", "voxel", "inset"}."""
    from scipy import ndimage
    from skimage import measure
    o = {**SHADOW_PROXY, **{k: v for k, v in dict(voxel=voxel, close=close, inset=inset, smooth=smooth, step=step).items()
                            if v is not None}}
    h = float(o["voxel"])
    V = np.asarray(V, np.float64)
    T = np.asarray(T, np.int64)
    A, B, C = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    L = np.maximum(np.maximum(np.linalg.norm(B - A, axis=1), np.linalg.norm(C - A, axis=1)), np.linalg.norm(C - B, axis=1))
    k = np.clip(np.ceil(L / (0.5 * h)).astype(int), 1, 64)  # samples per edge: every voxel a triangle crosses is hit
    pts = []
    for kk in np.unique(k):
        sel = k == kk
        u, v = np.meshgrid(np.arange(kk + 1), np.arange(kk + 1), indexing="ij")
        m = (u + v) <= kk
        u, v = u[m] / kk, v[m] / kk
        a, b, c = A[sel], B[sel], C[sel]
        pts.append((a[:, None] + u[None, :, None] * (b - a)[:, None] + v[None, :, None] * (c - a)[:, None]).reshape(-1, 3))
    P = np.concatenate(pts)
    pad = int(o["close"]) + 4
    lo = P.min(0) - pad * h
    n = np.ceil((P.max(0) + pad * h - lo) / h).astype(int) + 1
    g = np.zeros(n, bool)
    ij = np.floor((P - lo) / h).astype(int)
    g[ij[:, 0], ij[:, 1], ij[:, 2]] = True
    ball = ndimage.generate_binary_structure(3, 1)
    c = int(o["close"])
    g = ndimage.binary_dilation(g, ball, iterations=c)
    g = ndimage.binary_fill_holes(g)
    g = ndimage.binary_erosion(g, ball, iterations=c + int(round(float(o["inset"]) / h)))
    f = ndimage.gaussian_filter(g.astype(np.float32), float(o["smooth"]))
    if f.max() < 0.5:
        return {"verts": np.zeros((0, 3), np.float32), "tris": np.zeros((0, 3), np.int64), "voxel": h, "inset": o["inset"]}
    vv, ff, _, _ = measure.marching_cubes(f, 0.5, step_size=int(o["step"]), allow_degenerate=False)
    return {"verts": (vv * h + lo).astype(np.float32), "tris": ff.astype(np.int64), "voxel": h, "inset": float(o["inset"])}


def write_obj(path, verts, tris, name: str = "hair_shadow", yup: bool = True) -> None:
    """A plain OBJ (positions + faces): what every engine and DCC imports. yup: Blender's Z-up written Y-up (as the
    GLB beside it, and as OBJ importers expect: x, z, -y)."""
    V = np.asarray(verts, np.float64)
    if yup:
        V = np.stack([V[:, 0], V[:, 2], -V[:, 1]], 1)
    with open(path, "w") as fh:
        fh.write(f"o {name}\n")
        np.savetxt(fh, V, fmt="v %.5f %.5f %.5f")
        np.savetxt(fh, np.asarray(tris) + 1, fmt="f %d %d %d")
