#!/bin/bash
# train_seg.sh <batch> <epochs> <epochs per segment> "<train.py args (no epochs / stop / resume)>"
# A stage-1 training run on NICO-TOP IN SEGMENTS, each one compute job that ends with the whole training state
# (models/<batch>/<name>/state.pth: weights, EMA, optimiser, schedule, epoch, log) + an evaluable model.pt of the EMA so
# far; the next segment's job gets that state in its folder. RESUME = RUN THE SAME COMMAND AGAIN (it reads how far the
# state got; the data list, the arguments and the code commit are fixed at the first call: models/<batch>/run.txt).
# Start it DETACHED (it must outlive the agent's shell; the client serves the files to NICO-TOP from this computer):
#    setsid nohup /mnt/data/hifipushie/denselm/train_seg.sh s30k 60 10 "name=hm18 ..." > /mnt/data/hifipushie/denselm/out/train_s30k.log 2>&1 < /dev/null &
# Progress: out/train_<batch>.log (epoch lines "step: {...}"); models/<batch>/STATUS (one line per segment);
# DONE / FAILED files in models/<batch>/. A failed segment is NOT retried (rule: a job that dies gets reported, not
# resubmitted blindly): look at models/<batch>/STATUS and the log, then run the same command again.
W=/home/joe/dev/hifipushie/.claude/worktrees/agent-a2e75a7e571826c88
D=/mnt/data/hifipushie/denselm
O=$D/offload
batch=$1; epochs=$2; seg=$3; args=$4
M=$D/models/$batch
name=$(echo "$args" | tr ' ' '\n' | grep '^name=' | cut -d= -f2); name=${name:-run0}
mkdir -p $M $O
exec 9> $M/lock; flock -n 9 || { echo "train_seg: $batch is already being driven (lock $M/lock)"; exit 1; }
rm -f $M/FAILED
if [ ! -f $M/run.txt ]; then
  dirs=$(python3 -c "
import numpy as np,glob
print(' '.join(d.split('/')[-2] for d in sorted(glob.glob('$D/data_s1/*/labels.npz')) if 'tmp' not in d and np.load(d)['xy'].shape[1]==756))")
  echo "$dirs" > $M/dirs.txt
  python3 $W/spikes/denselm/slim.py $D/data_s1 $D/data_s1_slim || exit 1
  (cd $D/data_s1_slim && tar -cf $O/${batch}_data.tar landmarks.json $dirs) || exit 1
  (cd $W && git rev-parse HEAD) > $M/commit.txt
  echo "$epochs $seg $args" > $M/run.txt
  echo "$(date '+%F %T') new run $batch: $(echo $dirs | wc -w) dressings, data $(du -h $O/${batch}_data.tar | cut -f1), commit $(cat $M/commit.txt)" | tee -a $M/STATUS
fi
read epochs seg args < $M/run.txt
export HP_REF=$(cat $M/commit.txt)
while :; do
  done_ep=$(python3 -c "
import json,os
p='$M/$name/log.json'
print(len(json.load(open(p))) if os.path.exists('$M/$name/state.pth') and os.path.exists(p) else 0)")
  if [ "$done_ep" -ge "$epochs" ]; then touch $M/DONE; echo "$(date '+%F %T') DONE: $epochs epochs; weights $M/$name/model.pt" | tee -a $M/STATUS; exit 0; fi
  stop=$((done_ep + seg)); [ $stop -gt $epochs ] && stop=$epochs
  k=e$done_ep
  J=$O/${batch}_$k/j0
  rm -rf $O/${batch}_$k; mkdir -p $J
  echo "$args epochs=$epochs stop=$stop" > $J/params.txt
  ln $O/${batch}_data.tar $J/data.tar 2>/dev/null || cp $O/${batch}_data.tar $J/data.tar
  [ -f $M/$name/state.pth ] && cp $M/$name/state.pth $J/state.pth
  echo "$(date '+%F %T') segment $k: epochs $done_ep..$((stop-1)) submitted (batch dl-${batch}$k-*)" | tee -a $M/STATUS
  (cd $O && BATCH=dl-${batch}$k-$(date +%H%M%S) TIMEOUT=${SEG_TIMEOUT:-100} $W/spikes/denselm/remote_train.sh out.tar,log.txt 12 10 ${batch}_$k/j0)
  code=$?
  R=$(ls -d $O/results/dl-${batch}$k-* 2>/dev/null | tail -1)
  if [ $code -ne 0 ] || [ -z "$R" ] || [ ! -f $R/j0/out.tar ]; then
    echo "$(date '+%F %T') segment $k FAILED (client exit $code; results ${R:-none}); not resubmitted. Resume: the same command." | tee -a $M/STATUS $M/FAILED; exit 1
  fi
  tar xf $R/j0/out.tar -C $M --strip-components=1 && cp $R/j0/log.txt $M/log_$k.txt && rm -f $R/j0/out.tar && rm -rf $O/${batch}_$k
  cp $M/$name/model.pt $M/$name/model_$k.pt
  echo "$(date '+%F %T') segment $k back: $(python3 -c "
import json
l=json.load(open('$M/$name/log.json')); v=json.load(open('$M/$name/val.json'))
print(len(l),'epochs done; held-out median mm', round(v.get('mm_median_visible',-1),2), 'mean', round(v.get('mm_visible',-1),2), 'calib', round(v.get('calib_visible',-1),2), 'dist err %', round(v.get('dist_err_pct',-1),1))")" | tee -a $M/STATUS
done
