"""pose.py <src> <dst> <shape>=<weight> ... [ex:<component>=<value> ...]: a FORK of <src> posed in ARKit-named face
shapes (and / or raw GNM expression components, e.g. ex:pupils_000=-1): the shapes' GNM expression coefficients
(faceshapes.GnmFace.shape_coeffs) summed into base.head.expression, on top of what the model already has.
The posed model is a scratch look model: every component follows from the one expression vector."""
import sys

from hifipushie import blockin as bi
from hifipushie import faceshapes, store

src, dst = sys.argv[1:3]
sp = store.load(src)
face = faceshapes.GnmFace(sp)
ex = dict(sp["base"]["head"].get("expression") or {})
said = []
for a in sys.argv[3:]:
    k, v = a.split("=", 1)
    v = float(v)
    if k.startswith("ex:"):
        ex[k[3:]] = ex.get(k[3:], 0.0) + v
    else:
        for n, c in face.shape_coeffs(k).items():
            ex[n] = ex.get(n, 0.0) + v * c
    said.append(a)
bi.fork(src, dst, replace=True)
sp = store.load(dst)
sp["base"]["head"]["expression"] = {k: round(float(v), 5) for k, v in ex.items() if abs(v) > 1e-6}
bi._save(dst, sp, f"gnmnative pose of {src}: {' '.join(said)}", bi._refs(dst))
print(dst, "posed:", " ".join(said), f"({len(sp['base']['head']['expression'])} expression components, largest "
      f"{max(abs(v) for v in sp['base']['head']['expression'].values()):.2f}); mouth:", "GNM's own" if face.gnm_mouth else "the kit's")
