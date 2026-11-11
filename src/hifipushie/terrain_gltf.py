"""Writing a terrain mesh as glTF. Part of the terrain mesh (terrain_mesh.py has the overview)."""
from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------- glTF
def _pad4(b: bytes, fill=b"\0"):
    return b + fill * (-len(b) % 4)


def write_glb(path, name, prims, translation, material, extras=None, images=None):
    """One node (at `translation`, glTF axes) with one mesh of primitives: each {"attrs": {NAME: float array},
    "indices": uint array, "material": index or None, "extras": {}}. Materials: a list of glTF material dicts."""
    bin_ = bytearray()
    views, accs = [], []

    def add(arr, target, comp, typ, minmax=False):
        arr = np.ascontiguousarray(arr)
        off = len(bin_)
        bin_.extend(_pad4(arr.tobytes()))
        views.append({"buffer": 0, "byteOffset": off, "byteLength": arr.nbytes, "target": target})
        acc = {"bufferView": len(views) - 1, "componentType": comp, "count": int(arr.shape[0]), "type": typ}
        if minmax:
            acc["min"] = [float(x) for x in arr.min(0)]
            acc["max"] = [float(x) for x in arr.max(0)]
        accs.append(acc)
        return len(accs) - 1

    gprims = []
    for p in prims:
        if not len(p["indices"]):
            continue
        attrs = {}
        for k, a in p["attrs"].items():
            a = np.asarray(a, np.float32)
            typ = {1: "SCALAR", 2: "VEC2", 3: "VEC3", 4: "VEC4"}[a.shape[1]]
            attrs[k] = add(a, 34962, 5126, typ, minmax=(k == "POSITION"))
        idx = np.asarray(p["indices"]).ravel()
        n = len(p["attrs"]["POSITION"])
        if n < 65535:
            ia = add(idx.astype(np.uint16), 34963, 5123, "SCALAR")
        else:
            ia = add(idx.astype(np.uint32), 34963, 5125, "SCALAR")
        gp = {"attributes": attrs, "indices": ia, "mode": 4}
        if p.get("material") is not None:
            gp["material"] = p["material"]
        if p.get("extras"):
            gp["extras"] = p["extras"]
        gprims.append(gp)
    doc = {"asset": {"version": "2.0", "generator": "hifipushie terrain_mesh"},
           "scene": 0, "scenes": [{"nodes": [0]}],
           "nodes": [{"name": name, "mesh": 0, "translation": [float(x) for x in translation]}],
           "meshes": [{"name": name, "primitives": gprims}],
           "accessors": accs, "bufferViews": views, "buffers": [{"byteLength": len(bin_)}]}
    if material:
        doc["materials"] = material
    if images:  # [(bytes, mime type) | uri]: embedded or (a str) a file beside the GLB; texture i = image i, one
        # sampler (trilinear, repeat)
        doc["images"] = []
        for im in images:
            if isinstance(im, str):
                doc["images"].append({"uri": im})
                continue
            data, mime = im
            off = len(bin_)
            bin_.extend(_pad4(data))
            views.append({"buffer": 0, "byteOffset": off, "byteLength": len(data)})
            doc["images"].append({"bufferView": len(views) - 1, "mimeType": mime})
        doc["samplers"] = [{"magFilter": 9729, "minFilter": 9987}]
        doc["textures"] = [{"source": i, "sampler": 0} for i in range(len(images))]
        doc["buffers"][0]["byteLength"] = len(bin_)
    if extras:
        doc["nodes"][0]["extras"] = extras
    js = _pad4(json.dumps(doc, separators=(",", ":")).encode(), b" ")
    total = 12 + 8 + len(js) + 8 + len(bin_)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, total))
        f.write(struct.pack("<II", len(js), 0x4E4F534A))
        f.write(js)
        f.write(struct.pack("<II", len(bin_), 0x004E4942))
        f.write(bytes(bin_))


def read_glb(path):
    """(translation, [primitive dicts {attr: array, "indices", "extras"}]) of a GLB written by write_glb."""
    b = Path(path).read_bytes()
    jl = struct.unpack_from("<I", b, 12)[0]
    doc = json.loads(b[20:20 + jl])
    bl = struct.unpack_from("<I", b, 20 + jl)[0]
    binb = b[28 + jl:28 + jl + bl]
    comp = {5126: np.float32, 5123: np.uint16, 5125: np.uint32}
    width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}

    def acc(i):
        a = doc["accessors"][i]
        v = doc["bufferViews"][a["bufferView"]]
        arr = np.frombuffer(binb, comp[a["componentType"]], a["count"] * width[a["type"]], v["byteOffset"])
        return arr.reshape(a["count"], width[a["type"]]) if width[a["type"]] > 1 else arr

    prims = []
    for p in doc["meshes"][0]["primitives"]:
        d = {k: acc(i) for k, i in p["attributes"].items()}
        d["indices"] = acc(p["indices"]).reshape(-1, 3).astype(np.int64)
        d["extras"] = p.get("extras", {})
        prims.append(d)
    return np.array(doc["nodes"][0].get("translation", [0, 0, 0]), float), prims


def _to_gltf(P):  # ours (x east, y north, z up) -> glTF (x, y up, z = -north)
    return np.c_[P[:, 0], P[:, 2], -P[:, 1]]


def _from_gltf(P):
    return np.c_[P[:, 0], -P[:, 2], P[:, 1]]
