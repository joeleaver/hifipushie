#!/bin/bash
# go.sh <NAME> [views] [variant]: th_<NAME> = tess_a1 + server.tie_hair(style = styles/<NAME>.json, carry_from $SRC
# (default th_T34), look = looks/<NAME>.json when there is one) + server.groom_hair(groom = grooms/<NAME>.json when
# there is one) THROUGH THE TOOLS (riff5.py), then close-up tiles (cu.sh) and their crops (cc.py -> out/_f _q _l.png).
# CU=0: no render.
D=/mnt/data/hifipushie/tesshair5
n=$1
L=""; G=""
[ -f $D/looks/$n.json ] && L="look=@$D/looks/$n.json"
[ -f $D/grooms/$n.json ] && G="groom=@$D/grooms/$n.json"
$D/run.sh riff5.py th_$n tess_a1 ${SRC:-th_T34} @$D/styles/$n.json $L $G > $D/out/riff_$n.txt 2>&1 || { echo FAILED; tail -5 $D/out/riff_$n.txt; exit 1; }
grep -E "^saved|^made|tie_hair" $D/out/riff_$n.txt
[ "${CU:-1}" = 0 ] && exit 0
$D/cu.sh th_$n ${3:-base} ${2:-front,frontq,left}
python3 /home/joe/dev/hifipushie/.claude/worktrees/agent-a3e04a545de405a3f/spikes/tesshair5/cc.py th_$n
