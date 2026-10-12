#!/bin/bash
# the three reruns with the new solve's defaults (no hold, no expression): good Garrett, Tess, Garrett's paintings
cd /mnt/data/hifipushie/solvereads
./run.sh spikes/solvereads/chain.py gh_G00 gh_B 6 >> out/rerun2_gh.log 2>&1
./run.sh spikes/solvereads/chain.py tv_T00 tv_B 5 >> out/rerun2_tv.log 2>&1
./run.sh spikes/solvereads/chain.py gp_G00 gp_B 5 >> out/rerun2_gp.log 2>&1
./run.sh spikes/solvereads/chain.py gh_G00 gh_H 6 hold=auto >> out/rerun2_ghH.log 2>&1
./run.sh spikes/solvereads/chain.py gp_G00 gp_H 5 hold=auto >> out/rerun2_gpH.log 2>&1
./run.sh spikes/solvereads/chain.py tv_T00 tv_H 5 hold=auto >> out/rerun2_tvH.log 2>&1
echo done > out/reruns2_done
