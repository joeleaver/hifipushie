"""Compute job: renders of a packed model (spikes/tour/pack_model.py; ref / own models packed alongside), tiles -> tiles.tar.
Default: the skin feature tour (spikes/tour/skintour.py; features.txt). With cu.txt in the job: one spikes/projskin/cu.py
run per line (the line = cu.py's arguments after <model> <out>, e.g. `ref=tp_h3 own=tp_h3_lef2 only=face views=0,1,2
size=768 hair=0`): the gate render set's close-ups, all into tiles/. A line "@<repo script> args" runs that script
instead (<model> <out> args), e.g. "@spikes/projskin/nape.py size=512"."""
import os, shlex, subprocess, sys, tarfile, time
job = os.path.abspath(sys.argv[1]); env = os.environ["HP_DIR"]
sys.path.insert(0, os.path.join(env, "spikes/tour"))
import pack_model
m = open(os.path.join(job, "model.txt")).read().strip()
ws = pack_model.unpack(job)
out = os.path.join(job, "tiles"); t = time.time()
e = {**os.environ, "HIFIPUSHIE_HOME": ws, "HIFIPUSHIE_ASSETS": os.path.join(env, "_assets"),
     "HIFIPUSHIE_BLENDER": os.environ.get("OXIDEGEN_BLENDER", "blender"), "XDG_RUNTIME_DIR": os.path.join(job, "run")}
os.makedirs(e["XDG_RUNTIME_DIR"], exist_ok=True); os.makedirs(out, exist_ok=True)
py = os.path.join(env, ".venv/bin/python")
cu = os.path.join(job, "cu.txt")
if os.path.exists(cu):
    runs = [[py, os.path.join(env, l.split()[0][1:]), m, out] + shlex.split(l)[1:] if l.startswith("@") else
            [py, os.path.join(env, "spikes/projskin/cu.py"), m, out] + shlex.split(l)
            for l in open(cu).read().splitlines() if l.strip()]
else:
    feats = open(os.path.join(job, "features.txt")).read().strip() if os.path.exists(os.path.join(job, "features.txt")) else "eyes,mouth"
    runs = [[py, os.path.join(env, "spikes/tour/skintour.py"), m, out, "features=" + feats, "proj=" + os.environ.get("PROJ", "0")]]
log, rc = [], 0
for i, cmd in enumerate(runs):
    print(f"step: run {i + 1}/{len(runs)} {m} {' '.join(cmd[4:])[:80]}", flush=True)
    t1 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, env=e, cwd=job)
    rc = rc or r.returncode
    log.append(f"=== {' '.join(cmd[2:])}\nexit {r.returncode} in {time.time() - t1:.0f} s\n" + r.stdout[-4000:] + "\n--- stderr\n" + r.stderr[-4000:])
open(os.path.join(job, "log.txt"), "w").write(f"exit {rc} in {time.time() - t:.0f} s on {os.uname().nodename}\n" + "\n".join(log))
with tarfile.open(os.path.join(job, "tiles.tar"), "w") as tf:
    tf.add(out, arcname="tiles")
print("step: done", rc, flush=True)
