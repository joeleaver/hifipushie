#!/bin/bash
# riffs.sh [names..]: the riffs on Tess's head THROUGH THE TOOL (riff.py = server.tie_hair, carry_from th_T27), each
# rendered from five sides on the shared dressed stage (iso.py). Styles in riffs.txt: <name>|<style json>
D=/mnt/data/hifipushie/tesshair3
SRC=${SRC:-th_T27}
while IFS='|' read -r n st; do
  [ -z "$n" ] && continue
  if [ $# -gt 0 ]; then case " $* " in *" $n "*) ;; *) continue;; esac; fi
  $D/run.sh riff.py th_$n tess_a1 $SRC "$st" > $D/out/riff_$n.txt 2>&1 || { echo "FAILED $n"; tail -4 $D/out/riff_$n.txt; continue; }
  grep -E "^saved|^made" $D/out/riff_$n.txt
  $D/run.sh iso.py th_$n a=base views=${VIEWS:-front,frontq,left,backl,back,right} size=560 > $D/out/riff_${n}_iso.txt 2>&1 || { echo "FAILED iso $n"; tail -4 $D/out/riff_${n}_iso.txt; }
done < $D/riffs.txt
