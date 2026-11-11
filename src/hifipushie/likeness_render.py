"""The model through a reference's camera: the clay render (raster, depth map, ambient occlusion, soft key, SH light). Part of likeness (likeness.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import likeness

# ---- the model through a reference's camera: a clay render -----------------------------------------------------------
def _raster():
    from numba import njit

    @njit(cache=True)
    def run(sx, sy, z, F, C, W, H, img, zb):
        for t in range(F.shape[0]):
            i0, i1, i2 = F[t, 0], F[t, 1], F[t, 2]
            x0, x1, x2 = sx[i0], sx[i1], sx[i2]
            y0, y1, y2 = sy[i0], sy[i1], sy[i2]
            a0 = max(int(np.floor(min(x0, min(x1, x2)))), 0)
            a1 = min(int(np.ceil(max(x0, max(x1, x2)))), W - 1)
            b0 = max(int(np.floor(min(y0, min(y1, y2)))), 0)
            b1 = min(int(np.ceil(max(y0, max(y1, y2)))), H - 1)
            if a0 > a1 or b0 > b1:
                continue
            d = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
            if abs(d) < 1e-12:
                continue
            for py in range(b0, b1 + 1):
                gy = py + 0.5
                for px in range(a0, a1 + 1):
                    gx = px + 0.5
                    w0 = ((y1 - y2) * (gx - x2) + (x2 - x1) * (gy - y2)) / d
                    w1 = ((y2 - y0) * (gx - x2) + (x0 - x2) * (gy - y2)) / d
                    w2 = 1.0 - w0 - w1
                    if w0 < 0 or w1 < 0 or w2 < 0:
                        continue
                    zz = w0 * z[i0] + w1 * z[i1] + w2 * z[i2]
                    if zz < zb[py, px]:
                        zb[py, px] = zz
                        for c in range(3):
                            img[py, px, c] = w0 * C[i0, c] + w1 * C[i1, c] + w2 * C[i2, c]
    return run


def _sphere(c, r, fwd, n=28):
    """A UV sphere (eyeball) with a dark iris and pupil where `fwd` leaves it: (V, F, colour per vertex)."""
    th, ph = np.meshgrid(np.linspace(0, np.pi, n), np.linspace(0, 2 * np.pi, 2 * n, endpoint=False), indexing="ij")
    d = np.stack([np.sin(th) * np.cos(ph), np.sin(th) * np.sin(ph), np.cos(th)], -1).reshape(-1, 3)
    V = np.asarray(c, float) + r * d
    F = []
    m = 2 * n
    for i in range(n - 1):
        for j in range(m):
            a, b, cc, dd = i * m + j, i * m + (j + 1) % m, (i + 1) * m + (j + 1) % m, (i + 1) * m + j
            F += [[a, cc, b], [a, dd, cc]]
    cs = d @ (np.asarray(fwd, float) / np.linalg.norm(fwd))
    col = np.where(cs[:, None] > 0.97, [25, 18, 15], np.where(cs[:, None] > 0.86, [80, 62, 48], [235, 230, 225])).astype(float)
    return V, np.asarray(F, np.int64), col


def model_mesh(base: dict) -> dict:
    """The model's head as the clay render draws it: skin (template quads), eyeballs with irises, and the brows (paint
    on the real model: drawn as strokes through the model's brow landmarks)."""
    from . import humanfit
    return model_mesh_from_state(humanfit.state(base))


def model_mesh_from_state(st: dict) -> dict:
    """model_mesh of a humanfit.state."""
    tpl, ht = st["tpl"], st["head"]
    Lf = np.asarray(tpl["L"]).reshape(-1, 4)
    F = np.r_[Lf[:, [0, 1, 2]], Lf[:, [0, 2, 3]]].astype(np.int64)
    V = np.asarray(tpl["P"], float)
    fwd = np.asarray(ht.get("forward", [0, -1, 0]), float)
    eyes = []
    r = float(ht.get("eye_r", 0.012))
    for c in ht["eyes"]:
        eyes.append(_sphere(c, r * 0.985, fwd))
    from . import likeness_shape as ls
    ears = None
    try:
        from . import onemesh
        from . import base_identity
        gid = np.asarray(onemesh.asset()["gnm_id"], int)[np.asarray(tpl["fid"])]
        eg = np.asarray(base_identity._gnm_data()["groups"]["ears"], float) > 0.5
        ears = np.where((gid >= 0) & eg[np.maximum(gid, 0)])[0]
    except Exception:  # noqa: BLE001  (not a one-mesh template: no ear vertices known)
        ears = None
    return {"V": V, "F": F, "eyes": eyes, "L": st["L"], "state": st, "ears": ears, "shape3d": ls.measures3d(st)}


                     # its depth maps at SHADOW_MM were 27 Mpx; nothing below the neck shadows the face in these views)

def _occluders(mesh: dict):
    """(V, F) of everything near the face that casts shadow: the skin within OCCLUDE_R of the eyes and the eyeballs."""
    if "_occ" in mesh:
        return mesh["_occ"]
    V, F = mesh["V"], mesh["F"]
    if mesh["eyes"]:
        c = np.mean([e[0].mean(0) for e in mesh["eyes"]], 0)
        near = np.linalg.norm(V - c, axis=1) < likeness.OCCLUDE_R
        F = F[near[F].all(1)]
    Vs, Fs, n = [V], [F], len(V)
    for Ve, Fe, _ in mesh["eyes"]:
        Vs.append(Ve)
        Fs.append(Fe + n)
        n += len(Ve)
    Vo, Fo = np.concatenate(Vs), np.concatenate(Fs).astype(np.int64)
    used = np.unique(Fo)
    remap = np.full(len(Vo), -1)
    remap[used] = np.arange(len(used))
    mesh["_occ"] = (Vo[used], remap[Fo])
    return mesh["_occ"]


def _vertex_normals(V, F):
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    vn = np.zeros_like(V)
    for c in range(3):
        np.add.at(vn, F[:, c], fn)
    return vn / np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-15)


class _DepthMap:
    """An orthographic depth map of (V, F) seen from far along direction d (unit, world, pointing TO the source):
    depth = -X . d (smaller = nearer the source); `lit(X, n)` says which points the source sees (no occluder nearer
    than the point, with a slope-scaled bias)."""

    def __init__(self, V, F, d, mm=likeness.SHADOW_MM):
        if not likeness._RUN:
            likeness._RUN.append(_raster())
        d = np.asarray(d, float) / np.linalg.norm(d)
        a = np.array([1.0, 0, 0]) if abs(d[0]) < 0.9 else np.array([0, 1.0, 0])
        u = np.cross(d, a)
        u /= np.linalg.norm(u)
        v = np.cross(d, u)
        self.d, self.B, self.s = d, np.stack([u, v]), 1000.0 / mm   # px per m
        uv = V @ self.B.T
        self.o = uv.min(0) - 2 / self.s
        q = (uv - self.o) * self.s
        W, H = int(np.ceil(q[:, 0].max())) + 3, int(np.ceil(q[:, 1].max())) + 3
        self.zb = np.full((H, W), np.inf)
        dummy = np.zeros((H, W, 3))
        likeness._RUN[0](q[:, 0], q[:, 1], -(V @ d), np.ascontiguousarray(F), np.zeros((len(V), 3)), W, H, dummy, self.zb)
        # 3 x 3 max filter of the occluder depth: a point is tested against its own surface's farthest neighbour, so the
        # rasterised surface never shadows itself (map aliasing), while a real occluder (mm in front) still does
        from scipy.ndimage import maximum_filter
        z = np.where(np.isfinite(self.zb), self.zb, -np.inf)
        self.zmax = maximum_filter(z, 3)

    def lit(self, X, n=None, bias_mm=0.35):
        q = (X @ self.B.T - self.o) * self.s
        j = np.clip(np.floor(q[:, 0]).astype(int), 0, self.zb.shape[1] - 1)
        i = np.clip(np.floor(q[:, 1]).astype(int), 0, self.zb.shape[0] - 1)
        z = -(X @ self.d)
        bias = bias_mm * 1e-3
        if n is not None:
            c = np.clip(n @ self.d, 0.05, 1.0)
            bias = bias + 1.5 / self.s * np.sqrt(1 - c ** 2) / c
            bias = np.minimum(bias, 8.0 / self.s + bias_mm * 1e-3)
        return z <= self.zmax[i, j] + bias


def ambient_occlusion(mesh: dict, n_dirs: int = likeness.AO_DIRS, mm: float = 0.5) -> np.ndarray:
    """Per-vertex ambient occlusion of the skin (cosine-weighted visibility of the sky over each vertex's hemisphere,
    1 = open), the eyeballs occluding too; cached on the mesh dict. What makes the nostrils, the stomion, the lid
    crease's fold and the alar groove dark in a photo's soft light, which smooth-normal clay can't."""
    if "_ao" in mesh:
        return mesh["_ao"]
    V, F = mesh["V"], mesh["F"]
    Vo, Fo = _occluders(mesh)
    vn = _vertex_normals(V, F)
    k = np.arange(n_dirs) + 0.5
    th = np.arccos(1 - 2 * k / n_dirs)
    ph = np.pi * (1 + 5 ** 0.5) * k
    D = np.c_[np.sin(th) * np.cos(ph), np.sin(th) * np.sin(ph), np.cos(th)]
    num, den = np.zeros(len(V)), np.zeros(len(V))
    near = np.ones(len(V), bool)
    if mesh["eyes"]:
        near = np.linalg.norm(V - np.mean([e[0].mean(0) for e in mesh["eyes"]], 0), axis=1) < likeness.OCCLUDE_R
    for d in D:
        c = vn @ d
        up = (c > 0) & near
        if not up.any():
            continue
        dm = _DepthMap(Vo, Fo, d, mm)
        vis = dm.lit(V[up], vn[up])
        num[up] += c[up] * vis
        den[up] += c[up]
    mesh["_ao"] = np.where(near, num / np.maximum(den, 1e-9), 1.0)
    return mesh["_ao"]


def render(mesh: dict, cam: dict, box, px: int = likeness.RENDER_PX, brows: bool = True, passes: bool = False, light=None,
           ao: bool = False, shadow: bool = False):
    """(PIL image, scale px per picture pixel): the model through the reference's camera, cropped to box (picture
    pixels), lit by a key from the upper left (smooth normals), eyes with irises, brows drawn. passes=True also
    returns {"zb": camera depth (m; inf off the model), "nrm": camera-frame normals, "part": 0 skin / 1 eyes / -1 none}.
    light = (c0, w) (likeness_shape.fit_light: luminance = c0 + w . n) lights the skin like the photo instead.
    ao=True darkens the ambient term by ambient_occlusion (nostrils, stomion, folds); shadow=True casts the key's (or
    the photo light's w) shadows per pixel from a depth map (shadow=<degrees>: a disc light that wide, soft edges) (the upper lip's shadow on the lower, the nose's on the
    lip, the brow's on the lid): the cues a photo shows and the readers compare (passes then also has "lit": the
    direct light's visibility per pixel, "ao" per pixel)."""
    from PIL import Image, ImageDraw
    from . import humanfit
    if not likeness._RUN:
        likeness._RUN.append(_raster())
    if ao or shadow:
        return _render_shaded(mesh, cam, box, px, brows, passes, light, ao, shadow)
    x0, y0, x1, y1 = box
    k = px / max(x1 - x0, y1 - y0)
    W, H = int(round((x1 - x0) * k)), int(round((y1 - y0) * k))
    img = np.full((H, W, 3), 238.0)
    zb = np.full((H, W), np.inf)
    nimg = np.zeros((H, W, 3))
    pimg = np.full((H, W, 3), -1.0)
    zn, zq = np.full((H, W), np.inf), np.full((H, W), np.inf)
    Rc = humanfit._cam_rot(cam)
    parts = [(mesh["V"], mesh["F"], None)] + list(mesh["eyes"])
    for pi, (V, F, col) in enumerate(parts):
        if passes or light is not None:
            Xc = (V - np.asarray(cam["centre"])) @ Rc.T + np.asarray(cam["t"])
            P = humanfit.project(cam, V)
            fn = np.cross(Xc[F[:, 1]] - Xc[F[:, 0]], Xc[F[:, 2]] - Xc[F[:, 0]])
            keep = ((fn * Xc[F].mean(1)).sum(1) < 0) & (Xc[F][:, :, 2] > likeness.NEAR).all(1)
            vn = np.zeros_like(Xc)
            for c in range(3):
                np.add.at(vn, F[:, c], fn)
            vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-15)
            args = ((P[:, 0] - x0) * k, (P[:, 1] - y0) * k, Xc[:, 2].copy(), np.ascontiguousarray(F[keep]))
            likeness._RUN[0](*args, np.ascontiguousarray(vn), W, H, nimg, zn)
            likeness._RUN[0](*args, np.ascontiguousarray(np.full_like(vn, float(min(pi, 1)))), W, H, pimg, zq)
    for V, F, col in parts:
        Xc = (V - np.asarray(cam["centre"])) @ Rc.T + np.asarray(cam["t"])
        P = humanfit.project(cam, V)
        fn = np.cross(Xc[F[:, 1]] - Xc[F[:, 0]], Xc[F[:, 2]] - Xc[F[:, 0]])
        keep = ((fn * Xc[F].mean(1)).sum(1) < 0) & (Xc[F][:, :, 2] > likeness.NEAR).all(1)   # facing the camera
        vn = np.zeros_like(Xc)
        for c in range(3):
            np.add.at(vn, F[:, c], fn)
        vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-15)
        sh = 0.24 + 0.76 * np.clip(vn @ likeness.KEY, 0, 1) ** 1.3 + 0.06 * np.clip(-vn[:, 2], 0, 1)
        if light is not None and col is None:  # the photo's light (linear luminance -> sRGB grey, skin-tinted)
            lum = np.clip((light[0] + vn @ np.asarray(light[1])) / max(light[2] if len(light) > 2 else 0.2, 1e-6), 0.0, 3.0)
            sh = 0.8 * lum ** (1 / 2.2)   # the face's median at 0.8 of the skin colour
        base_c = (np.asarray(mesh["C"], float) if mesh.get("C") is not None else np.broadcast_to(likeness.SKIN, Xc.shape)) if col is None else col
        C = np.clip(base_c * sh[:, None], 0, 255)
        likeness._RUN[0]((P[:, 0] - x0) * k, (P[:, 1] - y0) * k, Xc[:, 2].copy(), np.ascontiguousarray(F[keep]),
                np.ascontiguousarray(C), W, H, img, zb)
    im = Image.fromarray(img.astype(np.uint8))
    if brows:
        L = humanfit.project(cam, mesh["L"])
        d = ImageDraw.Draw(im)
        wpx = max(2, int(round(_mm_per_px(cam, mesh["L"]) ** -1 * 4.0 * k)))  # ~4 mm thick
        for a, b in ((17, 22), (22, 27)):
            pts = [((L[i, 0] - x0) * k, (L[i, 1] - y0) * k) for i in range(a, b)]
            d.line(pts, fill=(70, 52, 40), width=wpx, joint="curve")
    if passes:
        return im, k, {"zb": zn, "nrm": nimg, "part": np.where(np.isfinite(zq), pimg[..., 0], -1).round().astype(int)}
    return im, k


def _light_disc(d, deg: float) -> list:
    """Directions over a disc light of angular radius deg about d (a Fibonacci spiral; [d] for a point light)."""
    d = np.asarray(d, float) / np.linalg.norm(d)
    if deg <= 0:
        return [d]
    a = np.array([1.0, 0, 0]) if abs(d[0]) < 0.9 else np.array([0, 1.0, 0])
    u = np.cross(d, a)
    u /= np.linalg.norm(u)
    v = np.cross(d, u)
    out = []
    for i in range(likeness.SOFT_N):
        r = np.tan(np.radians(deg)) * np.sqrt((i + 0.5) / likeness.SOFT_N)
        t = i * np.pi * (3 - 5 ** 0.5)
        e = d + r * (np.cos(t) * u + np.sin(t) * v)
        out.append(e / np.linalg.norm(e))
    return out


def sh9(n):
    """The 9 real spherical-harmonics basis functions (up to constants) of unit normals (..., 3)."""
    n = np.asarray(n, float)
    x, y, z = n[..., 0], n[..., 1], n[..., 2]
    return np.stack([np.ones_like(x), x, y, z, x * y, y * z, x * z, x * x - y * y, 3 * z * z - 1], -1)


def _render_shaded(mesh, cam, box, px, brows, passes, light, ao, shadow):
    """render() with ambient occlusion and / or cast shadows: the ambient and the direct terms are rasterised
    separately (per-vertex, interpolated) and the direct one is multiplied per pixel by the key's visibility."""
    from PIL import Image, ImageDraw
    from . import humanfit
    x0, y0, x1, y1 = box
    k = px / max(x1 - x0, y1 - y0)
    W, H = int(round((x1 - x0) * k)), int(round((y1 - y0) * k))
    Rc = humanfit._cam_rot(cam)
    aov = ambient_occlusion(mesh) if ao else np.ones(len(mesh["V"]))
    key_c = np.asarray(light[1], float) if light is not None else likeness.KEY
    key_w = Rc.T @ (key_c / max(np.linalg.norm(key_c), 1e-12))   # world direction to the light
    parts = [(mesh["V"], mesh["F"], None, aov)] + [(V, F, col, None) for V, F, col in mesh["eyes"]]
    img_a, img_d = np.full((H, W, 3), 238.0), np.zeros((H, W, 3))
    za, zd = np.full((H, W), np.inf), np.full((H, W), np.inf)
    nimg, pimg, aimg = np.zeros((H, W, 3)), np.full((H, W, 3), -1.0), np.ones((H, W, 3))
    zn, zq, zo = (np.full((H, W), np.inf) for _ in range(3))
    for pi, (V, F, col, av) in enumerate(parts):
        Xc = (V - np.asarray(cam["centre"])) @ Rc.T + np.asarray(cam["t"])
        P = humanfit.project(cam, V)
        fn = np.cross(Xc[F[:, 1]] - Xc[F[:, 0]], Xc[F[:, 2]] - Xc[F[:, 0]])
        keep = ((fn * Xc[F].mean(1)).sum(1) < 0) & (Xc[F][:, :, 2] > likeness.NEAR).all(1)
        vn = np.zeros_like(Xc)
        for c in range(3):
            np.add.at(vn, F[:, c], fn)
        vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-15)
        args = ((P[:, 0] - x0) * k, (P[:, 1] - y0) * k, Xc[:, 2].copy(), np.ascontiguousarray(F[keep]))
        base_c = (np.asarray(mesh["C"], float) if mesh.get("C") is not None else np.broadcast_to(likeness.SKIN, Xc.shape)) if col is None else col
        avv = np.ones(len(V)) if av is None else av
        if light is not None and col is None and len(light) > 4 and light[4] is not None:
            # (blockin2) a 2nd-order spherical-harmonics light fitted on the photo's skin (ambient + key + fill / bounce
            # from below, x AO): light[4] = 9 coefficients over camera-frame normals (sh9); no separate direct term
            sc = max(light[2] if len(light) > 2 else 0.2, 1e-6)
            aw = float(light[3]) if len(light) > 3 else 1.0
            tot = (sh9(vn) @ np.asarray(light[4], float)) * (1.0 - aw + aw * avv) / sc
            Ca = 0.8 * np.clip(tot, 0, 3)[:, None] * base_c
            Cd = np.zeros_like(Ca)
        elif light is not None and col is None:
            sc = max(light[2] if len(light) > 2 else 0.2, 1e-6)
            # light[3] (optional, 0..1): how much of the ambient term AO darkens (fitted to the photo: soft studio
            # light fills cavities more than an open sky does)
            aw = float(light[3]) if len(light) > 3 else 1.0
            amb = float(light[0]) / sc * (1.0 - aw + aw * avv)
            dirc = (vn @ np.asarray(light[1], float)) / sc
            # (the photo's linear model: the negative part of w . n stays ambient-like, unshadowed)
            amb = amb + np.minimum(dirc, 0)
            dirc = np.maximum(dirc, 0)
            Ca = 0.8 * np.clip(amb, 0, 3)[:, None] * base_c
            Cd = 0.8 * np.clip(dirc, 0, 3)[:, None] * base_c
        else:
            Ca = base_c * ((0.24 + 0.06 * np.clip(-vn[:, 2], 0, 1)) * avv)[:, None]
            Cd = base_c * (0.76 * np.clip(vn @ likeness.KEY, 0, 1) ** 1.3)[:, None]
        likeness._RUN[0](*args, np.ascontiguousarray(Ca), W, H, img_a, za)
        likeness._RUN[0](*args, np.ascontiguousarray(Cd), W, H, img_d, zd)
        likeness._RUN[0](*args, np.ascontiguousarray(vn), W, H, nimg, zn)
        likeness._RUN[0](*args, np.ascontiguousarray(np.full_like(vn, float(min(pi, 1)))), W, H, pimg, zq)
        likeness._RUN[0](*args, np.ascontiguousarray(np.repeat(avv[:, None], 3, 1)), W, H, aimg, zo)
    lit = np.ones((H, W))
    on = np.isfinite(zn)
    if shadow and on.any() and np.all(np.isfinite(key_w)) and np.linalg.norm(key_c) > 1e-9:   # (no direct light: no shadow)
        from .likeness_shape import unproject
        Vo, Fo = _occluders(mesh)
        ii, jj = np.nonzero(on)
        uv = np.c_[x0 + (jj + 0.5) / k, y0 + (ii + 0.5) / k]
        Xw = unproject(cam, uv, zn[ii, jj])
        nw = nimg[ii, jj] @ Rc   # camera-frame normals back to world
        acc = np.zeros(len(ii))
        dirs = _light_disc(key_w, 0.0 if shadow is True else float(shadow))
        for d in dirs:
            acc += _DepthMap(Vo, Fo, d).lit(Xw, nw)
        lit[ii, jj] = acc / len(dirs)
        from scipy.ndimage import gaussian_filter
        lit = np.where(on, np.clip(gaussian_filter(lit, 0.6), 0, 1), 1.0)   # (a pixel's worth of penumbra)
    img = np.clip(img_a + img_d * lit[..., None], 0, 255)
    img[~on] = 238.0
    im =Image.fromarray(img.astype(np.uint8))
    if brows:
        L = humanfit.project(cam, mesh["L"])
        d = ImageDraw.Draw(im)
        wpx = max(2, int(round(_mm_per_px(cam, mesh["L"]) ** -1 * 4.0 * k)))
        for a, b in ((17, 22), (22, 27)):
            pts = [((L[i, 0] - x0) * k, (L[i, 1] - y0) * k) for i in range(a, b)]
            d.line(pts, fill=(70, 52, 40), width=wpx, joint="curve")
    if passes:
        return im, k, {"zb": zn, "nrm": nimg, "part": np.where(np.isfinite(zq), pimg[..., 0], -1).round().astype(int),
                       "lit": lit, "ao": np.where(on, aimg[..., 0], 1.0)}
    return im, k


def _mm_per_px(cam: dict, X) -> float:
    """mm per picture pixel at the depth of these points (the mean)."""
    from . import humanfit
    Xc = (np.asarray(X, float).mean(0) - np.asarray(cam["centre"])) @ humanfit._cam_rot(cam).T + np.asarray(cam["t"])
    return float(Xc[2] / cam["f"] * 1000.0)
