#!/bin/bash
# run.sh <script> [args]: the tesshair3 worktree's code on the main workspace, memory-capped, one BLAS thread.
# Scripts are looked up in spikes/tesshair3, then tesshair2, then tesshair.
W=/home/joe/dev/hifipushie/.claude/worktrees/agent-a9ff53d876e89ff26
export HIFIPUSHIE_HOME=/home/joe/dev/hifipushie/workspace
export HIFIPUSHIE_ASSETS=/home/joe/dev/hifipushie/workspace/_templates
export PYTHONUNBUFFERED=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
export TH=/mnt/data/hifipushie/tesshair3 T=/mnt/data/hifipushie/tess TOUT=${TOUT:-/mnt/data/hifipushie/tesshair3/out}
export PYTHONPATH=$W/src:$W/spikes/tesshair3:$W/spikes/tesshair2:$W/spikes/tesshair:$W/spikes/garrett3:$W/spikes/tess
cd $W
s=$1; shift
case "$s" in /*) ;; *) for d in tesshair3 tesshair2 tesshair; do if [ -f $W/spikes/$d/$s ]; then s=$W/spikes/$d/$s; break; fi; done ;; esac
exec nice -n 15 /mnt/data/hifipushie/bin/capped uv run python "$s" "$@"
