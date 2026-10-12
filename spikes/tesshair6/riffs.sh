#!/bin/bash
# riffs.sh <NAME> ...: each th_<NAME> through the tool (go.sh, CU=0) + six unfitted views on the shared stage
# (iso.py: out/iso_th_<NAME>_a_<view>.png) and a close-up of the temple hairline (cu.sh frontq,left -> _c_)
D=/mnt/data/hifipushie/tesshair6
for n in "$@"; do
  CU=0 $D/go.sh $n || continue
  $D/run.sh iso.py th_$n a=base views=front,frontq,left,backl,back,right size=640 > $D/out/riff_${n}_iso.txt 2>&1 || { echo "FAILED iso $n"; tail -4 $D/out/riff_${n}_iso.txt; }
  $D/cu.sh th_$n base frontq,left > /dev/null
  echo "done $n"
done
