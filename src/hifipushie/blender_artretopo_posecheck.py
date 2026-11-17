"""Artist retopo, step 5 (Blender): the range of motion on rigged.blend, or LOD1's own export.
    blender -b --factory-startup --python blender_artretopo_posecheck.py -- job.json
job: dir; mode "rom" (default) or "lod";
  rom: poses (names of the standard set and / or {name: [[bone, [axis], degrees] | [bone, "aim", [direction]], ...]};
       default: the whole standard set, + "wheel_grip" when the joints hold a "wheel" {c, r, tilt} and "fingers": a
       two-bone IK grip solved by a curl search), clavicle, close (your own close-ups {name: {view, target, scale}}; "name" is a
       pose name, "name#tag" for a second view of it), close_ups (true: the standard close-ups as well).
  Writes rom.json, rom_<pose>_{front,3q}.png, lod1_<pose>.png, close_<pose>.png.
  lod: writes lod1_rigged.glb (LOD1 + the rig + the props) and lod1_rest.png.
blender_artretopo_rom.py holds the poses, the measures and the framing."""
import json
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blender_artretopo_common as C  # noqa: E402
import blender_artretopo_rom as ROM  # noqa: E402

J = C.job(); D = J["dir"]
RJ = json.load(open(f"{D}/rig.json"))
bpy.ops.wm.open_mainfile(filepath=f"{D}/rigged.blend")
sc = bpy.context.scene
body = bpy.data.objects[RJ["body"]]; rig = bpy.data.objects[RJ["rig"]]
LODS = [bpy.data.objects[n] for n in RJ["lods"]]; props = [bpy.data.objects[n] for n in RJ["props"]]
BONES = [tuple(b) for b in RJ["bones"]]; HELP = RJ["helpers"]; PFX = RJ["prefix"]
J["joints"] = RJ["joints"]
J.setdefault("clavicle", 0.3)

if J.get("mode") == "lod":
    if not LODS:
        raise SystemExit("no LOD1 in this rig (press with after > 0 makes one)")
    C.select_only(rig, *LODS, *props, active=rig)
    bpy.ops.export_scene.gltf(filepath=f"{D}/lod1_rigged.glb", use_selection=True, export_format="GLB")
    for o in sc.objects:
        if o.type == "MESH":
            o.hide_render = not (o in LODS or o in props)
    R = ROM.Rest(LODS[0]); H = R.hi[2] - R.lo[2]
    sh = C.workbench(sc, 520, colour="TEXTURE"); sh.show_cavity = False
    cam = C.ortho_camera(sc, 1.45 * H); C.aim(cam, [(a + b) / 2 for a, b in zip(R.lo, R.hi)], (-0.9, -1, 0.35))
    sc.render.filepath = f"{D}/lod1_rest.png"; bpy.ops.render.render(write_still=True)
    json.dump({"lod1_faces": len(LODS[0].data.polygons), "groups": len(LODS[0].vertex_groups)},
              open(f"{D}/lod1.json", "w"))
    print("LOD EXPORTED")
    raise SystemExit(0)

want = J.get("poses") or [n for n in ROM.POSES if n != "mouth_open_20" or "jaw" in J["joints"]]
poses = {"rest": []}
for p in want:
    if p == "wheel_grip":
        continue                    # solved below (two-bone IK + a curl search) when the joints hold a wheel
    if isinstance(p, str):
        if p not in ROM.POSES:
            raise SystemExit(f"no standard pose {p!r}: {list(ROM.POSES)}")
        poses[p] = ROM.POSES[p]
    else:
        for k, v in p.items():
            poses[k] = ROM.spec_of(v)
if "mouth_open_20" in poses and "jaw" not in J["joints"]:
    poses.pop("mouth_open_20")
WHEEL = None; grip = None
if "wheel" in J["joints"] and J["joints"].get("fingers") and (not J.get("poses") or "wheel_grip" in want):
    WHEEL = ROM.wheel_object(J["joints"])
    grip = ROM.solve_grip(rig, J, BONES, HELP, PFX); poses["wheel_grip"] = grip[2]
    print("GRIP curl", grip[1], "deg; tips", round(grip[0] * 100, 1), "cm from the rim")
rom = ROM.run(J, sc, rig, body, LODS, props, BONES, HELP, PFX, poses, wheel=WHEEL)
if grip:
    rom["wheel_grip"] = {"curl_deg": grip[1], "tips_from_rim_cm": round(grip[0] * 100, 2)}
rom["rig"] = RJ["info"]; rom["lod1"] = RJ["info"].get("lod1", {})
json.dump(rom, open(f"{D}/rom.json", "w"), indent=1)
if J.get("close_ups", True) or J.get("close"):
    ROM.close_ups(J, sc, rig, body, BONES, HELP, PFX, poses, extra=J.get("close"), standard=J.get("close_ups", True),
                  wheel=WHEEL)
print("ROM DONE")
