#!/bin/bash
# go.sh <NAME> [views] [variant]: th_<NAME> = tess_a1 + server.tie_hair(style = styles/<NAME>.json, carry_from $SRC
# (default th_T34), look = looks/<NAME>.json when there is one) + server.groom_hair(groom = grooms/<NAME>.json when
# there is one, seed = $SEED) THROUGH THE TOOLS (riff6.py), then close-up tiles (cu.sh) and their crops (cc.py ->
# out/_f _q _l.png). CU=0: no render.
D=/mnt/data/hifipushie/tesshair6
W=/home/joe/dev/hifipushie/.claude/worktrees/agent-ac19f4a9531cf46f3
n=$1
L=""; G=""; S=""
[ -f $D/looks/$n.json ] && L="look=@$D/looks/$n.json"
[ -f $D/grooms/$n.json ] && G="groom=@$D/grooms/$n.json"
[ -n "$SEED" ] && S="seed=$SEED"
$D/run.sh riff6.py th_$n tess_a1 ${SRC:-th_T34} @$D/styles/${STYLE:-$n}.json $L $G $S > $D/out/riff_$n.txt 2>&1 || { echo FAILED; tail -5 $D/out/riff_$n.txt; exit 1; }
grep -E "^saved|^made|tie_hair" $D/out/riff_$n.txt | cut -c1-200
[ "${CU:-1}" = 0 ] && exit 0
$D/cu.sh th_$n ${3:-base} ${2:-front,frontq,left}
TOUT=$D/out python3 $W/spikes/tesshair5/cc.py th_$n
