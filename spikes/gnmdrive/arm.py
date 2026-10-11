"""arm.py <src set> <dst set>: copy a set's cases (fresh state) and hidden files to another arm (e.g. s2 -> m2), so
two driver groups drive the same pairs independently."""
import json
import shutil
import sys

import drv

src, dst = sys.argv[1], sys.argv[2]
for h in sorted(drv.HIDDEN.glob(f"{src}_??.json")):
    case = h.stem
    new = dst + case[len(src):]
    d = json.loads(h.read_text())
    d["case"] = new
    (drv.HIDDEN / f"{new}.json").write_text(json.dumps(d, indent=1))
    o = drv.HIDDEN / f"{case}_oracle.json"
    if o.exists():
        shutil.copy(o, drv.HIDDEN / f"{new}_oracle.json")
    dd = drv.CASES / new
    dd.mkdir(exist_ok=True)
    (dd / "case.json").write_text(json.dumps({"case": new, "difficulty": d["difficulty"]}))
    (dd / "state.json").write_text(json.dumps({"c": d["A"], "moves": [], "trial": None}))
    print(new)
