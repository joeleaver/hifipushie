#!/bin/bash
# hsrd_resume.sh [list file]: resume the HSRD-100 pull. Poses already in the set (summary.json) are skipped, a
# half-written pose directory is removed and redone, a half-downloaded archive is continued (curl -C -) and checked
# (unzip -t), originals and the working copy are deleted after each pose, index.json is rewritten after each pose.
# Stops by itself under 60 GB free on the data disk (MINFREE). One pose at a time, ~7 min each. Log per pose:
# $HIFIPUSHIE_GROUNDTRUTH/out/pull/<pose>.log; one line per finished pose: out/pull_resume.log.
R=${HIFIPUSHIE_GROUNDTRUTH:-/mnt/data/hifipushie/groundtruth}
G=$(cd "$(dirname "$0")" && pwd)
L=${1:-$G/hsrd_poses.txt}
mkdir -p $R/out/pull
pgrep -f "hsrd_pull.sh HSR" > /dev/null && { echo "a pull is already running (pgrep -f 'hsrd_pull.sh HSR'): not starting a second one"; exit 1; }
while read person pose keep; do
  case "$person" in ''|\#*) continue;; esac
  rm -rf $R/hsrd100/x/$pose $R/work/$pose          # a cut-off run's unpacked files / working copy: redo from the archives
  $G/hsrd_pull.sh $person $pose $keep > $R/out/pull/$pose.log 2>&1
  rc=$?
  echo "$(date +%F\ %H:%M) $pose rc=$rc $(tail -1 $R/out/pull/$pose.log | cut -c1-200)" >> $R/out/pull_resume.log
  [ $rc = 3 ] && break
done < "$L"
echo "$(date +%F\ %H:%M) list finished" >> $R/out/pull_resume.log
