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
sp["hair"].get("groom", {}).get("loose", {}).pop("swoop", None)  # hair7 in progress: not in the merged hair.py
if len(sys.argv) > 3:
    apply(sp, json.load(open(sys.argv[3])))
store.save(dst, sp, f"likeloop: g4_garrett's skin, {head}'s head, hair7's groom")
shutil.copy(store.HOME / head / "human_refs.json", store.HOME / dst / "human_refs.json")
print("saved", dst)
