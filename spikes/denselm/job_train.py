"""Compute job (spikes/offload/remote.sh ... gpu): train the denselm network on another machine's GPU. The job folder
holds data.tar (dressing folders + landmarks.json, made by pack_data.sh) and params.txt = train.py's arguments on one
line; several runs: one line each (learning-curve points share the unpacked data and the torch environment).
The torch environment is the bundle's ({dir}/_torch: built once per machine by remote_train.sh's setup); the model comes back as out.tar (model.pt, weights.pth, log.json, val.json, val.npz per run)."""
import os
import subprocess
import sys
import tarfile
import time

job = os.path.abspath(sys.argv[1])
env = os.environ["HP_DIR"]
t = time.time()
log = open(os.path.join(job, "log.txt"), "w")


def sh(cmd, **kw):
    print("step:", " ".join(cmd)[:160], flush=True)
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=job, **kw)
    for line in p.stdout:
        log.write(line)
        log.flush()
        if line.startswith("step:"):
            print(line.rstrip()[:300], flush=True)
    return p.wait()


with tarfile.open(os.path.join(job, "data.tar")) as tf:
    tf.extractall(os.path.join(job, "data"))
os.remove(os.path.join(job, "data.tar"))
py = os.path.join(env, "_torch", "bin", "python")      # the torch venv in the machine's cache (remote_train.sh's setup)
code = sh([py, "-c", "import torch, sys; ok = torch.cuda.is_available(); print('step: torch', torch.__version__, 'cuda', ok, "
                     "torch.cuda.get_device_name(0) if ok else '-', flush=True); sys.exit(0 if ok or '" + os.environ.get("DL_ALLOW_CPU", "0") + "' == '1' else 3)"])
if code:
    subprocess.run(["sh", "-c", "nvidia-smi; ls -la /dev/dxg /usr/lib/wsl/lib 2>&1 | head -20; " + py + " -c 'import torch; print(torch.version.cuda); torch.cuda.init()'"],
                   stdout=log, stderr=subprocess.STDOUT, cwd=job)
runs = [ln.split() for ln in open(os.path.join(job, "params.txt")).read().splitlines() if ln.strip()]
for k, args in enumerate(runs):
    if code:
        break
    name = next((a.split("=", 1)[1] for a in args if a.startswith("name=")), f"run{k}")
    args = [a for a in args if not a.startswith("name=")]
    code = sh([py, os.path.join(env, "spikes/denselm/train.py"), os.path.join(job, "out", name), os.path.join(job, "data")] + args,
              env={**os.environ, "PYTHONUNBUFFERED": "1"})
    for f in ("pack_img.npy",):
        p = os.path.join(job, "out", name, f)
        if os.path.exists(p):
            os.remove(p)
log.write(f"exit {code} in {time.time() - t:.0f} s on {os.uname().nodename}\n")
log.close()
with tarfile.open(os.path.join(job, "out.tar"), "w") as tf:
    if os.path.isdir(os.path.join(job, "out")):
        tf.add(os.path.join(job, "out"), arcname="out")
print("step: done", code, flush=True)
