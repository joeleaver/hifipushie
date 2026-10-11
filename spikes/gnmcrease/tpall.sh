#!/bin/bash
# tpall.sh <target model> <prefix> <donor>...: face-held strip transplants (sigma 0.2, strip 12 mm, affine) -> out/tp_<prefix>_<donor>.npy
cd /mnt/data/hifipushie/gnmcrease
m=$1; p=$2; shift 2
for d in "$@"; do
  t=${p}_${d//[:_]/}
  HOLDALL=0.3 STRIP=12 AFFINE=1 ./run.sh transplant.py "$m" "$d" "$t" 0.2 2>&1 | grep -E "made|local|hsoft|clay|macros"
done
