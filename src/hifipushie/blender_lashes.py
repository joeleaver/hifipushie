"""Inside Blender: the eyelash ribbons (lashes.py) as one mesh object, "hp_lashes", replaced when their key changes.
Its material: the per-vertex colour (upper / lower), a little darker at the roots, roughness from the spec, two-sided."""
import bpy
import numpy as np

NAME = "hp_lashes"


def _material(rough: float):
    m = bpy.data.materials.get("hp_lashes") or bpy.data.materials.new("hp_lashes")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    col = nt.nodes.new("ShaderNodeAttribute")
    col.attribute_name = "hp_col"
    along = nt.nodes.new("ShaderNodeAttribute")
    along.attribute_name = "hp_along"
    # roots a little darker (denser pigment where the lash leaves the follicle), tips a touch paler
    ramp = nt.nodes.new("ShaderNodeMapRange")
    nt.links.new(along.outputs["Fac"], ramp.inputs["Value"])
    ramp.inputs["To Min"].default_value = 0.8
    ramp.inputs["To Max"].default_value = 1.25
    mul = nt.nodes.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs["Factor"].default_value = 1.0
    nt.links.new(col.outputs["Color"], mul.inputs["A"])
    comb = nt.nodes.new("ShaderNodeCombineColor")
    for k in ("Red", "Green", "Blue"):
        nt.links.new(ramp.outputs["Result"], comb.inputs[k])
    nt.links.new(comb.outputs["Color"], mul.inputs["B"])
    nt.links.new(mul.outputs["Result"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Specular IOR Level"].default_value = 0.5
    nt.links.new(bsdf.outputs[0], out.inputs[0])
    m.use_backface_culling = False
    return m


def show(entry: dict) -> list:
    """(Re)make the lash object from the job entry {"key", "npz", "roughness"}; nothing if it is current."""
    ob = bpy.data.objects.get(NAME)
    if entry is None:
        if ob is not None:
            bpy.data.objects.remove(ob)
            return [NAME]
        return []
    if ob is not None and ob.get("hp_lash_key") == entry["key"]:
        return []
    if ob is not None:
        me_old = ob.data
        bpy.data.objects.remove(ob)
        bpy.data.meshes.remove(me_old)
    z = np.load(entry["npz"])
    V, T = z["verts"], z["tris"]
    me = bpy.data.meshes.new(NAME)
    me.vertices.add(len(V))
    me.vertices.foreach_set("co", V.astype(np.float32).ravel())
    me.loops.add(len(T) * 3)
    me.loops.foreach_set("vertex_index", T.astype(np.int32).ravel())
    me.polygons.add(len(T))
    me.polygons.foreach_set("loop_start", np.arange(0, len(T) * 3, 3, dtype=np.int32))
    me.update()
    me.validate()
    uvl = me.uv_layers.new(name="UVMap")
    lv = np.empty(len(me.loops), np.int32)
    me.loops.foreach_get("vertex_index", lv)
    uvl.data.foreach_set("uv", z["uv"][lv].astype(np.float32).ravel())
    a = me.attributes.new("hp_col", "FLOAT_COLOR", "POINT")
    a.data.foreach_set("color", np.c_[z["col"], np.ones(len(V))].astype(np.float32).ravel())
    a = me.attributes.new("hp_along", "FLOAT", "POINT")
    a.data.foreach_set("value", z["along"].astype(np.float32))
    me.shade_smooth()
    if len(V) == len(me.vertices):
        me.normals_split_custom_set_from_vertices(z["normal"].astype(np.float32).tolist())
    me.materials.append(_material(float(entry.get("roughness", 0.42))))
    ob = bpy.data.objects.new(NAME, me)
    ob["hp_lash_key"] = entry["key"]
    ob["hp_lashes"] = 1
    bpy.context.scene.collection.objects.link(ob)
    return [NAME]
