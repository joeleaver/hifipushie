"""Export: the GLB writer, the litter tile, the recipes, `export` and its report. Part of clutter (clutter.py has the overview)."""
from __future__ import annotations

import json
import math
import struct
from pathlib import Path

import numpy as np

from . import clutter
from .clutter import resolve, style_sheet
from .clutter_build import build
from .clutter_forms import _u

# ------------------------------------------------------------------------------------------------------------ files
def _png(a) -> bytes:
    import io
    from PIL import Image
    b = io.BytesIO()
    Image.fromarray(np.clip(np.asarray(a) * 255 + 0.5, 0, 255).astype(np.uint8)).save(b, "PNG")
    return b.getvalue()


def _yup(v):
    return np.stack([v[:, 0], v[:, 2], -v[:, 1]], 1)


class Glb:
    """A small glTF 2.0 writer: meshes with POSITION / NORMAL / TANGENT / TEXCOORD_0 / COLOR_0, external or embedded
    images, extras."""

    def __init__(self):
        self.buf = bytearray()
        self.views, self.acc, self.meshes, self.nodes, self.mats, self.tex, self.images, self.scene = [], [], [], [], [], [], [], []
        self.samplers = [{"magFilter": 9729, "minFilter": 9987, "wrapS": 33071, "wrapT": 33071}]

    def _view(self, data: bytes, target=None):
        while len(self.buf) % 4:
            self.buf.append(0)
        v = {"buffer": 0, "byteOffset": len(self.buf), "byteLength": len(data)}
        if target:
            v["target"] = target
        self.buf += data
        self.views.append(v)
        return len(self.views) - 1

    def accessor(self, a, kind, ctype=5126, target=34962, minmax=False):
        a = np.ascontiguousarray(a, {5126: np.float32, 5125: np.uint32, 5123: np.uint16}[ctype])
        acc = {"bufferView": self._view(a.tobytes(), target), "componentType": ctype, "count": int(len(a) if kind != "SCALAR" else a.size), "type": kind}
        if minmax:
            acc["min"], acc["max"] = a.min(0).tolist(), a.max(0).tolist()
        self.acc.append(acc)
        return len(self.acc) - 1

    def image(self, uri=None, data=None):
        if uri is not None:
            self.images.append({"uri": uri})
        else:
            self.images.append({"bufferView": self._view(data), "mimeType": "image/png"})
        self.tex.append({"source": len(self.images) - 1, "sampler": 0})
        return len(self.tex) - 1

    def material(self, m: dict):
        self.mats.append(m)
        return len(self.mats) - 1

    def mesh(self, name, V, F, N=None, T=None, UV=None, C=None, material=None, extras=None, wind=None):
        at = {"POSITION": self.accessor(_yup(V), "VEC3", minmax=True)}
        if N is not None:
            n = _yup(N)
            n = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
            at["NORMAL"] = self.accessor(n, "VEC3")
        if T is not None:
            t = _yup(T[:, :3])
            t = t / np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-9)
            at["TANGENT"] = self.accessor(np.c_[t, T[:, 3]], "VEC4")
        if UV is not None:
            at["TEXCOORD_0"] = self.accessor(UV, "VEC2")
        if wind is not None:  # the plants' wind channels (veg_export.WIND_RECIPE)
            at["TEXCOORD_1"] = self.accessor(wind[:, :2], "VEC2")
            at["TEXCOORD_2"] = self.accessor(wind[:, 2:], "VEC2")
            at["_WIND"] = self.accessor(wind, "VEC4")
        if C is not None:
            at["COLOR_0"] = self.accessor(np.clip(C, 0, 1), "VEC3" if C.shape[1] == 3 else "VEC4")
        F = np.asarray(F)
        big = len(V) > 65535
        prim = {"attributes": at, "indices": self.accessor(F.reshape(-1), "SCALAR", 5125 if big else 5123, 34963), "mode": 4}
        if material is not None:
            prim["material"] = material
        m = {"name": name, "primitives": [prim]}
        if extras:
            m["extras"] = extras
        self.meshes.append(m)
        return len(self.meshes) - 1

    def node(self, name, mesh=None, translation=None, in_scene=True, extras=None):
        n = {"name": name}
        if mesh is not None:
            n["mesh"] = mesh
        if translation is not None:
            n["translation"] = [float(translation[0]), float(translation[2]), float(-translation[1])]
        if extras:
            n["extras"] = extras
        self.nodes.append(n)
        if in_scene:
            self.scene.append(len(self.nodes) - 1)
        return len(self.nodes) - 1

    def write(self, path, extras=None, generator="hifipushie clutter"):
        while len(self.buf) % 4:
            self.buf.append(0)
        G = {"asset": {"version": "2.0", "generator": generator}, "scene": 0, "scenes": [{"nodes": self.scene}],
             "nodes": self.nodes, "meshes": self.meshes, "accessors": self.acc, "bufferViews": self.views,
             "buffers": [{"byteLength": len(self.buf)}]}
        if self.mats:
            G["materials"] = self.mats
        if self.tex:
            G["textures"], G["images"], G["samplers"] = self.tex, self.images, self.samplers
        if extras:
            G["asset"]["extras"] = extras
        js = json.dumps(G, separators=(",", ":")).encode()
        js += b" " * (-len(js) % 4)
        with open(path, "wb") as f:
            f.write(struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(js) + 8 + len(self.buf)))
            f.write(struct.pack("<I4s", len(js), b"JSON") + js)
            f.write(struct.pack("<I4s", len(self.buf), b"BIN\x00") + bytes(self.buf))
        return str(path)


def litter_tile(px: int, f: dict, season: str, sat_val, seed: int):
    """A debris patch's picture from above: (rgb (px, px, 3) sRGB, alpha). Leaves lie thickest in the middle and thin
    out raggedly; each casts a little shade on what is under it; twigs and crumbs between."""
    from PIL import Image, ImageDraw
    from scipy import ndimage
    from .terrain_style import _hsv
    rng = np.random.default_rng(seed)  # (the same seed every season: the same patch, leaves added or gone)
    S = 3 * px
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    pal = [np.asarray(_hsv(c, sat_val[0], sat_val[1])) for c in f["colors"].get(season, f["colors"]["summer"])]
    n0 = int(rng.integers(f["leaves"][0], f["leaves"][1] + 1))
    lobe = rng.uniform(0, 2 * math.pi, 3)

    def spot():  # a ragged round patch: denser in the middle, lobed outline
        while True:
            a = rng.uniform(0, 2 * math.pi)
            r = 0.44 * rng.uniform() ** 0.7 * (1 + 0.18 * math.sin(3 * a + lobe[0]) + 0.1 * math.sin(5 * a + lobe[1]))
            if r < 0.44:
                return np.array([0.5 + r * math.cos(a), 0.5 + r * math.sin(a)])
    tw = tuple(int(255 * c) for c in _hsv(f["twig_color"], sat_val[0], sat_val[1])) + (255,)
    for _ in range(int(rng.integers(f["bits"][0], f["bits"][1] + 1))):
        c = spot() * S
        r = rng.uniform(0.004, 0.01) * S
        dr.ellipse([c[0] - r, c[1] - r * 0.7, c[0] + r, c[1] + r * 0.7], fill=tw)
    leaves = []
    for i in range(n0):
        leaves.append((spot(), rng.uniform(0, 2 * math.pi), _u(rng, f["leaf"]), rng.uniform(-1, 1), int(rng.integers(0, 8)), rng.uniform()))
    keep = {"summer": 1.0, "autumn": f["autumn"], "winter": f["winter"], "spring": f["spring"]}.get(season, 1.0)
    extra = np.random.default_rng(seed + 5)
    if keep > 1:
        for i in range(int(n0 * (keep - 1))):
            leaves.append((spot(), extra.uniform(0, 2 * math.pi), _u(extra, f["leaf"]), extra.uniform(-1, 1), int(extra.integers(0, 8)), extra.uniform()))
    else:
        leaves = [l for l in leaves if l[5] < keep]
    for j in range(int(rng.integers(f["twigs"][0], f["twigs"][1] + 1))):
        c, a, L = spot(), rng.uniform(0, 2 * math.pi), _u(rng, f["twig"])
        d = np.array([math.cos(a), math.sin(a)])
        k = rng.uniform(-0.15, 0.15)
        pts = [tuple(((c + d * L * (t - 0.5) + np.array([-d[1], d[0]]) * k * L * math.sin(math.pi * t)) * S).tolist()) for t in np.linspace(0, 1, 8)]
        dr.line(pts, fill=tw, width=max(2, int(0.006 * S)))
    for c, a, L, tn, ci, _ in leaves:
        d = np.array([math.cos(a), math.sin(a)])
        nrm = np.array([-d[1], d[0]])
        W = L * f["round"]
        poly = []
        us = np.linspace(0, 1, 13)
        for sgn, seq in ((1, us), (-1, us[::-1][1:-1])):
            for u in seq:
                w = W * 0.5 * math.sin(math.pi * u ** 0.75)
                if f["lobed"]:
                    w *= 1 - f["lobed"] * 0.5 * (0.5 + 0.5 * math.cos(u * 5 * 2 * math.pi))
                poly.append(c + d * L * (u - 0.5) + nrm * w * sgn)
        tone = 1 + f["tones"] * tn
        if f["steps"]:
            tone = round(tone * f["steps"]) / f["steps"]
        col = np.clip(pal[ci % len(pal)] * tone, 0, 1)
        xy = [tuple((q * S).tolist()) for q in poly]
        if f["shadow"]:
            sh = [tuple((q * S + [0.004 * S, 0.006 * S]).tolist()) for q in poly]
            dr.polygon(sh, fill=tuple(int(255 * x * (1 - f["shadow"])) for x in col) + (255,))
        dr.polygon(xy, fill=tuple(int(255 * x) for x in col) + (255,))
        if f["outline"]:
            dr.line(xy + [xy[0]], fill=tuple(int(255 * x * 0.3) for x in col) + (255,), width=max(2, int(f["outline"] * S)))
        else:
            dr.line([tuple(((c - d * L * 0.5) * S).tolist()), tuple(((c + d * L * 0.45) * S).tolist())],
                    fill=tuple(int(255 * x * 0.75) for x in col) + (255,), width=max(1, S // 400))
    im = im.resize((px, px), Image.LANCZOS)
    a = np.asarray(im, float) / 255.0
    alpha, rgb = a[..., 3], a[..., :3]
    solid = alpha > 0.5
    if solid.any():
        idx = ndimage.distance_transform_edt(~solid, return_distances=False, return_indices=True)
        rgb = rgb[idx[0], idx[1]]
    return rgb, alpha


def _export_litter(cfg: dict, out: Path, stem: str, progress=None) -> dict:
    """A debris patch: LOD 0 an octagon lifted a little in the middle (8 triangles), LOD 1 a quad; one RGBA picture
    per season (all variants in it); no normal map (a flat lie: the vertex normal is the ground's up)."""
    from . import veg_export
    f = cfg["form"]
    nv = cfg["variants"]
    grid = 1 if nv == 1 else 2
    base = cfg["atlas"]
    cell = base // grid
    st = style_sheet(cfg["style"]).get("colour") or {}
    sv = (st.get("saturation", 1.0), st.get("value", 1.0))
    season_tex = {}
    for se in ("summer", "spring", "autumn", "winter"):
        im = np.zeros((base, base, 4))
        for k in range(nv):
            rgb, al = litter_tile(cell, f, se, sv, cfg["seed"] * 100 + k)
            x0, y0 = (k % grid) * cell, (k // grid) * cell
            im[y0: y0 + cell, x0: x0 + cell, :3], im[y0: y0 + cell, x0: x0 + cell, 3] = rgb, al
        fn = f"{stem}_albedo.png" if se == "summer" else f"{stem}_albedo_{se}.png"
        (out / fn).write_bytes(_png(im))
        season_tex[se] = fn
    mext = {"hifipushie_clutter": {"kind": cfg["kind"], "style": cfg["style"], "grade": "clutter"}, "alpha_mips": clutter.ALPHA_MIPS}

    def mat(g):
        return g.material({"name": "litter", "pbrMetallicRoughness": {"baseColorTexture": {"index": g.image(season_tex["summer"])}, "metallicFactor": 0.0, "roughnessFactor": 0.9},
                           "alphaMode": "MASK", "alphaCutoff": 0.5, "extras": mext})

    def mesh(k, lod):
        x0, y0 = (k % grid) * cell, (k // grid) * cell
        if lod == 0:
            a = np.arange(8) * math.pi / 4 + math.pi / 8
            r = 0.5 / math.cos(math.pi / 8)
            V = np.r_[[[0, 0, f["dome"]]], np.c_[r * np.cos(a), r * np.sin(a), np.zeros(8)]]
            F = np.array([[0, 1 + i, 1 + (i + 1) % 8] for i in range(8)])
        else:
            V = np.array([[-0.5, -0.5, 0.004], [0.5, -0.5, 0.004], [0.5, 0.5, 0.004], [-0.5, 0.5, 0.004]])
            F = np.array([[0, 1, 2], [0, 2, 3]])
        V = np.clip(V, [-0.5, -0.5, 0], [0.5, 0.5, 1])
        UV = np.c_[(x0 + (V[:, 0] + 0.5) * cell) / base, (y0 + (0.5 - V[:, 1]) * cell) / base]
        N = np.tile([0, 0, 1.0], (len(V), 1))
        return V, F, N, UV
    variants, on = [], []
    for k in range(nv):
        files = []
        for lod in (0, 1):
            V, F, N, UV = mesh(k, lod)
            g = Glb()
            g.node("litter", g.mesh(f"v{k}_LOD{lod}_litter", V, F, N, None, UV, material=mat(g)))
            fn = f"{stem}_v{k}_LOD{lod}.glb"
            g.write(out / fn)
            files.append({"lod": lod, "file": fn, "triangles": int(len(F)), "vertices": int(len(V)), "outline_iou": 1.0})
            on.append({"file": fn, "mesh": f"v{k}_LOD{lod}_litter", "primitive": 0})
        variants.append({"name": f"v{k}", "lods": files, "collision": None, "collision_triangles": 0, "height_m": f["dome"], "sink_m": 0.0,
                         "bounds": [[-0.5, -0.5, 0], [0.5, 0.5, f["dome"]]]})
    g = Glb()
    m = mat(g)
    for k in range(nv):
        V, F, N, UV = mesh(k, 0)
        g.node(f"v{k}", g.mesh(f"v{k}_LOD0_litter", V, F, N, None, UV, material=m), translation=(1.2 * k, 0, 0))
    g.write(out / f"{stem}.glb")

    def state(se):
        hidden = se == "snow"
        return {"material": "litter", "baseColorFactor": [1, 1, 1, 1], "roughnessFactor": 0.9, "alphaMode": "MASK", "alphaCutoff": 0.5, "doubleSided": False,
                "hidden": hidden, "baseColorTexture": {"file": season_tex.get(se, season_tex["winter"])}}
    J = {"contract": {"version": veg_export.CONTRACT, "changes": veg_export.CONTRACT_LOG,
                      "rule": "an engine should refuse a version or a slot it doesn't know: every slot is in slot_list"},
         "grade": "clutter", "kind": cfg["kind"], "style": {"name": cfg["style"], "foliage": None}, "about": cfg["about"], "glb": f"{stem}.glb",
         "lods": [{"lod": j, "triangles": [v["lods"][j]["triangles"] for v in variants], "grade": "clutter"} for j in (0, 1)],
         "slot_list": [{"slot": "litter", "on": on, "hidden_in": ["snow"], "channels": ["NORMAL", "POSITION", "TEXCOORD_0"]}],
         "slots": {"litter": state("summer")}, "default": "summer", "variants": [],
         "seasons": {se: {"litter": state(se)} for se in ("spring", "summer", "autumn", "winter", "snow")},
         "snow": {**veg_export.snow_numbers({}, None), "coverage": 0.0, "hidden": True, "note": "a debris patch is not snowed on: it is hidden under snow (slot_list hidden_in)"}, "impostor": None, "alpha_mips": clutter.ALPHA_MIPS,
         "clutter": {"size_m": 1.0, "what_scale_means": "instance scale = the patch's width in metres", "height_m": f["dome"], "sink_m": 0.0,
                     "pivot": "the ground: lay it ON the surface, turned to the ground's normal (a decal with a mesh); draw after the terrain with a small depth bias, or lift it 1 cm",
                     "size_range_m": cfg["size_range"], "place": cfg["place"], "variants": variants,
                     "lod_switch_m": {"lod1": 8.0, "lod2": None, "cull": 30.0, "times": "the instance's scale"},
                     "instancing": clutter.INSTANCE_RECIPE, "collision": None, "wet": {}, "tint": None, "instance_tints": [],
                     "textures": {"atlas_px": base, "shared_by": "every variant and LOD", "mipmaps": True, "normal": None,
                                  "seasons": "a season is another albedo picture (same uv, the same patch with leaves added or gone): seasons.<season>.litter.baseColorTexture.file; hidden under snow"}},
         "note": "a debris patch is one alpha-MASK card per variant; cast no shadow, receive shadows"}
    (out / f"{stem}_seasons.json").write_text(json.dumps(J, indent=1))
    return J


def export(spec: dict, out_dir, stem: str | None = None, progress=None) -> dict:
    """Write a clutter asset into out_dir: <stem>_v<k>_LOD<j>.glb per variant and LOD, <stem>_v<k>_collision.glb
    (convex hull, node `..-convcolonly`), the shared <stem>_albedo[_<season>] / _normal / _orm.png (referenced by uri),
    <stem>.glb (every variant's LOD 0 in a row, to look at), <stem>_seasons.json (the plant contract's shape: grade
    "clutter", kind, slots, lods, variants, sizes, recipes). Returns the json."""
    from . import veg_export
    from .terrain_style import _srgb_lin as _lin
    cfg = resolve(spec)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = stem or f"ck_{cfg['kind']}_{cfg['style']}"
    if cfg["material"] == "litter":
        return _export_litter(cfg, out, stem, progress)
    B = build(spec, progress)
    leaf = cfg["material"] == "leaf"
    slot = {"wood": "wood", "leaf": "foliage"}.get(cfg["material"], "rock")
    tex, season_tex = {}, {}
    for se, im in B["albedo"].items():
        fn = f"{stem}_albedo.png" if se == "summer" else f"{stem}_albedo_{se}.png"
        (out / fn).write_bytes(_png(im if leaf else im[..., :3]))
        season_tex[se] = fn
    tex["albedo"] = season_tex["summer"]
    for nm, im in (("normal", B["normal"]), ("orm", B["orm"])):
        tex[nm] = f"{stem}_{nm}.png"
        (out / tex[nm]).write_bytes(_png(im))
    mext = {"hifipushie_clutter": {"kind": cfg["kind"], "style": cfg["style"], "grade": "clutter", "wet": cfg["wet"]}}
    if leaf:
        mext["alpha_mips"] = clutter.ALPHA_MIPS
        mext["wind"] = veg_export.WIND_RECIPE

    def mat(g):
        a_, n_, o_ = g.image(tex["albedo"]), g.image(tex["normal"]), g.image(tex["orm"])
        m = {"name": slot, "pbrMetallicRoughness": {"baseColorTexture": {"index": a_}, "metallicRoughnessTexture": {"index": o_},
                                                      "metallicFactor": 0.0, "roughnessFactor": 1.0},
             "normalTexture": {"index": n_}, "occlusionTexture": {"index": o_}, "extras": mext}
        if leaf:
            m["alphaMode"], m["alphaCutoff"] = "MASK", 0.5
        return g.material(m)
    variants, on = [], []
    for v in B["variants"]:
        files = []
        for j, L in enumerate(v["lods"]):
            g = Glb()
            g.node(f"{slot}", g.mesh(f"{v['name']}_LOD{j}_{slot}", L["V"], L["F"], L["N"], L["T"], L["UV"], material=mat(g), wind=L.get("wind")))
            fn = f"{stem}_{v['name']}_LOD{j}.glb"
            g.write(out / fn)
            files.append({"lod": j, "file": fn, "triangles": L["triangles"], "vertices": int(len(L["V"])), "outline_iou": L.get("iou", 1.0),
                          **({"cards": L.get("cards", 0)} if leaf else {})})
            on.append({"file": fn, "mesh": f"{v['name']}_LOD{j}_{slot}", "primitive": 0})
        colf = None
        if v["collision"] is not None:
            g = Glb()
            g.node(f"{stem}_{v['name']}-convcolonly", g.mesh("collision", v["collision"][0], v["collision"][1]))
            colf = f"{stem}_{v['name']}_collision.glb"
            g.write(out / colf)
        variants.append({"name": v["name"], "lods": files, "collision": colf, "collision_triangles": int(len(v["collision"][1])) if colf else 0,
                         "height_m": v["height"], "sink_m": v["sink"], "bounds": v["bounds"]})
    g = Glb()
    m = mat(g)
    for i, v in enumerate(B["variants"]):
        L = v["lods"][0]
        g.node(f"{v['name']}", g.mesh(f"{v['name']}_LOD0_{slot}", L["V"], L["F"], L["N"], L["T"], L["UV"], material=m, wind=L.get("wind")), translation=(1.4 * i, 0, 0))
    g.write(out / f"{stem}.glb", extras={"hifipushie_clutter": {"kind": cfg["kind"], "style": cfg["style"]}})

    def state(se):
        st = {"material": slot, "baseColorFactor": [1, 1, 1, 1], "roughnessFactor": 1.0, "alphaMode": "MASK" if leaf else "OPAQUE", "doubleSided": False,
              "hidden": False, "baseColorTexture": {"file": season_tex.get(se, season_tex.get("winter" if se == "snow" else "summer", tex["albedo"]))},
              "normalTexture": {"file": tex["normal"]},
              "ormTexture": {"file": tex["orm"], "channels": "R occlusion, G roughness, B metallic (0)"}}
        if leaf:
            st["alphaCutoff"] = 0.5
        return st
    snow = veg_export.snow_numbers({}, None)
    snow.pop("variant", None)
    channels = ["NORMAL", "POSITION", "TANGENT", "TEXCOORD_0"] + (["TEXCOORD_1", "TEXCOORD_2", "_WIND"] if leaf else [])
    J = {"contract": {"version": veg_export.CONTRACT, "changes": veg_export.CONTRACT_LOG,
                      "rule": "an engine should refuse a version or a slot it doesn't know: every slot is in slot_list"},
         "grade": "clutter", "kind": cfg["kind"], "style": {"name": cfg["style"], "foliage": (("an open bush from a grown shrub: stems + spray cards (LOD 0), a share of the same sprays, larger (LOD 1), "
                                                       "two crossed cards (LOD 2); one alpha-MASK material") if cfg["form"].get("open", True)
                                                      else "closed leafy lumps standing on the ground (one material)") if leaf else None},
         "about": cfg["about"],
         "glb": f"{stem}.glb",
         "lods": [{"lod": j, "triangles": [v["lods"][j]["triangles"] for v in variants], "grade": "clutter"} for j in range(len(cfg["lods"]))],
         "slot_list": [{"slot": slot, "on": on, "hidden_in": [], "channels": channels}],
         "slots": {slot: state("summer")},
         "default": "summer", "variants": [],
         "seasons": {se: {slot: state(se)} for se in ("spring", "summer", "autumn", "winter", "snow")},
         "snow": snow, "impostor": None,
         "clutter": {"size_m": 1.0, "what_scale_means": "instance scale = the largest plan dimension in metres (the mesh is 1 m at scale 1" + (", its sprays a little more)" if leaf else ")"),
                     "height_m": round(float(np.mean([v["height_m"] for v in variants])), 3),
                     "sink_m": round(float(np.mean([v["sink_m"] for v in variants])), 3),
                     "pivot": "the ground line: place it ON the surface; sink_m (x scale) of the mesh is below it",
                     "size_range_m": cfg["size_range"], "place": cfg["place"],
                     "variants": variants, "lod_switch_m": {"lod1": clutter.LOD_SWITCH[0], "lod2": clutter.LOD_SWITCH[1], "cull": clutter.LOD_SWITCH[2], "times": "the instance's scale"},
                     "color_srgb": [round(c, 4) for c in cfg["color"]], "color_linear": [round(float(c), 4) for c in _lin(cfg["color"])],
                     "wet": {**cfg["wet"], "row": "water", "recipe": clutter.WET_RECIPE}, "tint": clutter.TINT_RECIPE if slot == "rock" else None, "tone_range": cfg["paint"].get("tone_range") if slot == "rock" else None,
                     "instance_tints": clutter.INSTANCE_TINTS if slot == "rock" else [], "instancing": clutter.INSTANCE_RECIPE,
                     "collision": ("convex hull per variant (<stem>_v<k>_collision.glb, node name ends -convcolonly); scale with the instance"
                                   if cfg["collision"] else None),
                     "textures": {"atlas_px": cfg["atlas"], "shared_by": "every variant and LOD of this folder (uv by position: box charts)",
                                  "mipmaps": True, "normal": "tangent space, OpenGL (+Y up), TANGENT written in the meshes",
                                  "seasons": "a season changes only the albedo picture (same uv): seasons.<season>.<slot>.baseColorTexture.file" if leaf else None}},
         "note": ("a clutter bush has ONE slot (foliage: the dome and its sprays, alpha MASK); a season = another albedo picture; snow = the winter picture + the snow numbers on the vertex NORMAL"
                  if leaf else "a clutter solid has one slot and no season variants: seasons are the same material (snow = the snow numbers on the vertex NORMAL)")}
    if leaf:
        J["alpha_mips"] = clutter.ALPHA_MIPS
        J["wind"] = veg_export.WIND_RECIPE
    (out / f"{stem}_seasons.json").write_text(json.dumps(J, indent=1))
    return J


def report(J: dict) -> str:
    c = J["clutter"]
    v = c["variants"]
    lines = [f"clutter {J['kind']} in style {J['style']['name']} (contract {J['contract']['version']}, grade clutter): {len(v)} variants, "
             f"height {c['height_m']} m at 1 m across, {c['sink_m']} m of it below the ground line",
             "triangles per LOD: " + "; ".join(f"LOD{l['lod']} " + "/".join(str(t) for t in l["triangles"]) for l in J["lods"]),
             "outline IoU against LOD 0 (8 directions): " + "; ".join(
                 f"LOD{j} " + "/".join(f"{x['lods'][j]['outline_iou']:.2f}" for x in v) for j in range(1, len(J["lods"])))
             + ("  WARNING: a LOD under 0.9 pops" if any(l_["outline_iou"] < 0.9 for x in v for l_ in x["lods"]) else ""),
             f"LOD switch at {c['lod_switch_m']['lod1']} / {c['lod_switch_m']['lod2']} m x scale, gone at {c['lod_switch_m']['cull']} m x scale",
             "collision: " + (f"convex hulls of {'/'.join(str(x['collision_triangles']) for x in v)} triangles" if c["collision"] else "none (walked over)"),
             f"textures: {c['textures']['atlas_px']} px " + ("albedo / normal / orm" if c['textures'].get('normal') else "albedo (alpha), a picture per season") + " shared by all variants and LODs",
             f"files: {J['glb']} (all variants, to look at), <stem>_v<k>_LOD<j>.glb, <stem>_seasons.json"]
    return "\n".join(lines)
