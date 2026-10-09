"""bake_age.py: the older shape ops (headage / base.head.shape: nasolabial, prejowl, cheek_flat, lid_fold, planes, lean,
hollow, chin cleft) baked ONCE into morph targets for faceslide: each op at its unit amount on a sex-neutral template
adult (one mesh, no identity) minus the same head without it, the skin's move taken back into GNM's frame
(world = s * d @ R.T). Writes src/hifipushie/face_sliders_baked.npz (float32, GNM's 17821 vertices; the loops take
their parents' mean at load). Run: run.sh bake_age.py"""
import copy
from pathlib import Path

import numpy as np

from hifipushie import base as basemod
from hifipushie import faceslide, humans, onemesh

OUT = Path(basemod.__file__).with_name("face_sliders_baked.npz")
b0 = humans.spec(age=40, sex=0.5, seed=None, skin=False, source="human")["base"]


def head(shape):
    b = copy.deepcopy(b0)
    if shape:
        b.setdefault("head", {})["shape"] = shape
    onemesh._CACHE.pop("never", None)
    return onemesh.head_template(b)


g = basemod._gnm_data()
skin_ids = np.flatnonzero(g["skin"])
h0 = head(None)
assert h0.get("skin_index") is None, "the template's lips must not be zipped for the bake"
R, s = np.asarray(h0["carry"]["R"], float), float(h0["carry"]["s"])
out = {}
for name, shape in faceslide.BAKED.items():
    h1 = head(shape)
    dW = np.asarray(h1["verts"], float) - np.asarray(h0["verts"], float)
    d = np.zeros((len(g["template_vertex_positions"]), 3))
    d[skin_ids] = dW @ R / s
    out[name] = d.astype(np.float32)
    print(name, shape, "max move mm", round(1000 * float(np.linalg.norm(dW, axis=1).max()), 2))
np.savez_compressed(OUT, **out)
print(OUT, OUT.stat().st_size)
