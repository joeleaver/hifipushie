"""The hosted runner's GPU readiness probe: renders a cube at 64 px with Workbench (clay looks) and EEVEE (painted
looks), headless, exactly as hifipushie runs Blender (-b --factory-startup), and reports what the GPU module ran on.

blender -b --factory-startup --python-exit-code 1 --python blender_probe.py -- <out dir>
Prints one line: @@probe {"workbench": "ok" | error, "eevee": "ok" | error, "backend", "vendor", "renderer",
"version"}. "ok" means an image came out with the cube in it (not a blank frame).
"""

import json
import os
import sys

import bpy


def scene():
    for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.cameras, bpy.data.lights):
        for item in list(coll):
            coll.remove(item)
    s = bpy.context.scene
    bpy.ops.mesh.primitive_cube_add()
    cam = bpy.data.objects.new("probe_cam", bpy.data.cameras.new("probe_cam"))
    s.collection.objects.link(cam)
    cam.location = (4.0, -4.0, 3.0)
    cam.rotation_euler = (1.1, 0.0, 0.785)
    s.camera = cam
    sun = bpy.data.objects.new("probe_sun", bpy.data.lights.new("probe_sun", "SUN"))
    s.collection.objects.link(sun)
    sun.rotation_euler = (0.6, 0.2, 0.4)
    s.render.resolution_x = s.render.resolution_y = 64
    s.render.resolution_percentage = 100
    return s


def render(s, engine: str, path: str) -> str:
    try:
        s.render.engine = engine
        if engine == "BLENDER_EEVEE":
            s.eevee.taa_render_samples = 1
        s.render.filepath = path
        bpy.ops.render.render(write_still=True)
        if not os.path.exists(path):
            return "no image written"
        img = bpy.data.images.load(path)
        px = list(img.pixels)
        lum = [px[i] + px[i + 1] + px[i + 2] for i in range(0, len(px), 4)]
        if max(lum) - min(lum) < 0.05:
            return "blank image (the cube didn't render)"
        return "ok"
    except Exception as e:  # (the probe reports; it never fails the runner)
        return f"{type(e).__name__}: {e}"[:500]


def main():
    out = sys.argv[sys.argv.index("--") + 1]
    s = scene()
    res = {"workbench": render(s, "BLENDER_WORKBENCH", os.path.join(out, "workbench.png")),
           "eevee": render(s, "BLENDER_EEVEE", os.path.join(out, "eevee.png"))}
    try:
        import gpu
        res.update(backend=gpu.platform.backend_type_get(), vendor=gpu.platform.vendor_get(),
                   renderer=gpu.platform.renderer_get(), version=gpu.platform.version_get())
    except Exception as e:
        res["gpu_error"] = f"{type(e).__name__}: {e}"[:300]
    print("@@probe " + json.dumps(res), flush=True)


main()
