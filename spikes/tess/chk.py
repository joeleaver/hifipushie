"""chk.py <model> <garment> [stages, default place]: check_garment, the FAIL / WARN lines and the verdict."""
import os, sys
from hifipushie import server

st = (sys.argv[3] if len(sys.argv) > 3 else "place").split(",")
r = server.check_garment(sys.argv[1], sys.argv[2], stages=st, save=os.path.join(os.environ["T"], "out", f"{sys.argv[1]}_{sys.argv[2]}.png"))
txt = r if isinstance(r, str) else "\n".join(x for x in r if isinstance(x, str))
print("\n".join(l[:400] for l in txt.splitlines() if "FAIL" in l or "WARN" in l or l.startswith("==")))
