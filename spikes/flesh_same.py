"""flesh_same.py <out.npz> <model|path.json>...: each model's skin weights (store.build mesh, skin_mesh), saved to
compare two checkouts (run once per checkout, then --diff a.npz b.npz)."""
import sys, json, numpy as np
from hifipushie import store, rig as R
if sys.argv[1] == "--diff":
    a, b = np.load(sys.argv[2]), np.load(sys.argv[3])
    for k in sorted({x.rsplit("_", 1)[0] for x in a.files}):
        Da, Db = a[k + "_D"], b[k + "_D"]
        d = np.abs(Da - Db).max(1)
        print(f"{k}: verts {len(d)}, max |dW| {d.max():.4f}, verts changed >0.01: {(d > 0.01).sum()}")
    sys.exit()
out = {}
for m in sys.argv[2:]:
    spec = json.load(open(m)) if m.endswith(".json") else store.load(m)
    name = m.rsplit("/", 1)[-1].replace(".json", "")
    if m.endswith(".json"):
        store.save(name + "_fleshchk", spec, "flesh_same check")
    z = np.load(store.build(name + "_fleshchk" if m.endswith(".json") else m, 128)["mesh"])
    try:
        rb = R.rig_bones(spec)
    except ValueError as e:
        print(name, "no rig:", str(e)[:60]); continue
    J, W = R.skin_mesh(spec, rb, z["verts"].astype(float), z["faces"], z["part"], [str(n) for n in z["part_names"]])
    D = np.zeros((len(J), len(rb))); np.add.at(D, (np.repeat(np.arange(len(J)), J.shape[1]), J.ravel()), W.ravel())
    out[name + "_D"] = D
np.savez(sys.argv[1], **out)
