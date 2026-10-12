#!/bin/bash
# final.sh: with the final code: th_T33's round (+ Cycles) and its row of unfitted views, the riffs through the tool
# carried from th_T33, her style on hu_w28d through the tool, then the sheets.
D=/mnt/data/hifipushie/tesshair3
$D/round3.sh th_T33 cycles
$D/run.sh iso.py th_T33 a=base views=front,frontq,left,backl,back,right size=560 > $D/out/final_iso.txt 2>&1 || tail -4 $D/out/final_iso.txt
SRC=th_T33 $D/riffs.sh
$D/run.sh riff.py th_H1 hu_w28d th_T33 '{}' sync=1 look=$D/out/look_th_H1.png size=640 > $D/out/riff_H1.txt 2>&1 || tail -5 $D/out/riff_H1.txt
grep -E "^saved|^made|^rendered" $D/out/riff_H1.txt
$D/run.sh mk_sheets.py best=th_T33
echo ALL DONE
