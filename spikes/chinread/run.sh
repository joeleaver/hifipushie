#!/bin/bash
# chinread agent: every python through the memory cap, this worktree's src on the path, main's workspace
W=/home/joe/dev/hifipushie/.claude/worktrees/agent-ae615b730ec496d10
cd $W
export HIFIPUSHIE_HOME=/home/joe/dev/hifipushie/workspace HIFIPUSHIE_ASSETS=/home/joe/dev/hifipushie/workspace/_templates PYTHONUNBUFFERED=1
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
export PYTHONPATH=$W/src:$W/spikes/chinread:$W/spikes/solvereads:$W/spikes/garrettgood:$W/spikes/reruns:$W/spikes/refread:/home/joe/dev/hifipushie/spikes/garrett3:$PYTHONPATH
exec nice -n 10 /mnt/data/hifipushie/bin/capped uv run python "$@"
