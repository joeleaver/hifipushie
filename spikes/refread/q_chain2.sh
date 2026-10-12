#!/bin/bash
R=/mnt/data/hifipushie/refread
$R/run.sh spikes/refread/chain.py tq_T00 tqf_T 4 first=free rest=free > $R/out/chain_tqf.log 2>&1
$R/run.sh /home/joe/dev/hifipushie/spikes/reruns/eyespan.py tqf_T04 tk_T06 > $R/out/eyespan2.log 2>&1
