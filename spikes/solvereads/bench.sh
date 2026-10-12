#!/bin/bash
# the benchmark: every variant of the solve on the known heads, 3 calls each, one after another
# letters: N = no hold, no expression (today's solve + the carried down-weighting / readers / damping), E = expression per
# view, S = expression shared, H = hold what no read looks at, K = hold + expression
cd /mnt/data/hifipushie/solvereads
run() {  # tag truth letter options...
  t=$1; tr=$2; l=$3; shift 3
  [ -f out/bench_${t}_${l}.log ] && grep -q "${l}03" out/bench_${t}_${l}.log && return
  ./run.sh spikes/solvereads/chain.py sx_${t}_00 sx_${t}_${l} 3 truth=sx_${tr}_T "$@" > out/bench_${t}_${l}.log 2>&1
}
run a_x a_x N
run a_x a_x X expression=view
run a_x a_x S expression=shared
run a_n a_n N
run a_n a_n X expression=view
run a_n a_n H hold=auto
run b_n b_n N
run b_n b_n H hold=auto
run b_x b_x N
run b_x b_x X expression=view
for t in b_n a_n; do
  [ -d /home/joe/dev/hifipushie/workspace/sx_${t}2_00 ] || ./run.sh spikes/solvereads/mk2.py $t > out/mk2_$t.log 2>&1
  run ${t}2 $t N
  run ${t}2 $t H hold=auto
done
run a_x a_x S expression=shared
run b_x b_x L hold=auto expression=view
run a_x a_x L hold=auto expression=view
echo done > out/bench_done
