#!/bin/bash
# run.sh <script> [args]: the tesshair worktree's code on the main workspace, memory-capped, one BLAS thread.
W=/home/joe/dev/hifipushie/.claude/worktrees/agent-a1e75b477d022cecb
export HIFIPUSHIE_HOME=/home/joe/dev/hifipushie/workspace
export HIFIPUSHIE_ASSETS=/home/joe/dev/hifipushie/workspace/_templates
export PYTHONUNBUFFERED=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
export TH=/mnt/data/hifipushie/tesshair T=/mnt/data/hifipushie/tess TOUT=/mnt/data/hifipushie/tesshair/out
export PYTHONPATH=$W/src:$W/spikes/tesshair:$W/spikes/garrett3:$W/spikes/tess
cd /home/joe/dev/hifipushie
s=$1; shift
case "$s" in /*) ;; *) s=$W/spikes/tesshair/$s ;; esac
exec nice -n 15 /mnt/data/hifipushie/bin/capped uv run python "$s" "$@"
