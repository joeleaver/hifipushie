#!/bin/bash
# shots.sh <model> ...: the judging shots (the pictures projected as the model's skin + own dressing, through each fitted
# camera; spikes/reruns/jsheet.py) cached in the scratch out/ (j_<model>_<view>.png), one model after another
export G=/mnt/data/hifipushie/chinread SIZE=520
for m in "$@"; do
  /home/joe/dev/hifipushie/.claude/worktrees/agent-ae615b730ec496d10/spikes/chinread/run.sh spikes/reruns/jsheet.py /mnt/data/hifipushie/chinread/out/js_$m.png $m=$m > /mnt/data/hifipushie/chinread/out/js_$m.log 2>&1
done
