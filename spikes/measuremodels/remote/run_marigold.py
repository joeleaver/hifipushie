"""Marigold normals on a folder: run_marigold.py <src> <out> [v11 | lcm] [steps] -> <out>/<id>.npz with normal (H, W, 3).
v11 = prs-eth/marigold-normals-v1-1 (OpenRAIL++-M), lcm = prs-eth/marigold-normals-lcm-v0-1 (Apache-2.0)."""
import glob, os, sys, time
import numpy as np, torch, diffusers
from PIL import Image
src, out = sys.argv[1:3]
model = sys.argv[3] if len(sys.argv) > 3 else "v11"
steps = int(sys.argv[4]) if len(sys.argv) > 4 else 4
REPO = {"v11": "prs-eth/marigold-normals-v1-1", "lcm": "prs-eth/marigold-normals-lcm-v0-1"}[model]
os.makedirs(out, exist_ok=True)
try:
    pipe = diffusers.MarigoldNormalsPipeline.from_pretrained(REPO, variant="fp16", torch_dtype=torch.float16).to("cuda")
except Exception:
    pipe = diffusers.MarigoldNormalsPipeline.from_pretrained(REPO, torch_dtype=torch.float16).to("cuda")
pipe.set_progress_bar_config(disable=True)
t0 = time.time()
for p in sorted(glob.glob(src + "/*.png")):
    im = Image.open(p).convert("RGB")
    n = pipe(im, num_inference_steps=steps, ensemble_size=3, generator=torch.Generator("cuda").manual_seed(0)).prediction[0]
    n = np.asarray(n, np.float32)
    if n.shape[:2] != im.size[::-1]:
        import cv2
        n = cv2.resize(n, im.size, interpolation=cv2.INTER_LINEAR)
    np.savez_compressed(os.path.join(out, os.path.basename(p)[:-4] + ".npz"), normal=n.astype(np.float16))
print("done marigold", model, time.time() - t0, n.shape)
