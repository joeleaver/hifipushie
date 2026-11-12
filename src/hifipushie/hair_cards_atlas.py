"""The strand tiles and the atlas: drawn lines, a tile, `atlas`, remap_v, write_atlas. Part of hair cards (hair_cards.py has the overview)."""
from __future__ import annotations

import hashlib
import json

import numpy as np

from . import hair_cards
from .hair_cards import _lin, _srgb, _ss, _unit

# ------------------------------------------------------------------------------------------------ the strand atlas
def _drawn_lines(kind: str, w: int, S: dict, rng) -> list:
    """Strands made up for a tile: [(x across 0..1, v along 0..1, depth 0..1, id 0..1), ...]."""
    k = hair_cards.KIND[kind]
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


def _tile(kind: str, w: int, H: int, S: dict, rng, ss: int = 3, lines: list | None = None, short: bool = False) -> dict:
    """One tile: strands drawn root (row 0) to tip, lower ones first. alpha, id (a value per strand), depth (0 deep ..
    1 on top), all (H, w) floats."""
    from PIL import Image, ImageDraw
    from scipy import ndimage
    if kind == "band":
        one = np.ones((H, w), np.float32)
        return {"alpha": one, "id": one * 0.5, "depth": one, "band": True}
    k = hair_cards.KIND[kind]
    W2, H2 = w * ss, H * ss
    ims = [Image.new("L", (W2, H2), 0) for _ in range(3)]
    da, di, dd = (ImageDraw.Draw(i) for i in ims)
    # fly: the tile of wisps and stray hairs, a few separate hairs drawn THICK (a wisp card is ~6 mm across 64 px:
    # at 3 texels a hair is 0.3 mm, a few hairs lying together, and still there after an alpha test at arm's length;
    # at one texel the whole wisp fell under the cutoff and vanished) from a root that starts at full strength (it
    # comes out of the hair, its root buried there: faded in, the wisp seemed to start on bare skin lower down)
    thick = (max(3.0 * ss, hair_cards.FLY_HAIR * w * ss) if kind == "fly" else max(k["thick"] * ss * w / 160, 1.15 * ss)) if kind in ("fly", "baby") else k["thick"] * ss
    if lines is None:  # drawn strands (no groom at hand); else `lines` = real strands of the groom's own clumps
        lines = _drawn_lines(kind, w, S, rng)
    if short and kind in hair_cards.SHORT_TILE:  # a short cut's card is ~1 cm wide and seen 3-4 mips down: a few strands, each
        # several texels thick (0.3-0.5 mm on the card), survive the minification as strands; a hundred 1-texel ones
        # average to a grey film that an alpha test turns into a solid flake or into sparkle
        n_, th_ = hair_cards.SHORT_TILE[kind]
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
    elif short and kind in hair_cards.SHORT_TILE:  # a few hairs over the cap: lit (the cap under them is the shade)
        dep = hair_cards.SHORT_DEPTH + (1 - hair_cards.SHORT_DEPTH) * dep
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
    solid = a > hair_cards.EDGE_SOLID
    if solid.any():  # values carried past the alpha's edge and over its anti-aliased rim (no dark fringe under filtering)
        ix = ndimage.distance_transform_edt(~solid, return_distances=False, return_indices=True)
        idm, dep = idm[ix[0], ix[1]], dep[ix[0], ix[1]]
    return {"alpha": a, "id": idm, "depth": dep}


def atlas(S: dict, look: dict, lines: dict | None = None, cap: dict | None = None, key: str = "",
          bake: dict | None = None, shells: list | None = None) -> dict:
    """The strand atlas: {"color" (H, W, 4) sRGB floats, straight alpha; "normal" (H, W, 3); "aux" (H, W, 4): root
    gradient, strand id, depth, alpha; "tiles": [{"kind", "u0", "u1"}] (v runs the whole height: 0 = the root, at the
    top of the picture)}. Colour = the look's gap colour deep down to its lit colour on top, a value per strand.
    `bake` (hair_clumps_bake.bake: cards' own strands, a block as wide as the tiles + chart): stacked UNDER the tiles; the
    tiles' rows are then the top `rows` of `rows_total` (every tile / chart uv's v is remapped: remap_v).
    `shells` (hair_cap.combed's shell maps, sh1): a block under everything else, one slot (size / 2 square) a shell
    side by side; out["shells"] = {"row0", "rows", "slot_w"} (texels) for their uv."""
    key = hashlib.sha1(json.dumps([{k: S.get(k) for k in ("clump", "frizz", "curl", "tips", "atlas", "short")},
                                   {k: look.get(k) for k in ("gap", "lit", "vary", "band", "card_band", "card_gain", "card_sat", "tone_front", "tone_back", "grey", "grey_share", "card_grey", "grey_locks", "grey_amount", "sun", "highlights", "highlight_contrast", "variation", "headroom")}, key, sorted(hair_cards.SHORT_TILE.items()), hair_cards.SHORT_DEPTH, hair_cards.EDGE_SOLID, hair_cards.GREY_LIFT, hair_cards.GREY_SPREAD, (bake or {}).get("key"), [hashlib.sha1(np.ascontiguousarray(s_["alpha"]).tobytes()).hexdigest() for s_ in (shells or [])],
                                   [hashlib.sha1(np.ascontiguousarray(m_["value"]).tobytes()).hexdigest() for m_ in [cap or {}] + list(shells or []) if m_.get("value") is not None]], sort_keys=True).encode()).hexdigest()
    if key in hair_cards._ATLAS:
        return hair_cards._ATLAS[key]
    from scipy import ndimage
    size = int(S["atlas"])
    H = size
    rng = np.random.default_rng(11)
    cols, tiles, x = [], [], 0
    cap_val = None
    for kind, w0 in hair_cards.TILES:
        w = int(round(w0 * size / 1024))
        cols.append(_tile(kind, w, H, S, rng, lines=(lines or {}).get(len(cols)), short=bool(S.get("short"))))
        tiles.append({"kind": kind, "u0": (x + 2.0) / size, "u1": (x + w - 2.0) / size})
        x += w
    if cap is not None:  # the scalp's own chart beside the tiles (hair_strands.cap_chart): the atlas is 2 : 1
        from PIL import Image
        rs = lambda m: np.asarray(Image.fromarray((np.clip(m, 0, 1) * 255).astype(np.uint8)).resize(  # noqa: E731
            (size, H), Image.BILINEAR), np.float32) / 255
        cols.append({k: rs(cap[k]) for k in ("alpha", "id", "depth")})
        if cap.get("value") is not None:  # (sh4) the cap's regional value factor (hair_cap.VALUE_MAP)
            cap_val = rs(np.clip(cap["value"], 0, 1))
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
    Hb_ = a.shape[0]  # (the tiles' and the bake block's rows: shells go under them)
    sh_rows, sh_w = 0, 0
    if shells:
        from PIL import Image as _Im
        sh_rows = sh_w = size // 2
        if len(shells) * sh_w > a.shape[1]:
            raise ValueError("hair atlas: at most %d shells" % (a.shape[1] // sh_w))
        rsh = lambda m: np.asarray(_Im.fromarray((np.clip(m, 0, 1) * 255).astype(np.uint8)).resize(  # noqa: E731
            (sh_w, sh_rows), _Im.BILINEAR), np.float32) / 255
        blk = {k: np.zeros((sh_rows, a.shape[1]), np.float32) for k in ("alpha", "id", "depth", "grey")}
        for j_, s_ in enumerate(shells):
            for k in blk:
                blk[k][:, j_ * sh_w:(j_ + 1) * sh_w] = rsh(s_[k])
        a, idm, dep = (np.concatenate([m, blk[k]], 0) for m, k in ((a, "alpha"), (idm, "id"), (dep, "depth")))
    gap, lit = _lin(look.get("gap", "#221310")), _lin(look.get("lit", "#56352d"))
    shade = (0.45 + 0.55 * dep ** 0.8)[..., None]
    # a value per strand: what makes a card read as hairs, not a painted sheet (strands: +-vary and more)
    val = (1 + float(look.get("vary", 0.25)) * 3.0 * (idm - 0.5))[..., None]
    hl_ = float(look.get("highlights") or 0.0)
    if hl_ > 0 and not S.get("short"):  # highlight RIBBONS as strands of the tiles (a share of the ids, lighter): a
        # card is 10-48 mm wide, a highlight a few mm; lit per card the tail was a patchwork of pale blocks
        hs_ = np.clip((idm - (1.0 - 0.22 * hl_)) / 0.03, 0.0, 1.0) * np.clip((dep - 0.32) / 0.2, 0.0, 1.0)
        xk_ = 0  # (not on the fly / baby tiles: of their 14 hairs two lit ones made a wisp card a silver-grey strip)
        for (kind_, _w), c_ in zip(hair_cards.TILES, cols):
            w_ = c_["alpha"].shape[1]
            if kind_ in ("fly", "baby"):
                hs_[:Ht, xk_:xk_ + w_] = 0.0
            xk_ += w_
        if bake is not None:  # (the baked strands carry their own ribbons in their tone)
            hs_[Ht:Hb_] = 0.0
        val = val * (1 + float(look.get("highlight_contrast", 0.6)) * hs_)[..., None]
    if bake is not None and bake.get("tone") is not None:  # the baked strands' own tone (hair_clumps_bake.strand_tones,
        # / peak: the cards' vertex colours then carry only the root ramp)
        from . import hair_colour as hcol
        # (normalised by their mean: the atlas's 8 bits clip over 1, and at tone x peak the highlights went white-grey;
        # the cards' vertex colours carry the mean back: mesh(), card["tone_k"])
        from .hair_clumps import TONE_HEAD
        tb_ = bake["tone"].astype(np.float32) * hcol.peak(look) * TONE_HEAD
        bake_k = float(np.mean(tb_[bake["alpha"] > 0.5])) if (bake["alpha"] > 0.5).any() else 1.0
        val[Ht:Hb_] = (tb_ / max(bake_k, 1e-3))[..., None]
    gain = float(look.get("card_gain", 1.0))  # measured against the strand look (hair.match_cards)
    if S.get("colour_model", True) and not S.get("short"):  # (the cards' vertex colours carry tone / peak: mesh())
        from . import hair_colour as hcol
        gain = gain * hcol.peak(look)
    base = gap[None, None] * (1 - shade) + lit[None, None] * shade
    if cap_val is not None or (shells and shells[0].get("value") is not None):  # (sh4) regional value (VALUE_MAP) on the
        # dark strands and the base only, before the grey hairs go in: on the whole colour (sh4v) the silver went with
        # it (p90 48 vs the photo's 56, grey share 69 -> 21 %); the photo is dark hair + bright silver, a wide range
        vr_ = np.ones(a.shape, np.float32)
        if cap_val is not None:
            vr_[:Ht, cap_x0:cap_x0 + size] = cap_val
        if shells and shells[0].get("value") is not None:
            for j_, s_ in enumerate(shells):
                vr_[Hb_:, j_ * sh_w:(j_ + 1) * sh_w] = rsh(s_["value"])
        base = base * vr_[..., None]
    gs = float(look.get("grey_share") or 0.0) * (float(look.get("card_grey", 0.5)) if S.get("short") else 1.0)  # grey hairs: that share of the strands (by their id) in the grey colour
    if gs > 0:  # (the strand look's own rule: look.grey_amount + the locks' grey x look.grey_locks; cards_job sets it)
        grey = np.clip(_lin(look.get("grey", "#9a948d")) * hair_cards.GREY_LIFT, 0.0, 1.0)
        # (the strands with the highest ids: a threshold on the id stays a strand's own through the picture's
        # anti-aliasing, and the opaque base under the strands (id 0) stays dark; a hash of the id speckled every
        # blended pixel and turned the cap's bare base grey)
        isg = (np.clip((idm - (1.0 - gs)) / 0.04, 0.0, 1.0) * np.clip((dep - 0.32) / 0.2, 0.0, 1.0))[..., None]  # (the
        # base under the strands sits at depth 0.3: it is the shadow between hairs, never grey)
        if bake is not None and bake.get("gshare") is not None:  # (c2) shared tiles: each draws ITS cards' grey share
            gsh_ = np.nan_to_num(np.asarray(bake["gshare"], np.float32), nan=gs)
            if hair_cards.GREY_SPREAD != 1.0:  # (c4) the tiles' shares stretched about their median: tiles average side and top
                # cards (Garrett: tiles side .74 / top .41 = 1.8x where the locks' grey is .64 / .22 = 2.9x; the groom's
                # silver sides read 50 L* at 3/4 vs the cards' 38.6)
                fin_ = np.isfinite(np.asarray(bake["gshare"], np.float32))
                md_ = float(np.median(gsh_[fin_])) if fin_.any() else gs
                gsh_ = np.clip(md_ + hair_cards.GREY_SPREAD * (gsh_ - md_), 0.0, 1.0)
            if hair_cards.GREY_QUANTILE:  # (c3) the share drawn AS a share: the id threshold at that quantile of the tiles' strand
                # pixels' ids (ids are not uniform over 0..1: a .74 share drew 26 % grey texels at Garrett's sides)
                sm_ = (dep[Ht:Hb_] > hair_cards.GREY_DEP0 + hair_cards.GREY_DEPW) & np.isfinite(idm[Ht:Hb_])
                if sm_.sum() > 1000:
                    qq_ = np.quantile(idm[Ht:Hb_][sm_], np.linspace(0, 1, 101))
                    gsh_ = 1.0 - np.interp(1.0 - gsh_, np.linspace(0, 1, 101), qq_)
            isg[Ht:Hb_] = (np.clip((idm[Ht:Hb_] - (1.0 - gsh_)) / 0.04, 0.0, 1.0)
                        * np.clip((dep[Ht:Hb_] - hair_cards.GREY_DEP0) / hair_cards.GREY_DEPW, 0.0, 1.0))[..., None]
        if cap is not None and cap.get("grey") is not None:  # a baked chart knows which of its strands are grey
            isg[:Ht, cap_x0:cap_x0 + size, 0] = rs(cap["grey"])  # (per region: the locks' own shares)
        if shells:  # (sh1) each shell's own grey strands
            isg[Hb_:, :, 0] = blk["grey"]
        base = base * (1 - isg) + grey[None, None] * (0.6 + 0.4 * shade) * isg
    lin = base * val * gain
    cs = float(look.get("card_sat", 1.0))  # x the colour's saturation (cards measured against the strand look)
    if cs != 1.0:
        yl = (lin @ np.array([0.2126, 0.7152, 0.0722]))[..., None]
        lin = yl + (lin - yl) * cs
    if hair_cards.HUE_CLIP > 0:  # (round 41) an over-range texel scaled down as a whole, not clipped per channel: red clipped
        # first and the lightest texels (lifted face wisps, the top's light streaks) went grey-yellow (wisps hue 73 vs
        # the groom's 63, C* 11.8 vs 13.9; atlas red at 252 over 125k texels)
        mx_ = np.max(lin, axis=-1, keepdims=True)
        lin = np.where(mx_ > 1.0, lin / np.maximum(mx_, 1e-6) ** hair_cards.HUE_CLIP, lin)
    col = _srgb(np.clip(lin, 0, 1))
    hr_ = float(look.get("headroom") or 1.0)
    if bake is not None and hr_ > 1.0 and (bake["alpha"] > 0.5).any():  # (c14, Garrett) the baked cards' vertex colours
        # carry tone_k (bake_k x tint) and clip at 1: a third of c11L's card vertices sat AT 1.0 and tone_back 1.0 put
        # 71-83 % there, so every LIGHTENING lever (tone_back, the flow top's lit, card_gain) was eaten while the atlas
        # used ~0.43 of its linear range. Move a factor H into the bake block (H <= headroom, its p99.9 texel <= .98)
        # and divide bake_k by it (the cards' colours / H): the same picture where nothing clipped
        lb_ = lin[Ht:Hb_][bake["alpha"] > 0.5]
        H_ = float(np.clip(0.98 / max(float(np.percentile(lb_, 99.9)), 1e-4), 1.0, hr_))
        lin = lin.copy()
        lin[Ht:Hb_] = lin[Ht:Hb_] * H_
        col = np.concatenate([col[:Ht], _srgb(np.clip(lin[Ht:Hb_], 0, 1)), col[Hb_:]], 0)
        bake_k = bake_k / H_
        print(f"atlas headroom: bake block x {H_:.2f} (cards' vertex colours / {H_:.2f})", flush=True)
    x = 0
    # the tie: under strands the hair gathered into it hides the band; cards run INTO it and the look's band colour
    # (a dark elastic) showed as a black hole (Tess, review c2). It wears the hair's own median colour unless the
    # look names `card_band`
    hair_ = col[:Hb_][(a[:Hb_] > 0.5)] if (a[:Hb_] > 0.5).any() else None  # (not the shells' block: sh1)
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
        flow[Ht:Hb_, :, 0], flow[Ht:Hb_, :, 1] = fb[..., 0] / nb[..., 0], -fb[..., 1] / nb[..., 0]
        flow[Ht:Hb_, :, 2] = np.clip(nb[..., 0], 0, 1)
        root = np.concatenate([root, bake["root"].astype(np.float32)], 0)
    if shells:  # (sh1) the shells' flow / normal; root: their strands' own along-ness is in depth already
        for j_, s_ in enumerate(shells):
            sl_ = (slice(Hb_, Hb_ + sh_rows), slice(j_ * sh_w, (j_ + 1) * sh_w))
            rs3_ = lambda m: np.stack([rsh(m[..., i] * 0.5 + 0.5) * 2 - 1 for i in range(m.shape[-1])], -1)  # noqa: E731
            nrm[sl_] = _unit(rs3_(s_["normal"])) * 0.5 + 0.5
            f_ = rs3_(s_["flow"][..., :2])
            flow[sl_[0], sl_[1], :2] = _unit(np.concatenate([f_, np.zeros_like(f_[..., :1])], -1))[..., :2]
            flow[sl_[0], sl_[1], 2] = rsh(s_["flow"][..., 2])
        root = np.concatenate([root, np.full((sh_rows, root.shape[1]), 0.5, np.float32)], 0)
    out = {"color": np.concatenate([col, a[..., None]], -1).astype(np.float32), "normal": nrm.astype(np.float32),
           "aux": np.stack([root, idm, dep, a], -1).astype(np.float32), "tiles": tiles, "size": size,
           "flow": np.concatenate([flow[..., :2] * 0.5 + 0.5, flow[..., 2:]], -1).astype(np.float32),
           "coverage": {t["kind"]: round(float(c["alpha"].mean()), 2) for t, c in zip(tiles, cols)},
           "source": "groom" if lines else "drawn", "rows": Ht, "rows_total": a.shape[0], "bake_k": bake_k,
           "shells": {"row0": Hb_, "rows": sh_rows, "slot_w": sh_w, "n": len(shells or [])}}
    if len(hair_cards._ATLAS) > 6:
        hair_cards._ATLAS.pop(next(iter(hair_cards._ATLAS)))
    hair_cards._ATLAS[key] = out
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
