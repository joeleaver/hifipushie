"""pr.py <frames tag> [..]: the cached frames as pictures, like with like: per view PICTURE | OUR RENDER brought to the
picture's exposure (x the plain skin's gain, linear) -> $G/out/pr_<tag>.png."""
import os, pickle, sys
import numpy as np
from PIL import Image, ImageDraw
from hifipushie import skin_read as sr

G = os.environ["G"] + "/out"
for tag in sys.argv[1:]:
    frames = pickle.load(open(f"{G}/frames_{tag}.pkl", "rb"))
    c = sr.context(tag, frames=frames, log=lambda s: None)
    rows = []
    for f, v in zip(frames, c.views):
        g = np.asarray(v["gain"])
        P = sr._srgb(np.clip(f["P"], 0, 1))
        a = f["alpha"][..., None]
        R = sr._srgb(np.clip(f["R"] * g, 0, 1)) * a + 0.8 * (1 - a)
        rows.append(np.concatenate([P, R], 1))
    im = Image.fromarray(np.round(255 * np.concatenate(rows, 0)).astype(np.uint8))
    ImageDraw.Draw(im).text((6, 6), f"{tag}: PICTURE | OURS x gain", fill=(0, 0, 0))
    im.save(f"{G}/pr_{tag}.png")
    print(f"{G}/pr_{tag}.png")
