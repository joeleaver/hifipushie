"""calib.py: the dressed line's height (readd.json, lidfold.read_lid on the face frame at the photo's mm/px) vs the geometric
crease (col.py, mid column and middle-5 mean) over the dressed samples."""
import json
import numpy as np
import col

G = "/mnt/data/hifipushie/gnmcrease/out/"
rd = json.load(open(G + "readd.json"))
SRC = {"i140": "ict_2:140", "i157": "ict_2:157", "i170": "ict_2:170", "i308": "ict_2:308", "i339": "ict_2:339", "i347": "ict_2:347",
       "i76": "ict_2:76", "s115": "gnm_1:115", "s290": "gnm_1:290", "s319": "gnm_1:319", "s376": "gnm_1:376", "s381": "gnm_1:381",
       "s487": "gnm_1:487", "s540": "gnm_1:540", "s562": "gnm_1:562", "s650": "gnm_1:650", "s96": "gnm_1:96",
       "t12": "model:gd_T12", "t30": "model:gd_T30"}
X, Y = [], []
for t, s in SRC.items():
    c, e, _ = col.src(s)
    cols = col.columns(c, e)
    sm = col.summary(cols)
    hm = float(np.nanmedian([q["h"] for q in cols[1:6] if q]))
    print(f"{t:5s} geo h_mid {sm['h_mid']:.2f} median5 {hm:.2f} narrow {sm['narrow_mean']:.2f} show {sm['show_mid']:.2f} brow {sm['brow_mid']:.2f} "
          f"h/brow {sm['h_over_brow']:.2f} | dressed line {rd[t]['tps']:.2f} dark {rd[t]['dark']:.2f} width {rd[t]['width']:.2f}")
    X.append(hm); Y.append(rd[t]["tps"])
X, Y = np.array(X), np.array(Y)
ok = (X < 7) & (Y < 7)
a, b = np.polyfit(X[ok], Y[ok], 1)
print(f"dressed line ~ {a:.2f} * geo + {b:.2f} (n {ok.sum()}, r {np.corrcoef(X[ok], Y[ok])[0, 1]:.2f}); photo 4.97 -> geo {(4.97 - b) / a:.2f}")
