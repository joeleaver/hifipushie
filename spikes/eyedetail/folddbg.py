"""folddbg.py <model>: the fold curve of a model's eye 0: spacing, distance of its samples from the base surface,
normals' and ups' turn between neighbours; and the field's profile across the crease at s 0.3 / 0.5 / 0.7."""
import sys

import numpy as np

from hifipushie import base as basemod, lidfold, sdf, store
from hifipushie.spec import compile_prims, expand_mirror

spec = store.load(sys.argv[1])
s = expand_mirror(spec)
cfg = lidfold.config(s)
head = basemod.head_of(s, s["base"])
prims = compile_prims(spec)
base = [p for p in prims if p.kind == "base" and p.part == "body"]
c = lidfold.curves(head, cfg, field=lambda X: sdf.field_at(base, X, clip=False))[0]
c_head = lidfold.curves(head, cfg)[0]
prims = compile_prims(spec)
base = [p for p in prims if p.kind == "base" and p.part == "body"]
fold = [p for p in prims if p.kind == "fold"]
print("fold prims", [(p.name, p.part, p.op) for p in fold], "base part", base[0].part)
q = c["pts"][36:37]
print("field base", sdf.field_at(base, q), "base+fold", sdf.field_at(base + fold, q), "fold pts dist", np.linalg.norm(fold[0].params["pts"][36] - q[0]))
P = c["pts"]
f0 = sdf.field_at(base, P)
print("head-seated vs field-seated mm", np.round(np.linalg.norm(c_head["pts"] - c["pts"], axis=1) * 1000, 2)[::4])
print("spacing mm", np.round(np.linalg.norm(np.diff(P, axis=0), axis=1) * 1000, 2)[::6])
print("off surface mm", np.round(f0 * 1000, 2)[::4])
print("normal turn deg", np.round(np.degrees(np.arccos(np.clip((c["nrm"][1:] * c["nrm"][:-1]).sum(1), -1, 1))), 1)[::4])
print("up turn deg", np.round(np.degrees(np.arccos(np.clip((c["up"][1:] * c["up"][:-1]).sum(1), -1, 1))), 1)[::4])
print("h mm", np.round(c["h"] * 1000, 2)[::6])
for si in (0.3, 0.5, 0.7):
    i = int(np.argmin(np.abs(c["s"] - si)))
    t = np.linspace(-4, 5, 37) * 0.001
    Q = P[i] + t[:, None] * c["up"][i]
    # along the normal through each point: where the surfaces sit (base vs base + fold)
    hs = np.linspace(-3, 3, 241) * 0.001
    row_b, row_f = [], []
    for q in Q:
        L = q + hs[:, None] * c["nrm"][i]
        fb = sdf.field_at(base, L)
        ff = sdf.field_at(base + fold, L)
        zb = hs[np.argmin(np.abs(fb))]
        zf = hs[np.argmin(np.abs(ff))]
        row_b.append(zb)
        row_f.append(zf)
    print(f"s {si}: t mm / surface move (fold - base) mm")
    print("  ", " ".join(f"{tt * 1000:+.1f}:{(b - a) * 1000:+.2f}" for tt, a, b in zip(t[::2], row_b[::2], row_f[::2])))
fp = lidfold.prims(s, base[0])
print("direct prims dist", np.linalg.norm(fp[0].params["pts"][36] - q[0]))
import inspect; from hifipushie import spec as specmod; print([l for l in inspect.getsource(specmod._compile).splitlines() if "lidfold" in l])
from hifipushie import spec as specmod
g = specmod.geometry(spec); sg = expand_mirror(g)
b0 = specmod._base(sg, 0.03)
print("fresh base vs compiled at q", sdf.field_at([b0], q, clip=False), sdf.field_at(base, q, clip=False))
print("lo/hi", b0.lo, b0.hi, base[0].lo, base[0].hi)
fp2 = lidfold.prims(sg, b0); print("prims on geometry-expanded spec dist", np.linalg.norm(fp2[0].params["pts"][36] - q[0]))
fp3 = lidfold.prims(s, base[0]); print("prims with compiled base dist", np.linalg.norm(fp3[0].params["pts"][36] - q[0]))
print("c", c["pts"][36], "c_head", c_head["pts"][36], "fp", fp[0].params["pts"][36], "fpR", fp[1].params["pts"][36])
cc = lidfold.curves(head, cfg, field=lambda X: sdf.field_at([base[0]], X, clip=False))
print("cc0", cc[0]["pts"][36], "cc1", cc[1]["pts"][36])
