#!/bin/bash
# run.sh <script> [args]: the tesshair4 worktree's code on the main workspace, memory-capped, one BLAS thread.
# Scripts are looked up in spikes/tesshair4, tesshair3, tesshair2, tesshair.
W=/home/joe/dev/hifipushie/.claude/worktrees/tesshair7
export HIFIPUSHIE_HOME=/home/joe/dev/hifipushie/workspace
export HIFIPUSHIE_ASSETS=/home/joe/dev/hifipushie/workspace/_templates
export HIFIPUSHIE_BLENDER=/mnt/data/hifipushie/tesshair7/blender6 PYTHONUNBUFFERED=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
export TH=/mnt/data/hifipushie/tesshair7 T=/mnt/data/hifipushie/tess TOUT=${TOUT:-/mnt/data/hifipushie/tesshair7/out}
export PYTHONPATH=$W/src:$W/spikes/tesshair7:$W/spikes/tesshair6:$W/spikes/tesshair5:$W/spikes/tesshair4:$W/spikes/tesshair3:$W/spikes/tesshair2:$W/spikes/tesshair:$W/spikes/garrett3:$W/spikes/tess
cd $W
s=$1; shift
case "$s" in /*) ;; *) for d in tesshair7 tesshair6 tesshair5 tesshair4 tesshair3 tesshair2 tesshair; do if [ -f $W/spikes/$d/$s ]; then s=$W/spikes/$d/$s; break; fi; done ;; esac
exec nice -n 15 /mnt/data/hifipushie/bin/capped uv run python "$s" "$@"
