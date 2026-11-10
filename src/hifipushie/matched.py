"""Matched views: look at a model from the camera its concept image was drawn from, and cut the same feature
tiles from both, so the LOOK gate compares like with like (gap from Baynard Racing's Puddles, 2026-11-06).

Why: a camera picked by eye, or a silhouette overlay, shows what the author meant, not what is there. Puddles'
arms, ears and tail went many rounds that way (an arm welded along the side, ears on stalks, the wrong fold);
once the concept's own camera was fitted and named feature tiles went to the blind review, one round found it.

- `fit_camera(name, image)`: the perspective camera (azimuth, elevation, roll, focal length, aim) whose
  silhouette of the model best overlaps the image's foreground (IoU). Conventions as `render.VIEWS`: azimuth 0 =
  from the front (-Y), positive = round toward the creature's left (+X); elevation positive = from above; roll
  positive = the camera turned anticlockwise. The camera sits `dist` m from its aim (default 3 x the model's
  largest extent); `f_px` is the focal length in pixels at the image's own size. Saved as
  <model>/cameras/<label>.json with the image's path. Start: a coarse azimuth / elevation sweep, each start's
  scale and aim set from the bounding boxes, then Nelder-Mead from the best few, polished at a finer raster.
- `render(name, label)`: the model from that camera at the image's own size, in form-revealing clay (big area
  lights, no hard shadows): pixel-aligned with the image, so the same box crops the same feature from both.
- `tiles(name, label, features)`: named, same-box feature tiles from the image and the matched render, each
  feature boxed from its parts' / elements' bounds through the camera (or a pixel box), squared, padded and
  scaled up to >= `min_px`: ready for bin/review, one region per pair.
- `look_camera(cam)`: the fitted camera as a `look` camera ({"eye", "target", "fov", "up"}).
"""
from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import store

WORK = 256  # fit raster width (px); the polish runs at 2 x


# ---------------------------------------------------------------- the image's foreground

def mask_of(image: str | Path, mask: str | Path | None = None, threshold: float = 30.0) -> np.ndarray:
    """The figure's foreground: a given mask image (white = figure), else the image's alpha, else every pixel that
    is NOT background connected to the border (background: within `threshold` of the border's median colour), with
    holes filled. Concept renders on a grey sweep pass; a busy background needs a mask."""
    from scipy import ndimage
    if mask:
        return np.asarray(Image.open(mask).convert("L")) > 127
    im = Image.open(image)
    if im.mode in ("RGBA", "LA") or "transparency" in im.info:
        return np.asarray(im.convert("RGBA"))[..., 3] > 127
    rgb = np.asarray(im.convert("RGB")).astype(float)
    border = np.median(np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]]), 0)
    # background = the border's hue at any brightness, flooded only across soft gradients: a soft floor shadow is
    # eaten, the figure's sharp edge stops the flood (grey hooves survive inside it). Puddles: IoU 0.96 with a
    # hand-made mask; what's left is the hard contact shadow between the feet.
    chroma = np.linalg.norm((rgb - rgb.mean(-1, keepdims=True)) - (border - border.mean()), axis=-1)
    lum = ndimage.gaussian_filter(rgb.mean(-1), 1.0)
    grad = np.hypot(ndimage.sobel(lum, 0), ndimage.sobel(lum, 1)) / 8
    near = (chroma < threshold * 0.6) & (grad < 8)
    lab, _ = ndimage.label(near)
    edge = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    bg = np.isin(lab, edge[edge > 0])
    # the flood stops where the blurred gradient rises, a pixel or two outside the edge: background-coloured pixels
    # next to it are background too (the figure's own colour, or a dark hoof, stays)
    like = (chroma < threshold * 0.6) & (np.abs(rgb.mean(-1) - border.mean()) < 15)
    for _ in range(3):
        bg |= like & ndimage.binary_dilation(bg)
    fg = ndimage.binary_fill_holes(ndimage.binary_opening(~bg, iterations=2))
    lab, n = ndimage.label(fg)
    if n > 1:  # the figure is the biggest piece (drop specks, a signature)
        sizes = ndimage.sum(fg, lab, range(1, n + 1))
        fg = np.isin(lab, 1 + np.flatnonzero(sizes >= 0.05 * sizes.max()))
    if not fg.any():
        raise ValueError(f"{image}: no foreground found against the border colour (pass mask=<white-on-black png>)")
    return fg


# ---------------------------------------------------------------- the camera

def axes(az: float, el: float, roll: float):
    """(D aim -> camera, forward, right, up) for the conventions above."""
    a, e, r = np.radians([az, el, roll])
    D = np.array([np.sin(a) * np.cos(e), -np.cos(a) * np.cos(e), np.sin(e)])
    Fw = -D
    R = np.cross(Fw, [0, 0, 1.0])
    R /= np.linalg.norm(R)
    U = np.cross(R, Fw)
    return D, Fw, np.cos(r) * R + np.sin(r) * U, -np.sin(r) * R + np.cos(r) * U


def project(P: np.ndarray, cam: dict, size=None):
    """World points -> (pixel xy at `size` (default the camera's), depth)."""
    D, Fw, R, U = axes(cam["az"], cam["el"], cam["roll"])
    W, H = size or cam["size"]
    f = cam["f_px"] * W / cam["size"][0]
    p = P - (np.asarray(cam["aim"]) + cam["dist"] * D)
    z = np.maximum(p @ Fw, 1e-6)
    return np.stack([W / 2 + (p @ R) / z * f, H / 2 - (p @ U) / z * f], 1), z


def _splat(xy: np.ndarray, size) -> np.ndarray:
    """A silhouette from projected surface samples (a closed surface's front covers its whole outline)."""
    from scipy import ndimage
    W, H = size
    ij = np.round(xy).astype(int)
    ok = (ij[:, 0] >= 0) & (ij[:, 0] < W) & (ij[:, 1] >= 0) & (ij[:, 1] < H)
    m = np.zeros((H, W), bool)
    m[ij[ok, 1], ij[ok, 0]] = True
    return ndimage.binary_fill_holes(ndimage.binary_closing(m, iterations=2))


def _samples(mesh: Path) -> np.ndarray:
    with np.load(mesh) as z:
        v, f = z["verts"].astype(float), z["faces"]
    return np.concatenate([v, v[f].mean(1)])


def look_camera(cam: dict) -> dict:
    """The fitted camera as a `look` camera (eye, target, fov across, up: the roll)."""
    D, _, _, U = axes(cam["az"], cam["el"], cam["roll"])
    aim = np.asarray(cam["aim"], float)
    fov = math.degrees(2 * math.atan(cam["size"][0] / 2 / cam["f_px"]))
    return {"eye": (aim + cam["dist"] * D).tolist(), "target": aim.tolist(), "fov": fov, "up": U.tolist(),
            "name": cam.get("label", "fitted")}


def cam_path(name: str, label: str) -> Path:
    return store._dir(name) / "cameras" / f"{label}.json"


def load_camera(name: str, label: str = "concept") -> dict:
    p = cam_path(name, label)
    if not p.exists():
        have = sorted(q.stem for q in p.parent.glob("*.json")) if p.parent.exists() else []
        raise ValueError(f"{name} has no fitted camera {label!r} (have {have}); fit_concept_camera first")
    return json.loads(p.read_text())


def fit_camera(name: str, image: str, mask: str | None = None, label: str = "concept", resolution: int = 96,
               az: float | None = None, el: float | None = None, dist: float | None = None) -> dict:
    """Fit and save the concept's camera (module docstring). az / el: a starting guess (default: a sweep)."""
    from scipy.optimize import minimize
    meta = store.build(name, resolution)
    P = _samples(Path(meta["mesh"]))
    ref = mask_of(image, mask)
    H0, W0 = ref.shape
    lo, hi = P.min(0), P.max(0)
    dist = float(dist or 3 * (hi - lo).max())
    small = (WORK, max(8, round(H0 * WORK / W0)))
    refs = {}

    def ref_at(size):
        if size not in refs:
            refs[size] = np.asarray(Image.fromarray(ref.astype(np.uint8) * 255).resize(size, Image.BILINEAR)) > 127
        return refs[size]

    def cam_of(x):
        return {"az": float(x[0]), "el": float(x[1]), "roll": float(x[2]), "f_px": float(x[3]),
                "aim": [float(v) for v in x[4:7]], "dist": dist, "size": [W0, H0]}

    def iou(x, size):
        m, R = _splat(project(P, cam_of(x), size)[0], size), ref_at(size)
        return (m & R).sum() / max((m | R).sum(), 1)

    ys, xs = np.nonzero(ref)
    rbox = np.array([xs.min(), ys.min(), xs.max(), ys.max()], float)

    def start(a, e):  # scale and aim from the bounding boxes
        x = np.array([a, e, 0.0, 1000.0, *((lo + hi) / 2)])
        for _ in range(3):
            xy = project(P, cam_of(x))[0]
            b = np.r_[xy.min(0), xy.max(0)]
            x[3] *= (rbox[3] - rbox[1]) / max(b[3] - b[1], 1e-6)
            xy = project(P, cam_of(x))[0]
            b = np.r_[xy.min(0), xy.max(0)]
            _, _, R, U = axes(x[0], x[1], x[2])
            z = float(np.median(project(P, cam_of(x))[1]))
            dx = ((rbox[0] + rbox[2]) - (b[0] + b[2])) / 2 * z / x[3]
            dy = ((rbox[1] + rbox[3]) - (b[1] + b[3])) / 2 * z / x[3]
            x[4:7] -= dx * R - dy * U
        return x

    sweep = [(a, e) for a in ([az] if az is not None else range(-60, 61, 15))
             for e in ([el] if el is not None else (0, 10, 25))]
    scored = sorted((-iou(s, small), i, s) for i, s in enumerate(start(a, e) for a, e in sweep))
    fine = (2 * WORK, max(8, round(H0 * 2 * WORK / W0)))

    def descend(x0, size, k):  # Nelder-Mead from x0; k scales the first steps
        steps = k * np.array([6, 4, 3, 0.06 * x0[3], *(0.03 * (hi - lo).max(),) * 3])
        return minimize(lambda x: -iou(x, size), x0, method="Nelder-Mead",
                        options={"maxiter": 500, "xatol": 0.01, "fatol": 1e-4,
                                 "initial_simplex": np.vstack([x0, x0 + np.diag(steps)])})
    # A symmetric model's silhouette from az is nearly the mirror of the one from -az, so the IoU barely tells the
    # sides apart (Puddles: 0.93 vs 0.926). Each side is fitted on its own and the better kept; a close call is
    # flagged ("mirror"): check which way the face turns in the matched render and pass az with the right sign.
    branches = []
    for side in ((-1, 1) if az is None else (np.sign(az) or 1,)):
        mine = [t for t in scored if np.sign(t[2][0]) in (side, 0)][:2]
        if not mine:
            continue
        b = min((descend(x0, small, 1.0) for _, _, x0 in mine), key=lambda r: r.fun)
        branches.append(descend(b.x, fine, 0.3))
    branches.sort(key=lambda r: r.fun)
    r = branches[0]
    cam = cam_of(r.x)
    other = [{"az": round(float(b.x[0]), 1), "iou": round(-float(b.fun), 4)} for b in branches[1:]]
    cam.update(mirror=other[0] if other and other[0]["iou"] > -float(r.fun) - 0.015 else None,
               iou=round(-float(r.fun), 4), image=str(Path(image).expanduser().resolve()), label=label,
               mask=str(Path(mask).expanduser().resolve()) if mask else None, resolution=resolution)
    p = cam_path(name, label)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cam, indent=1))
    return cam


def overlay(name: str, cam: dict, resolution: int = 96, width: int = 512) -> Image.Image:
    """The image with the fitted silhouette's disagreement: red = model only, blue = image only."""
    meta = store.build(name, resolution)
    W0, H0 = cam["size"]
    size = (width, max(8, round(H0 * width / W0)))
    m = _splat(project(_samples(Path(meta["mesh"])), cam, size)[0], size)
    R = np.asarray(Image.fromarray(mask_of(cam["image"], cam.get("mask")).astype(np.uint8) * 255)
                   .resize(size, Image.BILINEAR)) > 127
    im = np.asarray(Image.open(cam["image"]).convert("RGB").resize(size)).astype(float) * 0.6 + 0.4 * 255
    im[m & ~R] = (220, 40, 40)
    im[R & ~m] = (40, 90, 230)
    return Image.fromarray(im.astype(np.uint8))


# ---------------------------------------------------------------- the matched render

def render(name: str, label: str = "concept", resolution: int = 192, samples: int = 32,
           colour=(0.62, 0.36, 0.3), only_parts=None, hide_parts=None, out: str | None = None) -> Path:
    """The model from the fitted camera, pixel-aligned with the image (module docstring). Returns the PNG."""
    from . import render as rendermod
    cam = load_camera(name, label)
    meta = store.build(name, resolution)
    mesh = Path(meta["mesh"])
    if only_parts or hide_parts:
        with np.load(mesh) as z:
            built = [str(n) for n in z["part_names"]]
        bad = [p for p in (only_parts or []) + (hide_parts or []) if p not in built]
        if bad:
            raise ValueError(f"no part(s) {bad}; parts: {built}")
        keep = [p for p in built if (not only_parts or p in only_parts) and p not in (hide_parts or [])]
        mesh = store.view_mesh(mesh, keep, [], None)
    dst = Path(out).expanduser() if out else cam_path(name, label).with_name(f"{label}_render.png")
    dst.parent.mkdir(parents=True, exist_ok=True)
    job = dst.with_suffix(".job.json")
    lo, hi = np.asarray(meta["bounds"][0]), np.asarray(meta["bounds"][1])
    job.write_text(json.dumps({**cam, "mesh": str(mesh), "out": str(dst), "samples": int(samples),
                               "colour": list(colour), "extent": float((hi - lo).max())}))
    script = Path(__file__).with_name("blender_matched.py")
    r = subprocess.run([rendermod.BLENDER, "-b", *rendermod._threads(), "--factory-startup", "--python", str(script),
                        "--", str(job)], capture_output=True, text=True, timeout=900)
    job.unlink(missing_ok=True)
    if r.returncode or not dst.exists():
        raise RuntimeError(f"matched render failed:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
    return dst


def pair(name: str, label: str = "concept", width: int = 512) -> Image.Image:
    """Image | matched render side by side, at `width` each (for the author and Joe; reviews take tiles)."""
    cam = load_camera(name, label)
    a = Image.open(cam["image"]).convert("RGB")
    b = Image.open(cam_path(name, label).with_name(f"{label}_render.png")).convert("RGB")
    h = round(a.height * width / a.width)
    out = Image.new("RGB", (2 * width + 8, h), "white")
    out.paste(a.resize((width, h)), (0, 0))
    out.paste(b.resize((width, h)), (width + 8, 0))
    return out


# ---------------------------------------------------------------- feature tiles

def feature_box(name: str, cam: dict, what, pad: float = 0.2) -> list[int]:
    """A square pixel box (image pixels) round a feature: [x0, y0, x1, y1] given, or the built surface on the named
    elements (prim names, ".L" / ".R" as named) or parts, projected through the camera, padded by `pad`."""
    if isinstance(what, (list, tuple)) and len(what) == 4 and all(isinstance(v, (int, float)) for v in what):
        x0, y0, x1, y1 = (float(v) for v in what)
    else:
        from .spec import compile_prims
        names = [what] if isinstance(what, str) else list(what)
        prims = compile_prims(store.load(name))
        sel = [p for p in prims if p.name in names or p.part in names]
        if not sel:
            raise ValueError(f"no element or part named {names}; e.g. {sorted({p.name for p in prims})[:20]}")
        from . import sdf
        with np.load(store.build(name, int(cam.get("resolution", 96)))["mesh"]) as z:
            V = z["verts"].astype(float)
        # the built surface on (or inside) these elements: prim bounds carry the blend's reach and boxed
        # Puddles' ear three times too big
        on = V[sdf.field_at(sel, V, clip=False) < 0.004]
        if not len(on):
            raise ValueError(f"{names}: no built surface on them (hidden inside the rest?)")
        xy = project(on, cam)[0]
        (x0, y0), (x1, y1) = xy.min(0), xy.max(0)
    c, s = np.array([(x0 + x1) / 2, (y0 + y1) / 2]), max(x1 - x0, y1 - y0) * (1 + 2 * pad) / 2
    W, H = cam["size"]
    s = min(s, W / 2, H / 2)
    c = np.clip(c, s, [W - s, H - s])
    n = int(round(2 * s))
    x0, y0 = int(round(c[0] - s)), int(round(c[1] - s))
    return [x0, y0, x0 + n, y0 + n]


def tiles(name: str, features: dict, label: str = "concept", out_dir: str | None = None, min_px: int = 448,
          pad: float = 0.2) -> dict:
    """Named, same-box tiles from the image and the matched render (module docstring). features: {region name:
    element / part names or a pixel box}. Region names are what the reviewer reads: plain words, no numbers.
    Returns {"dir", "tiles": {region: [ref, ours, box]}, "review": the bin/review command}."""
    cam = load_camera(name, label)
    rpath = cam_path(name, label).with_name(f"{label}_render.png")
    if not rpath.exists():
        raise ValueError(f"no matched render for {label!r} yet: look_matched first")
    ref, ours = Image.open(cam["image"]).convert("RGB"), Image.open(rpath).convert("RGB")
    if ref.size != ours.size:
        raise ValueError(f"the render ({ours.size}) is not the image's size ({ref.size}): render it again")
    d = Path(out_dir).expanduser() if out_dir else cam_path(name, label).parent / f"{label}_tiles"
    d.mkdir(parents=True, exist_ok=True)
    out, args = {}, []
    for region, what in features.items():
        box = feature_box(name, cam, what, pad)
        side = max(min_px, box[2] - box[0])
        slug = "".join(ch if ch.isalnum() else "_" for ch in region.lower()).strip("_")
        pa, pb = d / f"{slug}_ref.png", d / f"{slug}_ours.png"
        ref.crop(box).resize((side, side), Image.LANCZOS).save(pa)
        ours.crop(box).resize((side, side), Image.LANCZOS).save(pb)
        out[region] = [str(pa), str(pb), box]
        args.append(f'"{region}={pa}:{pb}"')
    cmd = (f"/mnt/data/hifipushie/bin/review {d / 'review'} " + " ".join(args)
           + ' --context "<one neutral line: what kind of thing this is>"')
    return {"dir": str(d), "tiles": out, "review": cmd}
