"""chk.py: likeness.check_references on the good head set, alone and together with the two concept paintings."""
from hifipushie import server
R = "/home/joe/dev/s0urc3/docs/img/garrett_ref_full/garrett_head_"
C = "/home/joe/dev/hifipushie/workspace/garrett_v20/"
good = [R + k + ".png" for k in ("front", "front_raking", "three_quarter_left", "profile_left", "closeup_eyes", "closeup_mouth", "hair_as_worn_back")]
print("=== the good set ===")
print(server.check_references(good))
print("=== good front / 3-4 + the two concepts ===")
print(server.check_references([good[0], good[2], good[1], C + "concept_v8_front_apose.png", C + "concept_v6_portrait_at_desk.png"]))
