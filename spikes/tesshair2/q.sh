#!/bin/bash
# q.sh <tag> <patch.json ...>: a QUICK look: th_T<tag> regrown, the front + profile tiles through the fitted cameras, the
# hairline / outline measure of the front. ~1 min.
D=/mnt/data/hifipushie/tesshair2
n=$1; shift
$D/mk.sh $n "$@" || exit 1
$D/run.sh v0.py th_T$n > $D/out/q${n}_v0.txt 2>&1 || { tail -5 $D/out/q${n}_v0.txt; exit 1; }
$D/run.sh hline.py th_T$n 0 > $D/out/q${n}_hline.txt 2>&1
grep SUMMARY $D/out/q${n}_hline.txt
grep -A6 "HAIRLINE" $D/out/q${n}_hline.txt | head -12
