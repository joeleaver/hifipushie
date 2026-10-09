"""An OPEN clutter bush, from a grown shrub (the coordinator's read of the first one: a closed leafy dome with sprigs
is a moss-covered rock; a shrub is many thin stems from the ground, foliage in separate masses with sky and ground
between them, an irregular outline, a darker inside).

Three tiers, each made FROM the one before (what vegetation artists do at clutter budgets):
- LOD 0: the grown shrub's stoutest stems as 3-sided tubes + 20-30 alpha spray cards standing where the plant's own
  twigs are (its ~200 twigs clustered; a card runs the way its twigs run and faces out of the bush), darker pictures
  on the inner ones.
- LOD 1: 7 bough cards, each the picture of the LOD 0 sprays of one part of the bush seen from outside (composited
  here in software: every spray quad warped into the bough's plane, far ones first) + the three stoutest stems.
- LOD 2: 2 crossed upright cards with the whole bush (sprays and stems) seen from two sides.
One atlas (a picture per season), one alpha-MASK material, the plants' wind channels; normals lean up and out of the
bush on both faces of a card. No Blender."""
from __future__ import annotations

import math

import numpy as np

from . import clutter

N_BOUGH = 7
STEMS = (6, 3)   # stems drawn as tubes at LOD 0, LOD 1
DARK = 0.6       # the inner sprays' pictures, x the colour


def _kmeans(P, k, iters=20):
    """Deterministic k-means (farthest-point start): labels, centres."""
    k = min(k, len(P))
    c = [P[int(np.argmin(P[:, 2]))]]
    d = np.linalg.norm(P - c[0], axis=1)
    for _ in range(k - 1):
        i = int(d.argmax())
        c.append(P[i])
        d = np.minimum(d, np.linalg.norm(P - P[i], axis=1))
    C = np.array(c)
    for _ in range(iters):
        lab = np.linalg.norm(P[:, None] - C[None], axis=2).argmin(1)
        for j in range(k):
            if (lab == j).any():
                C[j] = P[lab == j].mean(0)
    return lab, C


def grown(cfg: dict, k: int) -> dict:
    """Variant k's shrub: stems [(points, radii)] stoutest first, twigs (pos, run), height; 1 m across its foliage."""
    from . import veg_leaf, vegetation
    f = cfg["form"]
    vf = (cfg.get("variant_forms") or [{}])
    o = vf[k % len(vf)]
    spec = {"species": "shrub", "seed": int(cfg["seed"]) * 10 + k + 1, "height": 1.0,
            "habit": {"stems": int(o.get("stems", f["stems"])), "stem_angle": float(o.get("stem_angle", f["stem_angle"]))}}
    tree = vegetation.grow(spec)
    tw = veg_leaf.place_live(tree)
    P, par, rad, ax = tree["pos"], tree["parent"], tree["radius"], tree["axis"]
    tp, run = tw["pos"], tw["frame"][:, 1] if tw["frame"].shape[1:] == (3, 3) else tw["frame"][:, :, 1]
    lo, hi = tp.min(0), tp.max(0)
    s = 1.0 / max(hi[0] - lo[0], hi[1] - lo[1])
    aspect = float(o.get("height", f["height"]))  # height / width asked: the shrub squashed or stretched to it
    cx = np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, 0.0])
    zs = aspect / max((hi[2]) * s, 1e-6)
    tr = lambda X: (X - cx) * s * [1, 1, zs]
    stems = []
    for a in np.unique(ax[1:]):
        nodes = np.flatnonzero(ax == a)
        nodes = nodes[nodes > 0]
        if len(nodes) < 2:
            continue
        pts = np.vstack([P[par[nodes[0]]], P[nodes]])
        rr = np.r_[rad[nodes[0]], rad[nodes]]
        L = float(np.linalg.norm(np.diff(pts, axis=0), axis=1).sum())
        stems.append((float(rr.max()) * L, tr(pts), rr * s))
    stems.sort(key=lambda t: -t[0])
    return {"stems": [(p, r) for _, p, r in stems], "twigs": tr(tp), "run": run / np.maximum(np.linalg.norm(run, axis=1, keepdims=True), 1e-9),
            "H": float(tr(tp)[:, 2].max()), "twig_len": float(tree["spec"]["leaves"]["twig"]["length"]) * s}


def _tube(pts, rad, sides, keep):
    """A stem as an open tube: (V, N, F); `keep` points along it (ends kept)."""
    idx = np.unique(np.round(np.linspace(0, len(pts) - 1, min(keep, len(pts)))).astype(int))
    pts, rad = pts[idx], np.clip(rad[idx], 0.005, 0.014)
    V, N, F = [], [], []
    for i, (c, r) in enumerate(zip(pts, rad)):
        d = pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]
        d /= np.linalg.norm(d)
        a = np.cross(d, [0, 0, 1.0] if abs(d[2]) < 0.9 else [1.0, 0, 0])
        a /= np.linalg.norm(a)
        b = np.cross(d, a)
        for j in range(sides):
            t = 2 * math.pi * j / sides
            n = math.cos(t) * a + math.sin(t) * b
            V.append(c + r * n)
            N.append(n)
    for i in range(len(pts) - 1):
        for j in range(sides):
            p0, p1 = i * sides + j, i * sides + (j + 1) % sides
            F += [[p0, p1, p1 + sides], [p0, p1 + sides, p0 + sides]]
    V, N, F = np.array(V), np.array(N), np.array(F)
    fn = np.cross(V[F[0, 1]] - V[F[0, 0]], V[F[0, 2]] - V[F[0, 0]])
    if fn @ N[F[0, 0]] < 0:
        F = F[:, ::-1]
    return V, N, F


def bough_tile(px: int, paint: dict, color, season: dict, seed: int, dark: float = 1.0):
    """A leafy spray for a card: three shoots fanning from the bottom middle, leaves alternate along each: (rgb, alpha)."""
    from PIL import Image, ImageDraw
    from scipy import ndimage
    sp = paint["spray"]
    rng = np.random.default_rng(seed)
    S = 4 * px
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    col = np.asarray(color, float)
    if season.get("mix") is not None:
        col = col * (1 - season["amount"]) + np.asarray(season["mix"], float) * season["amount"]
    col = col * dark
    steps = int(paint.get("steps") or 0)
    wood = tuple(int(255 * c) for c in np.clip(col * [1.1, 0.8, 0.7] * 0.55, 0, 1)) + (255,)
    shoots = [(0.0, 1.0)] + [(sg * rng.uniform(0.4, 0.62), rng.uniform(0.62, 0.82)) for sg in (-1, 1)] + \
             [(sg * rng.uniform(0.16, 0.3), rng.uniform(0.75, 0.95)) for sg in (-1, 1)]
    for lean, length in sorted(shoots, key=lambda t: -abs(t[0])):
        bend = rng.uniform(-0.1, 0.1)
        base0 = np.array([0.5, 0.99])

        def stem(t):
            a = lean + bend * math.sin(t * 2.2)
            return base0 + 0.93 * length * t * np.array([math.sin(a), -math.cos(a)])
        dr.line([tuple((stem(t) * S).tolist()) for t in np.linspace(0, 1, 14)], fill=wood, width=max(2, S // 110))
        n = max(4, int(round(int(rng.integers(sp["leaves"][0], sp["leaves"][1] + 1)) * length * 0.75)))
        for i in range(n):
            t = min((i + 0.9) / (n + 0.3) * rng.uniform(0.95, 1.05), 1.0)
            b = stem(t)
            side = 1 if i % 2 == 0 else -1
            ang = lean + (math.radians(rng.uniform(34, 64)) * side if i < n - 1 else rng.uniform(-0.2, 0.2))
            d = np.array([math.sin(ang), -math.cos(ang)])
            L = clutter._u(rng, sp["leaf"]) / 0.34 * (0.7 + 0.4 * math.sin(math.pi * min(t + 0.15, 1.0)))
            W = L * sp["round"]
            nr = np.array([-d[1], d[0]])
            us = np.linspace(0, 1, 9)
            poly = [b + d * L * u + nr * W * 0.5 * math.sin(math.pi * u ** 0.8) for u in us] + \
                   [b + d * L * u - nr * W * 0.5 * math.sin(math.pi * u ** 0.8) for u in us[::-1][1:]]
            tone = 1 + sp["tones"] * rng.uniform(-1, 1) - 0.22 * (1 - t)
            if steps:
                tone = round(tone * steps) / steps
            c = tuple(int(255 * x) for x in np.clip(col * tone, 0, 1)) + (255,)
            xy = [tuple((np.asarray(q_) * S).tolist()) for q_ in poly]
            dr.polygon(xy, fill=c)
            if sp.get("outline"):
                dr.line(xy + [xy[0]], fill=tuple(int(255 * x) for x in np.clip(col * 0.25, 0, 1)) + (255,), width=max(2, int(sp["outline"] * S)))
            if sp.get("midrib"):
                dr.line([tuple((b * S).tolist()), tuple(((b + d * L * 0.9) * S).tolist())],
                        fill=tuple(int(255 * x) for x in np.clip(col * tone * (1 + sp["midrib"]), 0, 1)) + (255,), width=max(1, S // 300))
            if season.get("flowers") and paint.get("flowers") and rng.uniform() < paint["flowers"] * 1.4:
                ce = (b + d * L * rng.uniform(0.1, 0.5)) * S
                r = paint["flower_size"] / 0.34 * S * rng.uniform(0.9, 1.4)
                dr.ellipse([ce[0] - r, ce[1] - r, ce[0] + r, ce[1] + r], fill=tuple(int(255 * x) for x in paint["flower_color"]) + (255,))
    return im.resize((px, px), Image.LANCZOS)


def _fatten(im, px: int):
    """A far card's picture with its alpha grown by `px` (and the colour under it): thin leaves average under the
    cut-off in the first mip levels and a far bush vanishes; grown, its cover holds (what vegetation artists do to
    billboard atlases)."""
    from PIL import Image, ImageFilter
    a = np.asarray(im, float) / 255.0
    a = _bleed(a)
    al = Image.fromarray((a[..., 3] * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(2 * px + 1))
    a[..., 3] = np.asarray(al, float) / 255.0
    return Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8), "RGBA")


def _bleed(a):
    """RGBA float (h, w, 4): the colour of the nearest solid texel under every empty one (mips stay leaf-coloured)."""
    from scipy import ndimage
    solid = a[..., 3] > 0.5
    if solid.any() and not solid.all():
        idx = ndimage.distance_transform_edt(~solid, return_distances=False, return_indices=True)
        a[..., :3] = a[..., :3][idx[0], idx[1]]
    return a


def _persp(dst, src):
    """PIL PERSPECTIVE coefficients taking output pixels `dst` (4 x 2) to source pixels `src` (4 x 2)."""
    A, b = [], []
    for (x, y), (u, v) in zip(dst, src):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        b += [u, v]
    try:
        return np.linalg.solve(np.array(A, float), np.array(b, float)).tolist()
    except np.linalg.LinAlgError:
        return None


def composite(quads, tiles, origin, r, u, ext, size, stems=None, stem_color=(60, 45, 30)):
    """The picture of spray quads [(corners 4 x 3: bottom-left, bottom-right, top-right, top-left; tile index)] seen
    square on a plane (origin, right r, up u; ext = (r0, r1, u0, u1) m), far ones first: an RGBA PIL image `size`."""
    from PIL import Image, ImageDraw
    W, H = size
    n = np.cross(r, u)
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    to_px = lambda X: np.c_[((X - origin) @ r - ext[0]) / (ext[1] - ext[0]) * W, (1 - ((X - origin) @ u - ext[2]) / (ext[3] - ext[2])) * H]
    if stems:
        dr = ImageDraw.Draw(out)
        for pts, rad in stems:
            p = to_px(pts)
            w = max(1, int(round(float(rad.mean()) * 2 / (ext[1] - ext[0]) * W)))
            dr.line([tuple(q) for q in p.tolist()], fill=tuple(stem_color) + (255,), width=w)
    order = sorted(range(len(quads)), key=lambda i: float((quads[i][0].mean(0) - origin) @ n))
    for i in order:
        Q, ti = quads[i]
        tile = tiles[ti]
        tw, th = tile.size
        d = to_px(Q)  # bl, br, tr, tl in the output
        co = _persp(d, [[0, th], [tw, th], [tw, 0], [0, 0]])
        if co is None:
            continue
        x0, y0 = np.floor(d.min(0)).astype(int) - 1
        x1, y1 = np.ceil(d.max(0)).astype(int) + 1
        if x1 <= 0 or y1 <= 0 or x0 >= W or y0 >= H:
            continue
        layer = tile.transform((W, H), Image.PERSPECTIVE, co, Image.BILINEAR)
        out = Image.alpha_composite(out, layer)
    return out


def _mask(quads, tiles, az, R, H, px=96):
    """What the cards cover seen from the side (deg): a boolean picture (the outline AND the gaps)."""
    a = math.radians(az)
    r = np.array([math.cos(a), math.sin(a), 0.0])
    im = composite(quads, tiles, np.zeros(3), r, np.array([0, 0, 1.0]), (-R, R, 0.0, H), (px, int(px * H / (2 * R)) + 1))
    return np.asarray(im)[..., 3] > 127


def build(spec: dict, progress=None) -> dict:
    """The open bush: variants' three LODs and the atlas per season (see the module's text). Same shape as clutter.build."""
    from PIL import Image
    cfg = clutter.resolve(spec)
    f, paint = cfg["form"], cfg["paint"]
    nv = min(cfg["variants"], 4)
    base = cfg["atlas"]
    c4, c8 = base // 4, base // 8
    seasons = cfg["seasons"]
    # the sprays' pictures: two light, two dark (the inside of a bush)
    tiles = {se: [bough_tile(c4, paint, cfg["color"], sv, cfg["seed"] * 100 + t, dark=1.0 if t < 2 else DARK) for t in range(4)]
             for se, sv in seasons.items()}
    atl = {se: Image.new("RGBA", (base, base), (0, 0, 0, 0)) for se in seasons}
    for se in seasons:
        for t in range(4):
            atl[se].paste(tiles[se][t], (t * c4, 0))
    bark = tuple(int(255 * c) for c in np.clip(np.asarray(cfg["color"]) * [1.3, 0.9, 0.7] * 0.8, 0, 1))
    out = []
    for k in range(nv):
        G = grown(cfg, k)
        H = G["H"]
        rng = np.random.default_rng([cfg["seed"], k, 911])
        n0 = int(rng.integers(f["cards"][0], f["cards"][1] + 1))
        lab, C = _kmeans(G["twigs"], n0)
        rad_xy = np.linalg.norm(C[:, :2], axis=1)
        inner = (rad_xy < 0.55 * np.median(rad_xy)) | ((C[:, 2] < 0.45 * H) & (rad_xy < 0.9 * np.median(rad_xy)))
        quads, frames = [], []
        for j in range(len(C)):
            m = lab == j
            if not m.any():
                continue
            out_dir = np.r_[C[j, :2], 0.0]
            out_dir = out_dir / np.linalg.norm(out_dir) if np.linalg.norm(out_dir) > 1e-3 else np.array([1.0, 0, 0])
            a = G["run"][m].mean(0) * 0.5 + out_dir * 0.35 + np.array([0, 0, 0.45])
            a /= np.linalg.norm(a)
            rt = np.cross(a, out_dir)
            rt = rt / np.linalg.norm(rt) if np.linalg.norm(rt) > 1e-3 else np.array([0, 1.0, 0])
            nrm0 = np.cross(rt, a)
            ro = rng.uniform(-0.9, 0.9)  # turned about its run: not every card square to the outside
            rt = rt * math.cos(ro) + nrm0 * math.sin(ro)
            spread = float(np.linalg.norm(G["twigs"][m] - C[j], axis=1).mean()) if m.sum() > 1 else 0.0
            L = float(np.clip(2.0 * spread + 1.1 * G["twig_len"], f["card"][0], f["card"][1]))
            b = C[j] - a * L * 0.5
            b[2] = max(b[2], 0.02)
            w = 0.5 * L
            Q = np.array([b - rt * w, b + rt * w, b + rt * w + a * L, b - rt * w + a * L])
            Q[:, 2] += max(0.0, 0.01 - float(Q[:, 2].min()))  # (no spray under the ground)
            ti = int(rng.integers(0, 2)) + (2 if inner[j] else 0)
            quads.append((Q, ti))
            nn = out_dir * 0.6 + np.array([0, 0, 0.8])
            frames.append((nn / np.linalg.norm(nn), rt, float(rng.uniform())))
        R = float(max(np.abs(np.concatenate([q for q, _ in quads])[:, :2]).max(), 0.5)) * 1.02
        Htop = float(np.concatenate([q for q, _ in quads])[:, 2].max()) * 1.02

        def card_mesh(Q, uvpx, nn, rt, phase, branch=(0.5, 1.0), flutter=(0.0, 1.0)):
            tt = rt - nn * (nn @ rt)
            tt /= max(np.linalg.norm(tt), 1e-9)
            wsg = 1.0 if np.cross(nn, tt) @ (Q[3] - Q[0]) > 0 else -1.0
            trk = lambda z: float(np.clip(z / max(Htop, 1e-6), 0, 1.3) ** 1.5)
            wind = [[trk(Q[0][2]), branch[0], phase, flutter[0]], [trk(Q[1][2]), branch[0], phase, flutter[0]],
                    [trk(Q[2][2]), branch[1], phase, flutter[1]], [trk(Q[3][2]), branch[1], phase, flutter[1]]]
            # front and back are triangles on vertices of their own (the same normal on both: a card lit by its face flickers):
            # two faces on the same three vertices are one face to Blender's importer, and the back went missing
            uv = np.asarray(uvpx, float) / base
            return {"V": np.r_[Q, Q], "N": np.tile(nn, (8, 1)), "UV": np.r_[uv, uv], "T": np.tile(np.r_[tt, wsg], (8, 1)),
                    "F": np.array([[0, 1, 2], [0, 2, 3], [4, 6, 5], [4, 7, 6]]), "wind": np.r_[np.array(wind), np.array(wind)]}

        def stems_mesh(n, keep):
            parts = []
            x0, y0 = 7 * c8 + c8 // 2, c4 + k * c8 + c8 // 2  # the bark patch: variant k's last bough cell
            for pts, rr in G["stems"][:n]:
                V, N_, F_ = _tube(pts, rr, 3, keep)
                trk = np.clip(V[:, 2] / max(Htop, 1e-6), 0, 1.3) ** 1.5
                parts.append({"V": V, "N": N_, "UV": np.tile([x0 / base, y0 / base], (len(V), 1)),
                              "T": np.tile([1.0, 0, 0, 1.0], (len(V), 1)), "F": F_,
                              "wind": np.c_[trk, 0.3 * trk, np.full(len(V), 0.37 * k % 1.0), np.zeros(len(V))]})
            return parts

        def join(parts, cards):
            V, o = [], 0
            L = {key: [] for key in ("V", "N", "UV", "T", "wind")}
            F = []
            for p in parts:
                for key in L:
                    L[key].append(p[key])
                F.append(p["F"] + o)
                o += len(p["V"])
            L = {key: np.concatenate(v) for key, v in L.items()}
            L["F"] = np.concatenate(F)
            L["triangles"] = int(len(L["F"]))
            L["cards"] = cards
            return L
        # ---- LOD 0
        l0 = stems_mesh(STEMS[0], 4)
        for (Q, ti), (nn, rt, ph) in zip(quads, frames):
            x0 = ti * c4
            m_ = 1.5
            l0.append(card_mesh(Q, [[x0 + m_, c4 - m_], [x0 + c4 - m_, c4 - m_], [x0 + c4 - m_, m_], [x0 + m_, m_]], nn, rt, ph))
        L0 = join(l0, len(quads))
        # ---- LOD 1: bough cards, each the picture of its sprays from outside
        cen = np.array([q.mean(0) for q, _ in quads])
        blab, BC = _kmeans(cen, N_BOUGH)
        l1 = stems_mesh(STEMS[1], 3)
        bq = []
        for g in range(len(BC)):
            mem = [quads[i] for i in np.flatnonzero(blab == g)]
            if not mem:
                continue
            od = np.r_[BC[g, :2], 0.0]
            od = od / np.linalg.norm(od) if np.linalg.norm(od) > 1e-3 else np.array([1.0, 0, 0])
            nn = od * 0.9 + np.array([0, 0, 0.45])
            nn /= np.linalg.norm(nn)
            r_ = np.cross([0, 0, 1.0], nn)
            r_ /= np.linalg.norm(r_)
            u_ = np.cross(nn, r_)
            pts = np.concatenate([q for q, _ in mem])
            pr, pu = (pts - BC[g]) @ r_, (pts - BC[g]) @ u_
            ext = (float(pr.min()), float(pr.max()), float(pu.min()), float(pu.max()))
            cx_, cy_ = (g % 8) * c8, c4 + k * c8
            for se in seasons:
                pic = _fatten(composite(mem, tiles[se], BC[g], r_, u_, ext, (c8, c8)), 2)
                atl[se].paste(pic, (cx_, cy_))
            Q = np.array([BC[g] + r_ * ext[0] + u_ * ext[2], BC[g] + r_ * ext[1] + u_ * ext[2],
                          BC[g] + r_ * ext[1] + u_ * ext[3], BC[g] + r_ * ext[0] + u_ * ext[3]])
            m_ = 1.0
            n2 = od * 0.6 + np.array([0, 0, 0.8])
            l1.append(card_mesh(Q, [[cx_ + m_, cy_ + c8 - m_], [cx_ + c8 - m_, cy_ + c8 - m_], [cx_ + c8 - m_, cy_ + m_], [cx_ + m_, cy_ + m_]],
                                n2 / np.linalg.norm(n2), r_, float(rng.uniform()), branch=(0.4, 0.9), flutter=(0.1, 0.6)))
            bq.append((Q, (se, cx_, cy_)))
        L1 = join(l1, len(bq))
        # the bark patch (variant k's eighth bough cell)
        for se in seasons:
            atl[se].paste(Image.new("RGBA", (c8, c8), bark + (255,)), (7 * c8, c4 + k * c8))
        # ---- LOD 2: two crossed upright cards with the whole bush on them
        l2, cq = [], []
        a0 = float(rng.uniform(0, math.pi))
        for ci in range(2):
            a = a0 + ci * math.pi / 2
            r_ = np.array([math.cos(a), math.sin(a), 0.0])
            u_ = np.array([0, 0, 1.0])
            ext = (-R, R, 0.0, Htop)
            cx_, cy_ = (k * 2 + ci) * c8, 3 * c4
            for se in seasons:
                pic = _fatten(composite(quads, tiles[se], np.zeros(3), r_, u_, ext, (c8, c4), stems=G["stems"][:STEMS[0]], stem_color=bark), 2)
                atl[se].paste(pic, (cx_, cy_))
            Q = np.array([r_ * -R, r_ * R, r_ * R + u_ * Htop, r_ * -R + u_ * Htop])
            m_ = 1.0
            l2.append(card_mesh(Q, [[cx_ + m_, cy_ + c4 - m_], [cx_ + c8 - m_, cy_ + c4 - m_], [cx_ + c8 - m_, cy_ + m_], [cx_ + m_, cy_ + m_]],
                                np.array([0, 0, 1.0]), r_, 0.37 * k % 1.0, branch=(0.0, 0.5), flutter=(0.0, 0.3)))
            cq.append(Q)
        L2 = join(l2, 2)
        # ---- how well the tiers keep the bush's cover (alpha and all), from two sides
        se0 = "summer"
        ious = [[], []]
        for az in (20.0, 110.0):
            m0 = _mask(quads, tiles[se0], az, R, Htop)
            A = np.asarray(atl[se0])
            b1 = [(Q, i) for i, (Q, _) in enumerate(bq)]
            t1 = [Image.fromarray(A[cy: cy + c8, cx: cx + c8]) for _, (_, cx, cy) in bq]
            m1 = _mask(b1, t1, az, R, Htop)
            t2 = [Image.fromarray(A[3 * c4: 4 * c4, (k * 2 + ci) * c8: (k * 2 + ci + 1) * c8]) for ci in range(2)]
            m2 = _mask([(Q, i) for i, Q in enumerate(cq)], t2, az, R, Htop)
            for i_, m_ in enumerate((m1, m2)):
                ious[i_].append(float((m0 & m_).sum() / max((m0 | m_).sum(), 1)))
        L0["iou"], L1["iou"], L2["iou"] = 1.0, round(float(np.mean(ious[0])), 3), round(float(np.mean(ious[1])), 3)
        m0 = _mask(quads, tiles[se0], 20.0, R, Htop)
        hull_fill = float(m0.mean())
        out.append({"name": f"v{k}", "lods": [L0, L1, L2], "collision": None, "height": round(Htop, 4), "sink": 0.0,
                    "bounds": [[-R, -R, 0.0], [R, R, round(Htop, 4)]], "open": round(1 - hull_fill, 3)})
        if progress:
            progress(f"bush {cfg['style']} variant {k}: {L0['triangles']} / {L1['triangles']} / {L2['triangles']} triangles, "
                     f"{len(quads)} sprays -> {len(bq)} boughs -> 2 crossed cards; cover kept {L1['iou']:.2f} / {L2['iou']:.2f}; "
                     f"{1 - hull_fill:.0%} of its side view is gaps")
    albs = {se: _bleed(np.asarray(im, float) / 255.0) for se, im in atl.items()}
    nrm = np.zeros((16, 16, 3))
    nrm[..., :] = [0.5, 0.5, 1.0]
    orm = np.ones((16, 16, 3))
    orm[..., 1], orm[..., 2] = float(paint["roughness"]), 0.0
    return {"cfg": cfg, "variants": out, "albedo": albs, "normal": nrm, "orm": orm}
