"""R1 (drape first) helpers: exact mesh clipping by a scalar, components, polyline tools, a software rasterizer
(orthographic z-buffer, Lambert, no GPU) for 4-view sheets beside the reference, and the picture -> model mapping
of step 2's traces. Spike code (docs/proposals/drape_first.md)."""
import numpy as np
from PIL import Image, ImageDraw
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

PX_H = 1.0811e-3  # m per reference px across (step 0's chest: body 335.8 mm on 310.5 px)
PX_V = 1.0487e-3  # m per reference px up (crotch v1000 = 870 mm, eyes v240 = 1667 mm)
U0, V0, Z0 = 628.0, 1000.0, 0.8705  # centre-front column, crotch row, crotch height


def px_to_xz(u, v):
    return (np.asarray(u, float) - U0) * PX_H, Z0 + (V0 - np.asarray(v, float)) * PX_V


def clip(V, F, phi):
    """Mesh (V, F) clipped exactly to phi >= 0 (phi per vertex, linear on each triangle): new vertices on cut edges."""
    phi = np.asarray(phi, float).copy()
    phi[np.abs(phi) < 1e-9] = 1e-9
    pos = phi > 0
    keep = pos[F].all(1)
    part = pos[F].any(1) & ~keep
    newV = [V]
    cache = {}
    nV = len(V)

    def mid(a, b):
        nonlocal nV
        k = (min(a, b), max(a, b))
        if k not in cache:
            t = phi[a] / (phi[a] - phi[b])
            newV.append((V[a] + t * (V[b] - V[a]))[None])
            cache[k] = nV
            nV += 1
        return cache[k]

    out = [F[keep]]
    add = []
    for f in F[part]:
        s = pos[f]
        if s.sum() == 1:  # one inside: a smaller triangle
            i = int(np.argmax(s))
            a, b, c = f[i], f[(i + 1) % 3], f[(i + 2) % 3]
            add.append([a, mid(a, b), mid(a, c)])
        else:  # two inside: a quad, two triangles
            i = int(np.argmin(s))
            a, b, c = f[i], f[(i + 1) % 3], f[(i + 2) % 3]
            mb, mc = mid(a, b), mid(a, c)
            add += [[mb, b, c], [mb, c, mc]]
    if add:
        out.append(np.array(add, int))
    V2 = np.concatenate(newV)
    return compact(V2, np.concatenate(out))


def compact(V, F):
    used = np.unique(F)
    remap = -np.ones(len(V), int)
    remap[used] = np.arange(len(used))
    return V[used], remap[F]


def face_components(F, nV, cut=None):
    """Face labels: faces joined across shared edges, except edges in `cut` (a set of (a, b) with a < b)."""
    E = np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), axis=1)
    fid = np.tile(np.arange(len(F)), 3)
    key = E[:, 0].astype(np.int64) * nV + E[:, 1]
    o = np.argsort(key, kind="stable")
    k, f = key[o], fid[o]
    same = k[1:] == k[:-1]
    a, b = f[:-1][same], f[1:][same]
    if cut:
        ck = np.array([x * nV + y for x, y in cut], np.int64)
        ok = ~np.isin(k[:-1][same], ck)
        a, b = a[ok], b[ok]
    A = coo_matrix((np.ones(len(a)), (a, b)), shape=(len(F), len(F)))
    return connected_components(A, directed=False)[1]


def largest(V, F):
    lab = face_components(F, len(V))
    big = np.bincount(lab).argmax()
    return compact(V, F[lab == big])


def resample(P, step=0.004):
    P = np.asarray(P, float)
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    k = max(2, int(np.ceil(s[-1] / step)) + 1)
    t = np.linspace(0, s[-1], k)
    return np.c_[[np.interp(t, s, P[:, i]) for i in range(3)]].T


def length(P):
    return float(np.linalg.norm(np.diff(np.asarray(P), axis=0), axis=1).sum())


def normals(V, F):
    n = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    return n / (np.linalg.norm(n, axis=1, keepdims=True) + 1e-12)


# ---------- views: (screen u axis, depth axis) in world coords; side view faces left
VIEWS = {"front": ((1, 0, 0), (0, 1, 0)), "left": ((0, 1, 0), (-1, 0, 0)),
         "back": ((-1, 0, 0), (0, -1, 0)), "right": ((0, -1, 0), (1, 0, 0))}


def render(meshes, lines=(), view="front", box=((-0.62, 0.62), (0.80, 1.70)), mpp=0.0022, flip_dark=False):
    """meshes: [(V, F, face colours (n, 3) 0-255)]; lines: [(P (n, 3), colour, width)] drawn where not hidden.
    Orthographic, z-buffered by sampling each triangle (triangles are ~2 px), Lambert from the camera."""
    U, D = np.array(VIEWS[view][0], float), np.array(VIEWS[view][1], float)
    (u0, u1), (z0, z1) = box
    W, H = int((u1 - u0) / mpp), int((z1 - z0) / mpp)
    zb = np.full((H, W), np.inf)
    img = np.full((H, W, 3), 245, np.uint8)
    bary = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1], [1 / 3, 1 / 3, 1 / 3], [.5, .5, 0], [0, .5, .5], [.5, 0, .5],
                     [2 / 3, 1 / 6, 1 / 6], [1 / 6, 2 / 3, 1 / 6], [1 / 6, 1 / 6, 2 / 3]])
    for V, F, C in meshes:
        n = normals(V, F)
        lam = np.abs(n @ -D) * 0.75 + 0.25
        col = np.clip(np.asarray(C, float) * lam[:, None], 0, 255).astype(np.uint8)
        T = V[F]  # (f, 3, 3)
        S = np.einsum("bk,fkd->fbd", bary, T).reshape(-1, 3)
        cc = np.repeat(col, len(bary), axis=0)
        u = ((S @ U - u0) / mpp).astype(int)
        v = ((z1 - S[:, 2]) / mpp).astype(int)
        d = S @ D
        ok = (u >= 0) & (u < W) & (v >= 0) & (v < H)
        u, v, d, cc = u[ok], v[ok], d[ok], cc[ok]
        o = np.argsort(-d)  # far first, near written last
        u, v, d, cc = u[o], v[o], d[o], cc[o]
        better = d < zb[v, u]
        u, v, d, cc = u[better], v[better], d[better], cc[better]
        zb[v, u] = d
        img[v, u] = cc
        zb2 = zb.copy()
        zb2[v, u] = np.minimum(zb2[v, u], d)
        zb = zb2
    im = Image.fromarray(img)
    dr = ImageDraw.Draw(im)
    for P, colour, w in lines:
        P = np.asarray(P, float)
        u = (P @ U - u0) / mpp
        v = (z1 - P[:, 2]) / mpp
        d = P @ D
        ui, vi = np.clip(u.astype(int), 0, W - 1), np.clip(v.astype(int), 0, H - 1)
        seen = d <= zb[vi, ui] + 0.012
        for i in range(len(P) - 1):
            if seen[i] and seen[i + 1]:
                dr.line([(u[i], v[i]), (u[i + 1], v[i + 1])], fill=colour, width=w)
    return im


def sheet(tiles, ref=None, h=700, labels=None):
    """Reference (if given) then the tiles, each scaled to height h, side by side."""
    ims = ([Image.open(ref).convert("RGB")] if ref else []) + list(tiles)
    ims = [im.resize((max(1, int(im.width * h / im.height)), h)) for im in ims]
    out = Image.new("RGB", (sum(i.width for i in ims) + 8 * len(ims), h + 24), (255, 255, 255))
    x = 0
    dr = ImageDraw.Draw(out)
    for k, im in enumerate(ims):
        out.paste(im, (x, 24))
        if labels and k < len(labels):
            dr.text((x + 4, 4), labels[k], fill=(0, 0, 0))
        x += im.width + 8
    return out


PAL = [(214, 39, 40), (31, 119, 180), (44, 160, 44), (148, 103, 189), (255, 127, 14), (140, 86, 75), (227, 119, 194),
       (23, 190, 207), (188, 189, 34), (127, 127, 127)]
