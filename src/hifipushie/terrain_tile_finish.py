"""Finishing a tile: corner normals, creases, split normals, the textured prep, baking and the border. Part of
the terrain mesh (terrain_mesh.py has the overview)."""
from __future__ import annotations

import os
import math

import numpy as np

from . import terrain_sharp
from .profiling import span as _span
from .terrain_field import Metric
from .terrain_gltf import _to_gltf, write_glb
from .terrain_materials import _linear
from .terrain_mesh import _CTX
from .terrain_tile_mesh import _face_normals
from .terrain_volumes import NORMAL_H

def _corner_normals(P, F, field, h):
    """Each face corner's normal read from the field just inside its face (so on its face's side of a crease), and
    that sample point stepped onto the surface. Samples reading across a crease from their face take its normal."""
    fn = _face_normals(P, F)
    Q = (0.75 * P[F] + 0.25 * P[F].mean(1)[:, None, :]).reshape(-1, 3)
    f, g = field.value_gradient(Q, h)
    gl = np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-12)
    Nc = (g / gl).reshape(-1, 3, 3)
    Qs = (Q - (f / gl[:, 0])[:, None] * (g / gl)).reshape(-1, 3, 3)
    off = (Nc * fn[:, None, :]).sum(2) < 0.3
    Nc = np.where(off[..., None], fn[:, None, :], Nc)
    return fn, Nc, Qs


def snap_creases(P, F, field, v, movable, angle=25.0, rounds=2):
    """Vertices beside a crease moved onto it (the point nearest them on the tangent planes their faces see, as dual
    contouring places vertices): marching cubes can't put vertices on a crease that runs across its cells, and the
    crease came out as a row of teeth. Only vertices whose faces turn by more than `angle` are tried; a move is kept
    if it stays within half a voxel, on the surface, and turns no face over."""
    P = P.copy()
    h = NORMAL_H * v
    cosa = math.cos(math.radians(angle))
    for _ in range(rounds):
        fn = _face_normals(P, F)
        vn = _vertex_normals(P, F)
        # candidates: a vertex whose faces disagree with their mean
        worst = np.ones(len(P))
        for c in range(3):
            np.minimum.at(worst, F[:, c], (fn * vn[F[:, c]]).sum(1))
        cand = movable & (worst < cosa)
        if not cand.any():
            break
        # the tangent planes of the candidate and its ring (vertices on the surface, each with the exact normal of
        # its own side): their quadric's minimum is the crease point nearest it, regularised toward where it is
        e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]], F[:, [1, 0]], F[:, [2, 1]], F[:, [0, 2]]])
        e = np.unique(e[cand[e[:, 0]]], axis=0)
        e = np.r_[e, np.repeat(np.flatnonzero(cand), 2).reshape(-1, 2)]
        near = np.unique(e[:, 1])
        _, g = field.value_gradient(P[near], h)
        Nn = np.zeros_like(P)
        Nn[near] = g / np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-12)
        A = np.zeros((len(P), 3, 3))
        b = np.zeros((len(P), 3))
        n = Nn[e[:, 1]]
        nn = n[:, :, None] * n[:, None, :]
        np.add.at(A, e[:, 0], nn)
        np.add.at(b, e[:, 0], (nn @ P[e[:, 1]][:, :, None])[:, :, 0])
        idx = np.flatnonzero(cand)
        eps = 0.05
        Ai = A[idx] + eps * np.eye(3)[None]
        bi = b[idx] + eps * P[idx]
        x = np.linalg.solve(Ai, bi[:, :, None])[:, :, 0]
        mv = np.linalg.norm(x - P[idx], axis=1)
        ok = (mv < 0.6 * v) & (np.abs(field.value(x)) < 0.1 * v)
        idx, x = idx[ok], x[ok]
        old = P[idx].copy()
        P[idx] = x
        # undo moves that turn a face over
        fn2 = _face_normals(P, F)
        flip = (fn2 * fn).sum(1) < 0.2
        if flip.any():
            bad = np.zeros(len(P), bool)
            bad[F[flip].ravel()] = True
            back = bad[idx]
            P[idx[back]] = old[back]
    return P


def _unflip_corners(P, F, N, src, which, fixed=None):
    """Face corners (of faces `which`) whose vertex normal points against the face get a vertex of their own with the
    face's normal. Such a corner shades the face black (a "shard"): a coarse LOD's face bridging air round a stack.
    Vertices `fixed` (on a tile's border) keep one normal: both tiles must draw the border alike (split there, the
    two tiles' border normals differed by 96-142 deg). (P, F, N, src)."""
    k = np.flatnonzero(which)
    if not len(k):
        return P, F, N, src
    fn = np.cross(P[F[k, 1]] - P[F[k, 0]], P[F[k, 2]] - P[F[k, 0]])
    ln = np.linalg.norm(fn, axis=1)
    ok = ln > 1e-12
    fn = fn / np.maximum(ln, 1e-12)[:, None]
    d = np.einsum("fcj,fj->fc", N[F[k]], fn)
    bad = (d < 0) & ok[:, None]
    if fixed is not None:
        bad &= ~fixed[F[k]]
    fi, ci = np.nonzero(bad)
    if not len(fi):
        return P, F, N, src
    f = k[fi]
    v = F[f, ci]
    n0 = len(P)
    F = F.copy()
    F[f, ci] = n0 + np.arange(len(f))
    return (np.vstack([P, P[v]]), F, np.vstack([N, fn[fi]]), np.r_[src, src[v]])


def split_normals(P, F, N, field, keep, h, angle=75.0):
    """Hard edges where the rock creases: each face corner reads the field's normal just inside its face; corners that
    disagree with their vertex's normal by more than `angle` (the other side of a crease, or a vertex whose normal
    faces away from the face: a black shard) get a copy of the vertex with their side's normal, copies shared by
    corners that agree. Vertices in `keep` (tile borders: both tiles must match) never split.
    Returns positions, faces, normals and each new vertex's source vertex."""
    fn, Nc, _ = _corner_normals(P, F, field, h)
    cos = math.cos(math.radians(angle))
    Nv = N[F]
    ok = ((Nc * Nv).sum(2) >= cos) & ((Nv * fn[:, None, :]).sum(2) > 0.1)
    ok |= keep[F]
    if ok.all():
        return P, F, N, np.arange(len(P))
    F2 = F.copy()
    newP, newN, src = [], [], []
    groups = {}
    nxt = len(P)
    for f, c in zip(*np.nonzero(~ok)):
        v = int(F[f, c])
        n = Nc[f, c]
        gl = groups.setdefault(v, [])
        for gi, (s, idx) in enumerate(gl):
            m = s / np.linalg.norm(s)
            if m @ n >= cos:
                gl[gi] = (s + n, idx)
                F2[f, c] = idx
                break
        else:
            gl.append((n.copy(), nxt))
            F2[f, c] = nxt
            src.append(v)
            nxt += 1
    for v, gl in groups.items():
        for s, idx in gl:
            newN.append(s / np.linalg.norm(s))
    order = np.argsort([idx for gl in groups.values() for _, idx in gl])
    newN = np.array(newN)[order]
    src = np.array(src, np.int64)
    return np.vstack([P, P[src]]), F2, np.vstack([N, newN]), np.r_[np.arange(len(P)), src]


def _prim(P, N, C, W, F, material, extras, mats, lo, cfg):
    attrs = {"POSITION": _to_gltf(P), "NORMAL": _to_gltf(N), "COLOR_0": _linear(C)}
    for g in range(0, W.shape[1], 4):
        w = W[:, g:g + 4]
        attrs[f"_WEIGHTS{g // 4}"] = np.c_[w, np.zeros((len(w), 4 - w.shape[1]))]
    sp = int(cfg["splat"])
    if sp:  # splat UVs: the tile's texture, its margin into the neighbours
        mg = int(cfg["splat_margin"])
        Nn = sp + 2 * mg
        u = (P[:, 0] / cfg["tile"] * sp + mg) / Nn
        vv = 1 - (P[:, 1] / cfg["tile"] * sp + mg) / Nn
        attrs["TEXCOORD_0"] = np.c_[u, vv]
    return {"attrs": attrs, "indices": F, "material": material, "extras": extras}


def _textured_prep(P, N, W, F, k, origin, stem):
    """A tile LOD's visible surface with its own UV atlas (terrain_bake): the primitive (material 2, the baked reference
    material), a partial report, and a bake request ({"stem", "k", "n" texels}). Its texels, AO and atlas go to the
    work dir; `_job_bake` bakes the texels in pieces across the pool and `_job_finish` assembles the maps (base colour,
    ORM, normal embedded; height and layer-weight maps beside the GLB in maps/) and writes the GLB."""
    from . import terrain_bake
    c = _CTX
    cfg, v0 = c["cfg"], c["v0"]
    dens = cfg["_density"][min(k, len(cfg["_density"]) - 1)]
    with _span("maps/unwrap"):
        uvc, size, d, _ = terrain_bake.unwrap(P, F, dens, int(cfg["texture_max"]))
    D = c.get("detail")
    with _span("maps/tangents"):
        bins = np.repeat(D.face_bins(P, F)[:, None], 3, 1) if D is not None else None
        sp = terrain_bake.split_corners(P, _unit_rows(N), F, uvc, extra={"W": W}, ids=bins)
        T4 = terrain_bake.tangents(sp["P"], sp["N"], sp["uv"], sp["F"])
    with _span("maps/texels"):
        tx = terrain_bake.texels(sp["uv"], sp["F"], size)
        # texels in space-filling-curve order of where they land (every map value is per texel, so the order is free):
        # a bake piece then covers a compact patch of rock, and its facet triangulations (terrain_facets, cached per
        # process) are few and reused; in atlas order every piece touched the whole tile
        bary = terrain_bake._bary(sp["uv"], sp["F"], tx["size"], tx["t"], tx["xs"], tx["ys"])
        o = _morton(np.einsum("nk,nkc->nc", bary, sp["P"][sp["F"][tx["t"]]]), 2.0)
        for key in ("ys", "xs", "t", "inside"):
            tx[key] = tx[key][o]
    Pa, Na = sp["P"], sp["N"]
    if getattr(c.get("field"), "region", None) is not None and str(stem).startswith("tile"):
        from . import terrain_cliffs
        # (a cliff shell's sunk edge takes the AO of the true ground over it: its vertices metres down read 0, and
        # interpolated up its dive, the strip that shows over the heightmap was black: pushieworld note 104)
        Pa, Na = terrain_cliffs.lifted(c["field"], Pa, Na)
    ao_v = terrain_bake.bake_ao(Metric(c["base"]), Pa, Na)
    info = {}
    if k == 0:  # how well the triangles follow the rock's creases (terrain_sharp.crease_error)
        fn_ = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
        rock = fn_[:, 2] / np.maximum(np.linalg.norm(fn_, axis=1), 1e-12) < math.cos(math.radians(40))
        if rock.sum() > 16:
            with _span("maps/crease error"):
                info["crease"] = terrain_sharp.crease_error(P, F, c["field"], max(0.01, v0 / 32), rock=rock)
    np.savez(c["work"] / f"bake_{stem}.npz", P=sp["P"], N=sp["N"], T4=T4, uv=sp["uv"], F=sp["F"], ao=ao_v,
             size=np.array(tx["size"]), ys=tx["ys"].astype(np.int32), xs=tx["xs"].astype(np.int32), t=tx["t"],
             inside=tx["inside"], fill=np.array(tx["fill_pct"]))
    attrs = {"POSITION": _to_gltf(sp["P"] - origin), "NORMAL": _to_gltf(sp["N"]),
             "TANGENT": np.c_[_to_gltf(T4[:, :3]), T4[:, 3]], "TEXCOORD_0": sp["uv"]}
    sq = int(cfg["splat"])
    if sq:
        mg = int(cfg["splat_margin"])
        Nn = sq + 2 * mg
        Q = sp["P"] - origin
        attrs["TEXCOORD_1"] = np.c_[(Q[:, 0] / cfg["tile"] * sq + mg) / Nn, 1 - (Q[:, 1] / cfg["tile"] * sq + mg) / Nn]
    if D is not None:  # the tiling detail's projection (terrain_swatch.DetailProjection)
        with _span("maps/detail projection"):
            attrs[f"TEXCOORD_{1 + bool(sq)}"] = D.uv(sp["P"], sp["ids"])
            attrs["_DETAIL"] = D.attrs(sp["P"])
    Wv = sp["W"]
    for g in range(0, Wv.shape[1], 4):
        w = Wv[:, g:g + 4]
        attrs[f"_WEIGHTS{g // 4}"] = np.c_[w, np.zeros((len(w), 4 - w.shape[1]))]
    info.update(size=[int(size[0]), int(size[1])], texels_per_m=round(float(d), 2), height=f"maps/{stem}_height.png")
    return ({"attrs": attrs, "indices": sp["F"], "material": 2, "extras": {"role": "surface"}}, info,
            {"stem": stem, "k": k, "n": int(len(tx["t"]))})


def _morton(X, cell):
    """An order of points X (n, 3) along a Z-order curve over cells `cell` m across."""
    q = np.floor((X - X.min(0)) / cell).astype(np.int64)
    key = np.zeros(len(X), np.int64)
    for bit in range(20):
        for a in range(3):
            key |= ((q[:, a] >> bit) & 1) << (3 * bit + a)
    return np.argsort(key, kind="stable")


LIGHTS = {  # render_tiles(light=...) presets: the sky's dust/air (Nishita), sun watts, sky strength, exposure
    "hazy": {"dust": 0.3, "air": 0.8, "sun_energy": 2.4, "sky_strength": 0.12, "exposure": 0.0},
    # matched to a clear sunny photo (the Pebble 7th): its sky deep blue (v ~0.75 s ~0.45 at the top), crisp shadows
    # exposure metered on the sun's height (`meter` stops per doubling of sin(height) over 25 deg)
    "clear": {"dust": 0.02, "air": 1.0, "sun_energy": 3.2, "sky_strength": 0.08, "exposure": -0.35, "meter": 0.8,
              # the sky as the camera sees it, deeper (camera and glossy rays only: the light it casts is unchanged), and
              # the sea a deep blue body with water's IOR (measured against the photo: the sea there h 212 s 0.45-0.49)
              "sky_sat": 1.3, "sky_value": 1.12, "sky_horizon_tint": [0.5, 0.72, 1.0],
              "water": [0.006, 0.028, 0.065], "water_roughness": 0.12,
              "haze_scale": 3.0},  # (clear air: the photo's sea stays deep blue to the horizon, 3 km off)
}


def _light(light):
    """A light preset's settings (render_tiles(light=)): a LIGHTS name, a dict, or {} for none."""
    if isinstance(light, str):
        return LIGHTS.get(light, {})
    return light or {}


RELIEF_CHART = 2.5  # the ground's maps-only relief on cliff tiles is band-limited as if their texel were this x larger:
# their charts' texel grids don't line up across a tile border (ground tiles' do), so fine relief differed there
BAKE_PIECE = 120_000  # texels per bake job (a 64 m tile's LOD 0 atlas at 13-16 texels/m is 1.2-2.6M: 10-20 jobs)


def _job_bake(args):
    """One piece of a tile LOD's atlas: texels [a, b) baked (terrain_bake.bake_texels), saved for _job_finish."""
    from . import terrain_bake
    stem, k, a, b = args
    c = _CTX
    d = np.load(c["work"] / f"bake_{stem}.npz")
    reach = max(0.6, 4 * c["cfg"]["error"][k] + 0.5)
    bf = c["bakefield"][k]
    surface = lambda Pl, Nl: terrain_bake._surface(bf, Pl, Nl, c["v0"], reach)
    lines = None
    if c.get("detail") is not None and c["cfg"].get("lines", True):
        from . import terrain_swatch
        tx_ = 1.0 / c["cfg"]["_density"][min(k, len(c["cfg"]["_density"]) - 1)]
        lines = lambda Pl, Nl: terrain_swatch.structure_lines(c["base"], Pl, tx_, N=Nl)
    vals = terrain_bake.bake_texels(surface, c["mats"], d["P"], d["N"], d["T4"], d["uv"], d["F"], tuple(d["size"]),
                                    d["t"][a:b], d["xs"][a:b], d["ys"][a:b], d["inside"][a:b], c["layer_rough"],
                                    bf, first=a, gfield=c.get("weightfield"), lines=lines,
                                    texel=RELIEF_CHART / c["cfg"]["_density"][min(k, len(c["cfg"]["_density"]) - 1)],
                                    border=_bake_border(c, stem, k),
                                    map_texel=1.0 / c["cfg"]["_density"][min(k, len(c["cfg"]["_density"]) - 1)])
    np.savez(c["work"] / f"baked_{stem}_{a:09d}.npz", **vals)


BORDER_FLAT = 1.5  # texels: every LOD's normal maps eased to the low poly's normal this close to a tile's edge


def _bake_border(c, stem, k):
    """(lo, hi, fade m) for a cliff tile's LOD k bake (terrain_bake.bake_texels `border`), else None."""
    import re
    m = re.match(r"tile_(\d+)_(\d+)_lod(\d+)$", stem)
    if not m or BORDER_FLAT <= 0:  # (LOD 0 too: eased at LOD 1-2 only, LOD 0 against LOD 2 read p50 7.3 deg (limit 6))
        return None
    lo, hi = c["G"].bounds(int(m.group(1)), int(m.group(2)))
    return (lo, hi, BORDER_FLAT / c["cfg"]["_density"][min(k, len(c["cfg"]["_density"]) - 1)])

def _job_finish(stem):
    """A tile LOD's maps assembled from its baked pieces, and its GLB written. Returns (bytes, the maps report)."""
    import pickle
    from PIL import Image
    from . import terrain_bake
    c = _CTX
    out, work = c["out"], c["work"]
    d = np.load(work / f"bake_{stem}.npz")
    tx = {"size": tuple(int(x) for x in d["size"]), "ys": d["ys"], "xs": d["xs"], "t": d["t"], "inside": d["inside"],
          "fill_pct": float(d["fill"])}
    pieces = sorted(work.glob(f"baked_{stem}_*.npz"))
    vals = terrain_bake.concat([dict(np.load(f)) for f in pieces])
    maps, info = terrain_bake.assemble(tx, vals, d["ao"], d["uv"], d["F"])
    with _span("maps/encode + save"):
        (out / "maps").mkdir(exist_ok=True)
        Image.fromarray(maps["height"], "I;16").save(out / "maps" / f"{stem}_height.png")
        wfiles = []
        for g, w in enumerate(maps["weights"]):
            fn = f"maps/{stem}_weights{g}.png"
            Image.fromarray(w, "RGBA").save(out / fn)
            wfiles.append(fn)
        if "lines" in maps:
            Image.fromarray(maps["lines"], "RGBA").save(out / "maps" / f"{stem}_lines.png")
            info["lines"] = f"maps/{stem}_lines.png"
        images = [(terrain_bake.jpeg(maps["basecolor"]), "image/jpeg"),
                  (terrain_bake.png(maps["orm"], "RGB"), "image/png"),
                  (terrain_bake.png(maps["normal"], "RGB"), "image/png")]
    with open(work / f"glb_{stem}.pkl", "rb") as fh:
        glb = pickle.load(fh)
    de = c.get("detail_entry")
    if de is not None:  # the detail layer in the GLB: the lines map embedded, the swatches as files beside it
        ext = {"recipe": "manifest.json detail.recipe", "texCoord_detail": de["texcoord"],
               "attribute": "_DETAIL (strike x, strike y, side share, bed coordinate m)", "size_m": de["size_m"]}
        if "lines" in maps:
            images.append((terrain_bake.png(maps["lines"], "RGBA"), "image/png"))
            ext["lines"] = {"index": len(images) - 1, "texCoord": 0, "range_m": de["line_d"],
                            "channels": "R bed planes, G joints: signed distance (0.5 = on the line, +-range_m); "
                                        "B, A: their strengths"}
        for key in ("albedo", "normal", "rough", "variation"):
            images.append(de[key])
            ext[key] = {"index": len(images) - 1, "texCoord": de["texcoord"]}
        glb["mats"] = [dict(m) for m in glb["mats"]]
        [m for m in glb["mats"] if m["name"] == "terrain_baked"][0]["extras"] = {"hifipushie_detail": ext}
    with _span("maps/write glb"):
        write_glb(glb["path"], glb["name"], glb["prims"], glb["trans"], glb["mats"], extras=glb["extras"],
                  images=images)
    if os.environ.get("HIFIPUSHIE_KEEP_BAKE"):  # (debug: each atlas's texels kept in <out>/_bakes, to re-bake one map
        # alone with terrain_bake.bake_lines while trying line variants)
        (out / "_bakes").mkdir(exist_ok=True)
        import shutil
        shutil.copy(work / f"bake_{stem}.npz", out / "_bakes" / f"bake_{stem}.npz")
    for f in pieces + [work / f"bake_{stem}.npz", work / f"glb_{stem}.pkl"]:
        f.unlink()
    info["weights"] = wfiles
    return glb["path"].stat().st_size, info


def _unit_rows(N):
    return N / np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)


def _compact(P, N, C, W, F):
    """The vertices faces F use, renumbered."""
    used = np.unique(F)
    remap = np.full(len(P), -1, np.int64)
    remap[used] = np.arange(len(used))
    return P[used], N[used], C[used], W[used], remap[F]


def _vertex_normals(P, F):
    fn = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
    vn = np.zeros_like(P)
    for c in range(3):
        np.add.at(vn, F[:, c], fn)
    return vn / np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-20)


def _on_border(P, lo, hi):
    return (P[:, 0] == lo[0]) | (P[:, 0] == hi[0]) | (P[:, 1] == lo[1]) | (P[:, 1] == hi[1])


def _shared(a, b, lo, hi, G):
    """Is edge a-b on a border this tile shares with a neighbour (not the world's edge)?"""
    for ax, lim in ((0, lo[0]), (0, hi[0]), (1, lo[1]), (1, hi[1])):
        if a[ax] == lim and b[ax] == lim:
            return G.lo[ax] < lim < G.hi[ax]
    return False


def _planes(ka, kb, G, k):
    """The border planes (axis, lattice index, tile span index) both endpoints of a border edge lie on."""
    v = G.v(k)
    n = int(round(G.tile / v))
    NX, NY = int(round(G.span[0] / v)), int(round(G.span[1] / v))
    out = []
    for ax, lim in ((0, NX), (1, NY)):
        ca, cb = ka[1 + ax], kb[1 + ax]
        if ka[0] != ax and kb[0] != ax and ca == cb and (ca % n == 0 or ca == lim):
            other = 1 - ax
            span = min(ka[1 + other], kb[1 + other]) // n
            out.append((ax, round(ca * v, 6), span))  # world position of the plane, in metres from the origin
    return out


def _thickness(field, P, d, want, v):
    """How far each point can go along d before it leaves the rock (capped at `want`), minus a margin."""
    out = want.copy()
    step = v / 2
    s = step
    alive = np.ones(len(P), bool)
    while alive.any() and s <= want.max() + step:
        k = np.flatnonzero(alive & (s <= want + step))
        if not len(k):
            break
        f = field.value(P[k] + d[k] * s)
        leave = f > 0
        out[k[leave]] = np.minimum(out[k[leave]], max(s - step, 0.0) + 0.25 * step)
        alive[k[leave]] = False
        s += step
    return out
