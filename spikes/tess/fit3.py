"""fit3.py <src> <dst> [read json]: MAP face fit on S0urc3's approved head set: front + three-quarter (detector) +
true left profile (clicked points). Copies src -> dst first."""
import copy, json, os, sys
from hifipushie import server, store

D = "/home/joe/dev/s0urc3/docs/img/tess_ref_full/"
src, dst = sys.argv[1], sys.argv[2]
read = json.loads(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] else None
if src != dst:
    store.save(dst, copy.deepcopy(store.load(src)), f"tess: copy of {src}")
# profile points (px in the 1152 x 1536 picture), read off a 25 px grid
prof = {"nose_tip": [125, 675], "nose_base": [163, 710], "nose_bridge": [198, 570], "lip_upper": [163, 760],
        "lip_lower": [170, 795], "chin": [195, 905], "eye_outer.L": [288, 592], "mouth_corner.L": [225, 770]}
views = [{"image": D + "tess_head_front.png", "size": [1152, 1536], "yaw": 0},
         {"image": D + "tess_head_three_quarter_left.png", "size": [1152, 1536], "yaw": 45},
         {"image": D + "tess_head_profile_left.png", "size": [1152, 1536], "yaw": 90, "points": prof}]
r = server.human_reference(dst, views, read=read, note=f"tess: MAP face fit on the approved head set, read={read}")
for x in r:
    if isinstance(x, str):
        print(x)
    else:
        open(os.path.join(os.environ["T"], "out", dst + "_fit.png"), "wb").write(x.data)
