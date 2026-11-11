"""The strand bake: shade and tones per strand, `bake`, tile groups, `bake_tiles`. Part of hair clumps (hair_clumps.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import hair_clumps
from .hair_clumps import _cen_of, _ss, _unit, kmeans
from .hair_clumps_layout import _card_coords, _density, layout

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
    age = a0[:, None] + np.arange(St["Q"].shape[1])[None] * hair_clumps.STEP
    n = len(R)
    t = hcol.strand_tone(look, age.ravel(), np.repeat(lv, age.shape[1]),
                         np.zeros(age.size) if shade is None else np.asarray(shade, float).ravel(),
                         np.repeat(np.maximum(ch, cb * 0.9), age.shape[1]), np.repeat(cm, age.shape[1]), 0.0,
                         np.repeat((St["cls"] == "face").astype(float), age.shape[1]))
    return np.clip(np.asarray(t).reshape(n, -1) / (hair_clumps.TONE_HEAD * hcol.peak(look)), 0, 1)


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
        if c.get("draw", 1.0) < 1.0 and len(mem) > hair_clumps.MIN_STRANDS:
            mem = mem[St["rand"][mem] < c["draw"]] if (St["rand"][mem] < c["draw"]).sum() >= hair_clumps.MIN_STRANDS else mem
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
                if not m_.any() or inside[m_].mean() < hair_clumps.IN_SHARE:
                    continue
            elif not c.get("fly") and inside.mean() < hair_clumps.IN_SHARE:
                continue
            frac = np.nonzero(ok)[0] * hair_clumps.STEP / max(float(St["len"][j]), 1e-6)
            for k_ in range(int(c.get("kids", 1))):  # a groom strand stands for many real hairs: at a fine texel each
                # is drawn as `kids` hairs offset across (filling the gaps a sparse groom leaves), each ending at its own
                # length (the tip a feathered fringe in alpha, not a cut block) with its own tone
                if k_ == 0:
                    segs.append((float(np.median(dp)), ax, al, dp, frac, float(St["rand"][j]), tones[j][ok]))
                    continue
                end = 1.0 - hair_clumps.KID_TIP * rng.random() ** 0.7
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
        if hair_clumps.RIBBON_SHARE > 0 and not c.get("fly") and c.get("cls") in ("head", "tail"):  # highlight RIBBONS (see RIBBON_W)
            nb = max(1, int(np.ceil(2 * hwm / hair_clumps.RIBBON_W)))
            rrng = np.random.default_rng(seed + 7919 + int(c.get("_tile_seed", len(segs))))
            rib = (rrng.random(nb) < hair_clumps.RIBBON_SHARE, rrng.random(nb) * 6.283, nb,
                   hair_clumps.RIBBON_GAIN * float((look or {}).get("highlight_contrast", 0.6)) / 0.6 * (0.5 if c.get("cls") == "tail" else 1.0))
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
            keep = np.abs(dY) >= hair_clumps.SIDEWAYS * np.hypot(dX, dY)
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
            a = a * c.get("alpha_k", 0.45 if fly else hair_clumps.FACE_ALPHA)  # a single hair in the open: soft (alpha-to-coverage / dither keep it a hair, not a wire)
        xx = (np.arange(w) + 0.5) / w
        yy = (np.arange(h)[:, None] + 0.5) / h
        if c.get("edge") and hair_clumps.HL_SOFT > 0:  # a hairline card's roots: sparse, lighter hair the skin shows through
            # (the groom's hairline is +18 L* over the hair behind it, these cards' +1.5: alpha-tested roots drawn at
            # the deep tone were a hard dark rim, hairline.py g1v0 / g1v1). Thin hairs drop under the cutoff, those
            # left are lit (no depth shade) and lighter, as hair over skin at 1 m
            rr = _ss(np.clip((float(c.get("s0", 0.0)) + yy * L) / hair_clumps.HL_SOFT, 0.0, 1.0))  # 0 at the root .. 1 past HL_SOFT
            a = a * (hair_clumps.HL_ALPHA + (1 - hair_clumps.HL_ALPHA) * rr)
            dep = np.maximum(dep, 1.0 - rr * (1.0 - dep))
            tn2 = np.clip(tn2 * (1.0 + hair_clumps.HL_LIFT * (1.0 - rr)), 0, 1)
        if c.get("cls") == "face" and hair_clumps.WISP_LIFT > 0:  # a face-framing wisp hangs in the open over skin: lit, no depth
            # shade, lighter (wispL.py g1v1 at 1 m: groom wisps L* 54 over 2175 px, the cards' 38.6 over 560 px: dark
            # stiff strings in front of the ear, g2_b17 / g3_b18)
            dep = np.ones_like(dep)  # (dep is 1 - depth: 1 = on top, unshaded)
            tn2 = np.clip(tn2 * (1.0 + hair_clumps.WISP_LIFT), 0, 1)
        if c.get("lit"):  # (c10) a flow / hairline-row card on top, in the light: no depth shade, tone x (1 + lit)
            dep = np.ones_like(dep)
            tn2 = np.clip(tn2 * (1.0 + float(c["lit"])), 0, 1)
        if c.get("cls") == "tail" and hair_clumps.TAIL_TONE != 1.0:  # (round 24) the tail cards' tone x this: against gSc (the groom
            # with its own shadow) the tail was +8.9 L* at the back (g1backl) and +3.0 at 3/4 front, the head cards ~+2 / 0
            tn2 = np.clip(tn2 * hair_clumps.TAIL_TONE, 0, 1)
        if hair_clumps.TONE_CONTRAST != 1.0 and not fly and c.get("cls") in ("head", "tail") and (a > 0.15).any():
            m_ = float(np.median(tn2[a > 0.15]))  # (round 25) strand contrast about the island's median
            k_ = hair_clumps.TONE_CONTRAST_TAIL if (c.get("cls") == "tail" and hair_clumps.TONE_CONTRAST_TAIL > 0) else hair_clumps.TONE_CONTRAST
            kd_ = hair_clumps.TONE_CONTRAST_DARK if hair_clumps.TONE_CONTRAST_DARK > 0 else k_
            tn2 = np.clip(m_ + np.where(tn2 > m_, k_, kd_) * (tn2 - m_), 0, 1)
        if hair_clumps.FACE_CONTRAST > 0 and c.get("cls") == "face" and (a > 0.05).any():  # (round 41) a face wisp's hairs spread
            # about their median like the head's: r41w1's denser wisps read as flat pale strips (the groom's: blonde
            # and brown hairs side by side)
            m_ = float(np.median(tn2[a > 0.05]))
            tn2 = np.clip(m_ + hair_clumps.FACE_CONTRAST * (tn2 - m_), 0, 1)
        if c.get("cls") == "tail" and hair_clumps.TAIL_ROOT_LIFT > 0:
            rr_ = 1.0 - _ss(np.clip((float(c.get("s0", 0.0)) + yy * L) / hair_clumps.TAIL_ROOT_LEN, 0.0, 1.0))  # 1 at the root
            dep = np.maximum(dep, rr_ + (1.0 - rr_) * dep)
            tn2 = np.clip(tn2 * (1.0 + hair_clumps.TAIL_ROOT_LIFT * rr_), 0, 1)
        if c.get("cls") == "tail" and hair_clumps.TIP_FADE_TAIL > 0:  # the tail's hairs end one by one under the cutoff
            a = a * (1.0 - _ss(np.clip((yy - (1.0 - hair_clumps.TIP_FADE_TAIL)) / hair_clumps.TIP_FADE_TAIL, 0.0, 1.0)))
        elif c.get("cover") and hair_clumps.COVER_FADE > 0:  # (round 33) the part cover's tips end soft on the side cards
            a = a * (1.0 - _ss(np.clip((yy - (1.0 - hair_clumps.COVER_FADE)) / hair_clumps.COVER_FADE, 0.0, 1.0)))
        if c["layer"] == 0 and c.get("cls") in ("head", "tail"):  # coverage: an opaque core under the strands where they are (no scalp between)
            # (not into the tips: an opaque core to the card's end was a straight cut with a dark band, Tess's tail)
            base = np.clip(ndimage.gaussian_filter(a, 1.5) * 2.2, 0, 1) * 0.92 * (1 - _ss((yy - 0.6) / 0.3)) \
                * _ss((yy * L - hair_clumps.BASE_IN) / 0.008)
            under = a < base
            idm = np.where(under, a * idm + (1 - a) * rng.uniform(0.3, 0.7), idm)
            dep = np.where(under, a * dep + (1 - a) * 0.3, dep)
            a = np.maximum(a, base)
        # the picture fades out at the card's sides and in from its root (no hard card edge, no root line at the part)
        # (over at least a texel and a half: a 6-texel flyaway island kept its full edge column)
        a = a * (_ss((0.5 - np.abs(xx - 0.5)) / max(0.5 * hair_clumps.EDGE_FADE, 1.5 / w)))[None] \
            * _ss(yy / max(hair_clumps.ROOT_FADE / L, 1.5 / h))
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
        n += ((np.abs(ax) <= hwm) & (al >= 0) & (al <= L)).mean() >= hair_clumps.IN_SHARE
    return n / len(mem)


def bake_tiles(cards: list, St: dict, W: int, H: int, n: int = hair_clumps.TILES, ss: int = 2, seed: int = 0,
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
        if cg is not None and hair_clumps.GREY_TILES > 0:  # (grey shares 0..1: x 6 puts .2 apart about as far as 2x the length)
            F = np.concatenate([F, (6.0 * hair_clumps.GREY_TILES * cg[idx])[:, None]], 1)
        lab = kmeans(F, kk, seed=seed) if kk > 1 else np.zeros(len(idx), int)
        for q in np.unique(lab):
            mem = idx[lab == q]
            f = F[lab == q]
            # the medoid among the cards with the most strands (a sparse card's picture would be a sparse tile)
            ns = np.array([len(cards[i]["strands"]) for i in mem])
            ok = ns >= np.percentile(ns, 50)
            d = np.linalg.norm(f - np.median(f, 0), axis=1) + np.where(ok, 0.0, 1e3)
            r = int(mem[int(np.argmin(d))])
            if hair_clumps.TILE_REP_DRAWN > 0:  # (c8) the medoid's picture must DRAW: see TILE_REP_DRAWN
                best, bd = r, -1.0
                for i_ in mem[np.argsort(d)][:hair_clumps.TILE_REP_TRY]:
                    dr_ = _drawn_share(cards[int(i_)], St)
                    if dr_ > bd:
                        best, bd = int(i_), dr_
                    if dr_ >= hair_clumps.TILE_REP_DRAWN:
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
            c["kid_cover"], c["kid_spread"] = hair_clumps.KID_COVER, 2 * hw / ns
        else:  # face wisps and flyaways: at a fine texel one hair is ~0.2 mm at 0.45-0.55 alpha, invisible (c9: "wisps
            # missing", 7-9 MAJOR mentions); a few hairs each, drawn near opaque (the soft alpha was for 1 mm texels)
            c["kid_cover"], c["kid_spread"] = hair_clumps.KID_WISP, max(2 * hw / ns, 0.0006)
            c["alpha_k"], c["kid_max"] = hair_clumps.WISP_ALPHA, (3 if c.get("fly") else hair_clumps.WISP_KIDS_FACE)
        R.append(c)
    if hair_clumps.TILE_TONE_POOL > 0:  # the tile's child hairs wear the tone spread of EVERY strand its cards stand for
        sm = np.array([float(np.nanmean(t)) if np.isfinite(t).any() else np.nan for t in tones])
        for q, r in enumerate(reps):
            if R[q].get("fly") or R[q].get("cls") == "face":
                continue
            pool = np.concatenate([np.asarray(cards[i]["strands"], int) for i in np.nonzero(tile == q)[0]])
            v = sm[pool][np.isfinite(sm[pool])]
            if len(v) < 4:
                continue
            ratio = np.clip(1.0 + hair_clumps.TILE_TONE_POOL * (v / max(float(np.mean(v)), 1e-3) - 1.0), 0.4, 2.5)
            R[q]["tone_ratio"] = ratio
        _rr = [R[q]["tone_ratio"] for q in range(len(R)) if R[q].get("tone_ratio") is not None]
        if _rr:
            _a = np.concatenate(_rr)
            print(f"tile tone pool: {len(_rr)} tiles, ratio p5 / p50 / p95 / p99 = "
                  f"{' / '.join(f'{x:.2f}' for x in np.percentile(_a, [5, 50, 95, 99]))}", flush=True)
    B = bake(R, St, W, H, ss=ss, seed=seed, look=look, C=C, locks=locks, tones=tones, aniso=hair_clumps.TILE_ANISO)
    # tint: a card's strands' mean tone / its tile's
    def mt(c):
        m = np.asarray(c["strands"], int)
        t = tones[m] if len(m) else np.full((1, 1), 0.5)
        return float(np.nanmean(t)) if np.isfinite(t).any() else 0.5
    rt = [max(mt(cards[r]), 1e-3) for r in reps]
    tint = np.array([np.clip(mt(c) / rt[tile[i]], *((0.7, 1.4) if (c.get("fly") or c.get("cls") == "face")
                                                      else hair_clumps.TINT_TOP if (c.get("cls") == "head" and c.get("layer") == 2)
                                                      else hair_clumps.TINT_RANGE)) for i, c in enumerate(cards)])
    if hair_clumps.NAPE_LIFT > 0 and C is not None:  # the nape's head cards out of the depth shade (see NAPE_LIFT)
        R0 = np.asarray(St["root"], float)
        for i, c in enumerate(cards):
            # (tail cards too: b23's dark serrated marks behind the ear are HANGING layer-1 cards, flat passes per
            # range: tris 13668-17114 alone draw them, head cards none; the head-only lift changed nothing)
            short_ = hair_clumps.NAPE_SHORT > 0 and float(c["s"][-1] - c["s"][0]) < hair_clumps.NAPE_SHORT and not c.get("wisp")  # (round 42)
            if (c.get("cls") not in ("head", "tail") and not short_) or not len(c["strands"]):
                continue
            if c.get("cls") == "tail" and c.get("layer") != 1 and not short_:  # only the range the trace named (hanging layer 1):
                continue  # b24 lifted every tail card in the band, 1 m hair L* overshot the groom's (k 0.83-0.89)
            r_ = R0[np.asarray(c["strands"], int)].mean(0) - np.asarray(C, float)
            w_ = _ss(np.clip((-r_[2] - hair_clumps.NAPE_BAND[0]) / (hair_clumps.NAPE_BAND[1] - hair_clumps.NAPE_BAND[0]), 0, 1)) \
                * _ss(np.clip((r_[1] - hair_clumps.NAPE_Y[0]) / (hair_clumps.NAPE_Y[1] - hair_clumps.NAPE_Y[0]), 0, 1))
            tint[i] *= 1.0 + hair_clumps.NAPE_LIFT * float(w_)
    tf_, tb_ = float((look or {}).get("tone_front", hair_clumps.TONE_FRONT)), float((look or {}).get("tone_back", hair_clumps.TONE_BACK))
    # (c10: look tone_front / tone_back override the constants per model: Tess's 0.85 front left Garrett's front -3 L*)
    if (tb_ != 1.0 or tf_ != 1.0) and C is not None:  # (round 26) the head's tone by place (front / back)
        R0 = np.asarray(St["root"], float)
        for i, c in enumerate(cards):
            if c.get("cls") != "head" or c.get("fly") or not len(c["strands"]):
                continue
            r_ = R0[np.asarray(c["strands"], int)].mean(0) - np.asarray(C, float)
            w_ = _ss(np.clip((r_[1] - hair_clumps.TONE_POS_Y[0]) / (hair_clumps.TONE_POS_Y[1] - hair_clumps.TONE_POS_Y[0]), 0, 1))
            tint[i] *= tf_ + (tb_ - tf_) * float(w_)
    if hair_clumps.GREY_TINT > 0 and locks:  # (c1) a card's tone by its locks' grey (the groom's grey by region: Garrett's sides .65,
        # top .22): the tiles are shared, so a grey region's cards came out the head's one dark tone (g1v1 -16 L* p50)
        gk = np.asarray([float((k.get("inputs") or {}).get("Grey", k.get("grey", 0.0)) or 0.0) for k in locks])
        gc = np.asarray([float(gk[np.asarray(St["lock"])[np.asarray(c["strands"], int)]].mean()) if len(c["strands"])
                         else np.nan for c in cards])
        if np.isfinite(gc).any() and np.nanstd(gc) > 1e-3:
            gm = float(np.nanmedian(gc))
            tint = tint * np.clip(1.0 + hair_clumps.GREY_TINT * np.nan_to_num(gc - gm), 0.6, 2.2)
    if cg is not None and hair_clumps.GREY_TILES > 0:  # each tile's grey-hair share: the mean of its cards' (by their strands)
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
