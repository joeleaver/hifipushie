"""diag.py <model> <export dir> <out prefix> [tiers=hero,main,npc,far] [size=400] [export=1]: export the card tiers
and judge them as an engine gets them (hair.check_tiers): sheet + numbers."""
import json, os, sys, time
from pathlib import Path
from hifipushie import hair

name, out_dir, prefix = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
kw = dict(a.split("=", 1) for a in sys.argv[4:])
tiers = kw.get("tiers", "hero,main,npc,far").split(",")
HR = Path(os.environ["HR"])
t0 = time.time()
if int(kw.get("export", 1)):
    rep = hair.export_hair(name, out_dir, tiers=tuple(tiers), groom=False)
    print("export", round(time.time() - t0, 1), "s")
chk = hair.check_tiers(name, out_dir, tiers=tiers, save=str(HR / f"{prefix}.png"), size=int(kw.get("size", 400)),
                       solid=bool(int(kw.get("solid", 1))))
(HR / f"{prefix}.json").write_text(json.dumps(chk, indent=1, default=float))
print(hair.tiers_text(chk))
for t, r in chk["tiers"].items():
    print(t, r["budget"], r["layers"])
print("total", round(time.time() - t0, 1), "s")
