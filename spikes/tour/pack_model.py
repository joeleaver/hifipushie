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
rj = json.load(open(os.path.join(src, "human_refs.json")))
for v in rj["views"]:
    f = os.path.basename(v["image"])
    shutil.copy(v["image"], os.path.join(job, "ws", "_refs", f))
    v["image"] = "@refs/" + f
json.dump(rj, open(os.path.join(dst, "human_refs.json"), "w"))
open(os.path.join(job, "model.txt"), "w").write(m)
print(job, sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(job) for f in fs) // 1024, "KB")
