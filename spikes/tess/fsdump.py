"""fsdump.py <model> <garment>: run dress() up to the fine settle's start check (the coarse result handed back by
stage.sh) and pickle (M, plan, allow, report) to $T/out/fs_<garment>.pkl; prints the check's report and, per piece,
the worst start stretch of draped triangles and where (pattern uv)."""
import os, sys, pickle
import numpy as np
from hifipushie import cloth, server
from hifipushie.cloth_zozo import _start_stretch

name, g = sys.argv[1], sys.argv[2]
out = os.path.join(os.environ["T"], "out", f"fs_{g}.pkl")
orig = cloth.fine_start_check


def spy(M, plan, limit=cloth.FINE_START_MAX, allow=None):
    rep = orig(M, plan, limit, allow)
    with open(out, "wb") as f:
        pickle.dump({"M": M, "plan": plan, "allow": allow, "report": rep}, f)
    print("CHECK:", rep or "clean")
    F = M["F"]
    s = _start_stretch(np.c_[M["uv"], np.zeros(len(M["uv"]))], plan["start"], F)
    pc = M["piece"][F[:, 0]]
    for k, nm in enumerate(M["names"]):
        sel = pc == k
        if sel.any():
            i = np.where(sel)[0][np.argmax(s[sel])]
            print(f"  {nm:12s} max {s[sel].max():.2f} p99 {np.percentile(s[sel], 99):.2f} allow "
                  f"{(allow[sel].max() if allow is not None else 0):.2f} worst at uv {np.round(M['uv'][F[i]].mean(0), 3).tolist()}")
    raise SystemExit(0)


cloth.fine_start_check = spy
r = server.dress(name, garment=g, quality="final", wait=1200, note=f"tess2: {g} fsdump")
print(r if isinstance(r, str) else "\n".join(x for x in r if isinstance(x, str))[:3000])
