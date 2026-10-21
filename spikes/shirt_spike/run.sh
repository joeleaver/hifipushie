#!/bin/bash
# run.sh <script> [args]: shirt spike scripts with the modest-napier worktree's code, under bin/capped
export HIFIPUSHIE_HOME=/home/joe/dev/hifipushie/workspace HIFIPUSHIE_ASSETS=/home/joe/dev/hifipushie/workspace/_templates
export TMPDIR=/mnt/data/hifipushie/tmp OPENBLAS_NUM_THREADS=4 OMP_NUM_THREADS=4 PYTHONUNBUFFERED=1 HIFIPUSHIE_CLOTH_SHADOWS=0
cd /home/joe/dev/hifipushie/.claude/worktrees/modest-napier-7b031c
s=$1; shift
case $s in /*) p=$s ;; *) p=/mnt/data/hifipushie/shirt_spike/$s ;; esac
/mnt/data/hifipushie/bin/capped uv run python $p "$@"
