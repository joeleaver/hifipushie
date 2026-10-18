"""eyeflat.py <glb> <out.png>: flat front albedo pass (no light) of the left eye region, head + eyes + lashes off (0.1 mm/px)."""
import sys, numpy as np
from PIL import Image
glb_, out_ = sys.argv[1], sys.argv[2]
sys.argv = [sys.argv[0], glb_, "/dev/null", "neutral"]
src = open("/mnt/data/hifipushie/assembly/mouthhits_v1.py").read()
exec(src.split("base = raster({})")[0].replace('PARTS = ["head", "teeth", "teeth_lower", "tongue"]', 'PARTS = ["head", "eyes"]'))
E = g["meshes"]["eyes"]["V"]; ev = E[E[:, 0] > 0]; cx, cz = np.median(ev[:, 0]), np.median(ev[:, 2])
S = 0.0001; X0, X1, Z0, Z1 = cx - .022, cx + .022, cz - .016, cz + .02
W, H = int((X1 - X0) / S), int((Z1 - Z0) / S)
pid, fid, ny, alb = raster({})
Image.fromarray(alb.astype(np.uint8)).save(out_); print(W, H)
