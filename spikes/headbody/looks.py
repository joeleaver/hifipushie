"""looks.py <model> <out prefix> [views=front,side] [size=900] [res=160] [shading=clay] [focus=x,y,z zoom=z]: single-view
clay tiles through server.look (one heavy slot for the lot)."""
import sys, time
from hifipushie import resources, server

m, out = sys.argv[1:3]
kw = dict(a.split("=", 1) for a in sys.argv[3:])
views = kw.get("views", "front,side").split(",")
with resources.heavy(f"headbody looks {m}", gb=8):
    for v in views:
        t0 = time.time()
        extra = {}
        if kw.get("focus"):
            extra = {"focus": [float(x) for x in kw["focus"].split(",")], "zoom": float(kw.get("zoom", 3))}
        r = server.look(m, views=[v], size=int(kw.get("size", 900)), resolution=int(kw.get("res", 160)), shading=kw.get("shading", "clay"),
                        paint=False, save=f"{out}_{v}.png", **extra)
        print(v, f"{time.time() - t0:.0f} s", str(r[-1])[:300] if isinstance(r, (list, tuple)) else str(r)[:300], flush=True)
