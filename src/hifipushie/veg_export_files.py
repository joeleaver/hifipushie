"""The files beside the GLB: seasons_json, write_collision. Part of the plant export (veg_export.py has the contract)."""
from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

from . import veg_export
from . import veg_mesh
from .veg_export import _yup
from .veg_export_parts import collision

def seasons_json(glb: str, images: bool = True) -> dict | None:
    """For engines that drop KHR_materials_variants (Godot 4.7 does: only the default material arrives): what each
    variant puts in each material slot, read back from the written GLB and saved beside it as <stem>_seasons.json:
    {"variants", "default", "slots": {slot (the default material's name): {"material", "baseColorFactor",
    "roughnessFactor", "alphaMode", "alphaCutoff", "doubleSided", "hidden", "baseColorTexture": {"image": index in the
    GLB, "file": the same picture written beside it}}}, "seasons": {variant: {slot: the same keys}}}. `hidden` = the
    slot is not drawn in that season (a deciduous winter): hide the mesh; don't rely on its alpha cut-off."""
    raw = open(glb, "rb").read()
    jl = struct.unpack("<I", raw[12:16])[0]
    G = json.loads(raw[20:20 + jl])
    binp = raw[20 + jl + 8:]
    names = [v_["name"] for v_ in (G.get("extensions") or {}).get("KHR_materials_variants", {}).get("variants", [])]
    if not names:
        return None
    stem = Path(glb).with_suffix("")
    written = {}

    def params(mi):
        m = G["materials"][mi]
        pbr = m.get("pbrMetallicRoughness", {})
        d = {"material": m["name"], "baseColorFactor": pbr.get("baseColorFactor", [1, 1, 1, 1]), "roughnessFactor": pbr.get("roughnessFactor", 1.0),
             "alphaMode": m.get("alphaMode", "OPAQUE"), "doubleSided": bool(m.get("doubleSided", False)),
             "hidden": bool((m.get("extras") or {}).get("hidden"))}
        if (m.get("extras") or {}).get("receive_shadows") is False:
            d["receive_shadows"] = False  # (an impostor's crossed quads shadow each other)
        if "alphaCutoff" in m:
            d["alphaCutoff"] = m["alphaCutoff"]
        if (m.get("extras") or {}).get("factor_over_one"):  # (a factor over 1 is not glTF; this file may carry it whole)
            d["baseColorFactor"] = [*m["extras"]["factor_over_one"], 1.0]
        hi_ = (m.get("extras") or {}).get("hifipushie_impostor")
        if hi_:
            d["impostor"] = {k_: v_ for k_, v_ in hi_.items() if k_ != "normal_texture_index"}
        for key, src in (("baseColorTexture", pbr.get("baseColorTexture")), ("normalTexture", m.get("normalTexture")),
                         ("metallicRoughnessTexture", pbr.get("metallicRoughnessTexture")),
                         ("impostorNormalTexture", {"index": hi_["normal_texture_index"]} if hi_ and hi_.get("normal_texture_index") is not None else None)):
            if src is None:
                continue
            im = G["textures"][src["index"]]["source"]
            d[key] = {"image": im}
            if images and key in ("baseColorTexture", "normalTexture", "impostorNormalTexture"):
                if im not in written:
                    bv = G["bufferViews"][G["images"][im]["bufferView"]]
                    f = Path(f"{stem}_{m['name']}{'_normal' if key != 'baseColorTexture' else ''}.png")
                    f.write_bytes(binp[bv.get("byteOffset", 0): bv.get("byteOffset", 0) + bv["byteLength"]])
                    written[im] = f.name
                d[key]["file"] = written[im]
        return d

    slots, seasons, where = {}, {n_: {} for n_ in names}, {}
    for mesh in G["meshes"]:
        for pi, p_ in enumerate(mesh["primitives"]):
            maps = (p_.get("extensions") or {}).get("KHR_materials_variants", {}).get("mappings")
            if "material" not in p_ or mesh["name"].endswith("_collision"):
                continue
            slot = G["materials"][p_["material"]]["name"]
            where.setdefault(slot, []).append({"mesh": mesh["name"], "primitive": pi})
            if slot in slots:
                continue
            slots[slot] = params(p_["material"])
            for mp in maps or []:
                for vi in mp["variants"]:
                    seasons[names[vi]][slot] = params(mp["material"])
    for n_ in names:  # (a slot a variant doesn't map keeps its default)
        for slot, d in slots.items():
            seasons[n_].setdefault(slot, d)
    slot_list = [{"slot": slot, "on": where[slot], "hidden_in": [n_ for n_ in names if seasons[n_][slot]["hidden"]],
                  "channels": sorted({a_ for mesh in G["meshes"] for p_ in mesh["primitives"]
                                      if "material" in p_ and G["materials"][p_["material"]]["name"] == slot for a_ in p_["attributes"]})}
                 for slot in slots]
    hp = (G.get("extras") or {}).get("hifipushie_plant") or {}
    out = {"contract": {"version": veg_export.CONTRACT, "changes": {str(k_): v_ for k_, v_ in veg_export.CONTRACT_LOG.items()},
                        "rule": "an engine should refuse a version or a slot it doesn't know: every slot is in slot_list"},
           "slot_list": slot_list,
           "grade": hp.get("grade", "full"), "lods": hp.get("lods"),
           "style": {"name": (hp.get("style") or {}).get("name", "realistic"), "foliage": (hp.get("style") or {}).get("kind", "cards")},
           "snow": hp.get("snow_numbers"),
           "impostor": next((d_["impostor"] for d_ in slots.values() if "impostor" in d_), None),
           "glb": Path(glb).name, "variants": names, "default": names[0], "slots": slots, "seasons": seasons,
           "note": "colours are linear RGBA factors (x the texture when there is one, x COLOR_0 where the mesh has it); "
                   "hidden = don't draw that slot's meshes in that season"}
    am = next((m_["extras"]["alpha_mips"] for m_ in G["materials"] if "alpha_mips" in (m_.get("extras") or {})), None)
    if am:
        out["alpha_mips"] = am
    Path(f"{stem}_seasons.json").write_text(json.dumps(out, indent=1))
    out["path"] = f"{stem}_seasons.json"
    return out


def write_collision(tree: dict, path: str, name: str) -> str | None:
    """The collision mesh as a file of its own, its node in the scene and named `<name>_collision-colonly` (Godot's
    importer makes a static body of a node so named and drops the mesh; the plant's own GLB keeps it outside the scene,
    where Godot never sees it). Capsules in extras. The grown tree's, whatever its style."""
    caps = collision(tree)
    thr = max(0.05, 0.3 * float(tree["radius"][1]))
    C = veg_mesh.tubes(tree, sides=(4, 5), min_radius=thr, simplify=1.5, collar=0)
    if not len(C["F"]):
        return None
    V = _yup(C["V"]).astype(np.float32)
    F = C["F"].astype(np.uint32).ravel()
    buf = V.tobytes() + F.tobytes()
    gltf = {"asset": {"version": "2.0", "generator": "hifipushie vegetation"}, "scene": 0, "scenes": [{"nodes": [0]}],
            "nodes": [{"name": f"{name}_collision-colonly", "mesh": 0, "extras": {"collision": True}}],
            "meshes": [{"name": f"{name}_collision", "primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
            "accessors": [{"bufferView": 0, "componentType": 5126, "count": len(V), "type": "VEC3", "min": V.min(0).tolist(), "max": V.max(0).tolist()},
                          {"bufferView": 1, "componentType": 5125, "count": len(F), "type": "SCALAR"}],
            "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": V.nbytes, "target": 34962},
                            {"buffer": 0, "byteOffset": V.nbytes, "byteLength": F.nbytes, "target": 34963}],
            "buffers": [{"byteLength": len(buf)}],
            "extras": {"hifipushie_collision": {"plant": name, "capsules": [
                {"a": _yup(np.array([q["a"]]))[0].tolist(), "b": _yup(np.array([q["b"]]))[0].tolist(), "ra": q["ra"], "rb": q["rb"]} for q in caps]}}}
    js = json.dumps(gltf, separators=(",", ":"), default=float).encode()
    js += b" " * (-len(js) % 4)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(js) + 8 + len(buf)))
        f.write(struct.pack("<I4s", len(js), b"JSON"))
        f.write(js)
        f.write(struct.pack("<I4s", len(buf), b"BIN\0"))
        f.write(buf)
    return str(path)
