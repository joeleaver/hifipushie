"""exph.py <model> <out dir> [tiers csv]: export_hair (card GLBs per tier + groom) and print the report."""
import sys, time
from hifipushie import server

name, out = sys.argv[1], sys.argv[2]
tiers = sys.argv[3].split(",") if len(sys.argv) > 3 else ["hero", "main"]
t = time.time()
r = server.export_hair(name, out, tiers=tiers, groom=False, check=True)
print(r if isinstance(r, str) else "\n".join(x for x in r if isinstance(x, str)))
print(f"{time.time() - t:.0f} s")
