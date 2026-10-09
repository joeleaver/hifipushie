"""fetch_measure.py <out_dir>: MakeHuman's measure targets (CC0, the pack's pinned commit) for fit-solvable hips /
waist / shoulders / bust; prints each file's sha256 and the assets.json rows."""
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

C = "a8bc2d54ff0ac92e78ff71431b1023eda42bf482"
B = f"https://raw.githubusercontent.com/makehumancommunity/makehuman/{C}/makehuman/data/targets"
out = Path(sys.argv[1])
(out / "targets" / "measure").mkdir(parents=True, exist_ok=True)
rows = []
for m in ("hips-circ", "waist-circ", "shoulder-dist", "bust-circ"):
    for d in ("decr", "incr"):
        rel = f"measure/measure-{m}-{d}.target"
        try:
            data = urllib.request.urlopen(f"{B}/{rel}", timeout=60).read()
        except Exception as e:  # noqa: BLE001
            print("MISSING", rel, e)
            continue
        (out / "targets" / rel).write_bytes(data)
        h = hashlib.sha256(data).hexdigest()
        rows.append({"path": f"targets/{rel}", "url": f"{B}/{rel}", "sha256": h})
        print(rel, len(data), h)
(out / "rows.json").write_text(json.dumps(rows, indent=1))
