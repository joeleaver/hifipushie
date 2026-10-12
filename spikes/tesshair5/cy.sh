#!/bin/bash
# cy.sh <model> <tag> [look name in looks/ | -] [extra cyccal args]: cyccal.py with the look merged from looks/<name>.json
D=/mnt/data/hifipushie/tesshair5
m=$1; t=$2; l=${3:--}; shift 3
if [ "$l" = "-" ]; then
  $D/run.sh cyccal.py $m tag=$t "$@" > $D/out/cy_${m}_$t.txt 2>&1
else
  $D/run.sh cyccal.py $m tag=$t look=@$D/looks/$l.json "$@" > $D/out/cy_${m}_$t.txt 2>&1
fi
grep -E "^v|^   |rror" $D/out/cy_${m}_$t.txt
