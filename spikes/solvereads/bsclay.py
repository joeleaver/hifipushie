"""bsclay.py <model> ...: the detector's blendshape scores on each model's own CLAY picture through its front camera
(what the differential anchors' render is): does the IDENTITY read as an expression (brow down, squint) with no
dressing in the way? Also with a known expression added (arg +class=amount applies to the models after it)."""
import copy, sys
from hifipushie import blockin as bi, face_ruler as fr, likeness, store
from hifipushie import blockin_models, face_ruler_blockin, likeness_detect, likeness_render, likeness_sides
cols, D, ex = [], [], {}
for a in sys.argv[1:]:
    if a.startswith("+"):
        k, v = a[1:].split("=")
        ex[k] = float(v)
        continue
    spec, rj = copy.deepcopy(store.load(a)), blockin_models._refs(a)
    if ex:
        spec["base"]["head"]["expression"] = face_ruler_blockin.expression_coeffs(ex)
    head = face_ruler_blockin.model_head(spec)
    cam, v = rj["cameras"][0], rj["views"][0]
    from PIL import Image
    box = likeness_sides._box(dict(v.get("points") or {}), Image.open(v["image"]).size)
    im = likeness_render.render(head["mesh"], cam, box)[0]
    im.save(f"/mnt/data/hifipushie/solvereads/out/bsclay_{a}{'_x' if ex else ''}.png")
    D.append(likeness_detect.detect_info([im])[0])
    cols.append(a[-8:] + ("+x" if ex else ""))
keys = sorted({k for d in D if d for k, v in (d.get("bs") or {}).items() if v > 0.08})
print(" " * 22 + "  ".join(f"{c:>10s}" for c in cols))
for k in keys:
    print(f"{k:22s}" + "  ".join(f"{(d.get('bs') or {}).get(k, 0):10.2f}" if d else "      none" for d in D))
