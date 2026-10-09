"""MapAnything (Apache checkpoint) on PAIRS of pictures of one head (front + tq): <out>/<id>.npz per view with
points (that view's camera frame), depth, K (pixels), plus world points and pose in <out>/<subject>_pair.npz."""
import glob, os, sys, time
import numpy as np, torch
from mapanything.models import MapAnything
from mapanything.utils.image import load_images
src, out = sys.argv[1:3]
views = sys.argv[3:] or ["front", "tq"]
os.makedirs(out, exist_ok=True)
model = MapAnything.from_pretrained("facebook/map-anything-apache").to("cuda").eval()
subs = sorted({os.path.basename(p)[: -len("_front.png")] for p in glob.glob(src + "/*_front.png")})
t0 = time.time()
for s in subs:
    paths = [f"{src}/{s}_{v}.png" for v in views]
    if not all(os.path.exists(p) for p in paths):
        continue
    with torch.no_grad():
        preds = model.infer(load_images(paths), memory_efficient_inference=False, use_amp=True)
    for v, p in zip(views, preds):
        d = {"points": p["pts3d_cam"][0].float().cpu().numpy(), "depth": p["depth_z"][0, ..., 0].float().cpu().numpy(),
             "K": p["intrinsics"][0].float().cpu().numpy(), "pose": p["camera_poses"][0].float().cpu().numpy(),
             "world": p["pts3d"][0].float().cpu().numpy(), "conf": p["conf"][0].float().cpu().numpy()}
        np.savez_compressed(f"{out}/{s}_{v}.npz", **{k: x.astype(np.float32) for k, x in d.items()})
print("done mapanything", time.time() - t0, {k: x.shape for k, x in d.items()})
