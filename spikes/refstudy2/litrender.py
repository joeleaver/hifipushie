"""litrender.py: onemesh2 refsheet3 lit numpy renderer (key from the upper left, smooth normals, Lambert + fill)."""
import numpy as np
from PIL import Image
from hifipushie import humanfit

KEY = np.array([-0.35, -0.45, -0.82])
KEY /= np.linalg.norm(KEY)


def render(V, F, cam, box, px, lit, col=None, two=None):
    P = humanfit.project(cam, V)
    Rc = humanfit._cam_rot(cam)
    Xc = (V - np.asarray(cam["centre"])) @ Rc.T + np.asarray(cam["t"])
    z = Xc[:, 2]
    x0, y0, x1, y1 = box
    k = px / max(x1 - x0, y1 - y0)
    sx, sy = (P[:, 0] - x0) * k, (P[:, 1] - y0) * k
    W, H = int((x1 - x0) * k), int((y1 - y0) * k)
    zb = np.full((H, W), np.inf)
    img = np.full((H, W, 3), 236.0)
    fn = np.cross(Xc[F[:, 1]] - Xc[F[:, 0]], Xc[F[:, 2]] - Xc[F[:, 0]])
    vn = np.zeros_like(Xc)
    for c in range(3):
        np.add.at(vn, F[:, c], fn)
    vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-15)
    fnn = fn / np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-15)
    L0 = np.array([0.3, -0.5, -0.8])
    L0 /= np.linalg.norm(L0)
    for t in range(len(F)):
        i = F[t]
        if fn[t] @ Xc[i].mean(0) > 0 and (two is None or not two[t]):
            continue
        xs, ys = sx[i], sy[i]
        a0, a1 = int(max(np.floor(xs.min()), 0)), int(min(np.ceil(xs.max()), W - 1))
        b0, b1 = int(max(np.floor(ys.min()), 0)), int(min(np.ceil(ys.max()), H - 1))
        if a0 > a1 or b0 > b1:
            continue
        gx, gy = np.meshgrid(np.arange(a0, a1 + 1) + 0.5, np.arange(b0, b1 + 1) + 0.5)
        d = (ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2])
        if abs(d) < 1e-12:
            continue
        w0 = ((ys[1] - ys[2]) * (gx - xs[2]) + (xs[2] - xs[1]) * (gy - ys[2])) / d
        w1 = ((ys[2] - ys[0]) * (gx - xs[2]) + (xs[0] - xs[2]) * (gy - ys[2])) / d
        w2 = 1 - w0 - w1
        m = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        zz = w0 * z[i[0]] + w1 * z[i[1]] + w2 * z[i[2]]
        sub = zb[b0:b1 + 1, a0:a1 + 1]
        upd = m & (zz < sub)
        if not upd.any():
            continue
        sub[upd] = zz[upd]
        if lit:
            n = w0[upd, None] * vn[i[0]] + w1[upd, None] * vn[i[1]] + w2[upd, None] * vn[i[2]]
            n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
            n = np.where(n[:, 2:3] > 0, -n, n)  # (two-sided faces: the side toward the camera)
            sh = 0.22 + 0.78 * np.clip(n @ KEY, 0, 1) ** 1.5 + 0.08 * np.clip(-n[:, 2], 0, 1)
            img[b0:b1 + 1, a0:a1 + 1][upd] = np.clip((np.array([225, 205, 185]) if col is None else col[t])[None] * sh[:, None], 0, 255)
        else:
            img[b0:b1 + 1, a0:a1 + 1][upd] = np.array([210, 200, 190]) * (0.3 + 0.7 * abs(fnn[t] @ L0))
    return Image.fromarray(img.astype(np.uint8)), k


def row(tiles, h):
    r = Image.new("RGB", (sum(t.size[0] for t in tiles), h), (30, 30, 34))
    x = 0
    for t in tiles:
        r.paste(t, (x, 0))
        x += t.size[0]
    return r
