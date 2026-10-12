#!/bin/bash
# b1.sh: the anchors' part in the chin: variants on the two solvereads heads (b = narrow chin truth, a = broad)
B=/home/joe/dev/hifipushie/.claude/worktrees/agent-ae615b730ec496d10/spikes/chinread/bench.sh
for t in b_n a_n; do
  $B sx_${t}_00 sx_${t}_T cz_${t}_N ${t}_N
  $B sx_${t}_00 sx_${t}_T cz_${t}_A ${t}_A anchors=none
  $B sx_${t}_00 sx_${t}_T cz_${t}_S ${t}_S chin.lm_stretch=1
  $B sx_${t}_00 sx_${t}_T cz_${t}_C ${t}_C chin.chin_lm=none
  $B sx_${t}_00 sx_${t}_T cz_${t}_SC ${t}_SC chin.lm_stretch=1 chin.chin_lm=none
  $B sx_${t}_00 sx_${t}_T cz_${t}_SY ${t}_SY chin.lm_stretch=1 chin.chin_lm=y
done
