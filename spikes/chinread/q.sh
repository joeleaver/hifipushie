#!/bin/bash
# q.sh <queue file>: ONE job at a time (the coordinator's cap: two processes for this agent: this queue + one foreground
# command), each line a command run from the worktree; waits first for any chinread job still running. Every python goes
# through run.sh (bin/capped, OPENBLAS / OMP 1 thread); renders take resources.heavy themselves.
cd /home/joe/dev/hifipushie/.claude/worktrees/agent-ae615b730ec496d10
until [ "$(pgrep -fc 'spikes/chinread/(cchain|mkhead|rval|eev)[.]py')" = "0" ]; do sleep 10; done
while IFS= read -r line; do
  [ -z "$line" ] && continue
  case "$line" in \#*) continue ;; esac
  echo "$(date +%H:%M:%S) $line" >> /mnt/data/hifipushie/chinread/out/q.log
  bash -c "$line" >> /mnt/data/hifipushie/chinread/out/q.log 2>&1
done < "$1"
echo "$(date +%H:%M:%S) queue $1 done" >> /mnt/data/hifipushie/chinread/out/q.log
