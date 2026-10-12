#!/bin/bash
R=/mnt/data/hifipushie/refread
$R/run.sh spikes/refread/nrmval.py dressed tk_T06 diff=1 > $R/out/nrmval_dressed_diff.log 2>&1
$R/run.sh spikes/refread/nrmval.py dressed tk_T06 diff=clay > $R/out/nrmval_dressed_xclay.log 2>&1
