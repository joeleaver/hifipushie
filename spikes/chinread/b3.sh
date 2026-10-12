#!/bin/bash
# b3.sh: the TIE (unread jaw / chin widths follow their expectation given the read measures), its tightness, with / without anchors
B=/home/joe/dev/hifipushie/.claude/worktrees/agent-ae615b730ec496d10/spikes/chinread/bench.sh
for t in b_n a_n; do
  $B sx_${t}_00 sx_${t}_T cz_${t}_T3 ${t}_T3 chin.tie=1
  $B sx_${t}_00 sx_${t}_T cz_${t}_T1 ${t}_T1 chin.tie=1 chin.tie_sig=0.1
  $B sx_${t}_00 sx_${t}_T cz_${t}_T10 ${t}_T10 chin.tie=1 chin.tie_sig=1.0
  $B sx_${t}_00 sx_${t}_T cz_${t}_TA ${t}_TA chin.tie=1 anchors=none
  $B sx_${t}_00 sx_${t}_T cz_${t}_TW ${t}_TW chin.tie=1 chin.lm_sig=3
done
