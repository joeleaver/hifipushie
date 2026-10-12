#!/bin/bash
# round.sh <NN> <patch.json ...>: th_T<NN> = tess_a1 + f3_t1's groom + the patches (in order), regrown; shots (3 fitted
# cameras + 3 unseen views), the hairline / outline measure, hscore. Logs in out/r<NN>_*.txt
D=/mnt/data/hifipushie/tesshair
n=$1; shift
m=th_T$n
$D/run.sh mk.py $m tess_a1 f3_t1 "$@" > $D/out/r${n}_mk.txt 2>&1 || { tail -5 $D/out/r${n}_mk.txt; exit 1; }
tail -1 $D/out/r${n}_mk.txt
$D/run.sh shots.py $m > $D/out/r${n}_shots.txt 2>&1 || { tail -5 $D/out/r${n}_shots.txt; exit 1; }
$D/run.sh hline.py $m 0,1 > $D/out/r${n}_hline.txt 2>&1
grep SUMMARY $D/out/r${n}_hline.txt
$D/run.sh hs.py $m 0,1,2 > $D/out/r${n}_hs.txt 2>&1
grep -E "^view|hairline band|forehead arch" $D/out/r${n}_hs.txt
