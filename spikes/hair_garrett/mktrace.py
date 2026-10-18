"""mktrace.py <base style.json> <photo trace.json> <out style.json> [prev style.json prev trace.json] [regions=front,top]
[roots=front:1,top:1] [k=key=val ...]: a style with groom.loose.trace from fronttrace's samples.

The first round commands the photo's own heights (h_cmd = h_photo). Given the previous round's style and ITS trace
(fronttrace run on that model: h_ours per ray), each sample's command is solved by one fixed-point step against the
screen's outline: h_cmd *= h_photo / h_ours (clipped 0.6..1.8; rays where ours didn't meet the backdrop keep theirs).
Samples are matched by (view, ray angle)."""
import copy
import json
import sys

import numpy as np


def main(base, trace, out, prev=None, prev_trace=None, regions=("front", "top"), roots=None, extra=None):
    st = json.load(open(base))
    T = json.load(open(trace))["samples"]
    S = [r for r in T if r["reg"] in regions and r["h_photo"] == r["h_photo"]]
    cmd = {(r["view"], r["ang"]): max(r["h_photo"], 0.0) for r in S}
    if prev:
        pv = json.load(open(prev))["groom"]["loose"]["trace"]
        pcmd = {(int(k[0]), float(k[1])): float(h) * 1000 for k, h in zip(pv["keys"], (s[2] for s in pv["samples"]))}
        PT = {(r["view"], r["ang"]): r for r in json.load(open(prev_trace))["samples"]}
        g = []
        for k in cmd:
            c0 = pcmd.get(k, cmd[k])
            o = PT.get(k, {}).get("h_ours")
            if o is not None and o > 0.5:
                f = float(np.clip(cmd[k] / o, 0.6, 1.8))
                g.append(f)
                cmd[k] = c0 * f
            else:
                cmd[k] = c0
        print(f"solve step: gains median {np.median(g):.2f} p10 {np.percentile(g, 10):.2f} p90 {np.percentile(g, 90):.2f}")
    keys = [k for k in cmd]
    by = {(r["view"], r["ang"]): r for r in S}
    tr = {"samples": [[by[k]["az"], by[k]["el"], round(cmd[k] / 1000.0, 5)] for k in keys],
          "keys": [[k[0], k[1]] for k in keys], "regions": roots or {"front": 1.0, "top": 1.0}}
    for kv in extra or []:
        a, v = kv.split("=", 1)
        tr[a] = json.loads(v)
    lo = st["groom"]["loose"]
    lo["trace"] = tr
    json.dump(st, open(out, "w"), indent=1)
    hs = [cmd[k] for k in keys]
    print(f"WROTE {out}: {len(keys)} samples, h_cmd median {np.median(hs):.1f} mm, regions {regions}, roots {tr['regions']}")


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if "=" not in x]
    kw = {}
    extra = []
    for x in sys.argv[1:]:
        if x.startswith("k="):
            extra.append(x[2:])
        elif "=" in x:
            kw.update([x.split("=", 1)])
    roots = {r.split(":")[0]: float(r.split(":")[1]) for r in kw["roots"].split(",")} if "roots" in kw else None
    main(a[0], a[1], a[2], a[3] if len(a) > 3 else None, a[4] if len(a) > 4 else None,
         tuple(kw.get("regions", "front,top").split(",")), roots, extra)
