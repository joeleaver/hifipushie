#!/bin/bash
# bench.sh [part1|part2|all] [tags..]: the ground-truth benchmark, start to end (docs/notes/groundtruth.md).
#   Data: $HIFIPUSHIE_GROUNDTRUTH (fetch.sh; nothing of it in git). Tags: lps HSR0040-Body-023 HSR0112-Body-018.
#   RUN = how one python job is started (default: uv run python; on the shared machine a light slot:
#   RUN="/mnt/data/hifipushie/groundtruth/run.sh"). Part 2's chains are ~10-16 min each: queue them (three at once).
# part1 (the CEILING, ~15 min a scan): working copy, landmark start, HSRD scan -> rig registration, the direct fits, tables, sheet
# part2 (the PIPELINE, ~1 h a scan): truth model + pictures + starts, 4 chains x 8 calls, scores against the scan, sheets
set -e
cd "$(dirname "$0")/../.."
export PYTHONPATH=$PWD/src:$PWD/spikes/groundtruth:$PWD/spikes/solvecams:$PWD/spikes/chinread:$PWD/spikes/garrett3:$PYTHONPATH
RUN=${RUN:-uv run python}
G=spikes/groundtruth
R=${HIFIPUSHIE_GROUNDTRUTH:-/mnt/data/hifipushie/groundtruth}
what=${1:-all}; shift || true
TAGS=${@:-lps HSR0040-Body-023 HSR0112-Body-018}
short() { case $1 in lps) echo lps;; HSR0040-Body-023) echo h40;; HSR0112-Body-018) echo h112;; esac; }
mkdir -p $R/out/chains $R/out/logs
if [ $what = part1 ] || [ $what = all ]; then
  for t in $TAGS; do
    if [ $t = lps ]; then $RUN $G/prep.py lps; $RUN $G/align0.py lps yup=1
    else $RUN $G/prep.py hsrd $t; $RUN $G/align0.py $t turn=180; $RUN $G/register.py $t; $RUN $G/check_cams.py $t; fi
    for a in "prior=1 cmax=3" "prior=0.25 cmax=3" "prior=1 cmax=3 expr=1" "prior=0.25 cmax=3 expr=1" "prior=1" "prior=1 expr=1"; do $RUN $G/fit3d.py $t $a; done
  done
  $RUN $G/tab1.py $TAGS | tee $R/out/tab1.md
  $RUN $G/sheet1.py workspace/human_renders/gt_01_ceiling.png $(for t in $TAGS; do echo $t:p1b3; done) features=1
fi
if [ $what = part2 ] || [ $what = all ]; then
  for t in $TAGS; do
    k=$(short $t)
    # HSR0112: the cameras chosen by eye (her head stands at the edge of several photos)
    [ $t = HSR0112-Body-018 ] && extra="cams=f:A05,s72:B05,s90:B03,fu:A02" || extra=""
    $RUN $G/gmk.py $t $extra
    ni=""; [ $t = lps ] && ni="noiris=1"          # the Lee Perry-Smith head's eyes are shut
    $RUN $G/gchain.py gt_${k}_A00 gt_${k}_Afr 8 truth=gt_${k}_AT cameras=free $ni
    $RUN $G/gchain.py gt_${k}_A00 gt_${k}_Afrd 8 truth=gt_${k}_AT cameras=free dense=1 $ni
    $RUN $G/gchain.py gt_${k}_A00 gt_${k}_Apu 8 truth=gt_${k}_AT cameras=free start=true pert=f:pitch:8 $ni
    $RUN $G/gchain.py gt_${k}_A00 gt_${k}_Apud 8 truth=gt_${k}_AT cameras=free start=true pert=f:pitch:8 dense=1 $ni
    $RUN $G/gsum.py $t "off, start fitted"=gt_${k}_Afr "on, start fitted"=gt_${k}_Afrd "off, true cams +8 pitch"=gt_${k}_Apu "on, true cams +8 pitch"=gt_${k}_Apud | tee $R/out/sum_$k.md
    $RUN $G/glm.py $t | tee $R/out/dense_$t.md
  done
  $RUN $G/sheet2.py workspace/human_renders/gt_02_pipeline.png $(for t in $TAGS; do k=$(short $t); echo $t:gt_${k}_Afr08:gt_${k}_Afrd08; done) features=1
fi
