#!/bin/bash
# bench.sh <start model> <truth model> <out prefix> <log name> [cchain options]: one benchmark chain (3 calls; N=<n> for
# more), skipped when its log is complete
O=/mnt/data/hifipushie/chinread/out
s=$1; t=$2; p=$3; l=$4; shift 4
n=${N:-3}
[ -f $O/$l.log ] && grep -q "${p}0${n}" $O/$l.log && exit 0
/home/joe/dev/hifipushie/.claude/worktrees/agent-ae615b730ec496d10/spikes/chinread/run.sh spikes/chinread/cchain.py $s $p $n truth=$t "$@" > $O/$l.log 2>&1
