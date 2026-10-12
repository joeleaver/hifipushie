"""nrmdbg.py: the estimator's normals on two dressed shots of nearly the same head (tk_T06 and nv_cf_p = + cheek_fullness
1.5), compared pixel by pixel on the skin: where do 25 deg differences come from?"""
import numpy as np
from PIL import Image
from hifipushie import blockin as bi, face_ruler as fr, facenormals as fnm, store

m = "tk_T06"
rj = bi._refs(m)
A = fr.model_head(store.load(m))
for vi in range(3):
    cam, box = rj["cameras"][vi], rj["blockin"]["boxes"][vi]
    ib = [int(round(x)) for x in box]
    a = Image.open(f"/mnt/data/hifipushie/reruns/out/d_{m}_{vi}.png").convert("RGB")
    b = Image.open(f"/mnt/data/hifipushie/refread/out/nv_nv_cf_p_{vi}.png").convert("RGB")
    sc = a.size[0] / float(ib[2] - ib[0])
    PL = (fr._cam_points(cam, np.asarray(A["L"], float)[:68])[1] - ib[:2]) * sc
    bx = fnm.head_box(PL, a.size)
    na, nb = fnm.estimate(a, bx)["n"], fnm.estimate(b, bx)["n"]
    ang = np.degrees(np.arccos(np.clip((na * nb).sum(-1), -1, 1)))
    d = np.abs(np.asarray(a, float) - np.asarray(b, float)).mean()
    print(f"view {vi}: sizes {a.size} {b.size}; mean |pixel difference| {d:.1f}; normals differ: median {np.median(ang):.1f} deg, p90 {np.percentile(ang, 90):.1f}")
    Image.fromarray(np.hstack([np.asarray(a.resize((400, 400))), np.asarray(b.resize((400, 400)))])).save(f"/mnt/data/hifipushie/refread/out/nrmdbg_{vi}.png")
