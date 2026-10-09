"""A transformers depth-estimation model on a folder: <out>/<id>.npz with depth (model's own units: relative inverse
depth for Depth Anything V2 relative checkpoints, metres for metric ones)."""
import glob, os, sys, time
import numpy as np, torch
from PIL import Image
from transformers import AutoImageProcessor, AutoModelForDepthEstimation
name, src, out = sys.argv[1:4]
os.makedirs(out, exist_ok=True)
proc = AutoImageProcessor.from_pretrained(name)
m = AutoModelForDepthEstimation.from_pretrained(name).cuda().eval()
t0 = time.time()
for p in sorted(glob.glob(src + "/*.png")):
    im = Image.open(p).convert("RGB")
    x = proc(images=im, return_tensors="pt").to("cuda")
    with torch.no_grad():
        d = m(**x).predicted_depth
    d = torch.nn.functional.interpolate(d[None], size=im.size[::-1], mode="bicubic", align_corners=False)[0, 0]
    np.savez_compressed(os.path.join(out, os.path.basename(p)[:-4] + ".npz"), depth=d.cpu().numpy().astype(np.float32))
print("done", name, time.time() - t0)
