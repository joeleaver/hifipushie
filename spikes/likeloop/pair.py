"""pair.py <model> <out.png> [patch.json] [title]: the matched pair (photo | model | 50/50) through the front photo's
fitted camera, face-ID scores and checklist rows; patch = {"dotted.path": value} applied to the spec in memory
(value null deletes). Prints the rows and scores; writes <out>.json beside the png and a flicker <out>.gif."""
import json
import sys
import time

from hifipushie import likeness_pair, store


def apply(spec, patch):
    for path, v in patch.items():
        if isinstance(v, str) and v.startswith("@"):   # "@file.json": the value read from a file
            v = json.load(open(v[1:]))
        d, ks = spec, path.split(".")
        for k in ks[:-1]:
            d = d.setdefault(k, {})
        if v is None:
            d.pop(ks[-1], None)
        else:
            d[ks[-1]] = v
    return spec


if __name__ == "__main__":
    t = time.time()
    name, out = sys.argv[1], sys.argv[2]
    spec = store.load(name)
    if len(sys.argv) > 3 and sys.argv[3] != "-":
        apply(spec, json.load(open(sys.argv[3])))
    title = sys.argv[4] if len(sys.argv) > 4 else name
    m = likeness_pair.matched(name, spec["base"])
    likeness_pair.sheet(m, out, gif=out.rsplit(".", 1)[0] + ".gif", title=title)
    rec = {"face_id": m.get("face_id"), "items": m["items"]}
    json.dump(rec, open(out.rsplit(".", 1)[0] + ".json", "w"), indent=1)
    print(json.dumps(rec["face_id"]))
    for k, r in m["items"].items():
        print(f"{k:18s} {r['photo']!s:>7} {r['model']!s:>7} {r['unit'] or ''} tol {r['tol']}")
    print(f"{time.time() - t:.0f} s")
