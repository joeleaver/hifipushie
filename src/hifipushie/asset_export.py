"""`_export`: the export itself (one function), and `preview`. Part of the game-ready export (asset.py has the overview)."""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image

from . import asset
from . import render, sdf, store
from .asset_bake import bake, face_keep_paint, inner_paint
from .asset_budget import _blender, budget_check, game, lash_cap
from .asset_gates import approved_head, decimate_cloth, game_light_view, hair_tier_default
from .asset_glb import _garment_stack, _head_share, _trs, garment_over, head_body_meshes, texel_sizes, write_glb
from .asset_hidden import (
    _over_chain, cloth_under_keep, cull_exposed_keep, cull_tris, cull_under_garments, garment_cull_masks,
    hide_export_part, own_mouth_meshes, prune_hidden, skin_pose_exposed, under_cloth_keep,
)
from .asset_parts import (
    _Log, _max_triangles, _min_triangles, _weight, atlas_groups, decal_focus, focus_regions, lowpoly, part_areas,
    planar_uvs, texture_loads,
)
from .asset_quality import _designed_interior, defect_regions, mesh_quality, seam_steps
from .asset_raster import _png
from .asset_scene import scene_maps, write_fbx
from .asset_split import _pow2, density_groups, mesh_parts, split, split_big, topology_parts

def _export(name: str, out_dir: Path, triangles: int | None = None, texture: int = 2048, resolution: int = 256,
            atlases: int = 1, texel_density: float | None = None, instancing: bool = True, rig: bool | dict = False,
            fbx: bool = False, face_shapes: bool | list | None = None, asset_name: str | None = None,
            lods: bool | list | None = None, cloth_triangles: int | None = None,
            cull_under_cloth: bool = True, role: str | None = None, correctives: bool = True,
            cull_poses: list | str | None = None) -> dict:
    """Build, decimate + unwrap, bake every map, write PNGs, <name>.glb and <name>.json into out_dir.
    asset_name: what the files, nodes, meshes and materials are called (default: the model's name): an engine's
    importer and tools key on them (s0urc3's Garrett is model rg_garrett, asset "garrett": garrett_body, ...).
    Per part (spec["parts"][p]): "triangle_weight" and "texel_density" (relative, default 1) scale its share of
    the triangles and its texels per metre; "atlas" (any name) puts it on an atlas of its own; "uv": "planar" gives
    a swappable flat surface (a dial, a sign, a screen) its own material and upright 0..1 planar UVs.
    texel_density (texels per metre): atlases are opened as needed to give every part that (x its own weight) at
    most `texture`^2 each, each atlas the smallest power of two that holds its parts. Without it, `atlases` (n)
    atlases of `texture`^2 split the parts by load.
    instancing: prefabs with 2+ instances are one mesh and one set of texels, placed by a node per instance
    (prefabs.<p>.export = "unique" bakes a prefab's instances into the scene instead). `triangles` counts the
    triangles drawn (a prefab's once per instance); the file holds fewer. With instancing every instance is a
    movable asset (a prefab of one instance too), as in the Blender scene. The paint and AO maps are baked by
    Cycles from the model's Blender scene (`scene_maps`; AO is each asset's own, as an engine expects).
    face_shapes: True (every ARKit shape faceshapes.py makes) or a list of names: morph targets on the parts that
    move with the face (faceshapes_apply.apply), the neutral's mouth closed; listed per part in the json.
    lods: True (lods.LOD_RATIOS) or a list of shares of LOD0's triangles: <asset>_LOD<k>.glb beside the GLB, the same
    skeleton, weights, face shapes and atlas (they reference LOD0's maps by file name); hair cards by whole layers.
    cloth_triangles: the simulated garments together decimated to this many triangles (their sim mesh, two-sided, is
    10-40k each: Tess's jeans 38k, sweater 28k); None keeps the sim mesh. cull_under_cloth: the skin (and shells on
    it without a garment fit, socks) the garments cover is left out (under_cloth_keep), a rim kept at the openings."""
    log = _Log(name)
    t = time.time()
    rb = None
    if role:  # the budgets profile (budgets.json, docs/notes/budgets.md): what this role may cost; explicit arguments win
        from . import budgets as budgetmod
        rb = budgetmod.role(role)
        bp_ = rb["parts"]
        if triangles is None:  # what the joint decimation spends: the body (head + body meshes) and the small parts
            triangles = sum(int(bp_[k]["default"]) for k in ("head", "body", "eyes_mouth_lashes", "accessories") if k in bp_)
        if cloth_triangles is None and "clothing" in bp_:
            cloth_triangles = int(bp_["clothing"]["default"])
        texture = min(texture, int((rb.get("textures") or {}).get("max_map", texture)))
        if texel_density is None:  # atlases sized by the role's texel density (the face's higher density is the
            # model's parts.<skin>.texel_focus; separate head / body texture SETS need the native head unwrapped as its
            # own part: not built, the two meshes share one atlas)
            texel_density = float(((rb.get("textures") or {}).get("texel_density_px_per_m") or {}).get("body", 1024))
        if lods is None:
            lods = True
        log.append(f"budgets: role {role!r}: triangles {triangles} (head + body + eyes/mouth/lashes + accessories), "
                   f"clothing {cloth_triangles}, maps <= {texture}, LOD0 total {rb['lod0_triangles']['default']}")
    if triangles is None:
        triangles = 15000
        log.append("WARNING budgets: no role given and no triangles: 15000 (not a stated budget; pass role=)")
    spec = store.load(name)
    from . import skin_route
    skin_route.refuse_photo_skin(spec)
    if (spec.get("base") or {}).get("head_approved"):  # (Garrett s7) the head geometry must BE the approved head's: a
        # gate, not a swap (geometry is built from the stored model); compose the spec with approved_head first
        lg_ = []
        ah_ = approved_head(spec, lg_)
        h_ = ah_["base"]["head"]
        if h_ != spec["base"].get("head"):
            raise ValueError(f"{name}: base.head is not the approved head ({lg_[0]}): write approved_head(spec)'s "
                             "head into the model first")
        if (ah_.get("skin") or {}).get("folds") != (spec.get("skin") or {}).get("folds"):  # (s8: folds that change form)
            raise ValueError(f"{name}: skin.folds change the head's form ({'; '.join(m for m in lg_ if 'WARNING' in m)}): "
                             "write approved_head(spec)'s skin.folds into the model first")
        if (ah_.get("skin") or {}).get("stack") != (spec.get("skin") or {}).get("stack"):  # (r63) this gate's result
            # is not what ships (textures come from the stored model): the lid layers re-baked by stack_on_head must be
            # IN the model, or the blink map / lid shading of the lid_fold head ships (Tess rc2o did exactly that)
            raise ValueError(f"{name}: skin.stack was measured on another head "
                             f"({'; '.join(m for m in lg_ if m.startswith('skin stack'))}): write approved_head(spec)'s "
                             "skin.stack into the model first")
        log.append(f"head: = the approved head {spec['base']['head_approved']} (checked)")
        for m_ in lg_:  # (append: the export log prints on append, not extend)
            if "skin.folds" in m_:
                log.append(m_)
    aname = asset_name or name
    from .base_implied import part_defs
    defs = part_defs(spec)  # (the base's implied parts too: a clear cornea's lens)
    fine, tri_focus, rest_w = {}, [], {}
    if face_shapes:  # say now, not after the bake, that the face can't take them; mesh the slit open; keep
        # triangles at the lids and lips
        from . import faceshapes_apply
        from .spec import SpecError
        faceshapes_apply.names_of(face_shapes)
        fface = faceshapes_apply.face_of(spec)
        from . import facepose
        rest_w = facepose.rest_of(spec)  # face_shapes.rest: carried as the meshes' default weights, not baked
        if set(rest_w) - set(faceshapes_apply.names_of(face_shapes)):
            raise SpecError(f"face_shapes.rest uses {sorted(set(rest_w) - set(faceshapes_apply.names_of(face_shapes)))}, "
                            "which this export's face_shapes leave out")
        fine, tri_focus = fface.voxels(), fface.tri_focus()
    out_dir.mkdir(parents=True, exist_ok=True)
    ctx = split(spec, resolution, instancing, log, min_share=1, voxels=fine)
    if rig:  # parts bound to a joint of their own (parts.<p>.rig_bone) move apart from the rest: what they cover
        # at rest is seen in a pose (the golfer's shorts had a hole where the hip bag sat, shown by a lifted thigh)
        ctx["apart"] = {pn: (defs.get(ctx["origin"][pn]) or {}).get("rig_bone") for pn in ctx["streams"]}
    for pn, v in fine.items():
        if ctx["frames"].get(pn) and ctx["frames"][pn][1] <= v:
            log.append(f"{pn}: meshed at {ctx['frames'][pn][1] * 1000:.2f} mm for the face shapes (the lips' slit, teeth)")
    origin = ctx["origin"]
    tm = time.time()
    high = mesh_parts(ctx, out_dir / "high.npz")
    log.append(f"meshed {len(ctx['streams'])} parts in {time.time() - tm:.1f}s (scene voxel {ctx['voxel'] * 1000:.1f} mm)")
    own_surface = None
    if face_shapes and getattr(fface, "gnm_mouth", False):  # GNM's own teeth and tongue lie behind the closed lips
        from . import base_gnm_parts
        from . import base
        mp = base_gnm_parts.gnm_mouth(fface.head)
        pts = {k: base_gnm_parts._piece_points(mp[k]["verts"], mp[k]["faces"])["verts"] for k in ("teeth_upper", "teeth_lower", "tongue")}
        own_surface = {base.TEETH_PARTS[0]: pts["teeth_upper"], base.TEETH_PARTS[1]: pts["teeth_lower"],
                       "tongue": pts["tongue"]}
        own_mouth_meshes(high, mp, log)
        # (their own vertices ARE the surface: every face kept, whatever covers the rows in the neutral)
        own_surface.update({base.TEETH_PARTS[0]: np.asarray(mp["teeth_upper"]["verts"], float),
                            base.TEETH_PARTS[1]: np.asarray(mp["teeth_lower"]["verts"], float),
                            "tongue": np.asarray(mp["tongue"]["verts"], float)})
    prune_hidden(ctx, high, log, own_surface)
    if texel_density:
        split_big(high, ctx, {pn: _weight(defs, origin[pn], "texel_density") * texel_density for pn in ctx["streams"]},
                  texture, log)
    areas = part_areas(high)

    def w(pn, key):
        return _weight(defs, origin[pn], key)
    focus = {pn: focus_regions(spec, origin[pn]) for pn in areas}
    # image decals keep their own resolution: their density relative to the part's (asked, or what an atlas of
    # `texture` holds over every part). A prefab's part (or a split slab) takes the decals reaching its own mesh: it
    # is unwrapped where its bake instance stands, as the scene paints it
    guess = texture * np.sqrt(asset.FILL / max(sum(areas.values()), 1e-9))
    with np.load(high) as z:
        hv, hp, hnames = z["verts"], z["part"], [str(n) for n in z["part_names"]]
    for pn in areas:
        box = None
        if pn != origin[pn] and pn in hnames:
            pv = hv[hp == hnames.index(pn)]
            box = (pv.min(0) - 0.01, pv.max(0) + 0.01) if len(pv) else None
        if pn == origin[pn] or box is not None:
            dec = decal_focus(spec, origin[pn], w(pn, "texel_density") * (texel_density or guess), box)
            if dec:
                focus[pn] = focus[pn] + dec
                log.append(f"{pn}: texel focus over {len(dec)} image decal(s), x{', x'.join(f'{d[4]:.1f}' for d in dec)}")
    rel ={pn: w(pn, "texel_density") * (texel_density or 1.0) for pn in areas}
    loads = texture_loads(high, rel, focus)
    fixed = {pn: str(defs[origin[pn]]["atlas"]) for pn in areas if (defs.get(origin[pn]) or {}).get("atlas") is not None}
    # parts.<p>.uv = "planar": a swappable surface (a clock's dial, a sign, a screen) gets its own material and 0..1
    # planar UVs, so an engine swaps its texture by one property (s0urc3: the dial needed a custom UV shader)
    planar = {pn for pn in areas if (defs.get(origin[pn]) or {}).get("uv") == "planar"}
    for pn in planar:
        fixed.setdefault(pn, f"planar_{pn}")
    pf_of = {pn: pf for pf, d in ctx["prefabs"].items() for pn in d["parts"]}
    units: dict[str, list] = {}
    for pn in areas:  # a prefab's parts go on one atlas together (one material per instance where possible)
        units.setdefault(pf_of.get(pn, pn), []).append(pn)
    if texel_density:  # say now, not after the bake, which parts can't get the density asked for (a prefab too
        # big for an atlas: scene parts were split above)
        for u, pns in units.items():
            need = sum(loads[pn] for pn in pns)
            cap = texture ** 2 * asset.FILL
            if need > cap:
                got = texel_density * np.sqrt(cap / need)
                area = sum(loads[pn] / rel[pn] ** 2 for pn in pns)
                log.append(f"{u}: {area:.0f} m^2 of surface wants {np.sqrt(need / asset.FILL):.0f}^2 texels at "
                           f"{texel_density:g}/m, more than one {texture}^2 atlas holds: expect ~{got:.0f}/m "
                           f"(split it into parts, raise texture, or give it a lower texel_density)")
    topo = topology_parts(spec, ctx, out_dir, log, high)
    fill = asset.FILL
    for attempt in range(2):
        group = density_groups(units, loads, fixed, texture, fill) if texel_density else atlas_groups(
            loads, fixed, atlases)
        names = sorted(set(group.values()), key=lambda g: (not g.isdigit(), int(g) if g.isdigit() else 0, g))
        sizes = {ai: min(texture, _pow2(np.sqrt(sum(loads[pn] for pn in areas if group[pn] == an) / fill)))
                 if texel_density else texture for ai, an in enumerate(names)}
        cfg = {pn: {"weight": w(pn, "triangle_weight"), "density": w(pn, "texel_density"),
                    "atlas": names.index(group[pn]), "focus": focus[pn], "split": pn in ctx.get("split", {}),
                    "copies": len(ctx["prefabs"][pf_of[pn]]["instances"]) if pn in pf_of else 1,
                    **({} if _min_triangles(defs, origin[pn]) is None else  # (absent: cached decimations stay valid)
                       {"min": _min_triangles(defs, origin[pn])}),
                    **({} if _max_triangles(defs, origin[pn]) is None else {"max": _max_triangles(defs, origin[pn])}),
                    **({"fixed": topo[pn][0], "fixed_sum": topo[pn][1]} if pn in topo else {})} for pn in areas}
        t1 = time.time()
        from . import lashes as _lashes  # the lash ribbons come out of the same budget (their own count, fixed)
        lash_tris = _lashes.triangles(spec)
        if lash_tris:
            log.append(f"lashes: {lash_tris} triangles of the {triangles} budget")
        parts, binfo = lowpoly(high, out_dir / "lowpoly.npz", cfg, max(triangles - lash_tris, triangles // 2), sizes,
                               ctx["voxel"], tri_focus)
        for pn in planar & set(parts):
            parts[pn].update(planar_uvs(parts[pn]))
            log.append(f"{pn}: own material, planar 0..1 UVs (uv: planar)")
        if not texel_density:
            break
        # the size each atlas needs for every part to get its density, now that it's packed
        ts = texel_sizes(parts, sizes, {pn: focus.get(pn) or [] for pn in parts})

        def needs(pn, ai):  # the part's own density, and each focus region's (a decal covering a whole mug: the
            # part's average is the focus's, and sizing the atlas by it alone dropped the focus)
            yield sizes[ai] * ts[pn]["mm_per_texel"] * rel[pn] / 1000
            for f, mm in zip(focus.get(pn) or [], ts[pn].get("focus_mm_per_texel") or []):
                if mm > 0:  # (0: no face of this part in the region)
                    yield sizes[ai] * mm * rel[pn] * f[4] / 1000
        need = {ai: max(x for pn, p in parts.items() if p["atlas"] == ai for x in needs(pn, ai))
                for ai in range(len(names))}
        over = [ai for ai in need if need[ai] > 1.05 * texture and len({pf_of.get(pn, pn) for pn, p in parts.items()
                                                                         if p["atlas"] == ai}) > 1]
        if over and attempt == 0:
            fill = 0.95 * min(sum(ts[pn]["uv_fill"] for pn, p in parts.items() if p["atlas"] == ai) for ai in over)
            log.append(f"atlases {[names[ai] for ai in over]} came out too full for {texel_density:g} texels/m at "
                       f"{texture}: regrouping for a pack fill of {fill:.0%}")
            continue
        sizes = {ai: min(texture, _pow2(0.97 * need[ai])) for ai in need}
        break
    hid_tris = {pn: hide_export_part(ctx, pn, parts[pn], log) for pn in parts}  # (parts.<p>.hides: also after a
    # template wrap or a decimation, which bring back what the high mesh had already lost)
    ntri = sum(len(p["corner_vert"]) // 3 for p in parts.values())
    log.append(f"low poly: {ntri} triangles in the file in {time.time() - t1:.1f}s (joint decimation {binfo['joint_s']:.1f}s, "
               f"per-part {binfo['decimate_s'] - binfo['joint_s']:.1f}s, unwrap + pack {binfo['unwrap_s']:.1f}s)")
    tsz = texel_sizes(parts, sizes, {pn: focus[pn] for pn in parts})
    report = {}
    for pn, p in parts.items():
        b = binfo["parts"][pn]
        report[pn] = {"triangles": len(p["corner_vert"]) // 3, "atlas": names[p["atlas"]],
                      "mm_per_texel": round(tsz[pn]["mm_per_texel"], 2), "area_m2": round(tsz[pn]["area_m2"], 3),
                      "islands": b.get("islands"), "joint_decimation_share": b["joint_count"],
                      "mirrored": b["symmetric"], "texel_density": cfg[pn]["density"],
                      "triangle_weight": cfg[pn]["weight"],
                      **({"uv": "planar", "material": f"{aname}_{names[p['atlas']]}_material"} if pn in planar else {})}
        if pn in pf_of:
            report[pn]["prefab"] = pf_of[pn]
        if hid_tris.get(pn):
            report[pn]["hidden_dropped"] = hid_tris[pn]
        if "focus_mm_per_texel" in tsz[pn]:
            report[pn]["focus_mm_per_texel"] = tsz[pn]["focus_mm_per_texel"]
        des = _designed_interior(topo.get(pn), p["verts"], lid_fold=((spec.get("base") or {}).get("head") or {}).get("lid_fold"))
        if des is not None:  # (bake: the interior's texels keep the low poly's own surface)
            p["designed"] = _designed_interior(topo.get(pn), p["verts"], creases=False)
        q = mesh_quality(p["verts"], p["corner_vert"].reshape(-1, 3), ctx["streams"][pn], designed=des)
        spots = q.pop("spots")
        for other, st in ctx["streams"].items():  # what lies inside another part is never seen (the skin running
            if other != pn and len(spots):       # on into the socket behind an eyeball, a tooth's root)
                spots = spots[sdf.field_at(st, spots, clip=False) > 0]
        if face_shapes and len(spots) and ctx["origin"][pn] == fface.slit_part:
            # the mouth's interior (slit walls, the bag's corners) folds at a game budget and is behind the lips:
            # counted, not part of the tear alarm (Garrett's bag read "TORN OR TANGLED at eye_front.L (12)")
            inm = fface.inside_mouth(spots, ctx["streams"][pn])
            if inm.any():
                q["inside_mouth"] = int(inm.sum())
                spots = spots[~inm]
        where = defect_regions(spots, spec)
        if (defs.get(ctx["origin"][pn]) or {}).get("folds"):  # parts.<p>.folds = true: folded by design (a turned
            where = []                                         # collar, a cuff, pleats): counts stay, no alarm
        if where:
            q["defects_by_joint"] = dict(where)
        report[pn]["quality"] = q
        vx_mm = ctx["frames"][pn][1] * 1000
        warn = [w for w, bad in ((f"p99 {q['err_mm_p99']:.1f} mm from the surface (> 4 voxels: bridged gaps or "
                                  f"cut corners; raise its triangle_weight)", q["err_mm_p99"] > 4 * vx_mm),
                                 (f"{q['folds']} folded edges", q["folds"] > 0),
                                 (f"{q.get('turned', 0)} faces turned against the surface", q.get("turned", 0) > 0),
                                 ("TORN OR TANGLED at " + ", ".join(f"{j} ({k})" for j, k in where[:4])
                                  + ": folded edges / turned faces in a cluster; look at it in clay "
                                    "(rig(glb=..., focus=...)) before shipping", bool(where)),
                                 (f"{q['non_manifold_edges']} non-manifold edges", q["non_manifold_edges"] > 0))
                if bad]
        log.append(f"  {pn} quality: error p50/p99/max {q['err_mm_p50']}/{q['err_mm_p99']}/{q['err_mm_max']} mm, "
                   f"{q['slivers']} slivers, {q['open_edges']} open edges"
                   + (f" ({q['inside_mouth']} of the folds / turned faces are inside the mouth)" if q.get("inside_mouth") else "")
                   + (f": WARNING {'; '.join(warn)}" if warn else ""))
    for ai, an in enumerate(names):
        fill_a = sum(tsz[pn]["uv_fill"] for pn, p in parts.items() if p["atlas"] == ai)
        short = ""
        if texel_density:
            got = min(1000 / r["mm_per_texel"] / (rel[pn] / texel_density) for pn, r in report.items()
                      if r["atlas"] == an)
            short = f" (below the {texel_density:g}/m asked: {got:.0f}/m)" if got < 0.9 * texel_density else ""
        log.append(f"atlas {an}: {sizes[ai]}^2, {fill_a:.0%} filled{short}; " + ", ".join(
            f"{pn} {r['triangles']} tris {r['mm_per_texel']:.1f} mm/texel"
            + (f" (focus {', '.join(f'{v:.1f}' for v in r['focus_mm_per_texel'])})" if "focus_mm_per_texel" in r else "")
            for pn, r in report.items() if r["atlas"] == an))
    atlas_files, maps_info, heights, cover = [], {}, {}, {}
    skin_recipe = None
    if spec.get("skin"):
        # (r65, coordinator) the skin's micro detail (pores, cells, lines, the lip lines) is BAKED into the part's own
        # maps: as tiling maps in the shading json alone, neither plain glTF viewers nor blender_game apply them, and
        # the lower lip shipped as one smooth, unbroken highlight (game_ready.md r64). The tiling maps still ship, as
        # an optional close-up extra (normal only: their tint / roughness are in the maps already).
        from . import skin_build
        skin_recipe = skin_build.export_recipe(spec, out_dir, name, baked=asset.BAKE_SKIN_DETAIL)
        ctx["bake_detail"] = asset.BAKE_SKIN_DETAIL or not (skin_recipe and skin_recipe["detail"])
        if skin_recipe and skin_recipe["detail"]:
            log.append("skin: micro detail " + ("baked into the part's maps; also written as tiling normal maps (close-up "
                       "extra, normal only) (" if asset.BAKE_SKIN_DETAIL else "left out of the baked maps and written as "
                       "tiling normal maps (") + ", ".join(d["normal"] for d in skin_recipe["detail"]) + "): the recipe "
                       "is in the json and the skin material's extras")
    if face_shapes and getattr(fface, "gnm_mouth", False):  # the lips' inner rolls: hidden in the closed scene,
        inner_paint(parts, topo, fface.head, log)            # painted on the low poly's own triangles
    face_keep_paint(parts, topo, log)
    if spec.get("skin"):
        ctx["lip_floor"] = (spec, (spec.get("skin") or {}).get("part", "body"))
    # (s14) the finest texel any part bakes at: the bake prefilters paint images finer than its sample spacing
    ctx["texel_m"] = min((min([r["mm_per_texel"]] + list(r.get("focus_mm_per_texel") or [])) for r in report.values()
                          if r.get("mm_per_texel")), default=0.0) / 1000.0
    given = scene_maps(name, parts, sizes, ctx, resolution, log)
    ek_ = (spec.get("base") or {}).get("eyes")
    ctx["ao_off"] = [ek_] if isinstance(ek_, str) else []
    fo_ = ((spec.get("hair") or {}).get("export") or {}).get("fade")
    if fo_:  # (sh8) hair.export.fade: the same map the hair export writes (hair_fade.build is deterministic per seed)
        from . import hair as hairmod_, hair_fade
        from . import hair_export, hair_head
        ctx["skin_fade"] = {"map": hair_fade.build(hair_head.scalp(name, spec), fo_),
                            "part": (spec.get("skin") or {}).get("part", "body")}
        log.append(f"hair fade: {ctx['skin_fade']['map']['hairs']} cut hairs, baked into {ctx['skin_fade']['part']}")
    for ai, an in enumerate(names):
        stem = aname if len(names) == 1 else f"{aname}_{an}"
        if len(names) > 1:
            log.append(f"atlas {an}:")
        res = bake(parts, sizes[ai], ctx, log, ai, given[ai])
        maps = res["maps"]
        for pn, sh in res.get("lip_astray", {}).items():
            report[pn]["lip_astray"] = {"share": round(sh, 4), "warn": sh > asset.LIP_ASTRAY_WARN}
        for pn, p in parts.items():  # seams: does the baked colour run on across each chart border? (~1 = yes)
            if p["atlas"] == ai:
                st = {k: seam_steps(p, maps[k]) for k in ("basecolor", "orm")}
                report[pn]["seams"] = st
                if st["basecolor"]:
                    b = st["basecolor"]
                    log.append(f"  {pn} seams: {b['edges']} edges, colour step across / beside {b['excess']} (p95 "
                               f"{b['p95']}), orm {st['orm']['excess']}"
                               + (": WARNING, the maps step at chart borders" if b["excess"] > asset.SEAM_LIMIT else ""))
        files = {}
        for key in ("basecolor", "normal", "orm", "roughness", "metallic", "specular", "ao"):
            files[key] = out_dir / f"{stem}_{key}.png"
            _png(files[key], maps[key])
        files["height"] = out_dir / f"{stem}_height.png"
        _png(files["height"], maps["height"], bits=16)
        if "blink" in maps:   # the minimal wrinkle map: basecolor x lerp(1, blink, 1 - eyeBlink)
            files["blink"] = out_dir / f"{stem}_blink_multiply.png"
            _png(files["blink"], maps["blink"])
            log.append(f"  {stem}_blink_multiply.png: the crease line + lid occlusion, NOT in basecolor; engine: "
                       "basecolor x lerp(1, map, 1 - eyeBlink) (eyeBlink = the ARKit morph weight; open eye = full)")
        # glTF reads specular from the alpha channel of its texture
        spec_rgba = out_dir / f"{stem}_specular_gltf.png"
        a = (np.clip(maps["specular"][..., 0], 0, 1) * 255 + 0.5).astype(np.uint8)
        Image.fromarray(np.stack([np.full_like(a, 255)] * 3 + [a], -1), "RGBA").save(spec_rgba)
        atlas_files.append((an, {"basecolor": files["basecolor"], "orm": files["orm"], "normal": files["normal"],
                                 "specular": spec_rgba}))
        maps_info[an] = {k: str(v) for k, v in files.items()}
        heights[an] = res["height_range"]
        cover[an] = res["coverage"]
    extra_ext = {}
    if (spec.get("hair") or {}).get("locks"):  # curve locks (hair.py): meshed and baked in Blender, their own atlas
        from . import hair as hairmod
        from . import hair_export, hair_head
        spec = hair_tier_default(spec, role, log)
        from . import hair_route
        hw_ = hair_route.head_warning(name, spec)
        if hw_:
            log.append(hw_)
        hp = hair_export.export_part(name, out_dir, spec, texture=min(texture, 2048), log=log)
        if hp is not None:
            hpart, hfiles = hp
            pn_h = (spec["hair"].get("part") or "hair")
            hpart["atlas"] = len(atlas_files)
            parts[pn_h] = hpart
            origin[pn_h] = pn_h
            atlas_files.append((pn_h, hfiles))
            maps_info[pn_h] = {k: str(v) for k, v in hfiles.items()}
            heights[pn_h], cover[pn_h] = 0.0, 1.0
            report[pn_h] = {"triangles": len(hpart["corner_vert"]) // 3, "atlas": pn_h, "curves": True}
            hair_cards = hpart.pop("hair", None)
            if hair_cards:
                k0 = sum(len(i_) for _, i_ in atlas_files[:-1])
                hair_cards["aux_texture"] = k0 + list(hfiles).index("aux")
                report[pn_h].update(cards=True, layers=hair_cards["layers"], budget=hair_cards["budget"],
                                    back_faces=bool(hair_cards.get("back_faces")), vertices=len(hpart["verts"]))
            names.append(pn_h)
            sizes[len(names) - 1] = min(texture, 2048)
            ntri += report[pn_h]["triangles"]
            # a lock's sheen runs along it (the uv's v): anisotropy turned 90 degrees from the tangent (u, round the
            # lens), and a soft warm sheen
            lk = hairmod.full_look(spec["hair"].get("look"))
            sheen = [round(float(c), 3) for c in hair_export.srgb_to_linear(lk["sheen"])]
            extra_ext[len(atlas_files) - 1] = {
                # (r59) half the specular, in the sheen's colour (hair.card_specular_tint): the default white x 2 mirrored
                # the key light off the crown's cards as a white plate (Tess rc2i, Garrett v5)
                # (no specular texture: the hair's is a flat 0.5; F0 = 0.04 x factor x colour = 0.02 x tint)
                "KHR_materials_specular": {"specularFactor": hairmod.CARD_SPECULAR,
                                           "specularColorFactor": hair_export.card_specular_tint(sheen)},
                "KHR_materials_anisotropy": {"anisotropyStrength": float(lk.get("anisotropic", 0.7)),
                                             "anisotropyRotation": 1.5708},
                "KHR_materials_sheen": {"sheenColorFactor": sheen, "sheenRoughnessFactor": 0.35}}
    chain_w, chain_looks, left_out, chain_lods = {}, {}, [], {}
    if spec.get("cloth"):  # garments. A chain garment (one with a garment record) ships as export_garment wrote it at
        # step 10 (garment_asset, C434: the old route re-simulated its draft and shipped that); any other garment is
        # the old simulation's (cloth.py): its settled mesh, the flat pattern as the uv
        from . import cloth as clothmod
        from . import garment_asset
        chain = garment_asset.records(name, spec)
        gparts, chain_w, chain_looks, left_out, chain_lods = garment_asset.parts(name, chain, out_dir, log.append)
        for g_, why_ in left_out:
            log.append(f"NOT IN THIS EXPORT: garment {g_}: {why_}")
        old_ = {g_: v_ for g_, v_ in spec["cloth"].items() if g_ not in chain}
        cparts = clothmod.export_part(name, {**spec, "cloth": old_}, out_dir, texture=min(texture, 2048),
                                      log=log.append) if old_ else []
        n_c = sum(len(cp["corner_vert"]) // 3 for _, cp, _ in cparts)
        # (what covers the skin: the sim's own mesh before any decimation, and the chain garments as they ship)
        cover_by = [cp for _, cp, _ in cparts + gparts]
        if cloth_triangles and n_c > cloth_triangles:  # the sim's 1 cm mesh (two-sided) is far over a game budget:
            # decimated like a LOD (patches with their borders held: seams, hems, the pattern's uv)
            from . import lods as lodmod
            from . import lods_part, lods_under
            cparts = decimate_cloth(cparts, cloth_triangles, log)
        cparts = cparts + gparts  # (a chain garment's grid was already chosen for its role's budget: never decimated here)
        for pn_c, cpart, cfiles in cparts:
            cpart["atlas"] = len(atlas_files)
            parts[pn_c] = cpart
            origin[pn_c] = pn_c
            atlas_files.append((pn_c, cfiles))
            maps_info[pn_c] = {k: str(v) for k, v in cfiles.items()}
            heights[pn_c], cover[pn_c] = 0.0, 1.0
            report[pn_c] = {"triangles": len(cpart["corner_vert"]) // 3, "atlas": pn_c, "cloth": True}
            names.append(pn_c)
            sizes[len(names) - 1] = min(texture, 2048)
            ntri += report[pn_c]["triangles"]
        if cull_under_cloth and cparts:  # skin the garments cover: never seen, and a bent limb pokes it through
            cl = cover_by
            skin_pn = (spec.get("skin") or {}).get("part", "body")
            under = {skin_pn} | {p_ for p_, d_ in defs.items() if (d_ or {}).get("shell") == skin_pn
                                 and not (d_ or {}).get("garment")}  # (the skin and paint-like shells: socks)
            for pn in list(parts):
                if report.get(pn, {}).get("cloth") or report.get(pn, {}).get("curves") or pn in pf_of:
                    continue
                if origin.get(pn) not in under:
                    continue
                n0 = len(parts[pn]["corner_vert"]) // 3
                keep = under_cloth_keep(parts[pn], cl)
                if keep.all():
                    continue
                cm = np.repeat(keep, 3)
                for k_ in ("corner_vert", "uv", "normal", "tangent", "sign"):
                    parts[pn][k_] = parts[pn][k_][cm]
                report[pn]["triangles"] = int(keep.sum())
                report[pn]["under_cloth_dropped"] = int(n0 - keep.sum())
                ntri -= int(n0 - keep.sum())
                log.append(f"{pn}: {n0 - int(keep.sum())} of {n0} triangles under the garments dropped (covered "
                           f"within {asset.UNDER_CLOTH_REACH * 1000:.0f} mm along the normal, {asset.UNDER_CLOTH_RIM * 1000:.0f} mm "
                           "rim kept at every opening)")
            # (r53, coordinator) garment under garment: the faces of an under garment its covers hide (the same test,
            # reach and rim) are dropped at LOD0, so every LOD inherits it: rc2's jeans / sweater kept every triangle under
            # the coat, which cost budget and poked through at LOD1+
            cnames = [pn_c for pn_c, _, _ in cparts]
            over_ = garment_over(spec, log.append)
            for gn in over_:
                un = f"cloth_{gn}"
                ups = [f"cloth_{o_}" for o_ in over_ if gn in _over_chain(over_, o_)]
                cov = [cover_by[cnames.index(u_)] for u_ in ups if u_ in cnames]
                if un not in parts or not cov or not asset.CLOTH_UNDER_CULL:
                    continue
                n0 = len(parts[un]["corner_vert"]) // 3
                keep = cloth_under_keep(parts[un], cov)
                if keep.all():
                    continue
                if cull_poses:  # (r54) a face uncovered in ANY dumped clip frame is kept (cull_exposed_keep)
                    ups_ = [u_ for u_ in ups if u_ in parts]
                    keep, ex_ = cull_exposed_keep(parts[un], [parts[u_] for u_ in ups_], un, ups_, cull_poses, keep)
                    log.append(f"{un}: {ex_['restored']} culled triangles restored, exposed in a clip frame "
                               f"({ex_['frames']} frames; worst {ex_['worst']})")
                    report[un]["cull_exposed"] = ex_
                parts[un] = cull_tris(parts[un], keep)
                report[un]["triangles"] = int(keep.sum())
                report[un]["under_cloth_dropped"] = int(n0 - keep.sum())
                ntri -= int(n0 - keep.sum())
                log.append(f"{un}: {n0 - int(keep.sum())} of {n0} triangles under {', '.join(ups)} dropped (garment "
                           f"under garment, {asset.UNDER_CLOTH_RIM * 1000:.0f} mm rim kept at every opening)")
    from . import lashes as lashmod
    lash = lashmod.export_part(spec, out_dir, log=log.append)
    if lash:  # eyelash ribbons (lashes.py): their own mesh and tiny maps, two-sided; face shapes turn them with the lids
        pn_l, lpart, lfiles = lash
        cap_ = lash_cap(rb, report) if rb else None
        if cap_ is not None:  # the eyes / mouth / lashes budget: the lashes fit what eyes, teeth, tongue and brows leave
            from .lods_part import ribbon_fit
            lpart, linfo_ = ribbon_fit(lpart, cap_)
            if linfo_["triangles"] < linfo_["triangles0"]:
                log.append(f"lashes: {linfo_['triangles0']} -> {linfo_['triangles']} triangles ({linfo_['ribbons_kept']} of "
                           f"{linfo_['ribbons']} lashes, widened x{linfo_['widen']:.2f}) to fit eyes_mouth_lashes "
                           f"{int(rb['parts']['eyes_mouth_lashes']['default'])}")
        lpart["atlas"] = len(atlas_files)
        parts[pn_l] = lpart
        origin[pn_l] = pn_l
        atlas_files.append((pn_l, lfiles))
        maps_info[pn_l] = {k: str(v) for k, v in lfiles.items()}
        heights[pn_l], cover[pn_l] = 0.0, 1.0
        report[pn_l] = {"triangles": len(lpart["corner_vert"]) // 3, "atlas": pn_l, "lashes": True}
        names.append(pn_l)
        sizes[len(names) - 1] = 16
        ntri += report[pn_l]["triangles"]
    glb = out_dir / f"{aname}.glb"
    looks = {pn: {k: float(d[k]) for k in ("transmission", "alpha", "ior") if k in d}
             for pn in parts for d in [defs.get(origin[pn]) or {}] if any(k in d for k in ("transmission", "alpha"))}
    for pn, lk_ in chain_looks.items():  # (a chain garment's alpha-cut base map: frayed or lace edges)
        if pn in parts:
            looks.setdefault(pn, {}).update(lk_)
    if (spec.get("hair") or {}).get("locks") and locals().get("hair_cards"):
        looks.setdefault(pn_h, {}).update(alpha_cutoff=hair_cards["alpha_cutoff"],
                                          double_sided=not hair_cards.get("back_faces"),  # (c6: own back faces)
                                          extras={"hifipushie_hair": hair_cards})
    if skin_recipe:  # the skin part's own material: the film's second lobe and the sheen as ratified extensions, the
        sp = (spec.get("skin") or {}).get("part", "body")  # rest (scattering, tiling detail) in its extras
        for pn in parts:
            if origin[pn] == sp:
                looks.setdefault(pn, {}).update(
                    ext={"KHR_materials_clearcoat": {"clearcoatFactor": float(skin_recipe["specular"]["coat"]),
                                                     "clearcoatRoughnessFactor": float(skin_recipe["specular"]["coat_roughness"])},
                         "KHR_materials_sheen": {"sheenColorFactor": [float(skin_recipe["sheen"])] * 3, "sheenRoughnessFactor": 0.5}},
                    extras={"hifipushie_skin": skin_recipe})
    if lash:
        looks.setdefault(lash[0], {})["double_sided"] = True
    from .skin_features_eyes import eye_base
    ek = eye_base(spec)
    if ek:  # the eyes' tear film: a clear coat over the matte iris and sclera (the catchlight)
        for pn in parts:
            if origin.get(pn) == ek[0]:
                looks.setdefault(pn, {}).setdefault("ext", {})["KHR_materials_clearcoat"] = {
                    "clearcoatFactor": float(ek[1]["coat"]), "clearcoatRoughnessFactor": float(ek[1]["coat_roughness"])}
    rigged = None
    if rig:  # an armature from the skeleton, the parts (not prefabs) skinned to it
        from . import rig as rigmod
        from . import rig_bend, rig_head, rig_model, rig_report, rig_skin, rig_twist
        tr = time.time()
        rspec = spec
        if isinstance(rig, dict):  # export options over spec["rig"]: {"twist": ..., "rigid_head": ...}
            rspec = {**spec, "rig": {**(spec.get("rig") or {}), **rig}}
        bones = rig_report.rig_bones(rspec)
        skin_at = {pn: np.array(p["verts"], np.float64) for pn, p in parts.items() if pn not in pf_of}
        rigged = {"bones": bones, "weights": rig_skin.skin_parts(
            rspec, bones, {pn: (skin_at[pn], parts[pn]["corner_vert"].reshape(-1, 3)) for pn in skin_at}, smooth=3)}
        if chain_w:  # a chain garment keeps the weights its own export made and checked in the bend poses
            from . import garment_asset
            rigged["weights"].update(garment_asset.bone_weights({pn: w_ for pn, w_ in chain_w.items() if pn in parts},
                                                                bones))
        hf = rig_head.head_field(rspec, bones)
        ntw = sum(1 for b in bones if b.get("twist"))
        log.append(f"rig: {len(bones)} bones ({(spec.get('rig') or {}).get('type', 'humanoid')}, root "
                   f"{bones[0]['name']!r}; {ntw} twist bones after the base set), {len(rigged['weights'])} parts "
                   f"skinned, head rigid by {hf['how'] if hf else 'nothing (off, or no Head bone)'}, "
                   f"{time.time() - tr:.1f}s")
        from . import rig_template as _rt
        if _rt.weights_note(rspec):
            log.append(_rt.weights_note(rspec))
        from . import rig_audit as _ra
        sit = _ra.seated(bones)
        if sit and len(skin_at) > 1:  # do the layers stay in order when the character sits (rig_audit.layers)
            pn_s = list(skin_at)
            Vs = np.concatenate([skin_at[pn] for pn in pn_s])
            off = np.cumsum([0] + [len(skin_at[pn]) for pn in pn_s])
            Fs_ = np.concatenate([parts[pn]["corner_vert"].reshape(-1, 3) + off[i] for i, pn in enumerate(pn_s)])
            Js = np.concatenate([np.asarray(rigged["weights"][pn][0]) for pn in pn_s])
            Ws = np.concatenate([np.asarray(rigged["weights"][pn][1], np.float64) for pn in pn_s])
            rows = _ra.layers(Vs, Fs_, np.repeat(np.arange(len(pn_s)), np.diff(off)), pn_s,
                              rig_model.pose(bones, Vs, Js, Ws, rig_twist.drive_twist(bones, sit)),
                              skip=[pn for pn in pn_s if (defs.get(origin[pn]) or {}).get("rig_bone")])
            bad = [r for r in rows if r["through"] > _ra.LAYER_BAD]
            log += [("WARNING rig: " if bad else "rig: ") + ln.strip() if i == 0 else ln
                    for i, ln in enumerate(_ra.layers_text(rows, top=4))]
            rigged["layers_seated"] = rows[:8]
    shapes = {}
    if face_shapes:  # after the bake and the skin: both use the meshed (open-mouthed) low poly
        from . import faceshapes
        from . import faceshapes_apply
        tf = time.time()
        for pn, (tp, _) in topo.items():  # (one mesh, own quads) each low-poly vertex's GNM vertex: face shapes
            # by index. Only when the low poly is still the topology's vertices as they were written
            z = np.load(tp)
            if pn in parts and "gnm" in z.files and len(z["verts"]) == len(parts[pn]["verts"]) and \
                    np.allclose(np.asarray(parts[pn]["verts"], float), z["verts"], atol=1e-5):
                parts[pn]["gnm_index"] = z["gnm"]
            elif pn in parts and "gnm" in z.files:
                log.append(f"WARNING face shapes: {pn}'s low poly isn't its topology's vertices: shapes by projection")
        moving = {pn: p for pn, p in parts.items() if pn not in pf_of and not report[pn].get("curves")}
        if os.environ.get("HP_SHAPES_DUMP"):  # (debug / fast tuning: the parts as faceshapes_apply.apply gets them, so a
            # shape constant can be retried on them in seconds; spikes/game_ready/shapesfast.py)
            import copy
            import pickle
            with open(os.environ["HP_SHAPES_DUMP"], "wb") as fh:
                pickle.dump({"spec": spec, "parts": copy.deepcopy(moving), "face_shapes": face_shapes}, fh)
        shapes = faceshapes_apply.apply(spec, moving, face_shapes, log)
        from . import skin_folds_geometry
        fx = skin_folds_geometry.expression(spec, {pn: parts[pn] for pn in shapes}, log)   # the folds' own change with each shape
        for pn, nms in shapes.items():
            report[pn]["face_shapes"] = nms
            if fx and parts[pn].get("shapes") and pn.split("/")[-1].split("~")[0] == (spec.get("skin") or {}).get("part", "body"):
                report[pn]["fold_expressions"] = fx
            if parts[pn].get("shape_unevenness"):  # (faceshapes_apply.unevenness: shapes over UNEVEN_COUNT, worst vertex)
                report[pn]["face_shape_unevenness"] = parts[pn].pop("shape_unevenness")
        log.append(f"face shapes: {len(faceshapes_apply.names_of(face_shapes))} on {len(shapes)} parts in "
                   f"{time.time() - tf:.1f}s")
        if rigged and hf is not None:  # whatever a face shape moves is head: it must not also bend with the neck
            moved = {}
            for pn in shapes:
                d = [np.linalg.norm(np.asarray(x[0]), axis=1) for x in (parts[pn].get("shapes") or {}).values()]
                if d and pn in skin_at and len(d[0]) == len(skin_at[pn]):
                    moved[pn] = np.max(d, 0)
            before = {pn: _head_share(rigged, pn, hf["bone"]) for pn in moved}
            skin_cov = rig_skin.skin_cover(rspec, bones, {pn: (skin_at[pn], parts[pn]["corner_vert"].reshape(-1, 3))
                                                     for pn in skin_at}, hf)
            rigged["weights"] = rig_head.rigid_near(bones, rigged["weights"], skin_at, moved, hf["band"], skin_cov,
                                                     hf["h"] if rspec.get("base") else None)
            for pn, mv in moved.items():
                m = mv >= rigmod.MOVED[1]
                if m.any():
                    b0, b1 = before[pn][m], _head_share(rigged, pn, hf["bone"])[m]
                    log.append(f"rig: {pn}: {int(m.sum())} vertices the face shapes move "
                               f"{rigmod.MOVED[1] * 1e3:g} mm or more are Head {b1.min():.2f}+ "
                               f"({int((b0 < 0.99).sum())} weren't: least {b0.min():.2f})")
    for p in parts.values():  # (the lashes' roots: only face shapes needed them)
        p.pop("lash_root", None)
        p.pop("lash_centre", None)
    corr_keys = []
    if rigged and correctives:  # pose correctives (correctives.py): morph targets faded in by the joint's angle
        from . import correctives as cormod, rig_bend
        tc = time.time()
        corr_keys = cormod.keys(rigged["bones"])
        seen_ = {k["name"] for k in corr_keys}
        nc_ = 0
        for pn in list(rigged["weights"]):
            if pn not in skin_at or report[pn].get("curves") or report[pn].get("lashes") or \
                    (defs.get(origin.get(pn, pn)) or {}).get("rig_bone"):
                continue
            Jp, Wp = rigged["weights"][pn]
            Fp = parts[pn]["corner_vert"].reshape(-1, 3)
            # this part's keys from its own limbs' girth (the frames its weights were painted with: a stub's hip
            # gets its seat, rig.ARC_GIRTH); a person's are the plain keys
            kp_ = cormod.keys(rigged["bones"], girth=rig_bend.limb_girth(rigged["bones"], skin_at[pn], Jp, Wp))
            corr_keys += [k for k in kp_ if k["name"] not in seen_]
            seen_ |= {k["name"] for k in kp_}
            D = cormod.solve(rigged["bones"], skin_at[pn], Fp, Jp, Wp, kp_, log if pn == "body" else [])
            D = {k: v for k, v in D.items() if np.abs(v).max() > cormod.EPS}
            if not D:
                continue
            n0 = cormod.vertex_normals(skin_at[pn], Fp)
            sh = parts[pn].setdefault("shapes", {})
            for k in kp_:
                if k["name"] in D:
                    sh[k["name"]] = (D[k["name"]], n0, cormod.vertex_normals(skin_at[pn] + D[k["name"]], Fp))
            report[pn]["pose_correctives"] = [k["name"] for k in kp_ if k["name"] in D]
            nc_ += len(D)
        log.append(f"pose correctives: {len(corr_keys)} ({', '.join(sorted({k['motion'] for k in corr_keys}))}), "
                   f"{nc_} targets over the parts, {time.time() - tc:.1f}s")
    seam = head_body_meshes(spec, parts, topo, log)
    if seam:
        report[seam["part"]]["meshes"] = seam["report"]
    if spec.get("cloth") and asset.LOD0_PUSH_UNDER:  # (r57) LOD0 too: rc2f's sweater poked 0.4-1 mm through both coat shells
        # beside her left chest pocket in the rest pose (an orange speck at 1 m); LOD1-3 start from this
        from . import lods as lodmod0_
        from . import lods_part, lods_under
        st0_ = _garment_stack(spec, parts, log.append)
        if st0_:
            pu0_ = lods_under.push_under_layers(parts, st0_, gap=asset.LOD0_UNDER_GAP)
            log.append("LOD0: under garments put back under their covers (lods_under.push_under_layers): " + ", ".join(
                f"{pn} poking {v['poking0']} vertices / {v['faces_poking0']} faces -> {v['poking']} ({v['moved']} moved"
                f"{', %d capped' % v['capped'] if v.get('capped') else ''}"
                f"{', ' + str(v['flaps']) + ' in a flap through the cover' if v.get('flaps') else ''})"
                for pn, v in pu0_.items()))
            for pn, v in pu0_.items():
                report.setdefault(pn, {})["under0"] = v
    if face_shapes and rest_w:  # the rest expression: each face-shape mesh's default weights (facepose.py)
        for p in parts.values():
            if p.get("shapes"):
                p["shape_rest"] = rest_w
        log.append("face shapes: rest expression " + ", ".join(f"{k} {v:.2f}" for k, v in rest_w.items())
                   + " as the meshes' default weights (mesh.weights, extras.restExpression); the neutral stays closed")
    write_glb(glb, aname, parts, atlas_files, ctx["prefabs"], looks, rigged, extra_ext)
    lod_info = []
    if lods:
        from . import lods as lodmod
        from . import lods_part, lods_under
        ratios = list(lodmod.LOD_RATIOS) if lods is True else [float(r) for r in lods]
        ratio_of, mesh_r, shape_lods = None, None, None
        if rb is not None and lods is True:
            from . import budgets as budgetmod
            above, below = budgetmod.lod_ratios("head"), budgetmod.lod_ratios("body")
            ratios = budgetmod.lod_ratios(None)[1:]
            shape_lods = set((rb.get("face_shapes") or {}).get("lods") or [0])

            ratio_of = True
        cards = [pn for pn in parts if report[pn].get("curves") or report[pn].get("lashes")]
        tier_parts = {}
        if locals().get("hair_cards"):  # hair LODs are the groom's own card TIERS (one atlas for all:
            # hair.export_hair), cut for their budget; thinning LOD0's cards dropped the tail first. (Unrigged too,
            # round 25: whole layers dropped once, 11996 -> 5324 at LOD1 and flat at LOD2 / LOD3.)
            from . import hair as hairmod
            from . import hair_export, hair_head
            hb_ = next((i for i, b in enumerate(rigged["bones"]) if b["name"].endswith("Head")), 0) if rigged else 0
            for k, r in enumerate(ratios, 1):
                tier_ = lodmod.HAIR_TIERS[min(k, len(lodmod.HAIR_TIERS)) - 1]
                sp_ = {**spec, "hair": {**spec["hair"], "export": {**(spec["hair"].get("export") or {}), "tier": tier_}}}
                try:
                    tp_, _tf = hair_export.export_cards(name, out_dir / f"_lod{k}", sp_, log)
                except Exception as e:  # (LOD0 hair kept)
                    log.append(f"WARNING LOD{k}: hair tier {tier_} failed ({type(e).__name__}: {e}); LOD0's cards kept")
                    continue
                tp_.pop("hair", None)
                own_ = None
                if hair_export.share_atlas(tp_, _tf, dict(atlas_files[parts[pn_h]["atlas"]][1])):
                    tp_["atlas"] = parts[pn_h]["atlas"]  # (its uv on LOD0's atlas: a tier's atlas lacks the baked rows)
                else:  # its own maps beside the GLBs (a tier whose pictures differ from LOD0's)
                    import shutil
                    own_ = {}
                    for mk_, f_ in _tf.items():
                        own_[mk_] = out_dir / f"{pn_h}_lod{k}_{mk_}.png"
                        shutil.copyfile(f_, own_[mk_])
                    log.append(f"LOD{k}: hair tier {tier_}'s atlas differs from LOD0's: it carries its own maps")
                nv_ = len(tp_["verts"])
                Jh = np.zeros((nv_, 4), np.int64)
                Jh[:, 0] = hb_
                Wh = np.zeros((nv_, 4), np.float32)
                Wh[:, 0] = 1.0
                tier_parts[k] = (tp_, (Jh, Wh), tier_, own_)
        layer_stack = {}  # (r53) {under garment part: the garment parts over it, transitively}: each LOD puts the under
        # garments back under their decimated covers (lods_under.push_under_layers)
        if spec.get("cloth") and asset.LOD_PUSH_UNDER:
            layer_stack = _garment_stack(spec, parts)
        under_masks = {}  # (r54) parts worn under garments that are not garments (socks, the body): put back under the
        # garments too, but only where they were under one at LOD0 (lods_under.under_at_lod0). rc2c's LOD2 showed the socks
        # (kept whole) through the decimated jeans' calves (101 vertices poking, 1 at LOD0) and the body through the sweater.
        garm_ = [pn for pn in parts if pn.startswith("cloth_") and pn not in pf_of]
        if garm_ and asset.LOD_PUSH_UNDER and asset.LOD_PUSH_WORN:
            for pn, p in parts.items():
                if (pn in garm_ or pn in pf_of or pn in cards or pn in asset.LOD_PUSH_WORN_SKIP or report.get(pn, {}).get("lashes")
                        or p.get("shell")):
                    continue
                P0_, un0_, sh_, ov0_, N0_ = lods_under.under_at_lod0(p, [parts[g] for g in garm_], share=True)
                if int(un0_.sum()) >= asset.LOD_PUSH_WORN_MIN and sh_ >= asset.LOD_PUSH_WORN_SHARE:
                    layer_stack[pn] = list(garm_)
                    under_masks[pn] = (P0_, ~ov0_ if asset.LOD_PUSH_WORN_NOT_OVER else un0_, sh_, N0_, un0_)  # (r55) every vertex NOT over a
                    # garment at LOD0 may move: rc2d's LOD2 left calf showed 22 sock vertices through the jeans whose LOD0
                    # vertices had no jeans within reach (a loose leg), so the 'under at LOD0' mask kept them still
            sk_ = (spec.get("skin") or {}).get("part", "body")
            if sk_ in under_masks and asset.LOD_SKIN_CULL_FROM is not None:  # (Garrett s14) the skin's deep-covered faces drop at
                # LOD >= LOD_SKIN_CULL_FROM too (its residue under the jacket's armhole poked through the decimated sleeve:
                # the underarm notch), except where a dumped clip frame (cull_poses: the seated poses) uncovers it
                P0_, a_, b_, c_, un0_ = under_masks[sk_]
                exp_ = skin_pose_exposed(parts[sk_], P0_, [parts[g] for g in garm_], sk_, garm_, cull_poses)
                under_masks[sk_] = (P0_, a_, b_, c_, un0_, un0_ & ~exp_)  # [5]: what the per-LOD cull may drop
                log.append(f"LODs: {sk_}: {int(un0_.sum())} LOD0 points under the garments, {int((un0_ & exp_).sum())} of them "
                           f"uncovered in a clip frame (kept at every LOD)")
            if under_masks:
                log.append("LODs: parts worn under garments also put back under them: " + ", ".join(
                    f"{pn} ({int(m_[1].sum())} vertices free to move, {m_[2]:.0%} of those in reach under)" for pn, m_ in under_masks.items()))
        garment_cull = garment_cull_masks(parts, layer_stack, garm_)  # (Garrett s10) under garments' LOD0 cover masks
        through0 = {}  # (C441) {part worn under: (its LOD0 points, covered by a chain garment there)}: garment_asset.skin_through
        if chain_lods:
            from . import garment_asset
            cov0_ = [parts[g_] for g_ in chain_w if g_ in parts and parts[g_].get("shell")]
            through0 = {pn: garment_asset.covered_at_lod0(parts[pn], cov0_, m_) for pn, m_ in under_masks.items()
                        if cov0_ and len(m_) >= 5}
        if os.environ.get("HP_LOD_DUMP"):  # (r60, debug: the LOD inputs, to probe a part's LOD steps offline)
            import pickle
            with open(os.environ["HP_LOD_DUMP"], "wb") as fh:
                pickle.dump({"parts": {pn: p for pn, p in parts.items() if pn not in pf_of and pn not in cards},
                             "rigged": rigged, "layer_stack": layer_stack, "under_masks": under_masks,
                             "ratios": ratios, "above": locals().get("above"), "below": locals().get("below")}, fh)
        for k, r in enumerate(ratios, 1):
            tl = time.time()
            if ratio_of is not None:  # above the neck holds detail longer than below it (budgets.lod_ratios)
                kk_ = min(k, len(above) - 1)
                skin_pn_ = (spec.get("skin") or {}).get("part", "body")

                def r_part(pn, kk_=kk_):  # head parts (the skin's head mesh by mesh_ratios) above, the rest below
                    if pn == skin_pn_ or pn in ("eyes", "teeth", "teeth_lower", "tongue") or report.get(pn, {}).get("lashes"):
                        return above[kk_]
                    return below[min(kk_, len(below) - 1)]
                rr_, mesh_r = r_part, {"head": above[kk_], "body": below[min(kk_, len(below) - 1)]}
            else:
                rr_ = r
            own_ = {pn: v for pn, v in chain_lods.get(k, {}).items() if pn in parts}  # (C439) a chain garment's LOD is
            # its own file (export_garment's re-grid at a coarser grid), never a decimation of its LOD0
            lp, lr, rep_l = lods_part.lod_parts({pn: p for pn, p in parts.items() if pn not in pf_of and pn not in own_},
                                             rigged, rr_, skip=cards,
                                             cards={pn_h: hair_cards["layers"]} if locals().get("hair_cards") and k not in tier_parts else None,
                                             mesh_ratios=mesh_r, shapes=(shape_lods is None or k in shape_lods),
                                             ribbons=[pn for pn in cards if report[pn].get("lashes")])
            if own_:
                from . import garment_asset
                log.append(f"LOD{k}: " + garment_asset.take_lods(own_, parts, lp, lr, rep_l, rigged and rigged["bones"]))
            for pn in chain_w:  # (a garment with LOD files, but none for this LOD: more LODs asked than its role has)
                if pn in parts and pn not in own_ and any(pn in v_ for v_ in chain_lods.values()):
                    log.append(f"WARNING LOD{k}: {pn} has no LOD{k} file of its own: DECIMATED from LOD0 like any part "
                               "(export_garment writes one file per LOD of its role)")
            if layer_stack:
                rb_ = below[min(kk_, len(below) - 1)] if ratio_of is not None else r
                pu_ = lods_under.push_under_layers(lp, layer_stack, masks=under_masks, face_deep=(
                    lodmod.LOD_UNDER_FACE_DEEP_FAR if rb_ < lodmod.LOD_SMALL_FAR_RATIO else None))
                log.append(f"LOD{k}: under garments put back under their covers (lods_under.push_under_layers): " + ", ".join(
                    f"{pn} poking {v['poking0']} -> {v['poking']} ({v['moved']} moved{', %d capped' % v['capped'] if v.get('capped') else ''})" for pn, v in pu_.items()))
                for pn, v in pu_.items():
                    rep_l.setdefault(pn, {})["under"] = v
            skin_pn0_ = (spec.get("skin") or {}).get("part", "body")
            for pn, m_ in under_masks.items():  # (r60) the worn parts' covered rims (socks); (s14) the skin's from its own LOD
                    from_ = asset.LOD_SKIN_CULL_FROM if pn == skin_pn0_ else lodmod.LOD_UNDER_CULL_FROM
                    if not from_ or k < from_ or pn not in lp or len(m_) < 5:
                        continue
                    kc_ = lods_under.cull_covered(lp[pn], m_[0], m_[5] if len(m_) > 5 else m_[4])
                    if not kc_.all():
                        lp[pn] = cull_tris(lp[pn], kc_)
                        rep_l.setdefault(pn, {})["covered_culled"] = int((~kc_).sum())
                        rep_l[pn]["triangles"] = len(lp[pn]["corner_vert"]) // 3
                        log.append(f"LOD{k}: {pn}: {int((~kc_).sum())} of {len(kc_)} triangles deep under the garments at LOD0 "
                                   f"dropped (lods_under.cull_covered, {lodmod.LOD_UNDER_CULL_RIM * 1000:.0f} mm rim)")
            for pn, m_ in (through0.items() if own_ else ()):  # (C441) skin still THROUGH a chain garment's own LOD
                # cloth (its flat faces sink further than the push-under looks or moves), covered at LOD0: cut
                cov_ = [lp[g_] for g_ in own_ if g_ in lp and lp[g_].get("shell")]
                if pn not in lp or not cov_:
                    continue
                kt_ = garment_asset.skin_through(lp[pn], cov_, m_[0], m_[1])
                if not kt_.all():
                    lp[pn] = cull_tris(lp[pn], kt_)
                    rep_l.setdefault(pn, {})["through_cut"] = int((~kt_).sum())
                    rep_l[pn]["triangles"] = len(lp[pn]["corner_vert"]) // 3
                    log.append(f"LOD{k}: {pn}: {int((~kt_).sum())} of {len(kt_)} triangles through the garments' own LOD "
                               f"cloth cut (covered at LOD0; garment_asset.skin_through, {garment_asset.THROUGH_REACH * 1000:.0f} mm reach)")
            cull_under_garments(lp, garment_cull, k, log, rep_l)
            atl_k, ext_k = atlas_files, extra_ext
            if k in tier_parts:
                tp_, w_, tier_, own_ = tier_parts[k]
                if own_ is not None:  # (an atlas of its own, wearing the hair material's extensions)
                    hi_ = parts[pn_h]["atlas"]
                    tp_ = {**tp_, "atlas": len(atlas_files)}
                    atl_k = atlas_files + [(f"{pn_h}_lod{k}", own_)]
                    ext_k = {**extra_ext, **({len(atlas_files): extra_ext[hi_]} if hi_ in extra_ext else {})}
                lp[pn_h] = tp_
                if lr is not None:
                    lr["weights"][pn_h] = w_
                rep_l[pn_h] = {"triangles0": len(parts[pn_h]["corner_vert"]) // 3,
                               "triangles": len(tp_["corner_vert"]) // 3, "tier": tier_,
                               "atlas": "own" if own_ is not None else "LOD0's"}
            lg = out_dir / f"{aname}_LOD{k}.glb"
            write_glb(lg, aname, lp, atl_k, {}, looks, lr, ext_k, external=True)
            tri_k = sum(v["triangles"] for v in rep_l.values())
            lod_info.append({"lod": k, "ratio": r, "glb": str(lg), "triangles": tri_k,
                             "parts": {pn: v["triangles"] for pn, v in rep_l.items()}})
            log.append(f"LOD{k} ({r:g} of LOD0): {tri_k} triangles in {time.time() - tl:.1f}s -> {lg.name} (maps "
                       f"by file name beside it); " + ", ".join(f"{pn} {v['triangles']}" for pn, v in rep_l.items()))
        import shutil
        for k in tier_parts:  # (the tiers' own copies of the shared hair atlas)
            shutil.rmtree(out_dir / f"_lod{k}", ignore_errors=True)
    budget_gate = None
    if rb is not None:  # each part's count against the role's budget (a gate line; over = WARNING)
        budget_gate = budget_check(rb, report, spec)
        for ln in budget_gate["lines"]:
            log.append(ln)
        if budget_gate["fail"]:  # (hair-budget rule) over the role's range max is refused, not a WARNING
            raise ValueError(f"{name}: over the {role} budget's hard limit: " + "; ".join(budget_gate["fail"]))
    if fbx:  # the same asset as FBX, for engines' skinned-mesh import
        tf = time.time()
        write_fbx(glb, glb.with_suffix(".fbx"))
        log.append(f"wrote {glb.with_suffix('.fbx').name} in {time.time() - tf:.1f}s")
    for _, f in atlas_files:
        if not lods:  # (the LODs' GLBs read it by name)
            f["specular"].unlink()
    (out_dir / "lowpoly.npz").unlink()
    high.unlink()
    out_dir.joinpath("high_focus.npz").unlink(missing_ok=True)
    # where everything ends up: scene parts as they are, a prefab at each of its instances
    placed = [p["verts"] for pn, p in parts.items() if pn not in pf_of]
    prefabs = {}
    for pf, d in ctx["prefabs"].items():
        M0inv = np.linalg.inv(d["instances"][d["bake"]])
        tri = sum(report[pn]["triangles"] for pn in d["parts"] if pn in report)
        texels = sum(tsz[pn]["uv_fill"] * sizes[parts[pn]["atlas"]] ** 2 for pn in d["parts"] if pn in parts)
        for M in d["instances"].values():
            A = M @ M0inv
            placed += [p["verts"] @ A[:3, :3].T + A[:3, 3] for pn, p in parts.items() if pf_of.get(pn) == pf]
        n = len(d["instances"])
        prefabs[pf] = {"instances": {i: _trs(M) for i, M in d["instances"].items()}, "bake_instance": d["bake"],
                       "parts": d["parts"], "triangles": tri, "texels": int(texels)}
        log.append(f"prefab {pf}: {tri} triangles and {texels / 1e6:.2f} Mtexels shown {n} times "
                   f"(unique copies would add {tri * (n - 1)} triangles, {texels * (n - 1) / 1e6:.2f} Mtexels)")
    allv = np.concatenate(placed)
    shown = ntri + sum(d["triangles"] * (len(d["instances"]) - 1) for d in prefabs.values())
    info = {"glb": str(glb), "triangles": ntri, "triangles_placed": shown,
            "bounds_blender": [allv.min(0).tolist(), allv.max(0).tolist()],
            "texture": texture, "texel_density": texel_density, "height_range_m": max(heights.values()),
            "maps": maps_info[names[0]],
            "atlases": {an: {"size": sizes[ai], "maps": maps_info[an], "height_range_m": heights[an],
                             "coverage": round(cover[an], 3),
                             "parts": [pn for pn, r in report.items() if r["atlas"] == an]} for ai, an in enumerate(names)},
            "parts": report, "prefabs": prefabs, **({"lods": lod_info} if lod_info else {}),
            **({"role": role, "budget": budget_gate} if rb is not None else {}), **({"skin": skin_recipe} if skin_recipe else {}),
            **({"rig": {"bones": [b["name"] for b in rigged["bones"]],
                        "base_bones": sum(1 for b in rigged["bones"] if not b.get("twist") and not b.get("bend")),
                        "layers_seated": rigged.get("layers_seated", []),
                        "rest": "every base joint unrotated at its head, pose as modelled; twist joints rotated so "
                                "local +Y runs along their segment",
                        "twist": rig_twist.twist_table(rigged["bones"]),
                        "twist_axes": "Blender axes here (Z up, faces -Y); the GLB's node extras.hifipushie_twist "
                                      "carry the same per joint in glTF axes (axis_parent) and local (+Y)",
                        "twist_recipe": asset.TWIST_RECIPE,
                        "bend": rig_bend.bend_table(rigged["bones"]), "bend_recipe": asset.BEND_RECIPE,
                        **({"correctives": __import__("hifipushie.correctives", fromlist=["table"]).table(corr_keys),
                            "corrective_recipe": asset.CORRECTIVE_RECIPE} if corr_keys else {}),
                        "head": (f"rigid: {hf['how']}; falloff to the neck over {hf['band'] * 1e3:.0f} mm below; "
                                 "face-shape vertices, teeth, tongue and eyes Head 1.0") if hf else "not rigid"}}
               if rigged else {}),
            **({"face_shapes": {"names": faceshapes_apply.names_of(face_shapes), "parts": shapes,
                                **({"rest": rest_w} if rest_w else {}), "rest_how": asset.REST_HOW,
                                "correctives": {c: f"{op}({a}, {b})" for c, (op, a, b) in faceshapes.CORRECTIVES.items()
                                                if c in faceshapes_apply.names_of(face_shapes)},
                                "convention": "ARKit blendshape names; glTF morph targets (names in mesh.extras."
                                              "targetNames, default weights = face_shapes.rest, else 0), FBX blend shapes of the same names; "
                                              "neutral = mouth closed, each shape its full extent at 1.0, additive; "
                                              "correctives are not ARKit channels: set each to its formula of the "
                                              "ARKit weights every frame (jawOpen_mouthClose = min(jawOpen, "
                                              "mouthClose) seals the lips over an open jaw); left at 0 the lips "
                                              "just stay parted"}}
               if face_shapes else {}),
            "conventions": {"up": "+Y (glTF)", "front": "+Z", "units": "metres", "normal_map": "OpenGL (+Y), MikkTSpace",
                            "height": "0.5 = low-poly surface, 0/1 = -/+ height_range_m (per atlas) along the normal",
                            "orm": "R ambient occlusion, G roughness, B metallic",
                            "specular": "0.5 = F0 0.04 (Blender's IOR level)",
                            "materials": "one per atlas, in the order of 'atlases'",
                            "prefabs": "one mesh per prefab (a primitive per part, in the prefab's frame), a node "
                                       "per instance with extras.prefab"},
            "seconds": round(time.time() - t, 1), "log": log,
            "garments_left_out": [{"garment": g_, "why": why_} for g_, why_ in left_out]}
    try:  # the engine-agnostic shading notes beside the GLB (shading.py): what each material is meant to do
        from . import shading
        from .hair_groom import look_of as _hlook
        sj, sm = shading.write(info, out_dir, aname, looks=looks,
                               hair_look=_hlook(spec) if spec.get("hair") else None, eyes_part=ek[0] if ek else None)
        info["shading"] = {"json": str(sj), "md": str(sm)}
    except Exception as e:  # (notes never fail an export; said in the log)
        log.append(f"WARNING shading notes not written: {type(e).__name__}: {e}")
    try:  # the rig's drivers (twist, bend helpers, pose correctives) per engine (rignotes.py)
        from . import rignotes
        rn = rignotes.write(info, out_dir, aname)
        if rn:
            info["rig_notes"] = {"json": str(rn[0]), "md": str(rn[1])}
    except Exception as e:
        log.append(f"WARNING rig notes not written: {type(e).__name__}: {e}")
    (out_dir / f"{aname}.json").write_text(json.dumps(info, indent=1))
    return info


def preview(glb: Path, views: list[str], size: int = 512, samples: int = 24, focus=None, zoom: float = 1.0,
            hide: list[str] | None = None, lighting: dict | None = None, cameras: list | None = None,
            denoise: bool = True, poses: list[dict] | None = None, engine: str = "game"):
    """Render the exported GLB as a game draws it: re-imported by Blender's glTF importer and rendered in EEVEE set up
    like a game (no ray tracing, alpha-tested cards, shadow maps), its materials built from the export's shading notes
    (<asset>_shading.json: blender_game.py, the engine stage of docs/notes/gates.md), face shapes and the blink map
    driven as an engine drives them. engine="cycles": the old path-traced look of the importer's materials (lighting,
    samples, denoise apply to it only).
    Views as in look; the GLB is Y up, so the cameras are turned to match. hide: parts left out (the roof and
    walls, to see an interior). lighting: a style look ({"lights", "world", "look", "exposure", "view"}, as scene_sync.look
    takes), so the preview compares with the painted look; default a neutral studio under Standard. cameras:
    perspective panels as look takes them (model coordinates, Z up), for close-ups of the textures.
    poses: [{shape name: weight}] (face shapes, the GLB's morph targets): one Blender run renders the views once per
    pose and a list of contact sheets comes back, one per pose."""
    bounds = np.array(json.loads(glb.with_suffix(".json").read_text())["bounds_blender"])
    with tempfile.TemporaryDirectory(prefix="hifipushie-prev-") as tmp:
        frames = (render.view_frames(bounds, views, focus, zoom) if views else []) + [
            render.camera_frame(c, i) for i, c in enumerate(cameras or [])]  # perspective: {"eye", "target", "fov"}
        for f in frames:  # Blender's glTF importer converts back to Z up, so the look cameras apply as they are
            f["out"] = str(Path(tmp) / f"{f['name']}.png")
        game_light_view(lighting, f"preview {glb.name}")  # (rule 5) the game rig only under the game's view
        if engine == "game":
            game(glb, frames=frames, size=size, hide=hide, poses=poses, timeout=600 + 60 * len(poses or []))
        else:
            _blender({"mode": "preview", "glb": str(glb), "views": frames, "size": size, "samples": samples,
                      "hide": list(hide or []), "lighting": lighting, "denoise": denoise, "poses": poses},
                     timeout=600 + 60 * len(poses or []))
        if poses is None:
            return render.contact_sheet([Image.open(f["out"]).convert("RGB") for f in frames], frames)
        return [render.contact_sheet([Image.open(f"{f['out'][:-4]}_p{i}.png").convert("RGB") for f in frames], frames)
                for i in range(len(poses))]
