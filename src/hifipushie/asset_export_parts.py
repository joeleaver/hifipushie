"""The parts on their way to the atlas: the scene split and meshed, texel density and who shares an atlas, the low
poly, the bake. Stages of the game-ready export (asset_export._export calls them in order; asset.py has the overview)."""
from __future__ import annotations

import time

import numpy as np
from PIL import Image

from . import asset
from . import sdf
from .asset_bake import bake, face_keep_paint, inner_paint
from .asset_glb import texel_sizes
from .asset_hidden import hide_export_part, own_mouth_meshes, prune_hidden
from .asset_parts import _max_triangles, _min_triangles, _weight, atlas_groups, decal_focus, focus_regions, lowpoly, part_areas, planar_uvs, texture_loads
from .asset_quality import _designed_interior, defect_regions, mesh_quality, seam_steps
from .asset_raster import _png
from .asset_scene import scene_maps
from .asset_split import _pow2, density_groups, mesh_parts, split, split_big, topology_parts

def _mesh(ex):
    """The scene split into parts and meshed at full detail; what never shows pruned."""
    ex.out_dir.mkdir(parents=True, exist_ok=True)
    ex.ctx = split(ex.spec, ex.resolution, ex.instancing, ex.log, min_share=1, voxels=ex.fine)
    if ex.rig:  # parts bound to a joint of their own (parts.<p>.rig_bone) move apart from the rest: what they cover
        # at rest is seen in a pose (the golfer's shorts had a hole where the hip bag sat, shown by a lifted thigh)
        ex.ctx["apart"] = {pn: (ex.defs.get(ex.ctx["origin"][pn]) or {}).get("rig_bone") for pn in ex.ctx["streams"]}
    for pn, v in ex.fine.items():
        if ex.ctx["frames"].get(pn) and ex.ctx["frames"][pn][1] <= v:
            ex.log.append(f"{pn}: meshed at {ex.ctx['frames'][pn][1] * 1000:.2f} mm for the face shapes (the lips' slit, teeth)")
    ex.origin = ex.ctx["origin"]
    tm = time.time()
    ex.high = mesh_parts(ex.ctx, ex.out_dir / "high.npz")
    ex.log.append(f"meshed {len(ex.ctx['streams'])} parts in {time.time() - tm:.1f}s (scene voxel {ex.ctx['voxel'] * 1000:.1f} mm)")
    own_surface = None
    if ex.face_shapes and getattr(ex.fface, "gnm_mouth", False):  # GNM's own teeth and tongue lie behind the closed lips
        from . import base_gnm_parts
        from . import base
        mp = base_gnm_parts.gnm_mouth(ex.fface.head)
        pts = {k: base_gnm_parts._piece_points(mp[k]["verts"], mp[k]["faces"])["verts"] for k in ("teeth_upper", "teeth_lower", "tongue")}
        own_surface = {base.TEETH_PARTS[0]: pts["teeth_upper"], base.TEETH_PARTS[1]: pts["teeth_lower"],
                       "tongue": pts["tongue"]}
        own_mouth_meshes(ex.high, mp, ex.log)
        # (their own vertices ARE the surface: every face kept, whatever covers the rows in the neutral)
        own_surface.update({base.TEETH_PARTS[0]: np.asarray(mp["teeth_upper"]["verts"], float),
                            base.TEETH_PARTS[1]: np.asarray(mp["teeth_lower"]["verts"], float),
                            "tongue": np.asarray(mp["tongue"]["verts"], float)})
    prune_hidden(ex.ctx, ex.high, ex.log, own_surface)


def _density(ex):
    """Texel density: each part's area, focus regions and texture load, planar parts, who shares an atlas, topology parts."""
    if ex.texel_density:
        split_big(ex.high, ex.ctx, {pn: _weight(ex.defs, ex.origin[pn], "texel_density") * ex.texel_density for pn in ex.ctx["streams"]},
                  ex.texture, ex.log)
    ex.areas = part_areas(ex.high)

    def w(pn, key):
        return _weight(ex.defs, ex.origin[pn], key)
    ex.w = w
    ex.focus = {pn: focus_regions(ex.spec, ex.origin[pn]) for pn in ex.areas}
    # image decals keep their own resolution: their density relative to the part's (asked, or what an atlas of
    # `texture` holds over every part). A prefab's part (or a split slab) takes the decals reaching its own mesh: it
    # is unwrapped where its bake instance stands, as the scene paints it
    guess = ex.texture * np.sqrt(asset.FILL / max(sum(ex.areas.values()), 1e-9))
    with np.load(ex.high) as z:
        hv, hp, hnames = z["verts"], z["part"], [str(n) for n in z["part_names"]]
    for pn in ex.areas:
        box = None
        if pn != ex.origin[pn] and pn in hnames:
            pv = hv[hp == hnames.index(pn)]
            box = (pv.min(0) - 0.01, pv.max(0) + 0.01) if len(pv) else None
        if pn == ex.origin[pn] or box is not None:
            dec = decal_focus(ex.spec, ex.origin[pn], ex.w(pn, "texel_density") * (ex.texel_density or guess), box)
            if dec:
                ex.focus[pn] = ex.focus[pn] + dec
                ex.log.append(f"{pn}: texel focus over {len(dec)} image decal(s), x{', x'.join(f'{d[4]:.1f}' for d in dec)}")
    ex.rel ={pn: ex.w(pn, "texel_density") * (ex.texel_density or 1.0) for pn in ex.areas}
    ex.loads = texture_loads(ex.high, ex.rel, ex.focus)
    ex.fixed = {pn: str(ex.defs[ex.origin[pn]]["atlas"]) for pn in ex.areas if (ex.defs.get(ex.origin[pn]) or {}).get("atlas") is not None}
    # parts.<p>.uv = "planar": a swappable surface (a clock's dial, a sign, a screen) gets its own material and 0..1
    # planar UVs, so an engine swaps its texture by one property (s0urc3: the dial needed a custom UV shader)
    ex.planar = {pn for pn in ex.areas if (ex.defs.get(ex.origin[pn]) or {}).get("uv") == "planar"}
    for pn in ex.planar:
        ex.fixed.setdefault(pn, f"planar_{pn}")
    ex.pf_of = {pn: pf for pf, d in ex.ctx["prefabs"].items() for pn in d["parts"]}
    ex.units: dict[str, list] = {}
    for pn in ex.areas:  # a prefab's parts go on one atlas together (one material per instance where possible)
        ex.units.setdefault(ex.pf_of.get(pn, pn), []).append(pn)
    if ex.texel_density:  # say now, not after the bake, which parts can't get the density asked for (a prefab too
        # big for an atlas: scene parts were split above)
        for u, pns in ex.units.items():
            need = sum(ex.loads[pn] for pn in pns)
            cap = ex.texture ** 2 * asset.FILL
            if need > cap:
                got = ex.texel_density * np.sqrt(cap / need)
                area = sum(ex.loads[pn] / ex.rel[pn] ** 2 for pn in pns)
                ex.log.append(f"{u}: {area:.0f} m^2 of surface wants {np.sqrt(need / asset.FILL):.0f}^2 texels at "
                           f"{ex.texel_density:g}/m, more than one {ex.texture}^2 atlas holds: expect ~{got:.0f}/m "
                           f"(split it into parts, raise texture, or give it a lower texel_density)")
    ex.topo = topology_parts(ex.spec, ex.ctx, ex.out_dir, ex.log, ex.high)
    ex.fill = asset.FILL


def _lowpoly(ex):
    """The low poly and its atlases (packed, once more at a smaller fill if they do not fit), hidden parts, each part's report."""
    for attempt in range(2):
        group = density_groups(ex.units, ex.loads, ex.fixed, ex.texture, ex.fill) if ex.texel_density else atlas_groups(
            ex.loads, ex.fixed, ex.atlases)
        ex.names = sorted(set(group.values()), key=lambda g: (not g.isdigit(), int(g) if g.isdigit() else 0, g))
        ex.sizes = {ai: min(ex.texture, _pow2(np.sqrt(sum(ex.loads[pn] for pn in ex.areas if group[pn] == an) / ex.fill)))
                 if ex.texel_density else ex.texture for ai, an in enumerate(ex.names)}
        ex.cfg = {pn: {"weight": ex.w(pn, "triangle_weight"), "density": ex.w(pn, "texel_density"),
                    "atlas": ex.names.index(group[pn]), "focus": ex.focus[pn], "split": pn in ex.ctx.get("split", {}),
                    "copies": len(ex.ctx["prefabs"][ex.pf_of[pn]]["instances"]) if pn in ex.pf_of else 1,
                    **({} if _min_triangles(ex.defs, ex.origin[pn]) is None else  # (absent: cached decimations stay valid)
                       {"min": _min_triangles(ex.defs, ex.origin[pn])}),
                    **({} if _max_triangles(ex.defs, ex.origin[pn]) is None else {"max": _max_triangles(ex.defs, ex.origin[pn])}),
                    **({"fixed": ex.topo[pn][0], "fixed_sum": ex.topo[pn][1]} if pn in ex.topo else {})} for pn in ex.areas}
        ex.t1 = time.time()
        from . import lashes as _lashes  # the lash ribbons come out of the same budget (their own count, fixed)
        lash_tris = _lashes.triangles(ex.spec)
        if lash_tris:
            ex.log.append(f"lashes: {lash_tris} triangles of the {ex.triangles} budget")
        ex.parts, ex.binfo = lowpoly(ex.high, ex.out_dir / "lowpoly.npz", ex.cfg, max(ex.triangles - lash_tris, ex.triangles // 2), ex.sizes,
                               ex.ctx["voxel"], ex.tri_focus)
        for pn in ex.planar & set(ex.parts):
            ex.parts[pn].update(planar_uvs(ex.parts[pn]))
            ex.log.append(f"{pn}: own material, planar 0..1 UVs (uv: planar)")
        if not ex.texel_density:
            break
        # the size each atlas needs for every part to get its density, now that it's packed
        ts = texel_sizes(ex.parts, ex.sizes, {pn: ex.focus.get(pn) or [] for pn in ex.parts})

        def needs(pn, ai):  # the part's own density, and each focus region's (a decal covering a whole mug: the
            # part's average is the focus's, and sizing the atlas by it alone dropped the focus)
            yield ex.sizes[ai] * ts[pn]["mm_per_texel"] * ex.rel[pn] / 1000
            for f, mm in zip(ex.focus.get(pn) or [], ts[pn].get("focus_mm_per_texel") or []):
                if mm > 0:  # (0: no face of this part in the region)
                    yield ex.sizes[ai] * mm * ex.rel[pn] * f[4] / 1000
        need = {ai: max(x for pn, p in ex.parts.items() if p["atlas"] == ai for x in needs(pn, ai))
                for ai in range(len(ex.names))}
        over = [ai for ai in need if need[ai] > 1.05 * ex.texture and len({ex.pf_of.get(pn, pn) for pn, p in ex.parts.items()
                                                                         if p["atlas"] == ai}) > 1]
        if over and attempt == 0:
            ex.fill = 0.95 * min(sum(ts[pn]["uv_fill"] for pn, p in ex.parts.items() if p["atlas"] == ai) for ai in over)
            ex.log.append(f"atlases {[ex.names[ai] for ai in over]} came out too full for {ex.texel_density:g} texels/m at "
                       f"{ex.texture}: regrouping for a pack fill of {ex.fill:.0%}")
            continue
        ex.sizes = {ai: min(ex.texture, _pow2(0.97 * need[ai])) for ai in need}
        break
    hid_tris = {pn: hide_export_part(ex.ctx, pn, ex.parts[pn], ex.log) for pn in ex.parts}  # (parts.<p>.hides: also after a
    # template wrap or a decimation, which bring back what the high mesh had already lost)
    ex.ntri = sum(len(p["corner_vert"]) // 3 for p in ex.parts.values())
    ex.log.append(f"low poly: {ex.ntri} triangles in the file in {time.time() - ex.t1:.1f}s (joint decimation {ex.binfo['joint_s']:.1f}s, "
               f"per-part {ex.binfo['decimate_s'] - ex.binfo['joint_s']:.1f}s, unwrap + pack {ex.binfo['unwrap_s']:.1f}s)")
    ex.tsz = texel_sizes(ex.parts, ex.sizes, {pn: ex.focus[pn] for pn in ex.parts})
    ex.report = {}
    for pn, p in ex.parts.items():
        b = ex.binfo["parts"][pn]
        ex.report[pn] = {"triangles": len(p["corner_vert"]) // 3, "atlas": ex.names[p["atlas"]],
                      "mm_per_texel": round(ex.tsz[pn]["mm_per_texel"], 2), "area_m2": round(ex.tsz[pn]["area_m2"], 3),
                      "islands": b.get("islands"), "joint_decimation_share": b["joint_count"],
                      "mirrored": b["symmetric"], "texel_density": ex.cfg[pn]["density"],
                      "triangle_weight": ex.cfg[pn]["weight"],
                      **({"uv": "planar", "material": f"{ex.aname}_{ex.names[p['atlas']]}_material"} if pn in ex.planar else {})}
        if pn in ex.pf_of:
            ex.report[pn]["prefab"] = ex.pf_of[pn]
        if hid_tris.get(pn):
            ex.report[pn]["hidden_dropped"] = hid_tris[pn]
        if "focus_mm_per_texel" in ex.tsz[pn]:
            ex.report[pn]["focus_mm_per_texel"] = ex.tsz[pn]["focus_mm_per_texel"]
        des = _designed_interior(ex.topo.get(pn), p["verts"], lid_fold=((ex.spec.get("base") or {}).get("head") or {}).get("lid_fold"))
        if des is not None:  # (bake: the interior's texels keep the low poly's own surface)
            p["designed"] = _designed_interior(ex.topo.get(pn), p["verts"], creases=False)
        q = mesh_quality(p["verts"], p["corner_vert"].reshape(-1, 3), ex.ctx["streams"][pn], designed=des)
        spots = q.pop("spots")
        for other, st in ex.ctx["streams"].items():  # what lies inside another part is never seen (the skin running
            if other != pn and len(spots):       # on into the socket behind an eyeball, a tooth's root)
                spots = spots[sdf.field_at(st, spots, clip=False) > 0]
        if ex.face_shapes and len(spots) and ex.ctx["origin"][pn] == ex.fface.slit_part:
            # the mouth's interior (slit walls, the bag's corners) folds at a game budget and is behind the lips:
            # counted, not part of the tear alarm (Garrett's bag read "TORN OR TANGLED at eye_front.L (12)")
            inm = ex.fface.inside_mouth(spots, ex.ctx["streams"][pn])
            if inm.any():
                q["inside_mouth"] = int(inm.sum())
                spots = spots[~inm]
        where = defect_regions(spots, ex.spec)
        if (ex.defs.get(ex.ctx["origin"][pn]) or {}).get("folds"):  # parts.<p>.folds = true: folded by design (a turned
            where = []                                         # collar, a cuff, pleats): counts stay, no alarm
        if where:
            q["defects_by_joint"] = dict(where)
        ex.report[pn]["quality"] = q
        vx_mm = ex.ctx["frames"][pn][1] * 1000
        warn = [w for w, bad in ((f"p99 {q['err_mm_p99']:.1f} mm from the surface (> 4 voxels: bridged gaps or "
                                  f"cut corners; raise its triangle_weight)", q["err_mm_p99"] > 4 * vx_mm),
                                 (f"{q['folds']} folded edges", q["folds"] > 0),
                                 (f"{q.get('turned', 0)} faces turned against the surface", q.get("turned", 0) > 0),
                                 ("TORN OR TANGLED at " + ", ".join(f"{j} ({k})" for j, k in where[:4])
                                  + ": folded edges / turned faces in a cluster; look at it in clay "
                                    "(rig(glb=..., focus=...)) before shipping", bool(where)),
                                 (f"{q['non_manifold_edges']} non-manifold edges", q["non_manifold_edges"] > 0))
                if bad]
        ex.log.append(f"  {pn} quality: error p50/p99/max {q['err_mm_p50']}/{q['err_mm_p99']}/{q['err_mm_max']} mm, "
                   f"{q['slivers']} slivers, {q['open_edges']} open edges"
                   + (f" ({q['inside_mouth']} of the folds / turned faces are inside the mouth)" if q.get("inside_mouth") else "")
                   + (f": WARNING {'; '.join(warn)}" if warn else ""))


def _bake(ex):
    """The bake: atlas names, the skin's recipe, the face's kept paint, the scene's maps, every atlas baked and written."""
    for ai, an in enumerate(ex.names):
        fill_a = sum(ex.tsz[pn]["uv_fill"] for pn, p in ex.parts.items() if p["atlas"] == ai)
        short = ""
        if ex.texel_density:
            got = min(1000 / r["mm_per_texel"] / (ex.rel[pn] / ex.texel_density) for pn, r in ex.report.items()
                      if r["atlas"] == an)
            short = f" (below the {ex.texel_density:g}/m asked: {got:.0f}/m)" if got < 0.9 * ex.texel_density else ""
        ex.log.append(f"atlas {an}: {ex.sizes[ai]}^2, {fill_a:.0%} filled{short}; " + ", ".join(
            f"{pn} {r['triangles']} tris {r['mm_per_texel']:.1f} mm/texel"
            + (f" (focus {', '.join(f'{v:.1f}' for v in r['focus_mm_per_texel'])})" if "focus_mm_per_texel" in r else "")
            for pn, r in ex.report.items() if r["atlas"] == an))
    ex.atlas_files, ex.maps_info, ex.heights, ex.cover = [], {}, {}, {}
    ex.skin_recipe = None
    if ex.spec.get("skin"):
        # (r65, coordinator) the skin's micro detail (pores, cells, lines, the lip lines) is BAKED into the part's own
        # maps: as tiling maps in the shading json alone, neither plain glTF viewers nor blender_game apply them, and
        # the lower lip shipped as one smooth, unbroken highlight (game_ready.md r64). The tiling maps still ship, as
        # an optional close-up extra (normal only: their tint / roughness are in the maps already).
        from . import skin_build
        ex.skin_recipe = skin_build.export_recipe(ex.spec, ex.out_dir, ex.name, baked=asset.BAKE_SKIN_DETAIL)
        ex.ctx["bake_detail"] = asset.BAKE_SKIN_DETAIL or not (ex.skin_recipe and ex.skin_recipe["detail"])
        if ex.skin_recipe and ex.skin_recipe["detail"]:
            ex.log.append("skin: micro detail " + ("baked into the part's maps; also written as tiling normal maps (close-up "
                       "extra, normal only) (" if asset.BAKE_SKIN_DETAIL else "left out of the baked maps and written as "
                       "tiling normal maps (") + ", ".join(d["normal"] for d in ex.skin_recipe["detail"]) + "): the recipe "
                       "is in the json and the skin material's extras")
    if ex.face_shapes and getattr(ex.fface, "gnm_mouth", False):  # the lips' inner rolls: hidden in the closed scene,
        inner_paint(ex.parts, ex.topo, ex.fface.head, ex.log)            # painted on the low poly's own triangles
    face_keep_paint(ex.parts, ex.topo, ex.log)
    if ex.spec.get("skin"):
        ex.ctx["lip_floor"] = (ex.spec, (ex.spec.get("skin") or {}).get("part", "body"))
    # (s14) the finest texel any part bakes at: the bake prefilters paint images finer than its sample spacing
    ex.ctx["texel_m"] = min((min([r["mm_per_texel"]] + list(r.get("focus_mm_per_texel") or [])) for r in ex.report.values()
                          if r.get("mm_per_texel")), default=0.0) / 1000.0
    from . import asset_recolour
    ex.ctx["recolour"] = asset_recolour.resolve(ex.recolour_masks, ex.parts, ex.origin)
    ex.recolour = None
    given = scene_maps(ex.name, ex.parts, ex.sizes, ex.ctx, ex.resolution, ex.log)
    ek_ = (ex.spec.get("base") or {}).get("eyes")
    ex.ctx["ao_off"] = [ek_] if isinstance(ek_, str) else []
    fo_ = ((ex.spec.get("hair") or {}).get("export") or {}).get("fade")
    if fo_:  # (sh8) hair.export.fade: the same map the hair export writes (hair_fade.build is deterministic per seed)
        from . import hair as hairmod_, hair_fade
        from . import hair_export, hair_head
        ex.ctx["skin_fade"] = {"map": hair_fade.build(hair_head.scalp(ex.name, ex.spec), fo_),
                            "part": (ex.spec.get("skin") or {}).get("part", "body")}
        ex.log.append(f"hair fade: {ex.ctx['skin_fade']['map']['hairs']} cut hairs, baked into {ex.ctx['skin_fade']['part']}")
    for ai, an in enumerate(ex.names):
        stem = ex.aname if len(ex.names) == 1 else f"{ex.aname}_{an}"
        if len(ex.names) > 1:
            ex.log.append(f"atlas {an}:")
        res = bake(ex.parts, ex.sizes[ai], ex.ctx, ex.log, ai, given[ai])
        maps = res["maps"]
        for pn, sh in res.get("lip_astray", {}).items():
            ex.report[pn]["lip_astray"] = {"share": round(sh, 4), "warn": sh > asset.LIP_ASTRAY_WARN}
        for pn, p in ex.parts.items():  # seams: does the baked colour run on across each chart border? (~1 = yes)
            if p["atlas"] == ai:
                st = {k: seam_steps(p, maps[k]) for k in ("basecolor", "orm")}
                ex.report[pn]["seams"] = st
                if st["basecolor"]:
                    b = st["basecolor"]
                    ex.log.append(f"  {pn} seams: {b['edges']} edges, colour step across / beside {b['excess']} (p95 "
                               f"{b['p95']}), orm {st['orm']['excess']}"
                               + (": WARNING, the maps step at chart borders" if b["excess"] > asset.SEAM_LIMIT else ""))
        files = {}
        for key in ("basecolor", "normal", "orm", "roughness", "metallic", "specular", "ao"):
            files[key] = ex.out_dir / f"{stem}_{key}.png"
            _png(files[key], maps[key])
        files["height"] = ex.out_dir / f"{stem}_height.png"
        _png(files["height"], maps["height"], bits=16)
        for k_ in range(len(ex.ctx["recolour"]["groups"]) if "recolour" in res else 0):  # linear RGBA channel masks
            files[f"mask{k_}"] = ex.out_dir / f"{stem}_mask{k_}.png"
            _png(files[f"mask{k_}"], maps[f"mask{k_}"])
        if "recolour" in res:
            ex.recolour = {"atlas": an, "material": f"{ex.aname}_{an}", "base_white": asset.RECOLOUR_BASE_WHITE,
                           "masks": [files[f"mask{k_}"].name for k_ in range(len(ex.ctx["recolour"]["groups"]))],
                           "channels": res["recolour"], "formula": asset_recolour.formula()}
        if "blink" in maps:   # the minimal wrinkle map: basecolor x lerp(1, blink, 1 - eyeBlink)
            files["blink"] = ex.out_dir / f"{stem}_blink_multiply.png"
            _png(files["blink"], maps["blink"])
            ex.log.append(f"  {stem}_blink_multiply.png: the crease line + lid occlusion, NOT in basecolor; engine: "
                       "basecolor x lerp(1, map, 1 - eyeBlink) (eyeBlink = the ARKit morph weight; open eye = full)")
        # glTF reads specular from the alpha channel of its texture
        spec_rgba = ex.out_dir / f"{stem}_specular_gltf.png"
        a = (np.clip(maps["specular"][..., 0], 0, 1) * 255 + 0.5).astype(np.uint8)
        Image.fromarray(np.stack([np.full_like(a, 255)] * 3 + [a], -1), "RGBA").save(spec_rgba)
        ex.atlas_files.append((an, {"basecolor": files["basecolor"], "orm": files["orm"], "normal": files["normal"],
                                 "specular": spec_rgba}))
        ex.maps_info[an] = {k: str(v) for k, v in files.items()}
        ex.heights[an] = res["height_range"]
        ex.cover[an] = res["coverage"]
