#!/bin/bash
# Snyder et al. 1977 (UMTRI-77-17, for the CPSC), "Anthropometry of Infants, Children and Youths to Age 18", as
# published by NIST AnthroKids (US government work, public domain)
D=/home/joe/dev/hifipushie/workspace/skin_refs/ages/snyder1977
mkdir -p $D; cd $D
UA="Mozilla/5.0 (X11; Linux x86_64) Chrome/126"
B="https://math.nist.gov/~SRessler/anthrokids/data1977"
T="61:weight 65:stature 97:sitting_height 145:head_circ 149:head_breadth 153:head_length 157:bizygomatic 165:lower_face_height 169:face_height 173:head_height 193:mouth_breadth 197:nose_length 201:neck_circ 205:neck_breadth 213:shoulder_breadth 217:biacromial 221:shoulder_elbow 237:elbow_hand 229:upper_arm_circ 261:hand_length 265:hand_breadth 317:suprasternale_height 325:chest_circ 329:chest_breadth 333:waist_height 337:waist_circ 357:hip_circ 361:hip_breadth 373:gluteal_furrow_height 377:trochanteric_height 381:upper_thigh_circ 389:tibiale_height 397:calf_circ 417:foot_length 421:foot_breadth"
for t in $T; do
  n=${t%%:*}; name=${t##*:}; m=$((n+2))
  curl -sL --max-time 40 -A "$UA" -o ${name}_all.csv "$B/$n.csv"
  curl -sL --max-time 40 -A "$UA" -o ${name}_f.csv "$B/${m}f.csv"
  curl -sL --max-time 40 -A "$UA" -o ${name}_m.csv "$B/${m}m.csv"
done
I="554:weight 555:crown_sole 556:crown_rump 557:head_circ 558:head_breadth 559:head_length 560:shoulder_breadth 561:shoulder_elbow 563:elbow_hand 566:hand_length 572:chest_circ 573:chest_breadth 574:waist_circ 576:rump_sole 577:rump_knee 578:hip_circ 579:hip_breadth 580:mid_thigh_circ 582:knee_sole 583:calf_circ 586:foot_length"
for t in $I; do
  n=${t%%:*}; name=${t##*:}
  curl -sL --max-time 40 -A "$UA" -o infant_${name}.csv "$B/$n.csv"
done
ls | wc -l; file stature_all.csv; head -12 stature_all.csv; head -8 infant_crown_sole.csv; grep -l -i "<html" *.csv | head
