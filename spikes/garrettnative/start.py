"""start.py <new> <refs model>: block_in_start on the TRUE GNM BASE (gnm_base 1.0: start() then also writes dimorphism
0, eyes 1.0 and drops the refs model's face style sliders), the male class mean, the refs model's cameras kept."""
import sys

from hifipushie import blockin as bi, store

name, refs = sys.argv[1:3]
e = bi.start(name, refs, sex="male", gnm_base=1.0, cameras="keep", replace=True)
sp = store.load(name)
print(name, e["start"], "|c|", e["c_norm"], "head", {k: v for k, v in sp["base"]["head"].items() if k != "identity"},
      "style", sp["base"].get("style"), "skin.eyes", (sp.get("skin") or {}).get("eyes"), "hair" in sp)
