"""jstep.py <src> <out> [share=1.0] [rounds=3]: the face ruler's own solved identity change (outlines + irises + limbus
over every view, GNM's prior, cameras free) applied as ONE block-in step."""
import sys
import numpy as np
from hifipushie import face_ruler as fr, blockin as bi, store
src, out = sys.argv[1:3]
share = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
rounds = int(sys.argv[4]) if len(sys.argv) > 4 else 3
c = fr.compare(src, rounds=rounds)
dc = np.asarray(c["dc"], float)
c0 = bi.identity(store.load(src))
print(f"solve: {c['n']} | |dc| {np.linalg.norm(dc):.2f}, |c| {np.linalg.norm(c0):.2f} -> {np.linalg.norm(c0 + share * dc):.2f}, largest comp {np.abs(c0 + share * dc).max():.2f} sd")
rep = bi.step(src, {}, out=out, seen="the face ruler's joint solve (outlines, irises, limbus; all views)",
              why=f"its solved identity change applied whole (share {share})", _identity=c0 + share * dc)
import json
rp = store.HOME / out / "human_refs.json"
rj = json.loads(rp.read_text())
for i, v in enumerate(c["views"]):       # the cameras the solve ended on (its yaw / pitch / shift / scale / roll)
    cam = {k: (np.asarray(x).tolist() if hasattr(x, "tolist") else x) for k, x in v["cam"].items()}
    rj["cameras"][i] = {**rj["cameras"][i], **cam}
rp.write_text(json.dumps(rj))
print("cameras moved by the solve:", np.round(np.asarray(c["cam_done"], float), 2).tolist())
rep["table"] = bi.table(out)
t = bi.step_text(rep)
print("\n".join(l for l in t.split("\n")[:2] if "MANUAL" not in l and not l.startswith(("- [", "  looks alike"))))
print(bi.table_text(rep["table"]) if hasattr(bi, "table_text") else "")
