#!/bin/bash
# run.sh <script in this folder> [args] : a scratch script with the hair agent's environment, from its worktree
export HIFIPUSHIE_ASSETS=/home/joe/dev/hifipushie/workspace/_templates
export HIFIPUSHIE_HOME=/home/joe/dev/hifipushie/workspace
export HR=/home/joe/dev/hifipushie/workspace/hair_renders
export SP=/tmp/claude-1000/-home-joe-dev-hifipushie/1d5c679b-4c56-495b-8635-72e86a3b3567/scratchpad/haircards
cd /home/joe/dev/hifipushie/.claude/worktrees/agent-aff168a4b06a3ed59
s="$1"
shift
if [ "$s" = "-" ]; then exec uv run python "$@"; fi
exec uv run python "$SP/$s" "$@"
