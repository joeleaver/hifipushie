#!/bin/bash
# final2.sh: th_T34 = th_T33's style regrown with the last code (smaller flick): round + Cycles, its unfitted row, sheets.
D=/mnt/data/hifipushie/tesshair3
ST='{"tie": "low", "side": "left", "tightness": 0.3, "neatness": 0.2, "tail": {"length": 0.24, "wave": 0.8, "fullness": 0.75}}'
$D/run.sh mk3.py th_T34 tess_a1 "$ST" from=th_T14 plot=1 > $D/out/f2_mk.txt 2>&1 || { tail -5 $D/out/f2_mk.txt; exit 1; }
$D/round3.sh th_T34 cycles
$D/run.sh iso.py th_T34 a=base views=front,frontq,left,backl,back,right size=560 > $D/out/f2_iso.txt 2>&1 || tail -4 $D/out/f2_iso.txt
$D/run.sh mk_sheets.py best=th_T34
echo ALL DONE
