#!/bin/bash
# tests.sh [test files..]: the hair tests on this worktree's code, each through a machine-wide LIGHT slot
W=/home/joe/dev/hifipushie/.claude/worktrees/agent-ac19f4a9531cf46f3
export HIFIPUSHIE_HOME=/home/joe/dev/hifipushie/workspace HIFIPUSHIE_ASSETS=/home/joe/dev/hifipushie/workspace/_templates
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
cd $W
T=${@:-test_hair_flow test_hair_tied test_hair_loose test_hair_lift test_hair_strands test_hair_ear test_toolsets}
for t in $T; do echo "== $t"; /mnt/data/hifipushie/bin/slot uv run python -m pytest -q tests/$t.py 2>&1 | tail -${TAILN:-6}; done
