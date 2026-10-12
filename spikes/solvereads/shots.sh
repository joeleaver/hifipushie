#!/bin/bash
# judging shots (projected skin + own dressing through each fitted camera) of the reruns' heads, cached in out/
cd /mnt/data/hifipushie/solvereads
until [ -f out/reruns2_done ]; do sleep 15; done
export G=/mnt/data/hifipushie/solvereads SIZE=520
for m in gh_B06 gh_H06 tv_B03 gp_B05 gp_H05 tv_H05; do
  ./run.sh spikes/reruns/jsheet.py out/js_$m.png $m=$m > out/js_$m.log 2>&1
done
./run.sh spikes/reruns/eyespan.py tv_B03 tqr_T04 tv_H05 gh_B06 gg_A06 gp_B05 gr_G05 > out/eyespan.log 2>&1
echo done > out/shots_done
