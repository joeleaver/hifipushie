"""gexpr.py [amount=0.3] [cls=happy]: the EXPRESSION test, on a KNOWN GNM benchmark head (solvecams' head a: sc_a_T; a
scan cannot be made to smile): its front picture shot again (the same stage, light and TRUE camera) with a slight
smile (GNM's sampler prototype `cls` x amount on base.head.expression), then the set A with that front instead of the
neutral one: gt_exs_AT (truth: the NEUTRAL identity, true cameras) and gt_exs_A00 (block_in_start on the pictures).
The neutral set is solvecams' own sc_a_AT / sc_a_A00. Heavy (one EEVEE frame): run through heavy.sh."""
import copy, json, sys
import numpy as np
import stage
from hifipushie import blockin as bi, face_ruler as fr, resources, store
import gt

kw = dict(a.split("=") for a in sys.argv[1:])
amount, cls = float(kw.get("amount", 0.3)), kw.get("cls", "happy")
sp = copy.deepcopy(store.load("sc_a_T"))
rt = json.loads((store.HOME / "sc_a_AT" / "human_refs.json").read_text())
X = "gt_exs_X"                                   # the smiling model (only to shoot it)
sp["base"]["head"]["expression"] = fr.expression_coeffs({cls: amount})
store._dir(X).mkdir(parents=True, exist_ok=True)
(store.HOME / X / "spec.json").write_text(json.dumps(sp))
i = [v["name"] for v in rt["views"]].index("f")
cam = rt["cameras"][i]
w, h = cam["size"]
fn = gt.ROOT / "pics" / f"ex_f_{cls}{amount:g}.png"
with resources.heavy("groundtruth expression front", gb=6):
    im = stage.shoot(X, [stage.fitted_frame(cam, [w / 2 - h / 2, 0.0, w / 2 + h / 2, float(h)], "f")], copy.deepcopy(stage.FRONT_LIGHT), size=int(h), hair_on=False)["f"]
x0 = int(round((h - w) / 2))
im.convert("RGB").crop((x0, 0, x0 + w, h)).save(fn)
views = copy.deepcopy(rt["views"])
views[i] = {"image": str(fn), "size": [w, h], "yaw": 0, "points": {}, "name": "f"}
views = bi.with_anchor_points(views)
ST = "gt_exs_AT"
store._dir(ST).mkdir(parents=True, exist_ok=True)
(store.HOME / ST / "spec.json").write_text(json.dumps(store.load("sc_a_T")))
(store.HOME / ST / "human_refs.json").write_text(json.dumps({"views": views, "cameras": rt["cameras"], "blockin": {"root": ST, "attach": "native"}}))
e = bi.start("gt_exs_A00", [copy.deepcopy(v) for v in views], sex="male", age=35, cameras="refit", replace=True)
print("shot", fn, "start gt_exs_A00:", e["start"]["cameras"])
