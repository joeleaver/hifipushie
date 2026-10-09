"""Marigold normals v1-1 on a folder: <out>/<id>.npz with normal (H, W, 3)."""
import glob, os, sys, time
import numpy as np, torch, diffusers
from PIL import Image
src, out = sys.argv[1:3]
os.makedirs(out, exist_ok=True)
pipe = diffusers.MarigoldNormalsPipeline.from_pretrained("prs-eth/marigold-normals-v1-1", variant="fp16", torch_dtype=torch.float16).to("cuda")
t0 = time.time()
for p in sorted(glob.glob(src + "/*.png")):
    im = Image.open(p).convert("RGB")
    n = pipe(im, num_inference_steps=4, ensemble_size=3, generator=torch.Generator("cuda").manual_seed(0)).prediction[0]
    n = np.asarray(n, np.float32)
    if n.shape[:2] != im.size[::-1]:
        import cv2
        n = cv2.resize(n, im.size, interpolation=cv2.INTER_LINEAR)
    np.savez_compressed(os.path.join(out, os.path.basename(p)[:-4] + ".npz"), normal=n)
print("done marigold", time.time() - t0, n.shape)
