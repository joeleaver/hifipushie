#!/bin/bash
# final.sh: ONE job after another (never two at once): the best (th_T66 = styles/T65.json, seed 0) through the tools,
# its tail measure, fitted-camera tiles (EEVEE 1536), the six riffs (th_V1..V6), the hairline before / after on the
# other humans (one model a process), then the Cycles tiles (last: minutes a frame).
D=/mnt/data/hifipushie/tesshair6
cp $D/looks/T56.json $D/looks/T66.json
SEED=0 STYLE=T65 CU=0 $D/go.sh T66
$D/run.sh tailfit.py th_T66 2>&1 | grep "^th_" | tee $D/out/tailfit_T66.txt
$D/run.sh shots5.py th_T66 size=1536 > $D/out/r_T66_shots.txt 2>&1 || tail -5 $D/out/r_T66_shots.txt
echo SHOTS DONE
$D/riffs.sh V1 V5 V3 V2 V4 V6
echo RIFFS DONE
for e in E3 E4 E0 E5 E7 E6 E8; do
  $D/run.sh hlE.py th_$e > $D/out/hlE_$e.log 2>&1
  grep -E "look_hair|FAILED" $D/out/hlE_$e.log | cut -c1-160
done
echo HAIRLINES DONE
$D/run.sh shots5.py th_T66 engine=cycles size=${CYS:-800} samples=64 > $D/out/r_T66_cyc.txt 2>&1 || tail -5 $D/out/r_T66_cyc.txt
echo ALL DONE
