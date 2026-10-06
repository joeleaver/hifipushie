"""A quick shaded wireframe view of a polygon mesh (PIL, painter's algorithm): loop close-ups without Blender."""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw


def view(V, faces, centre, size, az=0.0, el=0.0, px=900, colors=None, edge=(40, 40, 46), back=False, light=(0.4, -0.5, 0.75),
         title=None, line=1, hi_edges=None, hi_color=(220, 40, 40)):
    """Orthographic view of the faces within the window (`size` m across) round `centre`, seen from azimuth `az`
    (degrees; 0 = from the front, the figure faces -Y; 90 = from its left, +X) and elevation `el`. colors: per face
    RGB (0..255) or None (clay). hi_edges: [(a, b)] drawn thick."""
    V = np.asarray(V, float)
    a, e = np.radians(az), np.radians(el)
    fwd = -np.array([np.sin(a) * np.cos(e), -np.cos(a) * np.cos(e), np.sin(e)])  # camera looks along this
    right = np.array([np.cos(a), np.sin(a), 0.0])
    up = np.cross(right, fwd)
    X = V - np.asarray(centre, float)
    x, y, zd = X @ right, X @ up, X @ fwd
    sc = px / size
    sx, sy = px / 2 + x * sc, px / 2 - y * sc
    F = [np.asarray(f) for f in faces]
    cen = np.array([[sx[f].mean(), sy[f].mean(), zd[f].mean()] for f in F])
    nrm = np.array([np.cross(V[f[1]] - V[f[0]], V[f[2]] - V[f[0]]) for f in F])
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
    vis = (np.abs(cen[:, 0] - px / 2) < px * 0.6) & (np.abs(cen[:, 1] - px / 2) < px * 0.6)
    if not back:
        vis &= (nrm @ fwd) < 0.05
    L = np.asarray(light, float)
    L = L / np.linalg.norm(L)
    Lw = L[0] * right + L[1] * fwd + L[2] * up
    sh = 0.35 + 0.65 * np.clip(nrm @ Lw, 0, 1)
    img = Image.new("RGB", (px, px), (236, 236, 238))
    d = ImageDraw.Draw(img)
    for k in np.argsort(-cen[:, 2]):
        if not vis[k]:
            continue
        f = F[k]
        c = np.array(colors[k] if colors is not None else (205, 200, 192), float) * sh[k]
        d.polygon([(sx[v], sy[v]) for v in f], fill=tuple(int(t) for t in c), outline=edge if line else None)
    if hi_edges:
        for a_, b_ in hi_edges:
            d.line([(sx[a_], sy[a_]), (sx[b_], sy[b_])], fill=hi_color, width=3)
    if title:
        d.text((8, 6), title, fill=(20, 20, 20))
    return img


def sheet(images, cols, path):
    w, h = images[0].size
    rows = (len(images) + cols - 1) // cols
    out = Image.new("RGB", (cols * w, rows * h), (255, 255, 255))
    for i, im in enumerate(images):
        out.paste(im, ((i % cols) * w, (i // cols) * h))
    out.save(path)
    return path
