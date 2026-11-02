"""A small skinned GLB for step 10 (garment_export): meshes with flat-colour materials, UVs, one skin.

meshes: [{"name", "V" (Blender axes), "T", "uv" (optional, [0, 1]), "N" (optional), "colour" [r, g, b] 0..1, "J", "W"
(optional: bone indices / weights, 4 per vertex), "double_sided", "metallic", "roughness" (optional), "textures"
(optional, T14: {"base", "mr", "normal"}: PNG paths on the uv; "alpha_cut": an alpha-tested base)}]; bones as rig.rig_bones gives them
({"name", "head", "parent", "twist"?}): a joint node per bone at its head (parents first), twist bones turned as
asset.write_glb turns them, one skin. The <glb>.json beside it carries bounds_blender (asset.preview's cameras).
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

_Z_TO_Y = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], np.float64)  # (asset._Z_TO_Y) Blender Z up -> glTF Y up


def write(path: Path, name: str, meshes: list[dict], bones: list[dict] | None = None, frame: list | None = None) -> Path:
    """frame: [min, max] (Blender axes) the look's cameras frame (default: every mesh)."""
    from .asset import _arc_quat, _quat_matrix
    path = Path(path)
    buf, views, accs = bytearray(), [], []

    def add(a: np.ndarray, target, ctype, typ, minmax=False):
        while len(buf) % 4:
            buf.append(0)
        a = np.ascontiguousarray(a)
        views.append({"buffer": 0, "byteOffset": len(buf), "byteLength": a.nbytes, **({"target": target} if target else {})})
        buf.extend(a.tobytes())
        acc = {"bufferView": len(views) - 1, "componentType": ctype, "count": len(a), "type": typ}
        if minmax:
            acc["min"], acc["max"] = a.min(0).tolist(), a.max(0).tolist()
        accs.append(acc)
        return len(accs) - 1

    nodes, gl_meshes, mats, skins, top = [], [], [], [], []
    images, textures = [], []

    def image(png) -> int:
        """A PNG file embedded once (bufferView + mimeType) -> its texture index."""
        data = Path(png).read_bytes()
        while len(buf) % 4:
            buf.append(0)
        views.append({"buffer": 0, "byteOffset": len(buf), "byteLength": len(data)})
        buf.extend(data)
        images.append({"bufferView": len(views) - 1, "mimeType": "image/png"})
        textures.append({"source": len(images) - 1, "sampler": 0})
        return len(textures) - 1
    nb = len(bones or [])
    if nb:
        head = np.array([_Z_TO_Y @ np.asarray(b["head"], float) for b in bones])
        ibm = np.tile(np.eye(4, dtype=np.float32), (nb, 1, 1))
        ibm[:, :3, 3] = -head
        for i, b in enumerate(bones):
            ref = head[b["parent"]] if b["parent"] >= 0 else np.zeros(3)
            nodes.append({"name": b["name"], "translation": (head[i] - ref).tolist()})
            tw = b.get("twist")
            if tw:  # (asset.write_glb) a twist bone's local +Y is its segment's axis
                q = _arc_quat(np.array([0.0, 1.0, 0.0]), _Z_TO_Y @ np.asarray(tw["axis"], float))
                R = _quat_matrix(q)
                nodes[-1]["rotation"] = [float(x) for x in q]
                ibm[i, :3, :3] = R.T
                ibm[i, :3, 3] = -R.T @ head[i]
        for i, b in enumerate(bones):
            if b["parent"] >= 0:
                nodes[b["parent"]].setdefault("children", []).append(i)
        nodes.append({"name": "rig", "children": [i for i, b in enumerate(bones) if b["parent"] < 0]})
        top.append(len(nodes) - 1)
        skins.append({"name": f"{name}_rig", "joints": list(range(nb)), "skeleton": len(nodes) - 1,
                      "inverseBindMatrices": add(np.ascontiguousarray(ibm.transpose(0, 2, 1)).reshape(nb, 16).astype(np.float32),
                                                 None, 5126, "MAT4")})
    lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
    for m in meshes:
        V = np.asarray(m["V"], float)
        lo, hi = np.minimum(lo, V.min(0)), np.maximum(hi, V.max(0))
        attrs = {"POSITION": add((V @ _Z_TO_Y.T).astype(np.float32), 34962, 5126, "VEC3", True)}
        if m.get("N") is not None:
            N = np.asarray(m["N"], float) @ _Z_TO_Y.T
            N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
            attrs["NORMAL"] = add(N.astype(np.float32), 34962, 5126, "VEC3")
        if m.get("uv") is not None:
            uv = np.asarray(m["uv"], float).copy()
            uv[:, 1] = 1.0 - uv[:, 1]  # glTF's v runs down
            attrs["TEXCOORD_0"] = add(uv.astype(np.float32), 34962, 5126, "VEC2")
        skinned = nb and m.get("J") is not None
        if skinned:
            J, W = np.asarray(m["J"]), np.asarray(m["W"], float)
            W = W / np.maximum(W.sum(1, keepdims=True), 1e-12)
            attrs["JOINTS_0"] = add(J.astype(np.uint8 if nb <= 256 else np.uint16), 34962, 5121 if nb <= 256 else 5123, "VEC4")
            attrs["WEIGHTS_0"] = add(W.astype(np.float32), 34962, 5126, "VEC4")
        T = np.asarray(m["T"], np.uint32).reshape(-1)
        mat = {"name": f"{m['name']}_material", "doubleSided": bool(m.get("double_sided", False)),
               "pbrMetallicRoughness": {"baseColorFactor": [*map(float, m.get("colour") or [0.8, 0.8, 0.8]), 1.0],
                                        "metallicFactor": float(m.get("metallic", 0.0)),
                                        "roughnessFactor": float(m.get("roughness", 0.8))}}
        tex = m.get("textures") or {}
        if tex and m.get("uv") is not None:  # (T14: garment_appearance's maps, baked on the pattern UVs)
            pbr = mat["pbrMetallicRoughness"]
            if tex.get("base"):
                pbr["baseColorTexture"], pbr["baseColorFactor"] = {"index": image(tex["base"])}, [1.0, 1.0, 1.0, 1.0]
            if tex.get("mr"):
                pbr["metallicRoughnessTexture"], pbr["roughnessFactor"] = {"index": image(tex["mr"])}, 1.0
            if tex.get("normal"):
                mat["normalTexture"] = {"index": image(tex["normal"])}
            if m.get("alpha_cut"):
                mat["alphaMode"], mat["alphaCutoff"] = "MASK", 0.5
        mats.append(mat)
        gl_meshes.append({"name": m["name"], "primitives": [{"attributes": attrs, "indices": add(T, 34963, 5125, "SCALAR"),
                                                             "material": len(mats) - 1}]})
        nodes.append({"name": m["name"], "mesh": len(gl_meshes) - 1, **({"skin": 0} if skinned else {})})
        top.append(len(nodes) - 1)
    gltf = {"asset": {"version": "2.0", "generator": "hifipushie garment_export"}, "scene": 0,
            "scenes": [{"nodes": top}], "nodes": nodes, "meshes": gl_meshes, "materials": mats,
            "buffers": [{"byteLength": len(buf)}], "bufferViews": views, "accessors": accs}
    if skins:
        gltf["skins"] = skins
    if images:
        gltf.update({"images": images, "textures": textures,
                     "samplers": [{"magFilter": 9729, "minFilter": 9987, "wrapS": 33071, "wrapT": 33071}]})
    js = json.dumps(gltf, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    while len(buf) % 4:
        buf.append(0)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(buf)))
        f.write(struct.pack("<II", len(js), 0x4E4F534A)); f.write(js)
        f.write(struct.pack("<II", len(buf), 0x004E4942)); f.write(bytes(buf))
    path.with_suffix(".json").write_text(json.dumps({"glb": path.name, "parts": {}, "bounds_blender": frame if frame is not None else [lo.tolist(), hi.tolist()]}))
    return path


def read_counts(path: Path) -> dict:
    """{mesh name: triangles} from a GLB written here (the tests' and the text's check)."""
    raw = Path(path).read_bytes()
    n = struct.unpack("<I", raw[12:16])[0]
    g = json.loads(raw[20:20 + n])
    return {m["name"]: sum(g["accessors"][p["indices"]]["count"] // 3 for p in m["primitives"]) for m in g["meshes"]}
