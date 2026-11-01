"""groundtruth: a small z-buffer rasteriser (numba) for our own pictures of scans and GNM heads through KNOWN cameras
(the pipeline's camera dict: humanfit.project). A visibility buffer (face id + barycentrics per pixel), shaded in numpy:
vertex colours or a texture, smooth normals, two lights. No Blender: light, exact cameras, nothing heavy."""
from __future__ import annotations

import numpy as np

_RUN = []


def _raster():
    from numba import njit

    @njit(cache=True)
    def run(sx, sy, z, F, W, H, fid, bw, zb):
        for t in range(F.shape[0]):
            i0, i1, i2 = F[t, 0], F[t, 1], F[t, 2]
            if z[i0] <= 1e-4 or z[i1] <= 1e-4 or z[i2] <= 1e-4:
                continue
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
                    # perspective-correct depth
                    iz = w0 / z[i0] + w1 / z[i1] + w2 / z[i2]
                    zz = 1.0 / iz
                    if zz < zb[py, px]:
                        zb[py, px] = zz
                        fid[py, px] = t
                        bw[py, px, 0] = w0 / z[i0] * zz
                        bw[py, px, 1] = w1 / z[i1] * zz
    return run


def cam_points(cam, X):
    from hifipushie import humanfit
    Xc = (np.asarray(X, float) - np.asarray(cam["centre"], float)) @ humanfit._cam_rot(cam).T + np.asarray(cam["t"], float)
    w, h = cam["size"]
    return Xc, np.stack([cam["f"] * Xc[:, 0] / Xc[:, 2] + w / 2, cam["f"] * Xc[:, 1] / Xc[:, 2] + h / 2], 1)


def visibility(V, F, cam, ss: int = 1) -> dict:
    """The mesh through cam: {"fid" (H, W) face id or -1, "bw" (H, W, 3), "z" depth m, "Xc" camera-frame vertices}.
    ss = supersampling factor (the buffers are ss x the camera's size)."""
    if not _RUN:
        _RUN.append(_raster())
    Xc, P = cam_points(cam, V)
    w, h = cam["size"]
    W, H = int(w * ss), int(h * ss)
    fid = np.full((H, W), -1, np.int64)
    bw = np.zeros((H, W, 2))
    zb = np.full((H, W), np.inf)
    _RUN[0](P[:, 0] * ss, P[:, 1] * ss, Xc[:, 2].copy(), np.ascontiguousarray(F, dtype=np.int64), W, H, fid, bw, zb)
    b = np.concatenate([bw, 1 - bw.sum(-1, keepdims=True)], -1)
    return {"fid": fid, "bw": b, "z": zb, "Xc": Xc, "ss": ss}


def interp(vis, F, A):
    """A per-vertex attribute (n, k) (or per-corner (len(F), 3, k)) at every covered pixel: (H, W, k), nan elsewhere."""
    fid, bw = vis["fid"], vis["bw"]
    m = fid >= 0
    A = np.asarray(A, float)
    T = A[F[fid[m]]] if A.ndim == 2 else A[fid[m]]
    out = np.full(fid.shape + (T.shape[-1],), np.nan)
    out[m] = (bw[m][:, :, None] * T).sum(1)
    return out


LIGHTS = (((-0.45, -0.50, -0.74), 0.85), ((0.75, -0.15, -0.64), 0.35))     # directions TO the lights, camera frame (x right, y down, z into the picture): key upper left, fill right
AMBIENT = 0.22


def shade(vis, V, F, colour, cam=None, lights=LIGHTS, ambient=AMBIENT, bg=(238, 238, 238), normals=None, gamma: bool = False):
    """A picture (PIL) from a visibility buffer: colour = per-vertex (n, 3) 0..255, or a (H, W, 3) image already
    interpolated (a texture lookup); smooth normals in the camera frame, two directional lights + ambient.
    gamma=True: the colour is treated as sRGB albedo and lit in linear light (photo-like)."""
    from PIL import Image
    Xc = vis["Xc"]
    vn = vertex_normals_cam(Xc, F) if normals is None else normals
    N = interp(vis, F, vn)
    N /= np.maximum(np.linalg.norm(N, axis=-1, keepdims=True), 1e-12)
    m = vis["fid"] >= 0
    if m.any() and np.nanmean(N[m][:, 2]) > 0:      # the mesh's winding faces away: outward = toward the camera
        N = -N
    sh = np.full(m.shape, ambient)
    for d, e in lights:
        d = np.asarray(d, float)
        d = d / np.linalg.norm(d)
        sh = sh + e * np.clip(N @ d, 0, 1)          # d points TO the light
    C = interp(vis, F, colour) if np.asarray(colour).ndim == 2 and len(colour) == len(V) else np.asarray(colour, float)
    if gamma:
        img = 255.0 * np.clip(((np.clip(C, 0, 255) / 255.0) ** 2.2) * sh[..., None], 0, 1) ** (1 / 2.2)
    else:
        img = np.clip(C * sh[..., None], 0, 255)
    img = np.where(m[..., None], img, np.asarray(bg, float))
    im = Image.fromarray(img.astype(np.uint8))
    if vis["ss"] != 1:
        im = im.resize((im.width // vis["ss"], im.height // vis["ss"]), Image.LANCZOS)
    return im


def vertex_normals_cam(Xc, F):
    fn = np.cross(Xc[F[:, 1]] - Xc[F[:, 0]], Xc[F[:, 2]] - Xc[F[:, 0]])
    vn = np.zeros_like(Xc)
    for c in range(3):
        np.add.at(vn, F[:, c], fn)
    vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-20)
    # outward = toward the camera on visible faces: flip the whole mesh when its winding faces away
    return vn


def texture_lookup(vis, FUVc, tex):
    """Bilinear texture colours per pixel: FUVc (len(F), 3, 2) per-corner uv (v up, OBJ convention), tex (h, w, 3)."""
    uv = interp(vis, None, FUVc)
    m = vis["fid"] >= 0
    h, w = tex.shape[:2]
    out = np.zeros(m.shape + (3,))
    u = np.clip(uv[m][:, 0] % 1.0 * w - 0.5, 0, w - 1.001)
    v = np.clip((1 - uv[m][:, 1] % 1.0) * h - 0.5, 0, h - 1.001)
    x0, y0 = u.astype(int), v.astype(int)
    fx, fy = (u - x0)[:, None], (v - y0)[:, None]
    t = tex.astype(np.float32)
    out[m] = (t[y0, x0] * (1 - fx) * (1 - fy) + t[y0, x0 + 1] * fx * (1 - fy) + t[y0 + 1, x0] * (1 - fx) * fy + t[y0 + 1, x0 + 1] * fx * fy)
    return out


def look_cam(centre, yaw: float = 0.0, pitch: float = 0.0, dist: float = 1.2, lens: float = 85.0, size=(1152, 1536), shift=(0.0, 0.0)) -> dict:
    """A pipeline camera looking at `centre` (GNM world: the face looks along -Y): yaw degrees round the head (+ = the
    camera moves toward the head's left, as the benchmark's views), pitch = the camera raised (+) looking down."""
    from hifipushie import face_ruler as fr
    w, h = size
    f = lens / 36.0 * w
    cam = {"r": [0.0, 0.0, 0.0], "t": [float(shift[0]), float(shift[1]), float(dist)], "f": float(f), "size": [int(w), int(h)],
           "centre": [float(x) for x in centre], "yaw": float(-yaw)}
    if pitch:
        cam = fr.cam_moved(cam, pitch=pitch)
        cam = {k: (np.asarray(v).tolist() if hasattr(v, "tolist") else v) for k, v in cam.items()}
    return cam


def gap_colours(signed_mm, lim: float = 4.0, base=(205, 200, 195)):
    """Per-vertex colours for a signed gap (mm): red = the scan lies outside (GNM too small there), blue = inside;
    nan (not compared) = dark grey."""
    s = np.asarray(signed_mm, float)
    t = np.clip(np.nan_to_num(s) / lim, -1, 1)[:, None]
    base = np.asarray(base, float)
    C = np.where(t >= 0, base + t * (np.array([225.0, 40, 30]) - base), base + (-t) * (np.array([30.0, 70, 230]) - base))
    C[~np.isfinite(s)] = (95, 95, 95)
    return C
