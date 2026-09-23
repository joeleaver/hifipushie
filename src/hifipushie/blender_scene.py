"""Runs inside headless Blender: keeps a model's live scene (workspace/<model>/scene.blend) and renders it.

blender -b --factory-startup --python blender_scene.py -- job.json
Jobs:
  {"mode": "pull", "blend": path, "out": json}
      Reads what a person changed in the saved scene: every instance whose transform differs from the one the
      spec gave it ({instance: 4x4 world matrix}).
  {"mode": "sync", "blend": path, "objects": [{"key", "mesh": npz, "hash", "part", "color", "prefab"}],
   "instances": [{"name", "prefab", "matrix"}]}
      Brings the scene in line with the spec: objects whose content hash changed get new mesh data, objects no
      longer in the spec go, prefab parts live in a hidden collection per prefab ("prefab:<name>", in the
      prefab's own frame) and every instance is an empty showing that collection, at the spec's transform
      (stored on it as "hp_matrix", so a later pull can tell a person's edit from the spec's placement).
  {"mode": "render", "blend": path, "views": [...as blender_render...], "size": px, "engine": "EEVEE"}
      Renders views of the scene with a simple sun + sky rig (not saved into the file).
"""

import json
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector


def _open(path):
    import os
    if os.path.exists(path):
        bpy.ops.wm.open_mainfile(filepath=path)
    else:
        for ob in list(bpy.data.objects):
            bpy.data.objects.remove(ob)


def _coll(name, parent=None, hide=False):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(c)
    if hide:  # prefab sources: shown only through their instances
        lc = bpy.context.view_layer.layer_collection.children.get(name)
        if lc is not None:
            lc.exclude = True
    return c


def _material(part, color):
    name = f"part:{part}"
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
        m.use_nodes = True
    rgb = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in color[:3]]  # sRGB -> linear
    m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (*rgb, 1.0)
    m.diffuse_color = (*rgb, 1.0)
    return m


# ---- paint as nodes (paintnodes.py compiles the spec's layers into the program these build) ---------------------

def _lin(c):
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c[:3]]


class _Nodes:
    def __init__(self, tree, quantiles, packing):
        self.t, self.q, self.packing = tree, quantiles, packing
        self.x = 0
        self.attrs = {}

    def node(self, kind, **props):
        n = self.t.nodes.new(kind)
        n.location = (self.x, -len(self.t.nodes) * 3 % 4000)
        for k, v in props.items():
            setattr(n, k, v)
        return n

    def _in(self, sock, v):
        if hasattr(v, "is_output"):
            self.t.links.new(v, sock)
        else:
            sock.default_value = v

    def math(self, op, a, b=0.0, clamp=False):
        n = self.node("ShaderNodeMath", operation=op, use_clamp=clamp)
        self._in(n.inputs[0], a)
        self._in(n.inputs[1], b)
        return n.outputs[0]

    def vmath(self, op, a, b=None, scale=None):
        n = self.node("ShaderNodeVectorMath", operation=op)
        self._in(n.inputs[0], a)
        if b is not None:
            self._in(n.inputs[1], b)
        if scale is not None:
            self._in(n.inputs["Scale"], scale)
        return n.outputs["Value"] if op == "DOT_PRODUCT" else n.outputs["Vector"]

    def attr(self, name, vector=False):
        """A vector attribute (wpos, wnrm), or a scalar input: one channel of its pack (packing: name -> [pack,
        channel], so the shader reads a few vertex attributes, not dozens)."""
        key = (name, vector)
        if key not in self.attrs:
            if vector:
                n = self.node("ShaderNodeAttribute", attribute_type="GEOMETRY", attribute_name=name)
                self.attrs[key] = n.outputs["Vector"]
            else:
                pk, ch = self.packing[name]
                if (pk, "sep") not in self.attrs:
                    sep = self.node("ShaderNodeSeparateXYZ")
                    self._in(sep.inputs[0], self.attr(pk, True))
                    self.attrs[(pk, "sep")] = sep
                self.attrs[key] = self.attrs[(pk, "sep")].outputs[ch]
        return self.attrs[key]

    def value(self, v, name=None):
        if name is None:
            return float(v)
        n = self.node("ShaderNodeValue", name=name, label=name)
        n.outputs[0].default_value = float(v)
        n["hp_set"] = float(v)  # what the spec said: a later pull reports only what a person changed from it
        return n.outputs[0]

    def stretch(self, q, st):
        """paint._stretch: squashed along a direction, or along the vertex's element (then offset by its seed)."""
        if st[0] == "grain":
            _, f, seed = st
            g = self.vmath("NORMALIZE", self.attr("grain", True))  # its length is the end-grain weight
            q = self.vmath("SUBTRACT", q, self.vmath("SCALE", g, scale=self.math(
                "MULTIPLY", self.vmath("DOT_PRODUCT", q, g), 1 - 1 / f)))
            return self.vmath("ADD", q, self.vmath("SCALE", [97.3, 61.7, 83.1], scale=self.attr(seed)))
        dx, dy, dz, f = st
        along = self.vmath("DOT_PRODUCT", q, [dx, dy, dz])
        return self.vmath("SUBTRACT", q, self.vmath("SCALE", [dx, dy, dz], scale=self.math("MULTIPLY", along, 1 - 1 / f)))

    def ramp(self, x, a, b):
        """0 at a, 1 at b (either order), smoothstep between: paint._ramp."""
        n = self.node("ShaderNodeMapRange", clamp=True)
        self._in(n.inputs["Value"], x)
        self._in(n.inputs["From Min"], a)
        self._in(n.inputs["From Max"], b)
        t = n.outputs["Result"]
        return self.math("MULTIPLY", self.math("MULTIPLY", t, t), self.math("SUBTRACT", 3.0, self.math("MULTIPLY", t, 2.0)))

    def noise(self, q, scale, octaves, seed):
        """Our fbm's distribution from Blender's Noise Texture: the raw value through a quantile curve."""
        octaves = max(1, min(int(octaves), 4))
        q = self.vmath("ADD", q, [seed * 113.7, seed * 71.3, seed * 57.1])
        n = self.node("ShaderNodeTexNoise", noise_dimensions="3D")
        self._in(n.inputs["Vector"], q)
        self._in(n.inputs["Scale"], self.math("DIVIDE", 1.0, scale) if hasattr(scale, "is_output") else 1.0 / scale)
        n.inputs["Detail"].default_value = octaves - 1
        n.inputs["Roughness"].default_value = 0.5
        n.inputs["Lacunarity"].default_value = 2.0
        c = self.node("ShaderNodeFloatCurve")
        cv = c.mapping.curves[0]
        xs, ys = self.q["blender"][str(octaves)], self.q["ours"][str(octaves)]
        pts = sorted({round(x, 5): y for x, y in zip(xs, ys)}.items())
        cv.points[0].location = pts[0]
        cv.points[1].location = pts[-1]
        for x, y in pts[1:-1]:
            cv.points.new(x, y)
        c.mapping.use_clip = True
        c.mapping.update()
        self._in(c.inputs["Value"], n.outputs["Fac"])
        return c.outputs["Value"]

    def post(self, g, post):
        b = post.get("breakup")
        if b is not None:
            b = {"amount": float(b)} if isinstance(b, (int, float)) else b
            nz = self.noise(self.attr("wpos", True), float(b.get("scale", 0.03)), int(b.get("octaves", 3)),
                            int(b.get("seed", 0)))
            s = 0.5 * (1 - min(max(float(b.get("sharpness", 0.5)), 0.0), 0.98))
            shift = self.math("MULTIPLY", self.math("SUBTRACT", self.math("MULTIPLY", nz, 2.0), 1.0),
                              float(b.get("amount", 0.5)))
            g = self.ramp(self.math("ADD", g, shift), 0.5 - s, 0.5 + s)
        lv = post.get("levels")
        if lv is not None:
            lo, hi = float(lv[0]), float(lv[1])
            g = self.math("DIVIDE", self.math("SUBTRACT", g, lo), hi - lo if hi != lo else 1e-9)
            g = self.math("MAXIMUM", self.math("MINIMUM", g, 1.0), 0.0)
            if len(lv) > 2:
                g = self.math("POWER", g, 1.0 / float(lv[2]))
        if post.get("invert"):
            g = self.math("SUBTRACT", 1.0, g)
        return g

    def blend(self, mode, a, b):
        if mode == "multiply":
            return self.math("MULTIPLY", a, b)
        if mode == "add":
            return self.math("ADD", a, b)
        if mode == "subtract":
            return self.math("SUBTRACT", a, b)
        if mode == "min":
            return self.math("MINIMUM", a, b)
        if mode == "max":
            return self.math("MAXIMUM", a, b)
        if mode == "screen":
            return self.math("SUBTRACT", 1.0, self.math("MULTIPLY", self.math("SUBTRACT", 1.0, a), self.math("SUBTRACT", 1.0, b)))
        if mode == "overlay":
            lo = self.math("MULTIPLY", self.math("MULTIPLY", a, b), 2.0)
            hi = self.math("SUBTRACT", 1.0, self.math("MULTIPLY", self.math("MULTIPLY", self.math("SUBTRACT", 1.0, a),
                                                                            self.math("SUBTRACT", 1.0, b)), 2.0))
            step = self.math("GREATER_THAN", a, 0.5)
            return self.math("ADD", lo, self.math("MULTIPLY", step, self.math("SUBTRACT", hi, lo)))
        return b

    def exposed(self, e, key, v):
        path = e.get("expose", {}).get(key)
        return self.value(v, "hp:" + json.dumps(path)) if path else float(v)

    def gen(self, e):
        g = e["gen"]
        if g == "facing":
            if e["dir"] == "grain":  # along the vertex's element, either way
                d = self.math("ABSOLUTE", self.vmath("DOT_PRODUCT", self.vmath("NORMALIZE", self.attr("wnrm", True)),
                                                     self.attr("grain", True)))
            else:
                d = self.vmath("DOT_PRODUCT", self.vmath("NORMALIZE", self.attr("wnrm", True)), e["dir"])
            return self.ramp(d, self.exposed(e, "range0", e["range"][0]), self.exposed(e, "range1", e["range"][1]))
        if g == "axis":
            d = self.math("ADD", self.vmath("DOT_PRODUCT", self.attr("wpos", True), e["dir"]), e["offset"])
            return self.ramp(d, self.exposed(e, "range0", e["range"][0]), self.exposed(e, "range1", e["range"][1]))
        if g == "noise":
            q = self.attr("wpos", True)
            if e["stretch"]:
                q = self.stretch(q, e["stretch"])
            scale = self.exposed(e, "scale", e["scale"])
            if e["warp"]:  # displace the lookup by another noise (3 channels): torn grunge
                wn = self.node("ShaderNodeTexNoise", noise_dimensions="3D")
                self._in(wn.inputs["Vector"], q)
                self._in(wn.inputs["Scale"], self.math("DIVIDE", 1.0, scale) if hasattr(scale, "is_output") else 1.0 / scale)
                wn.inputs["Detail"].default_value = 1
                off = self.vmath("SUBTRACT", wn.outputs["Color"], [0.5, 0.5, 0.5])
                q = self.vmath("ADD", q, self.vmath("SCALE", off, scale=self.math("MULTIPLY", scale, 2 * e["warp"] * 3.0)))
            v = self.noise(q, scale, e["octaves"], e["seed"])
            return self.ramp(v, self.exposed(e, "range0", e["range"][0]), self.exposed(e, "range1", e["range"][1]))
        if g == "tiles":
            n = self.vmath("ABSOLUTE", self.attr("wnrm", True))
            sep = self.node("ShaderNodeSeparateXYZ")
            self._in(sep.inputs[0], n)
            w = [self.math("POWER", sep.outputs[k], 6.0) for k in range(3)]
            tot = self.math("MAXIMUM", self.math("ADD", self.math("ADD", w[0], w[1]), w[2]), 1e-12)
            acc = None
            for k, (dd, ee) in enumerate(e["planes"]):
                u = self.vmath("DOT_PRODUCT", self.attr("wpos", True), dd)
                v = self.vmath("DOT_PRODUCT", self.attr("wpos", True), ee)
                val = self.math("MULTIPLY", self.tiles(u, v, e), self.math("DIVIDE", w[k], tot))
                acc = val if acc is None else self.math("ADD", acc, val)
            return acc
        if g == "cells":
            q = self.attr("wpos", True)
            if e["stretch"]:
                q = self.stretch(q, e["stretch"])
            q = self.vmath("ADD", q, [e["seed"] * 31.7, e["seed"] * 17.3, e["seed"] * 23.9])

            def vor(feature):
                n = self.node("ShaderNodeTexVoronoi", voronoi_dimensions="3D", feature=feature, distance="EUCLIDEAN")
                self._in(n.inputs["Vector"], q)
                n.inputs["Scale"].default_value = 1.0 / e["scale"]
                n.inputs["Randomness"].default_value = e["jitter"]
                return n
            f1 = vor("F1")
            if e["mode"] == "edges":
                val = self.math("SUBTRACT", vor("F2").outputs["Distance"], f1.outputs["Distance"])
            elif e["mode"] == "distance":
                val = f1.outputs["Distance"]
            else:
                sep = self.node("ShaderNodeSeparateColor")
                self._in(sep.inputs[0], f1.outputs["Color"])
                val = sep.outputs[0]
            return self.ramp(val, e["range"][0], e["range"][1])
        if g == "input":
            x = self.attr(e["attr"])
            if e.get("sign", 1.0) != 1.0:
                x = self.math("MULTIPLY", x, e["sign"])
            if e["range"] is None:
                return x
            return self.ramp(x, self.exposed(e, "range0", e["range"][0]), self.exposed(e, "range1", e["range"][1]))
        if g == "near":
            w = self.exposed(e, "within", e["within"])
            return self.ramp(self.attr(e["attr"]), self.math("ADD", w, e["soft"]), w)
        if g == "mask":
            return self.stack(e["entries"])
        raise ValueError(g)

    def tiles(self, u, w, e):
        """paint._tiles on one plane: running bond, rows shifted by offset (or at random), joints gap wide."""
        L, H = e["size"]
        row = self.math("FLOOR", self.math("DIVIDE", w, H))
        if e["offset"] == "random":
            wn = self.node("ShaderNodeTexWhiteNoise", noise_dimensions="1D")
            self._in(wn.inputs["W"], self.math("ADD", row, e["seed"] * 7.13 + 0.5))
            shift = wn.outputs["Value"]
        else:
            shift = self.math("MULTIPLY", row, float(e["offset"]))
        uu = self.math("ADD", self.math("DIVIDE", u, L), shift)
        col = self.math("FLOOR", uu)
        if e["mode"] == "id":
            wn = self.node("ShaderNodeTexWhiteNoise", noise_dimensions="3D")
            cmb = self.node("ShaderNodeCombineXYZ")
            self._in(cmb.inputs[0], col)
            self._in(cmb.inputs[1], row)
            cmb.inputs[2].default_value = e["seed"] * 3.7 + 0.5
            self._in(wn.inputs["Vector"], cmb.outputs[0])
            return wn.outputs["Value"]
        fu = self.math("SUBTRACT", uu, col)
        fw = self.math("SUBTRACT", self.math("DIVIDE", w, H), row)
        d = self.math("MINIMUM", self.math("MINIMUM", self.math("MULTIPLY", fu, L),
                                           self.math("MULTIPLY", self.math("SUBTRACT", 1.0, fu), L)),
                      self.math("MINIMUM", self.math("MULTIPLY", fw, H),
                                self.math("MULTIPLY", self.math("SUBTRACT", 1.0, fw), H)))
        edge = self.ramp(d, e["gap"] / 2, e["gap"] / 2 + max(e["bevel"], 1e-6))
        return self.math("SUBTRACT", 1.0, edge) if e["mode"] == "gaps" else edge

    def stack(self, entries):
        m = None
        for e in entries:
            if e["gen"] is None:
                m = self.post(1.0 if m is None else m, e["post"])
                continue
            g = self.post(self.gen(e), e["post"])
            if m is None:
                m = g
                continue
            b = self.blend(e["blend"], m, g)
            w = e["weight"]
            m = self.math("ADD", m, self.math("MULTIPLY", self.math("SUBTRACT", b, m), w), clamp=True)
        return 1.0 if m is None else m


def _paint_material(part, base, layers, quantiles, prog_hash, packing, show=None):
    """A part's material: its base channels, then every layer on it mixed in by opacity x mask. show: a layer
    name: the material shows only that layer's mask, glowing orange 0..1 on grey clay (0 where the layer isn't on
    this part). A material's name shows its first sub-layer (its main coverage)."""
    name = f"part:{part}"
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    if show is None and m.get("hp_prog") == prog_hash:
        return m
    if show is not None:
        m.use_nodes = True
        t = m.node_tree
        t.nodes.clear()
        N = _Nodes(t, quantiles, packing)
        ly = next((ly for ly in layers if ly["name"] == show or ly["name"].startswith(show + ":")), None)
        mask = N.stack(ly["entries"]) if ly else 0.0
        # lit grey clay, the mask glowing orange on it: the shape reads where the mask is 0
        bsdf = N.node("ShaderNodeBsdfPrincipled")
        bsdf.inputs["Base Color"].default_value = (0.18, 0.18, 0.18, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.8
        bsdf.inputs["Emission Color"].default_value = (1.0, 0.35, 0.05, 1.0)
        if ly:
            N._in(bsdf.inputs["Emission Strength"], N.math("MULTIPLY", N.math("MAXIMUM", N.math("MINIMUM", mask, 1.0), 0.0), 2.5))
        out = N.node("ShaderNodeOutputMaterial")
        t.links.new(bsdf.outputs[0], out.inputs[0])
        m["hp_prog"] = "debug"
        return m
    m.use_nodes = True
    t = m.node_tree
    t.nodes.clear()
    N = _Nodes(t, quantiles, packing)
    col = N.node("ShaderNodeRGB").outputs[0]
    col.default_value = (*_lin(base["color"]), 1.0)
    ch = {"roughness": float(base["roughness"]), "metallic": float(base["metallic"]),
          "specular": float(base["specular"])}
    for i, ly in enumerate(layers):
        N.x = 400 * (i + 1)
        mask = N.stack(ly["entries"])
        op = N.value(ly["opacity"], "hp:" + json.dumps(ly["expose"]["opacity"])) if "opacity" in ly["expose"] else ly["opacity"]
        a = N.math("MULTIPLY", op, mask if not isinstance(mask, float) else mask)
        a = N.math("MAXIMUM", N.math("MINIMUM", a, 1.0), 0.0)
        for c, v in ly["channels"].items():
            if c == "color":
                rgb = N.node("ShaderNodeRGB")
                rgb.outputs[0].default_value = (*_lin(v), 1.0)
                if "color" in ly["expose"]:
                    rgb.name = rgb.label = "hp:" + json.dumps(ly["expose"]["color"])
                    rgb["hp_set"] = list(rgb.outputs[0].default_value)[:3]
                mix = N.node("ShaderNodeMix", data_type="RGBA", blend_type="MIX")
                N._in(mix.inputs[0], a)
                N._in(mix.inputs[6], col)
                N._in(mix.inputs[7], rgb.outputs[0])
                col = mix.outputs[2]
            else:
                ch[c] = N.math("ADD", ch[c], N.math("MULTIPLY", a, N.math("SUBTRACT", float(v), ch[c])))
    N.x += 400
    bsdf = N.node("ShaderNodeBsdfPrincipled")
    out = N.node("ShaderNodeOutputMaterial")
    N._in(bsdf.inputs["Base Color"], col)
    N._in(bsdf.inputs["Roughness"], ch["roughness"])
    N._in(bsdf.inputs["Metallic"], ch["metallic"])
    N._in(bsdf.inputs["Specular IOR Level"], ch["specular"])
    t.links.new(bsdf.outputs[0], out.inputs[0])
    m["hp_prog"] = prog_hash
    return m


def _mesh(name, path):
    z = np.load(path)
    verts, faces = z["verts"], z["faces"]
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", verts.astype(np.float32).ravel())
    me.loops.add(faces.size)
    me.loops.foreach_set("vertex_index", faces.astype(np.int32).ravel())
    me.polygons.add(len(faces))
    me.polygons.foreach_set("loop_start", np.arange(0, faces.size, 3, dtype=np.int32))
    me.update()
    me.shade_smooth()
    if "normals" in z:
        me.normals_split_custom_set_from_vertices(z["normals"].astype(np.float64))
    return me


def _inputs(me, path):
    """Per-vertex paint inputs (ao, sky, distances, world position and normal...) as mesh attributes."""
    z = np.load(path)
    for k in z.files:
        a = z[k].astype(np.float32)
        if a.ndim == 2:
            at = me.attributes.new(k, "FLOAT_VECTOR", "POINT")
            at.data.foreach_set("vector", a.ravel())
        else:
            at = me.attributes.new(k, "FLOAT", "POINT")
            at.data.foreach_set("value", a)


def _matrix(m):
    return Matrix([list(r) for r in m])


def _srgb(c):
    return [12.92 * x if x <= 0.0031308 else 1.055 * x ** (1 / 2.4) - 0.055 for x in c[:3]]


def pull(job):
    _open(job["blend"])
    moved, params = {}, {}
    for ob in bpy.data.objects:
        if ob.get("hp_instance") and ob.get("hp_matrix"):
            spec_m = np.array(ob["hp_matrix"]).reshape(4, 4)
            now = np.array(ob.matrix_world)
            if np.abs(now - spec_m).max() > 1e-5:
                moved[ob["hp_instance"]] = now.tolist()
    for m in bpy.data.materials:  # paint numbers exposed as named nodes; the same layer can sit in several parts
        if not m.name.startswith("part:") or not m.node_tree:
            continue
        for n in m.node_tree.nodes:
            if not n.name.startswith("hp:"):
                continue
            v = n.outputs[0].default_value
            was = n.get("hp_set")
            if was is not None:  # untouched since the spec set it: not an edit (the spec may have moved on since)
                now = list(v)[:3] if n.type == "RGB" else [float(v)]
                was = list(was) if n.type == "RGB" else [float(was)]
                if max(abs(a - b) for a, b in zip(now, was)) < 1e-5:
                    continue
            params.setdefault(n.name[3:], []).append(
                [round(float(x), 4) for x in _srgb(v)] if n.type == "RGB" else round(float(v), 5))
    json.dump({"moved": moved, "params": params}, open(job["out"], "w"))


def sync(job):
    _open(job["blend"])
    prog = job.get("program")
    if prog:
        for part, base in job["bases"].items():
            _paint_material(part, base, [ly for ly in prog["layers"] if part in ly["parts"] or "*" in ly["parts"]],
                            prog["quantiles"], job["prog_hash"], prog["packing"].get(part, {}))
    parts = _coll("parts")
    insts = _coll("instances")
    want = {o["key"]: o for o in job["objects"]}
    for ob in list(bpy.data.objects):  # objects whose content changed or that are gone
        key = ob.get("hp_key")
        if key is not None and (key not in want or ob.get("hp_hash") != want[key]["hash"]):
            me = ob.data
            bpy.data.objects.remove(ob)
            if me is not None and me.users == 0:
                bpy.data.meshes.remove(me)
    have = {ob.get("hp_key") for ob in bpy.data.objects}
    made = []
    for key, o in want.items():
        if key in have:
            continue
        me = _mesh(key, o["mesh"])
        if o.get("inputs"):
            _inputs(me, o["inputs"])
        ob = bpy.data.objects.new(key, me)
        ob["hp_key"], ob["hp_hash"], ob["hp_part"] = key, o["hash"], o["part"]
        ob.data.materials.append(bpy.data.materials.get(f"part:{o['part']}") or _material(o["part"], o["color"]))
        (_coll(f"prefab:{o['prefab']}", hide=True) if o.get("prefab") else parts).objects.link(ob)
        made.append(key)
    for c in list(bpy.data.collections):  # prefabs that are gone
        if c.name.startswith("prefab:") and not c.objects:
            bpy.data.collections.remove(c)
    keep = {i["name"] for i in job["instances"]}
    for ob in list(bpy.data.objects):
        if ob.get("hp_instance") and ob["hp_instance"] not in keep:
            bpy.data.objects.remove(ob)
    by_inst = {ob["hp_instance"]: ob for ob in bpy.data.objects if ob.get("hp_instance")}
    for i in job["instances"]:
        ob = by_inst.get(i["name"])
        if ob is None:
            ob = bpy.data.objects.new(i["name"], None)
            ob["hp_instance"] = i["name"]
            insts.objects.link(ob)
        ob.instance_type = "COLLECTION"
        ob.instance_collection = bpy.data.collections[f"prefab:{i['prefab']}"]
        ob["hp_prefab"] = i["prefab"]
        ob.matrix_world = _matrix(i["matrix"])
        ob["hp_matrix"] = [v for r in i["matrix"] for v in r]
    for key in ("prefab",):  # prefab collections excluded from the view layer (they show through instances)
        for c in bpy.data.collections:
            if c.name.startswith("prefab:"):
                lc = bpy.context.view_layer.layer_collection.children.get(c.name)
                if lc is not None:
                    lc.exclude = True
    bpy.context.scene.render.engine = "BLENDER_EEVEE"
    bpy.ops.wm.save_as_mainfile(filepath=job["blend"], compress=False)
    print("@@made", json.dumps(made))


def render(job):
    _open(job["blend"])
    scene = bpy.context.scene
    if job.get("show_layer"):  # one layer's mask on every part (not saved)
        prog = job["program"]
        for part, base in job["bases"].items():
            _paint_material(part, base, [ly for ly in prog["layers"] if part in ly["parts"] or "*" in ly["parts"]],
                            prog["quantiles"], None, prog["packing"].get(part, {}), show=job["show_layer"])
    scene.render.engine = "BLENDER_EEVEE"
    # ray-traced reflections and indirect light: without them everything indoors reflects the open sky (glossy
    # jars and cups get a bright rim) and rooms get no bounce light
    ee = scene.eevee
    ee.use_raytracing = True
    ee.ray_tracing_method = "SCREEN"
    ee.use_fast_gi = True
    ee.fast_gi_method = "GLOBAL_ILLUMINATION"
    scene.render.resolution_x = scene.render.resolution_y = job.get("size", 512)
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "AgX"
    scene.world = scene.world or bpy.data.worlds.new("w")
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.55, 0.62, 0.72, 1)
    bg.inputs["Strength"].default_value = 0.6
    ld = bpy.data.lights.new("hp_sun", "SUN")
    ld.energy, ld.angle = 3.5, 0.05
    sun = bpy.data.objects.new("hp_sun", ld)
    scene.collection.objects.link(sun)
    sun.rotation_euler = Vector(job.get("sun", [-0.4, -0.7, 0.6])).to_track_quat("Z", "Y").to_euler()
    cam_data = bpy.data.cameras.new("hp_cam")
    cam_data.clip_start, cam_data.clip_end = 0.01, 1000
    cam = bpy.data.objects.new("hp_cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    for v in job["views"]:
        d = Vector(v["dir"]).normalized()
        up = Vector(v["up"])
        right = up.cross(d).normalized()
        up = d.cross(right).normalized()
        rot = Matrix((right, up, d)).transposed().to_4x4()
        if v.get("eye") is not None:
            cam_data.type = "PERSP"
            cam_data.angle = np.radians(v["fov"])
            cam.matrix_world = Matrix.Translation(Vector(v["eye"])) @ rot
        else:
            cam_data.type = "ORTHO"
            cam_data.ortho_scale = v["scale"]
            cam.matrix_world = Matrix.Translation(Vector(v["center"]) + d * 50) @ rot
        scene.render.filepath = v["out"]
        bpy.ops.render.render(write_still=True)


def bake(job):
    """Bake a part's material (base colour, roughness) from its scene object onto a low-poly mesh with UVs, by
    Cycles "selected to active": each texel's ray hits the scene mesh and evaluates its shader there."""
    import time
    _open(job["blend"])
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = job.get("device", "CPU")
    scene.cycles.samples = job.get("samples", 4)
    z = np.load(job["low"])
    me = bpy.data.meshes.new("low")
    V, C, UV = z["verts"], z["corner_vert"], z["uv"]
    me.vertices.add(len(V))
    me.vertices.foreach_set("co", V.astype(np.float32).ravel())
    me.loops.add(len(C))
    me.loops.foreach_set("vertex_index", C.astype(np.int32))
    me.polygons.add(len(C) // 3)
    me.polygons.foreach_set("loop_start", np.arange(0, len(C), 3, dtype=np.int32))
    me.update()
    me.shade_smooth()
    uvl = me.uv_layers.new(name="UVMap")
    uvl.data.foreach_set("uv", UV.astype(np.float32).ravel())
    low = bpy.data.objects.new("low", me)
    scene.collection.objects.link(low)
    high = next(o for o in bpy.data.objects if o.get("hp_key") == job["key"])
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    high.select_set(True)
    low.select_set(True)
    bpy.context.view_layer.objects.active = low
    out = {}
    for what, kind, filter_ in (("basecolor", "DIFFUSE", {"COLOR"}), ("roughness", "ROUGHNESS", set())):
        img = bpy.data.images.new(what, job["size"], job["size"], float_buffer=False)
        img.colorspace_settings.name = "sRGB" if what == "basecolor" else "Non-Color"
        mat = bpy.data.materials.new(f"bake_{what}")
        mat.use_nodes = True
        tn = mat.node_tree.nodes.new("ShaderNodeTexImage")
        tn.image = img
        mat.node_tree.nodes.active = tn
        me.materials.clear()
        me.materials.append(mat)
        t = time.time()
        bpy.ops.object.bake(type=kind, pass_filter=filter_, use_selected_to_active=True,
                            cage_extrusion=job.get("extrusion", 0.03), max_ray_distance=job.get("ray", 0.06),
                            margin=job.get("margin", 4), target="IMAGE_TEXTURES")
        img.filepath_raw = job["out"] + f"_{what}.png"
        img.file_format = "PNG"
        img.save()
        out[what] = round(time.time() - t, 1)
    print("@@baked", json.dumps(out))


def _ao_override(distance, up, samples):
    """A material that emits the AO node's openness: around the surface normal, or looking straight up."""
    m = bpy.data.materials.new("hp_ao_up" if up else "hp_ao")
    m.use_nodes = True
    t = m.node_tree
    t.nodes.clear()
    ao = t.nodes.new("ShaderNodeAmbientOcclusion")
    ao.samples = samples
    ao.inputs["Distance"].default_value = distance
    ao.inputs["Color"].default_value = (1, 1, 1, 1)
    if up:
        cmb = t.nodes.new("ShaderNodeCombineXYZ")
        cmb.inputs[2].default_value = 1.0
        t.links.new(cmb.outputs[0], ao.inputs["Normal"])
    em = t.nodes.new("ShaderNodeEmission")
    out = t.nodes.new("ShaderNodeOutputMaterial")
    t.links.new(ao.outputs["Color"], em.inputs["Color"])
    t.links.new(em.outputs[0], out.inputs[0])
    return m


def _device(scene, device):
    if device == "GPU":
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "HIP"
        prefs.get_devices()
        for d in prefs.devices:
            d.use = d.type != "CPU"
        scene.cycles.device = "GPU"
    else:
        scene.cycles.device = "CPU"


def bake_inputs(job):
    """AO and sky openness per vertex by Cycles ray tracing, baked as emission into colour attributes, every
    object in one bake per pass (a bake call rebuilds the scene's BVH and shaders: once, not per object). Builds
    its own scene from the objects' meshes (no .blend): scene objects where they are, a prefab's parts at every
    instance (linked duplicates: they all occlude), baked at the bake instance. Writes <out>/<key>.npz {ao, sky}
    (by vertex, in the mesh file's order) and prints timings."""
    import os
    import time
    t0 = time.time()
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    _device(scene, job.get("device", "CPU"))
    scene.cycles.samples = 1
    scene.render.bake.target = "VERTEX_COLORS"
    vl = bpy.context.view_layer
    passes = {"ao": _ao_override(job["ao_distance"], False, job.get("samples", 32)),
              "sky": _ao_override(job["sky_distance"], True, job.get("samples", 32))}
    by_pf = {}
    for i in job["instances"]:
        by_pf.setdefault(i["prefab"], []).append(i)
    targets = {}
    for o in job["objects"]:
        me = _mesh(o["key"], o["mesh"])
        attr = me.color_attributes.new("hp_bake", "FLOAT_COLOR", "POINT")
        me.color_attributes.active_color = attr
        if not o.get("prefab"):
            ob = bpy.data.objects.new(o["key"], me)
            scene.collection.objects.link(ob)
            targets[o["key"]] = ob
            continue
        for i in by_pf[o["prefab"]]:
            ob = bpy.data.objects.new(f"{o['key']}@{i['name']}", me)
            scene.collection.objects.link(ob)
            ob.matrix_world = _matrix(i["matrix"])
            if i["name"] == o["bake"]:
                targets[o["key"]] = ob
    times = {"load": round(time.time() - t0, 1)}
    res = {k: {} for k in targets}
    os.makedirs(job["out"], exist_ok=True)
    for name, mat in passes.items():
        vl.material_override = mat
        for ob in scene.objects:
            ob.select_set(False)
        for t in targets.values():
            t.select_set(True)
        vl.objects.active = next(iter(targets.values()))
        t1 = time.time()
        bpy.ops.object.bake(type="EMIT", target="VERTEX_COLORS")
        times[name] = round(time.time() - t1, 1)
        for k, t in targets.items():
            a = np.empty(len(t.data.vertices) * 4, np.float32)
            t.data.color_attributes["hp_bake"].data.foreach_get("color", a)
            res[k][name] = a.reshape(-1, 4)[:, 0].copy()
    vl.material_override = None
    for k, r in res.items():
        np.savez(os.path.join(job["out"], k.replace("/", "__") + ".npz"), **r)
    print("@@times", json.dumps(times))


job = json.load(open(sys.argv[sys.argv.index("--") + 1]))
{"pull": pull, "sync": sync, "render": render, "bake": bake, "bake_inputs": bake_inputs}[job["mode"]](job)
