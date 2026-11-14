"""Views of a terrain: ground colours, the map image, the mask sheet, the mesh, the render. Part of terrain (terrain.py has the overview)."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from scipy import ndimage

from . import noise
from .terrain import smoothstep
from .terrain_model import Terrain

# ---------------------------------------------------------------- views
def _font(size):
    from PIL import ImageFont
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def ground_colours(T: Terrain, cover: bool = True) -> np.ndarray:
    """sRGB per cell: bare ground by slope and height, then each cover layer over it (its preview colour x
    density), water on top."""
    from . import terrain_design_cover
    slope = T._slope()
    hn = (T.H - T.H.min()) / max(np.ptp(T.H), 1)
    arid = T.world["kind"] in ("canyon", "dunes", "plateau")
    bare = np.array([0.66, 0.52, 0.36]) if arid else np.array([0.40, 0.47, 0.26])  # bare ground: sandstone or grass
    grass = bare * (1 - 0.3 * hn[..., None]) + np.array([0.10, 0.07, 0.02]) * hn[..., None]
    from .terrain_rock import base_colour
    rock = base_colour(T, slope, hn)
    w = smoothstep(28, 40, slope)[..., None]
    c = grass * (1 - w) + rock * w
    sea = getattr(T, "sea", None)
    if sea is not None:  # wet rock at the waterline: dark from the sea up to ~2 m (the same band as the 3D tiles')
        wet = smoothstep(2.2, 0.4, T.H - sea["level"]) * (T.H > sea["level"] - 1.0) * smoothstep(15, 30, slope)
        c = c * (1 - wet[..., None]) + np.array([0.17, 0.16, 0.15]) * wet[..., None]
    if cover:
        for name, m in T.cover.items():
            col = np.array(terrain_design_cover.cover_colour(T, name))
            a = np.clip(m, 0, 1)[..., None]  # density 1 covers the ground (at 85% black sand showed as grass)
            c = c * (1 - a) + col * a
    tone = (getattr(T, "rock", None) or {}).get("tone")
    if tone is not None:  # rock varies: pale buttresses, dark streaked gullies, patches (terrain_rock)
        c = c * (1 + (tone - 1) * smoothstep(38, 55, slope))[..., None]
    if "routes" in T.masks:  # the way itself: a worn, pale track (roads didn't show in any view)
        rd = np.clip(T.masks["routes"], 0, 1)[..., None] * 0.8
        c = c * (1 - rd) + (np.array([0.55, 0.47, 0.36]) if not arid else np.array([0.78, 0.66, 0.5])) * rd
    c[~np.isnan(T.water)] = [0.16, 0.28, 0.38]
    return c


def _nice(x):
    """1, 2 or 5 times a power of ten, near x."""
    e = 10 ** math.floor(math.log10(x))
    return min((1, 2, 5, 10), key=lambda m: abs(m * e - x)) * e


def map_image(T: Terrain, px: int = 1100, contour: float | None = None, labels: bool = True):
    """A plan view to reason on: hillshade over ground/cover colour, contours (index every 5th), rivers, ridges,
    divides, routes, sites, walls (red where climbable), names and a cover legend."""
    from PIL import Image, ImageDraw
    from skimage import measure
    from . import terrain_design_cover
    H = T.H
    contour = contour or _nice(max(np.ptp(H), 1) / 20)
    gy, gx = np.gradient(H, T.cell)
    az, el = math.radians(315), math.radians(40)
    L = np.array([math.cos(el) * math.sin(az), math.cos(el) * math.cos(az), math.sin(el)])
    n = np.stack([-gx, -gy, np.ones_like(H)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    shade = np.clip(n @ L, 0, 1)
    rgb = ground_colours(T) * (0.45 + 0.7 * shade[..., None])
    img = Image.fromarray((np.clip(rgb[::-1], 0, 1) * 255).astype(np.uint8))
    sc = px / img.width
    img = img.resize((px, int(img.height * sc)), Image.LANCZOS)
    d = ImageDraw.Draw(img)
    ny = H.shape[0]

    def to_px(x, y):
        return ((x - T.xs[0]) / T.cell * sc, (ny - 1 - (y - T.ys[0]) / T.cell) * sc)

    flat = T._slope() < 1.5  # a contour wandering over dead-flat ground (a mesa's caprock, a pad) is noise: a false ring
    for m in getattr(T, "mesas", {}).values():
        flat |= ndimage.binary_dilation(m["topmask"], iterations=1)
    for lev in np.arange(math.ceil(H.min() / contour) * contour, H.max(), contour):
        index = int(round(lev / contour)) % 5 == 0
        for cnt in measure.find_contours(H, lev):
            cnt = cnt[::2]
            on = ~flat[np.clip(np.round(cnt[:, 0]).astype(int), 0, ny - 1),
                       np.clip(np.round(cnt[:, 1]).astype(int), 0, H.shape[1] - 1)]
            lab, n = ndimage.label(on)
            for k in range(1, n + 1):
                pts = [(c[1] * sc, (ny - 1 - c[0]) * sc) for c in cnt[lab == k]]
                if len(pts) > 1:
                    d.line(pts, fill=(60, 40, 20) if index else (95, 75, 50), width=2 if index else 1)
    for Lr in T.lines.values():
        pts = [to_px(*p) for p in Lr.xy[::2]]
        if Lr.kind == "river":
            d.line(pts, fill=(40, 110, 200), width=3)
        elif Lr.kind == "flow":  # a lava flow: its path, dotted orange-red
            for a in range(0, len(pts) - 1, 6):
                d.line(pts[a:a + 2], fill=(220, 80, 30), width=2)
        elif Lr.kind == "rim":
            continue
        else:
            for a in range(0, len(pts) - 1, 4):
                d.line(pts[a:a + 3], fill=(120, 30, 30), width=2)
    if getattr(T, "_divide_mask", None) is not None:
        yy, xx = np.nonzero(T._divide_mask[::2, ::2])
        for y, x in zip(yy, xx):
            px_, py_ = to_px(T.xs[2 * x], T.ys[2 * y])
            d.point((px_, py_), fill=(150, 60, 60))
    for name, w in T.walls.items():
        for (x, y), ok in zip(w["boundary"], w["ok"]):
            px_, py_ = to_px(x, y)
            col = (70, 20, 20) if ok else (255, 40, 40)
            d.ellipse([px_ - 1.5, py_ - 1.5, px_ + 1.5, py_ + 1.5], fill=col)
    for name, R in T.routes.items():
        d.line([to_px(*p) for p in R.xy[::2]], fill=(235, 140, 20), width=3)
    f, fb = _font(15), _font(17)

    def label(xy, text, col=(0, 0, 0)):
        x, y = to_px(*xy)
        d.ellipse([x - 3, y - 3, x + 3, y + 3], fill=col)
        d.text((x + 6, y - 9), text, fill=col, font=f, stroke_width=2, stroke_fill=(255, 255, 255))

    if labels:
        for name, s in T.sites.items():
            x, y = to_px(*s["xy"])
            r = s["radius"] / T.cell * sc
            d.ellipse([x - r, y - r, x + r, y + r], outline=(160, 40, 160), width=2)
            label(s["xy"], f"{name} {s['level']:.0f}", (110, 20, 110))
        cols = T.spec.get("cols") or {}
        for name, (xy, h) in T.points.items():  # a col is labelled with the ground at it, a peak with its top
            label(xy, f"{name} {(T.height(xy) if name in cols else T.summit(name)):.0f}")
        for name, p in T.passes.items():
            label(p["xy"], f"{name} {T.height(np.array(p['xy'])):.0f}", (150, 70, 0))
        for name, m in getattr(T, "mesas", {}).items():
            label(m["xy"], f"{name} {float(np.median(T.H[m['topmask']])):.0f}")
        for Lr in T.lines.values():
            if Lr.kind == "river":
                label(Lr.at(0.5)[0], Lr.name, (20, 60, 150))
        for name, lf in (T.spec.get("landforms") or {}).items():
            if "_centre" in lf and name not in T.lakes:
                label(lf["_centre"], name, (90, 20, 90))
        for name, lk in T.lakes.items():
            label(lk["xy"], f"{name} {lk['level']:.0f}", (10, 50, 110))
        for name, R in T.routes.items():
            label(R.at(0.5)[0], name, (150, 70, 0))
        for name, it in (T.spec.get("intent") or {}).items():
            if "path" in it:
                d.line([to_px(*T.address(a)[0]) for a in it["path"]], fill=(235, 140, 20), width=1)
        W = img.width
        mu, un = T.units["mu"], T.units["name"]
        blen = _nice(T.size / mu / 4)  # in the spec's units
        bar = blen * mu * sc / T.cell
        d.rectangle([20, img.height - 30, 20 + bar, img.height - 22], fill=(0, 0, 0))
        d.text((24 + bar, img.height - 36), f"{blen:g} {un}", fill=(0, 0, 0), font=fb, stroke_width=2,
               stroke_fill=(255, 255, 255))
        d.text((W - 40, 12), "N", fill=(0, 0, 0), font=fb, stroke_width=2, stroke_fill=(255, 255, 255))
        d.polygon([(W - 34, 34), (W - 40, 50), (W - 28, 50)], fill=(0, 0, 0))
        d.text((20, 12), f"contours {contour / T.units['mu']:g} {T.units['name']}", fill=(0, 0, 0), font=f,
               stroke_width=2, stroke_fill=(255, 255, 255))
        y0 = 36
        for name in T.cover:
            col = tuple(int(255 * v) for v in terrain_design_cover.cover_colour(T, name))
            d.rectangle([20, y0, 36, y0 + 14], fill=col, outline=(0, 0, 0))
            d.text((42, y0 - 2), name, fill=(0, 0, 0), font=f, stroke_width=2, stroke_fill=(255, 255, 255))
            y0 += 20
    return img


def mask_sheet(T: Terrain, px: int = 360):
    """Every cover mask as a greyscale tile (white = 1) over faint hillshade, labelled: to judge each on its own."""
    from PIL import Image, ImageDraw
    gy, gx = np.gradient(T.H, T.cell)
    shade = np.clip(0.6 + 0.4 * (-gx + gy) / (np.hypot(gx, gy) + 0.3), 0, 1)
    tiles = []
    for name, m in T.cover.items():
        v = (0.25 * shade + 0.75 * np.clip(m, 0, 1))[::-1]
        im = Image.fromarray((v * 255).astype(np.uint8)).convert("RGB")
        im = im.resize((px, int(im.height * px / im.width)), Image.LANCZOS)
        from . import terrain_design_cover
        c = (T.spec.get("cover") or {}).get(name, {})
        lab = (f"{name} (~{c['count']} trees; each dot is one)" if c.get("count") and terrain_design_cover.tree_kind(T, name)
               else f"{name} ({100 * m.mean():.0f}%)")
        if c.get("count") and terrain_design_cover.tree_kind(T, name):  # a few trees' density is too faint to see: draw the mask full
            v = (0.25 * shade + 0.75 * np.clip(m / max(m.max(), 1e-6), 0, 1))[::-1]
            im = Image.fromarray((v * 255).astype(np.uint8)).convert("RGB")
            im = im.resize((px, int(im.height * px / im.width)), Image.LANCZOS)
        ImageDraw.Draw(im).text((8, 6), lab, fill=(255, 60, 60), font=_font(16),
                                stroke_width=2, stroke_fill=(0, 0, 0))
        tiles.append(im)
    if not tiles:
        return None
    cols = min(3, len(tiles))
    rows = math.ceil(len(tiles) / cols)
    sheet = Image.new("RGB", (cols * px, rows * tiles[0].height), (30, 30, 30))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % cols) * px, (i // cols) * tiles[0].height))
    return sheet


def write_mesh(T: Terrain, path, step: int = 1, up: int | None = None):
    """Grid mesh npz: verts, faces, linear colours, per-vertex tree densities; a water mesh for lakes. `up` (default 2
    for grids up to 700 cells a side) resamples the grid finer for the render only, cubic, kept within its neighbours'
    range: a 70 deg face is 2-3 cells across in plan and rendered as big flat triangles (crumpled paper)."""
    from . import terrain_design_cover
    H = T.H[::step, ::step]
    X, Y = T.X[::step, ::step], T.Y[::step, ::step]
    col = ground_colours(T)[::step, ::step]
    Wt = T.water[::step, ::step]
    if up is None:
        up = 2 if max(H.shape) <= 700 else 1
    if up > 1:
        ny0, nx0 = H.shape
        gy = np.linspace(0, ny0 - 1, (ny0 - 1) * up + 1)
        gx = np.linspace(0, nx0 - 1, (nx0 - 1) * up + 1)
        GY, GX = np.meshgrid(gy, gx, indexing="ij")
        lo = ndimage.map_coordinates(ndimage.minimum_filter(H, size=2, origin=-1), [np.floor(GY), np.floor(GX)], order=0)
        hi = ndimage.map_coordinates(ndimage.maximum_filter(H, size=2, origin=-1), [np.floor(GY), np.floor(GX)], order=0)
        H = np.clip(ndimage.map_coordinates(H, [GY, GX], order=3, mode="nearest"), lo, hi)
        X, Y = np.meshgrid(np.interp(gx, np.arange(nx0), X[0]), np.interp(gy, np.arange(ny0), Y[:, 0]))
        col = np.stack([ndimage.map_coordinates(col[..., k], [GY, GX], order=1) for k in range(3)], -1)
        wet0 = ~np.isnan(Wt)
        if wet0.any():
            _, (iy, ix) = ndimage.distance_transform_edt(~wet0, return_indices=True)
            lev = Wt[iy, ix]
        else:
            lev = np.zeros(Wt.shape)
        wetf = ndimage.map_coordinates(wet0.astype(float), [GY, GX], order=1) > 0.25
        Wt = np.where(wetf, ndimage.map_coordinates(lev, [GY, GX], order=1), np.nan)
    ny, nx = H.shape
    verts = np.stack([X.ravel(), Y.ravel(), H.ravel()], 1)
    i = np.arange(ny * nx).reshape(ny, nx)
    a, b, c, e = i[:-1, :-1].ravel(), i[:-1, 1:].ravel(), i[1:, 1:].ravel(), i[1:, :-1].ravel()
    # each quad split along its flatter diagonal (one diagonal everywhere striped every steep face with the same slant:
    # faces read as faintly triangulated close up)
    z = H.ravel()
    ac = np.abs(z[a] - z[c]) <= np.abs(z[b] - z[e])
    faces = np.concatenate([np.stack([a, b, c], 1)[ac], np.stack([a, c, e], 1)[ac],
                            np.stack([a, b, e], 1)[~ac], np.stack([b, c, e], 1)[~ac]])
    col = col.reshape(-1, 3)
    col = np.where(col <= 0.04045, col / 12.92, ((col + 0.055) / 1.055) ** 2.4)
    inst = terrain_design_cover.trees(T)  # the same instances the export writes
    # (hedge shrubs: the views draw each hedge as one continuous mass instead: strings of balls read as beads)
    shrub_l = [k for k, v in getattr(T, "tree_layers", {}).items() if v[1] == "shrub"]
    inst = inst[~np.isin(inst[:, 3], shrub_l)] if shrub_l else inst
    wet = ~np.isnan(Wt)
    wv = verts.copy()
    if wet.any():
        _, (iy, ix) = ndimage.distance_transform_edt(~wet, return_indices=True)  # levels differ along a river
        wv[:, 2] = Wt[iy, ix].ravel()
    q = (wet[:-1, :-1] | wet[:-1, 1:] | wet[1:, 1:] | wet[1:, :-1]).ravel()
    wf = np.concatenate([np.stack([a, b, c], 1)[q], np.stack([a, c, e], 1)[q]])
    # surf: white water where the sea is shallow over rocks and sand, broken up along the shore (the sea met the land
    # as a clean line, like a pond)
    foam = np.zeros(len(wv))
    if getattr(T, "sea", None) is not None and wet.any():
        depth = np.maximum(wv[:, 2] - verts[:, 2], 0)
        brk = noise.fbm(np.c_[verts[:, :2], np.full(len(verts), 5.0)], 6.0, 2, seed=91)
        foam = np.clip(1.0 - depth / 1.2, 0, 1) * np.clip(0.4 + 1.2 * brk, 0, 1)
    # stone walls and fences (below the grid): their lines on the ground, for the views' stand-ins
    lw_pts, lw_piece, lw_info = [], [], []
    for F in getattr(T, "features", {}).values():
        hedge = F["type"] == "hedge"
        if not (F.get("wall") or F.get("fence") or hedge):
            continue
        for xy in F["pieces"]:
            tg = np.gradient(xy, axis=0)
            tg /= np.linalg.norm(tg, axis=1, keepdims=True) + 1e-9
            nr = np.c_[-tg[:, 1], tg[:, 0]] * 0.5 * float(F["width"])
            # the ground under each side (a wall's foot follows it on a slope: one height stood as a slab over the drop)
            lw_pts.append(np.c_[xy, T.sample(xy), T.sample(xy + nr), T.sample(xy - nr)])
            lw_piece.append(np.full(len(xy), len(lw_info)))
            lw_info.append([float(F.get("height") or (2.2 if hedge else 1.2)), float(F["width"]),
                            2.0 if hedge else 1.0 if F.get("fence") else 0.0])
    extra = {}
    if lw_info:
        extra = {"lw_pts": np.vstack(lw_pts).astype(np.float32), "lw_piece": np.concatenate(lw_piece).astype(np.int32),
                 "lw_info": np.array(lw_info, np.float32)}
    np.savez(path, **extra, verts=verts.astype(np.float32), faces=faces.astype(np.int32), colors=col.astype(np.float32),
             wverts=wv.astype(np.float32), wfaces=wf.astype(np.int32), wfoam=foam.astype(np.float32),
             tree_xyz=inst[:, :3].astype(np.float32),
             tree_kind=np.array([getattr(T, "tree_layers", {}).get(int(i), ("", "broadleaf"))[1] for i in inst[:, 3]]),
             span=np.float32(max(np.ptp(T.X), np.ptp(T.Y))),
             # the ground beyond the frame: near its edge's height, not its lowest point (a plain far below read as a sea)
             base=np.float32(np.percentile(np.r_[T.H[0], T.H[-1], T.H[:, 0], T.H[:, -1]], 30)),
             sea=np.float32(T.sea["level"] if getattr(T, "sea", None) else np.nan),
             markers=np.array([[*st["xy"], st["level"]] for st in T.sites.values() if not st.get("prop")],
                              np.float32).reshape(-1, 3),
             props=np.array([[*st["xy"], T.height(np.array(st["xy"])), st["prop"]["yaw"]] for st in T.sites.values()
                             if st.get("prop")], np.float32).reshape(-1, 4),
             prop_names=np.array([st["prop"]["name"] for st in T.sites.values() if st.get("prop")]))


def render(T: Terrain, out_dir, views: list[dict], size=(1200, 700), samples=24):
    """Perspective Cycles renders: views are {"name", "eye": address | [x, y, z], "lift": m, "look": address, "fov",
    "sun"} (terrain_sun: auto picks a raking sun per view)."""
    import subprocess
    from . import terrain_sun
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    mesh = out_dir / "terrain_mesh.npz"
    write_mesh(T, mesh)
    jobs = []
    T.view_notes = []
    for v in views:
        exy, eh, _ = T.address(v["eye"])
        if isinstance(v["eye"], list) and len(v["eye"]) == 3:
            eh = v["eye"][2]
        wl = T.water.ravel()[int(np.clip(round((exy[1] - T.ys[0]) / T.cell), 0, len(T.ys) - 1)) * len(T.xs)
                                           + int(np.clip(round((exy[0] - T.xs[0]) / T.cell), 0, len(T.xs) - 1))]
        if np.isfinite(wl) and not (isinstance(v["eye"], list) and len(v["eye"]) == 3):
            eh = max(eh, float(wl))  # over water the eye stands on its surface, not on the bed (it rendered underwater)
        ez = eh + v.get("lift", 2)
        # never inside the ground: at least a person's eye above the highest ground within a few cells (on a slope the
        # ground beside the eye is higher than under it, and the near plane cut through it)
        near = np.hypot(T.X - exy[0], T.Y - exy[1]) <= 2.5 * T.cell
        floor = float(T.H[near].max()) if near.any() else T.height(exy)
        if ez < floor + 1.0:
            T.view_notes.append(f"view {v['name']!r}: the eye stood {ez - floor:.1f} m over the highest ground within "
                                f"{2.5 * T.cell:.0f} m (a slope beside it): lifted {floor + 1.7 - ez:.1f} m, to "
                                f"{floor + 1.7:.0f} m above sea level")

            ez = floor + 1.7
        txy, th, _ = T.address(v["look"])
        # and not facing a wall: the first stretch toward what it looks at must clear the ground (an eye clear of the
        # ground under it but a few metres from a cliff rendered black)
        dvec = np.array(txy) - np.array(exy)
        dist = float(np.linalg.norm(dvec))
        if dist > 1:
            ds = np.arange(T.cell, min(60.0, 0.3 * dist), T.cell / 2)
            if len(ds):
                pts = np.array(exy) + dvec / dist * ds[:, None]
                ray = ez + (th - ez) * ds / dist
                need = float((T.sample(pts) + 1.0 - ray).max())
                if need > 0:
                    T.view_notes.append(f"view {v['name']!r}: the ground just ahead toward {v['look']!r} was in the way: "
                                        f"the eye was raised {need:.0f} m to see past it")
                    ez += need
        sb, sh, snote = terrain_sun.for_view(T, v, [*exy, ez], [*txy, th])
        T.view_notes.append(f"view {v['name']!r}: {snote}")
        jobs.append({"eye": [*exy, ez], "look": [*txy, th], "fov": v.get("fov", 60), "sun": [sb, sh],
                     "out": str(out_dir / f"{v['name']}.png")})
    job = out_dir / "job.json"
    job.write_text(json.dumps({"mesh": str(mesh), "views": jobs, "size": size, "samples": samples}))
    script = Path(__file__).with_name("blender_terrain.py")
    from . import resources
    with resources.heavy(f"terrain views {Path(out_dir).name}", gb=6, gpu=True):  # (C445: one GPU render at a time)
        r = subprocess.run(["blender", "-b", "--factory-startup", "--python", str(script), "--", str(job)],
                           capture_output=True, text=True)
    if r.returncode or "Traceback" in r.stdout + r.stderr:  # Blender exits 0 after a Python error
        raise RuntimeError(r.stderr[-2000:] + r.stdout[-3000:])
    return [j["out"] for j in jobs]
