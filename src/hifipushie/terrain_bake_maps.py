"""Baking a tile's maps: fine rock relief, the surface's texels, lines, ambient occlusion, `assemble`, `bake`. Part of the terrain's bake (terrain_bake.py has the overview)."""
from __future__ import annotations

import math

import numpy as np
from scipy import ndimage

from . import terrain_bake
from . import noise, profiling
from . import terrain_relief
from .profiling import span as _span
from .terrain_bake import _unit
from .terrain_bake_unwrap import _raster

def micro_relief(r, amount=1.0, texel=0.1, fine=True):
    """A function p -> field offset: rock detail finer than the meshing voxel (facets 1.2 m and 0.45 m across, thin
    cracks along a coarser facet net's zero lines, the bedding plane's notch, laminae every sixth of a bed).
    Centimetres deep: for normal and height maps only. Band-limited to the map's texel: a feature narrower than
    ~4 texels fades out (sampled anyway it aliased, and two tiles' texels at a shared border read different
    normals)."""
    seed = r["seed"] + 77
    keep = lambda width: float(np.clip((width / texel - 3.0) / 3.0, 0.0, 1.0))  # 0 below 3 texels, 1 from 6
    a1, a2, ac = keep(1.2), keep(0.45), keep(0.3)
    if not fine:  # (the tiling detail draws everything under ~0.5 m: terrain_swatch. Its 0.45 m facets here were
        # the bake's smallest facet size, so most of its facet triangulations: a cost per square metre, not per texel)
        a2 = 0.0
    an, al = keep(0.6), keep(0.24)
    bed = r.get("bed")

    J = r.get("joints")

    def f(p, fd=None, u=None, g=None, I=None):
        fac = lambda size, sd: terrain_relief.facet(p, size, sd, fd, u)  # (irregular triangles on faces: terrain_facets)
        out = 0.06 * a1 * fac(1.2, seed)
        if a2 > 0:
            out = out + 0.015 * a2 * fac(0.45, seed + 1)
        if J and ac > 0:  # hairline cracks along the joint sets, on their candidate planes (most not meshed)
            for m, d in enumerate(J["dirs"][:2]):
                sp = J["spacing"][m]
                q = (p[:, :2] @ np.asarray(d)) / sp + 0.37 * terrain_relief._pl_facets(p, 2.0, seed + 9 + m)
                dist = np.abs(q - np.round(q)) * sp
                out = out + 0.03 * ac * np.clip(1 - dist / 0.12, 0, 1) ** 2
        if r.get("blocks") and fd is not None and (ac > 0 or al > 0):
            # the rock structure's fine lines (terrain_blocks): open joints, the open bed planes and every thin bed's
            # planes as notches; closed joints are left to the geometry's change of face
            from . import terrain_blocks
            if I is None:
                zoff = r["bed_offset"](p[:, :2]) if r.get("bed_offset") else 0.0
                I = terrain_blocks.ids(p, r["blocks"], fd, zoff)
            notch = lambda d, wd: np.clip(1 - d / wd, 0, 1) ** 2
            # (a thin bed's planes notched only where its package sits back, as much as it does: notched all along,
            # three notches in 0.6 m drew the pebble chasm's dark band in the normal map, the mesh smooth there)
            thin = np.zeros(len(p))
            k = np.flatnonzero(I["thin"])
            if len(k):
                thin[k] = terrain_blocks.package_recess(p[k, :2], I["K"][k], I["j"][k], r["blocks"])
            cr = np.maximum(I["bed_crack"], 0.5 * thin) * notch(I["bed_edge"], 0.22)
            for m, w in enumerate(I["weights"]):
                cr = np.maximum(cr, w * notch(I["open"][m], 0.22))
            out = out + 0.07 * max(ac, al) * cr
        if ac > 0 and not r.get("blocks"):  # (with blocks, the cracks are the structure's open joints)
            c = fac(3.1, seed + 2)
            out = out + 0.06 * ac * np.clip(1 - np.abs(c) / 0.1, 0, 1) ** 2  # cracks where the net crosses zero
        if bed and (an > 0 or al > 0) and not r.get("blocks"):  # (with blocks their bed planes are the beds: the big
            # beds' notch drew two dark lines along the whole pebble chasm)
            B = terrain_relief.bed_planes(p, r, g)
            zb = B["z"]
            e = np.abs(zb - np.round(zb)) * bed  # m from the nearest bedding plane
            # the bedding plane's notch: a smooth trough (a cusp stair-stepped when a close view magnified its texels)
            # (broken along its length, only where the plane shows at all, its width wandering: an unbroken dark line
            # of one width on every bed read as a seam). The noise only within the widest notch of a plane (1.45 x
            # 0.35 m): everywhere it was a large share of the micro relief's cost
            kn = np.flatnonzero(e < 0.35 * 1.45)
            if len(kn):
                nz = noise.fbm(p[kn] * np.array([1.0, 1.0, 0.2]), 6.0, 2, seed=seed + 5)
                u = np.clip(1 - e[kn] / (0.35 * (0.55 + 0.9 * nz)), 0, 1)
                brk = np.clip((nz - 0.42) * 3.5, 0, 1) * B["pres"][kn]
                out = out + 0.0  # (a copy: `out` may be a view of an earlier term)
                out[kn] = out[kn] + 0.14 * an * u * u * (3 - 2 * u) * brk
            if al > 0 and not r.get("blocks"):  # (with blocks, the thin beds are the laminae)
                z = zb * 6.0
                fr = z - np.floor(z)
                out = out + 0.025 * al * np.clip(1 - np.minimum(fr, 1 - fr) * bed / 6.0 / 0.12, 0, 1)
        if I is not None and "sharp" in I:  # (the structure filtered at ~2 texels, not the mesh's 2 voxels)
            out = out + I["sharp"]
        return amount * out
    # the rock structure in the maps: its offsets filtered over +-`sharp` instead of the mesh's +-ramp (Field._solid
    # asks terrain_blocks.structure for the difference): crisper edges at LOD 0 (2-voxel ramps read soft at 40 m),
    # never under 2 texels (narrower aliased as teeth), never softer than the mesh, and not below 0.25 m: the seam
    # check compares LOD 0's maps with LOD 2's (0.4 m texels, the mesh's ramp) at border points up to 0.6 m apart, and
    # 0.1 m edges made them differ by 6-7 deg at the median (limit 6); at 0.25 m they agree within it
    if r.get("blocks"):
        f.sharp = float(np.clip(2.0 * texel, terrain_bake.SHARP_MIN, r["blocks"]["ramp"]))
    return f


# ---------------------------------------------------------------- baking
def _surface(field, X, N0, v, reach):
    """Newton steps from X onto the field's surface (each capped at half a voxel; a texel that strays further than
    `reach` from where it started keeps its low-poly point), then the field's normal there."""
    X0 = X.copy()
    X = X.copy()
    h = max(0.01, v / 16)
    todo = np.arange(len(X))
    f = np.full(len(X), np.inf)
    g = np.zeros_like(X)
    for it in range(7):
        if not len(todo):
            break
        ft, gt = field.value_gradient(X[todo], h)
        f[todo], g[todo] = ft, gt
        if it == 6:
            break
        st = (ft / np.maximum((gt * gt).sum(1), 1e-12))[:, None] * gt
        n = np.linalg.norm(st, axis=1, keepdims=True)
        st *= np.minimum(1.0, 0.5 * v / np.maximum(n, 1e-12))
        # a step under 2 mm is the last: the gradient just taken is the normal there (a separate normal pass
        # was a sixth of the bake)
        last = n[:, 0] <= 2e-3
        X[todo[~last]] -= st[~last]
        todo = todo[~last]
    moved = np.linalg.norm(X - X0, axis=1)
    G = _unit(g)
    # (strayed, turned away, or never reached the surface: steps capped at half a voxel ran out)
    bad = (moved > reach) | ((G * N0).sum(1) < -0.2) | ~np.isfinite(G).all(1) | (np.abs(f) > 0.05 + 0.1 * v)
    X[bad], G[bad] = X0[bad], N0[bad]
    return X, G, bad


def _grain(X):
    """0..1 value noise over ~1 m (roughness variation)."""
    from . import noise
    return noise.fbm(X, 1.3, 3, seed=91)


def ambient(field, X, G):
    """Occlusion from the field (0 closed .. 1 open): how much rock stands within 0.3-6.4 m of each point along its
    normal and four directions tipped 50 deg from it (a crevice, a cave's back, the foot of a wall read dark)."""
    T = _unit(np.cross(G, np.where(np.abs(G[:, 2:3]) < 0.9, [[0, 0, 1.0]], [[1.0, 0, 0]])))
    B = np.cross(G, T)
    dirs = [G] + [_unit(G * math.cos(0.87) + math.sin(0.87) * (math.cos(a) * T + math.sin(a) * B))
                  for a in (0.3, 1.87, 3.44, 5.01)]
    occ = np.zeros(len(X))
    wsum = 0.0
    for dvec in dirs:
        for i, d in enumerate((0.3, 0.8, 1.6, 3.2, 6.4)):
            w = 0.5 ** i
            f = field.value(X + dvec * d)
            occ += w * np.clip((d - f) / d, 0, 1)
            wsum += w
    return np.clip(1.0 - 1.6 * occ / wsum, 0.0, 1.0)


def _chunked(fn, *arrays):
    """fn over the rows of `arrays` in CHUNK-sized pieces, outputs concatenated (a tuple or a single array)."""
    n = len(arrays[0])
    if n <= terrain_bake.CHUNK:
        return fn(*arrays)
    parts = [fn(*(a[i:i + terrain_bake.CHUNK] for a in arrays)) for i in range(0, n, terrain_bake.CHUNK)]
    if isinstance(parts[0], tuple):
        return tuple(np.concatenate([p[j] for p in parts]) for j in range(len(parts[0])))
    return np.concatenate(parts)


def texels(uv, F, size):
    """The texels an atlas bake fills: every texel a triangle covers, plus gutters (texels within 3.5 of a chart take
    its nearest covered texel's triangle, extrapolated). {"size", "ys", "xs", "t" (triangle per texel), "inside"}."""
    Wd, Hd = (size, size) if np.isscalar(size) else size
    tris = uv[F] * np.array([Wd, Hd], float)  # texel space, x right, y down
    ids = _raster(tris, Wd, Hd)
    covered = ids >= 0
    dist, (iy, ix) = ndimage.distance_transform_edt(~covered, return_indices=True)
    gut = (~covered) & (dist <= 3.5)
    ys, xs = np.nonzero(covered | gut)
    t = np.where(covered[ys, xs], ids[ys, xs], ids[iy[ys, xs], ix[ys, xs]])
    return {"size": (int(Wd), int(Hd)), "ys": ys, "xs": xs, "t": t, "inside": covered[ys, xs],
            "fill_pct": round(100 * float(covered.mean()), 1)}


def _bary(uv, F, size, t, xs, ys):
    tris = uv[F[t]] * np.array(size, float)
    q = np.stack([xs + 0.5, ys + 0.5], -1)
    a_, b_, c_ = tris[:, 0], tris[:, 1], tris[:, 2]
    v0, v1, v2 = b_ - a_, c_ - a_, q - a_
    den = v0[:, 0] * v1[:, 1] - v1[:, 0] * v0[:, 1]
    den = np.where(np.abs(den) < 1e-12, 1e-12, den)
    w1 = (v2[:, 0] * v1[:, 1] - v1[:, 0] * v2[:, 1]) / den
    w2 = (v0[:, 0] * v2[:, 1] - v2[:, 0] * v0[:, 1]) / den
    bary = np.stack([1 - w1 - w2, w1, w2], -1)
    # (gutters extrapolate a little past the edge; never far.) Clipped weights no longer sum to 1: a gutter texel of a
    # sliver triangle then landed at a fraction of its world position, hundreds of metres off (tile 10,3 of pebble
    # baked gutter texels at the arch 450 m away: an export of one tile read another's rock). Those take the triangle's
    # nearest point instead.
    out = np.clip(bary, -1.0, 2.0)
    off = np.abs(out.sum(1) - 1.0) > 1e-9
    if off.any():
        near = np.clip(bary[off], 0.0, 1.0)
        out[off] = near / near.sum(1, keepdims=True)
    return out


def bake_texels(surface, mats, P, N, T4, uv, F, size, t, xs, ys, inside, layers_rough, field=None, first=0,
                gfield=None, lines=None, texel=None, border=None, map_texel=None):
    """The per-texel part of a bake (pointwise, so an atlas can be baked in pieces): each texel's point on the low poly,
    moved onto the surface (`surface`), and its values quantised as the maps store them. `first`: the index of the
    first texel in the whole atlas's order (the texel-error sample is every 7th texel of the atlas). `texel` (m): the
    map's texel, for the ground's maps-only relief (Materials.relief: tussocks, scrub lumps, mower stripes; band-limited
    to what the texel carries). `border` (lo, hi, fade m): the normal map eased to flat (the low poly's own normal, the
    same on both sides) within `fade` of the tile's edges: at LOD 1-2 a border triangle is a few texels, and the two
    tiles' texels across a sheer crease read different rock (pebble's LOD 1 seams p95 15.8 deg, single borders 30-40)."""
    bary = _bary(uv, F, size, t, xs, ys)
    corner = lambda A: np.einsum("nk,nkc->nc", bary, A[F[t]])
    Pl = corner(P)
    Nl = _unit(corner(N))
    Tl = corner(T4[:, :3])
    Tl = _unit(Tl - Nl * (Tl * Nl).sum(1, keepdims=True))
    Bl = np.cross(Nl, Tl) * np.sign(T4[F[t, 0], 3])[:, None]
    profiling.count("bake texels", len(Pl))
    with _span("bake/surface (Newton + normal)"):
        X, G, bad = _chunked(surface, Pl, Nl)
    if field is not None and hasattr(field, "unsunk"):  # (a cliff shell's sunk edge: the true ground's normal)
        with _span("bake/unsunk"):
            # (bad texels too: a texel that fell back to the low poly on the dive kept the dive's normal, and its
            # weights picked rock: the dark line stayed)
            G = _unsunk(field, X, G, max(0.01, 0.25 * (map_texel or 0.125)))
            w_sunk = _chunked(lambda q: field.lift(q)[0], X)
    else:
        w_sunk = None
    height = ((X - Pl) * Nl).sum(1)
    tn = np.stack([(G * Tl).sum(1), (G * Bl).sum(1), (G * Nl).sum(1)], -1)
    tn[:, 2] = np.maximum(tn[:, 2], 0.02)
    tn = _unit(tn)
    if border is not None:
        blo, bhi, fade = border
        db = np.minimum(np.min(Pl[:, :2] - np.asarray(blo, float)[:2], 1), np.min(np.asarray(bhi, float)[:2] - Pl[:, :2], 1))
        wb = np.clip(db / max(fade, 1e-6), 0.0, 1.0)
        wb = wb * wb * (3 - 2 * wb)
        if w_sunk is not None:  # (not on a shell's sunk edge: its normal is the true ground's, the same in both tiles)
            wb = wb + (1 - wb) * w_sunk
        tn = _unit(tn * wb[:, None] + np.array([0.0, 0.0, 1.0]) * (1 - wb)[:, None])
    # layer weights and colour from the normal over ~half a metre (the fine relief's own normal flipped rock/grass
    # texel by texel, and two tiles sampling a border a texel apart disagreed). Every value is taken per texel from
    # its own world point, or interpolated from its own triangle's vertices: never filtered across the atlas image,
    # where neighbouring texels belong to unrelated charts (a sparse grid + blur there bled one chart into the next
    # and drew lines along every tile border)
    # (on a cliff shell's sunk edge, the point moved up onto the true ground over it first: what shows of the sunk
    # construction is coloured as that ground, and the weights' normal is the rock's unsunk (`gfield`): see
    # terrain_cliffs.UNSUNK_BAND)
    Xc = X
    if field is not None and hasattr(field, "lift"):
        w_, q_ = _chunked(field.lift, X)
        Xc = X + w_[:, None] * (q_ - X)
    Gs = G
    if field is not None:
        with _span("bake/normal 0.4 m"):
            gf = field if gfield is None else gfield  # (gfield: the same for every LOD; see terrain_mesh)
            Gs = _unit(_chunked(lambda q: gf.value_gradient(q, 0.4)[1], Xc))
        Gs = np.where(bad[:, None], G, Gs)
        if hasattr(gf, "unsunk"):
            Gs = _unsunk(gf, X, Gs, 0.4)
    with _span("bake/weights + colour"):
        Wt, col = _chunked(mats.weights, Xc, Gs)
    if texel and getattr(mats, "ground", None) is not None and hasattr(mats, "relief"):
        # the ground's own fine relief (grass, scrub, the mower's lean) tilts the normal; the geometry has none of it
        with _span("bake/ground relief"):
            gr = _chunked(lambda q, w: mats.relief(q, w, texel), X, Wt)
        live = ~bad & (np.abs(gr).sum(1) > 0)
        if live.any():
            G2 = _unit(G[live] - np.c_[gr[live], np.zeros(int(live.sum()))])
            t2 = np.stack([(G2 * Tl[live]).sum(1), (G2 * Bl[live]).sum(1), (G2 * Nl[live]).sum(1)], -1)
            t2[:, 2] = np.maximum(t2[:, 2], 0.02)
            tn[live] = _unit(t2)
    # roughness varies over a metre or so (one value per layer read as plastic, the wet band most of all)
    with _span("bake/roughness grain"):
        # (on rock and wet rock; grass and sand only a little: a mown fairway's 0.77-1.0 roughness patches caught a
        # high sun as soft sheen blotches a few metres across)
        lr = getattr(mats, "layers", None) or []
        stony = sum((Wt[:, i] for i, nm in enumerate(lr) if nm in ("rock", "wet_rock")), np.zeros(len(Wt)))
        amp = 0.35 * stony + 0.06 * (1.0 - stony)
        rgh = np.clip((Wt @ layers_rough) * (1.0 - amp * (0.43 - _grain(X))), 0.05, 1.0)
    q8 = lambda a: np.round(a * 255).clip(0, 255).astype(np.uint8)
    out = {"height": height, "normal": q8(tn * 0.5 + 0.5), "basecolor": q8(np.clip(col, 0, 1)),
           "rough": q8(np.clip(rgh, 0.02, 1)), "bad": bad,
           "weights": q8(np.c_[Wt, np.zeros((len(Wt), (-Wt.shape[1]) % 4))])}
    if lines is not None:  # the structure's lines as signed distances (terrain_swatch_lines.structure_lines)
        with _span("bake/lines"):
            out["lines"] = _lines_vals(lines, Pl, Nl)
    err = np.zeros(0)
    jump, jump_at = np.zeros(0, np.float32), np.zeros((0, 3))
    if field is not None:  # texel error: how far the baked points sit off the exact surface (every 7th atlas texel)
        k = np.flatnonzero(inside & ~bad & ((np.arange(len(X)) + first) % 7 == 0))
        with _span("bake/texel error"):
            err = np.abs(field.value(X[k])) if len(k) else err
        # jumps: the field's normal at two stencils (3 and 6 cm, as the normal map's own) on soft ground. A smooth surface (or
        # a designed step a few texels wide: the turf's riser) reads the same at both; a step in the field's VALUE reads
        # 1 / h steep, so the two disagree right at it. That is what drew pushieworld's dashed cracks on the grass (the
        # rock relief stepping in at its weight's cull, 2-3 cm): the maps' normal shades a sub-texel step as a dark line.
        ks = k[stony[k] < terrain_bake.JUMP_SOFT] if map_texel else k[:0]
        if len(ks) and hasattr(field, "relief_at"):  # (and where the rock character is all but absent: its own creases
            # and block edges are designed and band-limited, and on a rock face they read as steps at 3 cm)
            ks = ks[field.relief_at(X[ks, 0], X[ks, 1]) < terrain_bake.JUMP_RELIEF]
        if len(ks) and hasattr(field, "designed_step"):  # (nor where a step is designed: a turf riser, a bunker's edge)
            ks = ks[~field.designed_step(X[ks, 0], X[ks, 1])]
        if len(ks) and hasattr(field, "near_volume"):
            ks = ks[~field.near_volume(X[ks])]
        if len(ks):
            with _span("bake/jumps"):
                h1 = terrain_bake.JUMP_H
                nrm = lambda h: _unsunk(field, X[ks], _unit(field.value_gradient(X[ks], h)[1]), h) \
                    if hasattr(field, "unsunk") else _unit(field.value_gradient(X[ks], h)[1])
                g1, g2 = nrm(h1), nrm(2 * h1)
                jump = np.degrees(np.arccos(np.clip((g1 * g2).sum(1), -1, 1))).astype(np.float32)
                jump_at = X[ks][jump > terrain_bake.JUMP_DEG]
                jump = jump[jump > terrain_bake.JUMP_DEG]
    out["err"] = err
    out["jump"] = jump
    out["jump_at"] = jump_at
    return out


def _unsunk(field, X, G, h):
    """Normals G at points X on a cliff shell's front, eased to the true ground's where the front is the sunk
    construction at the region's edge (terrain_cliffs.CliffField.unsunk): what shows of it, a few cm before it dives
    under the heightmap, must read as the ground there, not as a steep dark crease."""
    def f(x, g):
        w, gt = field.unsunk(x, h)
        k = np.flatnonzero(w > 0)
        if not len(k):
            return g
        g = g.copy()
        g[k] = _unit(g[k] * (1 - w[k, None]) + _unit(gt[k]) * w[k, None])
        return g
    return _chunked(f, X, G)


def _lines_vals(lines, Pl, Nl):
    """The lines map's texels (RGBA uint8): `lines(Pl, Nl)` -> (s_bed, a_bed, s_joint, a_joint) at each texel's point
    on the low poly, with the low poly's interpolated (smooth) normal there (terrain_swatch_lines.structure_lines)."""
    from .terrain_swatch import LINE_D
    sb, ab, sj, aj = _chunked(lines, Pl, Nl)
    q8 = lambda a: np.round(a * 255).clip(0, 255).astype(np.uint8)
    return q8(np.c_[0.5 + 0.5 * sb / LINE_D, 0.5 + 0.5 * sj / LINE_D, ab, aj])


def bake_lines(lines, P, N, uv, F, size, t, xs, ys):
    """The lines map's texels alone (bake_texels' lines, for trying line variants on a kept bake: HIFIPUSHIE_KEEP_BAKE)."""
    bary = _bary(uv, F, size, t, xs, ys)
    Pl = np.einsum("nk,nkc->nc", bary, P[F[t]])
    Nl = _unit(np.einsum("nk,nkc->nc", bary, N[F[t]]))
    return _lines_vals(lines, Pl, Nl)


def bake_ao(ao_field, P, N):
    """AO at the mesh's vertices (identical on both sides of a tile border; interpolated over each triangle when the
    maps are assembled: it's broad over metres)."""
    with _span("bake/ao (vertices)"):
        return _chunked(lambda a, b: ambient(ao_field, a, b), P, _unit(N))


def assemble(tx, vals, ao_v, uv, F, field=True):
    """The maps of an atlas from its texels (`texels`) and their values (`bake_texels`, concatenated in texel order):
    each texel's value at its texel, dilated into the empty space (never filtered across the atlas: neighbouring texels
    belong to unrelated charts)."""
    Wd, Hd = tx["size"]
    ys, xs, t, inside = tx["ys"], tx["xs"], tx["t"], tx["inside"]
    with _span("bake/images (dilate)"):
        if ao_v is not None:
            bary = _bary(uv, F, tx["size"], t, xs, ys)
            ao = np.clip(np.einsum("nk,nk->n", np.clip(bary, 0, 1) / np.clip(bary, 0, 1).sum(1, keepdims=True),
                                   ao_v[F[t]]), 0, 1)
        else:
            ao = np.ones(len(xs))
        filled = np.zeros((Hd, Wd), bool)
        filled[ys, xs] = True
        _, (fy, fx) = ndimage.distance_transform_edt(~filled, return_indices=True)

        def img(v, fill):
            out = np.full((Hd, Wd) + v.shape[1:], fill, v.dtype)
            out[ys, xs] = v
            return out[fy, fx]  # (dilated into the empty space)
        q8 = lambda a: np.round(a * 255).clip(0, 255).astype(np.uint8)
        maps = {"normal": img(vals["normal"], 128), "basecolor": img(vals["basecolor"], 128)}
        orm = np.stack([q8(ao), vals["rough"], np.zeros(len(ao), np.uint8)], -1)
        maps["orm"] = img(orm, 128)
        height = vals["height"]
        hr = float(max(np.abs(height).max(), 1e-3))
        maps["height"] = np.round(img(height / hr * 0.5 + 0.5, 0.5) * 65535).astype(np.uint16)
        W = vals["weights"]
        maps["weights"] = [img(W[:, g:g + 4], 0) for g in range(0, W.shape[1], 4)]
        if "lines" in vals:
            maps["lines"] = img(vals["lines"], 128)
    bad = vals["bad"]
    extra = {}
    if field and inside.any():
        r = vals["err"] if len(vals["err"]) else np.zeros(1)
        extra["texel_error_mm_p50_p99"] = [round(1000 * float(np.percentile(r, q)), 2) for q in (50, 99)]
    if "jump" in vals:  # (steps in the field on soft ground: see bake_texels)
        extra["jumps"] = int(len(vals["jump"]))
        if len(vals["jump"]):
            o = np.argsort(-vals["jump"])[:4]
            extra["jump_at"] = [[round(float(c), 1) for c in vals["jump_at"][i]] + [round(float(vals["jump"][i]), 1)]
                                for i in o]
    return maps, {**extra, "height_range_m": round(hr, 4), "texels": int(inside.sum()),
                  "fallback_pct": round(100 * float(bad[inside].mean()), 3) if inside.any() else 0.0,
                  "fill_pct": tx["fill_pct"],
                  "height_abs_p99_m": round(float(np.percentile(np.abs(height[inside]), 99)), 4) if inside.any()
                  else 0.0}


def concat(parts):
    """bake_texels results of consecutive texel ranges, joined."""
    return {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}


def bake(surface, ao_field, mats, P, N, T4, uv, F, size, layers_rough, field=None, texel=None):
    """Every map of one mesh's atlas (size = (width, height)): {"normal": uint8 (h, w, 3), "orm", "basecolor",
    "weights": [RGBA...], "height": uint16}, plus the height range and how many texels fell back to the low poly.
    (texels + bake_texels + assemble in one process; the tile export runs bake_texels in pieces across its pool.)"""
    with _span("bake/raster + texels"):
        tx = texels(uv, F, size)
    vals = bake_texels(surface, mats, P, N, T4, uv, F, tx["size"], tx["t"], tx["xs"], tx["ys"], tx["inside"],
                       layers_rough, field, texel=texel)
    ao_v = bake_ao(ao_field, P, N) if ao_field is not None else None
    return assemble(tx, vals, ao_v, uv, F, field is not None)
