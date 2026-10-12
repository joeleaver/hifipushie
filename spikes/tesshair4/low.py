"""low.py <model>: locks that start low in front of the ears (what is the dark blade on the sideburn?)."""
import json, sys
s = json.load(open(f"/home/joe/dev/hifipushie/workspace/{sys.argv[1]}/spec.json"))
import numpy as np
for n, l in s["hair"]["locks"].items():
    p = l["pts"]
    if l.get("space") == "xyz":
        q = np.asarray(p)
        if n.startswith("tw"):
            print(n, "hairs", l["hairs"], "w", l["width"], "start", q[0].round(3), "end", q[-1].round(3), "len", round(float(np.linalg.norm(np.diff(q, axis=0), axis=1).sum()), 3))
        continue
    a = ((p[0][0] + 180) % 360) - 180
    if 45 < abs(a) < 105 and p[0][1] < 0:
        print(n, [round(v, 1) for v in p[0]], "->", [round(v, 1) for v in p[3]], l.get("strands", {}).get("roots"))
