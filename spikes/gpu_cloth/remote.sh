#!/usr/bin/env bash
# The "remote" cloth backend over SSH: HIFIPUSHIE_CLOTH_REMOTE="spikes/gpu_cloth/remote.sh" runs this with the job
# folder as its last argument. It copies the folder to the GPU box, runs run_newton.py there, copies out.npz back.
# The box is named by the environment only (never written to the repo or logs):
#   GPU_SSH_HOST (user@host), GPU_SSH_PORT (default 22), GPU_SSH_KEY (optional identity file),
#   GPU_WORKDIR (default /root/gpucloth: holds run_newton.py and a python with newton, GPU_PYTHON default python3)
set -euo pipefail
job="${@: -1}"
name="$(basename "$(dirname "$job")")_$(basename "$job")"
port="${GPU_SSH_PORT:-22}"
wd="${GPU_WORKDIR:-/root/gpucloth}"
py="${GPU_PYTHON:-python3}"
ssh_opts=(-p "$port" -o StrictHostKeyChecking=accept-new -o BatchMode=yes)
[ -n "${GPU_SSH_KEY:-}" ] && ssh_opts+=(-i "$GPU_SSH_KEY")
rsh="ssh ${ssh_opts[*]}"
rsync -az -e "$rsh" --exclude out.npz "$job/" "$GPU_SSH_HOST:$wd/jobs/$name/"
ssh "${ssh_opts[@]}" "$GPU_SSH_HOST" "cd $wd && $py run_newton.py jobs/$name ${GPU_RUN_ARGS:-}"
rsync -az -e "$rsh" "$GPU_SSH_HOST:$wd/jobs/$name/out.npz" "$job/out.npz"
