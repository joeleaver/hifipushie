"""mkd.py <dst> <head model> [skin_patch.json]: the dressed head = g4_garrett's spec (procedural skin, paint, body)
with <head model>'s base, hair7's groom (h7_garrett's spec["hair"]), the head model's human_refs.json; the patch is
{"dotted.path": value} on the spec (skin.wrinkles.forehead ...)."""
import json
import shutil
import sys

from hifipushie import store

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from pair import apply  # noqa: E402

dst, head = sys.argv[1], sys.argv[2]
sp = json.loads((store.HOME / "g4_garrett" / "spec.json").read_text())
sp["base"] = json.loads((store.HOME / head / "spec.json").read_text())["base"]
sp["hair"] = json.loads((store.HOME / "h7_garrett" / "spec.json").read_text())["hair"]
hb = json.load(open("/mnt/data/hifipushie/hair7/base.json"))   # hair7/8's groom (loose -> groom.loose; merged)


def merge(a, b):
    for k, v in b.items():
        a[k] = merge(a[k], v) if isinstance(v, dict) and isinstance(a.get(k), dict) else v
    return a


sp["hair"]["groom"]["loose"] = hb["loose"]
for k in ("body", "lay"):   # hair7's newer swoop keys, not in main's hair.py yet (2026-10-09 afternoon)
    hb["loose"].get("swoop", {}).pop(k, None)
merge(sp["hair"], {k: v for k, v in hb.items() if k != "loose"})
if len(sys.argv) > 3:
    apply(sp, json.load(open(sys.argv[3])))
store.save(dst, sp, f"likeloop: g4_garrett's skin, {head}'s head, hair7's groom")
shutil.copy(store.HOME / head / "human_refs.json", store.HOME / dst / "human_refs.json")
print("saved", dst)
