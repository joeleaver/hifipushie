"""mkd.py <dst> <head model> [skin_patch.json]: the dressed head = g4_garrett's spec (procedural skin, paint, body)
with <head model>'s base, hair7's p12 groom (a snapshot of h7_garrett's hair + base.json), the head model's
human_refs.json; the patch is {"dotted.path": value} on the spec (skin.wrinkles.forehead ...)."""
import json
import shutil
import sys

from hifipushie import store

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from pair import apply  # noqa: E402

dst, head = sys.argv[1], sys.argv[2]
sp = json.loads((store.HOME / "g4_garrett" / "spec.json").read_text())
sp["base"] = json.loads((store.HOME / head / "spec.json").read_text())["base"]
# hair: h7_garrett's hair copied ONCE (likeloop/hair_snapshot.json, 2026-10-09: the hair agent edits h7_garrett live)
# with hair7's p12 groom (base.json: loose -> groom.loose, the rest merged); nothing stripped
sp["hair"] = json.load(open("/mnt/data/hifipushie/likeloop/hair_snapshot.json"))
hb = json.load(open("/mnt/data/hifipushie/hair7/base.json"))


def merge(a, b):
    for k, v in b.items():
        a[k] = merge(a[k], v) if isinstance(v, dict) and isinstance(a.get(k), dict) else v
    return a


sp["hair"]["groom"]["loose"] = hb["loose"]
merge(sp["hair"], {k: v for k, v in hb.items() if k != "loose"})
if len(sys.argv) > 3:
    apply(sp, json.load(open(sys.argv[3])))
store.save(dst, sp, f"likeloop: g4_garrett's skin, {head}'s head, hair7's groom")
shutil.copy(store.HOME / head / "human_refs.json", store.HOME / dst / "human_refs.json")
print("saved", dst)
