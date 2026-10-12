"""nsheet.py <out png> <title>=<model> ...: UNSEEN ANGLES with the reference pictures projected as skin: one row per
model, the stage's view_frames the references do not cover (other 3/4, right profile, low angle, front under a side
light is not here: the projection bakes the photo's own light). Where the shape is wrong the projected face bends."""
import os, sys
from PIL import Image, ImageDraw
sys.path[:0] = ["/home/joe/dev/hifipushie/spikes/garrett3"]
import stage
from hifipushie import blockin as bi, resources, store

G = os.environ.get("G", "/mnt/data/hifipushie/reruns") + "/out"
N = int(os.environ.get("SIZE", "560"))
VIEWS = ("three_quarter", "three_quarter_other", "profile_right", "low_angle")
out, cols = sys.argv[1], [a.split("=", 1) for a in sys.argv[2:]]
rows = []
for title, m in cols:
    rj = bi._refs(m)
    order = [i for i in range(len(rj["views"])) if i != bi._front(rj)] + [bi._front(rj)]
    fs = [f"{G}/n_{m}_{v}.png" for v in VIEWS]
    if not all(os.path.exists(f) for f in fs):
        fr = stage.view_frames(store.load(m), VIEWS)
        with resources.heavy(f"unseen angles {m}", gb=6):
            ims = stage.shoot(m, fr, stage.photo_light(m), size=N * 2, hair_on=False, tex=order)
        for f, v in zip(fs, VIEWS):
            im = ims[v]
            bg = Image.new("RGB", im.size, (200, 200, 200))
            bg.paste(im, mask=im.split()[-1] if im.mode == "RGBA" else None)
            bg.save(f)
    rows.append((title, [Image.open(f).convert("RGB").resize((N, N), Image.LANCZOS) for f in fs]))
W = Image.new("RGB", (N * len(VIEWS), (N + 26) * len(rows)), "white")
d = ImageDraw.Draw(W)
for r, (title, tiles) in enumerate(rows):
    d.text((6, r * (N + 26) + 6), title + ": her pictures projected, angles the references do not show", fill=(0, 0, 0))
    for k, t in enumerate(tiles):
        W.paste(t, (k * N, r * (N + 26) + 26))
W.save(out); print(out)
