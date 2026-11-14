"""The grass detail: the sand and grass swatches (tiling, like the rock's) and their files. Part of the terrain's ground (terrain_ground.py has the overview)."""
from __future__ import annotations

import numpy as np
from scipy import ndimage

from . import terrain_ground

def sand_swatch(size=None, res=None, seed=4245):
    """A tileable sand swatch (top view, periodic, as grass_swatch returns it): wind/wave ripples ~8-12 cm apart in
    wandering patches (crests a little paler), grit speckle, scattered pebbles and shell (1-4 cm, darker and paler),
    so a beach isn't a smooth cream ramp at eye level."""
    from .terrain_swatch_periodic import spectral
    L = float(size or terrain_ground.GRASS["size"])
    n = int(round(L * (res or terrain_ground.GRASS["res"])))
    rng = np.random.default_rng(seed)
    t = L / n
    yy, xx = np.mgrid[0:n, 0:n] * t
    # ripples: crests along a direction that wanders, wavelength ~0.1 m, in patches; integer cycles per swatch so it
    # wraps (the phase field is periodic noise)
    mx, my = int(round(0.94 * L / 0.1)), int(round(0.34 * L / 0.1))  # (whole cycles across the swatch both ways)
    warp = spectral(n, 2.6, seed + 1, lo=3) * 1.6
    ph = 2 * np.pi * (mx * xx + my * yy) / L + warp * 2 * np.pi
    rip = np.sin(ph) + 0.35 * np.sin(2 * ph + 1.0)
    patch = np.clip(0.5 + 1.4 * spectral(n, 2.2, seed + 2, lo=4), 0, 1)
    hgt = 0.004 * rip * patch
    grit = spectral(n, 0.6, seed + 3, lo=8)
    alb = 1 + 0.10 * grit + 0.05 * rip * patch
    # pebbles and shell: discs 1-4 cm, splatted on the torus
    npb = int(260 * (L / 2.0) ** 2)
    c = rng.random((npb, 2)) * n
    rad = rng.uniform(0.005, 0.02, npb) / t
    tone = np.where(rng.random(npb) < 0.6, rng.uniform(0.45, 0.75, npb), rng.uniform(1.15, 1.35, npb))
    for (cx, cy), r, tn in zip(c, rad, tone):
        i0, i1 = int(cy - r - 1), int(cy + r + 2)
        j0, j1 = int(cx - r - 1), int(cx + r + 2)
        ii, jj = np.mgrid[i0:i1, j0:j1]
        d = np.hypot(ii - cy, jj - cx) / max(r, 1e-6)
        m = np.clip(1.2 - d, 0, 1)
        sl = (ii % n, jj % n)
        alb[sl] = alb[sl] * (1 - m) + tn * m
        hgt[sl] = np.maximum(hgt[sl], 0.6 * r * t * np.sqrt(np.clip(1 - d * d, 0, 1)))
    alb = np.repeat(alb[..., None], 3, -1) * np.array([1.0, 0.99, 0.96])
    alb = alb / alb.reshape(-1, 3).mean(0)
    gx = (np.roll(hgt, -1, 1) - np.roll(hgt, 1, 1)) / (2 * t)
    gy = (np.roll(hgt, -1, 0) - np.roll(hgt, 1, 0)) / (2 * t)
    nrm = np.stack([-gx, -gy, np.ones_like(gx)], -1)
    nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
    return {"albedo": alb, "height": hgt - hgt.mean(), "normal": nrm, "rough": np.ones((n, n)), "size_m": L,
            "texels_per_m": n / L, "n": n}


def grass_swatch(size=None, res=None, seed=4243, blades=None, length=None, dry=None, clump=1.0):
    """A tileable turf swatch (top view, periodic): blades as short strokes splatted on the torus (lit tips, dark
    gaps between them), clumps 0.1-0.4 m, dry blades straw-coloured. Returns {"albedo" (n, n, 3) multiplier, mean 1;
    "height" m; "normal" (n, n, 3) tangent space (+x east, +y north); "rough"; "size_m"; "texels_per_m"; "n"}. Below
    the ground maps' texel (4/m) the macro colour is mush at eye level; this is what an engine tiles over it."""
    from .terrain_swatch_periodic import spectral
    L = float(size or terrain_ground.GRASS["size"])
    n = int(round(L * (res or terrain_ground.GRASS["res"])))
    rng = np.random.default_rng(seed)
    nb = int((blades or terrain_ground.GRASS["blades"]) * (L / 2.0) ** 2)
    length = length or terrain_ground.GRASS["length"]
    dry = terrain_ground.GRASS["dry"] if dry is None else dry
    clump_n = spectral(n, 2.2, seed + 1, lo=5)  # (-1..1, 0.1-0.4 m)
    # blades seeded more densely in the clumps
    px = rng.random((nb * 2, 2)) * n
    cl = 0.5 + 0.5 * clump_n[px[:, 1].astype(int) % n, px[:, 0].astype(int) % n]
    keep = rng.random(nb * 2) < (0.6 - 0.25 * clump) + 0.5 * clump * cl
    px = px[keep][:nb]
    nb = len(px)
    ang = rng.random(nb) * 2 * np.pi
    ln = rng.uniform(*length, nb) * n / L
    dry = rng.random(nb) < dry
    hgt = np.zeros((n, n))
    tip = np.zeros((n, n))
    dryi = np.zeros((n, n))
    cnt = np.zeros((n, n))
    hb = 0.004 + 0.12 * float(np.mean(length))  # (taller blades stand higher)
    for t in np.linspace(0, 1, 9):
        q = px + (t * ln)[:, None] * np.c_[np.cos(ang), np.sin(ang)]
        ix, iy = q[:, 0].astype(int) % n, q[:, 1].astype(int) % n
        np.add.at(hgt, (iy, ix), 0.004 + hb * t)
        np.add.at(tip, (iy, ix), t)
        np.add.at(dryi, (iy, ix), dry * 1.0)
        np.add.at(cnt, (iy, ix), 1.0)
    hgt = ndimage.gaussian_filter(hgt, 0.6, mode="wrap") + 0.012 * clump * clump_n
    cover = 1 - np.exp(-cnt / 2.0)  # (how much of the texel blades cover; the rest is shadowed gap)
    tipm = tip / np.maximum(cnt, 1e-9)
    drym = np.clip(dryi / np.maximum(cnt, 1e-9), 0, 1)
    tone = (0.62 + 0.38 * cover) * (0.85 + 0.3 * tipm) * (1 + 0.12 * clump * clump_n)
    tone = ndimage.gaussian_filter(tone, 0.5, mode="wrap")
    straw = np.array([1.45, 1.30, 0.75])  # (a dry blade against the green: warmer and paler)
    alb = tone[..., None] * (1 + drym[..., None] * (straw - 1))
    alb = alb / alb.reshape(-1, 3).mean(0)
    t = L / n
    gx = (np.roll(hgt, -1, 1) - np.roll(hgt, 1, 1)) / (2 * t)
    gy = (np.roll(hgt, -1, 0) - np.roll(hgt, 1, 0)) / (2 * t)
    nrm = np.stack([-gx, -gy, np.ones_like(gx)], -1)
    nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
    rough = 1.0 + 0.1 * (1 - cover)
    return {"albedo": alb, "height": hgt - hgt.mean(), "normal": nrm, "rough": rough / rough.mean(), "size_m": L,
            "texels_per_m": n / L, "n": n}


def write_grass(out_dir, layers=None):
    """The grass swatches' images in out_dir/materials (rows top = north), as terrain_swatch_detail.write lays the rock's:
    <kind>_detail_albedo (linear, x 2 = the multiplier), _normal (tangent: +x east, +y north), _height (16-bit), one
    set per SWATCHES kind whose layers exist (`layers`: the terrain's layer names; None = all). Returns the manifest
    entry: the first swatch's keys at the top (as before) and every swatch under "swatches"."""
    from PIL import Image
    from .terrain_swatch_make import tileability
    d = out_dir / "materials"
    d.mkdir(exist_ok=True)
    q8 = lambda a: np.round(np.clip(a, 0, 1) * 255).astype(np.uint8)
    out = []
    for kind, P in terrain_ground.SWATCHES.items():
        lay = [nm for nm in P["layers"] if layers is None or nm in layers]
        if not lay:
            continue
        if P.get("gen") in ("cobble", "silt"):
            from . import terrain_stream_water
            S = (terrain_stream_water.cobble_swatch if P["gen"] == "cobble" else terrain_stream_water.silt_swatch)(seed=P["seed"])
        else:
            S = sand_swatch(seed=P["seed"]) if P.get("gen") == "sand" else \
                grass_swatch(seed=P["seed"], blades=P["blades"], length=P["length"], dry=P["dry"], clump=P["clump"])
        hr = float(max(np.abs(S["height"]).max(), 1e-4))
        imgs = {"albedo": q8(0.5 * S["albedo"]), "normal": q8(S["normal"] * 0.5 + 0.5),
                "height": np.round((S["height"] / hr * 0.5 + 0.5) * 65535).astype(np.uint16)}
        files, seams = {}, {}
        prefix = "grass" if kind == "grass" else kind
        for k, a in imgs.items():
            fn = f"materials/{prefix}_detail_{k}.png"
            Image.fromarray(np.ascontiguousarray(a[::-1]), "I;16" if a.dtype == np.uint16 else None).save(out_dir / fn)
            files[k] = fn
            seams[k] = tileability(a)
        out.append({"kind": kind, "layers": lay, **files, "size_m": S["size_m"], "texels_per_m": S["texels_per_m"],
                    "fade_m": list(P.get("fade", terrain_ground.GRASS_FADE)),
                    "height_m": round(hr, 5), "wrap_seam": seams})
    if not out:
        return None
    return {**{k: v for k, v in out[0].items() if k != "kind"}, "swatches": out,
            "projection": "top: uv = world (x, y) / size_m", "fade_m": list(terrain_ground.GRASS_FADE),
            "recipe": "Per swatch, where its layers weigh w (_WEIGHTS / the weights map), on ground and cliff tiles: "
                      "uv = worldpos.xy / size_m, and a second sampling at uv / 1.618 + (0.37, 0.71), CHOSEN between "
                      "by a smooth noise mask over ~8 m patches (smoothstep 0.42..0.58 of value noise at worldpos / 8 m) "
                      "to break the repeat (mixed 50/50 the two lattices beat into ~5 m blotches under a high sun); albedo: macro x (1 + w f (2 albedo - 1)); normal: the detail normal (+x east, "
                      "+y north) RNM-combined onto the macro normal by w f; f = 1 - smoothstep(fade_m[0], fade_m[1], "
                      "view distance)."}
