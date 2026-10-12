"""jl_look.py <model> <out.png> [views=0,1]: a first LOOK at the jaw's lower edge as a SHADING edge: the reference picture
and the model's own render under the picture's fitted light (blockin.lit_render: c0 + w.n, AO, soft cast shadow), both
with the model's jaw line (GNM lm 3..13 through the fitted camera) and search lines across it; then the luminance
profiles along those lines (picture = black, render = red), outward = right."""
import sys, time
import numpy as np
from PIL import Image, ImageDraw
from hifipushie import face_ruler as fr, blockin as bi, store

m, out = sys.argv[1], sys.argv[2]
vs = [int(x) for x in (sys.argv[3].split("=")[1].split(",") if len(sys.argv) > 3 else "0,1")]
rj = bi._refs(m)
head = fr.model_head(store.load(m))
tiles = []
for vi in vs:
    v, cam = rj["views"][vi], rj["cameras"][vi]
    img = Image.open(v["image"]).convert("RGB")
    t = time.time()
    im, lt, ps = bi.lit_render(head["mesh"], cam, img)
    print(f"view {vi}: lit_render {time.time() - t:.1f} s; light c0 {lt[0]:.3f} w {np.round(lt[1], 3)} ao share {lt[3]:.2f}; render {im.size}")
    k = im.size[1] / img.size[1]
    L = np.asarray(head["L"], float)
    P = fr._cam_points(cam, L[:68])[1]
    mm = float(cam["t"][2]) / cam["f"] * 1000.0
    a = np.asarray(img, float) / 255.0
    b = np.asarray(im.resize(img.size, Image.LANCZOS).convert("RGB"), float) / 255.0
    la, lb = a @ [0.299, 0.587, 0.114], b @ [0.299, 0.587, 0.114]
    # the jaw polyline, resampled every 4 mm
    J = P[2:15]
    S = fr._resample(J, 4.0 / mm)
    T = np.gradient(S, axis=0); T /= np.linalg.norm(T, axis=1, keepdims=True)
    N = np.stack([-T[:, 1], T[:, 0]], 1)
    c = P[[30, 8]].mean(0)
    N[((S - c) * N).sum(1) < 0] *= -1                      # outward: away from the face's middle
    ts = np.arange(-12, 12.01, 0.25) / mm
    pa, pb = [], []
    for s_, n_ in zip(S, N):
        q = s_[None] + ts[:, None] * n_[None]
        pa.append(fr._bil(la, q[:, 0], q[:, 1])); pb.append(fr._bil(lb, q[:, 0], q[:, 1]))
    x0, x1 = int(P[:17, 0].min() - 30), int(P[:17, 0].max() + 30)
    y0, y1 = int(P[[1, 15], 1].min() - 20), int(P[8, 1] + 110)
    for src in (img, im.resize(img.size, Image.LANCZOS)):
        t_ = src.copy(); d = ImageDraw.Draw(t_)
        d.line([tuple(p) for p in J], fill=(0, 230, 0), width=2)
        for i, (s_, n_) in enumerate(zip(S, N)):
            d.line([tuple(s_ - 12 / mm * n_), tuple(s_ + 12 / mm * n_)], fill=(255, 230, 0), width=1)
            d.text(tuple(s_ + 14 / mm * n_), str(i), fill=(255, 0, 0))
        tiles.append(t_.crop((x0, y0, x1, y1)))
    # the profiles
    n = len(S); w, h = 150, 90
    pl = Image.new("RGB", (w * 8, h * ((n + 7) // 8)), "white"); d = ImageDraw.Draw(pl)
    for i in range(n):
        ox, oy = (i % 8) * w, (i // 8) * h
        for prof, col in ((pa[i], (0, 0, 0)), (pb[i], (220, 0, 0))):
            pts = [(ox + 5 + j * (w - 10) / (len(ts) - 1), oy + h - 5 - float(np.clip(p_, 0, 1)) * (h - 10)) for j, p_ in enumerate(prof)]
            d.line(pts, fill=col, width=1)
        d.line([(ox + w / 2, oy), (ox + w / 2, oy + h)], fill=(0, 160, 0))
        d.text((ox + 4, oy + 2), str(i), fill=(0, 0, 255))
    tiles.append(pl)
W = max(t.size[0] for t in tiles)
sheet = Image.new("RGB", (W, sum(t.size[1] for t in tiles)), "white")
y = 0
for t in tiles:
    sheet.paste(t, (0, y)); y += t.size[1]
sheet.save(out)
print(out)
