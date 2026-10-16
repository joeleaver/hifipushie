"""Compute job: cloth.render jobs packed on the laptop (each subfolder r_<name>/ = cloth.render's job.json + its data
npz + the maps it names, paths made local by the packer; e.g. /mnt/data/hifipushie/dress_tess/fin/rvpack.py), rendered
with this machine's Blender (blender_cloth.py at this commit) -> renders.tar (r_<name>/<view>.png) + log.txt."""
import glob, json, os, subprocess, sys, tarfile, time
job = os.path.abspath(sys.argv[1]); env = os.environ["HP_DIR"]
bl = os.environ.get("OXIDEGEN_BLENDER", "blender")
script = os.path.join(env, "src/hifipushie/blender_cloth.py")
log, rc, t = [], 0, time.time()
dirs = sorted(glob.glob(os.path.join(job, "r_*")))
for i, d in enumerate(dirs):
    print(f"step: render {i + 1}/{len(dirs)} {os.path.basename(d)}", flush=True)
    jp = os.path.join(d, "job.json")
    j = json.load(open(jp))
    j["out_prefix"] = os.path.join(d, "out")
    for o in j["objects"]:
        for k, v in (o.get("maps") or {}).items():
            if isinstance(v, str):
                o["maps"][k] = os.path.join(d, v)
    json.dump(j, open(jp, "w"))
    t1 = time.time()
    r = subprocess.run([bl, "-b", "--factory-startup", "-t", "8", "--python", script, "--", jp], capture_output=True, text=True,
                       timeout=1200)
    rc = rc or r.returncode
    log.append(f"=== {d}\nexit {r.returncode} in {time.time() - t1:.0f} s\n" + (r.stdout + r.stderr)[-3000:])
open(os.path.join(job, "log.txt"), "w").write(f"exit {rc} in {time.time() - t:.0f} s on {os.uname().nodename}\n" + "\n".join(log))
with tarfile.open(os.path.join(job, "renders.tar"), "w") as tf:
    for d in dirs:
        for p in glob.glob(os.path.join(d, "out_*.png")):
            tf.add(p, arcname=os.path.relpath(p, job))
print("step: done", rc, flush=True)
