"""sealmesh.py <model> <voxel mm> ...: mesh a box round the mouth (store.build with a box) at a voxel and count the
OUTER surface's vertices sunk into the mouth: behind the lips' contact by more than 1.5 mm, between the corners, within
2.5 mm of the seam's height. A sealed mouth has none (its inside, if any, is a separate closed shell)."""
import json
import sys

import numpy as np
import scipy.sparse as sp
from scipy.sparse.csgraph import connected_components

from hifipushie import humanfit, store


def sunk(name, voxel_mm):
    st = humanfit.state(store.load(name)["base"])
    L = st["L"]
    c = 0.5 * (L[48] + L[54])
    half = np.array([0.03, 0.03, 0.025])
    lo, hi = c - half, c + half
    res = int(round(float((hi - lo).max()) / (voxel_mm / 1000)))
    store.build(name, resolution=res, box=(lo, hi))
    z = np.load(store._dir(name) / "build" / "closeup.npz")
    V = np.asarray(z["verts"] if "verts" in z.files else z["V"], float)
    F = np.asarray(z["faces"] if "faces" in z.files else z["F"], int)
    A = sp.coo_matrix((np.ones(3 * len(F)), (np.r_[F[:, 0], F[:, 1], F[:, 2]], np.r_[F[:, 1], F[:, 2], F[:, 0]])),
                      (len(V), len(V)))
    n, lab = connected_components(A, directed=False)
    main = lab == np.argmax(np.bincount(lab))
    # the face looks along -y. A hole in the seal lets the outer surface run deep into the mouth: per 1 mm column
    # between the corners, at the seam's height (mid upper / lower vermilion borders, +-2.5 mm), any main-surface
    # vertex more than DEEP behind that column's front-most one
    zc = float(0.5 * (L[51, 2] + L[57, 2]))
    xl, xr = sorted([L[48, 0], L[54, 0]])
    band = main & (np.abs(V[:, 2] - zc) < 0.0025) & (V[:, 0] > xl + 0.002) & (V[:, 0] < xr - 0.002)
    inside = np.zeros(len(V), bool)
    for x0 in np.arange(xl + 0.002, xr - 0.002, 0.001):
        col = band & (np.abs(V[:, 0] - x0 - 0.0005) <= 0.0005)
        if col.any():
            front = V[col, 1].min()
            inside |= col & (V[:, 1] > front + 0.006)
    return int(inside.sum()), len(V), n




def picture(name, out):
    """The last closeup's main surface: a side section through the mouth's middle (y across, z up), the sunk in red."""
    from PIL import Image, ImageDraw
    st = humanfit.state(store.load(name)["base"])
    L = st["L"]
    z = np.load(store._dir(name) / "build" / "closeup.npz")
    V = np.asarray(z["verts"], float)
    c = 0.5 * (L[48] + L[54])
    sel = np.abs(V[:, 0] - c[0]) < 0.0015
    im = Image.new("RGB", (600, 600), (255, 255, 255))
    d = ImageDraw.Draw(im)
    k = 600 / 0.05
    for p in V[sel]:
        u, w = (p[1] - c[1] + 0.025) * k, (c[2] + 0.025 - p[2]) * k
        d.point((u, w), fill=(0, 0, 0))
    for i in (51, 57, 62, 66):
        u, w = (L[i, 1] - c[1] + 0.025) * k, (c[2] + 0.025 - L[i, 2]) * k
        d.ellipse([u - 3, w - 3, u + 3, w + 3], outline=(255, 0, 0))
    im.save(out)




def holes(name, voxel_mm, cell=0.0005):
    """Seen from the front (+y): per cell over the lips (corners to corners, the seam +-3 mm), the front-most
    surface's depth; a hole = a cell more than 3 mm deeper than the median of its row's neighbours (the surface
    there is the mouth's inside)."""
    st = humanfit.state(store.load(name)["base"])
    L = st["L"]
    c = 0.5 * (L[48] + L[54])
    half = np.array([0.03, 0.03, 0.025])
    res = int(round(float((2 * half).max()) / (voxel_mm / 1000)))
    store.build(name, resolution=res, box=(c - half, c + half))
    z = np.load(store._dir(name) / "build" / "closeup.npz")
    V = np.asarray(z["verts"], float)
    F = np.asarray(z["faces"], int)
    # sample the faces densely (a vertex-only z-buffer has gaps at coarse voxels)
    w = np.random.default_rng(0).dirichlet([1, 1, 1], 12)
    P = (V[F][:, None, :, :] * w[None, :, :, None]).sum(2).reshape(-1, 3)
    P = np.r_[P, V]
    zc = float(0.5 * (L[51, 2] + L[57, 2]))
    xl, xr = sorted([L[48, 0], L[54, 0]])
    xs = np.arange(xl + 0.003, xr - 0.003, cell)
    zs = np.arange(zc - 0.003, zc + 0.003, cell)
    D = np.full((len(zs), len(xs)), np.nan)
    ix = np.floor((P[:, 0] - xs[0]) / cell).astype(int)
    iz = np.floor((P[:, 2] - zs[0]) / cell).astype(int)
    ok = (ix >= 0) & (ix < len(xs)) & (iz >= 0) & (iz < len(zs)) & (P[:, 1] < c[1] + 0.01)
    for a, b_, y in zip(iz[ok], ix[ok], P[ok, 1]):
        if not (D[a, b_] <= y):
            D[a, b_] = y
    from scipy.ndimage import median_filter
    med = median_filter(np.nan_to_num(D, nan=np.nanmax(D)), size=(1, 9))
    hole = np.isnan(D) | (D > med + 0.003)
    return int(hole.sum()), D.size


if __name__ == "__main__":
    if sys.argv[1] == "--holes":
        for i in range(2, len(sys.argv), 2):
            print(sys.argv[i], sys.argv[i + 1], "mm: hole cells", holes(sys.argv[i], float(sys.argv[i + 1])))
    elif sys.argv[-1].endswith(".png"):
        sunk(sys.argv[1], float(sys.argv[2]))
        picture(sys.argv[1], sys.argv[-1])
    else:
        for i in range(1, len(sys.argv), 2):
            s_, nv, ncomp = sunk(sys.argv[i], float(sys.argv[i + 1]))
            print(f"{sys.argv[i]} at {sys.argv[i + 1]} mm: outer-surface vertices sunk {s_} (of {nv}; {ncomp} pieces)")
