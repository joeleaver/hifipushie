#!/bin/bash
# q.sh <log> <script> [args]: run.sh under the render lock (one heavy job at a time)
G=/mnt/data/hifipushie/gnmcrease
log=$1; shift
exec 9> $G/.q.lock
flock 9
$G/run.sh "$@" > $G/out/$log 2>&1
echo "done $log: $(tail -1 $G/out/$log)"
