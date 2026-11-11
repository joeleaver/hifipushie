"""Plant tools: grow, edit and look at a plant, its form and references, export, wind, stands of plants."""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image as PILImage

from .mcp_app import mcp
from .tool_common import _out, _spec_arg

# ---------------------------------------------------------------- vegetation
@mcp.tool(structured_output=False)
def grow_plant(name: str, spec: dict | None = None, patch: dict | None = None, note: str = "",
               copy_from: str | None = None) -> str:
    """Create (spec) or change (patch, merged; lists replace whole) a plant in botanical words (species, age, seed,
    height, habit, environment, guides, prune, leaves, bark, season, style) and grow it; returns the report.
    copy_from starts from another plant. name only: the stored report; "" lists plants and species. Details:
    guide(topic="grow_plant")."""
    from . import veg_tools as vt
    from . import vegetation
    if not name:
        return json.dumps({"plants": vt.list_plants(), "species": {k: vegetation.preset(k).get("about", "") for k in vegetation.species()}}, indent=1)
    if spec is None and patch is None and not copy_from:
        return vt.report(name)
    exists = (vt._dir(name) / "plant.json").exists()
    prev = vt.load(name) if exists else None
    stats = vt.grown(name)["stats"] if exists else None
    if copy_from:
        base = vt.load(copy_from)
        new = vt.merge(base, _spec_arg(patch)) if patch is not None else base
    else:
        new = _spec_arg(spec) if spec is not None else vt.merge(prev or {}, _spec_arg(patch))
    if prev is not None and prev == new:
        return f"plant {name}: nothing changed (still v{len(vt.history(name))})\n" + vt.report(name)
    v = vt.save(name, new, note=note or (f"copy of {copy_from}" if copy_from else "grow_plant" if spec is not None else "patch"))
    ch = vt.change_note(name, prev if not copy_from else vt.load(copy_from), stats)
    return f"saved plant {name} v{v}" + (f" (a copy of {copy_from})" if copy_from else "") + "\n" + (ch + "\n" if ch else "") + vt.report(name)


@mcp.tool(structured_output=False)
def edit_plant(name: str, ops: list[dict], note: str = "") -> str:
    """Direct the plant like an artist; it regrows around each edit. ops: guide / remove_guide / take_limb, prune /
    remove_prune / clear_prunes, cut (pollard, coppice), dead / clear_dead, envelope, force / clear_forces, set
    {path, value}. Details: guide(topic="edit_plant")."""
    from . import veg_tools as vt
    before, prev = vt.grown(name)["stats"], vt.load(name)
    v = vt.edit(name, ops, note)
    return f"plant {name} v{v}\n" + vt.change_note(name, prev, before) + "\n" + vt.report(name)


@mcp.tool(structured_output=False)
def look_plant(name: str, views: list | None = None, azimuth: float = 0.0, size: int = 640,
               foliage: str | None = None, sheet: bool = False, triangles: int | None = None):
    """Plant images (Blender, 5-40 s): views clay, bare, leaf, far, near, close, under, ground, or a camera; azimuth,
    size, foliage "cards"|"mesh", triangles (as exported), sheet=True (reference sheet). Details:
    guide(topic="look_plant")."""
    from . import veg_tools as vt
    got = vt.look(name, tuple(views or ("clay", "leaf", "far")), azimuth, size, foliage, sheet, triangles)
    out = [_out(PILImage.open(p), None) for _, p in got]
    rep = vt.report(name)
    T = vt.grown(name)
    if triangles and not T.get("clump") and not sheet:  # the budgeted plant's own cards against the ground
        g_, w_ = vt.ground_lines(T, triangles)
        rep += "\n" + "\n".join(g_ + w_)
    out.append(rep + "\n" + "\n".join(f"{k}: {p}" for k, p in got))
    return out


@mcp.tool(structured_output=False)
def look_plants(names: list[str], at: list | None = None, spacing: float | None = None, views: list | None = None,
                azimuth: float = 0.0, size: int = 640, foliage: str | None = None, triangles: int | None = None):
    """Several plants together in one picture: names (or "set#*"), at [[x,y]] or spacing, views, azimuth, size,
    foliage, triangles. Details: guide(topic="look_plants")."""
    from . import veg_tools as vt
    names = [m for n in names for m in (vt.set_names(n[:-2]) if n.endswith("#*") else [n])]
    got = vt.look_group(names, at, spacing, tuple(views or ("far",)), azimuth, size, foliage, triangles)
    out = [_out(PILImage.open(p), None) for _, p in got]
    out.append("\n".join(f"{k}: {p}" for k, p in got))
    return out


@mcp.tool(structured_output=False)
def grow_stand(name: str, spec: dict | None = None, patch: dict | None = None) -> str:
    """A forest stand: a few grown trees per species and role stood many times, with a floor. spec or patch (species,
    age, spacing, size, variants, edge, rows, clearings, paths, floor, lod, haze, light). Returns the forester's
    numbers. name only: the stored stand. Details: guide(topic="grow_stand")."""
    from . import veg_stand
    if spec is not None or patch:
        veg_stand.save(name, spec, patch)
    st = veg_stand.grow(veg_stand.load(name))
    return f"stand {name}\n" + veg_stand.report(st)


@mcp.tool(structured_output=False)
def look_stand(name: str, views: list | None = None, size: int = 720, max_full: int = 25):
    """Pictures of a stand (2-8 min): views inside, aisle, edge, above, canopy or a camera; size, max_full (trees at
    full detail). Details: guide(topic="look_stand")."""
    from . import veg_stand
    from . import veg_tools as vt
    st = veg_stand.grow(veg_stand.load(name))
    stem = str(veg_stand.home() / name / "look")
    r = veg_stand.look(st, tuple(views or ("inside",)), stem, size=size, max_full=max_full)
    out = [_out(PILImage.open(p), None) for _, p in r["files"]]
    out.append("\n".join(f"{k}: {p}" for k, p in r["files"]) + f"\ndrawn: {r['near']} trees at full detail, {r['mid']} mid, {r['far']} far "
               f"({r['meshed']} meshes, {r['triangles_instanced']} triangles instanced), floor {r['floor']}; mesh {r['mesh_s']} s, Blender {r['blender_s']} s\n"
               + veg_stand.report(st, [j["eye"] for j in veg_stand.view_jobs(st, tuple(views or ("inside",)))]))
    return out


@mcp.tool(structured_output=False)
def export_stand(name: str, out_dir: str | None = None, triangles: int | None = None, lods: int = 3, impostor: bool = True) -> str:
    """Export a stand as a forest kit: a GLB per variant (lods, impostor, wind, collision), floor meshes, layout.json.
    out_dir, triangles. Heavy job. Details: guide(topic="export_stand")."""
    from . import veg_stand
    st = veg_stand.grow(veg_stand.load(name))
    out = out_dir or str(veg_stand.home() / name / "export")
    c = veg_stand.export(st, out, triangles, lods, impostor)
    return (f"exported {len(c['variants'])} variants for {c['trees']} trees to {out}\n"
            + "\n".join(f"  {v['name']}: " + "; ".join(f"LOD{q['lod']} {q['triangles']}" for q in v["lods"]) for v in c["variants"])
            + "\nfiles: " + ", ".join(Path(f).name for f in c["files"]))


@mcp.tool(structured_output=False)
def plant_form(name: str = "", species: str = "", cases: list[dict] | None = None, fit: dict | None = None,
               iters: int = 30, seeds: int = 2) -> str:
    """A tree's form across ages and settings, measured as foresters do (height, crown ratio, dbh ...), cases with
    target bands; fit {habit path: [lo, hi]} searches for the least miss (iters, seeds) and saves. Details:
    guide(topic="plant_form")."""
    from . import vegetation
    from . import veg_tools as vt
    spec = vt.load(name) if name else {"species": species}
    if not name and not species:
        raise ValueError("give a plant's name or species=<preset>")
    age = float(vegetation.resolve(spec)["age"])
    if not cases:
        cases = [{"name": f"open, {round(age * k)} y", "age": round(age * k)} for k in (0.2, 0.45, 1.0, 2.0)]
        cases += [{"name": f"stand edge, {round(age)} y", "age": age, "environment": {"setting": "edge", "spacing": 4.0, "open_side": [-1, 0]}},
                  {"name": f"stand interior, {round(age)} y", "age": age, "environment": {"setting": "forest", "spacing": 4.0}}]
    msg = ""
    sd = tuple(range(1, int(seeds) + 1))
    if fit:
        r = vegetation.fit_form(spec, cases, fit, iters=int(iters), seeds=sd)
        if name:
            v = vt.save(name, patch={"habit": r["habit"]}, note="fit to form targets")
            msg = f"fitted v{v}: "
        msg += f"miss {r['miss']} with habit {json.dumps(r['habit'])}\n"
        cs = r["cases"]
    else:
        cs = vegetation.form_cases(spec, cases, sd)
    L = []
    for c in cs:
        m = c["measures"]
        cells = []
        for k in vegetation.FORM_KEYS:
            t = c.get(k)
            cells.append(f"{k} {m[k]:g}" + ("" if t is None else (f" (in {t})" if t[0] <= m[k] <= t[1] else f" MISS {t}")))
        L.append(f"{c.get('name', str(c['age']) + ' y')}: " + ", ".join(cells) + f"; living limbs {m['limbs']:g}; over seeds width +-{c['spread']['width_over_height'] / 2:.2f}, crown +-{c['spread']['crown_ratio'] / 2:.2f}")
    return msg + "\n".join(L) + f"\ntotal miss {vegetation.form_miss(cs):.2f} (0 = every target met)"


@mcp.tool(structured_output=False)
def get_plant(name: str = "", species: str = "") -> str:
    """A plant's own spec, what it resolves to (every value in force), usual ranges and growth steps; read before
    overriding. species alone: that preset resolved. Details: guide(topic="get_plant")."""
    from . import veg_tools as vt
    if not name and not species:
        raise ValueError("give a plant's name, or species=<preset> to see a preset")
    return json.dumps(vt.describe(name or None, species or None), indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))


@mcp.tool(structured_output=False)
def plant_reference(name: str, image_path: str, crop: list[int] | None = None, foot: int | None = None,
                    polygon: list[list[float]] | None = None, tol: float = 30.0, horizon: int | None = None,
                    bare: bool = False, credit: str = "", fit: dict | None = None, fit_iters: int = 40) -> str:
    """Give the plant a reference photo (polygon, or crop + foot + tol + horizon; bare for winter) and measure the
    outline against it; fit {habit path: [lo, hi]} searches habit numbers (fit_iters). credit. Details:
    guide(topic="plant_reference")."""
    from . import veg_tools as vt
    from . import vegetation
    mask = {"polygon": polygon} if polygon else {"crop": crop, "foot": foot, "tol": tol, "horizon": horizon}
    if not polygon and (crop is None or foot is None):
        raise ValueError("give polygon (a traced outline), or crop [x0, y0, x1, y1] + foot (the trunk's x)")
    ref = vt.set_reference(name, image_path, mask, bare, credit)
    msg = ""
    if fit:
        R = vegetation.reference_mask(ref["image"], **ref["mask"])
        dirs = vegetation.photo_branch_directions(ref["image"], ref["mask"]) if bare else None
        r = vegetation.fit_habit(vt.load(name), R, fit, bare=bare, iters=int(fit_iters), directions=dirs)
        v = vt.save(name, patch={"habit": r["habit"]}, note="fit to reference")
        msg = f"fitted v{v}: outline IoU {r['iou']} with habit {json.dumps(r['habit'])}\n"
    return msg + vt.report(name)


@mcp.tool(structured_output=False)
def export_plant(name: str, out_dir: str | None = None, triangles: int | None = None, set: bool = False,
                 lods: int = 1, impostor: bool | str = False, seasons: list[str] | None = None, wet: bool = False,
                 lod_files: bool = False, grade: str = "full") -> str:
    """Export the plant as a GLB (wood + foliage cards, wind channels, collision): triangles (LOD 0 budget), lods,
    impostor (octahedral | "cross"), seasons, wet, lod_files, set (one file for a set), grade "groundcover"; swards
    export as tiles. Details: guide(topic="export_plant")."""
    from . import veg_tools as vt
    from . import veg_export as _ve
    vt_contract = lambda: _ve.CONTRACT
    if set:
        c = vt.export_set(name, out_dir, triangles, lods=lods, seasons=tuple(seasons or ("summer",)), wet=wet)
        return (f"exported {c['path']} ({c['bytes'] / 1e6:.1f} MB): {len(c['plants'])} plants, {c['total']} triangles in all (LOD 0), "
                f"one bark + one foliage material\n" + "\n".join(
                    f"  {q['name']}: {q['height_m']} m, " + "; ".join(f"LOD{l_['lod']} {l_['triangles']}" for l_ in q["lods"]) + " triangles"
                    + (f", {q['floating']:.0%} of the cards floating" if q.get("floating", 0) > 0.2 else "")
                    for q in c["plants"]))
    if vt.grown(name).get("sward"):
        c = vt.export(name, out_dir, seasons=tuple(seasons or ()))
        return (f"exported the sward {name} into {Path(c['path']).parent} (contract {vt_contract()}): "
                + "; ".join(f"LOD{l_['lod']} {l_['triangles']} triangles ({l_['triangles_per_m2']:.0f} per m2, {l_['blades']} blades)" for l_ in c["lods"])
                + f"\na {c['sward']['tile_m']:g} m TILE: lay tiles edge to edge, quarter turns; fade into the terrain's grass texture "
                  f"{c['sward']['fade']['start']}-{c['sward']['fade']['end']} m (recipe + root / tip colours in the seasons json `sward`)\n"
                + "files: " + ", ".join(Path(f).name for f in c["files"]))
    if grade == "groundcover":
        c = vt.export(name, out_dir, seasons=tuple(seasons or ()), grade="groundcover")
        return (f"exported the groundcover grade of {name} into {Path(c['path']).parent} (contract {vt_contract()}): "
                + "; ".join(f"LOD{l_['lod']} {l_['triangles']} triangles ({l_['planes']} cards)" for l_ in c["lods"])
                + f"; clump {c['H']:.2f} m tall, {2 * c['R']:.2f} m across; atlas {c['atlas'][0]} x {c['atlas'][1]} per season\n"
                + "files: " + ", ".join(Path(f).name for f in c["files"])
                + "\nENGINE: import the PNGs without mipmaps, or with them + the mip-scaled alpha (material extras.alpha_mips); "
                  "turn mesh LOD generation off for these files")
    c = vt.export(name, out_dir, triangles, lods=lods, seasons=tuple(seasons or ("summer",)), wet=wet, impostor_lod=impostor,
                  lod_files=lod_files)
    gl = []
    for mesh, g_ in (c.get("ground") or {}).items():
        if g_["under"]:
            gl.append(f"WARNING: {mesh}: {g_['under']} of {g_['vertices']} vertices are under the ground (deepest {g_['max_mm']} mm, "
                      f"median {g_['p50_mm']} mm)")
    ground = ("\nground: in the file, " + ("nothing but the trunk's foot is under it" if not gl else "geometry is under it")
              + "".join("\n" + l_ for l_ in gl)) if c.get("ground") else ""
    ground += ("\nfor engines without MSFT_lod / KHR_materials_variants (Godot 4.7 keeps only LOD 0 of the combined file, drops "
               "nodes outside the scene and drops variants): use the _LOD<k>.glb files (lod_files=True)"
               + (f", {Path(c['collision_file']).name} (its node is named ...-colonly: Godot makes a static body of it)" if c.get("collision_file") else "")
               + (f", {Path(c['seasons_file']).name} (contract version {vt_contract()} + the slot list, then each season's material parameters per slot; `hidden` = don't draw)" if c.get("seasons_file") else ""))
    if impostor == "cross":
        ground += ("\nimpostor: two crossed quads, albedo + normal map per season, lit by the engine like the mesh LODs; ENGINE: its material must not receive "
                   "shadows (Godot: disable_receive_shadows), or the two quads shadow each other into a dark wedge")
    elif impostor:
        ground += ("\nimpostor: hemi-octahedral (one quad + an 8 x 8 atlas of views over the upper hemisphere, object-space normals + depth): it NEEDS "
                   "the engine's impostor shader (recipe in the impostor material's extras.hifipushie_impostor and the seasons json `impostor`; "
                   "Godot: spikes/godot_veg/impostor_octa.gdshader, extra_cull_margin = size / 2); no shadows received on it. "
                   "Import the impostor atlases WITH mipmaps (Godot: mipmaps/generate=true; the normal atlas as plain RGBA, "
                   "not a normal map: its alpha is the depth): without mips a far impostor costs ~40x more GPU time")
    if c.get("style"):
        from . import veg_style
        ground += "\n" + "\n".join(veg_style.lines(c["style"]) + veg_style.warnings(c["style"]))
    return (f"exported {c['path']} ({c['bytes'] / 1e6:.1f} MB), {c['total']} triangles"
            + (f" for a budget of {triangles}" if triangles else "") + f": wood {c['wood_triangles']} triangles"
            + (f" (wood thinner than {c['wood_min_radius_m'] * 1000:.0f} mm left out)" if c["wood_min_radius_m"] else "")
            + f", foliage {c['foliage_triangles']} triangles"
            + (f" ({c['twigs_kept']:.0%} of the twigs, drawn larger)" if c["twigs_kept"] < 1 else "")
            + (f", atlas {c['atlas_px']} px" if "atlas_px" in c else "")
            + ("\nLODs: " + "; ".join(
                f"LOD{l_['lod']} {l_['triangles']} triangles" + (" (impostor)" if l_.get("impostor") else "")
                + (f", under {l_['switch_below_screen_height']:.0%} of the screen's height" if l_.get("switch_below_screen_height") else "")
                for l_ in c["lods"]) if len(c["lods"]) > 1 else "")
            + (f"\nvariants: {', '.join(c['variants'])}" if c["variants"] else "")
            + f"\nwind: TEXCOORD_1 (trunk, branch), TEXCOORD_2 (phase, flutter), _WIND; collision: {c['collision_capsules']} capsules"
              f" + a {c['collision_triangles']}-triangle mesh"
            + ground
            + (f"\nfiles: {', '.join(Path(f).name for f in c['files'])}" if len(c["files"]) > 1 else "")
            + (f"\nWARNING: {c['over']} triangles over the budget: the wood alone needs {c['wood_triangles']} "
               f"(a trunk and its main limbs can't go lower); raise the budget" if c["over"] else "")
            + (f"\nWARNING: {c['floating']:.0%} of the cards have no drawn wood near them (they will float): raise the budget"
               if c.get("floating", 0) > 0.2 else "")
            + ("\nWood you marked (dead wood, drawn guides) is kept down to a quarter of that girth." if triangles else "")
            + (f"\nLook at it before using it: look_plant(name, views=['leaf', 'far'], triangles={triangles}); "
               f"wind_plant(name) renders it swaying" if triangles else ""))


def _wind_disp(d: dict, height: float) -> str:
    """The clip's motion in metres, with what it should be."""
    if not d:
        return ""
    f = lambda k: f"{d[k]['mean_m'] * 100:.1f} cm mean / {d[k]['max_m'] * 100:.1f} cm most" if k in d else "none found"
    out = (f"moved, measured on the vertices: foot {f('foot')}; trunk top {f('trunk_top')}; limb ends {f('limb_ends')}; "
           f"leaf tips {f('leaf_tips')}")
    if "limbs_in_step" in d:
        out += f"; limbs in step {d['limbs_in_step']} (1 = all swing together, a board; 0.2-0.7 reads as a tree)"
    warn = []
    if d.get("foot", {}).get("max_m", 0) > 0.01:
        warn.append("WARNING: the foot moves (trunk channel not 0 at the ground)")
    if height and d.get("trunk_top", {}).get("max_m", 0) > 0.06 * height:
        warn.append("WARNING: the trunk's top swings more than 6% of the height: rubber; lower strength")
    if d.get("limb_ends", {}).get("max_m", 1) < 0.01:
        warn.append("WARNING: limb ends move under 1 cm: the tree stands frozen; raise strength")
    return out + ("\n" + "\n".join(warn) if warn else "") + "\n"


@mcp.tool(structured_output=False)
def wind_plant(name: str, triangles: int | None = 20000, seconds: float = 4.0, strength: float = 1.0,
               wind_from: float = 270.0, azimuth: float = 0.0):
    """Sway the exported plant from its own wind channels as a game would: a six-frame strip + mp4. triangles, seconds,
    strength (0.3 breeze .. 2 gale), wind_from (bearing), azimuth. Details: guide(topic="wind_plant")."""
    from . import veg_tools as vt
    r = vt.wind(name, triangles, seconds, 12, strength, wind_from, azimuth)
    imp = [o for o in r["import"]["objects"] if o.get("type") == "MESH"]
    txt = (f"wind: {r['n']} frames at 12 fps -> {r.get('mp4', '(no ffmpeg: frames in ' + r['frames'] + ')')}\nstrip: {r['strip']}\n"
           f"{r['moved_share']:.0%} of the picture changes against frame 0 (mean over the clip)\n"
           + _wind_disp(r["import"].get("displacement") or {}, r.get("height", 0.0)) +
           f"Blender {r['import']['blender']} import of {Path(r['glb']).name}: " + "; ".join(
               f"{o['name']} {o['triangles']} triangles, uv sets {len(o['uv_layers'])}, attributes {o['attributes'] or 'none'}"
               + (f", _WIND vs uv differ by {o['wind_custom_vs_uv_max_diff']}" if "wind_custom_vs_uv_max_diff" in o else "")
               for o in imp))
    return [_out(PILImage.open(r["strip"]), None), txt]


@mcp.tool(structured_output=False)
def sync_plant(name: str, pull_only: bool = False) -> str:
    """Round-trip the plant through plant.blend: guide/limb curve edits come back into the spec, then the file is
    rewritten (pull_only skips that). Details: guide(topic="sync_plant")."""
    from . import veg_tools as vt
    before, prev = vt.grown(name)["stats"], vt.load(name)
    if pull_only:
        came, head = vt.pull(name), ""
    else:
        r = vt.sync(name)
        came = r["pulled"]
        head = (f"wrote {r['blend']} ({r['guides']} guide curves, {r['limbs']} limb curves"
                + (", the running Blender reloaded it" if r["live"] else "") + ")\n")
    if not came:
        return head + "nothing was changed in Blender since the last sync"
    return head + "from Blender:\n" + "\n".join(f"  {c}" for c in came) + "\n" + vt.change_note(name, prev, before) + "\n" + vt.report(name)


@mcp.tool(structured_output=False)
def plant_history(name: str, revert_to: int | None = None) -> str:
    """List a plant's versions, or restore one (revert_to; saved as a new version). Details:
    guide(topic="plant_history")."""
    from . import veg_tools as vt
    if revert_to is not None:
        v = vt.revert(name, revert_to)
        return f"plant {name} v{v} = v{revert_to}\n" + vt.report(name)
    return "\n".join(f"v{h['version']}  {h['note']}" for h in vt.history(name))
