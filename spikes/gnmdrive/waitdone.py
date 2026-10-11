"""waitdone.py <minutes> <set>...: wait until every case of the sets is `done` (or the time is up); print progress."""
import json
import sys
import time
from pathlib import Path

G = Path("/mnt/data/hifipushie/gnmdrive/cases")
t0 = time.time()
lim = float(sys.argv[1]) * 60
while True:
    st = {}
    for s in sys.argv[2:]:
        for i in range(14):
            d = json.loads((G / f"{s}_{i:02d}" / "state.json").read_text())
            st[f"{s}_{i:02d}"] = ("D" if d.get("done") else "") + str(len(d["moves"]))
    if all(v.startswith("D") for v in st.values()) or time.time() - t0 > lim:
        break
    time.sleep(20)
print(" ".join(f"{k[:2]}{k[3:]}:{v}" for k, v in st.items()))
print("done", sum(v.startswith("D") for v in st.values()), "of", len(st))
