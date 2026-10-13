#!/bin/bash
# r8.sh <NAME> [views=v0,v1,v2] [size=640]: th_<NAME> = $HEAD (tess_a1) + tie_hair(styles/<NAME>.json, carry_from $SRC
# (th_T66), looks/<NAME>.json) + seed. THREE jobs one after another, each in its own queue (round two's machine rules):
#   light slot (runl.sh, waits): riff7.py + lockplot.py      heavy (run.sh; shots7 takes resources.heavy): the tiles
#   light slot: standoff.py + colvar.py.   Then out/row_<NAME>.jpg.
D=/mnt/data/hifipushie/tesshair7
n=$1; v=${2:-v0,v1,v2}; sz=${3:-640}
L=""; G=""
[ -f $D/looks/$n.json ] && L="look=@$D/looks/$n.json"
[ -f $D/grooms/$n.json ] && G="groom=@$D/grooms/$n.json"
export W=/home/joe/dev/hifipushie/.claude/worktrees/tesshair7
HV_LIGHT=1 $D/runl.sh hv.py riff7.py th_$n ${HEAD:-tess_a1} ${SRC:-th_T66} @$D/styles/${STYLE:-$n}.json $L $G seed=${SEED:-0} -- lockplot.py th_$n > $D/out/r8_$n.txt 2>&1 || { echo "FAILED grow"; tail -6 $D/out/r8_$n.txt; exit 1; }
$D/run.sh shots7.py th_$n size=$sz views=$v ${EXTRA} >> $D/out/r8_$n.txt 2>&1 || { echo "FAILED shots"; tail -6 $D/out/r8_$n.txt; exit 1; }
HV_LIGHT=1 $D/runl.sh hv.py standoff.py th_$n tag=a -- colvar.py th_$n >> $D/out/r8_$n.txt 2>&1
grep -E "FAILED|Error|top layer|view v|MEAN|^  [-+]|slot: waited" $D/out/r8_$n.txt | cut -c1-600
R=/home/joe/dev/s0urc3/docs/img/tess_ref_full
python3 $W/spikes/tesshair7/row.py $D/out/row_$n.jpg h=600 hers=$R/tess_head_front.png $n=$D/out/s_th_${n}_v0.png hers=$R/tess_head_three_quarter_left.png $n=$D/out/s_th_${n}_v1.png hers=$R/tess_head_profile_left.png $n=$D/out/s_th_${n}_v2.png > /dev/null
