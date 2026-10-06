#!/bin/bash
# run.sh <script in spikes/hair_strands/hs4> [args]: the hair4 agent's environment, from its worktree
export HIFIPUSHIE_ASSETS=/home/joe/dev/hifipushie/workspace/_templates
export HIFIPUSHIE_HOME=/home/joe/dev/hifipushie/workspace
export HR=/home/joe/dev/hifipushie/workspace/hair_renders
export OUT=/mnt/data/hifipushie/hair4
cd "$(dirname "$0")/../../.."
s="$1"; shift
exec uv run python "spikes/hair_strands/hs4/$s" "$@"
