"""Bake the strand atlas from Blender strands, compare it with the numpy one, and render a model's cards with it."""
import json
import os
import subprocess
import sys

import numpy as np
from PIL import Image
from hifipushie import hair, hair_cards as hc, render, store

HR, SP = os.environ["HR"], os.environ["SP"]
out = os.path.join(HR, "hc_14_atlas_baked_raw.png")
job = os.path.join(SP, "atlas_job.json")
json.dump({"tiles": hc.TILES, "out": out}, open(job, "w"))
r = subprocess.run([render.BLENDER, "-b", "--factory-startup", "--python", os.path.join(SP, "bl_atlas.py"), "--", job],
                   capture_output=True, text=True)
print("\n".join(x for x in r.stdout.splitlines() if x.startswith("@@")), r.stderr[-800:] if r.returncode else "")
baked = np.asarray(Image.open(out).convert("RGBA").resize((1024, 1024), Image.LANCZOS), np.float32) / 255
ours = hc.atlas(dict(hc.STRANDS), hair.LOOK)
bg = np.array([0.55, 0.6, 0.7])
comp = lambda c: c[..., :3] * c[..., 3:] + bg * (1 - c[..., 3:])
Image.fromarray((np.concatenate([comp(ours["color"]), comp(baked)], 1) * 255).astype(np.uint8)).save(
    os.path.join(HR, "hc_14_atlas_numpy_vs_baked.png"))
print("coverage baked", round(float(baked[..., 3].mean()), 2), "numpy", round(float(ours["color"][..., 3].mean()), 2))
orig = hc.atlas


def patched(S, look):
    at = dict(orig(S, look))
    col = baked.copy()
    band = [t for t in at["tiles"] if t["kind"] == "band"][0]
    x0 = int(band["u0"] * 1024) - 2
    col[:, x0:] = at["color"][:, x0:]
    at["color"] = col
    at["aux"] = at["aux"].copy()
    at["aux"][..., 3] = col[..., 3]
    return at


hc.atlas = patched
for name in sys.argv[1:]:
    spec = store.load(name)
    spec["hair"]["style"] = "cards"
    views = ("front", "side", "back", "close_front")
    hair.look(name, views=views, size=640, save=os.path.join(HR, f"hc_15_{name}_cards_baked.png"), spec=spec, clay=False)
    print(name, "cards with the baked atlas rendered")
