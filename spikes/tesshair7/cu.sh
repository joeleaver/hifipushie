#!/bin/bash
# cu.sh <model> [variant] [views] : CLOSE-UP tiles (fov 9, 900 px: ~0.28 mm a pixel, the references' scale) of the hairline
# + one row sheet out/cu_<model>[_<tag>].png. variant = an iso.py variant (default base), tag = $TAG (default c)
D=/mnt/data/hifipushie/tesshair7
m=$1; v=${2:-base}; vs=${3:-front,frontq,left}; t=${TAG:-c}
$D/run.sh iso.py $m $t=$v views=$vs size=${SIZE:-900} fov=${FOV:-9} dz=${DZ:-0.045} > $D/out/cu_${m}_$t.txt 2>&1 || { tail -8 $D/out/cu_${m}_$t.txt; exit 1; }
tail -1 $D/out/cu_${m}_$t.txt
