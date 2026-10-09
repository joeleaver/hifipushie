"""liptone.py: the lips layers' colour (skin.tone_rgb) for a few skin.lips settings on ll_e18's tone: does it move?"""
import json

from hifipushie import skin, store

sk = json.loads((store.HOME / "ll_e18" / "spec.json").read_text())["skin"]
t = skin.tone_params(sk.get("tone"))
for blood, mel in ((0.9, 2.6), (1.1, 3.4), (1.6, 2.6), (0.9, 5.0), (2.5, 4.0)):
    lm = 0.55 * mel
    up = skin.tone_rgb(t, melanin=lm * 1.15, blood=6.0 * blood, epidermis=0.5, oxygenation=0.62)
    lo = skin.tone_rgb(t, melanin=lm * 0.9, blood=7.0 * blood, epidermis=0.42, oxygenation=0.68)
    print(blood, mel, [round(x, 3) for x in up], [round(x, 3) for x in lo])
print("skin", [round(x, 3) for x in skin.tone_rgb(t)])
