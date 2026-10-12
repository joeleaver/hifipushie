"""Compute job: the skin feature tour of a packed model (spikes/tour/pack_model.py), tiles -> tiles.tar."""
import json, os, subprocess, sys, tarfile, time
job = os.path.abspath(sys.argv[1]); env = os.environ["HP_DIR"]
m = open(os.path.join(job, "model.txt")).read().strip()
ws = os.path.join(job, "ws")
p = os.path.join(ws, m, "human_refs.json"); rj = json.load(open(p))
for v in rj["views"]:
    v["image"] = v["image"].replace("@refs/", os.path.join(ws, "_refs") + "/")
json.dump(rj, open(p, "w"))
feats = open(os.path.join(job, "features.txt")).read().strip() if os.path.exists(os.path.join(job, "features.txt")) else "eyes,mouth"
out = os.path.join(job, "tiles"); t = time.time()
print("step: skin tour", m, feats, flush=True)
e = {**os.environ, "HIFIPUSHIE_HOME": ws, "HIFIPUSHIE_ASSETS": os.path.join(env, "_assets"),
     "HIFIPUSHIE_BLENDER": os.environ.get("OXIDEGEN_BLENDER", "blender"), "XDG_RUNTIME_DIR": os.path.join(job, "run")}
os.makedirs(e["XDG_RUNTIME_DIR"], exist_ok=True)
r = subprocess.run([os.path.join(env, ".venv/bin/python"), os.path.join(env, "spikes/tour/skintour.py"), m, out, "features=" + feats,
                    "proj=" + os.environ.get("PROJ", "0")], capture_output=True, text=True, env=e, cwd=job)
open(os.path.join(job, "log.txt"), "w").write(f"exit {r.returncode} in {time.time() - t:.0f} s on {os.uname().nodename}\n" + r.stdout[-6000:] + "\n--- stderr\n" + r.stderr[-6000:])
with tarfile.open(os.path.join(job, "tiles.tar"), "w") as tf:
    if os.path.isdir(out):
        tf.add(out, arcname="tiles")
print("step: done", r.returncode, flush=True)
