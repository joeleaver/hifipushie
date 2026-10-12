"""start.py [variant]: gg_R<v> (a references holder: Garrett's BODY from gj_G00 = the class-mean start of garrett_a1's
lineage, the old face style eye_spacing dropped, the GOOD head set as views) and gg_<v>00 = block_in_start on it (male
class mean, cameras fitted on these pictures). Nothing is read from or written to any existing Garrett model's face.
Variants: G = front, 3/4, "profile" with 8 clicks (yaw -90); C = front + 3/4 only; D = the "profile" picture as a
60 deg turned view (the detector finds the face in it), its clicks kept."""
import copy, json, sys
from hifipushie import store, server, blockin as bi

V = sys.argv[1] if len(sys.argv) > 1 else "G"
R = "/home/joe/dev/s0urc3/docs/img/garrett_ref_full/garrett_head_"
CLICKS = {"nose_tip": [207, 671], "nose_base": [266, 722], "nose_bridge": [283, 558], "lip_upper": [261, 768],
          "lip_lower": [269, 806], "chin": [296, 925], "eye_outer.L": [395, 567], "mouth_corner.L": [350, 790]}
VIEWS = [
    {"image": R + "front.png", "size": [1152, 1536], "yaw": 0, "points": {}},
    {"image": R + "three_quarter_left.png", "size": [1152, 1536], "yaw": 45, "points": {}},
    # a profile gets no detector points: clicked on a pixel grid (spikes/garrettgood/grid.py)
    {"image": R + "profile_left.png", "size": [1152, 1536], "yaw": -90, "points": CLICKS},
]
if V == "C":
    VIEWS = VIEWS[:2]
if V == "D":
    VIEWS[2] = {**VIEWS[2], "yaw": 60}
sp = copy.deepcopy(store.load("gj_G00"))
sp["base"]["style"]["human"].pop("eye_spacing", None)   # a hand style from the paintings: not carried
for k in ("hair", "cloth"):
    sp.pop(k, None)
holder = "gg_R" if V == "G" else f"gg_R{V}"
d = store._dir(holder); d.mkdir(parents=True, exist_ok=True)
(d / "spec.json").write_text(json.dumps(sp))
VIEWS = bi.with_anchor_points(VIEWS)   # the detector's lm17..67 on the front and the turned views: the solve's anchors' names
(d / "human_refs.json").write_text(json.dumps({"views": VIEWS, "cameras": [None] * len(VIEWS)}))
r = server.block_in_start(f"gg_{V}00", holder, sex="male", age=52, cameras="refit", replace=True,
                          save=f"/mnt/data/hifipushie/garrettgood/out/gg_{V}00.png")
print("\n".join(x for x in r if isinstance(x, str)))
