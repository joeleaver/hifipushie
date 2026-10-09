"""add_rows.py: the measure targets into assets.json's makehuman pack (rows from fetch_measure.py) and into the assets
directory ($HIFIPUSHIE_ASSETS/makehuman/targets/measure)."""
import json
import os
import shutil
from pathlib import Path

W = Path("/home/joe/dev/hifipushie/.claude/worktrees/agent-abc45e5f0969ff6fa/src/hifipushie/assets.json")
D = Path("/mnt/data/hifipushie/facesliders/dl_measure")
rows = json.loads((D / "rows.json").read_text())
a = json.loads(W.read_text())
mh = a["makehuman"]
have = {f["path"] for f in mh["files"]}
mh["files"] += [r for r in rows if r["path"] not in have]
if "targets/measure" not in mh["source"]:
    mh["source"] += ", targets/measure/measure-{hips-circ,waist-circ,shoulder-dist,bust-circ}-{decr,incr}.target"
W.write_text(json.dumps(a, indent=1) + "\n")
dst = Path(os.environ["HIFIPUSHIE_ASSETS"]) / "makehuman" / "targets" / "measure"
dst.mkdir(parents=True, exist_ok=True)
for r in rows:
    shutil.copy(D / r["path"], dst / Path(r["path"]).name)
print(len(rows), "rows;", dst)
