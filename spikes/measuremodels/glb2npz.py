"""Oxidegen's TRELLIS.2 GLBs -> MM/trellis/<name>.npz (V in OUR axes: z up, facing -y, left +x; F).
uv run --no-project --with trimesh --with numpy python glb2npz.py   (reads the GLBs read-only)"""
import glob, os
import numpy as np, trimesh
SRC = "/home/joe/dev/oxidegen/artifacts/head_prior/out"
DST = "/mnt/data/hifipushie/measuremodels/trellis"
os.makedirs(DST, exist_ok=True)
for p in sorted(glob.glob(SRC + "/*.glb")):
    o = os.path.join(DST, os.path.basename(p)[:-4] + ".npz")
    if os.path.exists(o):
        continue
    m = trimesh.load(p, force="mesh", process=False)
    V = np.asarray(m.vertices, float)
    V = np.stack([V[:, 0], -V[:, 2], V[:, 1]], 1)
    np.savez_compressed(o, V=V.astype(np.float32), F=np.asarray(m.faces, np.int32))
    print(os.path.basename(o), V.shape, len(m.faces), np.round(V.min(0), 3), np.round(V.max(0), 3))
