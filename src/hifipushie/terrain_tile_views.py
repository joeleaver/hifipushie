"""Views of exported tiles (render_tiles). Part of the terrain mesh (terrain_mesh.py has the overview)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy import ndimage

from .terrain_gltf import _from_gltf, read_glb
from .terrain_materials import Materials
from .terrain_tile_finish import LIGHTS, _light
from .terrain_tile_jobs import build_field
from .terrain_tile_mesh import _boundary_edges

# ---------------------------------------------------------------- views
def border_segments(out_dir, lod=0):
    """The shared tile borders as the meshes have them: every surface edge on a border between two tiles."""
    out = Path(out_dir)
    M = json.loads((out / "manifest.json").read_text())
    wlo = np.min([e["min"] for e in M["tiles"]], 0)
    whi = np.max([e["max"] for e in M["tiles"]], 0)
    segs = []
    for e in M["tiles"]:
        L = e["lods"][lod]
        if L is None:
            continue
        tr, prims = read_glb(out / L["file"])
        P = _from_gltf(prims[0]["POSITION"].astype(np.float64)) + _from_gltf(tr[None])[0]
        be = _boundary_edges(prims[0]["indices"])
        a, b = P[be[:, 0]], P[be[:, 1]]
        keep = np.zeros(len(be), bool)
        for ax, lim in ((0, e["min"][0]), (0, e["max"][0]), (1, e["min"][1]), (1, e["max"][1])):
            if wlo[ax] < lim < whi[ax]:
                keep |= (a[:, ax] == lim) & (b[:, ax] == lim)
        segs.append(np.stack([a[keep], b[keep]], 1))
    return np.concatenate(segs) if segs else np.zeros((0, 2, 3))


def _site_props(T, box=None):
    """The sites' props for render_tiles' stand-ins: [x, y, ground z, yaw, name] (inside `box` if given)."""
    out = []
    for st in getattr(T, "sites", {}).values():
        pr = st.get("prop")
        if not pr:
            continue
        x, y = map(float, st["xy"])
        if box and not (box[0][0] <= x <= box[1][0] and box[0][1] <= y <= box[1][1]):
            continue
        out.append([x, y, float(T.height(np.array([x, y]))), float(pr.get("yaw", 0.0)), str(pr["name"])])
    return out


def render_tiles(T, out_dir, views, lod=0, size=(1400, 800), samples=48, trees=True, box=None, skirt_color=None,
                 parts="all", textured=True, channel=None, ids=False, detail_fade=True, detail_show=None, haze=5000.0,
                 props=True, clutter=120.0, grade=None, light=None, grass=True, buried_color=None, extra=None,
                 styles_bump=False):
    """Cycles renders of the written tiles, imported by Blender's glTF importer. views: {"name", "eye": address |
    [x, y] | [x, y, z], "lift" (m above the ground or the sea), "look": address | [x, y, z], "fov", "sun": [bearing,
    height], "borders": bool, "lamp": watts (a headlamp at the eye, for inside caves), "out"}. box: [[x0, y0],
    [x1, y1]]: only tiles (and trees) inside. lod: a level, or
    "checker" (LOD 0 and the coarsest alternating, to see the skirts at work). parts (cliffs mode): "all", "ground"
    (the heightmap alone: what a game shows without the overlay) or "cliffs". textured: True (the baked material),
    "layered" (the engine recipe: tiling layers over the baked maps), "styles" (the terrain styles recipe:
    terrain_style.RECIPE, each zone in its style), "detail" (the tiling rock detail over the baked
    macro maps, as the manifest's detail recipe draws it: needs an export with cfg detail) or False (vertex colour). channel: one baked
    channel alone ("base", "ao": unlit; "normal": the normal map on flat grey; "clay": geometry only). ids: also an id
    pass per view (<out>_ids.npy: glb index + 1, chart, view distance) for `terrain_seams.measure`; the job's "glbs"
    and "kinds" say which file each index is. A view's "sun" may be [bearing, height], a word terrain_sun knows, or
    "auto" / left out (terrain_sun picks a raking sun for what the view sees; the choice is noted in render_job.json).
    haze: aerial perspective, metres for 63% (None/0: off). props: placeholder buildings, tee pads and baskets on the
    sites (the export's meta), for scale. clutter: metres round each eye where ground clutter placeholders stand
    (terrain_ground.clutter: bushes on the scrub, tussocks and tall grass in rough grass, boulders on the shore;
    0/None: none). grade: a view transform look ("AgX - Punchy"). light: a preset name from LIGHTS ("clear": a deep
    blue clear sky and a strong sun, like a sunny photo) or {"dust", "air", "sun_energy", "sky_strength",
    "exposure"}; default the hazy sky every earlier round was judged under. grass=False leaves the turf's tiling
    detail out (to tell what it adds). buried_color: [r, g, b] draws the cliff shells' buried backs flat in that
    colour (an engine shows any of it that stands in the open: a fault)."""
    import subprocess
    out = Path(out_dir)
    M = json.loads((out / "manifest.json").read_text())
    glbs, kinds = [], []
    for e in M["tiles"] * (parts != "ground") + M.get("ground", []) * (parts != "cliffs"):
        if box and (e["max"][0] < box[0][0] or e["min"][0] > box[1][0] or e["max"][1] < box[0][1]
                    or e["min"][1] > box[1][1]):
            continue
        k = (len(M["lods"]) - 1) * ((e["i"] + e["j"]) % 2) if lod == "checker" else lod  # mixed LODs: seams show
        if e["lods"][k]:
            glbs.append(str(out / e["lods"][k]["file"]))
            kinds.append(["ground" if e["lods"][k]["file"].startswith("ground") else "cliff", e["i"], e["j"], k])
    jobs, notes = [], []
    sea = M.get("sea_level")
    for v in views:
        if isinstance(v["eye"], list) and len(v["eye"]) == 3:
            eye = list(map(float, v["eye"]))
        else:
            xy, h, _ = T.address(v["eye"])
            if sea is not None:
                h = max(h, sea)
            eye = [float(xy[0]), float(xy[1]), h + v.get("lift", 1.7)]
        if isinstance(v["look"], list) and len(v["look"]) == 3:
            look = list(map(float, v["look"]))
        else:
            xy, h, _ = T.address(v["look"])
            look = [float(xy[0]), float(xy[1]), h]
        sun = v.get("sun", "auto")
        if not (isinstance(sun, (list, tuple)) and len(sun) == 2):
            from . import terrain_sun
            sb, sh, snote = terrain_sun.for_view(T, {**v, "sun": sun}, eye, look)
            sun = [float(sb), float(sh)]
            notes.append(f"{Path(v['out']).name}: {snote}")
        jobs.append({"eye": eye, "look": look, "fov": v.get("fov", 55), "sun": list(map(float, sun)),
                     "lamp": v.get("lamp", 0.0), "exposure": v.get("exposure", 0.0), "fill": v.get("fill", 0.4),
                     "fill_at": v.get("fill_at", 8.0),
                     "borders": v.get("borders", False), "out": str(Path(v["out"]).resolve())})
    job = {"glbs": glbs, "sea": sea, "size": list(size), "samples": samples, "views": jobs,
           "trees": str(out / "trees.csv") if trees else None, "tree_box": box, "skirt_color": skirt_color, "buried_color": buried_color,
           "textured": bool(textured), "channel": channel, "ids": bool(ids), "kinds": kinds,
           "haze": (float(haze) * float(_light(light).get("haze_scale", 1.0))) if haze else None, "notes": notes,
           "props": _site_props(T, box) if props else [], "grade": grade,
           "light": LIGHTS.get(light, light) if isinstance(light, str) else light}
    if textured == "layered":  # the engine recipe: tiling layers over the baked maps
        job["layers"] = [{"path": str((out / L["textures"]["height"]).resolve()), "scale": L["scale"],
                          "strength": L["textures"]["detail_strength"], "attr": L["weights"], "channel": L["channel"]}
                         for L in M["materials"]["layers"] if "textures" in L]
    if textured == "styles":  # the terrain styles' recipe (terrain_style.RECIPE) over the baked maps
        SM = M.get("styles")
        if not SM:
            raise ValueError("textured='styles' needs an export of a spec with \"styles\"")
        from . import terrain_style
        lin = lambda c: [float(x) for x in terrain_style._srgb_lin(c)]
        real = next(s for s in SM["styles"] if s["name"] == "realistic")
        wl = {L["name"]: (L["weights"], L["channel"]) for L in M["materials"]["layers"]}
        maps = [(str((out / fn).resolve()), SM["order"][4 * g:4 * g + 4]) for g, fn in enumerate(SM["maps"]["weights"])]
        job["styles"] = {
            "bump": bool(styles_bump),  # (the layers' heights as a bump: an engine uses their normal maps)
            "weights": wl, "ref": {k: lin(v["color"]) for k, v in real["layers"].items()},
            "extent": SM["maps"]["extent"], "maps": maps,
            "rock_scale": ({**SM["maps"]["rock_scale"], "file": str((out / SM["maps"]["rock_scale"]["file"]).resolve())}
                           if SM["maps"].get("rock_scale") else None),
            "styles": [{"name": s["name"], "macro": s["macro"], "macro_normal": s["macro_normal"],
                        "layers": {k: {"albedo": str((out / v["albedo"]).resolve()),
                                       "height": str((out / v["height"]).resolve()), "size": v["size_m"],
                                       "normal": (str((out / v["normal"]).resolve()) if v.get("normal") else None),
                                       "height_m": v["height_m"], "projection": v.get("projection", "top"),
                                       "small": ({**v["small"], "albedo": str((out / v["small"]["albedo"]).resolve())}
                                                 if v.get("small") else None)}
                                   for k, v in s["layers"].items()}}
                       for s in SM["styles"]]}
        grass = False
    if textured == "detail":  # the tiling rock detail (terrain_swatch) over the baked macro maps
        D = M.get("detail")
        if not D:
            raise ValueError("textured='detail' needs an export with the detail layer (cfg detail: true)")
        rock = [(L["weights"], L["channel"]) for L in M["materials"]["layers"] if L["name"] in D["layers"]]
        job["detail"] = {"uv": "UVMap" + (f".{D['texcoord']:03d}" if D["texcoord"] else ""), "size": D["size_m"],
                         "albedo": str((out / D["albedo"]).resolve()), "normal": str((out / D["normal"]).resolve()),
                         "height": str((out / D["height"]).resolve()), "height_m": D["height_m"], "rock": rock,
                         "bins": D["bins"], "line_d": D.get("line_d", 0.5),
                         "variation": str((out / D["variation"]).resolve()), "variation_m": D["variation_m"],
                         "variation_scale": D["variation_scale"], "variation_offset": D["variation_offset"],
                         "fade": (D.get("fade") or {}).get("footprint_m") if detail_fade else None, "show": detail_show}
    if clutter and not channel:  # ground clutter round the eyes (an engine's detail scatter, as placeholders)
        from . import terrain_ground
        cf, *_ = build_field(T)
        cm = Materials(T, cf)
        ks = ("bush", "tussock", "tallgrass", "boulder")
        eyes = np.array([j["eye"] for j in jobs], float)
        lo_, hi_ = eyes[:, :2].min(0) - clutter, eyes[:, :2].max(0) + clutter
        if box:
            lo_, hi_ = np.maximum(lo_, box[0]), np.minimum(hi_, box[1])
        C = terrain_ground.clutter(T, cm, cf, ks, box=[lo_.tolist(), hi_.tolist()], near=(eyes, clutter))
        if len(C):  # (no bush or boulder at an eye: a view from inside a bush was all leaves)
            from scipy.spatial import cKDTree
            de, _ = cKDTree(eyes[:, :2]).query(C[:, :2])
            C = C[(de > 2.5) | np.isin(C[:, 3], [ks.index("tussock"), ks.index("tallgrass")])]
        job["clutter"] = {k: C[C[:, 3] == i][:, [0, 1, 2, 4, 5, 6]].round(3).tolist() for i, k in enumerate(ks)}
        from . import terrain_stream
        if terrain_stream.config(T) is not None:  # (stream, lake and beach clutter: terrain_stream.all_clutter)
            from scipy.spatial import cKDTree
            SC = terrain_stream.all_clutter(T, cm, cf, box=[lo_.tolist(), hi_.tolist()])
            if len(SC):
                de, _ = cKDTree(eyes[:, :2]).query(SC[:, :2])
                SC = SC[(de < clutter) & (de > 1.2)]
            if len(SC):  # (half-buried stones: the row's sink)
                SC = SC.copy()
                SC[:, 2] -= SC[:, 10]
            for i, k in enumerate(terrain_stream.KINDS):  # (bush: with the dry ground's bushes)
                k = "driftwood" if k in ("snag", "limb") else k  # (drawn as driftwood stand-ins)
                job["clutter"][k] = job["clutter"].get(k, []) + SC[SC[:, 3] == i][:, [0, 1, 2, 4, 5, 6]].round(3).tolist()
    if not channel:  # the rivers' water: a ribbon at each river's own level, wider than the channel (the banks hide it)
        if True:
            rv = []
            for rw in (getattr(T, "river_water_lines", None) or {}).values():
                xy_, lv_, w_ = np.asarray(rw["xy"], float), np.asarray(rw["level"], float), np.asarray(rw["width"], float)
                live = w_ > 0
                if box is not None:
                    live &= (xy_[:, 0] >= box[0][0]) & (xy_[:, 0] <= box[1][0]) & (xy_[:, 1] >= box[0][1]) & \
                        (xy_[:, 1] <= box[1][1])
                if live.sum() >= 2:
                    # (the level eased along the path: its own steps, a few dm where a bank holds it down, drew the
                    # ribbon as a staircase)
                    lv_ = ndimage.gaussian_filter1d(lv_, 5.0, mode="nearest") - 0.04
                    rv.append(np.c_[xy_, lv_, w_ + 4.0][live].round(3).tolist())
            # (lakes: a level sheet over each lake's own wet cells, a strip per grid row and run, a cell past each end
            # so it meets the shore; over the lake's whole box it hung in the air beyond a dam)
            from . import terrain_shore
            c_ = float(T.cell)
            for _, m_, lv_ in terrain_shore.still_waters(T):
                m_ = ndimage.binary_dilation(m_)
                for iy_ in np.flatnonzero(m_.any(1)):
                    y_ = float(T.ys[iy_])
                    if box is not None and not (box[0][1] - c_ <= y_ <= box[1][1] + c_):
                        continue
                    d_ = np.diff(np.r_[0, m_[iy_].astype(np.int8), 0])
                    for a_, b_ in zip(np.flatnonzero(d_ == 1), np.flatnonzero(d_ == -1) - 1):
                        rv.append([[float(T.xs[a_]) - 0.5 * c_, y_, lv_ - 0.02, 0.5 * c_],
                                   [float(T.xs[b_]) + 0.5 * c_, y_, lv_ - 0.02, 0.5 * c_]])
            job["rivers"] = rv
        if job.get("clutter"):
            notes.append("clutter: " + ", ".join(f"{len(v)} {k}" for k, v in job["clutter"].items()))
    if extra:  # GLBs stood in the scene: [{"glb", "at": [x, y, z], "yaw": deg, "scale", "squash", "tint": linear rgb}] (clutter kit
        # assets beside the cliffs they should belong to; the tint is the per-instance colour an engine multiplies in)
        job["extra"] = extra
    GD = M.get("ground_detail")
    if GD and textured and not channel and grass:  # the turf's tiling detail over the baked maps (as an engine draws it)
        job["grass"] = [{"albedo": str((out / g["albedo"]).resolve()), "normal": str((out / g["normal"]).resolve()),
                         "size": g["size_m"], "fade": g.get("fade_m", GD["fade_m"]), "weights": g["weights"]}
                        for g in GD.get("swatches") or [GD]]
    if any(v.get("borders") for v in views):
        np.savez(out / "borders.npz", segs=border_segments(out, 0 if lod == "checker" else lod))
        job["borders"] = str(out / "borders.npz")
    (out / "render_job.json").write_text(json.dumps(job))
    script = Path(__file__).with_name("blender_tiles.py")
    r = subprocess.run(["blender", "-b", "--factory-startup", "--python", str(script), "--",
                        str(out / "render_job.json")], capture_output=True, text=True)
    if r.returncode or "Traceback" in r.stdout + r.stderr:
        raise RuntimeError(r.stderr[-2000:] + r.stdout[-3000:])
    return [j["out"] for j in jobs]
