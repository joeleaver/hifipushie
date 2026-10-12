"""start.py: gg_R (a references holder: Garrett's BODY from gj_G00 = the class-mean start of garrett_a1's lineage, the old
face style eye_spacing dropped, the GOOD head set as views) and gg_G00 = block_in_start on it (male class mean, cameras
fitted on these pictures). Nothing is read from or written to any existing Garrett model's face."""
import copy, json
from hifipushie import store, server, blockin as bi

R = "/home/joe/dev/s0urc3/docs/img/garrett_ref_full/garrett_head_"
VIEWS = [
    {"image": R + "front.png", "size": [1152, 1536], "yaw": 0, "points": {}},
    {"image": R + "three_quarter_left.png", "size": [1152, 1536], "yaw": 45, "points": {}},
    # a profile gets no detector points: clicked on a pixel grid (spikes/garrettgood/grid.py)
    {"image": R + "profile_left.png", "size": [1152, 1536], "yaw": 90, "points": {
        "nose_tip": [207, 671], "nose_base": [266, 722], "nose_bridge": [283, 558], "lip_upper": [261, 768],
        "lip_lower": [269, 806], "chin": [296, 925], "eye_outer.L": [395, 567], "mouth_corner.L": [350, 790]}},
]
sp = copy.deepcopy(store.load("gj_G00"))
sp["base"]["style"]["human"].pop("eye_spacing", None)   # a hand style from the paintings: not carried
for k in ("hair", "cloth"):
    sp.pop(k, None)
d = store._dir("gg_R"); d.mkdir(parents=True, exist_ok=True)
(d / "spec.json").write_text(json.dumps(sp))
(d / "human_refs.json").write_text(json.dumps({"views": VIEWS, "cameras": [None] * 3}))
r = server.block_in_start("gg_G00", "gg_R", sex="male", age=52, cameras="refit", replace=True,
                          save="/mnt/data/hifipushie/garrettgood/out/gg_G00.png")
print("\n".join(x for x in r if isinstance(x, str)))
