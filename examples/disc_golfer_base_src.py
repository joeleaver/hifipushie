"""The disc golfer rebuilt on the base mesh: python disc_golfer_base_src.py [examples/disc_golfer.json] [model]
The body is the template base, the head Google GNM (identity fitted to the reference's face proportions), eyeballs a
part; the blob-built body masses, face kit and hand kit are dropped; outfit, hair, beard, bag, discs, story and paint
carry over, face paint re-addressed to the base's face landmarks (lm_* joints) and eyeballs (eye.L)."""
import json
import sys

from hifipushie import store

src = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "examples/disc_golfer.json"))
name = sys.argv[2] if len(sys.argv) > 2 else "disc_golfer_base"
KEEP = ("hair_", "beard_", "moustache", "shirt_", "collar_", "shorts_", "sock", "shoe", "sole", "strap", "bag", "disc")

spec = {
    "symmetry": True, "blend": src.get("blend", 0.02),
    "base": {"template": "male_stylized", "eyes": "eyes", "girth": {"shoulder.L": 1.12, "chest": 1.06},
             "head": {"source": "gnm", "scale": 1.12, "eyes": 1.3,  # head ~1/7 of the height, as in the reference
                      # the reference's face, front view, in interocular units (widths at the ears, jaw angle and
                      # chin; eye line down to the chin, lower lip and nose base)
                      "fit": {"face_width": 2.2, "jaw_width": 1.75, "chin_width": 0.9, "eye_chin": 1.75,
                              "eye_mouth": 1.2, "eye_nose": 0.72},
                      "expression": {"left_eye_region_000": 0.9, "right_eye_region_000": 0.9,
                                     "left_eye_region_001": 0.5, "right_eye_region_001": 0.5}}},
    # the template's joints come from the base; the golfer's own (same positions) kept where the outfit uses them
    "joints": {**{k: v for k, v in src["joints"].items() if k in ("sleeve_end.L",)},
               "shoulder.L": {"pos": [0.215, 0.02, 1.4], "r": 0.05}},  # broader shoulders

    "bones": {k: v for k, v in src["bones"].items() if v.get("part")},
    "blobs": {k: v for k, v in src["blobs"].items() if k.startswith(KEEP)},
    "parts": src["parts"],
    "story": src["story"],
    "strokes": {
        "hair_part": src["strokes"]["hair_part"],
        "cargo_pocket.L": {"op": "clay", "part": "shorts", "width": 0.03, "depth": 0.008, "profile": "flat",
                           "path": [{"at": [0.14, -0.005, 0.68], "dir": [1, 0, 0]}, {"at": [0.14, -0.005, 0.59]}]},
        "brow_ridge.L": {"op": "clay", "width": 0.011, "depth": 0.0014,
                         "path": [{"at": "lm_brow_inner.L", "offset": [0, 0, 0.004], "dir": [0, -1, 0.3]},
                                  {"at": "lm_brow_mid.L", "offset": [0, 0, 0.004]},
                                  {"at": "lm_brow_outer.L", "offset": [0, 0, 0.004], "dir": [0.5, -1, 0.3]}]},
        "cheekbone.L": {"op": "clay", "width": 0.013, "depth": 0.0015,
                        "path": [{"at": "lm_eye_outer.L", "offset": [0.004, 0, -0.03], "dir": [0.4, -1, 0]},
                                 {"at": "lm_eye_outer.L", "offset": [0.026, 0.02, -0.026], "dir": [1, -0.4, 0]}]},
    },
}
# beard and moustache follow the base's face (the old blobs sat on the blob face): regions of the beard shell
spec["blobs"].update({
    "beard_jaw": {"at": "lm_chin", "offset": [0, 0.05, 0.028], "size": [0.085, 0.08, 0.05], "part": "beard"},
    "beard_side.L": {"at": "lm_jaw_2.L", "offset": [-0.008, 0.0, 0.01], "size": [0.022, 0.04, 0.05], "part": "beard"},
    "moustache": {"at": "lm_lip_upper", "offset": [0, 0, 0.009], "size": [0.03, 0.02, 0.007], "part": "beard"},
    "beard_mouth": {"at": "lm_lip_lower", "offset": [0, -0.01, 0.01], "size": [0.024, 0.03, 0.009],
                    "op": "subtract", "part": "beard"},
})
# the hair mass, carried from the blob head to the base's: about the eye line, 0.86 of the size
eye = [0.0, -0.083, 1.634]
old_eye = [0.0, src["joints"]["head"]["pos"][1] - 0.1, src["joints"]["head"]["pos"][2] - 0.004]
for k in [k for k in spec["blobs"] if k.startswith("hair_")]:
    b = dict(spec["blobs"][k])
    b["at"] = [round(e + 0.86 * (a - o), 4) for a, o, e in zip(b["at"], old_eye, eye)]
    b["size"] = [round(0.86 * x, 4) for x in b["size"]]
    spec["blobs"][k] = b
spec["strokes"]["hair_part"] = hp = json.loads(json.dumps(spec["strokes"]["hair_part"]))
for pt in hp["path"]:
    pt["at"] = [round(e + 0.86 * (a - o), 4) for a, o, e in zip(pt["at"], old_eye, eye)]
paint = dict(src["paint"])
paint["lips.L"] = {"color": "#b86a60", "roughness": 0.35, "width": 0.0055, "soft": 0.003,
                   "path": [{"at": "lm_mouth_corner.L", "dir": [0.3, -1, 0]}, {"at": "lm_lip_upper", "dir": [0, -1, 0]}]}
paint["lips_lower.L"] = {"color": "#b86a60", "roughness": 0.35, "width": 0.0065, "soft": 0.003,
                         "path": [{"at": "lm_mouth_corner.L", "dir": [0.3, -1, 0]},
                                  {"at": "lm_lip_lower", "dir": [0, -1, -0.2]}]}
for k in ("iris.L", "pupil.L", "glint.L"):
    paint[k] = json.loads(json.dumps(paint[k]).replace("face_eye.L", "eye.L"))
paint["iris.L"]["width"] = 0.0135  # the base's eyeballs are bigger than the kit's
paint["pupil.L"]["width"] = 0.0065
paint["brows.L"] = {"color": "#3a2414", "width": 0.007, "soft": 0.003,
                    "path": [{"at": "lm_brow_inner.L", "offset": [0, 0, 0.003], "dir": [0, -1, 0.3]},
                             {"at": "lm_brow_mid.L", "offset": [0, 0, 0.005]},
                             {"at": "lm_brow_outer.L", "offset": [0, 0, 0.003], "dir": [0.5, -1, 0.3]}]}
paint["skin_warm"] = {"color": "#d98f73", "opacity": 0.3,
                      "path": [{"at": "lm_nose_tip", "dir": [0, -1, 0]}], "width": 0.014, "soft": 0.02}
spec["paint"] = paint
v = store.save(name, spec, "rebuilt on the base: template body + GNM head, outfit/hair/beard/paint carried over")
print(name, "v", v)
