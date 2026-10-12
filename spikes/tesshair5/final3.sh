#!/bin/bash
# final3.sh [best NAME=T55]: with the hairline's EAR put where the ear is (grooms/<NAME>.json: hairline.ear -0.013,
# sideburns 0.035, through server.groom_hair): the best's tail measure and fitted-camera tiles, the six riffs regrown,
# the sheets (EEVEE first, then again with the Cycles tiles).
D=/mnt/data/hifipushie/tesshair5
B=${1:-T55}
for n in S1 S2 S3 S4 S5 S6; do cp $D/grooms/T55.json $D/grooms/$n.json; done
$D/run.sh tailfit.py th_$B 2>&1 | grep -E "^th_" | tee $D/out/tailfit_$B.txt
$D/run.sh shots5.py th_$B size=1536 > $D/out/r_${B}_shots.txt 2>&1 || tail -5 $D/out/r_${B}_shots.txt
$D/riffs.sh S1 S5 S3 S2 S4 S6
$D/run.sh mk_sheets5.py best=th_$B
echo EEVEE SHEETS DONE
$D/run.sh shots5.py th_$B engine=cycles size=${CYS:-800} samples=64 > $D/out/r_${B}_cyc.txt 2>&1 || tail -5 $D/out/r_${B}_cyc.txt
$D/run.sh mk_sheets5.py best=th_$B
echo ALL DONE
