#!/bin/bash
# run.sh <script in scratchpad/hs> [args]: with the hair2 agent's environment, from its worktree
export HIFIPUSHIE_ASSETS=/home/joe/dev/hifipushie/workspace/_templates
export HIFIPUSHIE_HOME=/home/joe/dev/hifipushie/workspace
export HR=/home/joe/dev/hifipushie/workspace/hair_renders
cd /home/joe/dev/hifipushie/.claude/worktrees/agent-a991060c01c5311d2
s="$1"; shift
exec uv run python "scratchpad/hs/$s" "$@"
