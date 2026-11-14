"""The tile export's worker jobs and their pool: maps, ground, marching cubes, the dense field, the field build,
the swatch, the fingerprint and the budget check. Part of the terrain mesh (terrain_mesh.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import terrain_mesh
from . import fieldjit, terrain_sharp
from .profiling import span as _span
from .terrain_field import Field, project
from .terrain_relief import rock_config
from .terrain_tile_border import _collapse_border
from .terrain_tile_finish import snap_creases
from .terrain_tile_mesh import _border_keys, _boundary_edges, _tile_mc
from .terrain_volumes import _sea, stacks, through_view, volumes

def _pool():
    """A fork pool sized by free memory (`resources.workers`), guarded: 16 fixed workers x ~2 GB plus other jobs
    OOM-killed the user's desktop twice."""
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor
    from . import resources
    n = resources.workers(terrain_mesh._CTX.get("worker_gb", terrain_mesh.WORKER_GB), cap=16)
    fieldjit.warm()  # (compiled kernels in the parent: the forked workers inherit them, none compiles its own)
    # (one BLAS thread a worker: each inherited the parent's 4, which spun on every small matmul)
    ex = ProcessPoolExecutor(max_workers=n, mp_context=multiprocessing.get_context("fork"),
                             initializer=resources._worker_init)
    return resources.guarded(ex, "terrain tiles")


def _job_maps(args):
    """A tile's heightmap (2^k + 1 samples, edges shared with the neighbours) and splat PNGs (runs in a worker)."""
    from PIL import Image
    i, j, lo = args
    c = terrain_mesh._CTX
    G, field, mats, cfg, out, hrange = c["G"], c["base"], c["mats"], c["cfg"], c["out"], c["hrange"]
    lo = np.array(lo)
    extra = {}
    hm = int(cfg["heightmap"]) if cfg["mode"] == "full" else 0  # (cliffs: the ground tiles wrote theirs)
    if hm:
        s = np.linspace(0, G.tile, hm)
        X, Y = np.meshgrid(lo[0] + s, lo[1] + s)
        h, _ = field.column(X.ravel(), Y.ravel())
        h = np.ascontiguousarray(h.reshape(hm, hm)[::-1], np.float32)  # north-up rows, C order on disk
        np.save(out / "heightmaps" / f"height_{i}_{j}.npy", h)
        q = np.round((h - hrange[0]) / (hrange[1] - hrange[0]) * 65535).clip(0, 65535).astype(np.uint16)
        Image.fromarray(q).save(out / "heightmaps" / f"height_{i}_{j}.png")
        extra["heightmap"] = f"heightmaps/height_{i}_{j}.npy"
    sp = int(cfg["splat"])
    if sp:
        mg = int(cfg["splat_margin"])
        Nn = sp + 2 * mg
        d = G.tile / sp
        cc = lo[0] + (np.arange(Nn) - mg + 0.5) * d
        r = lo[1] + (np.arange(Nn) - mg + 0.5) * d
        X, Y = np.meshgrid(cc, r[::-1])  # row 0 = north
        h, _ = field.column(X.ravel(), Y.ravel())
        P = np.c_[X.ravel(), Y.ravel(), h]
        _, g = field.value_gradient(P, 0.125)
        Nm = g / np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-12)
        W, _ = mats.weights(P, Nm)
        files = []
        for g4 in range(0, len(mats.layers), 4):
            ch = W[:, g4:g4 + 4]
            ch = np.c_[ch, np.zeros((len(ch), 4 - ch.shape[1]))]
            img = (np.clip(ch, 0, 1) * 255 + 0.5).astype(np.uint8).reshape(Nn, Nn, 4)
            fn = f"splats/splat{g4 // 4}_{i}_{j}.png"
            Image.fromarray(img, "RGBA").save(out / fn)
            files.append(fn)
        extra["splats"] = files
    return extra


def _job_ground(ij):
    from . import terrain_cliffs_ground
    c = terrain_mesh._CTX
    i, j = ij
    lo, _ = c["G"].bounds(i, j)
    return terrain_cliffs_ground.ground_tile(c["region"], c["mats"], i, j, lo, int(c["cfg"]["heightmap"]) or 65,
                                      c["G"].lods, c["out"], c["cfg"])


def _job_mc(ij):
    """A tile's marching cubes and its border vertices' lattice-edge keys (runs in a worker)."""
    c = terrain_mesh._CTX
    i, j = ij
    if hasattr(c["field"], "empty") and c["field"].empty(*c["G"].bounds(i, j)):
        return None
    r = _tile_mc(c["field"], c["G"], i, j, 0, c["vols"])
    if r is None:
        return None
    idx, faces, rng = r
    (_, _), (_, _), n, (NX, NY) = c["G"].cells(i, j, 0)
    kk = _border_keys(idx, rng, n, NX, NY)
    # the dense mesh goes to disk (per tile, streamed): only the border keys and edges come back to the parent,
    # which had held every tile's meshes at once
    np.savez(_work(c, "mc", i, j), idx=idx, faces=faces)
    bed = [(int(a), int(b)) for a, b in _boundary_edges(faces) if a in kk and b in kk]
    return rng, kk, bed


def _work(c, kind, i, j, k=None):
    return c["work"] / (f"{kind}_{i}_{j}.npz" if k is None else f"{kind}_{i}_{j}_{k}.npy")


def _dense(c, ij):
    d = np.load(_work(c, "dense", *ij))
    return d["P"], d["faces"], d["vrow"]


def _job_dense(ij):
    """A tile's LOD0 mesh: marching cubes on the lattice, interior projected, border vertices the canonical ones."""
    c = terrain_mesh._CTX
    G, v0, field, reg, CP = c["G"], c["v0"], c["field"], c["reg"], c["CP"]
    rng, kk, _ = c["mc"][ij]
    d = np.load(_work(c, "mc", *ij))
    idx, faces = d["idx"], d["faces"]
    P = np.c_[G.origin[0] + idx[:, 0] * v0, G.origin[1] + idx[:, 1] * v0, (idx[:, 2] + terrain_mesh.ZOFF) * v0]
    border = np.array(sorted(kk), np.int64)
    rows = np.array([reg[kk[q]] for q in border], np.int64)
    alias, gone = c.get("alias") or {}, np.zeros(0, np.int64)
    if alias and any(int(r) in alias for r in rows):  # (welded rows: their vertices merged, `_weld_rows`)
        rows = np.array([alias.get(int(r), int(r)) for r in rows], np.int64)
        orig = np.array([reg[kk[q]] for q in border], np.int64)
        remap = np.arange(len(P))
        first = {}
        for v, r, o in sorted(zip(border.tolist(), rows.tolist(), orig.tolist()), key=lambda t: (t[1], t[2] != t[1], t[0])):
            if r in first:
                remap[v] = first[r]
            else:
                first[r] = v
        gone = np.flatnonzero(remap != np.arange(len(P)))
        faces = remap[faces]
        faces = faces[(faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 0] != faces[:, 2])]
    inner = np.setdiff1d(np.arange(len(P)), border)
    N = np.zeros_like(P)
    with _span("dense/project"):
        P[inner], N[inner] = project(field, P[inner], v0)
    P[border], N[border] = CP[rows], c["CN"][rows]
    mov = np.ones(len(P), bool)
    mov[border] = False
    if c["cfg"].get("sharp", True):  # creases on mesh edges (extended marching cubes), not a sawtooth
        n0 = len(P)
        to_world = lambda q: np.array([G.origin[0] + q[0] * v0, G.origin[1] + q[1] * v0, (q[2] + terrain_mesh.ZOFF) * v0])
        with _span("dense/sharp features"):
            P, faces, N, _ = terrain_sharp.feature_points(P, faces, idx, N, field, to_world, v0, mov,
                                                          bounds=G.bounds(*ij))
        mov = np.r_[mov, np.ones(len(P) - n0, bool)]
    else:
        P = snap_creases(P, faces, field, v0, mov)
    vrow = np.full(len(P), -1, np.int64)
    vrow[border] = rows
    vrow[gone] = -1  # (merged into their weld's kept vertex: unused)
    with _span("dense/specks + save"):
        clr = None
        if hasattr(field, "region") and float(c["cfg"].get("float_piece_m2", terrain_mesh.FLOAT_PIECE)) > 0:
            clr = P[:, 2] - field.region.height(P[:, 0], P[:, 1])
        faces, dropped = _drop_specks(P, faces, vrow >= 0, float(c["cfg"].get("min_piece_m2", 4.0)), clr,
                                      float(c["cfg"].get("float_piece_m2", terrain_mesh.FLOAT_PIECE)))
        np.savez(_work(c, "dense", *ij), P=P, faces=faces, vrow=vrow)
    # the area its maps will cover (a cliff shell's visible front only): the export's texel density is chosen from it
    area = 0.0
    if len(faces):
        a = np.linalg.norm(np.cross(P[faces[:, 1]] - P[faces[:, 0]], P[faces[:, 2]] - P[faces[:, 0]]), axis=1) / 2
        if hasattr(field, "front"):
            with _span("dense/visible area"):
                a = a[np.abs(_chunks(field.front, P[faces].mean(1))) <= 0.3]
        area = float(a.sum())
    return True, area, dropped


def _chunks(fn, X, n=200_000):
    return np.concatenate([fn(X[i:i + n]) for i in range(0, len(X), n)]) if len(X) else np.zeros(0)


def _drop_specks(P, F, on_border, min_area, clearance=None, float_area=0.0, tol=terrain_mesh.FLOAT_TOL):
    """Closed pieces of a tile's mesh smaller than `min_area` m2 that touch no tile border: bubbles where the field
    grazes zero just off a steep face (rock relief on a 60 deg wall: 14-triangle specks floating 15 m up).
    With `clearance` (each vertex's height over the pushed heightmap: a cliff shell), closed pieces off the border
    under `float_area` m2 that never come down to the ground (the seam check's `floating` rule) go too: style or
    rock relief building out over a sheer lip and cut off. Returns (faces, dropped: [{at, triangles, m2,
    clearance_m}]): the export logs them. Bigger floating pieces stay and fail the check (a stack's head)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    n = len(P)
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]]])
    nc, lab = connected_components(coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n)), directed=False)
    if nc == 1:
        return F, []
    area = np.linalg.norm(np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]]), axis=1) / 2
    ca = np.bincount(lab[F[:, 0]], area, minlength=nc)
    border = np.zeros(nc, bool)
    border[lab[on_border]] = True
    small = (ca < min_area) & ~border
    dropped = []
    if clearance is not None and float_area > 0:
        used = np.zeros(n, bool)
        used[F.ravel()] = True
        low = np.full(nc, np.inf)
        np.minimum.at(low, lab[used], clearance[used])
        fl = (low > tol) & (ca < float_area) & ~border & ~small
        tri = np.bincount(lab[F[:, 0]], minlength=nc)
        for c_ in np.flatnonzero(fl):
            dropped.append({"at": P[lab == c_].mean(0).round(1).tolist(), "triangles": int(tri[c_]),
                            "m2": round(float(ca[c_]), 1), "clearance_m": round(float(low[c_]), 1)})
        small |= fl
    return (F[~small[lab[F[:, 0]]]] if small.any() else F), dropped


def _job_collapse(args):
    ij, keep_rows, k = args
    P, faces, vrow = _dense(terrain_mesh._CTX, ij)
    drop = np.flatnonzero((vrow >= 0) & ~np.isin(vrow, keep_rows))
    with _span("collapse border"):
        Fk, bad = _collapse_border(P, faces, drop)
    np.save(_work(terrain_mesh._CTX, "col", ij[0], ij[1], k), Fk)
    return {int(vrow[u]) for u in bad}


def _job_dense_full(ij):
    """A tile's dense LOD0 (`_job_dense`), its marching cubes first when the last export made them (incremental: the
    border keys came from the state). Those must come out as stored: a difference would break the invariant."""
    c = terrain_mesh._CTX
    if not _work(c, "mc", *ij).exists():
        r = _job_mc(ij)
        want = c["mc"][ij]
        if r is None or r[0] != want[0] or r[1] != want[1] or r[2] != want[2]:
            raise RuntimeError(f"tile {ij[0]},{ij[1]}: marching cubes made again differ from the stored ones")
    return _job_dense(ij)


def _job_prep_tile(ij):
    """The work files a tile's LODs read when the last export made its dense mesh and collapses: made again, with
    this export's kept vertices."""
    c = terrain_mesh._CTX
    if not _work(c, "dense", *ij).exists():
        _job_dense_full(ij)
    for k, kr in enumerate(c["keep"]):  # (the same sorted rows the collapse loop passed)
        _job_collapse((ij, kr, k))


def build_field(T, cfg=None):
    """The 3D field of a terrain: (field, volume pieces, notes, caves)."""
    from . import terrain_caves_build
    cfg = {**terrain_mesh.DEFAULTS, **((T.spec.get("export") or {}).get("tiles") or {}), **(cfg or {})}
    vols, notes = volumes(T)
    if cfg.get("stacks", True) and _sea(T) is not None:
        sv, sn = stacks(T)
        vols = vols + sv
        if sn:
            notes = notes + [sn]
    rock = rock_config(T, cfg)
    caves = terrain_caves_build.build(T, rock)
    for cv in caves:
        vols = vols + cv.tubes
        notes = notes + cv.notes
    from . import terrain_design_cover
    bunkers = []
    for name in getattr(T, "cover", {}):
        c = terrain_design_cover._spec_cover(T, name)
        if c.get("type", name) == "bunker":
            bunkers.append((T.cover[name], float(c.get("depth", 0.6)), name))
            notes = notes + [f"{name}: bunkers dug {float(c.get('depth', 0.6)):g} m in, over "
                             f"{float((T.cover[name] > 0.5).sum()) * T.cell ** 2:.0f} m2"]
    field = Field(T, vols, rock, dolines=[d for cv in caves for d in cv.dolines],
                  cuts=[v.cut for v in vols if getattr(v, "cut", None)], bunkers=bunkers)
    for v in vols:
        if getattr(v, "kind", None) == "arch":
            v.view = through_view(field, v)
            notes.append(v.view["note"])
    return field, vols, notes, caves


def _swatch(out, rock, macro_density=8.0, source="procedural"):
    """terrain_swatch.write(out, rock, "rock"), or what the last export wrote when the swatch's inputs (the rock's seed,
    the swatch's code) and its files are the same."""
    import pickle
    from . import codehash, terrain_swatch
    from . import terrain_incremental as inc
    key = inc._h(codehash.digest("terrain_swatch"), int((rock or {}).get("seed", 4242)), terrain_swatch.SIZE,
                 terrain_swatch.RES, float(macro_density), str(source))
    p = out / "_incremental" / "swatch.pkl"
    files = lambda de: sorted(v for v in de.values() if isinstance(v, str) and v.startswith("materials/"))
    try:
        k, de, fk = pickle.loads(p.read_bytes())
        if k == key and inc.files_key(out, files(de)) == fk:
            return de
    except Exception:
        pass
    de = terrain_swatch.write(out, rock, "rock", macro_density=float(macro_density), source=source)
    p.parent.mkdir(exist_ok=True)
    p.write_bytes(pickle.dumps((key, de, inc.files_key(out, files(de)))))
    return dict(de)


def _fingerprint(T, cfg, base, field, mats, region, G, hrange):
    """What every tile's outputs read (terrain_incremental.Fingerprint): the export's field, materials, cliff region
    and detail projection, the terrain's cover grids and the settings; per tile windows of the grids."""
    from . import codehash
    from .terrain_incremental import Fingerprint, Frame
    frames = [Frame("terrain", T.H.shape, "yx", T.xs[0], T.ys[0], T.cell)]
    if region is not None:  # (the cliff region's heightmap lattice [ix, iy], nodes and cells)
        frames += [Frame("region", (region.nx, region.ny), "xy", G.origin[0], G.origin[1], region.d),
                   Frame("region cells", (region.nx - 1, region.ny - 1), "xy", G.origin[0], G.origin[1], region.d)]
    roots = {"field": field, "base": base, "materials": mats, "terrain cover": dict(T.cover),
             "terrain frame": (float(T.xs[0]), float(T.ys[0]), float(T.cell), tuple(T.H.shape)),
             "region": region, "detail": terrain_mesh._CTX.get("detail"), "detail entry": terrain_mesh._CTX.get("detail_entry"),
             "config": {k: v for k, v in cfg.items() if k not in ("incremental", "corridors")}, "heights range": hrange,
             "grid": G, "sea": _sea(T), "code": codehash.digest(*terrain_mesh.MODULES)}
    return Fingerprint(roots, frames, base.vols, float(cfg["cave_wall"]) + 3.0)


class TilesCheckFailed(RuntimeError):
    """The export's checks failed AFTER everything was written. `result` is what export_tiles would have returned
    (out, manifest, stats, timing, check): the files and manifest.json are on disk and complete; `summary(result)`
    is the report with the failures on top."""

    def __init__(self, msg, result):
        super().__init__(msg)
        self.result = result


def budget_check(manifest_tiles, cfg, lods, caves=()):
    """Tile LODs over OVER_BUDGET x their triangle budget, with what the numbers say about why. `caves`: the caves'
    names (a tile a cave passes under is heavy for a reason the designer can act on)."""
    over = []
    for e in manifest_tiles:
        for k, L in enumerate(e["lods"]):
            if not L or k >= lods:
                continue
            b = cfg["budget"][min(k, len(cfg["budget"]) - 1)]
            if L["triangles"] <= terrain_mesh.OVER_BUDGET * b:
                continue
            mc = L.get("marching_cubes_triangles") or 0
            if mc and L["triangles"] > 0.9 * mc:
                why = ("decimation removed nothing (every simplification folded the mesh or opened it: rock or shell "
                       "thinner than the voxel)")
            else:
                why = "decimation stalled above it (folds in thin rock, or its border chain alone is this long)"
            here = [v for v in e.get("volumes", []) if v in set(caves)]
            if here:
                # (the island's 16,25: crown_tube's graded switchbacks run under it; the rock kept round the passage
                # (cave_wall) and the shell's back lie close together inside the rock, and pyfqmr folds them at every
                # count below LOD 1's mesh. Measured on the export: a valid mesh, only heavy)
                why = (f"the cave {', '.join(here)} runs under this tile: the rock kept round its passage and the "
                       f"shell's back lie close inside the rock and decimation folds them below this count. The mesh "
                       f"is valid, only heavy; to lighten it, route the passage under the middle of a tile or deeper "
                       f"(fewer crossings of tile borders, more rock between it and the ground)")
            over.append({"tile": [e["i"], e["j"]], "lod": k, "triangles": L["triangles"], "budget": int(b),
                         "visible_triangles": L.get("visible_triangles"), "marching_cubes_triangles": mc,
                         "volumes": e.get("volumes", []), "why": why})
    return over
