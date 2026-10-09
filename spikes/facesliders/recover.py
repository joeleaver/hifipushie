"""recover.py: known slider values recovered from a render (crease height by luminance on a lid with a defined crease,
canthal tilt by the rim). First the reading across the slider's range (monotonic?)."""
import copy

from hifipushie import faceslide, humanfit, humans

sp = humans.spec(age=40, sex=1.0, seed=None, skin=False, source="human")
b = sp["base"]
b.setdefault("head", {})["sliders"] = {"eye_crease_depth": 0.8}


def rd(sl):
    bt = copy.deepcopy(b)
    bt["head"]["sliders"] = {**b["head"]["sliders"], **sl}
    return faceslide.read_eyes(humanfit.state(bt))


for v in (-1, -0.5, 0, 0.5, 1):
    m = rd({"eye_crease_height": v})
    print("crease_height", v, "crease mm", round(m["crease"], 2), "dark", round(m["crease_dark"], 3))
for v in (0.6, -0.5):
    m = rd({"eye_crease_height": v})
    r = faceslide.fit(b, {"crease": (m["crease"], 0.1)}, ["eye_crease_height"], log=print)
    print("RECOVERED", r["sliders"], "true", v)
