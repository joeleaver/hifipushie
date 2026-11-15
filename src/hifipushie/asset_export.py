"""`_export`: the export itself (one function), and `preview`. Part of the game-ready export (asset.py has the overview)."""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image

from . import render, store
from .asset_budget import _blender, game
from .asset_gates import approved_head, game_light_view
from .asset_parts import _Log
from .asset_export_finish import _finish
from .asset_export_lods import _lods
from .asset_export_parts import _bake, _density, _lowpoly, _mesh
from .asset_export_rig import _correctives, _rig, _shapes
from .asset_export_wear import _clothes, _hair, _materials

class Export:
    """What one export carries from stage to stage: the arguments of `_export`, then what each stage sets for
    the ones after it. A stage reads and writes it as `ex.<name>`; what a stage only uses itself is a local there.
    _begin sets:
      log, t, rb, spec, aname, defs, fine, tri_focus, rest_w, faceshapes_apply, fface
    _mesh sets:
      ctx, origin, high
    _density sets:
      areas, w, focus, rel, loads, fixed, planar, pf_of, units, topo, fill
    _lowpoly sets:
      names, sizes, cfg, t1, parts, binfo, ntri, tsz, report
    _bake sets:
      atlas_files, maps_info, heights, cover, skin_recipe, recolour
    _hair sets:
      extra_ext, hair_cards, pn_h
    _clothes sets:
      chain_w, chain_looks, left_out, chain_lods, garment_asset
    _materials sets:
      glb, looks, ek
    _rig sets:
      rigged, rigmod, rig_twist, rig_skin, rig_head, rig_bend, rspec, bones, skin_at, hf
    _shapes sets:
      shapes, faceshapes
    _correctives sets:
      corr_keys
    _lods sets:
      lod_info, tp_, _tf, kk_
    """

    def __init__(self, **arguments):
        self.__dict__.update(arguments)


def _export(name: str, out_dir: Path, triangles: int | None = None, texture: int = 2048, resolution: int = 256,
            atlases: int = 1, texel_density: float | None = None, instancing: bool = True, rig: bool | dict = False,
            fbx: bool = False, face_shapes: bool | list | None = None, asset_name: str | None = None,
            lods: bool | list | None = None, cloth_triangles: int | None = None,
            cull_under_cloth: bool = True, role: str | None = None, correctives: bool = True,
            cull_poses: list | str | None = None, recolour_masks: list | None = None) -> dict:
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
    it without a garment fit, socks) the garments cover is left out (under_cloth_keep), a rim kept at the openings.
    recolour_masks: [{"R": [part, ...], "G": ..., "B": ..., "A": ...}, ...]: the listed parts bake a neutral base and one
    RGBA mask texture per entry (<asset>_mask<k>.png), each channel's default colour (its parts' own) in the json's
    "recolour" and the shading notes; a colour scheme is then one material with a tint per channel (asset_recolour)."""
    ex = Export(name=name, out_dir=out_dir, triangles=triangles, texture=texture, resolution=resolution,
                atlases=atlases, texel_density=texel_density, instancing=instancing, rig=rig, fbx=fbx,
                face_shapes=face_shapes, asset_name=asset_name, lods=lods, cloth_triangles=cloth_triangles,
                cull_under_cloth=cull_under_cloth, role=role, correctives=correctives, cull_poses=cull_poses,
                recolour_masks=recolour_masks)
    _begin(ex)
    _mesh(ex)
    _density(ex)
    _lowpoly(ex)
    _bake(ex)
    _hair(ex)
    _clothes(ex)
    _materials(ex)
    _rig(ex)
    _shapes(ex)
    _correctives(ex)
    _lods(ex)
    return _finish(ex)


def _begin(ex):
    """What is exported and what it may cost: the role's budgets, the spec, the approved head, the part definitions, what face shapes need."""
    ex.log = _Log(ex.name)
    ex.t = time.time()
    ex.rb = None
    if ex.role:  # the budgets profile (budgets.json, docs/notes/budgets.md): what this role may cost; explicit arguments win
        from . import budgets as budgetmod
        ex.rb = budgetmod.role(ex.role)
        bp_ = ex.rb["parts"]
        if ex.triangles is None:  # what the joint decimation spends: the body (head + body meshes) and the small parts
            ex.triangles = sum(int(bp_[k]["default"]) for k in ("head", "body", "eyes_mouth_lashes", "accessories") if k in bp_)
        if ex.cloth_triangles is None and "clothing" in bp_:
            ex.cloth_triangles = int(bp_["clothing"]["default"])
        ex.texture = min(ex.texture, int((ex.rb.get("textures") or {}).get("max_map", ex.texture)))
        if ex.texel_density is None:  # atlases sized by the role's texel density (the face's higher density is the
            # model's parts.<skin>.texel_focus; separate head / body texture SETS need the native head unwrapped as its
            # own part: not built, the two meshes share one atlas)
            ex.texel_density = float(((ex.rb.get("textures") or {}).get("texel_density_px_per_m") or {}).get("body", 1024))
        if ex.lods is None:
            ex.lods = True
        ex.log.append(f"budgets: role {ex.role!r}: triangles {ex.triangles} (head + body + eyes/mouth/lashes + accessories), "
                   f"clothing {ex.cloth_triangles}, maps <= {ex.texture}, LOD0 total {ex.rb['lod0_triangles']['default']}")
    if ex.triangles is None:
        ex.triangles = 15000
        ex.log.append("WARNING budgets: no role given and no triangles: 15000 (not a stated budget; pass role=)")
    ex.spec = store.load(ex.name)
    from . import skin_route
    skin_route.refuse_photo_skin(ex.spec)
    if (ex.spec.get("base") or {}).get("head_approved"):  # (Garrett s7) the head geometry must BE the approved head's: a
        # gate, not a swap (geometry is built from the stored model); compose the spec with approved_head first
        lg_ = []
        ah_ = approved_head(ex.spec, lg_)
        h_ = ah_["base"]["head"]
        if h_ != ex.spec["base"].get("head"):
            raise ValueError(f"{ex.name}: base.head is not the approved head ({lg_[0]}): write approved_head(spec)'s "
                             "head into the model first")
        if (ah_.get("skin") or {}).get("folds") != (ex.spec.get("skin") or {}).get("folds"):  # (s8: folds that change form)
            raise ValueError(f"{ex.name}: skin.folds change the head's form ({'; '.join(m for m in lg_ if 'WARNING' in m)}): "
                             "write approved_head(spec)'s skin.folds into the model first")
        if (ah_.get("skin") or {}).get("stack") != (ex.spec.get("skin") or {}).get("stack"):  # (r63) this gate's result
            # is not what ships (textures come from the stored model): the lid layers re-baked by stack_on_head must be
            # IN the model, or the blink map / lid shading of the lid_fold head ships (Tess rc2o did exactly that)
            raise ValueError(f"{ex.name}: skin.stack was measured on another head "
                             f"({'; '.join(m for m in lg_ if m.startswith('skin stack'))}): write approved_head(spec)'s "
                             "skin.stack into the model first")
        ex.log.append(f"head: = the approved head {ex.spec['base']['head_approved']} (checked)")
        for m_ in lg_:  # (append: the export log prints on append, not extend)
            if "skin.folds" in m_:
                ex.log.append(m_)
    ex.aname = ex.asset_name or ex.name
    if ex.recolour_masks:  # (asset_recolour) say now, not after the bake, that a mask names no part of the model
        from .spec import SpecError
        from .base_implied import part_defs
        pd_ = part_defs(ex.spec)
        bad_ = sorted({nm for g in ex.recolour_masks if isinstance(g, dict) for v in g.values()
                       for nm in ([v] if isinstance(v, str) else v) if nm not in pd_})
        if bad_:
            raise SpecError(f"recolour_masks: no part {bad_} in model {ex.name} (parts: {sorted(pd_)})")
    from .base_implied import part_defs
    ex.defs = part_defs(ex.spec)  # (the base's implied parts too: a clear cornea's lens)
    ex.fine, ex.tri_focus, ex.rest_w = {}, [], {}
    if ex.face_shapes:  # say now, not after the bake, that the face can't take them; mesh the slit open; keep
        # triangles at the lids and lips
        from . import faceshapes_apply
        ex.faceshapes_apply = faceshapes_apply
        from .spec import SpecError
        ex.faceshapes_apply.names_of(ex.face_shapes)
        ex.fface = ex.faceshapes_apply.face_of(ex.spec)
        from . import facepose
        ex.rest_w = facepose.rest_of(ex.spec)  # face_shapes.rest: carried as the meshes' default weights, not baked
        if set(ex.rest_w) - set(ex.faceshapes_apply.names_of(ex.face_shapes)):
            raise SpecError(f"face_shapes.rest uses {sorted(set(ex.rest_w) - set(ex.faceshapes_apply.names_of(ex.face_shapes)))}, "
                            "which this export's face_shapes leave out")
        ex.fine, ex.tri_focus = ex.fface.voxels(), ex.fface.tri_focus()


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
    from .asset_budget import notes_of
    bounds = np.array(json.loads(notes_of(glb)[0].read_text())["bounds_blender"])  # (a LOD: its asset's json)
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
