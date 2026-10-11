"""jsheet.py <out png> <title>=<model> ...: the JUDGING sheet. Per model one block of rows (one per reference view):
photo | 50 % blend | the model with the reference pictures projected as its skin (stage tex=, front most trusted) |
the model in its own dressing. Shots through each view's fitted camera at the block-in's boxes; cached in $G/out
(j_<model>_<view>.png projected, d_<model>_<view>.png own dressing). Prints face-ID cosines (projected shot vs photo)."""
import os, sys
from PIL import Image, ImageDraw
sys.path[:0] = ["/home/joe/dev/hifipushie/spikes/garrett3"]
import stage
from hifipushie import blockin as bi, resources, faceid

G = os.environ.get("G", "/mnt/data/hifipushie/reruns") + "/out"
N = int(os.environ.get("SIZE", "520"))
out, cols = sys.argv[1], [a.split("=", 1) for a in sys.argv[2:]]


def shot(m, vi, cam, ib, tex):
    f = f"{G}/{'j' if tex else 'd'}_{m}_{vi}.png"
    if not os.path.exists(f):
        rj = bi._refs(m)
        order = [i for i in range(len(rj["views"])) if i != bi._front(rj)] + [bi._front(rj)]
        with resources.heavy(f"judging shot {m} {vi}", gb=6):
            im = stage.shoot(m, [stage.fitted_frame(cam, [float(x) for x in ib], f"v{vi}")], stage.photo_light(m, vi), size=N * 2,
                             hair_on=False, tex=order if tex else None)[f"v{vi}"]
        bg = Image.new("RGB", im.size, (200, 200, 200))
        bg.paste(im, mask=im.split()[-1] if im.mode == "RGBA" else None)
        bg.save(f)
    return Image.open(f).convert("RGB").resize((N, N), Image.LANCZOS)


HEAD = 30
blocks = []
for title, m in cols:
    rj = bi._refs(m)
    rows = []
    for vi, (v, cam, box) in enumerate(zip(rj["views"], rj["cameras"], rj["blockin"]["boxes"])):
        ib = [int(round(x)) for x in box]
        ph = Image.open(v["image"]).convert("RGB").crop(tuple(ib)).resize((N, N), Image.LANCZOS)
        j, d_ = shot(m, vi, cam, ib, True), shot(m, vi, cam, ib, False)
        rows.append([ph, Image.blend(ph, j, 0.5), j, d_])
        try:
            sc = faceid.scores(ph, [j, d_])
            print(f"{m} view {vi}: face-ID vs photo: projected skin {sc[0]}, own dressing {sc[1]}")
        except Exception as e:  # noqa: BLE001
            print(m, vi, "face-ID failed", repr(e)[:120])
    b = Image.new("RGB", (4 * N, HEAD + N * len(rows)), "white")
    dr = ImageDraw.Draw(b)
    for k, t in enumerate((f"{title}: photo", "50 % blend (photo + projected)", "her pictures projected as skin", "its own dressing")):
        dr.text((k * N + 6, 8), t, fill=(0, 0, 0))
    for r, row in enumerate(rows):
        for k, t in enumerate(row):
            b.paste(t, (k * N, HEAD + r * N))
    blocks.append(b)
W = Image.new("RGB", (max(b.size[0] for b in blocks), sum(b.size[1] for b in blocks)), "white")
y = 0
for b in blocks:
    W.paste(b, (0, y)); y += b.size[1]
W.save(out); print(out)
