#!/bin/bash
# refread agent: every python through the memory cap, this worktree's src on the path, main's workspace
W=/home/joe/dev/hifipushie/.claude/worktrees/agent-afe13b70ba89a707e
cd $W
export HIFIPUSHIE_HOME=/home/joe/dev/hifipushie/workspace HIFIPUSHIE_ASSETS=/home/joe/dev/hifipushie/workspace/_templates PYTHONUNBUFFERED=1
export PYTHONPATH=$W/src:$W/spikes/refread:$W/spikes/reruns:/home/joe/dev/hifipushie/spikes/garrett3:$PYTHONPATH
exec nice -n 10 /mnt/data/hifipushie/bin/capped uv run python "$@"
