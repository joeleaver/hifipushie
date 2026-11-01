#!/bin/bash
# hsrd_pull.sh <person> <pose> [keep]: ONE HSRD-100 pose into the real-photo set: download (LOD0 scan, photos +
# masks + .xmp; the RealityCapture project is not needed), verify, working copy, scan -> rig registration, the Part 1
# fits, export (hsrd_export.py), then DELETE the download and the working copy (keep = leave them). Stops when
# /mnt/data has under MINFREE GB (default 60). Resumable: a pose with summary.json is skipped.
#   RUN = how a light python job starts (default the groundtruth slot wrapper); the scan's read runs capped at 10 GB.
set -e
# a pose that FAILS leaves nothing behind but its log (the next pose must not find the disk full of leftovers)
trap 'rc=$?; if [ $rc != 0 ] && [ $rc != 3 ] && [ -n "$p" ]; then rm -rf $D/dl/$p $D/x/$p $R/work/$p $D/$person/$p; fi' EXIT
R=${HIFIPUSHIE_GROUNDTRUTH:-/mnt/data/hifipushie/groundtruth}
G=$(cd "$(dirname "$0")" && pwd)
person=$1; p=$2
D=$R/hsrd100
[ -f $D/$person/$p/summary.json ] && { echo "$p: already in the set"; exit 0; }
rm -rf $D/$person/$p            # a half-written pose (no summary.json: an export that was cut off) starts clean
free=$(df -BG --output=avail $R | tail -1 | tr -dc 0-9)
[ "$free" -lt "${MINFREE:-60}" ] && { echo "STOP: $free GB free on the data disk (under ${MINFREE:-60})"; exit 3; }
# (bin/slot starves a serial job while other queues refill every freed slot at once: 24 min waiting for the first step;
# so this ONE serial job runs its solves outside the slots too: single thread, 6 GB cap, niced)
RUN=${RUN:-env CAP=6G OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 /mnt/data/hifipushie/bin/capped nice -n 10 uv run python}
# mesh reading / cutting / the export are not solves: ONE at a time (this script is serial), capped, niced, outside the light slots
MESH=${MESH:-env CAP=10G OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 /mnt/data/hifipushie/bin/capped nice -n 10 uv run python}
B=https://huggingface.co/datasets/digitalrealitylab/HSRD-100/resolve/main/data/$person/$p
mkdir -p $D/dl/$p $D/x/$p/photos $D/x/$p/scan
cd $D/dl/$p
for f in scans/$p-Scan-LOD0.zip source/$p-Photos.zip metadata/pose_meta.json metadata/person_meta.json; do
  [ -s $(basename $f) ] || curl -sL -C - --retry 5 -o $(basename $f) $B/$f
done
unzip -tq $p-Scan-LOD0.zip > /dev/null && unzip -tq $p-Photos.zip > /dev/null
sha256sum *.zip *.json > SHA256SUMS
unzip -q -o $p-Photos.zip -d $D/x/$p/photos
unzip -q -o $p-Scan-LOD0.zip -d $D/x/$p/scan
. $R/env.sh; cd $G/../..
$MESH $G/prep.py hsrd $p
ok=0
for turn in 180 0 90 270; do
  if $RUN $G/align0.py $p turn=$turn | tee /dev/stderr | grep -q "landmark residual"; then ok=1; break; fi
done
[ $ok = 1 ] || { echo "$p: no face found on the scan's front picture at any turn"; exit 4; }
$RUN $G/register.py $p
$RUN $G/fit3d.py $p prior=1 cmax=3
$RUN $G/fit3d.py $p prior=1 cmax=3 expr=1
$MESH $G/hsrd_export.py $p
mkdir -p $D/$person/$p
cp $D/dl/$p/SHA256SUMS $D/dl/$p/pose_meta.json $D/dl/$p/person_meta.json $D/$person/$p/
cp $R/out/register_$p.png $D/$person/$p/register_check.png 2>/dev/null || true
if [ "$3" != keep ]; then rm -rf $D/dl/$p $D/x/$p $R/work/$p; fi
$RUN $G/hsrd_index.py > $R/out/hsrd_set.md 2>&1 || true      # index.json is rewritten after EVERY finished pose
echo "done $p"
