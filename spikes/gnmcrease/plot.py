import glob, json
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
G = "/mnt/data/hifipushie/gnmcrease/out/"
dep, hs, dk, tp, kind = [], [], [], [], []
idx = {}
for f in sorted(glob.glob(G + "s_*_[123].npz")):
    z = np.load(f, allow_pickle=True); Gg = json.loads(str(z["geo"])); K = json.loads(str(z["clay"]))
    k = f.split("s_")[1][:-4]
    for i in range(len(Gg)):
        idx[f"{k}:{i}"] = len(dep)
        dep.append(Gg[i]["local"]); hs.append(Gg[i]["hsoft"]); dk.append(K[i]["dark"]); tp.append(K[i]["tps"]); kind.append(k.split("_")[0])
dep, hs, dk, tp = map(np.array, (dep, hs, dk, tp))
fig, ax = plt.subplots(1, 3, figsize=(16, 4.6))
for kk, col in (("gnm", "#4477aa"), ("ict", "#cc6677"), ("cls", "#228833")):
    m = np.array(kind) == kk
    ax[0].hist(dep[m], bins=40, alpha=0.5, color=col, label={"gnm": "N(0,I) 800", "ict": "ICT-led prior 400", "cls": "GNM sampler classes 400"}[kk])
for v, l in ((1.10, "Tess gd_T12 (id only)"), (1.64, "gd_T30 eye step d_line 3")):
    ax[0].axvline(v, color="k", ls="--"); ax[0].text(v, ax[0].get_ylim()[1] * 0.9, l, rotation=90, ha="right", fontsize=8)
ax[0].set_xlabel("upper-lid crease valley depth, mm (2.5 mm chord, sagittal through the pupil)"); ax[0].set_ylabel("samples"); ax[0].legend(fontsize=8)
ax[1].scatter(tp, dk, s=5, alpha=0.4, c=["#4477aa" if k == "gnm" else "#cc6677" if k == "ict" else "#228833" for k in kind])
ax[1].scatter([4.97], [0.32], marker="*", s=200, c="k"); ax[1].text(5.1, 0.33, "Tess photo")
ax[1].set_xlabel("clay-raster line height over the lashes, mm"); ax[1].set_ylabel("clay-raster line darkness (shadowless raster)")
rd = json.load(open(G + "readd.json"))
srcs = {"i140": "ict_2:140", "i157": "ict_2:157", "i170": "ict_2:170", "i308": "ict_2:308", "i339": "ict_2:339", "i347": "ict_2:347", "i76": "ict_2:76",
        "s115": "gnm_1:115", "s290": "gnm_1:290", "s319": "gnm_1:319", "s376": "gnm_1:376", "s381": "gnm_1:381", "s487": "gnm_1:487", "s540": "gnm_1:540",
        "s562": "gnm_1:562", "s650": "gnm_1:650", "s96": "gnm_1:96"}
for t, s in srcs.items():
    j = idx[s]
    ax[2].scatter(dk[j], rd[t]["dark"], c="#4477aa"); ax[2].text(dk[j], rd[t]["dark"], t, fontsize=7)
ax[2].axhline(rd["photo"]["dark"], color="k", ls="--"); ax[2].text(0.0, rd["photo"]["dark"] + 0.005, "Tess photo", fontsize=8)
ax[2].set_xlabel("clay-raster darkness (lidgnm)"); ax[2].set_ylabel("DRESSED darkness (EEVEE full-res GI, photo light)"); ax[2].set_ylim(0, 0.36)
plt.tight_layout(); plt.savefig("/home/joe/dev/hifipushie/workspace/human_renders/gk_03_crease_population.png", dpi=110)
print("ok")
