"""GLB: vertices, transforms, the bend / corrective / twist recipes, garment stacks, write_glb, head and body
meshes, texel sizes. Part of the game-ready export (asset.py has the overview)."""
from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

from . import asset

def _gltf_vertices(p: dict):
    """Split corners into glTF vertices (one per distinct position/uv/normal/tangent) and index them."""
    c = p["corner_vert"]
    rows = np.concatenate([c[:, None].astype(np.float64), p["uv"], p["normal"], p["tangent"], p["sign"][:, None]], 1)
    key = np.round(rows * 1e5).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    pos = p["verts"][c[first]] @ asset._Z_TO_Y.T
    nrm = _safe_unit(p["normal"][first].astype(np.float64), [0.0, 0.0, 1.0]) @ asset._Z_TO_Y.T
    tan = _safe_unit(p["tangent"][first].astype(np.float64), [1.0, 0.0, 0.0]) @ asset._Z_TO_Y.T
    uv = np.stack([p["uv"][first, 0], 1 - p["uv"][first, 1]], -1)  # glTF uv origin is the top left
    t4 = np.concatenate([tan, p["sign"][first, None]], 1)
    return (pos.astype(np.float32), nrm.astype(np.float32), np.ascontiguousarray(t4, np.float32),
            uv.astype(np.float32), inv.ravel().astype(np.uint32), c[first])


def _safe_unit(v: np.ndarray, fallback) -> np.ndarray:
    """Unit vectors; any zero-length one (glTF requires unit normals and tangents) becomes `fallback`."""
    n = np.linalg.norm(v, axis=1, keepdims=True)
    return np.where(n > 1e-9, v / np.maximum(n, 1e-12), np.asarray(fallback, float))


def _local(p: dict, M: np.ndarray) -> dict:
    """A part baked at its prefab's bake instance (local -> world M, no mirror) in the prefab's own frame."""
    A = np.linalg.inv(M[:3, :3])
    q = dict(p)
    q["verts"] = (p["verts"].astype(np.float64) - M[:3, 3]) @ A.T
    q["normal"], q["tangent"] = p["normal"] @ A.T, p["tangent"] @ A.T  # rotation x uniform scale: renormalised
    return q


def _trs(M: np.ndarray) -> dict:
    """glTF node transform (translation, rotation, scale) of a local -> world matrix in Blender axes."""
    from scipy.spatial.transform import Rotation
    G = asset._Z_TO_Y @ M[:3, :3] @ asset._Z_TO_Y.T
    det = float(np.linalg.det(G))
    sc = abs(det) ** (1 / 3)
    D = np.diag([-1.0, 1, 1]) if det < 0 else np.eye(3)  # a mirrored instance: negative x scale
    q = Rotation.from_matrix(G @ D / sc).as_quat()  # x, y, z, w as glTF wants
    return {"translation": (asset._Z_TO_Y @ M[:3, 3]).tolist(), "rotation": q.tolist(), "scale": (np.diag(D) * sc).tolist()}


def _arc_quat(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """The shortest turn from unit a to unit b as a glTF quaternion (x, y, z, w)."""
    c = float(a @ b)
    if c < -1 + 1e-9:  # opposite: half a turn about any axis across a
        ax = np.cross(a, [1.0, 0, 0]) if abs(a[0]) < 0.9 else np.cross(a, [0, 0, 1.0])
        return np.r_[ax / np.linalg.norm(ax), 0.0]
    q = np.r_[np.cross(a, b), 1.0 + c]
    return q / np.linalg.norm(q)


def _quat_matrix(q: np.ndarray) -> np.ndarray:
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def _head_share(rigged: dict, pn: str, bone: int) -> np.ndarray:
    J, W = rigged["weights"][pn]
    return (np.asarray(W) * (np.asarray(J) == bone)).sum(1)


def garment_over(spec: dict, log=None) -> dict:
    """{garment: the garment it is worn over} for the spec's garments. The spec's own "over" wins; a frozen garment
    without one ({"frozen", "color"}: cloth.FROZEN_KEYS carry no "over") falls back to the "over" frozen with it, the
    chain cloth's own layered cut uses (thaw). Garrett v6: his frozen garments wrote none, so _garment_stack was empty
    and no garment push-under or under-garment cull ran at any LOD (white shirt shards through the jacket at LOD1-3),
    silently. A fallback is logged; a cloth set with no chain at all is a WARNING."""
    import pickle
    from . import cloth as clothmod_
    out, fell = {}, []
    for gn, g_ in (spec.get("cloth") or {}).items():
        g_ = clothmod_.expanded(g_ or {})
        o_ = g_.get("over")
        if o_ is None and g_.get("frozen"):
            path = Path(g_["frozen"]).expanduser()
            if path.exists():
                st = path.stat()
                k0 = (str(path), st.st_mtime, st.st_size)
                if k0 not in asset._FROZEN_OVER:
                    th_ = clothmod_._THAWED.get(k0)
                    if th_ is None:
                        with open(path, "rb") as f:
                            th_ = pickle.load(f)
                    asset._FROZEN_OVER[k0] = (th_.get("g") or {}).get("over")
                o_ = asset._FROZEN_OVER[k0]
                if o_ is not None:
                    fell.append(f"{gn} over {o_}")
        out[gn] = o_
    if log is not None:
        if fell:
            log(f"garment layers: the spec gives no \"over\"; using the frozen garments' own chain: {', '.join(fell)}")
        if len(out) > 1 and all(v is None for v in out.values()):
            log(f"WARNING garment layers: {len(out)} garments and no \"over\" chain (spec or frozen): no garment "
                "push-under or under-garment cull runs at any LOD")
    return out


def _garment_stack(spec: dict, parts: dict, log=None) -> dict:
    """{under garment part: the garment parts over it, transitively} (cloth "over" chains, garment_over)."""
    stack = {}
    over_ = garment_over(spec, log)
    for on_ in over_:  # every garment down on_'s chain of "over" lies under on_
        x_, seen_ = over_.get(on_), {on_}
        while x_ is not None and x_ not in seen_:
            seen_.add(x_)
            if f"cloth_{x_}" in parts and f"cloth_{on_}" in parts:
                stack.setdefault(f"cloth_{x_}", []).append(f"cloth_{on_}")
            x_ = over_.get(x_)
    return stack


def write_glb(path: Path, name: str, parts: dict, atlases: list[tuple[str, dict[str, Path]]],
              prefabs: dict | None = None, looks: dict | None = None, rig: dict | None = None,
              extra_ext: dict | None = None, external: bool = False):
    """external: the images are referenced by file name (they lie beside the GLB) instead of embedded: several GLBs
    (LOD tiers) share one set of maps. One mesh per part, one material per atlas: atlases is [(atlas name, {basecolor, orm, normal, specular: png})]
    in atlas index order; each part uses the material of its "atlas" index. A shared prefab (prefabs: {prefab:
    {"bake", "instances": {instance: local -> world}, "parts"}}) is one mesh, a primitive per part in its own
    frame, and a node per instance (extras.prefab names it). looks: {part: {"transmission", "ior", "alpha"}}: such a
    part gets a variant of its atlas's material (same textures) with KHR_materials_transmission + KHR_materials_ior
    (glass) or alpha blending. rig: {"bones": [{"name", "head" (Blender axes), "parent"}], "weights": {part: (bone
    indices (verts, 4), weights (verts, 4))}}: a joint node per bone under a "rig" node (at its head, parents first),
    one skin, and the parts with weights skinned to it (`rig.py`)."""
    bin_ = bytearray()
    views, accessors = [], []

    def add(data: np.ndarray, target, ctype, typ, minmax=False):
        while len(bin_) % 4:
            bin_.append(0)
        views.append({"buffer": 0, "byteOffset": len(bin_), "byteLength": data.nbytes,
                      **({"target": target} if target else {})})
        bin_.extend(data.tobytes())
        acc = {"bufferView": len(views) - 1, "componentType": ctype, "count": len(data), "type": typ}
        if minmax:
            acc["min"], acc["max"] = data.min(0).tolist(), data.max(0).tolist()
        accessors.append(acc)
        return len(accessors) - 1

    # the images go into the buffer first: they are views 0..n-1, and texture i shows image i
    images = [p for _, imgs in atlases for p in imgs.values()]
    for p in ([] if external else images):
        while len(bin_) % 4:
            bin_.append(0)
        raw = Path(p).read_bytes()
        views.append({"buffer": 0, "byteOffset": len(bin_), "byteLength": len(raw)})
        bin_.extend(raw)
    materials, k = [], 0
    for an, imgs in atlases:
        ti = {key: k + i for i, key in enumerate(imgs)}
        k += len(imgs)
        materials.append({
            "name": f"{name}_material" if len(atlases) == 1 else f"{name}_{an}_material",
            "pbrMetallicRoughness": {"baseColorTexture": {"index": ti["basecolor"]},
                                     "metallicRoughnessTexture": {"index": ti["orm"]},
                                     "metallicFactor": 1.0, "roughnessFactor": 1.0},
            "normalTexture": {"index": ti["normal"]},
            "occlusionTexture": {"index": ti["orm"]},
            # specular 0..1 in the texture's alpha; 0.5 = F0 0.04 (dielectric default), as Blender's IOR level: the
            # colour factor 2 maps that back (F0 = 0.04 x 2 x 0.5); KHR_materials_specular allows factors > 1
            "extensions": {"KHR_materials_specular": {"specularTexture": {"index": ti["specular"]},
                                                      "specularFactor": 1.0, "specularColorFactor": [2.0, 2.0, 2.0]},
                           **((extra_ext or {}).get(len(materials)) or {})},
        })
    used = ["KHR_materials_specular"] + sorted({e for x in (extra_ext or {}).values() for e in x} - {"KHR_materials_specular"})
    variants = {}

    def material_of(pn, p):
        ai = int(p.get("atlas", 0))
        lk = (looks or {}).get(pn)
        if not lk:
            return ai
        key = (ai, json.dumps(lk, sort_keys=True))
        if key not in variants:
            m = json.loads(json.dumps(materials[ai]))
            m["name"] = f"{m['name']}_{pn.split('/')[-1].split('~')[0]}"
            if lk.get("transmission"):
                m["extensions"]["KHR_materials_transmission"] = {"transmissionFactor": float(lk["transmission"])}
                m["extensions"]["KHR_materials_ior"] = {"ior": float(lk.get("ior", 1.45))}
                for e in ("KHR_materials_transmission", "KHR_materials_ior"):
                    if e not in used:
                        used.append(e)
            if lk.get("alpha", 1.0) < 1.0:
                m["alphaMode"] = "BLEND"
                m["pbrMetallicRoughness"]["baseColorFactor"] = [1.0, 1.0, 1.0, float(lk["alpha"])]
            if lk.get("transmission") or lk.get("alpha", 1.0) < 1.0 or lk.get("double_sided"):
                m["doubleSided"] = True
            if lk.get("alpha_cutoff") is not None:  # alpha-tested, both sides drawn (hair cards)
                m["alphaMode"], m["alphaCutoff"] = "MASK", float(lk["alpha_cutoff"])
                m["doubleSided"] = bool(lk.get("double_sided", True))  # (hair cards with their own back faces: False)
                hx_ = (lk.get("extras") or {}).get("hifipushie_hair")
                if not m["doubleSided"] and hx_ is not None and not hx_.get("back_faces"):
                    raise ValueError(f"{pn}: single-sided hair-card material on cards WITHOUT their own back faces: every "
                                     "viewer culls half the cards (the half-sided hair misdiagnosis); double_sided=True, or "
                                     "export the cards with hair.BACK_FACES")
            for e, v in (lk.get("ext") or {}).items():  # further ratified extensions for this part's material
                m["extensions"][e] = v
                if e not in used:
                    used.append(e)
            if lk.get("extras"):
                m["extras"] = lk["extras"]
            materials.append(m)
            variants[key] = len(materials) - 1
        return variants[key]
    meshes, nodes = [], []

    skinned = (rig or {}).get("weights") or {}
    nb = len((rig or {}).get("bones") or [])

    def primitive(p, pn=None):
        pos, nrm, tan, uv, idx, src = _gltf_vertices(p)
        attrs = {"POSITION": add(pos, 34962, 5126, "VEC3", True), "NORMAL": add(nrm, 34962, 5126, "VEC3"),
                 "TANGENT": add(tan, 34962, 5126, "VEC4"), "TEXCOORD_0": add(uv, 34962, 5126, "VEC2")}
        if p.get("vcolor") is not None:  # a colour per vertex (hair cards: root-to-tip ramp, a value per lock)
            attrs["COLOR_0"] = add(np.ascontiguousarray(np.asarray(p["vcolor"], np.float32)[src]), 34962, 5126, "VEC3")
        if pn in skinned:
            J, W = skinned[pn]
            J, W = np.asarray(J)[src], np.asarray(W, np.float32)[src]
            W = W / W.sum(1, keepdims=True)
            J = np.where(W > 0, J, 0)  # unused slots: joint 0 at weight 0
            attrs["JOINTS_0"] = add(np.ascontiguousarray(J, np.uint8 if nb <= 256 else np.uint16), 34962,
                                    5121 if nb <= 256 else 5123, "VEC4")
            attrs["WEIGHTS_0"] = add(np.ascontiguousarray(W, np.float32), 34962, 5126, "VEC4")
        prim = {"attributes": attrs, "indices": add(idx, 34963, 5125, "SCALAR"), "material": material_of(pn, p)}
        if p.get("shapes"):  # face shapes (faceshapes.py): a morph target per shape, POSITION and NORMAL deltas
            prim["targets"] = [morph(d, n0, n1, src, nrm) for d, n0, n1 in p["shapes"].values()]
        return prim

    def morph(d, n0, n1, src, nrm):
        """One morph target: per glTF vertex the move (Blender -> glTF axes) and the turn of its own normal (the
        vertex normal's turn from the neutral to the target). Sparse accessors: a face shape moves a few percent of
        a body's vertices."""
        dp = (np.asarray(d, np.float64)[src] @ asset._Z_TO_Y.T).astype(np.float32)
        nn = _safe_unit(nrm.astype(np.float64) @ asset._Z_TO_Y, [0.0, 0.0, 1.0])  # back to Blender axes, as n0/n1
        from .faceshapes_apply import turn
        dn = ((turn(nn, n0[src], n1[src]) - nn) @ asset._Z_TO_Y.T).astype(np.float32)
        return {"POSITION": sparse(dp, True), "NORMAL": sparse(dn)}

    def sparse(data, minmax=False):
        rows = np.flatnonzero(np.abs(data).max(1) > 1e-7).astype(np.uint32)
        acc = {"componentType": 5126, "count": len(data), "type": "VEC3"}
        if minmax:
            acc["min"], acc["max"] = data.min(0).tolist(), data.max(0).tolist()
        if len(rows):  # (none: an accessor without a buffer view is all zeros)
            vi = add(rows, None, 5125, "SCALAR")
            vv = add(np.ascontiguousarray(data[rows]), None, 5126, "VEC3")
            accessors.pop()
            accessors.pop()
            acc["sparse"] = {"count": len(rows), "indices": {"bufferView": len(views) - 2, "componentType": 5125},
                             "values": {"bufferView": len(views) - 1}}
        accessors.append(acc)
        return len(accessors) - 1
    prefabs = prefabs or {}
    in_prefab = {pn for d in prefabs.values() for pn in d["parts"]}
    skins, top = [], []
    if nb:  # the armature: a node per bone at its head, relative to its parent's head; the skin's joints
        bones = rig["bones"]
        base = len(nodes)
        head = np.array([asset._Z_TO_Y @ np.asarray(b["head"], float) for b in bones])
        ibm = np.tile(np.eye(4, dtype=np.float32), (nb, 1, 1))
        ibm[:, :3, 3] = -head  # bind pose: every joint unrotated at its head
        for i, b in enumerate(bones):
            ref = head[b["parent"]] if b["parent"] >= 0 else np.zeros(3)
            nodes.append({"name": b["name"], "translation": (head[i] - ref).tolist()})
            tw = b.get("twist")
            if tw:  # a twist bone (rig.py): a leaf whose local +Y is its segment's axis, so a driver sets "turn
                # about Y by share x the driver's roll"; what to drive it from is in its extras
                a = asset._Z_TO_Y @ np.asarray(tw["axis"], float)
                q = _arc_quat(np.array([0.0, 1.0, 0.0]), a)
                R = _quat_matrix(q)
                nodes[-1]["rotation"] = [float(x) for x in q]
                nodes[-1]["extras"] = {"hifipushie_twist": {
                    "driver": tw["driver"], "mode": tw["mode"], "share": tw["share"], "station": tw["station"],
                    "axis_local": [0.0, 1.0, 0.0], "axis_parent": [round(float(x), 6) for x in a]}}
                ibm[i, :3, :3] = R.T
                ibm[i, :3, 3] = -R.T @ head[i]
            bd = b.get("bend")
            if bd:  # a bend helper (rig.py): rests unrotated like the joint it follows; driven by BEND_RECIPE
                nodes[-1]["extras"] = {"hifipushie_bend": {"driver": bd["driver"], "share": bd["share"]}}
        for i, b in enumerate(bones):
            if b["parent"] >= 0:
                nodes[base + b["parent"]].setdefault("children", []).append(base + i)
        nodes.append({"name": "rig", "children": [base + i for i, b in enumerate(bones) if b["parent"] < 0]})
        top.append(len(nodes) - 1)
        skins.append({"name": f"{name}_rig", "joints": list(range(base, base + nb)), "skeleton": len(nodes) - 1,
                      "inverseBindMatrices": add(np.ascontiguousarray(ibm.transpose(0, 2, 1)).reshape(nb, 16),
                                                 None, 5126, "MAT4")})
    for pn, p in parts.items():
        if pn in in_prefab:
            continue
        # (headbody) a part written as SEVERAL meshes on the one skeleton (a native head and its body): p["meshes"] =
        # {mesh name: triangle mask}. Each takes its triangles' corners of the SAME arrays, so the vertices of a shared
        # edge loop (the neck's seam ring) are written twice with identical position, normal, tangent, uv and weights:
        # no crack in any pose, no shading step. Morph targets go to the meshes named in p["shape_meshes"] only.
        subs = [(pn, p)]
        if p.get("meshes"):
            subs = []
            for mn, tm in p["meshes"].items():
                cm = np.repeat(np.asarray(tm, bool), 3)
                q = {**p, "corner_vert": p["corner_vert"][cm], "uv": p["uv"][cm], "normal": p["normal"][cm],
                     "tangent": p["tangent"][cm], "sign": p["sign"][cm]}
                if mn not in (p.get("shape_meshes") or [mn]):  # (pose correctives go on every mesh of the part)
                    q["shapes"] = {k: v for k, v in (q.get("shapes") or {}).items() if k.startswith("corr_")}
                    if not q["shapes"]:
                        q.pop("shapes")
                subs.append((mn, q))
        for mn, q in subs:
            meshes.append({"name": mn, "primitives": [primitive(q, pn)]})
            if q.get("shapes"):  # names in extras.targetNames (the glTF convention engines and Blender read)
                rw = q.get("shape_rest") or {}  # (face_shapes.rest: the rest expression, facepose.py)
                meshes[-1]["weights"] = [float(rw.get(k, 0.0)) for k in q["shapes"]]
                meshes[-1]["extras"] = {"targetNames": list(q["shapes"]),
                                        **({"restExpression": {k: float(v) for k, v in rw.items() if k in q["shapes"]}}
                                           if rw else {})}
            nodes.append({"name": f"{name}_{mn}", "mesh": len(meshes) - 1, **({"skin": 0} if pn in skinned else {})})
            top.append(len(nodes) - 1)
    for pf, d in prefabs.items():
        M0 = d["instances"][d["bake"]]
        meshes.append({"name": pf, "primitives": [primitive(_local(parts[pn], M0), pn) for pn in d["parts"] if pn in parts]})
        for inst, M in d["instances"].items():
            nodes.append({"name": inst, "mesh": len(meshes) - 1, **_trs(M), "extras": {"prefab": pf}})
            top.append(len(nodes) - 1)
    doc = {"asset": {"version": "2.0", "generator": "hifipushie"}, "scene": 0,
           "scenes": [{"nodes": top}], "nodes": nodes, "meshes": meshes, **({"skins": skins} if skins else {}),
           "materials": materials, "textures": [{"source": i, "sampler": 0} for i in range(len(images))],
           "samplers": [{"magFilter": 9729, "minFilter": 9987}],
           "images": ([{"uri": Path(p).name} for p in images] if external else
                      [{"bufferView": i, "mimeType": "image/png"} for i in range(len(images))]),
           "accessors": accessors, "bufferViews": views, "buffers": [{"byteLength": 0}],
           "extensionsUsed": used}
    while len(bin_) % 4:
        bin_.append(0)
    doc["buffers"][0]["byteLength"] = len(bin_)
    js = json.dumps(doc, separators=(",", ":")).encode()
    js += b" " * ((4 - len(js) % 4) % 4)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(bin_)))
        f.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
        f.write(struct.pack("<II", len(bin_), 0x004E4942) + bytes(bin_))


def head_body_meshes(spec: dict, parts: dict, topo: dict, log: list) -> dict | None:
    """(headbody) A native head (base.head.attach "native") and its body as TWO meshes sharing the neck's seam ring:
    sets parts[body]["meshes"] = {"head": triangles of GNM's vertices, "body": the rest} for write_glb when the body's
    low poly is its own quads (parts.body.topology "wrap": every vertex knows its GNM vertex). base.head.mesh
    "welded" keeps one mesh. -> {"part", "report": {mesh: {"triangles", "vertices"}, "seam": {"vertices", "gap",
    "normal_deg"}}} or None."""
    from . import onemesh
    b = spec.get("base") or {}
    if not onemesh.native(b):
        return None
    mode = (b.get("head") or {}).get("mesh", "separate")
    if mode not in ("separate", "welded"):
        raise ValueError('base.head.mesh: "separate" (head and body meshes sharing the seam ring; default) or "welded"')
    if mode == "welded":
        return None
    for pn, (tp, _) in topo.items():
        p = parts.get(pn)
        z = np.load(tp)
        if p is None or "gnm" not in z.files:
            continue
        gi = p.get("gnm_index")  # (face shapes checked it against the low poly before they moved anything)
        if gi is None and len(z["verts"]) == len(p["verts"]) and np.allclose(np.asarray(p["verts"], float), z["verts"], atol=1e-5):
            gi = z["gnm"]
        if gi is None or len(gi) != len(p["verts"]):
            log.append(f"WARNING head / body meshes: {pn}'s low poly isn't its topology's vertices "
                       f"({len(p['verts'])} against {len(z['verts'])}): written as one mesh")
            return None
        gi = np.asarray(gi, int)
        tri = np.asarray(p["corner_vert"]).reshape(-1, 3)
        head = (gi[tri] >= 0).all(1)
        p["meshes"] = {"head": head, "body": ~head}
        p["shape_meshes"] = ["head"]
        vh, vb = np.unique(tri[head]), np.unique(tri[~head])
        ring = np.intersect1d(vh, vb)
        # the ring's corners: the same vertex must carry the same normal on both sides (it does when the low poly's
        # normals are smooth there: both meshes read one array). Reported, so a hard edge at the seam is seen.
        cv = np.asarray(p["corner_vert"])
        N = np.asarray(p["normal"], float)
        hm = np.repeat(head, 3)
        worst = 0.0
        for v in ring:
            a_, b_ = N[(cv == v) & hm], N[(cv == v) & ~hm]
            if len(a_) and len(b_):
                worst = max(worst, float(np.degrees(np.arccos(np.clip((a_[:, None] * b_[None]).sum(-1) /
                            (np.linalg.norm(a_, axis=1)[:, None] * np.linalg.norm(b_, axis=1)[None] + 1e-12), -1, 1)).max())))
        rep = {"head": {"triangles": int(head.sum()), "vertices": int(len(vh))},
               "body": {"triangles": int((~head).sum()), "vertices": int(len(vb))},
               "seam": {"vertices": int(len(ring)), "gap": 0.0, "normal_deg": round(worst, 3)}}
        log.append(f"{pn}: written as two meshes on the one skeleton: head {rep['head']['triangles']} triangles (GNM's "
                   f"topology, face shapes), body {rep['body']['triangles']}; they share the seam ring's {len(ring)} "
                   f"vertices (same position, normal, uv, weights: largest normal difference across it {worst:.2f} deg)")
        return {"part": pn, "report": rep}
    log.append("WARNING head / body meshes: the body is decimated (no seam ring in it): one mesh. Set "
               "parts.body.topology \"wrap\" for the two-mesh export")
    return None


def texel_sizes(parts: dict, sizes: dict, focus: dict | None = None) -> dict:
    """Per part: surface area, uv area (fraction of its atlas) and the texel size it got (mm per texel) with its
    atlas at sizes[atlas index] texels, plus the texel size inside each of its focus regions ({part: [[x, y, z, r,
    w]]})."""
    out = {}
    for pn, p in parts.items():
        texture = sizes[p["atlas"]]
        c = p["verts"][p["corner_vert"]].reshape(-1, 3, 3).astype(np.float64)
        a3 = np.linalg.norm(np.cross(c[:, 1] - c[:, 0], c[:, 2] - c[:, 0]), axis=1) / 2
        u = p["uv"].reshape(-1, 3, 2).astype(np.float64)
        e1, e2 = u[:, 1] - u[:, 0], u[:, 2] - u[:, 0]
        auv = np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]) / 2

        def mm(sel):
            return float(1000 * np.sqrt(a3[sel].sum() / max(auv[sel].sum(), 1e-20)) / texture)
        out[pn] = {"area_m2": float(a3.sum()), "uv_fill": float(auv.sum()), "mm_per_texel": mm(slice(None))}
        regions = (focus or {}).get(pn) or []
        if regions:
            cen = c.mean(1)
            out[pn]["focus_mm_per_texel"] = [round(mm(np.linalg.norm(cen - f[:3], axis=1) <= f[3]), 2)
                                             for f in regions]
    return out
