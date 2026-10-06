#!/bin/bash
# run.sh <script in spikes/hair_strands/hs3> [args]: the hair3 agent's environment, from its worktree
export HIFIPUSHIE_ASSETS=/home/joe/dev/hifipushie/workspace/_templates
export HIFIPUSHIE_HOME=/home/joe/dev/hifipushie/workspace
export HR=/home/joe/dev/hifipushie/workspace/hair_renders
cd "$(dirname "$0")/../../.."
s="$1"; shift
exec uv run python "spikes/hair_strands/hs3/$s" "$@"
