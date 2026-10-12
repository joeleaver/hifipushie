"""Trial compute job: run one pytest file of the hifipushie tree (the bundle's environment) and write its report."""
import os, subprocess, sys, time
job = sys.argv[1]
name = open(os.path.join(job, "test.txt")).read().strip()
env = os.environ["HP_DIR"]
t = time.time()
print("step: running", name, flush=True)
r = subprocess.run([os.path.join(env, ".venv/bin/python"), "-m", "pytest", "-q", "-p", "no:cacheprovider", os.path.join(env, "tests", name)],
                   capture_output=True, text=True, cwd=job,
                   env={**os.environ, "HIFIPUSHIE_ASSETS": os.path.join(env, "_assets"), "HIFIPUSHIE_HOME": os.path.join(os.getcwd(), "ws")})
open(os.path.join(job, "report.txt"), "w").write(f"exit {r.returncode} in {time.time() - t:.0f} s on {os.uname().nodename}\n" + r.stdout[-3000:] + r.stderr[-1500:])
print("step: done", r.returncode, flush=True)
