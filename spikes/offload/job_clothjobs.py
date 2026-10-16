"""Compute job: cloth.render jobs packed on the laptop (each subfolder r_<name>/ = cloth.render's job.json + its data
npz + the maps it names, paths made local by the packer; e.g. spikes/offload/rvpack_cloth.py), rendered
with this machine's Blender (blender_cloth.py at this commit) -> renders.tar (r_<name>/<view>.png) + log.txt."""
import glob, json, os, subprocess, sys, tarfile, time


def check(job):
    """The pack this runner reads, checked on the laptop before a submit (remote.sh runs `<runner> --check <dir>`):
    dt-b01 went to job_clothrender.py (sheets.pkl) with job_clothjobs folders and failed on NICO-TOP after the queue.
    -> list of problems (empty = ok)."""
    import numpy as np
    dirs = sorted(glob.glob(os.path.join(job, "r_*")))
    if not dirs:
        return [f"{job}: no r_<name>/ folders (job_clothjobs packs; a sheets.pkl job is job_clothrender.py's)"]
    bad = []
    for d in dirs:
        jp = os.path.join(d, "job.json")
        if not os.path.exists(jp):
            bad.append(f"{d}: no job.json"); continue
        j = json.load(open(jp))
        if j.get("mode") != "render":
            bad.append(f"{d}: mode {j.get('mode')!r}, not 'render'")
        dp = os.path.join(d, j.get("data", ""))
        if not os.path.isfile(dp):
            bad.append(f"{d}: data {j.get('data')!r} missing"); continue
        keys = set(np.load(dp).files)
        for o in j.get("objects", []):
            for s in ("_V", "_F"):
                if o["name"] + s not in keys:
                    bad.append(f"{d}: {o['name']}{s} not in {j['data']}")
            for k, v in (o.get("maps") or {}).items():
                if isinstance(v, str) and (os.path.isabs(v) or not os.path.isfile(os.path.join(d, v))):
                    bad.append(f"{d}: map {o['name']}.{k} = {v!r} is not a file in the folder")
        if not j.get("views"):
            bad.append(f"{d}: no views")
    return bad


if sys.argv[1] == "--check":
    b = check(os.path.abspath(sys.argv[2]))
    print("\n".join(b) or "ok")
    sys.exit(1 if b else 0)
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
