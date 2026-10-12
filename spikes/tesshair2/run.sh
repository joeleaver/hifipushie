#!/bin/bash
# run.sh <script> [args]: the tesshair2 worktree's code on the main workspace, memory-capped, one BLAS thread.
# Scripts are looked up in spikes/tesshair2 first, then spikes/tesshair.
W=/home/joe/dev/hifipushie/.claude/worktrees/agent-a1369a88d9730a4d3
export HIFIPUSHIE_HOME=/home/joe/dev/hifipushie/workspace
export HIFIPUSHIE_ASSETS=/home/joe/dev/hifipushie/workspace/_templates
export PYTHONUNBUFFERED=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
export TH=/mnt/data/hifipushie/tesshair2 T=/mnt/data/hifipushie/tess TOUT=${TOUT:-/mnt/data/hifipushie/tesshair2/out}
export PYTHONPATH=$W/src:$W/spikes/tesshair2:$W/spikes/tesshair:$W/spikes/garrett3:$W/spikes/tess
cd $W
s=$1; shift
case "$s" in /*) ;; *) if [ -f $W/spikes/tesshair2/$s ]; then s=$W/spikes/tesshair2/$s; else s=$W/spikes/tesshair/$s; fi ;; esac
exec nice -n 15 /mnt/data/hifipushie/bin/capped uv run python "$s" "$@"
