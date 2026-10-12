"""rsheet.py <out png> <title>=<best model> <title>=<other> ...: the JUDGING sheet laid out reference | best | the rest.
One row per reference view: the picture | BEST: 50 % blend (picture + projected), the reference pictures projected as
its skin, its own dressing | each other model: blend, projected. Shots as spikes/reruns/jsheet.py (stage.shoot
through each view's fitted camera at the block-in's box; cached j_/d_<model>_<view>.png in $G/out, the reruns'
cached shots copied in if they exist)."""
import os, shutil, sys
from PIL import Image, ImageDraw
sys.path[:0] = ["/home/joe/dev/hifipushie/spikes/garrett3"]
from hifipushie import blockin as bi, resources

G = os.environ.get("G", "/mnt/data/hifipushie/refread") + "/out"
OLD = "/mnt/data/hifipushie/reruns/out"
N = int(os.environ.get("SIZE", "440"))
out, cols = sys.argv[1], [a.split("=", 1) for a in sys.argv[2:]]


def shot(m, vi, cam, ib, tex):
    f = f"{G}/{'j' if tex else 'd'}_{m}_{vi}.png"
    if not os.path.exists(f) and os.path.exists(f"{OLD}/{os.path.basename(f)}"):
        shutil.copy(f"{OLD}/{os.path.basename(f)}", f)
    if not os.path.exists(f):
        import stage
        rj = bi._refs(m)
        order = [i for i in range(len(rj["views"])) if i != bi._front(rj)] + [bi._front(rj)]
        with resources.heavy(f"judging shot {m} {vi}", gb=6):
            im = stage.shoot(m, [stage.fitted_frame(cam, [float(x) for x in ib], f"v{vi}")], stage.photo_light(m, vi), size=1040,
                             hair_on=False, tex=order if tex else None)[f"v{vi}"]
        bg = Image.new("RGB", im.size, (200, 200, 200))
        bg.paste(im, mask=im.split()[-1] if im.mode == "RGBA" else None)
        bg.save(f)
    return Image.open(f).convert("RGB").resize((N, N), Image.LANCZOS)


HEAD = 34
rows, heads = [], None
nv = len(bi._refs(cols[0][1])["views"])
for vi in range(nv):
    row, hd = [], []
    for k, (title, m) in enumerate(cols):
        rj = bi._refs(m)
        v, cam, box = rj["views"][vi], rj["cameras"][vi], rj["blockin"]["boxes"][vi]
        ib = [int(round(x)) for x in box]
        ph = Image.open(v["image"]).convert("RGB").crop(tuple(ib)).resize((N, N), Image.LANCZOS)
        if k == 0:
            row.append(ph); hd.append("REFERENCE")
        j = shot(m, vi, cam, ib, True)
        row += [Image.blend(ph, j, 0.5), j]
        hd += [f"{title}: 50 % blend", f"{title}: refs projected as skin"]
        if k == 0:
            row.append(shot(m, vi, cam, ib, False)); hd.append(f"{title}: own dressing")
    rows.append(row); heads = hd
W = Image.new("RGB", (N * len(rows[0]), HEAD + N * len(rows)), "white")
d = ImageDraw.Draw(W)
for k, t in enumerate(heads):
    d.text((k * N + 6, 10), t, fill=(0, 0, 0))
for r, row in enumerate(rows):
    for k, t in enumerate(row):
        W.paste(t, (k * N, HEAD + r * N))
W.save(out)
print(out)
