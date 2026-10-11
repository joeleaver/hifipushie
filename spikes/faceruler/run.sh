#!/bin/bash
# run.sh <script> [args]: faceruler worktree code on the main workspace, memory-capped, one BLAS thread.
W=/home/joe/dev/hifipushie/.claude/worktrees/agent-a61aa2d0ada1d80ab
export HIFIPUSHIE_HOME=/home/joe/dev/hifipushie/workspace
export HIFIPUSHIE_ASSETS=/home/joe/dev/hifipushie/workspace/_templates
export PYTHONUNBUFFERED=1 OPENBLAS_NUM_THREADS=${NT:-1} OMP_NUM_THREADS=${NT:-1}
export G=/mnt/data/hifipushie/faceruler R=/home/joe/dev/hifipushie/workspace/human_renders
export PYTHONPATH=/mnt/data/hifipushie/faceruler/scripts:$W/spikes/eyeruler:$W/spikes/gnmbrow:$W/spikes/facesliders:${SRC:-$W/src}
cd $W
s=$1; shift
case "$s" in /*) ;; *) s=/mnt/data/hifipushie/faceruler/scripts/$s ;; esac
exec nice -n 10 /mnt/data/hifipushie/bin/capped uv run python "$s" "$@"
