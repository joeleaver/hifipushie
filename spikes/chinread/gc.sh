#!/bin/bash
# gc.sh <start> <prefix> <n> <log> [options]: a rerun chain (no truth) through cchain.py, log in the scratch out/
O=/mnt/data/hifipushie/chinread/out
s=$1; p=$2; n=$3; l=$4; shift 4
/home/joe/dev/hifipushie/.claude/worktrees/agent-ae615b730ec496d10/spikes/chinread/runl.sh spikes/chinread/cchain.py $s $p $n "$@" > $O/$l.log 2>&1
