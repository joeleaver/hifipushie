"""look6.py <model> [stage=_g3_th_T04 engine=eevee size=640 views=ref0,ref1,ref2 mview=ref2 save=<png>]: THE TOOL
PATH for judging against the pictures: server.look_hair with the fitted reference cameras ("ref<i>"), a stage model
and measure (the tail / outline against her traced mask, the colour bands)."""
import os
import sys
import time

from hifipushie import server

m = sys.argv[1]
kw = dict(a.split("=", 1) for a in sys.argv[2:])
T = os.environ.get("T", "/mnt/data/hifipushie/tess")
out = os.environ.get("TOUT", "/mnt/data/hifipushie/tesshair6/out")
MASK = {"ref0": ("trace_front_mask.png", None), "ref1": ("trace_tq_mask.png", [905, 550]), "ref2": ("trace_profile_mask.png", [875, 545])}
mv = kw.get("mview", "ref2")
t = time.time()
r = server.look_hair(m, views=kw.get("views", "ref0,ref1,ref2").split(","), size=int(kw.get("size", 640)), clay=False,
                     engine=kw.get("engine", "eevee"), stage=kw.get("stage", "_g3_th_T04"),
                     save=kw.get("save", f"{out}/look6_{m}_{kw.get('engine', 'eevee')}.png"),
                     measure={"view": mv, "mask": f"{T}/{MASK[mv][0]}", "tie": MASK[mv][1]})
print(r[-1])
print(f"look_hair {time.time() - t:.0f} s")
