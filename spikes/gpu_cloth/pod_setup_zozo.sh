#!/usr/bin/env bash
# Set a CUDA box up for the "zozo" cloth backend (run there once): ZOZO's self-contained Linux release (its own Python
# and CUDA runtime: only the NVIDIA driver is needed) unpacked into $GPU_WORKDIR/ppf, checked by sha256 (the same
# release as src/hifipushie/assets.json's "zozo" pack). Then, from the laptop:
#   HIFIPUSHIE_ZOZO_REMOTE="spikes/gpu_cloth/remote.sh" GPU_SSH_HOST=... GPU_SSH_PORT=... dress / run.py
# runs each job there (remote.sh copies the job folder and src/hifipushie/cloth_zozo.py, streams progress, copies
# out.npz back).
set -euo pipefail
wd="${GPU_WORKDIR:-/root/gpucloth}"
tag=2026-10-01-19-29
name=ppf-contact-solver-$tag-linux-x86_64
sha=3ed5e9978a94bc29f69eedc0eb4ba24dfc950ce7f4215655e9e6cbe5e5696408
mkdir -p "$wd/jobs"
cd "$wd"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv
if [ ! -x ppf/python/bin/python3.12 ]; then
  curl -fL --retry 3 -o "$name.tar.gz" "https://github.com/st-tech/ppf-contact-solver/releases/download/$tag/$name.tar.gz"
  echo "$sha  $name.tar.gz" | sha256sum -c -
  tar xzf "$name.tar.gz"
  rm -rf ppf && mv "$name" ppf && rm "$name.tar.gz"
fi
CARGO_TARGET_DIR="$wd/ppf/target/cuda" PYTHONPATH="$wd/ppf" PYTHONNOUSERSITE=1 ppf/python/bin/python3.12 -c \
  "import frontend; print('zozo frontend ok')"
df -h "$wd" | tail -1
echo SETUP_DONE
