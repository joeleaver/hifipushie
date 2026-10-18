"""Compute job: game-like EEVEE renders of an exported GLB (src/hifipushie/blender_game.py) -> out.tar.

The job folder holds asset.glb, asset.json (the export's report) and shots.json (blender_game shot list), and
optional env.json ({"GE_...": "1"} debug switches). Renders land in out/x_<shot>_<view>.png. Assembly gate renders
(expressions, bends) go here when NICO-TOP is up; the laptop keeps light checks."""
import json
import os
import subprocess
import sys
import tarfile
import time

job = os.path.abspath(sys.argv[1])
env = os.environ["HP_DIR"]
out = os.path.join(job, "out")
os.makedirs(out, exist_ok=True)
spec = {"glb": os.path.join(job, "asset.glb"), "json": os.path.join(job, "asset.json"),
        "out": os.path.join(out, "x"), "shots": json.load(open(os.path.join(job, "shots.json")))}
if os.path.exists(os.path.join(job, "anim.glb")):  # (Garrett assembly) a Mixamo-named clip source (e.g. Xbot.glb) for "anim" shots
    spec["anim"] = os.path.join(job, "anim.glb")
jf = os.path.join(job, "ge_job.json")
json.dump(spec, open(jf, "w"))
e = dict(os.environ)
if os.path.exists(os.path.join(job, "env.json")):
    e.update(json.load(open(os.path.join(job, "env.json"))))
t = time.time()
print("step: blender_game", flush=True)
r = subprocess.run([os.environ.get("OXIDEGEN_BLENDER", "blender"), "-b", "--factory-startup", "-t", "8", "--python",
                    os.path.join(env, "src/hifipushie/blender_game.py"), "--", jf], capture_output=True, text=True, env=e)
lines = [x for x in r.stdout.splitlines() if x.startswith(("@@", "wrote", "done")) or "Error" in x or "Traceback" in x]
open(os.path.join(job, "log.txt"), "w").write(f"exit {r.returncode} in {time.time() - t:.0f} s on {os.uname().nodename}\n"
                                              + "\n".join(lines)[-8000:] + "\n--- stderr\n" + r.stderr[-4000:])
with tarfile.open(os.path.join(job, "out.tar"), "w") as tf:
    tf.add(out, arcname="out")
print("step: done", flush=True)
