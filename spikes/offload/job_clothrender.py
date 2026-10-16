"""Compute job: cloth gate sheets rendered from a dumped scene list -> sheets.tar.

The job folder holds sheets.pkl: [{"out": "<name>.png", "objs": [cloth.render objects; a "maps" value is a file name
in this folder], "views", "resolution", "box", "aspect", "textured"}] (written by a sheet() that dumps instead of
rendering, e.g. dress_garrett's run.py with RJOB=<dir>). Each sheet's views go through cloth.render and are pasted
side by side, as the local sheet() does. Joe 2026-10-15: all renders go to NICO-TOP; the laptop only for tiny crops."""
import os
import pickle
import sys
import tarfile

from PIL import Image

job = os.path.abspath(sys.argv[1])
# (as job_hairshots: the machine's Blender, and a runtime dir of the job's own for resources' lock files)
os.environ["HIFIPUSHIE_BLENDER"] = os.environ.get("OXIDEGEN_BLENDER", os.environ.get("HIFIPUSHIE_BLENDER", "blender"))
os.makedirs(os.path.join(job, "run"), exist_ok=True)
os.environ["XDG_RUNTIME_DIR"] = os.path.join(job, "run")
from hifipushie import cloth  # noqa: E402
S = pickle.load(open(os.path.join(job, "sheets.pkl"), "rb"))
out = os.path.join(job, "sheets")
os.makedirs(out, exist_ok=True)
for i, s in enumerate(S):
    print(f"step: sheet {i + 1}/{len(S)} {s['out']}", flush=True)
    for o in s["objs"]:
        if o.get("maps"):
            o["maps"] = {k: os.path.join(job, v) for k, v in o["maps"].items()}
    paths = cloth.render(s["objs"], os.path.join(job, "tmp", s["out"][:-4] + "_r"), views=list(s["views"]),
                         resolution=s["resolution"], box=s["box"], aspect=s["aspect"], textured=s["textured"])
    ims = [Image.open(p).convert("RGB") for p in paths]
    sh = Image.new("RGB", (sum(im.width for im in ims), ims[0].height), (60, 60, 60))
    x = 0
    for im in ims:
        sh.paste(im, (x, 0))
        x += im.width
    sh.save(os.path.join(out, s["out"]))
with tarfile.open(os.path.join(job, "sheets.tar"), "w") as t:
    t.add(out, arcname="sheets")
print("step: done", len(S), flush=True)
