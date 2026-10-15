"""Compute job: hair shots of a packed groomed model on its head stage (spikes/hair_garrett/hgshots.py) -> tiles.tar.

The job folder holds ws/<model>/ and ws/<stage>/ (spikes/tour/pack_model.py for each; the reference pictures in
ws/_refs/), model.txt, stage.txt, and optional args.txt: one hgshots run per line, its extra arguments (e.g.
"views=v0,v1,v2,y125,y180 size=1024 ss=2" then "views=t60,y180,y125,v1 size=1024 ss=2 tag=_mag look={...}").
Full-count gate renders go here (the laptop's iGPU wedged on heavy strand frames, 2026-10-14); one job batches
every view (one Blender start per hgshots run: the shader compile is ~1 min)."""
import json
import os
import shlex
import subprocess
import sys
import tarfile
import time

job = os.path.abspath(sys.argv[1])
env = os.environ["HP_DIR"]
m = open(os.path.join(job, "model.txt")).read().strip()
st = open(os.path.join(job, "stage.txt")).read().strip()
ws = os.path.join(job, "ws")
for name in {m, st}:
    p = os.path.join(ws, name, "human_refs.json")
    rj = json.load(open(p))
    for v in rj["views"]:
        v["image"] = v["image"].replace("@refs/", os.path.join(ws, "_refs") + "/")
    json.dump(rj, open(p, "w"))
lines = ["views=v0,v1,v2,y125,y180 size=1024 ss=2"]
if os.path.exists(os.path.join(job, "args.txt")):
    lines = [ln for ln in open(os.path.join(job, "args.txt")).read().splitlines() if ln.strip()]
out = os.path.join(job, "tiles")
os.makedirs(out, exist_ok=True)
e = {**os.environ, "HIFIPUSHIE_HOME": ws, "HIFIPUSHIE_ASSETS": os.path.join(env, "_assets"),
     "HIFIPUSHIE_BLENDER": os.environ.get("OXIDEGEN_BLENDER", "blender"), "XDG_RUNTIME_DIR": os.path.join(job, "run"),
     "TOUT": out, "PYTHONPATH": os.environ.get("PYTHONPATH", "") + ":" + os.path.join(env, "spikes/hair_garrett")
     + ":" + os.path.join(env, "spikes/tesshair7")}
os.makedirs(e["XDG_RUNTIME_DIR"], exist_ok=True)
log = []
for i, ln in enumerate(lines):
    t = time.time()
    print(f"step: hgshots {i + 1}/{len(lines)}: {ln[:80]}", flush=True)
    r = subprocess.run([os.path.join(env, ".venv/bin/python"), os.path.join(env, "spikes/hair_garrett/hgshots.py"), m,
                        "stage=" + st] + shlex.split(ln), capture_output=True, text=True, env=e, cwd=job)
    log.append(f"[{ln}] exit {r.returncode} in {time.time() - t:.0f} s on {os.uname().nodename}\n"
               + "\n".join(x for x in r.stdout.splitlines() if not x.startswith("[measure]"))[-4000:]
               + "\n--- stderr\n" + r.stderr[-4000:])
open(os.path.join(job, "log.txt"), "w").write("\n\n".join(log))
with tarfile.open(os.path.join(job, "tiles.tar"), "w") as tf:
    tf.add(out, arcname="tiles")
print("step: done", flush=True)
