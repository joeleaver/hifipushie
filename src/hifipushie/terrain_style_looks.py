"""Looks: swatch and season sheets, the transition strip; the game's view of the ground. Part of the terrain styles (terrain_style.py has the overview)."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from . import terrain_style
from .terrain_style import _lin_srgb, _srgb_lin, layer_colour
from .terrain_style_fields import texture
from .terrain_style_files import _q8
from .terrain_style_zones import edge_weights, layer_edge, season_colours, snow_numbers

# ------------------------------------------------------------------------------------------------ looks
def _shade(S, light=(-0.5, 0.45, 0.75)):
    l = np.array(light, float)
    l /= np.linalg.norm(l)
    ndl = np.clip((S["normal"] * l).sum(-1), 0, 1)
    lin = S["albedo_linear"] * (0.25 + 0.75 * ndl)[..., None]
    return _lin_srgb(lin)


def swatch_sheet(styles: list[dict], refs: dict, layers, path, px: int = 384, tiled: int = 2) -> Path:
    """A contact sheet: a row per style, per layer the albedo tiled `tiled` x `tiled` (the wrap shows if it seams),
    then lit with a low sun, then its normal map. Rows: style names; columns: layers."""
    from PIL import Image, ImageDraw
    cell = px
    cols = len(layers) * 3
    W, H = 160 + cols * (cell + 4), 40 + len(styles) * (cell + 24)
    im = Image.new("RGB", (W, H), (32, 32, 34))
    dr = ImageDraw.Draw(im)
    for c, nm in enumerate(layers):
        x = 160 + c * 3 * (cell + 4)
        dr.text((x + 4, 8), f"{nm}: albedo x{tiled * tiled} tiles | lit | normal", fill=(230, 230, 230))
    for r, st in enumerate(styles):
        y = 40 + r * (cell + 24)
        dr.text((8, y + cell // 2), st["name"], fill=(240, 240, 240))
        for c, nm in enumerate(layers):
            col = layer_colour(st, nm, refs)
            S = texture(st, nm, col, 512)
            x = 160 + c * 3 * (cell + 4)
            alb = np.tile(S["albedo"][::-1], (tiled, tiled, 1))
            panels = [alb, np.tile(_shade(S)[::-1], (tiled, tiled, 1)), S["normal"][::-1] * 0.5 + 0.5]
            for k, a in enumerate(panels):
                pim = Image.fromarray(_q8(a)).resize((cell, cell), Image.LANCZOS)
                im.paste(pim, (x + k * (cell + 4), y))
            dr.text((x + 2, y + cell + 2), f"{S['size_m']:g} m a tile ({tiled * S['size_m']:g} m shown)",
                    fill=(200, 200, 200))
    path = Path(path)
    im.save(path)
    return path


def season_sheet(styles: list[dict], refs: dict, layers, path, px: int = 160) -> Path:
    """Rows: style x layer; columns: spring, summer, autumn, winter, snow (by the snow numbers on a flat ground: the
    coverage's share of the texture whitened where its own normal faces up most). Lit with a low sun."""
    from PIL import Image, ImageDraw
    cols = list(terrain_style.SEASONS) + ["snow"]
    rows = [(st, nm) for st in styles for nm in layers]
    W, H = 200 + len(cols) * (px + 4), 24 + len(rows) * (px + 4)
    im = Image.new("RGB", (W, H), (32, 32, 34))
    dr = ImageDraw.Draw(im)
    for c, se in enumerate(cols):
        dr.text((200 + c * (px + 4) + 4, 6), se, fill=(230, 230, 230))
    for r, (st, nm) in enumerate(rows):
        y = 24 + r * (px + 4)
        dr.text((8, y + px // 2), f"{st['name']} {nm}", fill=(240, 240, 240))
        col = layer_colour(st, nm, refs)
        S = texture(st, nm, col, 256)
        sc = season_colours(st, nm, col)
        sn = snow_numbers(st)
        for c, se in enumerate(cols):
            lin = S["albedo_linear"] * np.array(sc[se if se != "snow" else "winter"]["tint_linear"])
            if se == "snow":
                up = S["normal"][..., 2]
                b = sn["by_normal"]
                f = np.clip((up - (1 - sn["coverage"] * 0.3) - b["from"]) / max(b["to"] - b["from"], 1e-6), 0, 1)
                f = np.clip(sn["coverage"] + 0.5 * (f - 0.5), 0, 1) * float((sn["layers"] or {}).get(nm, 1.0))
                lin = lin * (1 - f[..., None]) + np.array(sn["color_linear"]) * f[..., None]
            l = np.array([-0.5, 0.45, 0.75])
            l /= np.linalg.norm(l)
            ndl = np.clip((S["normal"] * l).sum(-1), 0, 1)
            img = _lin_srgb(lin * (0.25 + 0.75 * ndl)[..., None])
            pim = Image.fromarray(_q8(img[::-1])).resize((px, px), Image.LANCZOS)
            im.paste(pim, (200 + c * (px + 4), y))
    path = Path(path)
    im.save(path)
    return path


def transition_strip(styles: list[dict], refs: dict, layer: str, path, length_m: float = 60.0, band: float = terrain_style.BAND,
                     px_per_m: int = 24, width_m: float = 8.0) -> Path:
    """A top view of one layer walking through the styles in order, each pair blended over `band` m as the recipe
    does (weights by a smoothstep, a lit preview): what the engine's transition should look like."""
    from PIL import Image
    n_st = len(styles)
    Wm = length_m * n_st
    w_px, h_px = int(Wm * px_per_m), int(width_m * px_per_m)
    xs = (np.arange(w_px) + 0.5) / px_per_m
    ys = (np.arange(h_px) + 0.5) / px_per_m
    X, Y = np.meshgrid(xs, ys)
    acc = np.zeros((h_px, w_px, 3))
    wsum = np.zeros((h_px, w_px))
    for k, st in enumerate(styles):
        col = layer_colour(st, layer, refs)
        S = texture(st, layer, col, 512)
        L = S["size_m"]
        n = S["albedo"].shape[0]
        lit = _srgb_lin(_shade(S))
        ii = ((Y / L * n).astype(int)) % n
        jj = ((X / L * n).astype(int)) % n
        a, b = k * length_m, (k + 1) * length_m  # (this style's stretch; the strip's own ends don't blend)
        d = np.minimum(X - a if k > 0 else np.full_like(X, 1e9), b - X if k < n_st - 1 else np.full_like(X, 1e9))
        e = np.clip(d / band + 0.5, 0, 1)
        w = e * e * (3 - 2 * e)
        acc += w[..., None] * lit[ii, jj]
        wsum += w
    img = _lin_srgb(acc / np.maximum(wsum, 1e-6)[..., None])
    Image.fromarray(_q8(img)).save(path)
    return Path(path)


# ------------------------------------------------------------------------------------------------ the game's view
def _pyramid(img):
    """Box-filtered mip levels of a periodic (n, n, c) image (n a power of two), as a GPU's mipmaps."""
    lv = [img]
    while lv[-1].shape[0] > 4:
        a = lv[-1]
        lv.append(0.25 * (a[0::2, 0::2] + a[1::2, 0::2] + a[0::2, 1::2] + a[1::2, 1::2]))
    return lv


def _sample(lv, u, v, lod):
    """Trilinear sample of a pyramid at periodic uv (0..1 = one tile; rows run up) and per-point level."""
    lod = np.clip(lod, 0, len(lv) - 1)
    l0 = np.floor(lod).astype(int)
    f = (lod - l0)[..., None]
    out = np.zeros(u.shape + (lv[0].shape[2],))

    def bil(a, uu, vv):
        n = a.shape[0]
        x, y = uu * n - 0.5, vv * n - 0.5
        x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
        fx, fy = (x - x0)[..., None], (y - y0)[..., None]
        x0, y0, x1, y1 = x0 % n, y0 % n, (x0 + 1) % n, (y0 + 1) % n
        return ((a[y0, x0] * (1 - fx) + a[y0, x1] * fx) * (1 - fy) + (a[y1, x0] * (1 - fx) + a[y1, x1] * fx) * fy)

    for k in np.unique(l0):
        m = l0 == k
        a = bil(lv[k], u[m], v[m])
        b = bil(lv[min(k + 1, len(lv) - 1)], u[m], v[m])
        out[m] = a * (1 - f[m]) + b * f[m]
    return out


def ground_view(styles: list[dict], refs: dict, path, layers=("grass", "earth"), size=(560, 315), px: int = 1024,
                light: str = "game") -> Path:
    """What the ground looks like in the game, per style: a row of eye-level views (1.7 m up, looking along a gently
    curving path of the second layer through the first) and views from 25 m up, 40 deg down. The ground is flat, so
    only the textures, their layer edges (`layer_edge`) and mipmaps show: lit as the game's cel styles light flat ground
    (light "game": albedo x (sun band + flat ambient), no specular), sampled through mip levels as a GPU does. A stand-in
    for the baked macro colour (realistic's 60 / 15 m colour patches) is applied by each style's `macro`."""
    from PIL import Image, ImageDraw
    W, Hh = size
    fov = math.radians(70.0)
    cams = [("eye 1.7 m", 1.7, math.radians(-6.0)), ("25 m up", 25.0, math.radians(-40.0))]
    tiles = []
    for st in styles:
        tex = []
        for nm in layers:
            S = texture(st, nm, layer_colour(st, nm, refs), px)
            hr = max(float(np.abs(S["height"]).max()), 1e-6)
            tex.append((S["size_m"], _pyramid(np.concatenate([S["albedo_linear"], (S["height"] / hr)[..., None]], -1))))
        row = []
        for title, h, pitch in cams:
            jj, ii = np.meshgrid(np.arange(W) + 0.5, np.arange(Hh) + 0.5)
            t = math.tan(fov / 2)
            x = (2 * jj / W - 1) * t
            y = (1 - 2 * ii / Hh) * t * Hh / W
            # camera looking +y, pitched down
            dy = math.cos(pitch) - y * math.sin(pitch)
            dz = math.sin(pitch) + y * math.cos(pitch)
            dx = x
            hit = dz < -1e-4
            tt = np.where(hit, -h / np.minimum(dz, -1e-4), 0.0)
            px_ang = 2 * t / W
            dn = np.sqrt(dx * dx + dy * dy + dz * dz)
            Xw, Yw = dx * tt, dy * tt
            dist = tt * dn
            graze = np.clip(-dz / dn, 0.02, 1)
            across = dist * px_ang
            foot = across * np.sqrt(np.minimum(1 / graze, 8.0))  # (anisotropic filtering takes some of the stretch)
            # the second layer as a curving path 3 m wide, soft over ~1 m as the tiles' weight maps are
            cx = 2.5 * np.sin(Yw / 9.0) + 1.0
            we = np.clip((1.9 - np.abs(Xw - cx)) / 1.0 + 0.5, 0, 1)
            we = we * we * (3 - 2 * we)
            Wl = np.stack([1 - we, we]) if len(layers) == 2 else np.ones((1,) + Xw.shape)
            cols, hts = [], []
            for (L, lv) in tex:
                lod = np.log2(np.maximum(foot / (L / px), 1e-6))
                # the recipe's anti-tiling: a second sampling at uv / 1.618 + (0.37, 0.71), chosen by patches ~3 tiles
                pick = (np.sin(Xw / (0.9 * L) + np.sin(Yw / (1.3 * L))) * np.sin(Yw / (1.1 * L) + 0.5)) > 0
                s = _sample(lv, Xw / L, Yw / L, lod)
                s2 = _sample(lv, Xw / L / 1.618 + 0.37, Yw / L / 1.618 + 0.71, lod - math.log2(1.618))
                s = np.where(pick[..., None], s2, s)
                cols.append(s[..., :3])
                hts.append(s[..., 3])
            Wl = edge_weights(Wl, np.stack(hts), layer_edge(st))
            col = sum(Wl[k][..., None] * cols[k] for k in range(len(cols)))
            # the baked macro colour's variation (realistic's broad patches), kept by `macro`
            n1 = np.sin(Xw / 9.3 + 1.3 * np.sin(Yw / 13.0)) * np.sin(Yw / 11.7 + 0.7 * np.sin(Xw / 7.0))
            n2 = np.sin(Xw / 31.0 + 2.0) * np.sin(Yw / 27.0 + 0.4)
            var = 1 + 0.10 * n1 + 0.07 * n2
            col = col * (1 + float(st.get("macro", 1.0)) * (var - 1))[..., None]
            if light == "game":
                # (flat ground: fully in the sun band, the flat ambient on top, no specular: one factor)
                col = col * 0.92
            sky = np.array([0.42, 0.52, 0.66])
            haze = 1 - np.exp(-dist / 900.0)
            col = col * (1 - haze[..., None]) + sky * haze[..., None]
            img = np.where(hit[..., None], col, sky)
            im = Image.fromarray(_q8(_lin_srgb(img)))
            ImageDraw.Draw(im).text((6, 4), f"{st['name']}: {title}", fill=(255, 255, 255))
            row.append(im)
        tiles.append(row)
    out = Image.new("RGB", (W * len(cams) + 4 * (len(cams) - 1), Hh * len(styles) + 4 * (len(styles) - 1)), (30, 30, 30))
    for r, row in enumerate(tiles):
        for c, im in enumerate(row):
            out.paste(im, (c * (W + 4), r * (Hh + 4)))
    path = Path(path)
    out.save(path)
    return path
