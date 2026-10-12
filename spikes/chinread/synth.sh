#!/bin/bash
# synth.sh: the chinread benchmark's known heads (one after another; each takes the heavy slot for its shots)
R=/home/joe/dev/hifipushie/.claude/worktrees/agent-ae615b730ec496d10/spikes/chinread/run.sh
O=/mnt/data/hifipushie/chinread/out
mk() { t=$1; shift; [ -d /home/joe/dev/hifipushie/workspace/cz_${t}_00 ] || $R spikes/chinread/mkhead.py $t "$@" > $O/synth_$t.log 2>&1; }
mk c garrett_a1 move=chin_width:-5
mk d garrett_a1 move=chin_width:5
mk e rand:1:0.6
mk f rand:2:0.6
mk g rand:3:0.6 move=chin_width:-6,jaw_width:-6
mk h rand:4:0.6 move=chin_width:6,jaw_width:6
mk bs garrett_a1 light=soft
mk es rand:1:0.6 light=soft
mk gs rand:3:0.6 move=chin_width:-6,jaw_width:-6 light=soft
echo done > $O/synth_done
