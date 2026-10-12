"""start.py <new> <refs model> [cameras=keep|refit]: block_in_start of a GNM-native head from a refs model (its body,
references and cameras; the class mean for its sex; GNM's own eyeball and mouth: no eye_radius, no kit interior)."""
import sys

from hifipushie import blockin as bi
from hifipushie import store

name, refs = sys.argv[1:3]
kw = dict(a.split("=", 1) for a in sys.argv[3:])
e = bi.start(name, refs, sex=kw.get("sex"), cameras=kw.get("cameras", "keep"), replace=True)
sp = store.load(name)
hd = {k: v for k, v in sp["base"]["head"].items() if k != "identity"}
print(name, e["start"], "|c|", e["c_norm"], "head", hd, "skin.eyes", (sp.get("skin") or {}).get("eyes"))
