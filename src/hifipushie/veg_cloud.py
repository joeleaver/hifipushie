"""Leaf clouds: a style's crown as alpha cards in depth layers on its masses (veg_style crown kind "clouds": anime).

What artists do (sources in vegetation_guide.md "Styles"): Ghibli / Genshin / BotW-style foliage is a rounded proxy per
clump with quads scattered over it in a few depth layers, each quad a painted cluster of leaf dabs with alpha; the
quads' normals are replaced by the proxy's (out of the clump's middle), so a clump shades as one soft volume and the
cards only cut its edge into leaves; colour is a painted gradient per clump (dark base, mid, sunlit top).
Here the proxy is the style's masses (veg_style.masses: the same clusters the blobby crown is made of)."""

from __future__ import annotations

import json
import math

import numpy as np

from . import veg_leaf, vegetation

_DABS: dict = {}
DAB = {"variants": 4, "size": 256, "count": 34, "length": 0.42, "width": 0.5, "shape": "leaf", "ragged": 0.35, "core": 0.5,
       "tone": [0.84, 1.0], "droop": 0.0, "verts": 6, "out": 0.6}


def dab_atlas(spec: dict, st: dict, season: str | None = None) -> dict:
    """The painted picture a leaf cloud's cards carry: per variant a cluster of brush DABS (the species' leaf outline,
    fattened, `count` of them `length` x the tile long, pointing out of the cluster's middle by `out` and down by
    `droop`, a solid middle of `core` x the tile, a ragged rim), as a grey TONE (`tone` [dark, light] per dab: the
    material's colour and the clump's gradient multiply it) + alpha. {"color" (h, w, 4) uint8, "cards": per variant
    {"P" (n, 2) polygon corners in -1..1 round the alpha (first = its middle), "F", "uv"}, "fill" = the alpha's share
    of the polygons (overdraw's other side)}. No lighting, no season: seasons change the material's colour only."""
    from PIL import Image, ImageDraw
    from scipy.spatial import ConvexHull
    lf = spec["leaves"]
    d = {**DAB, **((st.get("crown") or {}).get("dab") or {})}
    shape = str(lf.get("shape", "ovate"))
    season = season or spec.get("season", "summer")
    # spring's new growth: the tip of every stroke lighter and fresher (`seasons.spring.tips`: {"share" of the stroke,
    # "light" its tone x, "tint" rgb x, "body" the rest's tone x}); the alpha (and so the cards) is the same
    tips = ((st.get("seasons") or {}).get("spring") or {}).get("tips") if season == "spring" else None
    key = json.dumps([d, shape, lf.get("lobes", 4), int(spec.get("seed", 1)), tips], sort_keys=True)
    if key in _DABS:
        return _DABS[key]
    nv, n, ss = int(d["variants"]), int(d["size"]), 3
    cols = int(math.ceil(math.sqrt(nv)))
    rows = int(math.ceil(nv / cols))
    A = np.zeros((rows * n, cols * n, 4), np.uint8)
    A[..., :3] = int(255 * float(np.mean(d["tone"])))
    cards, fills = [], []
    t = np.linspace(0, 1, 14)
    if d["shape"] == "spray" or (d["shape"] == "leaf" and shape.startswith("needle")):
        prof = (0.16 + 0.1 * np.sin(np.pi * t)) * np.minimum((1 - t) / 0.35, 1.0) ** 0.7 * np.minimum(t / 0.1, 1.0)  # a needle spray: a long thin stroke, pointed
    elif d["shape"] == "blade":
        prof = 0.1 * np.minimum(t / 0.05, 1.0) * np.minimum((1 - t) / 0.5, 1.0) ** 0.7
    else:
        prof = veg_leaf._profile(shape if shape in ("ovate", "triangular", "lanceolate", "lobed", "round") else "ovate", t, int(lf.get("lobes", 4)))
        prof = np.maximum(prof, 0.55 * np.sin(np.pi * t) ** 0.6)  # (fattened: a dab, not a botanical leaf)
    for v in range(nv):
        u = lambda i, salt: float(vegetation._u(np.array([i + 1000 * v + 100000 * int(spec.get("seed", 1))], np.uint64), salt)[0])
        N = n * ss
        col = Image.new("RGB", (N, N), (int(255 * float(np.mean(d["tone"]))),) * 3)
        alp = Image.new("L", (N, N), 0)
        dc, da = ImageDraw.Draw(col), ImageDraw.Draw(alp)
        px = lambda q: [((x * 0.5 + 0.5) * N, (0.5 - y * 0.5) * N) for x, y in q]
        cr = float(d["core"])
        if cr > 0:
            da.ellipse([N * (0.5 - 0.5 * cr), N * (0.5 - 0.5 * cr), N * (0.5 + 0.5 * cr), N * (0.5 + 0.5 * cr)], fill=255)
        cnt = int(d["count"])
        rr = np.array([u(i, 1) for i in range(cnt)]) ** 0.55
        for i in np.argsort(-rr):  # the rim first, the middle painted over it
            L = float(d["length"]) * (0.7 + 0.6 * u(i, 2))
            reach = max(0.92 - 0.55 * L, 0.2)
            a0 = 2 * math.pi * u(i, 3)
            r0 = rr[i] * reach * (1 - float(d["ragged"]) * u(i, 4) * rr[i])
            c = np.array([r0 * math.cos(a0), r0 * math.sin(a0)])
            dirn = float(d["out"]) * np.array([math.cos(a0), math.sin(a0)]) + float(d["droop"]) * np.array([0, -1.0]) + 0.5 * np.array([u(i, 5) - 0.5, u(i, 6) - 0.5])
            dirn = dirn / max(float(np.linalg.norm(dirn)), 1e-6)
            side = np.array([-dirn[1], dirn[0]])
            hw = 0.5 * float(d["width"]) * L * prof
            mid = c[None] + (t[:, None] - 0.5) * L * dirn[None]
            poly = np.vstack([mid + hw[:, None] * side[None], (mid - hw[:, None] * side[None])[::-1]])
            tone = d["tone"][0] + (d["tone"][1] - d["tone"][0]) * u(i, 7)
            da.polygon(px(poly), fill=255)
            if tips:
                tone_b = tone * float(tips.get("body", 0.85))
                dc.polygon(px(poly), fill=(int(255 * tone_b),) * 3)
                k0 = int(len(t) * (1 - float(tips.get("share", 0.3))))
                tp = np.vstack([(mid + hw[:, None] * side[None])[k0:], (mid - hw[:, None] * side[None])[k0:][::-1]])
                tl = min(tone * float(tips.get("light", 1.0)), 1.0)
                dc.polygon(px(tp), fill=tuple(int(255 * min(tl * float(c_), 1.0)) for c_ in tips.get("tint", [1.0, 1.0, 0.6])))
            else:
                dc.polygon(px(poly), fill=(int(255 * tone),) * 3)
        col = np.asarray(col.resize((n, n), Image.LANCZOS))
        alp = np.asarray(alp.resize((n, n), Image.LANCZOS))
        r_, c_ = divmod(v, cols)
        A[r_ * n: (r_ + 1) * n, c_ * n: (c_ + 1) * n, :3] = col
        A[r_ * n: (r_ + 1) * n, c_ * n: (c_ + 1) * n, 3] = alp
        ys, xs = np.nonzero(alp > 100)
        pts = np.c_[np.r_[xs, xs + 1, xs, xs + 1], np.r_[ys, ys, ys + 1, ys + 1]].astype(float)
        poly = np.clip(veg_leaf._enclose(pts[ConvexHull(pts).vertices], int(d["verts"])), 0, n)
        P = np.c_[poly[:, 0] / n * 2 - 1, 1 - poly[:, 1] / n * 2]
        if P[:, 0] @ np.roll(P[:, 1], -1) - P[:, 1] @ np.roll(P[:, 0], -1) < 0:
            P = P[::-1]
        area = 0.5 * abs(float(P[:, 0] @ np.roll(P[:, 1], -1) - P[:, 1] @ np.roll(P[:, 0], -1)))
        P = np.vstack([P.mean(0), P])
        k = len(P) - 1
        F = np.array([[0, 1 + i, 1 + (i + 1) % k] for i in range(k)])
        uv = np.c_[(c_ + (P[:, 0] * 0.5 + 0.5)) / cols, 1 - (r_ + (0.5 - P[:, 1] * 0.5)) / rows]
        fills.append(float((alp > 127).mean() * 4.0 / max(area, 1e-6)))
        cards.append({"P": P, "F": F, "uv": uv, "area": area})
    out = {"color": A, "cards": cards, "fill": float(np.mean(fills)), "triangles": int(max(len(c["F"]) for c in cards))}
    if len(_DABS) > 8:
        _DABS.clear()
    _DABS[key] = out
    return out


def _fib(n: int) -> np.ndarray:
    i = np.arange(n) + 0.5
    z = 1 - 2 * i / n
    a = i * math.pi * (3 - math.sqrt(5))
    r = np.sqrt(np.maximum(1 - z * z, 0))
    return np.c_[r * np.cos(a), r * np.sin(a), z]


def clouds(tree: dict, st: dict, ells: list, foliage_triangles: int, lod: float = 1.0, floor: float = 0.05) -> dict | None:
    """Leaf clouds: every mass dressed in `layers` shells of alpha cards. A card stands on its shell (the mass's
    ellipsoid x the layer's share), faces out of the mass tilted by up to `tilt` deg, is `card` x the mass's mean
    radius across (x up to `lod_grow` at lower LODs, where there are fewer), cupped back toward the mass, and carries a
    dab cluster from the atlas. Cards more than `bury` x its radius inside ANOTHER mass are left out. How many: what
    the triangle count buys, shared between masses by their area and between layers by `layer_weight` (a lower LOD
    takes the same cards' first share, the outer layers first). lod = this LOD's share of the full budget.
    Per vertex: NORMAL out of its clump's middle (mixed `normals` toward out of the crown's middle), uv in the atlas,
    "grad" = (height in its clump 0 base .. 1 top, (clump + 0.5) / clumps), "col" = the clump's painted gradient
    (`tone` per step, warmer above / cooler below by `warm_top`; inner layers darker by `depth_dark`), one step per
    CARD (a dab of paint), "rim" = 0 at a card's middle .. 1 at its corners (wind flutter)."""
    cr = st["crown"]
    spec = tree["spec"]
    at = dab_atlas(spec, st, spec.get("season", "summer"))
    ells = [e for e in ells if not e.get("core")]
    if not ells:
        return None
    tri = at["triangles"]
    layers = [float(x) for x in cr.get("layers", [0.55, 0.7, 0.85, 1.0])]
    lw = np.array(([float(x) for x in cr.get("layer_weight", [1.0])] * len(layers))[: len(layers)])
    if lod < 0.6:  # lower LODs: the outer layers carry it
        lw = lw * np.linspace(max(0.0, 2 * lod - 0.3), 1.0, len(layers))
    # overdraw at a distance (the game, note 84): `lod_layers` = [layers kept under lod 0.6, under 0.3] (the OUTER ones:
    # what is inside an outer shell of cards is mostly hidden but still drawn); `lod_area` = the exponent of the cards'
    # growth (0.5: fewer, larger cards cover what all of them did, i.e. as many pixels drawn; less = fewer pixels)
    kl = cr.get("lod_layers")
    if kl:
        n_keep = int(kl[0]) if lod < 0.6 else len(layers)
        n_keep = int(kl[1]) if lod < 0.3 and len(kl) > 1 else n_keep
        lw = lw.copy()
        lw[: max(len(layers) - n_keep, 0)] = 0.0
    n_cards = max(int(foliage_triangles // tri), 4 * len(ells))
    grow = float(np.clip(max(lod, 1e-3) ** -float(cr.get("lod_area", 0.5)), 1.0, float(cr.get("lod_grow", 1.9))))
    seed = int(spec.get("seed", 1))
    size = np.array([float(e["r"].mean()) for e in ells])
    area = size ** 2
    cz = np.array([e["c"][2] for e in ells])
    ez = np.array([math.sqrt(float(((e["R"][:, 2] * e["r"]) ** 2).sum())) for e in ells])
    ed = np.array([e["down"] if e.get("down") is not None else ez[j] for j, e in enumerate(ells)])
    cen = np.mean([e["c"] for e in ells], axis=0)
    share = area[:, None] * (lw * np.array(layers) ** 2)[None]
    share = share / share.sum()
    least = float(cr.get("clump_min_cards", 0)) * min(1.0, lod * 2) / max(n_cards, 1)  # (a small clump of three cards was confetti)
    short = share.sum(1) < least
    share[short] *= (least / np.maximum(share[short].sum(1), 1e-9))[:, None]
    if short.any() and (~short).any():  # traded within the budget: the big clumps give up what the small ones were raised by
        rest = 1.0 - float(share[short].sum())
        share[~short] *= max(rest, 0.0) / max(float(share[~short].sum()), 1e-9)
    share = share / max(float(share.sum()), 1e-9)
    under = float(cr.get("under", 1.0))  # tiers: what faces the ground under a bough is left open (its shadow, the trunk)
    cp, cn, cm, cl, ch = [], [], [], [], []
    for j, e in enumerate(ells):
        for li, s_ in enumerate(layers):
            want = share[j, li] * n_cards
            if want < 0.5:
                continue
            m_ = int(math.ceil(want * 2.2)) + 6
            ph = 2 * math.pi * float(vegetation._u(np.array([j * 16 + li + 1000 * seed], np.uint64), 21)[0])
            U = _fib(m_) @ np.array([[math.cos(ph), -math.sin(ph), 0], [math.sin(ph), math.cos(ph), 0], [0, 0, 1.0]]).T
            r_ = np.tile(e["r"], (m_, 1))
            if e.get("down") is not None:
                r_[U[:, 2] < 0, 2] = e["down"]
            nn = U / r_
            nn /= np.maximum(np.linalg.norm(nn, axis=1, keepdims=True), 1e-9)
            p = e["c"] + (s_ * r_ * U) @ e["R"]
            nw = nn @ e["R"]
            keep = p[:, 2] > floor + 0.2
            if under < 1.0:
                keep &= nw[:, 2] > -under
            for k2, e2 in enumerate(ells):  # buried in another mass
                if k2 == j:
                    continue
                q2 = (p - e2["c"]) @ e2["R"].T
                r2 = np.tile(e2["r"], (m_, 1))
                if e2.get("down") is not None:
                    r2[q2[:, 2] < 0, 2] = e2["down"]
                keep &= np.linalg.norm(q2 / r2, axis=1) > 1 - float(cr.get("bury", 0.3))
            idx = np.flatnonzero(keep)
            hk = (idx + 4096 * (j * 16 + li) + 1000003 * seed).astype(np.uint64)
            o_ = np.argsort(vegetation._u(hk, 22))[: max(int(round(want)), 1 if li == len(layers) - 1 else 0)]
            cp.append(p[idx[o_]]); cn.append(nw[idx[o_]]); ch.append(hk[o_])
            cm.append(np.full(len(o_), j)); cl.append(np.full(len(o_), li))
    P0, N0 = np.vstack(cp), np.vstack(cn)
    M, Lr, Hk = np.concatenate(cm), np.concatenate(cl), np.concatenate(ch)
    nc = len(P0)
    u = lambda salt: vegetation._u(Hk, salt)
    # the card's frame: out of the shell, tilted; its picture's up = world up (the dabs' droop hangs), rolled a little
    tilt = math.radians(float(cr.get("tilt", 25.0)))
    rnd = np.c_[u(31) - 0.5, u(32) - 0.5, u(33) - 0.5] * 2
    nrm = N0 + math.tan(tilt) * rnd * u(34)[:, None]
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)
    B = np.array([0, 0, 1.0])[None] - nrm * nrm[:, 2:3]
    flat = np.linalg.norm(B, axis=1) < 0.2
    B[flat] = np.array([1.0, 0, 0])[None] - nrm[flat] * nrm[flat, 0:1]
    B /= np.maximum(np.linalg.norm(B, axis=1, keepdims=True), 1e-9)
    T = np.cross(B, nrm)
    roll = math.radians(float(cr.get("roll", 30.0))) * (u(35) - 0.5) * 2
    roll = np.where(flat, 2 * math.pi * u(35), roll)
    T, B = T * np.cos(roll)[:, None] + B * np.sin(roll)[:, None], B * np.cos(roll)[:, None] - T * np.sin(roll)[:, None]
    half = float(cr.get("card", 0.45)) * size[M] * (0.8 + 0.4 * u(36)) * grow
    half = np.minimum(half, float(cr.get("card_max", 1e9)) * grow)
    # never taller than the tree: a card on an outer shell over the top clump stood a metre over it (the same
    # individual's height). Cards whose top would pass it sit down by the difference.
    ztop = float(tree["height"]) * 1.01
    P0 = P0.copy()
    P0[:, 2] -= np.maximum(P0[:, 2] + half * np.abs(B[:, 2]) - ztop, 0.0)
    var = (u(37) * len(at["cards"])).astype(int) % len(at["cards"])
    cup = float(cr.get("cup", 0.25))
    Vs, Fs, UVs, own, rim, n0 = [], [], [], [], [], 0
    for v in range(len(at["cards"])):
        sel = np.flatnonzero(var == v)
        if not len(sel):
            continue
        c_ = at["cards"][v]
        Pc = c_["P"]
        k = len(Pc)
        rr = np.linalg.norm(Pc, axis=1)
        V = (P0[sel, None, :] + half[sel, None, None] * (Pc[None, :, 0:1] * T[sel, None, :] + Pc[None, :, 1:2] * B[sel, None, :]
                                                         - cup * (rr ** 2)[None, :, None] * nrm[sel, None, :]))
        Vs.append(V.reshape(-1, 3))
        Fs.append((c_["F"][None] + (np.arange(len(sel)) * k)[:, None, None] + n0).reshape(-1, 3))
        UVs.append(np.tile(c_["uv"], (len(sel), 1)))
        own.append(np.repeat(sel, k))
        r0 = np.linalg.norm(Pc - Pc[0], axis=1)  # (from the polygon's own middle vertex: that one stays still)
        rim.append(np.tile(np.clip(r0 / max(float(r0.max()), 1e-6), 0, 1), len(sel)))
        n0 += len(sel) * k
    V, F, UV, own, rim = np.vstack(Vs), np.vstack(Fs), np.vstack(UVs), np.concatenate(own), np.concatenate(rim)
    V[:, 2] = np.maximum(V[:, 2], floor)
    mv = M[own]
    o1 = V - np.array([e["c"] for e in ells])[mv]
    o1 /= np.maximum(np.linalg.norm(o1, axis=1, keepdims=True), 1e-9)
    o2 = V - cen
    o2 /= np.maximum(np.linalg.norm(o2, axis=1, keepdims=True), 1e-9)
    wN = float(cr.get("normals", 0.2))
    Nv = (1 - wN) * o1 + wN * o2
    Nv /= np.maximum(np.linalg.norm(Nv, axis=1, keepdims=True), 1e-9)
    g = np.clip((V[:, 2] - (cz[mv] - ed[mv])) / (ez[mv] + ed[mv]), 0, 1)
    # the painted gradient: one step per card, by where the card sits in its clump; inner layers darker
    gc = np.clip((P0[:, 2] - (cz[M] - ed[M])) / (ez[M] + ed[M]), 0, 1)
    gc = gc + float(cr.get("grad_jitter", 0.12)) * (u(38) - 0.5) - float(cr.get("depth_dark", 0.35)) * (1 - np.array(layers)[Lr]) / max(1 - min(layers), 1e-6)
    tone = [float(x) for x in cr.get("tone", [0.6, 0.9, 1.25])]
    steps = len(tone)
    lo_, hi_ = cr.get("grad_range", [0.25, 0.7])
    si = np.clip(((gc - lo_) / max(hi_ - lo_, 1e-6) * (steps - 1) + 0.5).astype(int), 0, steps - 1)
    tf = si / max(steps - 1, 1)
    warm = float(cr.get("warm_top", 0.0))
    tn = np.array(tone)[si]
    ccol = np.stack([tn * (1 + warm * (tf - 0.5) * 2), tn, tn * (1 - warm * (tf - 0.5) * 2)], 1)
    gain = float(max(tone) * (1 + abs(warm)))
    return {"V": V, "F": F, "N": Nv, "uv": UV, "col": (ccol / gain)[own], "gain": gain, "mass": mv, "grad": np.c_[g, (mv + 0.5) / len(ells)],
            "rim": rim, "layer": Lr[own], "cards": nc, "atlas": at, "step": si[own], "card_of": own, "card_m": float(np.mean(2 * half)),
            "clumps": len(ells)}
