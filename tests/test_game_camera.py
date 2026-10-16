"""blender_game.set_fov: the field of view asked is the one rendered (Blender's `angle` setter uses the sensor size
of the fit current at the time: angle before sensor_fit = VERTICAL rendered 1.5x narrower, 2026-10-16)."""
import ast, math, shutil, subprocess, sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src/hifipushie/blender_game.py"


def test_set_fov_vertical_and_horizontal():
    if not shutil.which("blender"):
        print("  (no blender: skipped)")
        return
    tree = ast.parse(SRC.read_text())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "set_fov")
    code = "import bpy, math\n" + ast.get_source_segment(SRC.read_text(), fn) + """
c = bpy.data.cameras.new("t")
set_fov(c, 25.4, "VERTICAL"); print("VERT", math.degrees(c.angle_y))
set_fov(c, 30.0, "HORIZONTAL"); print("HORI", math.degrees(c.angle_x))
c.angle = math.radians(25.4); c.sensor_fit = "VERTICAL"; print("OLD", math.degrees(c.angle_y))
"""
    out = subprocess.run(["blender", "-b", "--factory-startup", "--python-expr", code], capture_output=True, text=True,
                         timeout=120).stdout
    got = {ln.split()[0]: float(ln.split()[1]) for ln in out.splitlines() if ln.split()[:1] in (["VERT"], ["HORI"], ["OLD"])}
    assert abs(got["VERT"] - 25.4) < 1e-3, got
    assert abs(got["HORI"] - 30.0) < 1e-3, got
    # the old order: 2 atan(12 / lens(36 mm, 25.4 deg)): the 1.5x zoom the photo camera showed
    assert abs(math.tan(math.radians(got["OLD"] / 2)) / math.tan(math.radians(12.7)) - 2 / 3) < 1e-3, got
    print("  set_fov ok", got)


if __name__ == "__main__":
    test_set_fov_vertical_and_horizontal()
