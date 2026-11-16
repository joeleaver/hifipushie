"""export_tiles: the terrain exported as tiles with LODs, maps and collision, and its summary. `_export_tiles` is the
context (TileExport, made from its arguments) and eleven stages called in order: _setup and _keys here, the tiles'
meshes in terrain_tiles_build, what lies on them in terrain_tiles_ground, the manifest and the checks in
terrain_tiles_manifest. Part of the terrain mesh (terrain_mesh.py has the overview)."""
from __future__ import annotations

import os
import time
from pathlib import Path

import numpy as np

from . import terrain_mesh
from . import profiling
from .terrain_materials import Materials
from .terrain_tile_jobs import _fingerprint, _swatch, build_field
from .terrain_tile_mesh import Grid
from .terrain_tiles_build import _border_chains, _cubes, _dense_meshes, _tile_lods
from .terrain_tiles_ground import _clutter, _ground_maps, _trees
from .terrain_tiles_manifest import _finish, _manifest

def export_tiles(T, out_dir, cfg: dict | None = None, log=print) -> dict:
    """See `_export_tiles`; holds the machine's heavy-job slot (`resources.heavy`) so exports don't stack up."""
    from . import resources
    from . import resources_guard
    # (PSS every 2 s: reading every worker's smaps_rollup each 0.5 s kept a parent thread ~40% busy)
    name = (cfg or {}).get("name") or Path(str(out_dir)).name
    with resources.heavy(f"terrain tiles {name}", log=log, kind="terrain_tiles", model=name,
                         gb=(cfg or {}).get("heavy_gb")), resources_guard.peak_memory(every=2.0) as peak:
        return _export_tiles(T, out_dir, cfg, log, peak)


class TileExport:
    """What one export carries from stage to stage: the arguments of `_export_tiles`, then what each stage sets for
    the ones after it. A stage reads and writes it as `tx.<name>`; what a stage only uses itself is a local there.
    _setup sets:
      copy, t_all, out, shutil, workdir, timing, prof, tile_key, t0, field, vols, notes, caves, base, mats, G, region,
      terrain_cliffs, tiles
    _keys sets:
      inc, hrange, fp, fkey, prev_state, why_cold, old, ns, redone
    _cubes sets:
      v0, mc, reg, fixed, CP, CN, CW, CC, pos
    _border_chains sets:
      alias, lines, keep
    _dense_meshes sets:
      work, rows_of, dkey, dropped_pieces, dense, dirn, thick, mat, rounds, tile_state, rpos_of, tile_wanted,
      col_known, col_used, col_file, col_all, first
    _tile_lods sets:
      need, manifest_tiles, stats, t_dec
    _ground_maps sets:
      hm, sp, ground
    _clutter sets:
      clutter_sec
    _trees sets:
      groups, layer_tex, style_sec, detail
    _manifest sets:
      manifest, over
    """

    def __init__(self, **arguments):
        self.__dict__.update(arguments)


def _export_tiles(T, out_dir, cfg: dict | None = None, log=print, peak=None) -> dict:
    """Mesh the terrain's field (heightfield + volumes) into seamless tiles; write GLBs per tile per LOD, collision
    GLBs, heightmap and splat tiles, trees.csv and manifest.json; run the seam check (raises if it fails)."""
    tx = TileExport(T=T, out_dir=out_dir, cfg=cfg, log=log, peak=peak)
    _setup(tx)
    _keys(tx)
    _cubes(tx)
    _border_chains(tx)
    _dense_meshes(tx)
    _tile_lods(tx)
    _ground_maps(tx)
    _clutter(tx)
    _trees(tx)
    _manifest(tx)
    return _finish(tx)


def _setup(tx):
    """The settings, the out and work dirs, the field and its materials, the grid, which tiles are exported."""
    from PIL import Image
    import copy
    tx.copy = copy
    tx.t_all = time.time()
    tx.cfg = {**terrain_mesh.DEFAULTS, **((tx.T.spec.get("export") or {}).get("tiles") or {}), **(tx.cfg or {})}
    tx.out = Path(tx.out_dir)
    tx.out.mkdir(parents=True, exist_ok=True)
    import shutil
    tx.shutil = shutil
    tx.workdir = tx.out / "_work"  # per-tile dense meshes, streamed through disk; removed at the end
    tx.shutil.rmtree(tx.workdir, ignore_errors=True)
    tx.workdir.mkdir()
    terrain_mesh._CTX.clear()
    terrain_mesh._CTX["work"] = tx.workdir
    tx.timing = {}
    tx.prof = profiling.Report(progress=tx.log)  # per stage: wall, workers' busy share, stragglers; spans, field counts (manifest "profile")
    tx.tile_key = lambda ij: f"{ij[0]},{ij[1]}"
    tx.t0 = time.time()
    _st = tx.prof.stage("setup (parent)")
    _st.__enter__()
    tx.field, tx.vols, tx.notes, tx.caves = build_field(tx.T, tx.cfg)
    tx.base = tx.field  # the whole rock (materials, trees, caves' walk, splats); `field` is what's meshed
    tx.mats = Materials(tx.T, tx.base)
    tx.G = Grid(tx.T, tx.cfg)
    if tx.cfg.get("detail") and tx.base.rock is not None:  # (the tiling detail's projection, read by the workers)
        from . import terrain_swatch
        from . import terrain_swatch_detail
        terrain_mesh._CTX["detail"] = terrain_swatch_detail.DetailProjection(tx.base, tx.base.rock)
        de = _swatch(tx.out, tx.base.rock, tx.cfg["texel_density"][0], tx.cfg["detail_source"])  # (cached by seed + code)
        de.update(texcoord=1 + bool(int(tx.cfg["splat"])), bins=terrain_mesh._CTX["detail"].BINS, line_d=terrain_swatch.LINE_D,
                  layers=[nm for nm in ("rock", "wet_rock") if nm in tx.mats.layers], recipe=terrain_swatch.RECIPE,
                  gltf=("each cliff tile LOD's baked material carries extras.hifipushie_detail: texture indices of "
                        "the embedded lines map and of the swatch images (files in materials/, by uri), and the UV "
                        "set; glTF viewers ignore it and show the macro maps"))
        terrain_mesh._CTX["detail_entry"] = de
        # (the drawn lines go to the lines map, crisp, instead of blurring into the macro colour)
        tx.mats.lines_in_maps = bool(tx.cfg.get("lines", True))
    tx.region = None
    if tx.cfg["mode"] == "cliffs":
        from . import terrain_cliffs
        tx.terrain_cliffs = terrain_cliffs
        from . import terrain_cliffs_checks, terrain_cliffs_ground
        tx.region = tx.terrain_cliffs.Region(tx.T, tx.base, tx.G, tx.cfg)
        tx.field = tx.terrain_cliffs.CliffField(tx.base, tx.region)
    elif tx.cfg["mode"] != "full":
        raise ValueError(f"export.tiles mode {tx.cfg['mode']!r}: use cliffs or full")
    _st.__exit__(None, None, None)
    tx.timing["setup"] = time.time() - tx.t0
    tx.tiles = [(i, j) for j in range(tx.G.nj) for i in range(tx.G.ni)]
    if tx.cfg.get("only"):  # a block of tiles [[i0, j0], [i1, j1]] (inclusive), for trying things
        (i0, j0), (i1, j1) = tx.cfg["only"]
        tx.tiles = [(i, j) for (i, j) in tx.tiles if i0 <= i <= i1 and j0 <= j <= j1]
    tx.log(f"{len(tx.tiles)} tiles ({tx.G.ni} x {tx.G.nj}) of {tx.G.tile:g} m, voxel {tx.G.voxel:g} m, LOD errors "
        f"{tx.cfg['error'][:tx.G.lods]} m, {len(tx.vols)} volume pieces")


def _keys(tx):
    """Incremental: each tile's inputs keyed; the previous export's state where it still applies."""

    # ---- 0. incremental: each tile's inputs keyed (terrain_incremental); the previous export's state if it applies
    from . import terrain_incremental as inc
    tx.inc = inc
    tx.t0 = time.time()
    with tx.prof.stage("incremental keys (parent)"):
        tx.hrange = [float(np.nanmin(tx.T.H)), float(np.nanmax(tx.T.H))]
        tx.fp = _fingerprint(tx.T, tx.cfg, tx.base, tx.field, tx.mats, tx.region, tx.G, tx.hrange)
        tx.fkey = {ij: tx.fp.tile(*tx.G.bounds(*ij)) for ij in tx.tiles}
        tx.prev_state, tx.why_cold = None, "incremental off (export.tiles incremental false or HIFIPUSHIE_TILES_COLD)"
        if tx.fp.unknown:
            tx.why_cold = f"inputs it can't fingerprint: {tx.fp.unknown[:3]}"
            (tx.out / tx.inc.STATE).unlink(missing_ok=True)
        elif tx.cfg.get("incremental", True) and not os.environ.get("HIFIPUSHIE_TILES_COLD"):
            tx.prev_state, tx.why_cold = tx.inc.load(tx.out, tx.fp.parts["code"], tx.fp.global_key, tx.fp.parts)
        else:
            (tx.out / tx.inc.STATE).unlink(missing_ok=True)
    tx.old = tx.prev_state["tiles"] if tx.prev_state else {}
    tx.ns = {ij: {"field": tx.fkey[ij][0], "parts": tx.fkey[ij][1]} for ij in tx.tiles}  # (the state this export leaves)
    tx.redone = {}
    if tx.prev_state is None:
        tx.log(f"cold export: {tx.why_cold}")
        for f in tx.out.glob("*.glb"):
            f.unlink()
    tx.timing["incremental keys"] = time.time() - tx.t0


def preview_tiles(T, out_dir, at, radius=40.0, density=6.0, cfg=None, log=print) -> dict:
    """A fast look at the rock round `at` (an address or [x, y]): only the tiles within `radius` m, one LOD, maps at
    `density` texels/m, ground maps at half their density, no checks. The same code path as the export (so what it
    shows is what an export bakes), sized for rock design rounds: a tile or four in about a minute instead of a block
    export's 15+. Render it with `render_tiles(T, out_dir, views)`."""
    base = {**terrain_mesh.DEFAULTS, **((T.spec.get("export") or {}).get("tiles") or {}), **(cfg or {})}
    G = Grid(T, base)
    xy = np.asarray(at, float)[:2] if isinstance(at, (list, tuple)) else np.asarray(T.address(at)[0], float)
    lo = np.floor((xy - radius - G.origin) / G.tile).astype(int).clip(0, [G.ni - 1, G.nj - 1])
    hi = np.floor((xy + radius - G.origin) / G.tile).astype(int).clip(0, [G.ni - 1, G.nj - 1])
    c = {"only": [lo.tolist(), hi.tolist()], "lods": 1, "texel_density": [float(density)], "checks": False,
         "ground_density": 0.5 * float(base["ground_density"])}
    return export_tiles(T, out_dir, {**c, **(cfg or {})}, log)


def summary(r) -> str:
    """A short text report of an export_tiles result."""
    M = r["manifest"]
    what = "cliff mesh tiles" if M.get("mode") == "cliffs" else "3D tiles"
    lines = []
    fails = (r.get("check") or {}).get("failures") or []
    if fails:
        lines += [f"CHECKS FAILED ({len(fails)}). The export is COMPLETE on disk (every tile and manifest.json, whose "
                  "seam_check.failed repeats this list) and loads in an engine. Each failure names its tiles. Open "
                  "edges or shards in a \"buried\" primitive are under the heightmap (not seen); in \"surface\" they "
                  "show (black slivers, holes). A tile over its budget is a valid mesh, only heavy."]
        lines += [f"  FAILED: {f}" for f in fails[:30]]
        if len(fails) > 30:
            lines.append(f"  ... and {len(fails) - 30} more")
    lines += [f"{what} in {r['out']}: {M['grid'][0]} x {M['grid'][1]} tiles of {M['tile_size']:g} m"
              + (f", {len(M['tiles'])} with cliffs" if M.get("mode") == "cliffs" else "")]
    for k, L in enumerate(M["lods"]):
        tris = [t["lods"][k]["triangles"] for t in M["tiles"] if t["lods"][k]]
        size = sum(t["lods"][k]["bytes"] for t in M["tiles"] if t["lods"][k])
        if tris:
            lines.append(f"LOD {k} (error {L['error_m']:g} m): {sum(tris)} triangles, per tile {min(tris)}-{max(tris)} "
                         f"(median {int(np.median(tris))}), {size / 1e6:.1f} MB")
    if M.get("ground"):
        for k in range(len(M["ground"][0]["lods"])):
            tris = [g["lods"][k]["triangles"] for g in M["ground"]]
            size = sum(g["lods"][k]["bytes"] for g in M["ground"])
            lines.append(f"ground LOD {k}: {sum(tris)} triangles ({min(tris)}-{max(tris)} a tile), {size / 1e6:.1f} MB")
        c = M["cliffs"]
        lines.append(f"heightmap pushed {c['heightmap'].split(' m ')[0].split()[-1]} m under the cliffs; "
                     f"{c['hole_cells']} hole cells")
    lines += [f"volume {n}" for n in M["volumes"]]
    lines += [f"walk: {n}" for n in M.get("caves", [])]
    sc = M["seam_check"]
    if "shared_edges" in sc:
        lines.append(f"seam check: {sc['failures']} failures; shared edges {sc['shared_edges']}, border normals within "
                     f"{sc['border_normal_max_deg']} deg, LOD gaps up to {sc['lod_pairs_max_gap_m']} m all under "
                     f"skirts")
    else:
        lines.append(f"seam check: {sc['failures']} failures")
    if "ground" in sc:
        lines.append("ground check: " + ", ".join(f"{k} {v}" for k, v in sc["ground"].items()))
    if "grid_squares" in sc:
        if "facet_periodicity" in sc:
            lines.append(f"facet periodicity (autocorrelation peak per plane orientation): {sc['facet_periodicity']}")
        lines.append(f"grid squares (colour kinks on cell lines vs between): x{sc['grid_squares']['ratio']}; texel "
                     "density " + ", ".join(f"{k} {v['min']:g}-{v['max']:g}/m (neighbours x{v['worst_neighbour_ratio']})"
                                            for k, v in sc.get("texel_density", {}).items()))
    sh = [f"LOD {k} {sc[f'lod{k}_shards']['area_pct']}%" for k in range(len(M["lods"])) if f"lod{k}_shards" in sc]
    if sh:
        lines.append("shards (corner normals against their face, share of the area): " + ", ".join(sh))
    inc_ = (M.get("profile") or {}).get("incremental")
    if inc_:  # (always said: cold and why, or what was redone)
        rd = inc_.get("redone") or {}
        lines.append(("incremental: reused the previous export; redone " + ", ".join(f"{k} {v}" for k, v in rd.items())
                      + f" of {inc_.get('tiles')} tiles") if inc_.get("previous export used") else
                     f"incremental: cold export ({inc_.get('why not') or 'no previous export'})")
    lines.append("timing (s): " + ", ".join(f"{k} {v}" for k, v in M["timing_s"].items()))
    if M.get("memory_gb"):
        m = M["memory_gb"]
        lines.append(f"memory peak: {m['job_gb']} GB for the job (largest worker {m['worker_gb']} GB, parent "
                     f"{m['parent_gb']} GB); the machine's free memory never below {m['min_available_gb']} GB")
    return "\n".join(lines)
