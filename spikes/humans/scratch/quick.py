"""quick.py: a painter's-order clay view of a quad/tri mesh in PIL (diagnosis only, no Blender)."""
import numpy as np
from PIL import Image, ImageDraw


def faces_of(b):
    L, S = np.asarray(b["L"]), np.asarray(b["S"])
    o = np.r_[0, np.cumsum(S)]
    return [L[o[i]:o[i + 1]] for i in range(len(S))]


def view(P, faces, az=0.0, px_per_m=400, box=None, bg=(120, 124, 132), color=(205, 200, 195), pad=0.03):
    """az degrees about z: 0 = front (camera at -y looking +y), 90 = the figure's left side."""
    a = np.radians(az)
    R = np.array([[np.cos(a), np.sin(a), 0], [-np.sin(a), np.cos(a), 0], [0, 0, 1]])
    Q = P @ R.T  # x right, y depth (away), z up
    lo = Q.min(0) - pad if box is None else np.array(box[0])
    hi = Q.max(0) + pad if box is None else np.array(box[1])
    W, H = int((hi[0] - lo[0]) * px_per_m), int((hi[2] - lo[2]) * px_per_m)
    im = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(im)
    F = [np.asarray(f) for f in faces]
    depth = np.array([Q[f][:, 1].mean() for f in F])
    light = np.array([-0.35, -0.8, 0.5])
    light /= np.linalg.norm(light)
    for i in np.argsort(-depth):
        f = F[i]
        p = Q[f]
        n = np.cross(p[1] - p[0], p[2] - p[0])
        ln = np.linalg.norm(n)
        if ln < 1e-12 or n[1] > 0:  # back face
            continue
        s = 0.25 + 0.75 * max(0.0, float(n @ light) / ln)
        xy = [((q[0] - lo[0]) * px_per_m, (hi[2] - q[2]) * px_per_m) for q in p]
        d.polygon(xy, fill=tuple(int(c * s) for c in color))
    return im


def row(ims, labels=None, bg=(30, 32, 36)):
    h = max(i.height for i in ims)
    out = Image.new("RGB", (sum(i.width for i in ims), h + 16), bg)
    x = 0
    for k, i in enumerate(ims):
        out.paste(i, (x, 16 + h - i.height))
        if labels:
            ImageDraw.Draw(out).text((x + 3, 2), labels[k], fill=(255, 255, 0))
        x += i.width
    return out
