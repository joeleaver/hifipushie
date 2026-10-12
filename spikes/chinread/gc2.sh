#!/bin/bash
# gc2.sh: the good Garrett set with the tie (all four / the chin's width alone), chin points left out
D=/home/joe/dev/hifipushie/.claude/worktrees/agent-ae615b730ec496d10/spikes/chinread
$D/gc.sh gc_G00 gc_T 6 gc_T chin.chin_lm=none chin.tie=1 &
$D/gc.sh gc_G00 gc_U 6 gc_U chin.chin_lm=none chin.tie=chin_width &
wait
