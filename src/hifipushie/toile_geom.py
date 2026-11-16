"""Geometry for the TOILE (step 4 of drape first, toile.py): exact mesh clipping by a scalar, components, welding,
boundary loops, polylines, the armhole CONE, the shoulder pad's wedge, and a software rasterizer (orthographic
z-buffer, Lambert, no GPU) for the 4-view look beside the reference. Ported from spikes r1_common / r2b_common (R1, R2b).

THE ARMHOLE RULE (a tailor's, C491): the armhole is the body's own armhole loop carried out to the garment along rays
from the shoulder joint (a cone with its apex in the joint), never a plane fitted to the loop: the plane leaves the loop
where the toile stands off the body and puts the sleeve's crown into the body."""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components


def smooth01(a):
    a = np.clip(a, 0, 1)
    return a * a * (3 - 2 * a)


def smin(a, b, k):
    """Smooth minimum (polynomial, blend width k)."""
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
    return b + (a - b) * h - k * h * (1 - h)


def clip(V, F, phi):
    """Mesh (V, F) clipped exactly to phi >= 0 (phi per vertex, linear on each triangle): new vertices on cut edges."""
    phi = np.asarray(phi, float).copy()
    phi[np.abs(phi) < 1e-9] = 1e-9
    pos = phi > 0
    keep = pos[F].all(1)
    part = pos[F].any(1) & ~keep
    newV, cache, add = [V], {}, []
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

    for f in F[part]:
        s = pos[f]
        if s.sum() == 1:
            i = int(np.argmax(s))
            a, b, c = f[i], f[(i + 1) % 3], f[(i + 2) % 3]
            add.append([a, mid(a, b), mid(a, c)])
        else:
            i = int(np.argmin(s))
            a, b, c = f[i], f[(i + 1) % 3], f[(i + 2) % 3]
            mb, mc = mid(a, b), mid(a, c)
            add += [[mb, b, c], [mb, c, mc]]
    out = [F[keep]] + ([np.array(add, int)] if add else [])
    return compact(np.concatenate(newV), np.concatenate(out))


def compact(V, F):
    used = np.unique(F)
    remap = -np.ones(len(V), int)
    remap[used] = np.arange(len(used))
    return V[used], remap[F]


def components(F, nV) -> np.ndarray:
    """Face labels: faces joined across shared edges."""
    E = np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), axis=1)
    fid = np.tile(np.arange(len(F)), 3)
    key = E[:, 0].astype(np.int64) * nV + E[:, 1]
    o = np.argsort(key, kind="stable")
    k, f = key[o], fid[o]
    same = k[1:] == k[:-1]
    A = coo_matrix((np.ones(int(same.sum())), (f[:-1][same], f[1:][same])), shape=(len(F), len(F)))
    return connected_components(A, directed=False)[1]


def largest(V, F):
    if not len(F):
        return V, F
    lab = components(F, len(V))
    return compact(V, F[lab == np.bincount(lab).argmax()])


def weld(V, F, tol=1e-6):
    """Vertices closer than tol merged (two halves cut on the same plane join there)."""
    key = np.round(V / tol).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    F2 = inv.reshape(-1)[F]
    F2 = F2[(F2[:, 0] != F2[:, 1]) & (F2[:, 1] != F2[:, 2]) & (F2[:, 2] != F2[:, 0])]
    return compact(V[first], F2)


def edge_counts(F):
    E = np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), axis=1)
    return np.unique(E, axis=0, return_counts=True)


def boundary_loops(F) -> list:
    """The free edges' loops, as vertex index lists (an edge used once is free)."""
    E, c = edge_counts(F)
    free = E[c == 1]
    nbr = {}
    for a, b in free:
        nbr.setdefault(int(a), []).append(int(b))
        nbr.setdefault(int(b), []).append(int(a))
    seen, loops = set(), []
    for s in nbr:
        if s in seen:
            continue
        loop, prev, cur = [s], None, s
        seen.add(s)
        while True:
            nxt = [n for n in nbr[cur] if n != prev and n not in seen]
            if not nxt:
                break
            prev, cur = cur, nxt[0]
            seen.add(cur)
            loop.append(cur)
        loops.append(loop)
    return loops


def resample(P, step=0.004):
    P = np.asarray(P, float)
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    k = max(2, int(np.ceil(s[-1] / step)) + 1)
    t = np.linspace(0, s[-1], k)
    return np.c_[[np.interp(t, s, P[:, i]) for i in range(P.shape[1])]].T


def length(P) -> float:
    return float(np.linalg.norm(np.diff(np.asarray(P, float), axis=0), axis=1).sum())


def outward(V, F):
    """Faces wound so a closed-ish surface's normals point out (its signed volume about the centroid positive)."""
    c = V.mean(0)
    vol = np.einsum("ij,ij->i", V[F[:, 0]] - c, np.cross(V[F[:, 1]] - c, V[F[:, 2]] - c)).sum()
    return F if vol >= 0 else F[:, ::-1].copy()


def normals(V, F):
    n = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    return n / (np.linalg.norm(n, axis=1, keepdims=True) + 1e-12)


def slice_points(V, F, z) -> np.ndarray:
    """Where the mesh crosses the plane at height z: one point per crossed edge of each crossed triangle."""
    d = V[:, 2] - z
    s = d[F] > 0
    cross = s.any(1) & ~s.all(1)
    out = []
    for i, j in ((0, 1), (1, 2), (2, 0)):
        a, b = F[cross, i], F[cross, j]
        m = (d[a] > 0) != (d[b] > 0)
        t = d[a[m]] / (d[a[m]] - d[b[m]])
        out.append(V[a[m]] + t[:, None] * (V[b[m]] - V[a[m]]))
    return np.concatenate(out) if out else np.zeros((0, 3))


class Cone:
    """The armhole (module doc): apex O on the arm's axis A, `back` m in from the shoulder; the loop's angle from the
    axis as a function of the azimuth round it. sdist(P) > 0 inside the cone (the sleeve side), in metres."""

    def __init__(self, sh, A, loop, back=0.05):
        self.A = A / np.linalg.norm(A)
        self.O = sh - back * self.A
        e1 = np.cross(self.A, [0, 1.0, 0])
        self.e1 = e1 / np.linalg.norm(e1)
        self.e2 = np.cross(self.A, self.e1)
        ps, al = self.polar(loop)
        o = np.argsort(ps)
        self.PS, self.AL = ps[o], al[o]

    def polar(self, P):
        d = np.atleast_2d(P) - self.O
        n = np.linalg.norm(d, axis=1) + 1e-12
        return np.arctan2(d @ self.e2, d @ self.e1), np.arccos(np.clip((d @ self.A) / n, -1, 1))

    def sdist(self, P):
        ps, al = self.polar(P)
        return (np.interp(ps, self.PS, self.AL, period=2 * np.pi) - al) * np.linalg.norm(np.atleast_2d(P) - self.O, axis=1)


def pad_thickness(P, x_sp, y_sh, z_sh, T, inward=0.13, over=0.03, half_w=0.11, drop=0.12):
    """A shoulder pad's thickness at P (folded to the left side): T at the shoulder point, thinning to nothing `inward`
    m toward the neck and `over` m past the point, cos^2 across the shoulder (half width `half_w` front and back of the
    shoulder line y_sh(x)), only on top of the shoulder (within `drop` m under the shoulder line z_sh(x))."""
    x = np.abs(P[:, 0])
    u = smooth01((x - (x_sp - inward)) / inward) * smooth01((x_sp + over - x) / over)
    dy = (P[:, 1] - y_sh(x)) / half_w
    v = np.where(np.abs(dy) < 1, np.cos(np.pi / 2 * dy) ** 2, 0.0)
    w = smooth01((P[:, 2] - (z_sh(x) - drop)) / 0.04)
    return T * u * v * w


# ---------- the look: views (screen u axis, depth axis) in world coords; the side view faces left
VIEWS = {"front": ((1, 0, 0), (0, 1, 0)), "left": ((0, 1, 0), (-1, 0, 0)),
         "back": ((-1, 0, 0), (0, -1, 0)), "right": ((0, -1, 0), (1, 0, 0))}
_BARY = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1], [1 / 3, 1 / 3, 1 / 3], [.5, .5, 0], [0, .5, .5], [.5, 0, .5],
                  [2 / 3, 1 / 6, 1 / 6], [1 / 6, 2 / 3, 1 / 6], [1 / 6, 1 / 6, 2 / 3]])


def zbuffer(meshes, view, box, mpp):
    """(image, depth buffer): meshes [(V, F, face colours)] orthographic, sampled per triangle, Lambert from the camera."""
    U, D = np.array(VIEWS[view][0], float), np.array(VIEWS[view][1], float)
    (u0, u1), (z0, z1) = box
    W, H = int((u1 - u0) / mpp), int((z1 - z0) / mpp)
    zb = np.full((H, W), np.inf)
    img = np.full((H, W, 3), 245, np.uint8)
    for V, F, C in meshes:
        if not len(F):
            continue
        lam = np.abs(normals(V, F) @ -D) * 0.75 + 0.25
        col = np.clip(np.asarray(C, float) * lam[:, None], 0, 255).astype(np.uint8)
        S = np.einsum("bk,fkd->fbd", _BARY, V[F]).reshape(-1, 3)
        cc = np.repeat(col, len(_BARY), axis=0)
        u = ((S @ U - u0) / mpp).astype(int)
        v = ((z1 - S[:, 2]) / mpp).astype(int)
        d = S @ D
        ok = (u >= 0) & (u < W) & (v >= 0) & (v < H)
        u, v, d, cc = u[ok], v[ok], d[ok], cc[ok]
        o = np.argsort(-d)
        u, v, d, cc = u[o], v[o], d[o], cc[o]
        b = d < zb[v, u]
        u, v, d, cc = u[b], v[b], d[b], cc[b]
        zb[v, u] = d  # (far first: the nearest sample is written last)
        img[v, u] = cc
    return img, zb


def render(meshes, lines=(), view="front", box=((-0.62, 0.62), (0.80, 1.70)), mpp=0.0022):
    img, zb = zbuffer(meshes, view, box, mpp)
    U, D = np.array(VIEWS[view][0], float), np.array(VIEWS[view][1], float)
    (u0, _), (_, z1) = box
    im = Image.fromarray(img)
    dr = ImageDraw.Draw(im)
    H, W = zb.shape
    for P, colour, w in lines:
        P = np.asarray(P, float)
        u, v, d = (P @ U - u0) / mpp, (z1 - P[:, 2]) / mpp, P @ D
        seen = d <= zb[np.clip(v.astype(int), 0, H - 1), np.clip(u.astype(int), 0, W - 1)] + 0.012
        for i in range(len(P) - 1):
            if seen[i] and seen[i + 1]:
                dr.line([(u[i], v[i]), (u[i + 1], v[i + 1])], fill=colour, width=w)
    return im


def sheet(tiles, ref=None, h=700, labels=None):
    """Reference (if given) then the tiles, each scaled to height h, side by side."""
    ims = ([Image.open(ref).convert("RGB")] if ref else []) + list(tiles)
    ims = [im.resize((max(1, int(im.width * h / im.height)), h)) for im in ims]
    out = Image.new("RGB", (sum(i.width for i in ims) + 8 * len(ims), h + 24), (255, 255, 255))
    x, dr = 0, ImageDraw.Draw(out)
    for k, im in enumerate(ims):
        out.paste(im, (x, 24))
        if labels and k < len(labels):
            dr.text((x + 4, 4), labels[k], fill=(0, 0, 0))
        x += im.width + 8
    return out
