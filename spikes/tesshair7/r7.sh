#!/bin/bash
# r7.sh <NAME> [views=v0,v1,v2] [size=640]: ONE heavy job: th_<NAME> = tess_a1 + tie_hair(styles/<NAME>.json, carry_from
# $SRC (default th_T66), look = looks/<NAME>.json) + groom seed $SEED (default 0) through the tools (riff7.py), the lock
# plot, the fitted-camera tiles (shots5.py), the stand-off measure. Then rows out/row_<NAME>.jpg.
D=/mnt/data/hifipushie/tesshair7
n=$1; v=${2:-v0,v1,v2}; sz=${3:-640}
L=""; G=""
[ -f $D/looks/$n.json ] && L="look=@$D/looks/$n.json"
[ -f $D/grooms/$n.json ] && G="groom=@$D/grooms/$n.json"
S="seed=${SEED:-0}"
export W=/home/joe/dev/hifipushie/.claude/worktrees/tesshair7
$D/run.sh hv.py riff7.py th_$n ${HEAD:-tess_a1} ${SRC:-th_T66} @$D/styles/${STYLE:-$n}.json $L $G $S \
  -- lockplot.py th_$n -- shots7.py th_$n size=$sz views=$v ${EXTRA} -- standoff.py th_$n tag=a -- colvar.py th_$n > $D/out/r7_$n.txt 2>&1
rc=$?
grep -E "FAILED|Error|top layer|view v|MEAN|^  [-+]" $D/out/r7_$n.txt | cut -c1-600
R=/home/joe/dev/s0urc3/docs/img/tess_ref_full
python3 $W/spikes/tesshair7/row.py $D/out/row_$n.jpg h=600 hers=$R/tess_head_front.png $n=$D/out/s_th_${n}_v0.png hers=$R/tess_head_three_quarter_left.png $n=$D/out/s_th_${n}_v1.png hers=$R/tess_head_profile_left.png $n=$D/out/s_th_${n}_v2.png
exit $rc
