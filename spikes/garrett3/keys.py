"""keys.py <model> [top-level keys...] [depth]: a model's spec as an outline (long values cut)."""
import json
import sys

from hifipushie import store


def sh(d, ind=0, depth=2):
    for k, v in d.items():
        if k in ("identity", "locks", "joints", "bones", "blobs"):
            print(" " * ind + str(k) + ": <" + str(len(v)) + ">")
        elif isinstance(v, dict) and depth > 0:
            print(" " * ind + str(k) + ":")
            sh(v, ind + 2, depth - 1)
        else:
            s = json.dumps(v)
            print(" " * ind + str(k) + ": " + (s if len(s) < 200 else s[:200] + "..."))


m = sys.argv[1]
ks = [a for a in sys.argv[2:] if not a.isdigit()]
dp = [int(a) for a in sys.argv[2:] if a.isdigit()]
s = json.loads((store.HOME / m / "spec.json").read_text())
print("=====", m, list(s.keys()))
for k in ks:
    if k in s:
        sh({k: s[k]}, 0, dp[0] if dp else 3)
