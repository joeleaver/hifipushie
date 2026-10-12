#!/bin/bash
# mk.sh <NN> <patch.json ...>: th_T<NN> = tess_a1 + f3_t1's groom + tesshair's p02-p04 (= th_T04) + the given patches
# (names in spikes/tesshair2), regrown. Refuses th_T01..T05.
D=/mnt/data/hifipushie/tesshair2
S=/home/joe/dev/hifipushie/.claude/worktrees/agent-a1369a88d9730a4d3/spikes
n=$1; shift
case "$n" in 01|02|03|04|05) echo "th_T$n is the first agent's"; exit 1;; esac
P=""; for f in "$@"; do P="$P $S/tesshair2/$f"; done
$D/run.sh mk.py th_T$n tess_a1 f3_t1 $S/tesshair/p02.json $S/tesshair/p03.json $S/tesshair/p04.json $P > $D/out/r${n}_mk.txt 2>&1 || { tail -5 $D/out/r${n}_mk.txt; exit 1; }
tail -1 $D/out/r${n}_mk.txt
