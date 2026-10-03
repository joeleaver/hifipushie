#!/usr/bin/env bash
# A cloth job on a GPU box over SSH: run with the job folder as its last argument, as
#   HIFIPUSHIE_ZOZO_REMOTE="spikes/gpu_cloth/remote.sh"       (garment backend "zozo": GPU_RUNNER=zozo, the default)
#   HIFIPUSHIE_CLOTH_REMOTE="spikes/gpu_cloth/remote.sh"      (backend "remote" with GPU_RUNNER=newton)
# It copies the folder and the runner to the box, runs it there (output streamed: the "cloth:" lines are progress) and
# copies out.npz back. The box is named by the environment only (never written to the repo or logs):
#   GPU_SSH_HOST (user@host), GPU_SSH_PORT (default 22), GPU_SSH_KEY (optional identity file),
#   GPU_WORKDIR (default /root/gpucloth), GPU_RUNNER (zozo | newton; default zozo),
#   zozo: GPU_PPF_ROOT (the unpacked ZOZO release on the box; default $GPU_WORKDIR/ppf), GPU_ZOZO_DEVICE (cuda);
#   newton: GPU_PYTHON (a python with warp + newton; default python3), GPU_RUN_ARGS.
set -euo pipefail
job="${@: -1}"
here="$(cd "$(dirname "$0")" && pwd)"
name="$(basename "$(dirname "$job")")_$(basename "$job")"
port="${GPU_SSH_PORT:-22}"
wd="${GPU_WORKDIR:-/root/gpucloth}"
runner="${GPU_RUNNER:-zozo}"
ssh_opts=(-p "$port" -o StrictHostKeyChecking=accept-new -o BatchMode=yes -o ServerAliveInterval=30)
[ -n "${GPU_SSH_KEY:-}" ] && ssh_opts+=(-i "$GPU_SSH_KEY")
rsh="ssh ${ssh_opts[*]}"
rsync -az -e "$rsh" --exclude out.npz "$job/" "$GPU_SSH_HOST:$wd/jobs/$name/"
case "$runner" in
  zozo)
    rsync -az -e "$rsh" "$here/../../src/hifipushie/cloth_zozo.py" "$GPU_SSH_HOST:$wd/cloth_zozo.py"
    ppf="${GPU_PPF_ROOT:-$wd/ppf}"
    dev="${GPU_ZOZO_DEVICE:-cuda}"
    ssh "${ssh_opts[@]}" "$GPU_SSH_HOST" "cd $wd && CARGO_TARGET_DIR=$ppf/target/$dev PYTHONPATH=$ppf PYTHONNOUSERSITE=1 \
      PYTHONDONTWRITEBYTECODE=1 $ppf/python/bin/python3.12 cloth_zozo.py jobs/$name ${GPU_RUN_ARGS:-}" ;;
  newton)
    rsync -az -e "$rsh" "$here/run_newton.py" "$GPU_SSH_HOST:$wd/run_newton.py"
    ssh "${ssh_opts[@]}" "$GPU_SSH_HOST" "cd $wd && ${GPU_PYTHON:-python3} run_newton.py jobs/$name ${GPU_RUN_ARGS:-}" ;;
  *) echo "GPU_RUNNER is zozo or newton, got $runner" >&2; exit 2 ;;
esac
rsync -az -e "$rsh" "$GPU_SSH_HOST:$wd/jobs/$name/out.npz" "$job/out.npz"
