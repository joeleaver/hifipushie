"""What moves: the rig, face shapes, pose correctives and the rest expression. Stages of the game-ready export (asset_export._export calls them in order; asset.py has the overview)."""
from __future__ import annotations

import os
import time

import numpy as np

from . import asset
from .asset_glb import _garment_stack, _head_share, head_body_meshes

def _rig(ex):
    """The rig: bones from the skeleton, every part skinned, the head rigid, twist and bend helpers, the audit."""
    ex.rigged = None
    if ex.rig:  # an armature from the skeleton, the parts (not prefabs) skinned to it
        from . import rig as rigmod
        ex.rigmod = rigmod
        from . import rig_bend, rig_head, rig_model, rig_report, rig_skin, rig_twist
        ex.rig_bend = rig_bend
        ex.rig_head = rig_head
        ex.rig_skin = rig_skin
        ex.rig_twist = rig_twist
        tr = time.time()
        ex.rspec = ex.spec
        if isinstance(ex.rig, dict):  # export options over spec["rig"]: {"twist": ..., "rigid_head": ...}
            ex.rspec = {**ex.spec, "rig": {**(ex.spec.get("rig") or {}), **ex.rig}}
        ex.bones = rig_report.rig_bones(ex.rspec)
        ex.skin_at = {pn: np.array(p["verts"], np.float64) for pn, p in ex.parts.items() if pn not in ex.pf_of}
        ex.rigged = {"bones": ex.bones, "weights": ex.rig_skin.skin_parts(
            ex.rspec, ex.bones, {pn: (ex.skin_at[pn], ex.parts[pn]["corner_vert"].reshape(-1, 3)) for pn in ex.skin_at}, smooth=3)}
        if ex.chain_w:  # a chain garment keeps the weights its own export made and checked in the bend poses
            from . import garment_asset
            ex.garment_asset = garment_asset
            ex.rigged["weights"].update(ex.garment_asset.bone_weights({pn: w_ for pn, w_ in ex.chain_w.items() if pn in ex.parts},
                                                                ex.bones))
        ex.hf = ex.rig_head.head_field(ex.rspec, ex.bones)
        ntw = sum(1 for b in ex.bones if b.get("twist"))
        ex.log.append(f"rig: {len(ex.bones)} bones ({(ex.spec.get('rig') or {}).get('type', 'humanoid')}, root "
                   f"{ex.bones[0]['name']!r}; {ntw} twist bones after the base set), {len(ex.rigged['weights'])} parts "
                   f"skinned, head rigid by {ex.hf['how'] if ex.hf else 'nothing (off, or no Head bone)'}, "
                   f"{time.time() - tr:.1f}s")
        from . import rig_template as _rt
        if _rt.weights_note(ex.rspec):
            ex.log.append(_rt.weights_note(ex.rspec))
        from . import rig_audit as _ra
        sit = _ra.seated(ex.bones)
        if sit and len(ex.skin_at) > 1:  # do the layers stay in order when the character sits (rig_audit.layers)
            pn_s = list(ex.skin_at)
            Vs = np.concatenate([ex.skin_at[pn] for pn in pn_s])
            off = np.cumsum([0] + [len(ex.skin_at[pn]) for pn in pn_s])
            Fs_ = np.concatenate([ex.parts[pn]["corner_vert"].reshape(-1, 3) + off[i] for i, pn in enumerate(pn_s)])
            Js = np.concatenate([np.asarray(ex.rigged["weights"][pn][0]) for pn in pn_s])
            Ws = np.concatenate([np.asarray(ex.rigged["weights"][pn][1], np.float64) for pn in pn_s])
            rows = _ra.layers(Vs, Fs_, np.repeat(np.arange(len(pn_s)), np.diff(off)), pn_s,
                              rig_model.pose(ex.bones, Vs, Js, Ws, ex.rig_twist.drive_twist(ex.bones, sit)),
                              skip=[pn for pn in pn_s if (ex.defs.get(ex.origin[pn]) or {}).get("rig_bone")])
            bad = [r for r in rows if r["through"] > _ra.LAYER_BAD]
            ex.log += [("WARNING rig: " if bad else "rig: ") + ln.strip() if i == 0 else ln
                    for i, ln in enumerate(_ra.layers_text(rows, top=4))]
            ex.rigged["layers_seated"] = rows[:8]


def _shapes(ex):
    """Face shapes: the ARKit set solved on the meshed low poly, lids and lashes with them."""
    ex.shapes = {}
    if ex.face_shapes:  # after the bake and the skin: both use the meshed (open-mouthed) low poly
        from . import faceshapes
        ex.faceshapes = faceshapes
        from . import faceshapes_apply
        ex.faceshapes_apply = faceshapes_apply
        tf = time.time()
        for pn, (tp, _) in ex.topo.items():  # (one mesh, own quads) each low-poly vertex's GNM vertex: face shapes
            # by index. Only when the low poly is still the topology's vertices as they were written
            z = np.load(tp)
            if pn in ex.parts and "gnm" in z.files and len(z["verts"]) == len(ex.parts[pn]["verts"]) and \
                    np.allclose(np.asarray(ex.parts[pn]["verts"], float), z["verts"], atol=1e-5):
                ex.parts[pn]["gnm_index"] = z["gnm"]
            elif pn in ex.parts and "gnm" in z.files:
                ex.log.append(f"WARNING face shapes: {pn}'s low poly isn't its topology's vertices: shapes by projection")
        moving = {pn: p for pn, p in ex.parts.items() if pn not in ex.pf_of and not ex.report[pn].get("curves")}
        if os.environ.get("HP_SHAPES_DUMP"):  # (debug / fast tuning: the parts as faceshapes_apply.apply gets them, so a
            # shape constant can be retried on them in seconds; spikes/game_ready/shapesfast.py)
            import copy
            import pickle
            with open(os.environ["HP_SHAPES_DUMP"], "wb") as fh:
                pickle.dump({"spec": ex.spec, "parts": copy.deepcopy(moving), "face_shapes": ex.face_shapes}, fh)
        ex.shapes = ex.faceshapes_apply.apply(ex.spec, moving, ex.face_shapes, ex.log)
        from . import skin_folds_geometry
        fx = skin_folds_geometry.expression(ex.spec, {pn: ex.parts[pn] for pn in ex.shapes}, ex.log)   # the folds' own change with each shape
        for pn, nms in ex.shapes.items():
            ex.report[pn]["face_shapes"] = nms
            if fx and ex.parts[pn].get("shapes") and pn.split("/")[-1].split("~")[0] == (ex.spec.get("skin") or {}).get("part", "body"):
                ex.report[pn]["fold_expressions"] = fx
            if ex.parts[pn].get("shape_unevenness"):  # (faceshapes_apply.unevenness: shapes over UNEVEN_COUNT, worst vertex)
                ex.report[pn]["face_shape_unevenness"] = ex.parts[pn].pop("shape_unevenness")
        ex.log.append(f"face shapes: {len(ex.faceshapes_apply.names_of(ex.face_shapes))} on {len(ex.shapes)} parts in "
                   f"{time.time() - tf:.1f}s")
        if ex.rigged and ex.hf is not None:  # whatever a face shape moves is head: it must not also bend with the neck
            moved = {}
            for pn in ex.shapes:
                d = [np.linalg.norm(np.asarray(x[0]), axis=1) for x in (ex.parts[pn].get("shapes") or {}).values()]
                if d and pn in ex.skin_at and len(d[0]) == len(ex.skin_at[pn]):
                    moved[pn] = np.max(d, 0)
            before = {pn: _head_share(ex.rigged, pn, ex.hf["bone"]) for pn in moved}
            skin_cov = ex.rig_skin.skin_cover(ex.rspec, ex.bones, {pn: (ex.skin_at[pn], ex.parts[pn]["corner_vert"].reshape(-1, 3))
                                                     for pn in ex.skin_at}, ex.hf)
            ex.rigged["weights"] = ex.rig_head.rigid_near(ex.bones, ex.rigged["weights"], ex.skin_at, moved, ex.hf["band"], skin_cov,
                                                     ex.hf["h"] if ex.rspec.get("base") else None)
            for pn, mv in moved.items():
                m = mv >= ex.rigmod.MOVED[1]
                if m.any():
                    b0, b1 = before[pn][m], _head_share(ex.rigged, pn, ex.hf["bone"])[m]
                    ex.log.append(f"rig: {pn}: {int(m.sum())} vertices the face shapes move "
                               f"{ex.rigmod.MOVED[1] * 1e3:g} mm or more are Head {b1.min():.2f}+ "
                               f"({int((b0 < 0.99).sum())} weren't: least {b0.min():.2f})")
    for p in ex.parts.values():  # (the lashes' roots: only face shapes needed them)
        p.pop("lash_root", None)
        p.pop("lash_centre", None)


def _correctives(ex):
    """Pose correctives, the head and body seam, garments pushed under at LOD0, the rest expression."""
    ex.corr_keys = []
    if ex.rigged and ex.correctives:  # pose correctives (correctives.py): morph targets faded in by the joint's angle
        from . import correctives as cormod, rig_bend
        ex.rig_bend = rig_bend
        tc = time.time()
        ex.corr_keys = cormod.keys(ex.rigged["bones"])
        seen_ = {k["name"] for k in ex.corr_keys}
        nc_ = 0
        for pn in list(ex.rigged["weights"]):
            if pn not in ex.skin_at or ex.report[pn].get("curves") or ex.report[pn].get("lashes") or \
                    (ex.defs.get(ex.origin.get(pn, pn)) or {}).get("rig_bone"):
                continue
            Jp, Wp = ex.rigged["weights"][pn]
            Fp = ex.parts[pn]["corner_vert"].reshape(-1, 3)
            # this part's keys from its own limbs' girth (the frames its weights were painted with: a stub's hip
            # gets its seat, rig.ARC_GIRTH); a person's are the plain keys
            kp_ = cormod.keys(ex.rigged["bones"], girth=ex.rig_bend.limb_girth(ex.rigged["bones"], ex.skin_at[pn], Jp, Wp))
            ex.corr_keys += [k for k in kp_ if k["name"] not in seen_]
            seen_ |= {k["name"] for k in kp_}
            D = cormod.solve(ex.rigged["bones"], ex.skin_at[pn], Fp, Jp, Wp, kp_, ex.log if pn == "body" else [])
            D = {k: v for k, v in D.items() if np.abs(v).max() > cormod.EPS}
            if not D:
                continue
            n0 = cormod.vertex_normals(ex.skin_at[pn], Fp)
            sh = ex.parts[pn].setdefault("shapes", {})
            for k in kp_:
                if k["name"] in D:
                    sh[k["name"]] = (D[k["name"]], n0, cormod.vertex_normals(ex.skin_at[pn] + D[k["name"]], Fp))
            ex.report[pn]["pose_correctives"] = [k["name"] for k in kp_ if k["name"] in D]
            nc_ += len(D)
        ex.log.append(f"pose correctives: {len(ex.corr_keys)} ({', '.join(sorted({k['motion'] for k in ex.corr_keys}))}), "
                   f"{nc_} targets over the parts, {time.time() - tc:.1f}s")
    seam = head_body_meshes(ex.spec, ex.parts, ex.topo, ex.log)
    if seam:
        ex.report[seam["part"]]["meshes"] = seam["report"]
    if ex.spec.get("cloth") and asset.LOD0_PUSH_UNDER:  # (r57) LOD0 too: rc2f's sweater poked 0.4-1 mm through both coat shells
        # beside her left chest pocket in the rest pose (an orange speck at 1 m); LOD1-3 start from this
        from . import lods as lodmod0_
        from . import lods_part, lods_under
        st0_ = _garment_stack(ex.spec, ex.parts, ex.log.append)
        if st0_:
            pu0_ = lods_under.push_under_layers(ex.parts, st0_, gap=asset.LOD0_UNDER_GAP)
            ex.log.append("LOD0: under garments put back under their covers (lods_under.push_under_layers): " + ", ".join(
                f"{pn} poking {v['poking0']} vertices / {v['faces_poking0']} faces -> {v['poking']} ({v['moved']} moved"
                f"{', %d capped' % v['capped'] if v.get('capped') else ''}"
                f"{', ' + str(v['flaps']) + ' in a flap through the cover' if v.get('flaps') else ''})"
                for pn, v in pu0_.items()))
            for pn, v in pu0_.items():
                ex.report.setdefault(pn, {})["under0"] = v
    if ex.face_shapes and ex.rest_w:  # the rest expression: each face-shape mesh's default weights (facepose.py)
        for p in ex.parts.values():
            if p.get("shapes"):
                p["shape_rest"] = ex.rest_w
        ex.log.append("face shapes: rest expression " + ", ".join(f"{k} {v:.2f}" for k, v in ex.rest_w.items())
                   + " as the meshes' default weights (mesh.weights, extras.restExpression); the neutral stays closed")
