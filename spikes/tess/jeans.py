"""jeans.py <src> <dst> [design json] [spec json]: dst = src + Tess's jeans design sheet (straight dark indigo jeans:
trousers kind from the trouser block, denim, straight leg, to the shoe), then the pattern + construction + place checks
(images saved to $T/out/<dst>_jeans_*)."""
import copy, json, os, sys
from hifipushie import server, store

src, dst = sys.argv[1], sys.argv[2]
dpatch = json.loads(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] else {}
spatch = json.loads(sys.argv[4]) if len(sys.argv) > 4 and sys.argv[4] else {}
if src != dst:
    store.save(dst, copy.deepcopy(store.load(src)), f"tess: copy of {src}")
    (store.HOME / dst / "human_refs.json").write_text((store.HOME / src / "human_refs.json").read_text())
design = {"kind": "suit_trousers", "fit": "classic", "fabric": "denim",
          "block_options": {"length": "shoe"},
          "details": {"crease": "none", "belt": "none"}, **dpatch}
spec = {"color": "#262c3f", "roughness": 0.85, "backend": "zozo", "zozo": {"stitch_stiffness": 8}, "resolution": 0.01,
        "coarse": 0.02, "collide": ["shoes", "soles"], **spatch}
r = server.design_garment(dst, "jeans", design=design, spec=spec, note="tess: jeans design sheet")
print(r if isinstance(r, str) else "\n".join(x for x in r if isinstance(x, str)))
r = server.check_garment(dst, "jeans", stages=["pattern", "construction", "place"],
                         save=os.path.join(os.environ["T"], "out", f"{dst}_jeans.png"))
print(r if isinstance(r, str) else "\n".join(x for x in r if isinstance(x, str))[:6000])
