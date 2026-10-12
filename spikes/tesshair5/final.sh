#!/bin/bash
# final.sh [best NAME=T53]: everything the sheets need, through the tool: Tess's fitted style + calibrated look
# (styles/T53.json, looks/T53.json), the hairline dial (H0 H5 H10), the six riffs (S1..S6), the fitted-camera tiles of
# the best (EEVEE at the references' own pixels, Cycles calibrated), the tail measure, then mk_sheets5.py.
D=/mnt/data/hifipushie/tesshair5
B=${1:-T53}
CU=0 $D/go.sh $B
$D/run.sh tailfit.py th_$B 2>&1 | grep -E "^th_" | tee $D/out/tailfit_$B.txt
for n in H0 H5 H10; do CU=0 $D/go.sh $n; $D/cu.sh th_$n; done
$D/riffs.sh ${RIFFS:-S1 S2 S3 S4 S5 S6}
$D/run.sh shots5.py th_$B size=1536 > $D/out/r_${B}_shots.txt 2>&1 || tail -5 $D/out/r_${B}_shots.txt
$D/run.sh shots5.py th_$B engine=cycles size=${CYS:-800} samples=64 > $D/out/r_${B}_cyc.txt 2>&1 || tail -5 $D/out/r_${B}_cyc.txt
$D/run.sh mk_sheets5.py best=th_$B
echo ALL DONE
