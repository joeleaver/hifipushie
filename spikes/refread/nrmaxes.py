"""nrmaxes.py <model> [view=0]: first look at the learned normals. The picture = the model's own dressed shot (cached
d_<model>_<view>.png); the estimator's normals against the mesh's own (likeness.render's normal pass through the same
camera): the axis signs that agree, the angular error on the skin, and a picture (estimate | mesh | angle error)."""
import sys, time
import numpy as np
from PIL import Image
from hifipushie import blockin as bi, face_ruler as fr, facenormals as fn, store

m, vi = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 0
spec, rj = store.load(m), bi._refs(m)
head = fr.model_head(spec)
cam, box = rj["cameras"][vi], rj["blockin"]["boxes"][vi]
shot = Image.open(f"/mnt/data/hifipushie/reruns/out/d_{m}_{vi}.png").convert("RGB")
n = shot.size[0]
ib = [int(round(x)) for x in box]
sc = n / float(ib[2] - ib[0])
view = {"cam": cam, "kind": "front", "img": shot, "scale": sc, "origin": (ib[0], ib[1])}
_, ps = fr._clay_crop(head, view)
N = ps["nrm"]
k = N.shape[0] / n
P = (fr._cam_points(cam, np.asarray(head["L"], float)[:68])[1] - ib[:2]) * sc
t = time.time()
res = fn.estimate(shot, fn.head_box(P, shot.size))
print(f"estimate: {time.time() - t:.0f} s; crop {res['box']}")
yy, xx = np.mgrid[0:N.shape[0]:4, 0:N.shape[1]:4]
ok = ps["part"][yy, xx] == 0
px = np.stack([xx[ok] / k, yy[ok] / k], 1)
E = fn.at(res, px) @ fn.AXES          # back to the raw output
M = N[yy[ok], xx[ok]]
g = np.isfinite(E).all(1) & (np.linalg.norm(M, axis=1) > 0.5)
E, M, px = E[g], M[g], px[g]
print("raw output . mesh normal, per axis pairing (rows = raw x y z, cols = mesh x y z):")
print(np.round(E.T @ M / len(E), 3))
for sg in ((1, 1, 1), (1, -1, -1), (1, 1, -1), (1, -1, 1), (-1, -1, -1), (-1, 1, -1)):
    a = np.degrees(np.arccos(np.clip(((E * sg) * M).sum(1), -1, 1)))
    print(f"signs {sg}: angle between estimate and mesh: median {np.median(a):.1f} deg, mean {a.mean():.1f}, p90 {np.percentile(a, 90):.1f}")
En = fn.at(res, px)
a = np.degrees(np.arccos(np.clip((En * M).sum(1), -1, 1)))
print(f"with facenormals.AXES: median {np.median(a):.1f} deg; mean normals est {np.round(En.mean(0), 3)} mesh {np.round(M.mean(0), 3)}")
vis = np.zeros((n, n * 3, 3), np.uint8)
full = fn.at(res, np.stack(np.meshgrid(np.arange(n), np.arange(n)), -1).reshape(-1, 2).astype(float)).reshape(n, n, 3)
vis[:, :n] = np.nan_to_num((full * 0.5 + 0.5) * 255)
Nr = np.asarray(Image.fromarray(((N * 0.5 + 0.5) * 255).astype(np.uint8)).resize((n, n)))
vis[:, n:2 * n] = Nr
Nf = Nr / 255.0 * 2 - 1
ang = np.degrees(np.arccos(np.clip((np.nan_to_num(full) * Nf).sum(-1), -1, 1)))
vis[:, 2 * n:] = np.clip(ang / 30.0, 0, 1)[..., None] * 255
Image.fromarray(vis).resize((n * 3 // 2, n // 2)).save(f"/mnt/data/hifipushie/refread/out/nrmaxes_{m}_{vi}.png")
