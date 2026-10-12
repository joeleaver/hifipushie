#!/bin/bash
# b4all.sh "<tags>" "<runs>": b4.sh on several heads, three at a time (waits for a head's start model to exist, up to 40 min)
D=/home/joe/dev/hifipushie/.claude/worktrees/agent-ae615b730ec496d10/spikes/chinread
one() {
  for i in $(seq 240); do [ -f /home/joe/dev/hifipushie/workspace/cz_$1_00/human_refs.json ] && break; sleep 10; done
  $D/b4.sh $1 "$2"
}
n=0
for t in $1; do
  one $t "$2" &
  n=$((n+1))
  if [ $((n % 3)) -eq 0 ]; then wait; fi
done
wait
