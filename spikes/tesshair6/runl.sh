#!/bin/bash
# runl.sh <script> [args]: a LIGHT job (a measure, a plot, no render / sync) on this worktree's code through the
# machine-wide light slots (/mnt/data/hifipushie/bin/slot: 4 slots, one thread, 6 GB). Heavy jobs: run.sh.
W=/home/joe/dev/hifipushie/.claude/worktrees/agent-ac19f4a9531cf46f3
export HIFIPUSHIE_HOME=/home/joe/dev/hifipushie/workspace
export HIFIPUSHIE_ASSETS=/home/joe/dev/hifipushie/workspace/_templates
export PYTHONUNBUFFERED=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
export TH=/mnt/data/hifipushie/tesshair6 T=/mnt/data/hifipushie/tess TOUT=${TOUT:-/mnt/data/hifipushie/tesshair6/out}
export PYTHONPATH=$W/src:$W/spikes/tesshair6:$W/spikes/tesshair5:$W/spikes/tesshair4:$W/spikes/tesshair3:$W/spikes/tesshair2:$W/spikes/tesshair:$W/spikes/garrett3:$W/spikes/tess
cd $W
s=$1; shift
case "$s" in /*) ;; *) for d in tesshair6 tesshair5 tesshair4 tesshair3 tesshair2 tesshair; do if [ -f $W/spikes/$d/$s ]; then s=$W/spikes/$d/$s; break; fi; done ;; esac
exec /mnt/data/hifipushie/bin/slot uv run python "$s" "$@"
