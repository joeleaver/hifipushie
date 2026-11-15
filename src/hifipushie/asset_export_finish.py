"""The end of an export: the budget gate, FBX, where everything ends up, the json beside the GLB, the notes. Stages of the game-ready export (asset_export._export calls them in order; asset.py has the overview)."""
from __future__ import annotations

import json
import time

import numpy as np

from . import asset
from .asset_budget import budget_check
from .asset_glb import _trs
from .asset_scene import write_fbx

def _finish(ex):
    """The budget gate, FBX, scratch files removed, where everything ends up, the json beside the GLB, the shading and rig notes."""
    budget_gate = None
    if ex.rb is not None:  # each part's count against the role's budget (a gate line; over = WARNING)
        budget_gate = budget_check(ex.rb, ex.report, ex.spec)
        for ln in budget_gate["lines"]:
            ex.log.append(ln)
        if budget_gate["fail"]:  # (hair-budget rule) over the role's range max is refused, not a WARNING
            raise ValueError(f"{ex.name}: over the {ex.role} budget's hard limit: " + "; ".join(budget_gate["fail"]))
    if ex.fbx:  # the same asset as FBX, for engines' skinned-mesh import
        tf = time.time()
        write_fbx(ex.glb, ex.glb.with_suffix(".fbx"))
        ex.log.append(f"wrote {ex.glb.with_suffix('.fbx').name} in {time.time() - tf:.1f}s")
    for _, f in ex.atlas_files:
        if not ex.lods:  # (the LODs' GLBs read it by name)
            f["specular"].unlink()
    (ex.out_dir / "lowpoly.npz").unlink()
    ex.high.unlink()
    ex.out_dir.joinpath("high_focus.npz").unlink(missing_ok=True)
    # where everything ends up: scene parts as they are, a prefab at each of its instances
    placed = [p["verts"] for pn, p in ex.parts.items() if pn not in ex.pf_of]
    prefabs = {}
    for pf, d in ex.ctx["prefabs"].items():
        M0inv = np.linalg.inv(d["instances"][d["bake"]])
        tri = sum(ex.report[pn]["triangles"] for pn in d["parts"] if pn in ex.report)
        texels = sum(ex.tsz[pn]["uv_fill"] * ex.sizes[ex.parts[pn]["atlas"]] ** 2 for pn in d["parts"] if pn in ex.parts)
        for M in d["instances"].values():
            A = M @ M0inv
            placed += [p["verts"] @ A[:3, :3].T + A[:3, 3] for pn, p in ex.parts.items() if ex.pf_of.get(pn) == pf]
        n = len(d["instances"])
        prefabs[pf] = {"instances": {i: _trs(M) for i, M in d["instances"].items()}, "bake_instance": d["bake"],
                       "parts": d["parts"], "triangles": tri, "texels": int(texels)}
        ex.log.append(f"prefab {pf}: {tri} triangles and {texels / 1e6:.2f} Mtexels shown {n} times "
                   f"(unique copies would add {tri * (n - 1)} triangles, {texels * (n - 1) / 1e6:.2f} Mtexels)")
    allv = np.concatenate(placed)
    shown = ex.ntri + sum(d["triangles"] * (len(d["instances"]) - 1) for d in prefabs.values())
    info = {"glb": str(ex.glb), "triangles": ex.ntri, "triangles_placed": shown,
            "bounds_blender": [allv.min(0).tolist(), allv.max(0).tolist()],
            "texture": ex.texture, "texel_density": ex.texel_density, "height_range_m": max(ex.heights.values()),
            "maps": ex.maps_info[ex.names[0]],
            "atlases": {an: {"size": ex.sizes[ai], "maps": ex.maps_info[an], "height_range_m": ex.heights[an],
                             "coverage": round(ex.cover[an], 3),
                             "parts": [pn for pn, r in ex.report.items() if r["atlas"] == an]} for ai, an in enumerate(ex.names)},
            "parts": ex.report, "prefabs": prefabs, **({"recolour": ex.recolour} if ex.recolour else {}), **({"lods": ex.lod_info} if ex.lod_info else {}),
            **({"role": ex.role, "budget": budget_gate} if ex.rb is not None else {}), **({"skin": ex.skin_recipe} if ex.skin_recipe else {}),
            **({"rig": {"bones": [b["name"] for b in ex.rigged["bones"]],
                        "base_bones": sum(1 for b in ex.rigged["bones"] if not b.get("twist") and not b.get("bend")),
                        "layers_seated": ex.rigged.get("layers_seated", []),
                        "rest": "every base joint unrotated at its head, pose as modelled; twist joints rotated so "
                                "local +Y runs along their segment",
                        "twist": ex.rig_twist.twist_table(ex.rigged["bones"]),
                        "twist_axes": "Blender axes here (Z up, faces -Y); the GLB's node extras.hifipushie_twist "
                                      "carry the same per joint in glTF axes (axis_parent) and local (+Y)",
                        "twist_recipe": asset.TWIST_RECIPE,
                        "bend": ex.rig_bend.bend_table(ex.rigged["bones"]), "bend_recipe": asset.BEND_RECIPE,
                        **({"correctives": __import__("hifipushie.correctives", fromlist=["table"]).table(ex.corr_keys),
                            "corrective_recipe": asset.CORRECTIVE_RECIPE} if ex.corr_keys else {}),
                        "head": (f"rigid: {ex.hf['how']}; falloff to the neck over {ex.hf['band'] * 1e3:.0f} mm below; "
                                 "face-shape vertices, teeth, tongue and eyes Head 1.0") if ex.hf else "not rigid"}}
               if ex.rigged else {}),
            **({"face_shapes": {"names": ex.faceshapes_apply.names_of(ex.face_shapes), "parts": ex.shapes,
                                **({"rest": ex.rest_w} if ex.rest_w else {}), "rest_how": asset.REST_HOW,
                                "correctives": {c: f"{op}({a}, {b})" for c, (op, a, b) in ex.faceshapes.CORRECTIVES.items()
                                                if c in ex.faceshapes_apply.names_of(ex.face_shapes)},
                                "convention": "ARKit blendshape names; glTF morph targets (names in mesh.extras."
                                              "targetNames, default weights = face_shapes.rest, else 0), FBX blend shapes of the same names; "
                                              "neutral = mouth closed, each shape its full extent at 1.0, additive; "
                                              "correctives are not ARKit channels: set each to its formula of the "
                                              "ARKit weights every frame (jawOpen_mouthClose = min(jawOpen, "
                                              "mouthClose) seals the lips over an open jaw); left at 0 the lips "
                                              "just stay parted"}}
               if ex.face_shapes else {}),
            "conventions": {"up": "+Y (glTF)", "front": "+Z", "units": "metres", "normal_map": "OpenGL (+Y), MikkTSpace",
                            "height": "0.5 = low-poly surface, 0/1 = -/+ height_range_m (per atlas) along the normal",
                            "orm": "R ambient occlusion, G roughness, B metallic",
                            "specular": "0.5 = F0 0.04 (Blender's IOR level)",
                            "materials": "one per atlas, in the order of 'atlases'",
                            "prefabs": "one mesh per prefab (a primitive per part, in the prefab's frame), a node "
                                       "per instance with extras.prefab"},
            "seconds": round(time.time() - ex.t, 1), "log": ex.log,
            "garments_left_out": [{"garment": g_, "why": why_} for g_, why_ in ex.left_out]}
    try:  # the engine-agnostic shading notes beside the GLB (shading.py): what each material is meant to do
        from . import shading
        from .hair_groom import look_of as _hlook
        sj, sm = shading.write(info, ex.out_dir, ex.aname, looks=ex.looks,
                               hair_look=_hlook(ex.spec) if ex.spec.get("hair") else None, eyes_part=ex.ek[0] if ex.ek else None)
        info["shading"] = {"json": str(sj), "md": str(sm)}
    except Exception as e:  # (notes never fail an export; said in the log)
        ex.log.append(f"WARNING shading notes not written: {type(e).__name__}: {e}")
    try:  # the rig's drivers (twist, bend helpers, pose correctives) per engine (rignotes.py)
        from . import rignotes
        rn = rignotes.write(info, ex.out_dir, ex.aname)
        if rn:
            info["rig_notes"] = {"json": str(rn[0]), "md": str(rn[1])}
    except Exception as e:
        ex.log.append(f"WARNING rig notes not written: {type(e).__name__}: {e}")
    (ex.out_dir / f"{ex.aname}.json").write_text(json.dumps(info, indent=1))
    return info
