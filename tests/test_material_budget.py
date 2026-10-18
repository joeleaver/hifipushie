"""EEVEE material budgets. Image reuse: a re-synced scene loaded every image again per node (relative paths saved),
55 images for 26 files: "too many fragment shader texture samplers", magenta. Attribute budget (gp_h6c_s11, 2026-10-16: the skin material read 15 vertex attributes = wpos + wnrm + 13 packs of
three; EEVEE "uses too many attributes", the head rendered MAGENTA, job exit 0). Scalars now pack four to an attribute
and a part over paintnodes.MAX_ATTRS is a SpecError at compile time, naming the layers."""
import json, os, subprocess, sys, tempfile
import pytest
from hifipushie import paintnodes, store
from hifipushie.spec import SpecError

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_pack_four():
    assert paintnodes.PACK == 4 and paintnodes.MAX_ATTRS == 14
    assert paintnodes.attr_count(37) == 12          # s11's 37 inputs: 15 attributes at three a pack, 12 at four
    assert paintnodes.attr_count(48) == 14 and paintnodes.attr_count(49) == 15


def _skin_head():
    for name in ("gp_h6c_s11", "tp_k19_s17"):
        try:
            return store.load(name)
        except Exception:
            continue
    pytest.skip("no skin head in the workspace")


def test_skin_head_packs_within_budget():
    prog = paintnodes.compile(_skin_head())
    for part, pk in prog["packing"].items():
        packs = {v[0] for v in pk.values()}
        assert all(0 <= v[1] < paintnodes.PACK for v in pk.values())
        assert len(packs) + len(paintnodes.FIXED_ATTRS) <= paintnodes.MAX_ATTRS, part


def test_over_budget_is_an_error(monkeypatch):
    s = _skin_head()
    monkeypatch.setattr(paintnodes, "MAX_ATTRS", 3)
    with pytest.raises(SpecError, match="vertex attributes"):
        paintnodes.compile(s)


BLENDER_PROBE = r'''
import bpy, sys, numpy as np
sys.path.insert(0, sys.argv[-1])
from hifipushie import blender_scene as bs
bpy.ops.mesh.primitive_plane_add(size=2)
me = bpy.context.object.data
nv = len(me.vertices)
bs._inputs.__globals__  # module loaded
import tempfile, os
f = os.path.join(tempfile.mkdtemp(), "in.npz")
np.savez(f, hp0=np.tile(np.array([0.1, 0.2, 0.3, 0.4], np.float32), (nv, 1)))
bs._inputs(me, f)
print("TYPE", me.attributes["hp0"].data_type)
m = bpy.data.materials.new("x"); m.use_nodes = True
N = bs._Nodes(m.node_tree, {}, {"a": ["hp0", 0], "d": ["hp0", 3]})
N.attr("a"); N.attr("d")
print("ATTRS", sorted(bs.material_attributes(m.node_tree)))
print("ALPHA", N.attr("d").name)
'''


def test_blender_reads_four_channels():
    import shutil
    if not shutil.which("blender"):
        pytest.skip("no blender")
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "probe.py")
        open(f, "w").write(BLENDER_PROBE)
        r = subprocess.run(["blender", "-b", "--factory-startup", "--python", f, "--", os.path.join(ROOT, "src")],
                           capture_output=True, text=True, timeout=300)
        out = r.stdout
        assert "TYPE FLOAT_COLOR" in out, out[-2000:]
        assert "ATTRS ['hp0']" in out and "ALPHA Alpha" in out, out[-2000:]


IMAGE_PROBE = r'''
import bpy, sys, os, tempfile, numpy as np
sys.path.insert(0, sys.argv[-1])
from hifipushie import blender_scene as bs
d = tempfile.mkdtemp(); os.makedirs(os.path.join(d, "_images")); os.makedirs(os.path.join(d, "st"))
png = os.path.join(d, "_images", "x.png")
im = bpy.data.images.new("t", 4, 4); im.filepath_raw = png; im.file_format = "PNG"; im.save()
m = bpy.data.materials.new("x"); m.use_nodes = True; m.use_fake_user = True
N = bs._Nodes(m.node_tree, {}, {})
t = m.node_tree.nodes.new("ShaderNodeTexImage"); t.image = N.image(png, True)
blend = os.path.join(d, "st", "scene.blend")
bpy.ops.wm.save_mainfile(filepath=blend)          # paths saved relative: //../_images/x.png
bpy.ops.wm.open_mainfile(filepath=blend)
m = bpy.data.materials["x"]
N = bs._Nodes(m.node_tree, {}, {})
a, b = N.image(png, True), N.image(png, True)
print("SAME", a == b, a.name, sorted(i.name for i in bpy.data.images if i.name.startswith("hp:")))
'''


def test_image_reused_after_save():
    import shutil
    if not shutil.which("blender"):
        pytest.skip("no blender")
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "probe.py")
        open(f, "w").write(IMAGE_PROBE)
        r = subprocess.run(["blender", "-b", "--factory-startup", "--python", f, "--", os.path.join(ROOT, "src")],
                           capture_output=True, text=True, timeout=300)
        assert "SAME True hp:x:data ['hp:x:data']" in r.stdout, r.stdout[-2000:]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
