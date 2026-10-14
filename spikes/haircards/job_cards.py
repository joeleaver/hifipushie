"""Compute job (spikes/offload/remote.sh): hair-cards renders on the offload machine. The job folder holds ws/ (models
packed by spikes/tour/pack_model.py; several: ws/<model>/), any exported hair GLB folders, and renders.json =
[[shots.py args...], ...] ("{job}" in an arg = this folder). Every render runs spikes/haircards/shots.py with
HIFIPUSHIE_HOME = ws; tiles -> out.tar, log.txt."""
import json
import os
import subprocess
import sys
import tarfile
import time

job = os.path.abspath(sys.argv[1])
env = os.environ["HP_DIR"]
ws = os.path.join(job, "ws")
for m in os.listdir(ws):  # (pack_model writes the pictures' paths relative: back to absolute here)
    p = os.path.join(ws, m, "human_refs.json")
    if os.path.exists(p):
        rj = json.load(open(p))
        for v in rj["views"]:
            v["image"] = v["image"].replace("@refs/", os.path.join(ws, "_refs") + "/")
        json.dump(rj, open(p, "w"))
out = os.path.join(job, "out")
os.makedirs(out, exist_ok=True)
sp = os.path.join(env, "spikes")
e = {**os.environ, "HIFIPUSHIE_HOME": ws, "HIFIPUSHIE_ASSETS": os.path.join(env, "_assets"), "TOUT": out,
     "HIFIPUSHIE_BLENDER": os.environ.get("OXIDEGEN_BLENDER", "blender"), "XDG_RUNTIME_DIR": os.path.join(job, "run"),
     "PYTHONPATH": ":".join([os.path.join(env, "src")] + [os.path.join(sp, d) for d in (
         "haircards", "tesshair7", "tesshair6", "tesshair5", "garrett3", "tess")])}
os.makedirs(e["XDG_RUNTIME_DIR"], exist_ok=True)
log = []
for args in json.load(open(os.path.join(job, "renders.json"))):
    args = [a.replace("{job}", job) for a in args]
    print("step: render", " ".join(args[:3]), flush=True)
    t = time.time()
    r = subprocess.run([os.path.join(env, ".venv/bin/python"), os.path.join(sp, "haircards", "shots.py"), *args],
                       capture_output=True, text=True, env=e, cwd=job)
    log.append(f"== {' '.join(args)}\nexit {r.returncode} in {time.time() - t:.0f} s on {os.uname().nodename}\n"
               + r.stdout[-4000:] + "\n--- stderr\n" + r.stderr[-4000:])
open(os.path.join(job, "log.txt"), "w").write("\n".join(log))
with tarfile.open(os.path.join(job, "out.tar"), "w") as tf:
    tf.add(out, arcname="out")
print("step: done", flush=True)
