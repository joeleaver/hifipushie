"""Textures: cracks, micro relief, paint, raster normals, and `bake_variant`. Part of clutter (clutter.py has the overview)."""
from __future__ import annotations

import math

import numpy as np

from . import clutter
from . import noise
from .clutter_mesh import _chart_axes, _chart_rect, _smooth_normal, _tangents
from .clutter_solid import Solid, _cells, _grad

# ---------------------------------------------------------------------------------------------------------- the bake
def _cracks(p, q, seed):
    """0..1: fracture traces. A crack is where a wandering PLANE meets the surface (a joint's trace: a line that runs
    on across faces and stops), a handful per stone, each present along stretches. Isolines of a noise drew closed
    loops: worm doodles."""
    rng = np.random.default_rng(seed + 2)
    size = p["crack_size"]
    out = np.zeros(len(q))
    for i in range(6):
        n = rng.normal(0, 1, 3)
        n /= np.linalg.norm(n)
        off = rng.uniform(-0.28, 0.28)
        w = rng.uniform(0.0025, 0.006)
        x = q @ n - off + 0.035 * size / 0.3 * (noise.fbm(q, 0.5 * size, 2, seed + 30 + i) - 0.5) * 2
        on = np.clip((noise.fbm(q + 7.1 * i, 1.2 * size, 1, seed + 40 + i) - 0.45) / 0.08, 0, 1)
        out = np.maximum(out, np.clip(1 - np.abs(x) / w, 0, 1) * on * rng.uniform(0.5, 1.0))
    return out


def _micro(cfg, I, P, seed):
    """Bake-only relief (m, + = out of the rock): grain, cracks, laminae along the bedding, grooves along wood."""
    p = cfg["paint"]
    q = I["q"]
    h = np.zeros(len(P))
    if p.get("grain"):
        h += p["grain"] * (noise.fbm(q, p["grain_size"], 2, seed + 1) - 0.5) * 2
    if p.get("cracks"):
        h -= p["cracks"] * _cracks(p, q, seed)
    if p.get("laminae"):
        zb = I["bed"] + 0.004 * noise.fbm(q, 0.15, 2, seed + 4)
        t = np.abs(((zb / p["lamina"]) % 1.0) - 0.5) * 2
        h -= p["laminae"] * np.clip(1 - t / 0.25, 0, 1) * (noise.fbm(q, 0.2, 1, seed + 5) > 0.4)
    if p.get("pits"):
        r = noise.fbm(q, 0.03, 2, seed + 6)
        h -= p["pits"] * np.clip((r - 0.62) / 0.1, 0, 1)
    if p.get("leaf_bump") and p.get("leaf_size"):
        f1, _, _ = _cells(q, p["leaf_size"], seed + 31)
        h += p["leaf_bump"] * np.clip(1 - f1 / (0.6 * p["leaf_size"]), 0, 1)
    if p.get("bark") and I.get("axis") is not None:
        ax_ = I["axis"]
        al_ = (q * ax_).sum(1, keepdims=True)
        bq = (q - ax_ * al_) / (0.4 * p["bark_size"]) + ax_ * al_ / p["bark_size"]
        h += 0.004 * np.clip((noise.fbm(bq, 1.0, 2, seed + 51) - (0.62 - 0.3 * p["bark"])) / 0.05, 0, 1)
    if p.get("grooves") and I.get("axis") is not None:
        ax = I["axis"]
        perp = q - ax * (q * ax).sum(1, keepdims=True)
        st = perp / p["groove_size"] + ax * (q * ax).sum(1, keepdims=True) / (p["groove_size"] * 30)
        h += p["grooves"] * (noise.fbm(st, 1.0, 2, seed + 7) - 0.5) * 2
    return h


def _paint(cfg, solid, P, Nrm, I, curv, ao, zrel, seed, zg=None, season=None, variant=0):
    """Albedo (sRGB) and roughness at surface points."""
    p = cfg["paint"]
    q = I["q"]
    tone = 1.0 + p["tone"] * (noise.fbm(q, p["tone_size"], 3, seed + 11) - 0.5) * 2
    tone = tone * (1 + p.get("face_tone", 0) * I["tone"])
    if p.get("speckle"):
        tone = tone * (1 + p["speckle"] * ((noise.fbm(q, 0.012, 2, seed + 12) - 0.5) * 2 + (noise.fbm(q, 0.05, 2, seed + 22) - 0.5) * 2))
    if p.get("streak") and I.get("axis") is not None:
        ax = I["axis"]
        al = (q * ax).sum(1, keepdims=True)
        st = (q - ax * al) / p["streak_size"][1] + ax * al / p["streak_size"][0]
        tone = tone * (1 + p["streak"] * (noise.fbm(st, 1.0, 3, seed + 13) - 0.5) * 2)
    if p.get("bands"):
        zb = I["bed"] + 0.01 * (noise.fbm(q, 0.3, 2, seed + 14) - 0.5)
        lo, hi = p["band_thick"]
        # bands of wandering thickness: a warped coordinate cut into unit cells, each cell one of the tones
        wz = zb / (0.5 * (lo + hi)) + 0.8 * (noise.fbm(np.c_[zb, zb * 0, zb * 0] + 3.1, hi * 2.0, 1, seed + 15) - 0.5) * (hi - lo) / (lo + hi) * 4
        cell = np.floor(wz).astype(np.int64)
        tn = np.asarray(p["band_tones"], float)
        pick = tn[(noise._hash(cell, cell * 0 + 5, cell * 0 + 9, seed + 16) * len(tn)).astype(int) % len(tn)]
        tone = tone * (1 + p["bands"] * pick)
    if p.get("cracks"):
        tone = tone * (1 - min(0.6, p["cavity"] * 1.6) * np.clip(_cracks(p, q, seed), 0, 1))
    flower = None
    if p.get("leaf_size"):
        f1, f2, cid = _cells(q, p["leaf_size"], seed + 31)
        tone = tone * (1 + p["leaf_tone"] * (cid - 0.5) * 2)
        gap = np.clip(1 - (f2 - f1) / (0.3 * p["leaf_size"]), 0, 1)
        tone = tone * (1 - p["leaf_gap"] * gap * gap)
        if season and season.get("flowers") and p.get("flowers"):
            g1, _, gid = _cells(q, p["flower_size"] * 3.2, seed + 41)
            flower = (g1 < p["flower_size"]) & (gid < p["flowers"]) & (Nrm[:, 2] > -0.1)
    if p.get("steps"):
        tone = np.round(tone * p["steps"] * 2) / (p["steps"] * 2)
    if season and season.get("mix") is not None:
        cfg = dict(cfg, color=(np.asarray(cfg["color"], float) * (1 - season["amount"]) + np.asarray(season["mix"], float) * season["amount"]).tolist())
    col = np.asarray(cfg["color"], float)[None] * tone[:, None]
    mn = p.get("minerals")
    if mn:
        col = col * np.asarray(mn[variant % len(mn)], float)[None]
    if p.get("bark") and I.get("axis") is not None:  # bark still on in patches
        ax_ = I["axis"]
        al_ = (q * ax_).sum(1, keepdims=True)
        bq = (q - ax_ * al_) / (0.4 * p["bark_size"]) + ax_ * al_ / p["bark_size"]
        bm = np.clip((noise.fbm(bq, 1.0, 2, seed + 51) - (0.62 - 0.3 * p["bark"])) / 0.05, 0, 1)
        rib = 0.75 + 0.5 * noise.fbm((q - ax_ * al_) / 0.012 + ax_ * al_ / 0.2, 1.0, 2, seed + 52)
        col = col * (1 - bm[:, None]) + np.asarray(p["bark_color"], float)[None] * rib[:, None] * bm[:, None]
    if p.get("bleach"):
        col = col * (1 + p["bleach"] * np.clip(Nrm[:, 2], 0, 1))[:, None]
    if p.get("streaks"):  # rain streaks: narrow in plan, long down the face, strongest under the top edge
        st_ = noise.fbm(np.c_[q[:, 0] / p["streak_width"], q[:, 1] / p["streak_width"], q[:, 2] / 0.9], 1.0, 2, seed + 53)
        steep = np.clip(1 - np.abs(Nrm[:, 2]) / 0.7, 0, 1)
        sm = np.clip((st_ - 0.56) / 0.1, 0, 1) * steep * np.clip(0.35 + zrel, 0, 1)
        col = col * (1 - p["streaks"] * sm)[:, None]
    # curvature: convex arrises worn pale, concave darker; an ink line along arrises
    cv = np.clip(curv, -1, 1)
    col = col * (1 + p["edge_light"] * np.clip(cv, 0, 1) - p["cavity"] * np.clip(-cv, 0, 1))[:, None]
    if p.get("ink"):
        e = np.clip(1 - np.abs(I["edge"]) / p["ink_width"], 0, 1)
        e = np.maximum(e, np.clip(cv * 1.5 - 0.35, 0, 1))
        col = col * (1 - p["ink"] * e * e * (3 - 2 * e))[:, None]
    up = Nrm[:, 2]
    if p.get("gradient"):
        col = col * (1 + p["gradient"] * (np.clip(zrel, 0, 1) - 0.5) + 0.5 * p["gradient"] * (up * 0.5))[:, None]
    if p.get("top_light"):
        col = col * (1 + p["top_light"] * (np.clip(up, 0, 1) ** 1.5 - 0.3))[:, None]
    if p.get("foot") and zg is not None:
        fz = np.clip(1 - zg / p["foot_height"], 0, 1)
        col = col * (1 - p["foot"] * fz * fz * (0.7 + 0.6 * noise.fbm(q, 0.08, 2, seed + 23)))[:, None]
    if p.get("foot_tint") and zg is not None:
        fz = np.clip(1 - zg / (1.4 * p["foot_height"]), 0, 1) * np.clip((noise.fbm(q, 0.1, 2, seed + 54) - 0.3) / 0.3, 0, 1)
        col = col * (1 - p["foot_tint"] * fz[:, None]) + np.asarray(p["foot_color"], float)[None] * (p["foot_tint"] * fz)[:, None]
    if p.get("lichen"):  # crusts: round patches (cells), in clusters, on tops and the weather side
        f1, _, cid = _cells(q, p["lichen_size"], seed + 55)
        wx = np.array([math.cos(seed * 1.7), math.sin(seed * 1.7), 0.0])
        where = np.clip(np.maximum((up - 0.2) / 0.5, (Nrm @ wx - 0.2) / 0.5), 0, 1)
        clus = np.clip((noise.fbm(q, 0.3, 2, seed + 56) - 0.5 + 0.35 * p["lichen"]) / 0.1, 0, 1)
        r_ = p["lichen_size"] * (0.35 + 0.4 * cid)  # (big enough that neighbours run together into blotches)
        ragged = 1 + 0.5 * (noise.fbm(q, 0.02, 2, seed + 57) - 0.5) * 2
        m = np.clip((r_ * ragged - f1) / 0.008, 0, 1) * where * clus * (cid < 0.3 + 0.7 * p["lichen"])
        m = m * (0.45 + 0.3 * noise.fbm(q, 0.01, 2, seed + 58))  # (a thin crust: the rock shows through)
        lc = np.asarray(p["lichen_colors"], float)
        pick = lc[(cid * 97).astype(int) % len(lc)]
        col = col * (1 - m[:, None]) + pick * m[:, None]
    if p.get("top"):
        m = np.clip((up - 0.45) / 0.35, 0, 1) * np.clip((noise.fbm(q, p["top_size"], 3, seed + 17) - 0.42) / 0.14, 0, 1)
        m = m * p["top"]
        col = col * (1 - m[:, None]) + np.asarray(p["top_color"], float)[None] * (0.85 + 0.3 * noise.fbm(q, 0.02, 2, seed + 18))[:, None] * m[:, None]
    if p.get("moss"):
        b0, b1 = p["moss_band"]
        band = np.clip((zrel - b0) / 0.08, 0, 1) * np.clip((b1 - zrel) / 0.15, 0, 1)
        mv = p.get("moss_vary")
        amt = p["moss"] * (float(mv[variant % len(mv)]) if mv else 1.0)
        # moss_up: only on faces turned up that far (a river stone is mossy on its top, above the water: never a green coat)
        face = np.clip(0.6 + up, 0, 1) if not p.get("moss_up") else np.clip((up - p["moss_up"]) / 0.3, 0, 1)
        m = band * np.clip((noise.fbm(q, 0.09, 3, seed + 19) - 0.5 + 0.5 * amt) / 0.15, 0, 1) * face
        m = np.clip(m * min(1.0, 2 * amt), 0, 1)
        col = col * (1 - m[:, None]) + np.asarray(p["moss_color"], float)[None] * (0.8 + 0.4 * noise.fbm(q, 0.015, 2, seed + 20))[:, None] * m[:, None]
    col = col * (1 - 0.5 * p["ao"] * (1 - ao))[:, None]
    if flower is not None and flower.any():
        col[flower] = np.asarray(p["flower_color"], float)
    rough = np.clip(p["roughness"] * (1 + 0.08 * (tone - 1) * 4), 0.05, 1.0)
    return np.clip(col, 0, 1), rough


def _dilate(img, solid_mask, rounds=6):
    """Filled texels spread into empty ones (nearest), so mips and bilinear taps at chart edges read rock."""
    from scipy import ndimage
    if solid_mask.all() or not solid_mask.any():
        return img
    idx = ndimage.distance_transform_edt(~solid_mask, return_distances=False, return_indices=True)
    return img[idx[0], idx[1]]


def _raster_normals(L, pix, ch, rect):
    """LOD 0's interpolated vertex normals per texel of chart ch: (h, w, 3) and a mask (what the engine's shading
    starts from there; the baked normal is told apart from THIS, so flat faces with their own normals stay flat)."""
    x0, y0, w, h = rect
    out = np.zeros((h, w, 3))
    got = np.zeros((h, w), bool)
    F, N = L["F"], L["N"]
    for f in F[L["chart"] == ch]:
        p = pix[f] - [x0, y0]
        lo = np.maximum(np.floor(p.min(0)).astype(int) - 1, 0)
        hi = np.minimum(np.ceil(p.max(0)).astype(int) + 2, [w, h])
        if (hi <= lo).any():
            continue
        X, Y = np.meshgrid(np.arange(lo[0], hi[0]) + 0.5, np.arange(lo[1], hi[1]) + 0.5)
        d = (p[1, 1] - p[2, 1]) * (p[0, 0] - p[2, 0]) + (p[2, 0] - p[1, 0]) * (p[0, 1] - p[2, 1])
        if abs(d) < 1e-9:
            continue
        a = ((p[1, 1] - p[2, 1]) * (X - p[2, 0]) + (p[2, 0] - p[1, 0]) * (Y - p[2, 1])) / d
        b = ((p[2, 1] - p[0, 1]) * (X - p[2, 0]) + (p[0, 0] - p[2, 0]) * (Y - p[2, 1])) / d
        c = 1 - a - b
        m = (a > -0.15) & (b > -0.15) & (c > -0.15)
        if not m.any():
            continue
        n = a[..., None] * N[f[0]] + b[..., None] * N[f[1]] + c[..., None] * N[f[2]]
        sl = (slice(lo[1], hi[1]), slice(lo[0], hi[0]))
        inside = (a >= 0) & (b >= 0) & (c >= 0)
        take = m & (inside | ~got[sl])
        out[sl][take] = n[take]
        got[sl] |= take
    ln = np.linalg.norm(out, axis=2, keepdims=True)
    return out / np.maximum(ln, 1e-9), got


def bake_variant(cfg, solid: Solid, vol, ax, vox, cell, seed, low=None, ground=None):
    """A variant's six charts: (albedo (cell, cell, 3) sRGB, normal (.., 3) tangent, orm (.., 3), filled mask)."""
    from scipy import ndimage
    p = cfg["paint"]
    albs = {se: np.zeros((cell, cell, 3)) for se in cfg["seasons"]}
    nrm = np.zeros((cell, cell, 3))
    nrm[..., 2] = 1
    orm = np.ones((cell, cell, 3))
    orm[..., 2] = 0
    filled = np.zeros((cell, cell), bool)
    lo, hi = solid.lo, solid.hi
    zbot = None
    for ch, (a, s) in enumerate(clutter.CHARTS):
        x0, y0, w, h = _chart_rect(ch, cell)
        ui, us, ri, rs = _chart_axes(a, s)
        m = 3
        fu = (np.arange(w) + 0.5 - m) / (w - 2 * m)
        fr = (np.arange(h) + 0.5 - m) / (h - 2 * m)
        if us < 0:
            fu = 1 - fu
        if rs < 0:
            fr = 1 - fr
        cu = lo[ui] + fu * (hi[ui] - lo[ui])
        cr = lo[ri] + fr * (hi[ri] - lo[ri])
        # the volume resampled on (depth along a) x (rows) x (cols)
        vo = np.moveaxis(vol, (a, ri, ui), (0, 1, 2))
        gi = (cr - ax[ri][0]) / vox
        gj = (cu - ax[ui][0]) / vox
        JJ, II = np.meshgrid(gj, gi)
        nd = vo.shape[0]
        stack = np.stack([ndimage.map_coordinates(vo[d], [II, JJ], order=1, mode="nearest") for d in range(nd)])
        if s > 0:
            stack = stack[::-1]
        inside = stack < 0
        first = inside.argmax(0)
        hit = inside.any(0) & (first > 0)
        f1 = np.take_along_axis(stack, first[None], 0)[0]
        f0 = np.take_along_axis(stack, np.maximum(first - 1, 0)[None], 0)[0]
        frac = np.where(hit, f0 / np.maximum(f0 - f1, 1e-9), 0)
        dpos = (first - 1 + frac)
        depth = ax[a][-1] - dpos * vox if s > 0 else ax[a][0] + dpos * vox
        rr, cc = np.nonzero(hit)
        if not len(rr):
            continue
        P = np.zeros((len(rr), 3))
        P[:, a] = depth[rr, cc]
        P[:, ri] = cr[rr]
        P[:, ui] = cu[cc]
        e = np.zeros(3)
        e[a] = 1
        for _ in range(3):  # onto the exact field along the ray
            P[:, a] -= np.clip(solid.sd(P), -vox, vox) * s * 0.9
        d, I = solid.sd(P, True)
        hstep = max(0.0025, vox * 0.25)

        def fine(X):
            dd, II_ = solid.sd(X, True)
            return dd - _micro(cfg, II_, X, seed)
        g = _grad(fine, P, hstep)
        nh = g / np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-9)
        Ns = _smooth_normal(solid, P, vox)
        if low is not None:
            Nl, got = _raster_normals(low[0], low[1], ch, (x0, y0, w, h))
            use = got[rr, cc] & ((Nl[rr, cc] * Ns).sum(1) > 0.2)
            Ns = np.where(use[:, None], Nl[rr, cc], Ns)
        T4 = _tangents(Ns, a, s)
        Bt = np.cross(Ns, T4[:, :3]) * T4[:, 3:4]
        nt = np.c_[(nh * T4[:, :3]).sum(1), (nh * Bt).sum(1), np.maximum((nh * Ns).sum(1), 0.05)]
        nt /= np.linalg.norm(nt, axis=1, keepdims=True)
        # where the ray met another part of a lobed form (a bush's neighbouring lobe, a stone behind a stone) the high
        # normal has nothing to do with this face: flat there (it shaded as a grey grazing sheen)
        off = (nh * Ns).sum(1) < 0.35
        nt[off] = [0.0, 0.0, 1.0]
        # curvature (the field's Laplacian at two sizes) and occlusion (the field a little way out)
        r1 = max(0.02, 3 * vox)
        lap = sum(solid.sd(P + o) for o in (np.eye(3)[i] * r1 * sg for i in range(3) for sg in (1, -1))) - 6 * d
        curv = lap / r1 * 0.35 - 0.12 / 1.0
        curv = np.clip((lap / r1 - 0.25) * 0.9, -1, 1)
        ao = np.ones(len(P))
        for r in (0.03, 0.08, 0.18):
            ao = np.minimum(ao, np.clip(solid.sd(P + Ns * r) / r, 0, 1) * 0.5 + 0.5 * ao)
        ztop, zbot = hi[2] - 0.05, lo[2] + 0.05
        zrel = (P[:, 2] - zbot) / max(ztop - zbot, 1e-6)
        Y, X = y0 + rr, x0 + cc
        for se, sv in cfg["seasons"].items():
            col, rough = _paint(cfg, solid, P, nh, I, curv, ao, zrel, seed, zg=P[:, 2] - ground if ground is not None else None, season=sv, variant=seed % 1000)
            albs[se][Y, X] = col
        nrm[Y, X] = nt
        orm[Y, X, 0] = 1 - p["ao"] * (1 - ao)
        orm[Y, X, 1] = rough
        filled[Y, X] = True
    # dilate per chart so charts don't bleed into each other
    for ch in range(6):
        x0, y0, w, h = _chart_rect(ch, cell)
        sl = (slice(y0, y0 + h), slice(x0, x0 + w))
        for im in list(albs.values()) + [nrm, orm]:
            im[sl] = _dilate(im[sl], filled[sl])
    return albs, nrm, orm, filled
