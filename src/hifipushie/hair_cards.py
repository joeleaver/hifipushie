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
    return {**STRANDS, **s}


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

def _tile(kind: str, w: int, H: int, S: dict, rng, ss: int = 3) -> dict:
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
    thick = k["thick"] * ss * w / 160 * 1.0 if kind in ("fly", "baby") else k["thick"] * ss
    for i in np.argsort(depth):
        v = v0[i] + t * (L[i] - v0[i])
        x = x0[i] + (xt[i] - x0[i]) * cl * _ss(v / 0.75)
        env = _ss(v / 0.12)
        x = x + fz * 0.03 * (np.sin(2 * np.pi * (1.3 * v + ph[i, 0])) + 0.6 * np.sin(2 * np.pi * (3.1 * v + ph[i, 1]))) * env
        x = x + tw * np.sin(2 * np.pi * (v * fw + cph[i])) * env
        x = np.clip(x, 0.025, 0.975)
        pts = list(zip((x * W2).tolist(), (v * H2).tolist()))
        cut = int(len(pts) * 0.82)
        for seg, wd in ((pts[:cut + 1], max(1, int(round(thick)))), (pts[cut:], max(1, int(round(thick * 0.5))))):
            da.line(seg, fill=255, width=wd)
            di.line(seg, fill=int(1 + 254 * ident[i]), width=wd)
            dd.line(seg, fill=int(1 + 254 * depth[i]), width=wd)
    a, idm, dep = (np.asarray(i.resize((w, H), Image.BOX), np.float32) / 255 for i in ims)
    cov = np.maximum(a, 1e-3)
    idm, dep = np.clip(idm / cov, 0, 1), np.clip(dep / cov, 0, 1)
    if kind in ("fly", "baby"):
        a = a * 0.85
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
    solid = a > 0.03
    if solid.any():  # values carried past the alpha's edge (no dark fringe under filtering)
        ix = ndimage.distance_transform_edt(~solid, return_distances=False, return_indices=True)
        idm, dep = idm[ix[0], ix[1]], dep[ix[0], ix[1]]
    return {"alpha": a, "id": idm, "depth": dep}


def atlas(S: dict, look: dict) -> dict:
    """The strand atlas: {"color" (H, W, 4) sRGB floats, straight alpha; "normal" (H, W, 3); "aux" (H, W, 4): root
    gradient, strand id, depth, alpha; "tiles": [{"kind", "u0", "u1"}] (v runs the whole height: 0 = the root, at the
    top of the picture)}. Colour = the look's gap colour deep down to its lit colour on top, a value per strand."""
    key = hashlib.sha1(json.dumps([{k: S[k] for k in ("clump", "frizz", "curl", "tips", "atlas")},
                                   {k: look.get(k) for k in ("gap", "lit", "vary", "band")}], sort_keys=True).encode()).hexdigest()
    if key in _ATLAS:
        return _ATLAS[key]
    from scipy import ndimage
    size = int(S["atlas"])
    H = size
    rng = np.random.default_rng(11)
    cols, tiles, x = [], [], 0
    for kind, w0 in TILES:
        w = int(round(w0 * size / 1024))
        cols.append(_tile(kind, w, H, S, rng))
        tiles.append({"kind": kind, "u0": (x + 2.0) / size, "u1": (x + w - 2.0) / size})
        x += w
    a, idm, dep = (np.concatenate([c[k] for c in cols], 1) for k in ("alpha", "id", "depth"))
    gap, lit = _lin(look.get("gap", "#221310")), _lin(look.get("lit", "#56352d"))
    shade = (0.25 + 0.75 * dep ** 0.8)[..., None]
    val = (1 + float(look.get("vary", 0.25)) * 1.6 * (idm - 0.5))[..., None]
    col = _srgb((gap[None, None] * (1 - shade) + lit[None, None] * shade) * val)
    x = 0
    for c in cols:  # the tie's own colour
        w = c["alpha"].shape[1]
        if c.get("band"):
            col[:, x:x + w] = np.array([int(look.get("band", "#23252b").lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)])
        x += w
    hgt = ndimage.gaussian_filter(dep * (a > 0.1), 0.8)
    gx, gy = np.gradient(hgt, axis=1) * 2.2, np.gradient(hgt, axis=0) * 0.6
    nrm = _unit(np.stack([-gx, gy, np.ones_like(gx)], -1)) * 0.5 + 0.5
    root = np.repeat(1 - (np.arange(H)[:, None] + 0.5) / H, a.shape[1], 1)
    out = {"color": np.concatenate([col, a[..., None]], -1).astype(np.float32), "normal": nrm.astype(np.float32),
           "aux": np.stack([root, idm, dep, a], -1).astype(np.float32), "tiles": tiles, "size": size,
           "coverage": {t["kind"]: round(float(c["alpha"].mean()), 2) for t, c in zip(tiles, cols)}}
    if len(_ATLAS) > 6:
        _ATLAS.pop(next(iter(_ATLAS)))
    _ATLAS[key] = out
    return out


def write_atlas(at: dict, stem: str) -> dict:
    """<stem>_color.png (RGBA), _normal.png, _aux.png (root, id, depth, alpha)."""
    from PIL import Image
    out = {}
    for k in ("color", "normal", "aux"):
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
                    "cval": 1 + R * rng.uniform(-0.28, 0.28),
                    "layer": layer, "bend": _unit(P[sel] - (cen[sel] if len(cen) > 1 else cen[0])), "T": T[sel]})

    edge = bool(lk.get("at_hairline"))
    for la in range(L):
        kind = ("hairline" if edge else "dense") if la == 0 else ("medium" if la == 1 else "sparse")
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
    for k in ("hw", "u"):
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
    V, F, UV, Nn, Tn, COL, AL, LAY, CID = [], [], [], [], [], [], [], [], []
    off = 0
    rootd, rootl = 0.62, float(look.get("root", 0.12))
    tip_amt = float(look.get("tip_amount", 0.0))
    rnd = float(S["round"])
    lam = max(float(S["wavelength"]), 0.01)
    for ci, c in enumerate(cards):
        length = float(c["s"][-1] - c["s"][0])
        per = seg if float(S["wave"]) <= 0 else min(seg, lam / 6)
        m = int(np.clip(np.ceil(length / max(per, 1e-4)), 2, 200)) + 1
        c = _resample(c, m)
        t = tiles[by[c["kind"]][int(rng.integers(len(by[c["kind"]])))]]
        ua, ub = (t["u0"], t["u1"]) if rng.random() < 0.5 else (t["u1"], t["u0"])
        vv = (c["s"] - c["s"][0]) / max(length, 1e-9)
        left, right = c["P"] - c["X"] * c["hw"][:, None], c["P"] + c["X"] * c["hw"][:, None]
        V.append(np.stack([left, right], 1).reshape(-1, 3))
        UV.append(np.stack([np.stack([np.full(m, ua), 1 - vv], 1), np.stack([np.full(m, ub), 1 - vv], 1)], 1).reshape(-1, 2))
        nb = c["N"] * np.where((c["N"] * c["bend"]).sum(-1, keepdims=True) < 0, -1.0, 1.0)
        nb = _unit((1 - rnd) * nb + rnd * c["bend"])
        Nn.append(np.repeat(nb, 2, 0))
        Tn.append(np.repeat(c["T"], 2, 0))
        ramp = rootd + (1 - rootd) * _ss(c["u"] / max(rootl, 1e-3))
        ramp = ramp * (1 + tip_amt * 0.35 * _ss((c["u"] - 0.55) / 0.45))
        lay = 0.6 + 0.4 * min(c["layer"], 2) / 2
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
                "card": np.zeros(0, np.int32)}
    return {"verts": np.concatenate(V).astype(np.float32), "tris": np.concatenate(F).astype(np.int32),
            "uv": np.concatenate(UV).astype(np.float32), "normal": np.concatenate(Nn).astype(np.float32),
            "tangent": np.concatenate(Tn).astype(np.float32), "col": np.concatenate(COL).astype(np.float32),
            "along": np.concatenate(AL).astype(np.float32), "layer": np.concatenate(LAY),
            "card": np.concatenate(CID)}


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


def triangles(cards: list, S: dict, segment: float | None = None) -> int:
    seg = float(segment or S["segment"])
    lam = max(float(S["wavelength"]), 0.01)
    per = seg if float(S["wave"]) <= 0 else min(seg, lam / 6)
    return int(sum(2 * int(np.clip(np.ceil(float(c["s"][-1] - c["s"][0]) / per), 2, 200)) for c in cards))


def fit_budget(cards: list, S: dict, budget: int) -> tuple[list, float, dict]:
    """Cards and a segment length for a triangle budget: segments lengthen first (to 3 cm, or a sixth of the wave),
    then fly-aways go, then the top layers. Returns (cards, segment, what was dropped)."""
    info = {"asked": int(budget)}
    seg = float(S["segment"])
    keep = list(cards)
    for step in range(40):
        n = triangles(keep, S, seg)
        if n <= budget:
            break
        if seg < 0.03:
            seg = min(0.03, seg * max(1.08, min(n / budget, 2.0)))
            continue
        top = max((c["layer"] for c in keep), default=0)
        if top == 0:
            break
        keep = [c for c in keep if c["layer"] < top]
        info.setdefault("dropped_layers", []).append(int(top))
    info["triangles"], info["segment"] = triangles(keep, S, seg), round(seg, 4)
    return keep, seg, info


def join(*meshes) -> dict:
    """Card meshes joined into one."""
    ms = [m for m in meshes if m is not None and len(m["verts"])]
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
