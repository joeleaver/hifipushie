#!/bin/bash
# b2.sh: the anchors' WEIGHT (their errors are correlated: a bias the 170 components absorb, not scatter adapt can see)
B=/home/joe/dev/hifipushie/.claude/worktrees/agent-ae615b730ec496d10/spikes/chinread/bench.sh
for t in b_n a_n; do
  $B sx_${t}_00 sx_${t}_T cz_${t}_W3 ${t}_W3 chin.lm_sig=3
  $B sx_${t}_00 sx_${t}_T cz_${t}_W3C ${t}_W3C chin.lm_sig=3 chin.chin_lm=none
  $B sx_${t}_00 sx_${t}_T cz_${t}_W6 ${t}_W6 chin.lm_sig=6
done
