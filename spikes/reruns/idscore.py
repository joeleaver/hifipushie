"""idscore.py <model> ...: face-ID cosine (SFace, ArcFace) of each model's cached DRESSED shots (dsheet.py's d_<model>_<view>.png)
against the reference picture of the same view."""
import sys, os
from PIL import Image
from hifipushie import faceid, blockin as bi
G = os.environ.get("G", "/mnt/data/hifipushie/reruns") + "/out"
ms = sys.argv[1:]
rj = bi._refs(ms[0])
for vi, v in enumerate(rj["views"]):
    fs = [f"{G}/d_{m}_{vi}.png" for m in ms]
    ok = [(m, f) for m, f in zip(ms, fs) if os.path.exists(f)]
    try:
        sc = faceid.scores(Image.open(v["image"]).convert("RGB"), [Image.open(f).convert("RGB") for _, f in ok])
    except Exception as e:
        print("view", vi, "ERR", repr(e)[:200]); continue
    print(f"view {vi} (yaw {v.get('yaw')}):")
    for (m, _), s in zip(ok, sc):
        print(f"  {m:10s} " + "  ".join(f"{k} {x:+.3f}" if isinstance(x, float) else f"{k} {x}" for k, x in s.items()))
