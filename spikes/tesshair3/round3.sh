#!/bin/bash
# round3.sh <model> [cycles]: the model's six tiles on the shared stage (3 fitted cameras + backl / backq / right), the
# same in Cycles when asked, the hairline / outline measure and hscore (un-shared: its own stage). Logs out/r_<model>_*.txt
D=/mnt/data/hifipushie/tesshair3
m=$1
$D/run.sh shots2.py $m > $D/out/r_${m}_shots.txt 2>&1 || { tail -5 $D/out/r_${m}_shots.txt; exit 1; }
if [ "$2" = "cycles" ]; then $D/run.sh shots2.py $m engine=cycles > $D/out/r_${m}_cyc.txt 2>&1 || tail -5 $D/out/r_${m}_cyc.txt; fi
$D/run.sh hline.py $m 0,1 > $D/out/r_${m}_hline.txt 2>&1
grep SUMMARY $D/out/r_${m}_hline.txt
$D/run.sh hs.py $m 0,1,2 > $D/out/r_${m}_hs.txt 2>&1
grep -E "^view|hairline band|forehead arch" $D/out/r_${m}_hs.txt
