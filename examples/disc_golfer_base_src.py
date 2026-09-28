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
    # a middle-aged, slightly plump body (the template is heroic): muscle smoothed away, thicker waist, thinner arms,
    # a soft belly, love handles, softer chest, smaller deltoids, a little roundness across the upper back
    "base": {"template": "male_stylized", "eyes": "eyes", "soften": 2.5,
             "girth": {"pelvis": 1.14, "chest": 1.03, "hip.L": 1.06, "shoulder.L": 0.93},
             "push": [{"at": [0, -0.1, 1.02], "radius": 0.16, "amount": 0.035},
                      {"at": [0.13, 0.0, 1.0], "radius": 0.09, "amount": 0.012},
                      {"at": [0.07, -0.1, 1.24], "radius": 0.07, "amount": 0.006},
                      {"at": [0, 0.08, 1.0], "radius": 0.12, "amount": 0.006},
                      {"at": [0.215, 0.015, 1.37], "radius": 0.075, "amount": -0.011},
                      {"at": [0.1, 0.06, 1.42], "radius": 0.08, "amount": 0.006}],
             "head": {"source": "gnm", "scale": 1.12, "eyes": 1.3,  # head ~1/7 of the height, as in the reference
                      # the reference's face, front view, in interocular units (widths at the ears, jaw angle and
                      # chin; eye line down to the chin, lower lip and nose base); a fuller lower face (older)
                      "fit": {"face_width": 2.25, "jaw_width": 1.85, "chin_width": 0.95, "eye_chin": 1.8,
                              "eye_mouth": 1.22, "eye_nose": 0.72},
                      "expression": {"left_eye_region_000": 0.9, "right_eye_region_000": 0.9,
                                     "left_eye_region_001": 0.5, "right_eye_region_001": 0.5}}},
    # the template's joints come from the base; the golfer's own (same positions) kept where the outfit uses them
    "joints": {**{k: v for k, v in src["joints"].items() if k in ("sleeve_end.L",)},
               "shoulder.L": {"pos": [0.198, 0.008, 1.39], "r": 0.05}},  # slightly rounded shoulders

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
# the beard is paint (short stubble, the user: "texture only"): no beard part or shell
for k in [k for k in spec["blobs"] if k.startswith(("beard_", "moustache"))]:
    del spec["blobs"][k]
# the hair: a mass on the base's skull (measured: half-width 0.082 and front/back -0.117/+0.101 at z 1.66, top 1.75):
# a cap ~7 mm over the skull (short sides), volume on top toward the front, a swept quiff, the face, ears and nape
# cut out of it
for k in [k for k in spec["blobs"] if k.startswith("hair_")]:
    del spec["blobs"][k]
spec["blobs"].update({
    "hair_cap": {"at": [0, -0.005, 1.672], "size": [0.089, 0.118, 0.092], "part": "hair", "blend": 0.02},
    "hair_top": {"at": [0, -0.028, 1.738], "size": [0.068, 0.09, 0.034], "rot": [-8, 0, 0], "part": "hair",
                 "blend": 0.025},
    "hair_quiff": {"at": [0.012, -0.082, 1.748], "size": [0.056, 0.04, 0.028], "rot": [-25, 0, -8], "part": "hair",
                   "blend": 0.02},
    "hair_face": {"at": [0, -0.135, 1.632], "shape": "box", "size": [0.084, 0.06, 0.062], "round": 0.035,
                  "op": "subtract", "part": "hair", "blend": 0.012},
    "hair_ear.L": {"at": [0.092, -0.012, 1.6], "size": [0.03, 0.05, 0.042], "op": "subtract", "part": "hair",
                   "blend": 0.01},
    "hair_nape": {"at": [0, 0.06, 1.555], "shape": "box", "size": [0.1, 0.07, 0.05], "round": 0.02,
                  "op": "subtract", "part": "hair", "blend": 0.015},
})
spec["strokes"]["hair_part"] = {"op": "crease", "part": "hair", "width": 0.004, "depth": [0.002, 0.004, 0.001],
                                "path": [{"at": [0.034, -0.1, 1.77], "dir": [0, -0.3, 1]}, {"at": [0.038, -0.02, 1.785]},
                                         {"at": [0.04, 0.05, 1.76]}]}
# the outfit, resized for the template's body: shirt a little wider (it left the armpits open), bigger shoes
spec["blobs"]["shirt_torso"]["size"] = [0.23, 0.2, 0.33]
spec["blobs"]["shoe.L"].update({"at": [0.105, -0.05, 0.046], "size": [0.066, 0.162, 0.062]})
spec["blobs"]["sole.L"].update({"at": [0.105, -0.05, 0.017], "size": [0.06, 0.157, 0.018]})
# the sleeve along the template's upper arm (from the moved shoulder), a little fuller: it left the armhole open
spec["joints"]["sleeve_end.L"] = {"pos": [0.252, 0.023, 1.31], "r": 0.01}
spec["bones"]["sleeve.L"] = {**spec["bones"]["sleeve.L"], "r_a": 0.095, "r_b": 0.08}
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
paint["hair_tone"] = {"part": ["hair"], "color": "#24150b", "opacity": 0.35,
                      "noise": {"scale": 0.004, "range": [0.45, 0.65], "stretch": {"dir": [0, 1, 0.15], "factor": 12}}}
# stubble: jaw line, chin, upper lip and the cheeks below the cheekbones, densest on chin and moustache, fading
# softly at the cheek and down the neck; speckled by fine noise, a little height
J = "lm_jaw_"
paint["stubble.L"] = {
    "color": "#2a1a10", "opacity": 0.62, "roughness": 0.7, "height": 0.00025,
    "mask": [
        {"path": [{"at": J + "1.L", "dir": [1, 0, 0]}, {"at": J + "3.L", "dir": [0.8, -0.2, -0.4]},
                  {"at": J + "5.L", "dir": [0.5, -0.5, -0.6]}, {"at": J + "7.L", "dir": [0.2, -0.8, -0.5]},
                  {"at": "lm_chin", "dir": [0, -0.8, -0.5]}], "width": 0.02, "profile": "soft"},
        {"path": [{"at": J + "2.L", "offset": [-0.018, -0.03, 0.012], "dir": [0.7, -0.7, 0]},
                  {"at": "lm_mouth_corner.L", "offset": [0.018, 0.004, 0.002], "dir": [0.5, -1, 0]}],
         "width": 0.018, "profile": "soft", "blend": "max", "weight": 0.8},
        {"path": [{"at": "lm_mouth_corner.L", "offset": [0.002, 0, 0.006], "dir": [0.3, -1, 0]},
                  {"at": "lm_lip_upper", "offset": [0, 0, 0.008], "dir": [0, -1, 0]}], "width": 0.007,
         "profile": "soft", "blend": "max"},
        {"path": [{"at": "lm_lip_lower", "offset": [0, 0, -0.016], "dir": [0, -1, -0.3]}], "width": 0.016,
         "profile": "soft", "blend": "max"},
        {"path": [{"at": J + "5.L", "offset": [-0.01, 0.02, -0.022], "dir": [0, -0.2, -1]},
                  {"at": "lm_chin", "offset": [0, 0.03, -0.028], "dir": [0, -0.2, -1]}], "width": 0.02,
         "profile": "soft", "blend": "max", "weight": 0.6},
        {"blur": 0.006},
        {"noise": {"scale": 0.0012, "range": [0.3, 0.75]}, "blend": "multiply", "weight": 0.7},
    ]}
spec["paint"] = paint
spec["parts"] = {k: v for k, v in spec["parts"].items() if k != "beard"}
paint.pop("beard_skin", None)
v = store.save(name, spec, "rebuilt on the base: template body + GNM head, outfit/hair/beard/paint carried over")
print(name, "v", v)
