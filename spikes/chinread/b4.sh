#!/bin/bash
# b4.sh <tag> [runs: "N C CT A"]: the benchmark's main variants on one chinread head (start cz_<tag>_00, truth cz_<tag>_T):
#   N today's solve; C = the detector's chin points left out; A = no anchors; CT = C + the tie; T = the tie alone;
#   W3 = anchors at 3 x their sigma; CW = C + anchors x 2
B=/home/joe/dev/hifipushie/.claude/worktrees/agent-ae615b730ec496d10/spikes/chinread/bench.sh
t=$1
for r in ${2:-N C CT A}; do
  case $r in
    N) o="chin.chin_lm=xy" ;;
    C) o="chin.chin_lm=none" ;;
    A) o="anchors=none" ;;
    T) o="chin.tie=1" ;;
    CT) o="chin.chin_lm=none chin.tie=1" ;;
    W3) o="chin.lm_sig=3" ;;
    CW) o="chin.chin_lm=none chin.lm_sig=2" ;;
    CY) o="chin.chin_lm=y" ;;
    CX) o="chin.chin_lm=x" ;;
    CF) o="chin.chin_lm=fx" ;;
    CS) o="chin.chin_lm=none chin.size=1" ;;
    CFS) o="chin.chin_lm=fx chin.size=1" ;;
    CW3) o="chin.chin_lm=none chin.lm_sig=3" ;;
  esac
  $B cz_${t}_00 cz_${t}_T cz_${t}_${r} ${t}_${r} $o
done
