#!/bin/bash
# whoz.sh <null model> <truth> <label> [who.py options]: who.py from the TRUE head: the step's move + the reads' bias lines only
R=/home/joe/dev/hifipushie/.claude/worktrees/agent-ae615b730ec496d10/spikes/chinread/run.sh
m=$1; t=$2; l=$3; shift 3
echo "## $l: $@"
$R spikes/chinread/who.py $m truth=$t "$@" 2>&1 | grep -E "^== |the step's move|sum \(the reads|^landmark|^outline|^group" | cut -c1-175
