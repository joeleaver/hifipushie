"""Texture repaint: REBUILD the maps at 4K the way a texture artist paints them, from the region reading.

colour   = each material's base colour (measured from the concept on squarely-seen, well-lit texels: the art is the
           authority; the generated texture's median where no view sees the material), region edges from the
           surface-smoothed probabilities (sharpened: clean, anti-aliased, the concept's design kept),
           + a soft large-scale value / hue drift (hand-painted, not flat) + the material's fine detail
normal   = the sculpted normal map (upsampled) + the material's fine detail as tangent-space bumps
rough    = per material + detail
Fine detail is evaluated in 3D at each texel's position (triplanar-like: no seams, no stretch on UV islands):
  clay  fingerprint ridges (sin of a warped noise field) + pores;   gloss  almost none;   horn  growth bands along z;
  wood  grain lines;   metal  brushed streaks + wear;   paint  soft orange-peel;   flat  nothing."""
from __future__ import annotations

import numpy as np
from scipy import ndimage

from .texrepaint_concept import lab
from .texrepaint_surface import Texels, pad

KIND_ROUGH = {"clay": 0.62, "gloss": 0.18, "horn": 0.45, "metal": 0.38, "wood": 0.7, "paint": 0.5, "flat": 0.6,
              "cloth": 0.85}


class Noise3:
    """smooth 3D value noise from a periodic random lattice (cheap: trilinear lookups)"""

    def __init__(self, seed=0, n=48):
        self.g = np.random.default_rng(seed).random((n, n, n)).astype(np.float32); self.n = n

    def __call__(self, pos, scale):
        c = (pos / scale).T % self.n
        return ndimage.map_coordinates(self.g, c, order=1, mode="grid-wrap") * 2 - 1

    def fbm(self, pos, scale, oct=3):
        return sum(self(pos * 1.0, scale / 2 ** o) * 0.5 ** o for o in range(oct)) / 1.75


def detail(kind: str, pos, nrm, model_h: float, seed=0):
    """per-texel (height -1..1, colour value multiplier delta, roughness delta) for a material kind"""
    N = Noise3(seed); s = model_h  # scales relative to model height (a 1 m clay figure)
    if kind == "clay":
        warp = N.fbm(pos, 0.05 * s)
        ridges = np.sin((N(pos + 7.0, 0.02 * s) * 3 + warp) * 40)        # fingerprint swirls
        pores = N(pos + 3.0, 0.0018 * s)
        h = 0.55 * ridges * np.clip(N(pos + 11.0, 0.06 * s) + 0.3, 0, 1) + 0.45 * pores
        return h, -0.012 * h, 0.05 * h
    if kind == "horn":
        bands = np.sin(pos[:, 2] / (0.004 * s) + N(pos, 0.03 * s) * 3)
        return 0.6 * bands, 0.03 * bands, 0.04 * bands
    if kind == "wood":
        g = np.sin((pos[:, 0] + pos[:, 1]) / (0.003 * s) + N(pos, 0.04 * s) * 6) * 0.5 + N(pos, 0.004 * s) * 0.5
        return g, 0.06 * g, 0.06 * g
    if kind == "metal":
        brushed = N(pos * [1, 1, 12], 0.01 * s); wear = np.clip(N.fbm(pos + 5, 0.05 * s) * 2, 0, 1)
        return 0.3 * brushed, 0.04 * brushed + 0.08 * wear, 0.08 * brushed - 0.15 * wear
    if kind == "paint":
        p = N(pos, 0.003 * s); return 0.3 * p, 0.01 * p, 0.04 * p
    if kind == "gloss":
        p = N(pos, 0.01 * s); return 0.05 * p, 0.004 * p, 0.01 * p
    return np.zeros(len(pos)), np.zeros(len(pos)), np.zeros(len(pos))


def base_colours(materials, R, tex_rgb, con_rgb, con_w, tx: Texels):
    """the colour each material is painted: an explicit "paint" wins; else the concept's colour on squarely seen,
    confidently labelled texels (median, upper-lightness half = the lit side, not the shadows); else the texture's"""
    lab_ = R["P"].argmax(1); conf = R["P"].max(1) > 0.85; out, src = [], []
    for k, m in enumerate(materials):
        if m.get("paint"):
            out.append(np.array(m["paint"], np.float32)); src.append("given"); continue
        from .texrepaint_regions import classify
        sel = (lab_ == k) & conf & (con_w > 0.5)
        if sel.any():   # only art pixels that read as this material themselves (not a held prop in front of it)
            sel[sel] = classify(con_rgb[sel], materials)[0] == k
        if sel.sum() > 200:
            c = con_rgb[sel]; s = "concept"
        else:
            sel = (lab_ == k) & conf
            c = tex_rgb[sel] if sel.sum() > 50 else np.array([m["colour"]], np.float32); s = "texture"
        L = lab(c)[:, 0]; lit = c[L >= np.median(L)] if len(c) > 10 else c
        out.append(np.median(lit, 0).astype(np.float32)); src.append(s)
    return np.array(out), src


def paint(tx: Texels, R, materials, cols, normal_old: np.ndarray, tex_rgb, model_h: float, sharp: float = 10.0,
          drift: float = 0.035, detail_strength: float = 1.0, bump: float = 1.6, keep_rgb=None, seed=0, keep_w=None):
    """-> colour (res,res,3 uint8), normal (res,res,3 uint8), roughness (res,res uint8), label (res,res uint8)"""
    P = np.clip(R["P"], 0, 1) ** sharp; P /= np.maximum(P.sum(1, keepdims=True), 1e-9)
    lin = (cols / 255.0) ** 2.2
    col = P @ lin                                                        # blend in linear light: clean AA edges
    N = Noise3(seed + 1)
    v = 1 + drift * N.fbm(tx.pos, 0.12 * model_h)                        # soft painterly drift (value)
    warm = drift * 0.5 * N(tx.pos + 13, 0.2 * model_h)
    col = col * v[:, None]; col[:, 0] *= 1 + warm; col[:, 2] *= 1 - warm
    rough = P @ np.array([m.get("rough", KIND_ROUGH.get(m.get("kind", "clay"), 0.6)) for m in materials], np.float32)
    height = np.zeros(len(tx.idx), np.float32)
    for k, m in enumerate(materials):
        w = P[:, k]; sel = w > 0.01
        if not sel.any():
            continue
        h, dv, dr = detail(m.get("kind", "clay"), tx.pos[sel], tx.nrm[sel], model_h, seed + k)
        h, dv, dr = (np.asarray(a, np.float32) * detail_strength for a in (h, dv, dr))
        col[sel] *= (1 + dv * w[sel])[:, None]; rough[sel] += dr * w[sel]; height[sel] += h * w[sel]
        if m.get("keep_texture"):
            t = (np.asarray(tex_rgb[sel] if keep_rgb is None else keep_rgb[sel], np.float32) / 255.0) ** 2.2
            col[sel] = col[sel] * (1 - w[sel, None]) + t * w[sel, None]
    if keep_w is not None and keep_w.any():   # painted details kept from the generated map (eyes, nostrils)
        t = (np.asarray(tex_rgb, np.float32) / 255.0) ** 2.2
        col = col * (1 - keep_w[:, None]) + t * keep_w[:, None]
    srgb = np.clip(col, 0, 1) ** (1 / 2.2) * 255
    m = tx.mask()
    colour = pad(tx.image(srgb.astype(np.float32), 0), m).clip(0, 255).astype(np.uint8)
    rough_img = pad(tx.image(np.clip(rough, 0.02, 1) * 255, 0), m).clip(0, 255).astype(np.uint8)
    label = tx.image(P.argmax(1).astype(np.uint8), 255)
    # normal: the sculpt's map (upsampled) + the detail bumps (tangent space: +u = image right, +v = image UP)
    nold = tx.sample(normal_old) / 127.5 - 1
    nold /= np.maximum(np.linalg.norm(nold, axis=1, keepdims=True), 1e-6)
    H = pad(tx.image(height, 0), m, px=4)
    H = ndimage.gaussian_filter(H, 0.7)
    gy, gx = np.gradient(H)
    du = gx.ravel()[tx.idx] * bump; dv = -gy.ravel()[tx.idx] * bump
    n = np.stack([nold[:, 0] - du, nold[:, 1] - dv, nold[:, 2]], 1)  # UDN blend
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-6)
    normal = pad(tx.image(((n + 1) * 127.5).astype(np.float32), 0), m).clip(0, 255).astype(np.uint8)
    normal[~m & (normal.sum(-1) == 0)] = (128, 128, 255)
    return colour, normal, rough_img, label
