#!/bin/bash
# the four known heads of the benchmark (one after another; each takes the heavy slot for its shots)
cd /mnt/data/hifipushie/solvereads
X="compress_face=0.5 squint=0.6 mouth_left=0.4 lips_roll_in=0.3"
./run.sh spikes/solvereads/mk_synth.py a_n gg_A06 > out/synth_a_n.log 2>&1
./run.sh spikes/solvereads/mk_synth.py a_x gg_A06 $X > out/synth_a_x.log 2>&1
./run.sh spikes/solvereads/mk_synth.py b_n garrett_a1 > out/synth_b_n.log 2>&1
./run.sh spikes/solvereads/mk_synth.py b_x garrett_a1 $X > out/synth_b_x.log 2>&1
echo done > out/synth_done
