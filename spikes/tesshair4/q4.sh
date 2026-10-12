#!/bin/bash
# q4.sh <NN> <style json> [views] [size]: th_T<NN> = tess_a1 + the tied style (hairline + look of th_T34), regrown;
# one row of unfitted views on the shared stage (iso.py). Tiles out/iso_th_T<NN>_a_<view>.png
D=/mnt/data/hifipushie/tesshair4
n=$1; st=$2; v=${3:-front,frontq,left,backl,back,right}
$D/run.sh mk3.py th_T$n tess_a1 "$st" from=${FROM:-th_T34} plot=1 > $D/out/q${n}_mk.txt 2>&1 || { tail -5 $D/out/q${n}_mk.txt; exit 1; }
$D/run.sh iso.py th_T$n a=base views=$v size=${4:-640} > $D/out/q${n}_iso.txt 2>&1 || { tail -8 $D/out/q${n}_iso.txt; exit 1; }
tail -1 $D/out/q${n}_iso.txt
