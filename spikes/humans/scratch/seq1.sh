#!/bin/bash
# the clay line-up, then the tests, one after the other
cd "$(dirname "$0")/.."
L=scratchpad/seq1.log
: > $L
bash scratchpad/run.sh spikes/humans/lineup.py clay >> $L 2>&1
for t in test_humans test_headfit test_skin test_images test_bodywarp; do
  echo "=== $t" >> $L
  bash scratchpad/run.sh tests/$t.py 2>&1 | tail -6 >> $L
done
echo ALLDONE >> $L
