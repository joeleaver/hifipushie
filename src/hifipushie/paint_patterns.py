"""Patterns: spots and tiling images, planar and tile coordinates, weave, grain, stretch, noise, cells. Part of paint (paint.py has the spec)."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from . import paint
from .noise import _hash, fbm
from .spec import SpecError
from .paint import _expanded, _ramp

# ---- spots and tiling images -------------------------------------------------------------------------------------
def resolve_spot(spec: dict, sp: dict, what: str = "spot") -> dict:
    """A spot's points in world space: {"c": (k, 3), "r": (k, 3), "soft", "line"}."""
    from .spec import resolve_point
    exp = _expanded(spec)
    at = sp["at"]
    pts = at if isinstance(at, list) and not (len(at) == 3 and all(isinstance(x, (int, float)) for x in at)) else [at]
    C = []
    for p in pts:
        try:
            if isinstance(p, dict) and "at" in p and set(p) <= {"at", "offset"}:
                C.append(np.asarray(resolve_point(exp, p["at"]), float) + np.asarray(p.get("offset", [0, 0, 0]), float))
            else:
                C.append(np.asarray(resolve_point(exp, p), float))
        except (KeyError, SpecError, ValueError, TypeError) as err:
            raise SpecError(f"{what}: spot point {p!r} isn't a joint, [x, y, z] or {{\"at\": joint, \"offset\"}} ({err})")
    r = sp["radius"]
    if isinstance(r, (int, float)):
        R = np.full((len(C), 3), float(r))
    elif len(r) == 3 and all(isinstance(x, (int, float)) for x in r) and len(C) != 3:
        R = np.tile(np.asarray(r, float), (len(C), 1))
    else:
        if len(r) != len(C):
            raise SpecError(f"{what}: spot radius is one number, [rx, ry, rz], or one per point ({len(C)} points)")
        R = np.array([np.full(3, float(x)) if isinstance(x, (int, float)) else np.asarray(x, float) for x in r])
    if np.any(R <= 0):
        raise SpecError(f"{what}: spot radius must be > 0")
    return {"c": np.array(C), "r": R, "soft": float(np.clip(sp.get("soft", 0.5), 1e-3, 1.0)), "line": bool(sp.get("line"))}


def spot_mask(s: dict, v: np.ndarray) -> np.ndarray:
    out = np.zeros(len(v))
    C, R, soft = s["c"], s["r"], s["soft"]
    if s["line"] and len(C) > 1:
        for a, b, ra, rb in zip(C[:-1], C[1:], R[:-1, 0], R[1:, 0]):
            ba = b - a
            h = np.clip((v - a) @ ba / max(float(ba @ ba), 1e-18), 0, 1)
            d = np.linalg.norm(v - a - h[:, None] * ba, axis=1) / (ra + (rb - ra) * h)
            out = np.maximum(out, _ramp(d, 1.0, 1.0 - soft))
        return out
    for c, r in zip(C, R):
        out = np.maximum(out, _ramp(np.linalg.norm((v - c) / r, axis=1), 1.0, 1.0 - soft))
    return out


def tile_source(t: dict) -> tuple:
    """(path, size m) of a tile's image."""
    from . import skin_swatch
    if "swatch" in t:
        return skin_swatch.make(t["swatch"]), float(t.get("size", skin_swatch.PERIOD[t["swatch"]]))
    return Path(t["file"]), float(t["size"])


def tile_mask(t: dict, v: np.ndarray, n: np.ndarray) -> np.ndarray:
    from . import skin_swatch
    src = t["swatch"] if "swatch" in t else t["file"]
    size = tile_source(t)[1]
    w = np.abs(n) ** 4
    w /= np.maximum(w.sum(1, keepdims=True), 1e-12)

    rot = bool(t.get("rotate"))

    def tri(sz, off):
        return sum(w[:, k] * skin_swatch.sample(src, v[:, [b, a] if rot else [a, b]] / sz + off)
                   for k, (a, b) in enumerate(((1, 2), (0, 2), (0, 1))))
    val = tri(size, 0.0)
    if t.get("vary", True):
        m = _ramp(fbm(v, paint.TILE_VARY[1], 2, int(t.get("seed", 0)) + 17), 0.4, 0.6)
        val = val * (1 - m) + tri(size * paint.TILE_VARY[0], 0.37) * m
    lo, hi = t.get("range", [0.0, 1.0])
    return np.clip((val - lo) / max(hi - lo, 1e-9), 0, 1)


def _planar(fn, v: np.ndarray, n: np.ndarray, d=None, sharp: float = 6.0) -> np.ndarray:
    """A 2D pattern fn(u, w) laid on the three axis planes and blended by how much the normal faces each
    (triplanar): exact on walls and floors, soft where a curved surface turns. u runs along `d` (projected
    into the plane; default horizontal on walls, X on floors), w across it."""
    wts = np.abs(n) ** sharp
    wts /= np.maximum(wts.sum(1, keepdims=True), 1e-12)
    out = np.zeros(len(v))
    for ax in range(3):
        sel = np.flatnonzero(wts[:, ax] > 1e-3)
        if not len(sel):
            continue
        a = paint._AXES[ax]
        dd = np.asarray(d if d is not None else paint._IN_PLANE[ax], float)
        dd = dd - (dd @ a) * a
        if np.linalg.norm(dd) < 0.3:  # the given direction is (nearly) this plane's normal
            dd = np.asarray(paint._IN_PLANE[ax], float)
        dd /= np.linalg.norm(dd)
        e = np.cross(a, dd)
        out[sel] += wts[sel, ax] * fn(v[sel] @ dd, v[sel] @ e)
    return out


def _tiles(u: np.ndarray, w: np.ndarray, t: dict) -> np.ndarray:
    """Running-bond tiles, "size": [along, across] (m), rows shifted by "offset" (0.5; "random"), joints "gap"
    wide. mode "gaps": 1 in the joints, fading over "bevel" (gap / 2); "bevel": 0 at the joint rising to 1
    over "bevel" (a tile's rounded face, for height); "id": a random 0..1 per tile."""
    L, H = (float(x) for x in t.get("size", [0.2, 0.1]))
    gap = float(t.get("gap", 0.005))
    bev = float(t.get("bevel", 0.5 * gap))
    seed = int(t.get("seed", 0))
    row = np.floor(w / H)
    off = t.get("offset", 0.5)
    shift = _hash(row.astype(np.int64), np.zeros_like(row, np.int64), np.zeros_like(row, np.int64), seed + 31) \
        if off == "random" else row * float(off)
    uu = u / L + shift
    col = np.floor(uu)
    fu, fw = uu - col, w / H - row
    dist = np.minimum.reduce([fu * L, (1 - fu) * L, fw * H, (1 - fw) * H])
    mode = t.get("mode", "gaps")
    if mode == "id":
        return _hash(col.astype(np.int64), row.astype(np.int64), np.zeros_like(row, np.int64), seed + 13)
    edge = _ramp(dist, gap / 2, gap / 2 + max(bev, 1e-6))
    return 1 - edge if mode == "gaps" else edge


def _weave(u: np.ndarray, w: np.ndarray, s: float) -> np.ndarray:
    """Plain weave, threads `s` apart: 1 on the crown of the thread on top, 0 in the holes."""
    fu, fw = u / s - np.floor(u / s), w / s - np.floor(w / s)
    over = (np.floor(u / s) + np.floor(w / s)) % 2 == 0
    warp = np.sqrt(np.maximum(np.sin(np.pi * fw), 0)) * (0.55 + 0.45 * np.sin(np.pi * fu))
    weft = np.sqrt(np.maximum(np.sin(np.pi * fu), 0)) * (0.55 + 0.45 * np.sin(np.pi * fw))
    return np.where(over, np.maximum(warp, 0.5 * weft), np.maximum(weft, 0.5 * warp))


def _along(nz: dict) -> bool:
    return (nz.get("stretch") or {}).get("dir") == "element"


def _grain(view) -> tuple:
    """The view's points' element axes (mirrored with the view) and element seeds."""
    g = view.get("grain")
    return (g * paint.MIRROR if view.mirror else g), view.get("grain_seed")


def _stretch(v: np.ndarray, nz: dict, grain: tuple | None = None) -> np.ndarray:
    """Positions squashed along "stretch": {"dir", "factor"}, so features come out `factor` times longer that way.
    dir "element": along each point's own element axis (grain = (axes, seeds)), offset by its element's seed."""
    st = nz.get("stretch")
    if not st:
        return v
    if st.get("dir") == "element":
        g, seed = grain
        g = g / np.linalg.norm(g, axis=1, keepdims=True)  # its length is the end-grain weight
        v = v - (1 - 1 / float(st.get("factor", 6.0))) * (v * g).sum(1)[:, None] * g
        return v + seed[:, None] * paint.GRAIN_OFFSET[None]
    d = np.asarray(st.get("dir", [0, 0, 1]), float)
    d /= np.linalg.norm(d)
    return v - (1 - 1 / float(st.get("factor", 6.0))) * (v @ d)[:, None] * d[None]


def noise(v: np.ndarray, nz: dict, grain: tuple | None = None) -> np.ndarray:
    """A noise generator's raw 0..1 value: fbm, optionally stretched (streaks) and domain-warped (grunge)."""
    scale, octaves, seed = float(nz.get("scale", 0.03)), int(nz.get("octaves", 3)), int(nz.get("seed", 0))
    q = _stretch(v, nz, grain)
    warp = float(nz.get("warp", 0.0))
    if warp:  # displace the lookup by another noise: swirly, torn-looking grunge instead of round blobs
        off = np.stack([fbm(q, scale, 2, seed + 11 + 7 * k) for k in range(3)], 1) - 0.5
        q = q + (2 * warp * scale) * off
    return fbm(q, scale, octaves, seed)


def cells(v: np.ndarray, scale: float, mode: str = "edges", jitter: float = 1.0, seed: int = 0) -> np.ndarray:
    """3D Voronoi on a jittered lattice, `scale` apart: "edges" F2 - F1 (0 on the borders between cells, in
    units of scale), "distance" F1 (0 at each cell's centre), "id" a random 0..1 per cell."""
    q = v / scale
    base = np.floor(q).astype(np.int64)
    f1 = np.full(len(q), np.inf)
    f2 = np.full(len(q), np.inf)
    ident = np.zeros(len(q))
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                c = base + np.array([dx, dy, dz])
                pt = c + 0.5 + jitter * (np.stack([_hash(c[:, 0], c[:, 1], c[:, 2], seed + 17 * k)
                                                   for k in range(3)], 1) - 0.5)
                d = np.linalg.norm(q - pt, axis=1)
                closer = d < f1
                f2 = np.where(closer, f1, np.minimum(f2, d))
                ident = np.where(closer, _hash(c[:, 0], c[:, 1], c[:, 2], seed + 99), ident)
                f1 = np.where(closer, d, f1)
    return {"edges": f2 - f1, "distance": f1, "id": ident}[mode]


def srgb_to_linear(c: np.ndarray) -> np.ndarray:
    c = np.asarray(c, float)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
