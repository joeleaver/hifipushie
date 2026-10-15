"""pack_model.py <model> <job dir>: a model as a compute-job folder (oxidegen `where: local`): <job>/ws/<model>/
{spec.json, human_refs.json} with the reference pictures copied to <job>/ws/_refs/ and their paths written RELATIVE
("@refs/<file>"), which the runner turns back into absolute paths on the machine. Model folders are small (the big
things are stage caches, rebuilt there); pictures are a few MB each."""
import json, os, shutil, sys
m, job = sys.argv[1], sys.argv[2]
src = os.path.join(os.environ.get("HIFIPUSHIE_HOME", "/home/joe/dev/hifipushie/workspace"), m)
dst = os.path.join(job, "ws", m)
os.makedirs(dst, exist_ok=True); os.makedirs(os.path.join(job, "ws", "_refs"), exist_ok=True)
shutil.copy(os.path.join(src, "spec.json"), dst)
# (stored images (paint "image" layers, workspace/_images/<id>.png) and painted masks (_painted/<id>.npz) the spec names:
# a stage's paint compiles them, a job without them fails "image ... is missing from the store")
import re
ws0 = os.path.dirname(src)
for h in set(re.findall(r"[0-9a-f]{16}", open(os.path.join(src, "spec.json")).read())):
    for sub, ext in (("_images", ".png"), ("_painted", ".npz")):
        f = os.path.join(ws0, sub, h + ext)
        if os.path.exists(f):
            os.makedirs(os.path.join(job, "ws", sub), exist_ok=True)
            shutil.copy(f, os.path.join(job, "ws", sub))
rj = json.load(open(os.path.join(src, "human_refs.json")))
for v in rj["views"]:
    f = os.path.basename(v["image"])
    shutil.copy(v["image"], os.path.join(job, "ws", "_refs", f))
    v["image"] = "@refs/" + f
json.dump(rj, open(os.path.join(dst, "human_refs.json"), "w"))
open(os.path.join(job, "model.txt"), "w").write(m)
print(job, sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(job) for f in fs) // 1024, "KB")
