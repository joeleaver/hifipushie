"""Hemi-octahedral impostors: the plant baked from N x N directions over the upper hemisphere into one atlas, drawn by
the engine as ONE camera-facing quad whose shader picks and blends the views nearest the camera's direction.

Why: two crossed quads hold only from the side; from a hill looking down 17 deg they read as a cross (an orange bird
in autumn). What engines do (Ryan Brucks' octahedral impostors for UE, https://shaderbits.com/blog/octahedral-impostors;
Amplify Impostors, https://amplify.pt/_AI; the Godot port https://github.com/SIsilicon/Godot-Octahedral-Impostors):
views on an octahedral grid, the hemisphere variant for things never seen from below (twice the resolution of the
full sphere for the same frames), and blending of the neighbouring frames so the picture never pops.

Conventions (glTF object space: +Y up, the plant's foot at the origin; everything here is in that space):
- a direction d (unit, d.y >= 0, from the bake centre TOWARD the camera) <-> hemi-oct coordinates (u, v) in [-1, 1]^2:
  s = |d.x| + |d.y| + |d.z|; px = d.x / s, pz = d.z / s; u = px + pz, v = px - pz. Back: px = (u + v) / 2,
  pz = (u - v) / 2, d = normalize(px, 1 - |px| - |pz|, pz). The square's border is the horizon.
- frame (i, j), i, j = 0 .. N-1: (u, v) = (2 i / (N - 1) - 1, 2 j / (N - 1) - 1) (frames on the grid's corners: the
  horizon views are baked exactly); in the atlas frame (i, j) is column i, row j (row 0 at the top of the image).
- a frame's picture: an orthographic view along -d through the centre C, `size` m square, image right = R(d) =
  normalize(cross(+Y, d)) (+X when cross is ~0), image up = U(d) = cross(d, R). A point p lands at
  fu = dot(p - C, R) / size + 0.5, fv = 0.5 - dot(p - C, U) / size (texture v down, as glTF uv).
- maps: albedo (sRGB, alpha = coverage) with the shade of what stands above baked in (as the crossed quads), and an
  OBJECT-SPACE normal map (rgb = n * 0.5 + 0.5, glTF axes; not tangent space: the quad turns with the camera)."""

from __future__ import annotations

import math

import numpy as np

FRAMES = 8   # 8 x 8 = 64 views (Amplify's default for trees; at 256 px a frame the atlas is 2048)
FRAME_PX = 256
KIND = "hemi_octahedral"
SHADER = "spikes/godot_veg/impostor_octa.gdshader"


def encode(d: np.ndarray) -> np.ndarray:
    d = np.atleast_2d(np.asarray(d, float))
    d = np.c_[d[:, 0], np.maximum(d[:, 1], 0.0), d[:, 2]]
    s = np.abs(d).sum(1, keepdims=True)
    p = d / np.maximum(s, 1e-12)
    return np.c_[p[:, 0] + p[:, 2], p[:, 0] - p[:, 2]]


def decode(uv: np.ndarray) -> np.ndarray:
    uv = np.atleast_2d(np.asarray(uv, float))
    px, pz = 0.5 * (uv[:, 0] + uv[:, 1]), 0.5 * (uv[:, 0] - uv[:, 1])
    d = np.c_[px, 1 - np.abs(px) - np.abs(pz), pz]
    return d / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-12)


def basis(d: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(right, up) of the view from direction d (rows)."""
    d = np.atleast_2d(d)
    r = np.cross(np.array([0, 1.0, 0])[None], d)
    n = np.linalg.norm(r, axis=1, keepdims=True)
    r = np.where(n > 1e-5, r / np.maximum(n, 1e-12), np.array([1.0, 0, 0])[None])
    return r, np.cross(d, r)


def frame_dirs(n: int = FRAMES) -> np.ndarray:
    """(n, n, 3): frame (i, j)'s direction, [i, j] = column i, row j."""
    g = 2 * np.arange(n) / (n - 1) - 1
    U, V = np.meshgrid(g, g, indexing="ij")
    return decode(np.c_[U.ravel(), V.ravel()]).reshape(n, n, 3)


def to_blender(v) -> list:
    v = np.asarray(v, float)
    return [float(v[0]), float(-v[2]), float(v[1])]


def bounds(tree: dict) -> tuple[np.ndarray, float]:
    """The bake centre (glTF) and the frames' size (m): a sphere round all the plant's wood and foliage from C."""
    P = np.asarray(tree["pos"], float)
    H = float(tree["height"])
    C = np.array([0.0, 0.5 * H, 0.0])
    Pg = np.c_[P[:, 0], P[:, 2], -P[:, 1]]
    r = float(np.percentile(np.linalg.norm(Pg - C, axis=1), 99.8))
    reach = 0.0
    try:
        from . import veg_leaf
        reach = float({**veg_leaf.TWIG, **((tree["spec"].get("leaves") or {}).get("twig") or {})}.get("length", 0.3))
    except Exception:
        pass
    r = max(r + reach, 0.5 * H) * 1.04
    return C, 2 * r


def jobs(tree: dict, tmp: str, n: int = FRAMES, px: int = FRAME_PX, kinds=("albedo", "normal", "shade", "depth")) -> tuple[list, np.ndarray, float]:
    C, size = bounds(tree)
    D = frame_dirs(n).reshape(-1, 3)
    R, U = basis(D)
    out = []
    for kind in kinds:
        for k in range(len(D)):
            out.append({"out": f"{tmp}/{kind}_{k:03d}.png", "size": [px, px], "azimuth": 0, "elevation": 0, "focus": to_blender(C), "span": size,
                        "leaves": True, "transparent": True, "no_ground": True, "pass": kind, "samples": 8,
                        "depth_range": [1.5 * size, 2.5 * size],
                        "basis": {"centre": to_blender(C), "right": to_blender(R[k]), "up": to_blender(U[k]), "back": to_blender(D[k]), "dist": 2.0 * size}})
    return out, C, size


def maps(albedo: list, normal: list, shade: list, n: int, shade_amount: float = 0.5, shade_bright: float = 0.7, depth: list | None = None) -> dict:
    """The atlas (n*px square) from the per-frame unlit passes (frame k = i * n + j: column i, row j): albedo sRGB with
    the baked shade and alpha, the object-space normal map (glTF axes), colour bled under the alpha."""
    from scipy import ndimage
    from .veg_export import _bleed
    px = albedo[0].shape[0]
    A = np.zeros((n * px, n * px, 4), np.float32)
    Nm = np.zeros((n * px, n * px, 4), np.float32)
    for k, (a, nw, sh) in enumerate(zip(albedo, normal, shade)):
        i, j = divmod(k, n)
        solid = a[..., 3] > 0.5
        got = sh[..., 3] > 0.05
        s_ = ndimage.gaussian_filter(_bleed(np.where(got, sh[..., 0], 1.0), got), 1.2)
        val = np.clip((a[..., :3].max(-1) - 0.35) / 0.5, 0, 1)
        kk = shade_amount * (1 - shade_bright * val * val * (3 - 2 * val))
        lin_ = np.where(a[..., :3] <= 0.04045, a[..., :3] / 12.92, ((a[..., :3] + 0.055) / 1.055) ** 2.4) * (1 - kk + kk * s_)[..., None]
        rgb = np.where(lin_ <= 0.0031308, lin_ * 12.92, 1.055 * np.maximum(lin_, 0) ** (1 / 2.4) - 0.055)
        nb = nw[..., :3] * 2 - 1  # Blender world (x, y, z) -> glTF (x, z, -y)
        ng = np.stack([nb[..., 0], nb[..., 2], -nb[..., 1]], -1)
        ng /= np.maximum(np.linalg.norm(ng, axis=-1, keepdims=True), 1e-6)
        ng = _bleed(ng, solid & (nw[..., 3] > 0.5)) if (solid & (nw[..., 3] > 0.5)).any() else np.tile([0, 1.0, 0], ng.shape[:2] + (1,))
        sl = (slice(j * px, (j + 1) * px), slice(i * px, (i + 1) * px))
        A[sl] = np.dstack([_bleed(rgb, solid) if solid.any() else rgb, a[..., 3]])
        if depth is not None:  # alpha = depth: 0 at the front of the bake sphere .. 1 at its back, 0.5 = the frame's middle plane
            dz = depth[k][..., 0]
            okd = solid & (depth[k][..., 3] > 0.5)
            dz = _bleed(dz, okd) if okd.any() else np.full_like(dz, 0.5)
        else:
            dz = np.full(a.shape[:2], 0.5)
        Nm[sl] = np.dstack([ng * 0.5 + 0.5, dz])
    return {"image": A, "normal": Nm}


def geometry_key(spec: dict, season: str | None) -> tuple:
    """Seasons whose plant has the same shape (so the same normal, depth and shade frames): in leaf or bare, and a
    realistic spring (smaller leaves) on its own."""
    from . import veg_style
    se = season or spec.get("season", "summer")
    st = veg_style.sheet(spec)
    bare = veg_style.season_color(spec, "winter" if se == "snow" else se, st) is None
    return (bare, se == "spring" and st is None)


def bake(tree: dict, n: int = FRAMES, px: int = FRAME_PX, geometry: dict | None = None, **over) -> dict:
    """Render the frames (Blender: three unlit passes each, as the crossed quads' pictures) and lay them out:
    {"image", "normal", "frames", "size", "centre" (glTF), "kind"}."""
    import tempfile
    from PIL import Image
    from . import veg_look
    with tempfile.TemporaryDirectory(prefix="hifipushie-octa-") as tmp:
        J, C, size = jobs(tree, tmp, n, px, ("albedo",) if geometry else ("albedo", "normal", "shade", "depth"))
        veg_look.render(tree, J, timeout=3600)
        rd = lambda kind: [np.asarray(Image.open(f"{tmp}/{kind}_{k:03d}.png").convert("RGBA"), np.float32) / 255 for k in range(n * n)]
        passes = geometry or {k_: rd(k_) for k_ in ("normal", "shade", "depth")}
        m = maps(rd("albedo"), passes["normal"], passes["shade"], n, depth=passes["depth"], **over)
    return {**m, "frames": n, "size": size, "centre": C.tolist(), "kind": KIND, "passes": passes}


def crop(images: list, n: int, margin: float = 0.03) -> list:
    """The part of a frame any frame of any of these atlases draws: [u0, u1, v0, v1] in frame uv (u right, v down),
    the union of every frame's alpha box, `margin` of the frame wider each way (views between the baked ones turn the
    plant a little further), clipped to 0..1. The engine's quad covers only that (the game, note 84: a 24 m crown on a
    33 m square drew ~2x the pixels it needed; impostors were 10-19 ms of the vale's frame)."""
    u0 = v0 = 1.0
    u1 = v1 = 0.0
    for im in images:
        a = np.asarray(im)[..., 3]
        px = a.shape[0] // n
        for i in range(n):
            for j in range(n):
                t = a[j * px:(j + 1) * px, i * px:(i + 1) * px] > 0.05
                if not t.any():
                    continue
                ys, xs = np.flatnonzero(t.any(1)), np.flatnonzero(t.any(0))
                u0, u1 = min(u0, xs[0] / px), max(u1, (xs[-1] + 1) / px)
                v0, v1 = min(v0, ys[0] / px), max(v1, (ys[-1] + 1) / px)
    if u1 <= u0 or v1 <= v0:
        return [0.0, 1.0, 0.0, 1.0]
    return [round(float(max(u0 - margin, 0.0)), 4), round(float(min(u1 + margin, 1.0)), 4),
            round(float(max(v0 - margin, 0.0)), 4), round(float(min(v1 + margin, 1.0)), 4)]


def recipe(n: int, size: float, centre, crop_: list | None = None) -> str:
    c_ = crop_ or [0.0, 1.0, 0.0, 1.0]
    return (f"hemi-octahedral impostor, {n} x {n} frames, each a {size:.3f} m square orthographic view through the centre "
            f"{[round(float(c), 3) for c in centre]} (glTF object space, +Y up). CROP {c_} = [u0, u1, v0, v1]: the quad covers only that "
            "part of a frame (every frame's drawn pixels are inside it): with uv the quad's corners, cu = mix(u0, u1, uv.x), cv = mix(v0, v1, uv.y), "
            "VERTEX = centre + (cu - 0.5) * size * right + (0.5 - cv) * size * up (below: uv.x / uv.y there read cu / cv). " + _recipe(n, size, centre))


def _recipe(n: int, size: float, centre) -> str:
    return (f"hemi-octahedral impostor, {n} x {n} frames, each a {size:.3f} m square orthographic view through the centre "
            f"{[round(float(c), 3) for c in centre]} (glTF object space, +Y up). Vertex: the quad (uv 0..1) is turned to face the camera: "
            "d = normalize(camera position in object space - centre), d.y clamped >= 0; right = normalize(cross(+Y, d)) (+X if ~0), "
            "up = cross(d, right); VERTEX = centre + (uv.x - 0.5) * size * right + (0.5 - uv.y) * size * up. Fragment: g = "
            "hemi-oct(d) = (px + pz, px - pz) with p = d / (|d.x| + |d.y| + |d.z|), grid = (g * 0.5 + 0.5) * (frames - 1); blend the "
            "4 frames round it bilinearly (weights to the power blend_sharp 2, normalised: the nearest view dominates); for each frame f (direction = decode of its grid point) its uv = (dot(P - centre, R(f)) / size + 0.5, "
            "0.5 - dot(P - centre, U(f)) / size), P = the fragment's object-space position, atlas uv = (column + uv) / frames; one "
            "parallax step first: depth = (normal atlas alpha there - 0.5) * size, P <- P - d * depth, uv again; "
            "colour and normal premultiplied by alpha, alpha scissor 0.5; the normal map is OBJECT space (rgb * 2 - 1, glTF axes): "
            "NORMAL = (VIEW_MATRIX * MODEL_MATRIX * vec4(n, 0)).xyz. Reference Godot 4 shader: " + SHADER + ". Do not receive "
            "shadows on it (cast is fine: in the shadow pass the quad faces the light and draws the view from the sun's side).")


SHARP = 2.0  # (the frames' blend: bilinear weights to this power, normalised)


def view(atlas: dict, d, out_px: int = 256, blend: bool = True, parallax: int = 1, sharp: float = SHARP) -> np.ndarray:
    """What the shader draws from direction d (glTF, toward the camera), as an RGBA float image in the quad's own frame:
    the reference the Godot shader is checked against and what tests hold the bake to."""
    img, n, size = atlas["image"], int(atlas["frames"]), float(atlas["size"])
    C = np.asarray(atlas["centre"], float)
    d = np.asarray(d, float)
    d = d / np.linalg.norm(d)
    d[1] = max(d[1], 0.0)
    d /= np.linalg.norm(d)
    R, U = basis(d[None])
    t = (np.arange(out_px) + 0.5) / out_px - 0.5
    X, Y = np.meshgrid(t, -t)
    P = C + size * (X[..., None] * R[0] + Y[..., None] * U[0])
    g = (encode(d[None])[0] * 0.5 + 0.5) * (n - 1)
    i0 = np.clip(np.floor(g).astype(int), 0, n - 2)
    f = np.clip(g - i0, 0, 1)
    fpx = img.shape[0] // n
    acc = np.zeros(P.shape[:2] + (4,))
    corners = [(0, 0), (1, 0), (0, 1), (1, 1)] if blend else [(int(round(f[0])), int(round(f[1])))]
    for a, b in corners:
        if blend:  # (bilinear, sharpened: w^s normalised; the shader's blend_sharp)
            sh_ = float(sharp)
            w = ((f[0] if a else 1 - f[0]) ** sh_ * (f[1] if b else 1 - f[1]) ** sh_) / (((1 - f[0]) ** sh_ + f[0] ** sh_) * ((1 - f[1]) ** sh_ + f[1] ** sh_))
        else:
            w = 1.0
        if w <= 0:
            continue
        i, j = i0[0] + a, i0[1] + b
        dfm = decode(np.array([[2 * i / (n - 1) - 1, 2 * j / (n - 1) - 1]]))
        Rf, Uf = basis(dfm)
        Q = P
        for _ in range(int(parallax)):  # where the view ray through P meets the plant as this frame saw it (one step)
            fu = (Q - C) @ Rf[0] / size + 0.5
            fv = 0.5 - (Q - C) @ Uf[0] / size
            cx = np.clip((fu * fpx).astype(int), 0, fpx - 1) + i * fpx
            cy = np.clip((fv * fpx).astype(int), 0, fpx - 1) + j * fpx
            dep = (atlas["normal"][cy, cx, 3] - 0.5) * size if atlas["normal"].shape[-1] > 3 else 0.0
            Q = P - d[None, None] * (dep[..., None] if np.ndim(dep) else dep)
        fu = (Q - C) @ Rf[0] / size + 0.5
        fv = 0.5 - (Q - C) @ Uf[0] / size
        cx = np.clip((fu * fpx).astype(int), 0, fpx - 1) + i * fpx
        cy = np.clip((fv * fpx).astype(int), 0, fpx - 1) + j * fpx
        s = img[cy, cx]
        inside = (fu >= 0) & (fu < 1) & (fv >= 0) & (fv < 1)
        al = s[..., 3] * inside
        acc[..., :3] += w * al[..., None] * s[..., :3]
        acc[..., 3] += w * al
    out = np.zeros_like(acc)
    out[..., :3] = acc[..., :3] / np.maximum(acc[..., 3:], 1e-6)
    out[..., 3] = acc[..., 3]
    return out
