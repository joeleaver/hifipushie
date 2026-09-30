"""Seams as the eye sees them: a rendered view against its exact id pass (`render_tiles(ids=True)`: which GLB and which
atlas chart each pixel shows, and how far away it is).

The numeric seam check (terrain_mesh.map_seams) decodes each channel on both sides of a border at the same points and
passes when they agree; it says nothing about what a border looks like after lighting, filtering and the eye's
sensitivity to long straight lines, and it never looks at chart borders or at regular patterns. Here every pair of
neighbouring pixels showing one continuous surface (no depth jump) is classed by what lies between them: a tile border
(two tiles of the same kind), the overlay's edge (a cliff mesh against the ground), a chart border (one tile, two
atlas charts), or nothing. A border that shows is a jump: the brightness step across it is larger than the steps of
the pixel pairs just before and after it (a crease on a border only bends the slope, so it doesn't count).
`excess` = (step across / steps beside) at the borders over the same ratio inside surfaces: ~1.0 = invisible.
(A first version compared the step with pairs a few pixels away: chart borders follow the faces' orientation, so
creases on them read as seams in every channel, clay included.)

`grid_squares` looks for the other kind of square: a pattern locked to the world's axes at a fixed spacing (a grid of
cells sampled bilinearly) shows as energy at that period along x and y in the rendered colour.
`texel_density` checks that neighbouring tiles' atlases have about the same texels per metre.
`straight_lines` finds what no border class holds: long straight edges in the render (a bed ruled across a whole wall
read as a seam while every border measured ~1.0)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy import ndimage


def _lum(path):
    from PIL import Image
    a = np.asarray(Image.open(path).convert("RGB"), float) / 255.0
    return a @ np.array([0.2126, 0.7152, 0.0722])


def classes(ids, kinds, depth_tol=0.02):
    """Per neighbouring pixel pair (horizontal then vertical): 0 none/invalid, 1 interior, 2 chart border, 3 tile
    border, 4 overlay edge (cliff mesh against ground). Pairs across a depth jump are invalid."""
    g = np.rint(ids[..., 0]).astype(np.int64)
    c = np.rint(ids[..., 1]).astype(np.int64)
    d = ids[..., 2]
    kind = np.array([0] + [1 if k[0] == "cliff" else 2 for k in kinds])
    tile = np.array([-1] + [k[1] * 100003 + k[2] for k in kinds])
    out = []
    for sl_a, sl_b in (((slice(None), slice(0, -1)), (slice(None), slice(1, None))),
                       ((slice(0, -1), slice(None)), (slice(1, None), slice(None)))):
        ga, gb, ca, cb, da, db = g[sl_a], g[sl_b], c[sl_a], c[sl_b], d[sl_a], d[sl_b]
        ok = (ga > 0) & (gb > 0) & (np.abs(da - db) < depth_tol * np.maximum(da, db) + 0.05)
        cl = np.ones(ga.shape, np.int8)
        same = ga == gb
        cl[same & (ca != cb)] = 2
        ka, kb = kind[ga], kind[gb]
        cl[~same & (ka == kb) & (tile[ga] != tile[gb])] = 3
        cl[~same & (ka != kb)] = 4
        cl[~same & (ka == kb) & (tile[ga] == tile[gb])] = 1  # (a tile's own LOD files: never happens in one render)
        cl[~ok] = 0
        out.append(cl)
    return out


def _jumps(L, cl, axis):
    """For every pixel pair along `axis` (pairs x|x+1): the step across it and the mean of the steps of the pairs just
    before and after it (x-1|x and x+1|x+2). A seam is a jump: its step stands out from its neighbours' (a crease only
    bends the slope: the steps either side of it are about as big as the one across)."""
    Lt = L if axis == 1 else L.T
    ct = cl if axis == 1 else cl.T
    d = np.abs(np.diff(Lt, axis=1))  # (h, w-1)
    step = d[:, 1:-1]
    nb = 0.5 * (d[:, :-2] + d[:, 2:])
    ok = (ct[:, :-2] == 1) & (ct[:, 2:] == 1)  # (the pairs either side are inside one surface)
    return step, nb, ct[:, 1:-1], ok


def measure(image, ids, kinds):
    """{class: {"pairs", "step" (mean |dL| across), "beside" (mean |dL| of the pairs either side), "excess" (step /
    beside, over the same ratio inside surfaces: 1.0 = the border can't be told from the surface round it)}} for one
    view, plus "interior" (the raw step / beside ratio off any border). image: the rendered PNG; ids: its _ids.npy (or
    the array); kinds: the render job's "kinds"."""
    L = _lum(image) if not isinstance(image, np.ndarray) else image
    I = np.load(ids) if not isinstance(ids, np.ndarray) else ids
    if L.shape != I.shape[:2]:
        raise ValueError(f"image {L.shape} and id pass {I.shape[:2]} differ")
    ch, cv = classes(I, kinds)
    parts = [_jumps(L, ch, 1), _jumps(L, cv, 0)]
    step, nb, cls, ok = (np.concatenate([q[n].ravel() for q in parts]) for n in range(4))
    base = ok & (cls == 1)
    # (+ half an 8-bit level: on a smooth, evenly lit surface the steps are all near zero and their ratio is noise)
    e = 0.5 / 255
    ref = float((step[base].mean() + e) / (nb[base].mean() + e)) if base.sum() > 20 else 1.0
    res = {"interior": {"pairs": int(base.sum()), "ratio": round(ref, 3)}}
    for k, nm in {2: "chart", 3: "tile", 4: "overlay"}.items():
        m = ok & (cls == k)
        if m.sum() < 20:
            continue
        r = float((step[m].mean() + e) / (nb[m].mean() + e))
        res[nm] = {"pairs": int(m.sum()), "step": round(float(step[m].mean()), 5),
                   "beside": round(float(nb[m].mean()), 5), "excess": round(r / max(ref, 1e-6), 3)}
    return res


RULER_M = 25.0      # a straight edge in the render longer than this (world metres) that isn't a border is a ruler line
RULER_FRAC = 0.4    # ... or crossing this share of the view's longer side
RULER_CONTRAST = 1.6  # ... and at least this much stronger (brightness gradient across it) than the view's median edge


def straight_lines(image, ids, kinds, fov=55.0, min_m=RULER_M, min_frac=RULER_FRAC, min_contrast=RULER_CONTRAST,
                   peaks=16):
    """Long straight edges in a rendered view that are no tile, overlay or silhouette border: what the eye reads as a
    seam although no border lies there (bedding one ruler-straight groove and tone step across a whole wall: "reads
    like a seam", with every border class at ~1.0). Canny edges on the render off borders and depth jumps, a Hough
    transform, and along each peak line its longest run of edge pixels (gaps under 1.5% of the width bridged); the
    run's length in world metres (the id pass's distance x the pixel's angle: fov across the image's longer side) and
    its contrast (mean brightness gradient across the line over the median at edge pixels of the view). Facet creases
    and joints are straight too but short: a rock feature longer than `min_m` in one straight line is geology drawn
    with a ruler; so is one crossing `min_frac` of a close view (40 m away the whole view is ~30 m wide). Returns
    {"lines": [{"length_m", "length_px", "angle" (deg, 0 = horizontal), "contrast", "from", "to" (px [x, y]),
    "ruler"}...] longest first, "rulers": how many are rulers (long and contrasted), "ok"}."""
    from skimage.feature import canny
    from skimage.transform import hough_line, hough_line_peaks
    L = _lum(image) if not isinstance(image, np.ndarray) else image
    I = np.load(ids) if not isinstance(ids, np.ndarray) else ids
    h, w = L.shape
    ch, cv = classes(I, kinds)
    bad = np.zeros((h, w), bool)  # silhouettes (depth jumps, sky) and tile / overlay borders
    for cl, sa, sb in ((ch, (slice(None), slice(0, -1)), (slice(None), slice(1, None))),
                       (cv, (slice(0, -1), slice(None)), (slice(1, None), slice(None)))):
        m = (cl == 0) | (cl == 3) | (cl == 4)
        bad[sa] |= m
        bad[sb] |= m
    bad |= I[..., 0] < 0.5
    bad = ndimage.binary_dilation(bad, iterations=4)
    edges = canny(L, sigma=2.0, low_threshold=0.02, high_threshold=0.05) & ~bad
    Ls = ndimage.gaussian_filter(L, 1.5)
    gy, gx = np.gradient(Ls)
    gm = np.hypot(gx, gy)
    med = float(np.median(gm[edges])) if edges.sum() > 50 else 1.0
    res = {"lines": [], "rulers": 0, "ok": True}
    if edges.sum() < 50:
        return res
    theta = np.deg2rad(np.arange(-90.0, 90.0, 0.25))
    H_, th_, di_ = hough_line(edges, theta=theta)
    near = ndimage.binary_dilation(edges, iterations=1)
    per_px = 2 * np.tan(np.deg2rad(fov) / 2) / max(h, w)  # radians a pixel (near the centre)
    dist = I[..., 2]
    gap = max(4, int(0.015 * w))
    for _, a, rho in zip(*hough_line_peaks(H_, th_, di_, num_peaks=peaks, min_distance=12, min_angle=4,
                                           threshold=0.15 * H_.max())):
        # the line x cos a + y sin a = rho, walked a pixel at a time across the image
        c, s = np.cos(a), np.sin(a)
        t = np.arange(-max(h, w) * 1.5, max(h, w) * 1.5, 1.0)
        xs, ys = rho * c - t * s, rho * s + t * c
        inside = (xs >= 0) & (xs <= w - 1) & (ys >= 0) & (ys <= h - 1)
        xs, ys = xs[inside], ys[inside]
        if len(xs) < 10:
            continue
        xi, yi = np.rint(xs).astype(int), np.rint(ys).astype(int)
        on = near[yi, xi]
        # the longest run of edge pixels with gaps up to `gap` bridged
        best, cur, last, start, bs = 0, 0, -10 ** 9, 0, 0
        idx = np.flatnonzero(on)
        for k in idx:
            if k - last > gap:
                start = k
            last = k
            if k - start + 1 > best:
                best, bs = k - start + 1, start
        if best < 10:
            continue
        seg = slice(bs, bs + best)
        sx, sy = xi[seg], yi[seg]
        ok = ~bad[sy, sx]
        if ok.sum() < 5:
            continue
        # the gradient across the line (its normal is (c, s) in x, y)
        across = np.abs(gx[sy, sx] * c + gy[sy, sx] * s)[ok]
        metres = float((dist[sy, sx][ok] * per_px).sum() * best / max(ok.sum(), 1))
        ang = (np.degrees(a) + 90.0) % 180.0
        ang = ang - 180.0 if ang > 90 else ang
        line = {"length_m": round(metres, 1), "length_px": int(best), "angle": round(float(ang), 1),
                "contrast": round(float(across.mean() / max(med, 1e-9)), 2),
                "from": [int(sx[0]), int(sy[0])], "to": [int(sx[-1]), int(sy[-1])]}
        line["ruler"] = bool((metres >= min_m or best >= min_frac * max(h, w)) and line["contrast"] >= min_contrast)
        res["lines"].append(line)
    res["lines"].sort(key=lambda q: -q["length_m"])
    res["rulers"] = sum(1 for q in res["lines"] if q["ruler"])
    res["ok"] = res["rulers"] == 0
    return res


def draw_lines(image, found, out):
    """The render with straight_lines' finds drawn: rulers magenta, shorter/weaker lines thin grey."""
    from PIL import Image, ImageDraw
    im = Image.open(image).convert("RGB")
    d = ImageDraw.Draw(im)
    for q in found["lines"]:
        r = q["ruler"]
        d.line([tuple(q["from"]), tuple(q["to"])], fill=(255, 0, 200) if r else (150, 150, 150), width=3 if r else 1)
    im.save(out)
    return out


GRID_KINK = 1.5  # colour kinks on the terrain's cell lines may be this much stronger than between them


def grid_squares(T, mats, rows=48, cells=24, seed=0) -> dict:
    """Squares locked to the terrain's grid: the colour's second difference along x and y (sampled at 1/8 cell over
    rock) at the cell lines against between them. A grid sampled bilinearly bends at every cell line (ratio 3-10: the
    per-cell tone showed as a quilt of cell-sized squares on the alps' rock); a smooth sampler has none (~1)."""
    rng = np.random.default_rng(seed)
    c = float(T.cell)
    gy, gx = np.gradient(T.H, c)
    steep = np.argwhere(np.hypot(gx, gy) > 1.0)  # (rock: where the colour's rock part shows)
    if len(steep) < 10:
        return {"ratio": 1.0, "ok": True, "note": "no rock"}
    pick = steep[rng.integers(0, len(steep), rows)]
    t = np.arange(-4, cells * 8 + 5) / 8.0
    num = den = 0.0
    on_line = (np.abs(t - np.round(t)) < 1e-9)[1:-1]
    for axis in (0, 1):
        for r, k in pick:
            x0, y0 = T.xs[0] + k * c, T.ys[0] + r * c
            xs = x0 + t * c if axis == 0 else np.full(len(t), x0 + 0.37 * c)
            ys = y0 + t * c if axis == 1 else np.full(len(t), y0 + 0.37 * c)
            P = np.c_[xs, ys, np.full(len(t), float(T.sample(np.array([[x0, y0]]))[0]))]
            N = np.tile([0.0, -0.94, 0.34], (len(t), 1))  # (a steep face: rock weight 1)
            _, col = mats.weights(P, N)
            d2 = np.abs(col[2:] - 2 * col[1:-1] + col[:-2]).sum(1)
            num += d2[on_line].mean()
            den += d2[~on_line].mean()
    ratio = float(num / max(den, 1e-12))
    return {"ratio": round(ratio, 2), "ok": ratio <= GRID_KINK}


def overlay(image, ids, kinds, out):
    """The render with its borders drawn from the id pass: tile borders red, the overlay's edge yellow, chart
    borders cyan (1 px, exact: no geometry lines to hide behind)."""
    from PIL import Image
    a = np.asarray(Image.open(image).convert("RGB")).copy()
    I = np.load(ids) if not isinstance(ids, np.ndarray) else ids
    ch, cv = classes(I, kinds)
    for k, col in ((2, (0, 230, 255)), (4, (255, 220, 0)), (3, (255, 30, 20))):
        m = np.zeros(a.shape[:2], bool)
        m[:, :-1] |= ch == k
        m[:-1, :] |= cv == k
        a[m] = col
    Image.fromarray(a).save(out)
    return out


def views(out_dir, rendered, job=None):
    """measure() and straight_lines() ("straight": the rulers and the five longest lines) for every view of a
    render_tiles job (the paths it returned)."""
    job = job or json.loads((Path(out_dir) / "render_job.json").read_text())
    fovs = {Path(v.get("out", "")).stem: v.get("fov", 55) for v in job.get("views", [])}
    res = {}
    for p in rendered:
        ids = Path(p).with_name(Path(p).stem + "_ids.npy")
        if ids.exists():
            res[Path(p).stem] = measure(p, ids, job["kinds"])
            sl = straight_lines(p, ids, job["kinds"], fov=fovs.get(Path(p).stem, 55))
            res[Path(p).stem]["straight"] = {"rulers": sl["rulers"], "ok": sl["ok"], "top": sl["lines"][:5]}
    return res


DENSITY_JUMP = 1.25  # neighbouring tiles' texel densities (same LOD) may differ by this factor at most


def texel_density(M) -> dict:
    """Texel density continuity across tile borders, from a manifest: per LOD the range of texels/m over the cliff
    tiles and the worst ratio between two neighbours. A tile whose atlas hit texture_max got a lower density than its
    neighbours: the same rock sharp on one side of a border and soft on the other, a square of blur from afar."""
    by = {(e["i"], e["j"]): e for e in M.get("tiles", [])}
    out, failures = {}, []
    lods = max((len(e["lods"]) for e in by.values()), default=0)
    for k in range(lods):
        d = {ij: e["lods"][k]["maps"]["texels_per_m"] for ij, e in by.items()
             if len(e["lods"]) > k and e["lods"][k] and (e["lods"][k].get("maps") or {}).get("texels_per_m")}
        if not d:
            continue
        worst, at = 1.0, None
        for (i, j), v in d.items():
            for n in ((i + 1, j), (i, j + 1)):
                if n in d:
                    r = max(v, d[n]) / max(min(v, d[n]), 1e-9)
                    if r > worst:
                        worst, at = r, [[i, j], list(n)]
        out[f"lod{k}"] = {"min": min(d.values()), "max": max(d.values()), "worst_neighbour_ratio": round(worst, 3),
                          "at": at}
        if worst > DENSITY_JUMP:
            failures.append(f"LOD {k}: texel density jumps x{worst:.2f} between tiles {at[0]} and {at[1]} "
                            f"({min(d.values()):g}-{max(d.values()):g} texels/m over the tiles)")
    return {"summary": out, "failures": failures}
