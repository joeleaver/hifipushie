#!/bin/bash
# final.sh <best model>: the fitted-camera tiles for the sheets: the best model (EEVEE at the references' own pixel
# size for the close-ups, Cycles), round three's th_R3 and th_W1 WITH ROUND THREE'S CODE (its worktree's run.sh), then
# the sheets (mk_sheets4.py).
D=/mnt/data/hifipushie/tesshair5
B=${1:-th_T47}
$D/run.sh shots2.py $B size=1536 > $D/out/r_${B}_shots.txt 2>&1 || tail -5 $D/out/r_${B}_shots.txt
$D/run.sh shots2.py $B engine=cycles size=1024 > $D/out/r_${B}_cyc.txt 2>&1 || tail -5 $D/out/r_${B}_cyc.txt
for m in th_R3 th_W1; do
  [ -f $D/out/s_${m}_v0.png ] || TOUT=$D/out /mnt/data/hifipushie/tesshair3/run.sh shots2.py $m > $D/out/r_${m}_shots.txt 2>&1 || tail -5 $D/out/r_${m}_shots.txt
done
$D/run.sh hs.py $B 0,1,2 > $D/out/r_${B}_hs.txt 2>&1
grep -E "^view|hairline band|forehead arch" $D/out/r_${B}_hs.txt
$D/run.sh mk_sheets4.py best=$B
echo ALL DONE
