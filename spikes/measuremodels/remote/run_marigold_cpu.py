"""Marigold normals on CPU: run_marigold_cpu.py <model: v11 | lcm> <out dir> <steps> <res> <png>...
<out>/<id>.npz with normal (H, W, 3) float16 at the picture's size. Skips pictures already done."""
import os, sys, time
import numpy as np, torch, diffusers, cv2
from PIL import Image
REPO = {"v11": "prs-eth/marigold-normals-v1-1", "lcm": "prs-eth/marigold-normals-lcm-v0-1"}
model, out, steps, res = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
os.makedirs(out, exist_ok=True)
torch.set_num_threads(int(os.environ.get("MG_THREADS", "8")))
try:
    pipe = diffusers.MarigoldNormalsPipeline.from_pretrained(REPO[model], variant="fp16", torch_dtype=torch.float32)
except Exception:
    pipe = diffusers.MarigoldNormalsPipeline.from_pretrained(REPO[model], torch_dtype=torch.float32)
pipe.set_progress_bar_config(disable=True)
t0 = time.time()
for p in sys.argv[5:]:
    o = os.path.join(out, os.path.basename(p)[:-4] + ".npz")
    if os.path.exists(o):
        continue
    im = Image.open(p).convert("RGB")
    with torch.no_grad():
        n = pipe(im, num_inference_steps=steps, ensemble_size=1, processing_resolution=res,
                 generator=torch.Generator().manual_seed(0)).prediction[0]
    n = np.asarray(n, np.float32)
    if n.shape[:2] != im.size[::-1]:
        n = cv2.resize(n, im.size, interpolation=cv2.INTER_LINEAR)
    np.savez_compressed(o + ".tmp.npz", normal=n.astype(np.float16))
    os.replace(o + ".tmp.npz", o)
    print(os.path.basename(p), round(time.time() - t0, 1), flush=True)
print("done", model, time.time() - t0)
