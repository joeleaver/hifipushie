#!/bin/bash
# synth2.sh: WHAT REFERENCE WOULD SETTLE IT: head b (garrett_a1's identity, a narrow chin) shot other ways
R=/home/joe/dev/hifipushie/.claude/worktrees/agent-ae615b730ec496d10/spikes/chinread/run.sh
O=/mnt/data/hifipushie/chinread/out
mk() { t=$1; shift; [ -d /home/joe/dev/hifipushie/workspace/cz_${t}_00 ] || $R spikes/chinread/mkhead.py $t "$@" > $O/synth_$t.log 2>&1; }
mk bq garrett_a1 yaw=0,45,72
mk bp garrett_a1 pitch=15
mk bm garrett_a1 pitch=-15
mk bqp garrett_a1 yaw=0,45,72 pitch=15
mk bqm garrett_a1 yaw=0,45,72 pitch=-15
mk gq rand:3:0.6 move=chin_width:-6,jaw_width:-6 yaw=0,45,72
mk hq rand:4:0.6 move=chin_width:6,jaw_width:6 yaw=0,45,72
echo done > $O/synth2_done
