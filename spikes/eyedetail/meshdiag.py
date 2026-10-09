"""meshdiag.py <stage model A> <stage model B>: the scene meshes' sagittal slices through eye.L (B - A), and the
render normals' tilt there: does the crease reach the scene's mesh?"""
import glob
import sys

import numpy as np

from crease_diag_lib import slice_mesh
from hifipushie import store
from hifipushie.spec import expand_mirror


def load(name):
    best = None
    for f in glob.glob(str(store._dir(name) / "scene_cache" / "*.npz")):
        z = np.load(f, allow_pickle=True)
        if "verts" in z.files and (best is None or len(z["verts"]) > len(best[1]["verts"])):
            best = (f, {k: z[k] for k in z.files})
    print(name, best[0].split("/")[-1], list(best[1].keys()), len(best[1]["verts"]))
    return best[1]


A, B = sys.argv[1], sys.argv[2]
J = {k: np.asarray(v["pos"], float) for k, v in expand_mirror(store.load(A))["joints"].items() if "pos" in v}
ex, ey, ez = J["eye.L"]
out = []
for nm in (A, B):
    m = load(nm)
    F = m.get("faces", m.get("tris"))
    z, y = slice_mesh(m["verts"].astype(float), F, ex, ez, ey)
    out.append(y)
print("z over eye centre (mm) | A y | B - A (mm, + = back)")
for i in range(0, len(z), 5):
    print(f"{(z[i] - ez) * 1000:5.1f}  {(out[0][i] - ey) * 1000:+7.2f}  {(out[1][i] - out[0][i]) * 1000:+.3f}")
