#!/bin/bash
# batch.sh <list file> [views] [size]: every line "<name>|<style json>" THROUGH THE TOOL (riff.py = server.tie_hair on a
# copy of tess_a1, carry_from $SRC) and rendered on the shared stage (iso.py). Tiles out/iso_th_<name>_a_<view>.png
D=/mnt/data/hifipushie/tesshair5
SRC=${SRC:-th_T66}
V=${2:-front,frontq,left,backl,back,right}; N=${3:-640}
while IFS='|' read -r n st; do
  [ -z "$n" ] && continue
  $D/run.sh riff.py th_$n tess_a1 $SRC "$st" > $D/out/riff_$n.txt 2>&1 || { echo "FAILED $n"; tail -4 $D/out/riff_$n.txt; continue; }
  $D/run.sh iso.py th_$n a=base views=$V size=$N > $D/out/riff_${n}_iso.txt 2>&1 || { echo "FAILED iso $n"; tail -4 $D/out/riff_${n}_iso.txt; }
  echo "done $n"
done < $1
