"""Terrain tools: a height field in a level designer's words, its checks, looks, export and history."""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
from mcp.server.mcpserver import Context
from PIL import Image as PILImage

from .mcp_app import mcp
from .tool_common import _out, _spec_arg

# ---------------------------------------------------------------- terrain
@mcp.tool(structured_output=False)
def set_terrain(name: str, spec: dict | None = None, patch: dict | None = None, note: str = "") -> str:
    """Create (spec) or change (patch, merged; null deletes) a terrain in a level designer's words; builds it and
    returns the report, or questions for the designer as JSON (relay them, don't answer them). Details:
    guide(topic="set_terrain")."""
    from . import terrain_tools as tt
    if spec is None and patch is None:
        raise ValueError("give spec (the whole spec) or patch (changes to merge into it)")
    if spec is not None:
        new = _spec_arg(spec)
    else:
        try:
            base = tt.load(name)
        except ValueError:
            base = {}
        new = tt.merge(base, _spec_arg(patch))
    if "extent" not in new:
        raise ValueError('a terrain needs "extent": [[x0, y0], [x1, y1]] (see guide(topic="terrain"))')
    from . import terrain
    terrain.normalise(new)  # cheap checks (units, named sections) before saving
    if new.get("styles"):
        from . import terrain_style
        terrain_style.resolve(new)  # (style names, keys, sheet overrides: zones are checked when the styles are written)
    prev = tt.load(name) if (tt._dir(name) / "spec.json").exists() else None
    if prev is not None and prev == new:  # (an empty or no-op patch made a new version each time)
        return f"terrain {name}: nothing changed (still v{len(tt.history(name))})\n" + tt.report(name)
    v = tt.save(name, new, note or ("set_terrain" if spec is not None else "patch"))
    try:
        rep = tt.report(name)
    except Exception:  # a spec that doesn't build isn't kept: the version and spec.json go back as they were
        tt.unsave(name, v, prev)
        raise
    return f"saved terrain {name} v{v}\n" + rep


@mcp.tool(structured_output=False)
def check_terrain(name: str) -> str:
    """The terrain's report measured on the built ground (kind, peaks, rivers, basins, walls, passes, sites, routes,
    cover, intent checks, WARNINGS); questions come back as JSON. Details: guide(topic="check_terrain")."""
    from . import terrain_tools as tt
    return tt.report(name)


@mcp.tool(structured_output=False)
def look_terrain(name: str, map: bool = True, masks: bool = False, views: list[dict] | None = None,
                 spec_views: bool = False, size: int = 1100, tiles: bool = False, haze: float | None = 5000.0,
                 light: str | None = None, styles: bool = False):
    """Terrain images: map (hillshade + annotations), masks, perspective views [{name, eye, lift, look, fov, sun}] or
    spec_views, tiles (render the exported tiles), haze, light, styles (swatch sheet), size. Details:
    guide(topic="look_terrain")."""
    from . import terrain_tools as tt
    from . import terrain_views
    from .terrain_world import Questions
    try:
        T = tt.build(name)
    except Questions as q:
        return tt.questions_data(q)
    d = tt._dir(name)
    ver = len(tt.history(name))  # files carry the version they show (a later look doesn't overwrite them)
    out, notes = [], []
    if map:
        im = terrain_views.map_image(T, px=size)
        out.append(_out(im, str(d / f"map_v{ver}.png")))
        notes.append(f"map: {d / f'map_v{ver}.png'}")
    if masks:
        sheet = terrain_views.mask_sheet(T)
        if sheet is None:
            notes.append("no cover layers, so no masks")
        else:
            out.append(_out(sheet, str(d / f"masks_v{ver}.png")))
            notes.append(f"masks: {d / f'masks_v{ver}.png'}")
    if styles:
        from . import terrain_style
        from . import terrain_style_files, terrain_style_looks
        sts = terrain_style.resolve(T.spec)
        sheets = [s["sheet"] for s in sts] + ([] if any(s["name"] == "realistic" for s in sts)
                                              else [terrain_style.sheet("realistic")])
        refs = terrain_style_files.refs_of(T)
        lays = [nm for nm in ("grass", "rock", "sand") if nm in refs]
        p = terrain_style_looks.swatch_sheet(sheets, refs, lays, d / f"styles_v{ver}.png")
        out.append(_out(PILImage.open(p), None))
        notes.append(f"styles sheet: {p}")
        p = terrain_style_looks.season_sheet(sheets, refs, lays, d / f"styles_seasons_v{ver}.png")
        out.append(_out(PILImage.open(p), None))
        notes.append(f"seasons sheet (spring, summer, autumn, winter, snow by the snow numbers): {p}")
        gl = [nm for nm in ("grass", "earth") if nm in refs]
        p = terrain_style_looks.ground_view(sheets, refs, d / f"styles_ground_v{ver}.png", layers=tuple(gl))
        out.append(_out(PILImage.open(p), None))
        notes.append(f"ground as the game shows it (flat cel light, mipmaps, anti-tiling, layer edges; eye level and "
                     f"25 m up): {p}")
        for nm in lays:
            q = terrain_style_looks.transition_strip(sheets, refs, nm, d / f"styles_strip_{nm}_v{ver}.png")
            out.append(_out(PILImage.open(q), None))
            notes.append(f"transition ({nm}, {' -> '.join(st['name'] for st in sheets)}): {q}")
    vs = list(views or []) + (list(T.spec.get("views") or []) if spec_views else [])
    if vs:
        for i, v in enumerate(vs):
            v.setdefault("name", f"view{i + 1}")
            if not re.fullmatch(r"[A-Za-z0-9_\-]+", v["name"]):
                raise ValueError(f"view name {v['name']!r}: letters, digits, _ and - only")
        for v in vs:
            v["name"] = f"{v['name']}_v{ver}"
        if tiles:
            from . import terrain_tile_views
            td = d / "tiles"
            if not (td / "manifest.json").exists():
                raise ValueError(f"no tiles for {name!r}: run export_terrain({name!r}, tiles=True) first")
            for v in vs:
                v["out"] = str(d / "views" / f"{v['name']}_tiles.png")
                if isinstance(v.get("eye"), list) and len(v["eye"]) == 2:
                    v["eye"] = [*v["eye"], float(T.height(np.array(v["eye"], float))) + v.get("lift", 1.7)]
                v.setdefault("look", v["eye"])
            (d / "views").mkdir(parents=True, exist_ok=True)
            for pth in terrain_tile_views.render_tiles(T, td, vs, haze=haze, light=light,
                                                 textured="styles" if styles else True):
                out.append(_out(PILImage.open(pth), None))
                notes.append(f"view: {pth}")
            notes += json.loads((td / "render_job.json").read_text()).get("notes", [])
            return out + ["\n".join(notes)]
        for pth in terrain_views.render(T, d / "views", vs):
            out.append(_out(PILImage.open(pth), None))
            notes.append(f"view: {pth}")
        notes += T.view_notes
    return out + ["\n".join(notes)]


def _progress_log(ctx, path: Path):
    """A log for a long job run by a tool: each line appended to `path` (tail it while it runs) and sent to the client
    as an MCP progress notification (when the call carries a progress token; never fails the job)."""
    import re
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")
    n = [0]

    def log(*a):
        line = " ".join(str(x) for x in a)
        with open(path, "a") as f:
            f.write(line + "\n")
        if ctx is None:
            return
        n[0] += 1
        m = re.search(r"(\d+) / (\d+) done", line)
        try:
            import anyio.from_thread
            first = line.splitlines()[0][:300] if line else ""
            if m:
                anyio.from_thread.run(ctx.report_progress, float(m.group(1)), float(m.group(2)), first)
            else:
                anyio.from_thread.run(ctx.report_progress, float(n[0]), None, first)
        except Exception:
            pass
    return log


@mcp.tool(structured_output=False)
def export_terrain(name: str, size: int | None = None, engine: str | None = None, out_dir: str | None = None,
                   tiles: bool = False, styles_only: bool = False, ctx: Context | None = None) -> str:
    """Write the terrain for an engine: heightmaps, masks, splat weights, trees.csv, meta.json (size, engine
    "unity"/..., out_dir); tiles=True writes seamless glTF mesh tiles with LODs and a manifest instead; styles_only
    writes only the style textures. Details: guide(topic="export_terrain")."""
    from . import terrain_tools as tt
    from .terrain_world import Questions
    try:
        T = tt.build(name)
    except Questions as q:
        return tt.questions_data(q)
    cfg = T.spec.get("export") or {}
    if styles_only:
        from . import terrain_style_files
        out = Path(out_dir).expanduser() if out_dir else tt._dir(name) / "tiles"
        sec = terrain_style_files.export_styles(T, out)
        return f"styles written to {out} (styles.json + manifest.json's \"styles\" if it exists)\n" + \
            terrain_style_files.summary(sec)
    if tiles:
        from . import terrain_tile_jobs, terrain_tiles
        out = Path(out_dir).expanduser() if out_dir else tt._dir(name) / "tiles"
        try:
            r = terrain_tiles.export_tiles(T, out, log=_progress_log(ctx, out / "export_log.txt"))
        except terrain_tile_jobs.TilesCheckFailed as e:
            # (the export is written and complete: the report, with what failed on top, not a traceback)
            r = e.result
        return terrain_tiles.summary(r)
    path = T.export(Path(out_dir).expanduser() if out_dir else tt._dir(name) / "export",
                    size=size or cfg.get("size"), engine=engine or cfg.get("engine"))
    meta = json.loads((path / "meta.json").read_text())
    files = sorted(str(p.relative_to(path)) for p in path.rglob("*") if p.is_file())
    return (f"exported {name} to {path}: {meta['size'][0]} x {meta['size'][1]}, heights {meta['height_range'][0]:.1f} "
            f"to {meta['height_range'][1]:.1f} m; Unity terrain size {[round(v, 1) for v in meta['unity']['terrain_size']]} "
            f"at {[round(v, 1) for v in meta['unity']['position']]}\nfiles: " + ", ".join(files))


@mcp.tool(structured_output=False)
def terrain_history(name: str, revert_to: int | None = None) -> str:
    """List a terrain's versions or restore one (revert_to; saved as new). name "" lists terrains. Details:
    guide(topic="terrain_history")."""
    from . import terrain_tools as tt
    if not name:
        return json.dumps(tt.list_terrains())
    if revert_to is not None:
        v = tt.save(name, tt.version_spec(name, revert_to), f"revert to v{revert_to}")
        return f"terrain {name} v{v} = v{revert_to}\n" + tt.report(name)
    return "\n".join(f"v{h['version']}  {h['time']}  {h['note']}" for h in tt.history(name))
