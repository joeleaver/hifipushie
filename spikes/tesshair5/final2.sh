#!/bin/bash
# final2.sh [best NAME=T54]: what final.sh left: the half-up riff, the best's fitted-camera tiles, the sheets.
D=/mnt/data/hifipushie/tesshair5
B=${1:-T54}
$D/riffs.sh S4
$D/run.sh shots5.py th_$B size=1536 > $D/out/r_${B}_shots.txt 2>&1 || tail -5 $D/out/r_${B}_shots.txt
$D/run.sh mk_sheets5.py best=th_$B
echo EEVEE SHEETS DONE
$D/run.sh shots5.py th_$B engine=cycles size=${CYS:-800} samples=64 > $D/out/r_${B}_cyc.txt 2>&1 || tail -5 $D/out/r_${B}_cyc.txt
$D/run.sh mk_sheets5.py best=th_$B
echo ALL DONE
