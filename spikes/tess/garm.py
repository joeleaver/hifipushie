"""garm.py <src> <dst> <garment> <design json> <spec json>: dst = src + a garment's design sheet, then the pattern +
construction + place checks (images $T/out/<dst>_<garment>_*)."""
import copy, json, os, sys
from hifipushie import server, store

src, dst, g = sys.argv[1:4]
design, spec = json.loads(sys.argv[4]), json.loads(sys.argv[5])
if src != dst:
    store.save(dst, copy.deepcopy(store.load(src)), f"tess: copy of {src}")
    (store.HOME / dst / "human_refs.json").write_text((store.HOME / src / "human_refs.json").read_text())
r = server.design_garment(dst, g, design=design, spec=spec, note=f"tess: {g} design sheet")
print(r if isinstance(r, str) else "\n".join(x for x in r if isinstance(x, str)))
r = server.check_garment(dst, g, stages=os.environ.get("STAGES", "pattern,construction,place").split(","),
                         save=os.path.join(os.environ["T"], "out", f"{dst}_{g}.png"))
print(r if isinstance(r, str) else "\n".join(x for x in r if isinstance(x, str))[:6000])
