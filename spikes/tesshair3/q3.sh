#!/bin/bash
# q3.sh <NN> <style json> [views] [head] : th_T<NN> = tess_a1 + the tied style, regrown; one row of unfitted views (iso.py)
D=/mnt/data/hifipushie/tesshair3
n=$1; st=$2; v=${3:-front,frontq,left,backl,back,right}
$D/run.sh mk3.py th_T$n tess_a1 "$st" plot=1 > $D/out/q${n}_mk.txt 2>&1 || { tail -5 $D/out/q${n}_mk.txt; exit 1; }
$D/run.sh iso.py th_T$n a=base views=$v size=560 > $D/out/q${n}_iso.txt 2>&1 || { tail -8 $D/out/q${n}_iso.txt; exit 1; }
tail -2 $D/out/q${n}_iso.txt
