"""looks2.py <prefix> <model> ...: per model the full figure front + side (clay) and neck close-ups (raking; front,
side, back, three_quarter, or only three_quarter with NECK=1), one heavy slot; neck focus from the attach report."""
import os, sys, time
from hifipushie import onemesh, resources, server, store
OUT = "/mnt/data/hifipushie/headbody/out"
pre = sys.argv[1]
with resources.heavy("headbody looks2", gb=8):
    for m in sys.argv[2:]:
        r = onemesh.attach_report(store.load(m)["base"])
        zc = r["stature"] - r["head_height"] - 0.05
        t0 = time.time()
        if not os.environ.get("NOFIG"):
            for v in ("front", "side"):
                server.look(m, views=[v], size=900, resolution=int(os.environ.get("RES", 220)), shading="clay", paint=False, save=f"{OUT}/{pre}F_{m}_{v}.png")
        for v in (("three_quarter", "front") if os.environ.get("NECK") else ("front", "side", "back", "three_quarter")):
            server.look(m, views=[v], size=700, resolution=220, shading="raking", paint=False, focus=[0, -0.03, zc], zoom=4.2 * r["stature"] / 1.7,
                        save=f"{OUT}/{pre}N_{m}_{v}.png")
        print(m, f"{time.time() - t0:.0f} s", flush=True)
