#!/bin/bash
# tests.sh [test files..]: the hair tests on this worktree's code (capped)
W=/home/joe/dev/hifipushie/.claude/worktrees/agent-a3e04a545de405a3f
export HIFIPUSHIE_HOME=/home/joe/dev/hifipushie/workspace HIFIPUSHIE_ASSETS=/home/joe/dev/hifipushie/workspace/_templates
cd $W
T=${@:-test_hair_flow test_hair_tied test_hair_loose test_hair_lift test_hair_strands}
for t in $T; do echo "== $t"; nice /mnt/data/hifipushie/bin/capped uv run python -m pytest -q tests/$t.py 2>&1 | tail -${TAILN:-6}; done
