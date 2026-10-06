"""var.py <model> <out.png> <common k=v ...> -- <label>: k=v ... [-- <label>: ...]: one row a variant (spec overrides
held in memory, nothing saved). Keys: views= size= engine= count= samples= budget= style=; skip=A,B (drop modifiers
whose name contains A or B); look.k=v; groom.a.b=v; other k=v = hair.strands dials."""
import json, os, sys, time
from PIL import Image, ImageDraw
from hifipushie import hair, store, hair_strands as HS

name, out = sys.argv[1], sys.argv[2]
groups, cur = [[]], None
for a in sys.argv[3:]:
    if a == "--":
        groups.append([])
    else:
        groups[-1].append(a)
common, variants = groups[0], groups[1:] or [["base:"]]
_st = HS.stacks


def run(args, label):
    spec = store.load(name)
    h = spec.setdefault("hair", {})
    h.setdefault("style", "strands")
    views, size, kw, skip = ("close_front", "three_quarter"), 480, {"clay": False}, []
    for a in args:
        k, v = a.split("=", 1)
        if k == "style": h["style"] = v
        elif k == "views": views = tuple(v.split(","))
        elif k == "size": size = int(v)
        elif k == "engine": kw["engine"] = v
        elif k in ("count", "samples"): kw[k] = int(v)
        elif k == "budget": kw["budget"] = int(v) if v.isdigit() else v
        elif k == "skip": skip = v.split(",")
        elif k == "light": kw["light"] = v
        elif k == "denoise": kw["denoise"] = bool(int(v))
        elif k.startswith("look."): h.setdefault("look", {})[k[5:]] = json.loads(v) if v[:1] != "#" else v
        elif k.startswith("groom."):
            d = h.setdefault("groom", {})
            ks = k[6:].split(".")
            for q in ks[:-1]: d = d.setdefault(q, {})
            d[ks[-1]] = json.loads(v)
        else: h.setdefault("strands", {})[k] = json.loads(v)

    def stacks(*a, **k):
        d = _st(*a, **k)
        return {n: [m for m in st if not any(q in m[0] for q in skip)] for n, st in d.items()}
    HS.stacks = stacks
    hair.validate(spec)
    t = time.time()
    sheet, sec, fr = hair.look(name, views=views, size=size, spec=spec, **kw)
    st = [l for l in fr if "strands" in l]
    print(label, sec, "s", "bare", hair.look.mass_share, st[0][:200] if st else "", flush=True)
    return sheet.crop((0, 22, size * len(views), 22 + size)), f"{label}   {sec}s"


rows = []
for v in variants:
    label = v[0].rstrip(":")
    rows.append(run(common + v[1:], label))
W = max(r.width for r, _ in rows)
img = Image.new("RGB", (W, sum(r.height + 20 for r, _ in rows)), (30, 31, 35))
d = ImageDraw.Draw(img)
y = 0
for r, lab in rows:
    d.text((6, y + 4), lab, fill=(240, 220, 160))
    img.paste(r, (0, y + 20))
    y += r.height + 20
img.save(out if os.path.isabs(out) else os.path.join(os.environ["HR"], out))
