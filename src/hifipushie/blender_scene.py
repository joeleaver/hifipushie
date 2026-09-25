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


def _open(path, live=False):
    """Open the scene file (headless). In a live session (a person's running Blender, which has this file open)
    the scene is already the one in memory: nothing to open."""
    import os
    if live:
        return
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
    height = None  # painted relief (paint.bump): the layers' height x mask, summed (m)
    for i, ly in enumerate(layers):
        N.x = 400 * (i + 1)
        mask = N.stack(ly["entries"])
        if ly.get("height"):
            hm = N.math("MULTIPLY", N.math("MAXIMUM", N.math("MINIMUM", mask, 1.0), 0.0), ly["height"]) \
                if not isinstance(mask, float) else ly["height"] * mask
            height = hm if height is None else N.math("ADD", height, hm)
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
    tr, al = float(base.get("transmission", 0.0)), float(base.get("alpha", 1.0))
    if tr > 0:  # glass: light through it (EEVEE refracts with ray tracing; dithered so it sorts per pixel)
        bsdf.inputs["Transmission Weight"].default_value = tr
        bsdf.inputs["IOR"].default_value = float(base.get("ior", 1.45))
        m.use_raytrace_refraction = True
        m.surface_render_method = "DITHERED"
    if al < 1:  # see-through by coverage (a fade, a gauze curtain)
        bsdf.inputs["Alpha"].default_value = al
        m.surface_render_method = "BLENDED"
    if height is not None:  # shading shows the relief; the export bakes the height itself (_emit "height")
        hn = N.node("ShaderNodeMath", operation="ADD", name="hp_height")
        N._in(hn.inputs[0], height)
        hn.inputs[1].default_value = 0.0
        bump = N.node("ShaderNodeBump")
        bump.inputs["Distance"].default_value = 1.0
        t.links.new(hn.outputs[0], bump.inputs["Height"])
        t.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    t.links.new(bsdf.outputs[0], out.inputs[0])
    m["hp_prog"] = prog_hash
    return m


def _mesh(name, path):
    z = np.load(path)
    return _mesh_from(name, z["verts"], z["faces"], z["normals"] if "normals" in z else None)


def _mesh_from(name, verts, faces, normals=None):
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", verts.astype(np.float32).ravel())
    me.loops.add(faces.size)
    me.loops.foreach_set("vertex_index", faces.astype(np.int32).ravel())
    me.polygons.add(len(faces))
    me.polygons.foreach_set("loop_start", np.arange(0, faces.size, 3, dtype=np.int32))
    me.update()
    me.shade_smooth()
    if normals is not None:
        me.normals_split_custom_set_from_vertices(normals.astype(np.float64))
    return me


def _split(path, subset):
    """An object's mesh arrays as two sets of faces: those touching `subset` (vertex indices; None = all: to bake)
    and the rest (occluders only). Returns (V, N, target faces, rest faces)."""
    z = np.load(path)
    V, F, N = z["verts"], z["faces"], z["normals"]
    if subset is None:
        return V, N, F, F[:0]
    mark = np.zeros(len(V), bool)
    mark[np.asarray(subset, np.int64)] = True
    hit = mark[F].any(1)
    return V, N, F[hit], F[~hit]


def _compact(V, N, F):
    used = np.unique(F)
    remap = np.full(len(V), -1, np.int64)
    remap[used] = np.arange(len(used))
    return V[used], N[used], remap[F], used


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
    _open(job["blend"], job.get("live"))
    bpy.context.view_layer.update()  # a live session's moves reach matrix_world only after an update
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
    _open(job["blend"], job.get("live"))
    prog = job.get("program")
    rebuilt = []
    if prog:
        ph = job["prog_hash"]
        for part, base in job["bases"].items():
            h = ph.get(part) if isinstance(ph, dict) else ph  # per part: only parts whose layers changed rebuild
            m = bpy.data.materials.get(f"part:{part}")
            if m is None or m.get("hp_prog") != h:
                rebuilt.append(part)
            _paint_material(part, base, [ly for ly in prog["layers"] if part in ly["parts"] or "*" in ly["parts"]],
                            prog["quantiles"], h, prog["packing"].get(part, {}))
    print("@@rebuilt", json.dumps(rebuilt))
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
    hide = set(job.get("hide") or ())
    for ob in bpy.data.objects:  # parts left out (scene objects and prefab sources alike: instances follow)
        if ob.get("hp_part") in hide:
            ob.hide_render = True
    if job.get("flat"):  # unlit colour: each material's base colour straight out
        for m in bpy.data.materials:
            if m.get("hp_prog") and m.node_tree:
                _emit(m, "color")
    scene.render.engine = "BLENDER_EEVEE"
    # ray-traced reflections and indirect light: without them everything indoors reflects the open sky (glossy
    # jars and cups get a bright rim) and rooms get no bounce light
    ee = scene.eevee
    ee.use_raytracing = True
    ee.ray_tracing_method = "SCREEN"
    ee.use_fast_gi = True
    ee.fast_gi_method = "GLOBAL_ILLUMINATION"
    scene.render.resolution_x = scene.render.resolution_y = job.get("size", 512)
    scene.render.film_transparent = bool(job.get("show_layer"))  # alpha: surface vs sky, for coverage
    scene.render.image_settings.color_mode = "RGBA" if job.get("show_layer") else "RGB"
    scene.view_settings.view_transform = "Standard" if job.get("flat") else "AgX"
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


def _low(name, path):
    """A low-poly export part from its npz (verts, corner_vert, uv, normal per corner) as an object with UVs."""
    z = np.load(path)
    V, C, UV = z["verts"], z["corner_vert"], z["uv"]
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(V))
    me.vertices.foreach_set("co", V.astype(np.float32).ravel())
    me.loops.add(len(C))
    me.loops.foreach_set("vertex_index", C.astype(np.int32))
    me.polygons.add(len(C) // 3)
    me.polygons.foreach_set("loop_start", np.arange(0, len(C), 3, dtype=np.int32))
    me.update()
    me.shade_smooth()
    me.normals_split_custom_set(z["normal"].astype(np.float64))  # rays leave along the exported normals
    me.uv_layers.new(name="UVMap").data.foreach_set("uv", UV.astype(np.float32).ravel())
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


HEIGHT_SCALE = 25.0  # painted height baked as 0.5 + h x 25: +-20 mm fits in 0..1


def _emit(mat, what):
    """Point a part material's output at an emission of what it computes: "color" (the base colour), "rms"
    (roughness, metallic, specular as RGB) or "aoh" (red: the ao_raw vertex attribute, green: painted relief in m
    as 0.5 + height x HEIGHT_SCALE). Emission sampling is off: an emissive material otherwise makes every
    triangle a light, and Cycles builds a light tree over millions of them on every bake call (~5 s each)."""
    t = mat.node_tree
    bsdf = next(n for n in t.nodes if n.type == "BSDF_PRINCIPLED")
    out = next(n for n in t.nodes if n.type == "OUTPUT_MATERIAL")
    em = t.nodes.get("hp_bake_em") or t.nodes.new("ShaderNodeEmission")
    em.name = "hp_bake_em"
    em.inputs["Strength"].default_value = 1.0
    mat.cycles.emission_sampling = "NONE"

    def feed(sock, name):
        inp = bsdf.inputs[name]
        if inp.is_linked:
            t.links.new(inp.links[0].from_socket, sock)
        else:
            v = inp.default_value
            sock.default_value = tuple(v) if hasattr(v, "__len__") and len(sock.default_value) == len(v) else v
    for link in list(em.inputs["Color"].links):
        t.links.remove(link)
    if what == "color":
        feed(em.inputs["Color"], "Base Color")
    else:
        cc = t.nodes.get("hp_bake_cc") or t.nodes.new("ShaderNodeCombineColor")
        cc.name = "hp_bake_cc"
        if what == "rms":
            for i, name in enumerate(("Roughness", "Metallic", "Specular IOR Level")):
                for link in list(cc.inputs[i].links):
                    t.links.remove(link)
                feed(cc.inputs[i], name)
        elif what == "aoh":  # red: the ao_raw vertex attribute, green: painted height (as for "height")
            hn = t.nodes.get("hp_height")
            sc = t.nodes.get("hp_bake_hs") or t.nodes.new("ShaderNodeMath")
            sc.name, sc.operation = "hp_bake_hs", "MULTIPLY_ADD"
            sc.inputs[1].default_value, sc.inputs[2].default_value = HEIGHT_SCALE, 0.5
            if hn is not None:
                t.links.new(hn.outputs[0], sc.inputs[0])
            else:
                sc.inputs[0].default_value = 0.0
            at = t.nodes.get("hp_bake_ao") or t.nodes.new("ShaderNodeAttribute")
            at.name, at.attribute_type, at.attribute_name = "hp_bake_ao", "GEOMETRY", "ao_raw"
            for link in list(cc.inputs[2].links):
                t.links.remove(link)
            t.links.new(at.outputs["Fac"], cc.inputs[0])
            t.links.new(sc.outputs[0], cc.inputs[1])
            cc.inputs[2].default_value = 0.0
        t.links.new(cc.outputs[0], em.inputs["Color"])
    t.links.new(em.outputs[0], out.inputs["Surface"])


def bake_maps(job):
    """The export's paint maps from the scene's materials, by Cycles "selected to active": each texel's ray from
    the low poly (along its exported normal, from `extrusion` out, up to `ray`) hits its own part's scene mesh
    and evaluates the material there. Per atlas, three float images: color (linear), rms (roughness, metallic,
    specular) and ao (the scene's raw Cycles AO, which only the part's own asset casts). One part at a time, only
    its own scene mesh selected, so a log never picks up the chinking beside it. Writes <out>/atlas<i>.npz
    {color, rms, ao} (rows top first, as the PNGs) and prints timings."""
    import time
    t0 = time.time()
    _open(job["blend"])
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    _device(scene, job.get("device", "CPU"))
    scene.cycles.samples = job.get("samples", 4)
    scene.render.bake.use_clear = False
    scene.render.bake.margin = 0  # our own dilation fills around every island afterwards
    by_key = {ob["hp_key"]: ob for ob in bpy.data.objects if ob.get("hp_key")}
    highs = {}
    for pt in job["parts"]:
        src = by_key[pt.get("scene_key", pt["key"])]  # a part split for the atlases bakes from its whole
        if pt.get("matrix") is not None:  # a prefab's part: its mesh at the bake instance
            ob = bpy.data.objects.new(pt["key"] + "@bake", src.data)
            scene.collection.objects.link(ob)
            from mathutils import Matrix
            ob.matrix_world = Matrix(pt["matrix"])
            highs[pt["key"]] = ob
        else:
            highs[pt["key"]] = src
    imgs = {}
    WHAT = ("color", "rms", "aoh")  # ao and painted height share a pass (red, green)
    for ai, size in job["atlases"].items():
        for what in WHAT:
            im = bpy.data.images.new(f"a{ai}_{what}", size, size, alpha=True, float_buffer=True)
            im.colorspace_settings.name = "Non-Color"
            im.generated_color = (0, 0, 0, 0)
            imgs[(ai, what)] = im
    lows = {pt["key"]: _low("low_" + pt["key"], pt["low"]) for pt in job["parts"]}
    bm = bpy.data.materials.new("hp_bake_target")
    bm.use_nodes = True
    tex = bm.node_tree.nodes.new("ShaderNodeTexImage")
    bm.node_tree.nodes.active = tex
    for low in lows.values():
        low.data.materials.append(bm)
    # Each bake call syncs every renderable object to Cycles (BVH and all): render only the pair being baked.
    # Rays only ever hit the selected high mesh, so what the others would add is set-up time, not texels.
    everything = list(scene.objects)
    times = {}
    for what in WHAT:
        for m in {mat for ob in highs.values() for mat in ob.data.materials if mat}:
            _emit(m, what)
        t1 = time.time()
        for i, pt in enumerate(job["parts"]):
            hi, lo = highs[pt["key"]], lows[pt["key"]]
            for ob in everything:
                ob.hide_render = ob is not hi and ob is not lo
                ob.select_set(False)
            hi.hide_render = lo.hide_render = False
            tex.image = imgs[(str(pt["atlas"]), what)]
            hi.select_set(True)
            lo.select_set(True)
            bpy.context.view_layer.objects.active = lo
            bpy.ops.object.bake(type="EMIT", use_selected_to_active=True, cage_extrusion=pt["extrusion"],
                                max_ray_distance=pt["ray"], margin=0, use_clear=False, target="IMAGE_TEXTURES")
            print(f"@@progress {what} {i + 1}/{len(job['parts'])} {pt['key']} {time.time() - t1:.0f}s", flush=True)
        times[what] = round(time.time() - t1, 1)
    for ai, size in job["atlases"].items():
        out = {}
        for what in WHAT:
            a = np.empty(size * size * 4, np.float32)
            imgs[(ai, what)].pixels.foreach_get(a)
            out[what] = a.reshape(size, size, 4)[::-1]  # Blender's rows start at the bottom
        aoh = out.pop("aoh")
        out["ao"] = aoh[..., [0, 0, 0, 3]]
        out["height"] = aoh[..., [1, 1, 1, 3]]
        np.savez(f"{job['out']}/atlas{ai}.npz", **out)
    times["total"] = round(time.time() - t0, 1)
    print("@@times", json.dumps(times))


def _ao_override(ao_distance, sky_distance, samples):
    """A material that emits both openings in one colour: red = AO around the surface normal, green = sky
    (AO looking straight up), so one bake measures both (each bake call has ~20 s of fixed cost). Emission
    sampling off: every triangle of an emissive material is otherwise a light in a tree Cycles rebuilds per call."""
    m = bpy.data.materials.new("hp_ao_sky")
    m.use_nodes = True
    m.cycles.emission_sampling = "NONE"
    t = m.node_tree
    t.nodes.clear()
    outs = []
    for dist, up in ((ao_distance, False), (sky_distance, True)):
        ao = t.nodes.new("ShaderNodeAmbientOcclusion")
        ao.samples = samples
        ao.inputs["Distance"].default_value = dist
        ao.inputs["Color"].default_value = (1, 1, 1, 1)
        if up:
            cmb = t.nodes.new("ShaderNodeCombineXYZ")
            cmb.inputs[2].default_value = 1.0
            t.links.new(cmb.outputs[0], ao.inputs["Normal"])
        outs.append(ao.outputs["AO"])
    rgb = t.nodes.new("ShaderNodeCombineColor")
    t.links.new(outs[0], rgb.inputs[0])
    t.links.new(outs[1], rgb.inputs[1])
    em = t.nodes.new("ShaderNodeEmission")
    out = t.nodes.new("ShaderNodeOutputMaterial")
    t.links.new(rgb.outputs[0], em.inputs["Color"])
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
    """AO and sky openness per vertex by Cycles, baked as emission into a colour attribute (red AO, green sky). No
    input depends on where anything movable stands (an engine lights the assets; baked shadows of a chair on the
    floor would be wrong the moment it moves):
      1. the building (objects that aren't prefab instances): AO and sky among its own parts, props absent;
      2. props' AO: each prefab (all its parts) alone, parked in a slot far from everything: self-occlusion only;
      3. props' sky: at their bake instance under the building (whether rain reaches them where they stand).
    Everything baked in a pass is ONE mesh in world space (Cycles bakes selected objects one by one with seconds
    of set-up each). An object with a "subset" (vertex indices) bakes only the faces touching it; the rest of it
    stays as an occluder. Writes <out>/<key>.npz {idx (vertex indices in the mesh file), ao, sky}."""
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
    mat = _ao_override(job["ao_distance"], job["sky_distance"], job.get("samples", 32))
    mats = {i["name"]: np.asarray(i["matrix"], float) for i in job["instances"]}
    slot = 3.0 * job["sky_distance"] + 10.0
    groups = {"static": [], "slot": [], "real": []}  # target pieces: (key, V, N, F, used)
    rests = {"static": [], "slot": [], "real": []}  # occluder objects

    def xform(V, N, M, shift=None):
        v = V @ M[:3, :3].T + M[:3, 3]
        n = N @ np.linalg.inv(M[:3, :3])
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
        if shift is not None:
            v = v + shift
        return v, n

    def occluder(where, name, V, N, F):
        if len(F):
            v, n, f, _ = _compact(V, N, F)
            ob = bpy.data.objects.new(name, _mesh_from(name, v, f, n))
            scene.collection.objects.link(ob)
            rests[where].append(ob)
    pf_slot = {}
    for o in job["objects"]:
        sub = o.get("subset")
        if isinstance(sub, str):
            sub = np.load(sub)
        V, N, F_t, F_r = _split(o["mesh"], sub)
        if not o.get("prefab"):
            occluder("static", o["key"] + "_rest", V, N, F_r)
            if len(F_t):
                groups["static"].append((o["key"], V, N, F_t))
            continue
        M = mats[o["bake"]]
        k = pf_slot.setdefault(o["prefab"], len(pf_slot) + 1)
        for where, shift in (("slot", np.array([k * slot, 0.0, 0.0])), ("real", None)):
            v, n = xform(V.astype(np.float64), N.astype(np.float64), M, shift)
            occluder(where, f"{o['key']}_rest_{where}", v, n, F_r)
            if len(F_t):
                groups[where].append((o["key"], v, n, F_t))

    def merged(where):
        if not groups[where]:
            return None, {}
        tv, tn, tf, spans = [], [], [], {}
        for key, V, N, F in groups[where]:
            v, n, f, used = _compact(V, N, F)
            base = sum(len(x) for x in tv)
            spans[key] = (base, len(v), used)
            tv.append(v)
            tn.append(n)
            tf.append(f + base)
        me = _mesh_from("hp_targets_" + where, np.concatenate(tv), np.concatenate(tf), np.concatenate(tn))
        me.color_attributes.active_color = me.color_attributes.new("hp_bake", "FLOAT_COLOR", "POINT")
        ob = bpy.data.objects.new("hp_targets_" + where, me)
        scene.collection.objects.link(ob)
        return ob, spans
    tgt = {w: merged(w) for w in groups}
    times = {"load": round(time.time() - t0, 1)}
    vl.material_override = mat
    res = {}
    # pass: (target set, occluder sets visible, which channels it gives)
    for where, visible, chans in (("static", ("static",), ("ao", "sky")), ("slot", ("slot",), ("ao",)),
                                  ("real", ("static", "real"), ("sky",))):
        ob, spans = tgt[where]
        if ob is None:
            continue
        show = {ob} | {x for w in visible for x in rests[w]} | {tgt[w][0] for w in visible if tgt[w][0] is not None}
        for x in scene.objects:
            x.hide_render = x not in show
            x.select_set(False)
        ob.select_set(True)
        vl.objects.active = ob
        t1 = time.time()
        bpy.ops.object.bake(type="EMIT", target="VERTEX_COLORS")
        times[where] = round(time.time() - t1, 1)
        a = np.empty(len(ob.data.vertices) * 4, np.float32)
        ob.data.color_attributes["hp_bake"].data.foreach_get("color", a)
        a = a.reshape(-1, 4)
        for key, (b0, n, used) in spans.items():
            r = res.setdefault(key, {"idx": used})
            for c in chans:
                r[c] = a[b0:b0 + n, 0 if c == "ao" else 1].copy()
    vl.material_override = None
    os.makedirs(job["out"], exist_ok=True)
    for key, r in res.items():
        np.savez(os.path.join(job["out"], key.replace("/", "__") + ".npz"), **r)
    print("@@times", json.dumps(times))


MODES = {"pull": pull, "sync": sync, "render": render, "bake_maps": bake_maps, "bake_inputs": bake_inputs}

if __name__ == "__main__" and "--" in sys.argv:  # run as a script by headless Blender; imported in a live session
    job = json.load(open(sys.argv[sys.argv.index("--") + 1]))
    MODES[job["mode"]](job)
