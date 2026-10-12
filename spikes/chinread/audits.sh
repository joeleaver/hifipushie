#!/bin/bash
# audits.sh <model> ...: solvereads' audit.py (what the joint solve reads, nothing applied) per model, the chin / jaw rows
for m in "$@"; do
  /home/joe/dev/hifipushie/.claude/worktrees/agent-ae615b730ec496d10/spikes/chinread/runl.sh spikes/solvereads/audit.py $m > /mnt/data/hifipushie/chinread/out/audit_$m.log 2>&1
  echo "== $m"; grep -E "^(chin_width|jaw_width|gonial_width|jaw_square|jaw_angle|chin_length|chin_forward|under_chin) " /mnt/data/hifipushie/chinread/out/audit_$m.log | sort -u | cut -c1-150
done
