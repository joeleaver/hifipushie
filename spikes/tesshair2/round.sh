#!/bin/bash
# round.sh <NN> <patch.json ...>: th_T<NN> = th_T04's recipe + the patches (spikes/tesshair2), regrown; shots (3 fitted
# cameras + 3 unseen views) on the shared stage, the hairline / outline measure, hscore. Logs out/r<NN>_*.txt
D=/mnt/data/hifipushie/tesshair2
n=$1; shift
m=th_T$n
$D/mk.sh $n "$@" || exit 1
$D/run.sh shots2.py $m > $D/out/r${n}_shots.txt 2>&1 || { tail -5 $D/out/r${n}_shots.txt; exit 1; }
$D/run.sh hline.py $m 0,1 > $D/out/r${n}_hline.txt 2>&1
grep SUMMARY $D/out/r${n}_hline.txt
$D/run.sh hs.py $m 0,1,2 > $D/out/r${n}_hs.txt 2>&1
grep -E "^view|hairline band|forehead arch" $D/out/r${n}_hs.txt
