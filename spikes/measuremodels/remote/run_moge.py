"""MoGe / MoGe-2 on a folder: <out>/<id>.npz with points (camera frame, x right y down z forward), depth, normal, mask, K."""
import glob, os, sys, time
import numpy as np, torch
from PIL import Image
name, src, out = sys.argv[1:4]     # e.g. Ruicheng/moge-2-vitl-normal
os.makedirs(out, exist_ok=True)
if "moge-2" in name:
    from moge.model.v2 import MoGeModel
else:
    from moge.model.v1 import MoGeModel
m = MoGeModel.from_pretrained(name).cuda().eval()
t0 = time.time()
for p in sorted(glob.glob(src + "/*.png")):
    im = torch.tensor(np.asarray(Image.open(p).convert("RGB")) / 255.0, dtype=torch.float32).permute(2, 0, 1).cuda()
    with torch.no_grad():
        o = m.infer(im)
    d = {k: v.float().cpu().numpy().astype(np.float32) for k, v in o.items() if torch.is_tensor(v)}
    np.savez_compressed(os.path.join(out, os.path.basename(p)[:-4] + ".npz"), **d)
print("done", name, time.time() - t0, list(d.keys()))
