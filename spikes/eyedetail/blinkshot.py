"""blinkshot.py <model> <glb> <out prefix>: the exported GLB through rig(glb=...) at the head, neutral / eyeBlinkLeft 1
/ eyeBlinkLeft 0.5, saved as <prefix>_<n>.png: do the lashes ride the lid?"""
import sys

from hifipushie import server

name, glb, out = sys.argv[1], sys.argv[2], sys.argv[3]
for tag, sh in (("neutral", None), ("blink50", {"eyeBlinkLeft": 0.5, "eyeBlinkRight": 0.5}),
                ("blink", {"eyeBlinkLeft": 1.0, "eyeBlinkRight": 1.0})):
    r = server.rig(name, glb=glb, focus="mixamorig:Head", zoom=4.0, views=["front", "side"], shapes=sh, save=f"{out}_{tag}.png")
    print(tag, r if isinstance(r, str) else [x for x in r if isinstance(x, str)][:1])
