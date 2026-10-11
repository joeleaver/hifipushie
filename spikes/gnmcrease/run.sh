#!/bin/bash
# run.sh <script> [args]: gnmcrease worktree code on the main workspace, memory-capped, one BLAS thread.
W=/home/joe/dev/hifipushie/.claude/worktrees/agent-a6be463cdefca130b
export HIFIPUSHIE_HOME=/home/joe/dev/hifipushie/workspace
export HIFIPUSHIE_ASSETS=/home/joe/dev/hifipushie/workspace/_templates
export PYTHONUNBUFFERED=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
export G=/mnt/data/hifipushie/gnmcrease R=/home/joe/dev/hifipushie/workspace/human_renders F=/mnt/data/hifipushie/faces5
export PYTHONPATH=/mnt/data/hifipushie/gnmcrease:$W/spikes/facesliders:$W/spikes/garrett3:${SRC:-$W/src}
cd $W
s=$1; shift
case "$s" in /*) ;; *) s=/mnt/data/hifipushie/gnmcrease/$s ;; esac
exec nice -n 19 /mnt/data/hifipushie/bin/capped uv run python "$s" "$@"
