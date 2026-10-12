#!/bin/bash
R=/mnt/data/hifipushie/refread
$R/run.sh spikes/refread/chain.py tq_T00 tq_T 4 first=trust rest=trust > $R/out/chain_tq.log 2>&1
$R/run.sh spikes/refread/chain.py gr_G00 gr_G 5 first=refit rest=free > $R/out/chain_gr.log 2>&1
$R/run.sh /home/joe/dev/hifipushie/spikes/reruns/eyespan.py tn_T00 tess_a1 tq_T04 gj_G00 b3_G17 gr_G05 > $R/out/eyespan.log 2>&1
