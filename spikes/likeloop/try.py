"""try.py <model> <tag> <ops.json> [save]: ops applied to the model's base in order, the matched pair rendered to
$L/out/<tag>.png (+ .json rows, .gif), the base written to $L/out/<tag>_base.json; "save" writes it into the model.
ops: [{"nudge": landmark, "move": [x, y, z] m}, {"set": {"head.shape.x": v, ...}}, {"base": "file.json"}]."""
import json
import os
import sys

from hifipushie import humanfit, likeness_pair, store

L = os.environ["L"]


def setp(b, path, v):
    d, ks = b, path.split(".")
    for k in ks[:-1]:
        d = d.setdefault(k, {})
    if v is None:
        d.pop(ks[-1], None)
    else:
        d[ks[-1]] = v


name, tag, ops = sys.argv[1], sys.argv[2], json.load(open(sys.argv[3]))
spec = store.load(name)
base = spec["base"]
for op in ops:
    if "base" in op:
        base = json.load(open(op["base"]))
    if "nudge" in op:
        base, rep = humanfit.nudge(base, op["nudge"], move=op["move"], radius=op.get("radius", 0.015))
        print("nudge", op["nudge"], {k: v for k, v in rep.items() if k not in ("landmark",)})
    if "macros" in op or "solve" in op or "read" in op:
        from hifipushie import humanmacro as hm
        c = hm.from_identity(base["head"].get("identity"))
        z0 = hm.read(c)
        if "macros" in op:
            c = hm.apply(c, op["macros"], held=op.get("held", True))
        if "solve" in op:  # relative: sigmas added to the current read
            c, rep = hm.solve(c, {k: z0[k] + v for k, v in op["solve"].items()})
            print("solve", rep)
        z1 = hm.read(c)
        print("macros", {k: (round(z0[k], 2), round(z1[k], 2)) for k in z0 if abs(z1[k] - z0[k]) > 0.15 or k in op.get("read", [])})
        print("soundness", hm.soundness(c))
        base["head"]["identity"] = {**{k: v for k, v in base["head"]["identity"].items() if k not in hm.space()["names"][:hm.K]},
                                    **hm.identity_dict(c)}
    for p, v in op.get("set", {}).items():
        setp(base, p, v)
out = f"{L}/out/{tag}.png"
m = likeness_pair.matched(name, base)
likeness_pair.sheet(m, out, gif=f"{L}/out/{tag}.gif", title=tag)
json.dump({"face_id": m.get("face_id"), "items": m["items"]}, open(f"{L}/out/{tag}.json", "w"), indent=1)
json.dump(base, open(f"{L}/out/{tag}_base.json", "w"))
print(json.dumps(m.get("face_id")))
for k, r in m["items"].items():
    d = "" if None in (r["photo"], r["model"]) else f"{(r['model'] - r['photo']) / r['tol']:+.1f} tol"
    print(f"{k:18s} {r['photo']!s:>7} {r['model']!s:>7} {r['unit'] or ''} {d}")
if len(sys.argv) > 4 and sys.argv[4] == "save":
    spec = json.load(open(store.HOME / name / "spec.json"))
    spec["base"] = base
    store.save(name, spec, note=f"likeloop {tag}")
    print("saved", name)
