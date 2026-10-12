#!/bin/bash
# chinread agent, LIGHT jobs (solver chains, benchmark tables, pytest; no rendering of dressed heads): through the
# machine-wide light slots (/mnt/data/hifipushie/bin/slot: 4 slots shared by all agents, one BLAS / OMP thread, 6 GB cap).
# Heavy jobs (mkhead.py, eev.py, jsheet.py: anything that renders or syncs a stage) use run.sh (capped + resources.heavy).
W=/home/joe/dev/hifipushie/.claude/worktrees/agent-ae615b730ec496d10
cd $W
export HIFIPUSHIE_HOME=/home/joe/dev/hifipushie/workspace HIFIPUSHIE_ASSETS=/home/joe/dev/hifipushie/workspace/_templates PYTHONUNBUFFERED=1
export PYTHONPATH=$W/src:$W/spikes/chinread:$W/spikes/solvereads:$W/spikes/garrettgood:$W/spikes/reruns:$W/spikes/refread:/home/joe/dev/hifipushie/spikes/garrett3:$PYTHONPATH
exec /mnt/data/hifipushie/bin/slot uv run python "$@"
