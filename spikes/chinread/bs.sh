#!/bin/bash
# bs.sh <log name pattern, e.g. "b_n_*">: bsum.py over the matching benchmark logs (ends only)
cd /mnt/data/hifipushie/chinread/out
/home/joe/dev/hifipushie/.claude/worktrees/agent-ae615b730ec496d10/spikes/chinread/runl.sh /home/joe/dev/hifipushie/.claude/worktrees/agent-ae615b730ec496d10/spikes/chinread/bsum.py $(ls $1.log | sed "s|^|/mnt/data/hifipushie/chinread/out/|") 2>&1 | grep -v "(start)"
