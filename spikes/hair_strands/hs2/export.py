"""export.py <model> <out dir> [tiers=a,b]: hair-only export (GLB per tier + groom)."""
import json, sys, time
from hifipushie import hair
name, out = sys.argv[1], sys.argv[2]
kw = dict(a.split("=", 1) for a in sys.argv[3:])
t = time.time()
rep = hair.export_hair(name, out, tiers=tuple(kw.get("tiers", "hero,main,npc,far").split(",")))
print(json.dumps({k: v for k, v in rep.items() if k not in ("recipe",)}, indent=1, default=float)[:2500])
print("seconds", round(time.time() - t, 1))
