"""Compute job (spikes/offload/remote.sh): one dressing of the denselm set on another machine. The job folder holds
params.txt = gen.py's arguments on one line (seed=.. n=.. size=.. ...); the samples come back as out.tar."""
import os
import subprocess
import sys
import tarfile
import time

job = os.path.abspath(sys.argv[1])
env = os.environ["HP_DIR"]
args = open(os.path.join(job, "params.txt")).read().split()
ws, out, t = os.path.join(job, "ws"), os.path.join(job, "out"), time.time()
e = {**os.environ, "HIFIPUSHIE_HOME": ws, "HIFIPUSHIE_ASSETS": os.path.join(env, "_assets"),
     "HIFIPUSHIE_BLENDER": os.environ.get("OXIDEGEN_BLENDER", "blender"), "XDG_RUNTIME_DIR": os.path.join(job, "run"),
     "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "PYTHONUNBUFFERED": "1",
     "PYTHONPATH": os.pathsep.join([os.path.join(env, "src"), os.path.join(env, "spikes/denselm"), os.path.join(env, "spikes/garrett3")])}
os.makedirs(e["XDG_RUNTIME_DIR"], exist_ok=True)
os.makedirs(ws, exist_ok=True)
print("step: denselm gen", " ".join(args), flush=True)
p = subprocess.Popen([os.path.join(env, ".venv/bin/python"), os.path.join(env, "spikes/denselm/gen.py"), out] + args,
                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=e, cwd=job)
log = []
for line in p.stdout:
    log.append(line)
    if line.startswith("step:"):
        print(line.rstrip(), flush=True)
code = p.wait()
open(os.path.join(job, "log.txt"), "w").write(f"exit {code} in {time.time() - t:.0f} s on {os.uname().nodename}\n" + "".join(log)[-12000:])
with tarfile.open(os.path.join(job, "out.tar"), "w") as tf:
    if os.path.isdir(out):
        tf.add(out, arcname="out")
print("step: done", code, flush=True)
