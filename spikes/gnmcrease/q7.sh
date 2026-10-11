#!/bin/bash
cd /mnt/data/hifipushie/gnmcrease
./q.sh dress7.log dress.py ssG376=ss:/mnt/data/hifipushie/gnmcrease/out/ss_G17_376.npz@b3_G17 ssG540=ss:/mnt/data/hifipushie/gnmcrease/out/ss_G17_540.npz@b3_G17
MAKEUP='{"eyeshadow": {"amount": 0.3, "color": "#b08878", "crease": "#7a5446", "finish": "matte"}}' ./q.sh dress8.log dress.py mkT376=ss:/mnt/data/hifipushie/gnmcrease/out/ss_T30_376.npz@gd_T30 mkT540=ss:/mnt/data/hifipushie/gnmcrease/out/ss_T30_540.npz@gd_T30
