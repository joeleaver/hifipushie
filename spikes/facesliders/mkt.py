"""mkt.py <dst> <head model> [dressed model=ts_t12]: Tess dressed = the tess agent's dressed spec (skin, paint, hair)
with <head model>'s base and refs (cameras), for shot2.py."""
import json
import shutil
import sys

from hifipushie import store

dst, head = sys.argv[1], sys.argv[2]
src = sys.argv[3] if len(sys.argv) > 3 else "ts_t12"
sp = json.loads((store.HOME / src / "spec.json").read_text())
sp = sp.get("spec", sp)
hb = json.loads((store.HOME / head / "spec.json").read_text())
sp["base"] = hb.get("spec", hb)["base"]
d = store.HOME / dst
d.mkdir(exist_ok=True)
(d / "spec.json").write_text(json.dumps(sp, indent=1))
shutil.copy(store.HOME / head / "human_refs.json", d / "human_refs.json")
for f in store.HOME.joinpath(src).glob("hair_scalp_*.npz"):
    shutil.copy(f, d / f.name)
print("wrote", d)
