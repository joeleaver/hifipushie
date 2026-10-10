"""dressg.py <model> <garment> [quality] [wait s]: dress() a garment (ZOZO on the GPU fleet: HIFIPUSHIE_GPU=bundle) and
print the report; then look_cloth saved to $T/out/<model>_<garment>_cloth.png."""
import os, sys, time
from hifipushie import server

name, g = sys.argv[1], sys.argv[2]
q = sys.argv[3] if len(sys.argv) > 3 else "final"
wait = float(sys.argv[4]) if len(sys.argv) > 4 else 3000
t = time.time()
r = server.dress(name, garment=g, quality=q, wait=wait, note=f"tess: {g} {q}")
print(r if isinstance(r, str) else "\n".join(x for x in r if isinstance(x, str))[:5000])
print(f"dress {time.time() - t:.0f} s")
r = server.look_cloth(name, garments=[g], views=["front", "side", "back", "three"],
                      save=os.path.join(os.environ["T"], "out", f"{name}_{g}_cloth.png"))
print("\n".join(x for x in r if isinstance(x, str))[:3000] if isinstance(r, list) else str(r)[:3000])
