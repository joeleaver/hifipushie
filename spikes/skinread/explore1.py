"""explore1.py <model> <view>: photo | dressed render (photo light) | flat albedo | geometry mask overlay; timings and
the alignment of the ruler mesh's silhouette with the stage's."""
import os, sys, time
import numpy as np
from PIL import Image
from hifipushie import skin_read as sr, blockin as bi, likeness as lk, resources, store
from hifipushie import blockin_models, likeness_render, skin_read_frames

m, vi = sys.argv[1], int(sys.argv[2])
G = os.environ["G"] + "/out"
rj = blockin_models._refs(m)
cam, box = rj["cameras"][vi], skin_read_frames.boxes(m)[vi]
t = time.time()
with resources.heavy(f"skinread explore {m}", gb=6):
    sn = skin_read_frames.stage(m)
    print("stage", sn, round(time.time() - t), "s"); t = time.time()
    fr = [skin_read_frames.fitted_frame(cam, box, "v")]
    lt = skin_read_frames.lighting(m, vi)
    print("light", {k: v for k, v in lt.items() if k == "fitted"}, [l["energy"] for l in lt["lights"]])
    R = skin_read_frames.shoot(sn, fr, lt)["v"]
    print("shot", round(time.time() - t), "s"); t = time.time()
    A = skin_read_frames.shoot(sn, fr, None, flat=True)["v"]
    print("flat", round(time.time() - t), "s"); t = time.time()
N = sr.N
ph = Image.open(rj["views"][vi]["image"]).convert("RGB").crop(tuple(int(round(x)) for x in box)).resize((N, N), Image.LANCZOS)
mesh = likeness_render.model_mesh(store.load(m)["base"])
_, k, ps = likeness_render.render(mesh, cam, box, px=N, passes=True)
on = np.isfinite(ps["zb"])
ra = np.asarray(Image.fromarray(R).resize((N, N), Image.LANCZOS))
aa = np.asarray(Image.fromarray(A).resize((N, N), Image.LANCZOS))
al = ra[..., 3] > 128
print("silhouette: ruler mesh px", on.sum(), "stage px", al.sum(), "IoU", round((on & al).sum() / (on | al).sum(), 4),
      "ruler only", (on & ~al).sum(), "stage only", (al & ~on).sum())
ov = np.zeros((N, N, 3), np.uint8); ov[..., 0] = on * 255; ov[..., 1] = al * 255
W = Image.new("RGB", (4 * N, N), (200, 200, 200))
W.paste(ph, (0, 0))
for i, x in enumerate((ra, aa)):
    im = Image.fromarray(x); W.paste(im, ((i + 1) * N, 0), im)
W.paste(Image.fromarray(ov), (3 * N, 0))
W.save(f"{G}/ex1_{m}_{vi}.png"); print(f"{G}/ex1_{m}_{vi}.png")
np.savez_compressed(f"{G}/ex1_{m}_{vi}.npz", R=R, A=A)
