"""mk_tess.py: hs_tess = a copy of hc_tess with a strand groom (tied, loose, wavy), regrown."""
import shutil, sys, json
from pathlib import Path
from hifipushie import hair, store
src, dst = store._dir("hc_tess"), store.HOME / "hs_tess"
if not dst.exists():
    shutil.copytree(src, dst)
name = "hs_tess"
spec = store.load(name)
kw = dict(a.split("=", 1) for a in sys.argv[1:])
spec["hair"] = {
    "style": "strands",
    "groom": {
        "parting": {"side": "none"}, "hairline": {"front": 0.72, "temples": 0.004, "sideburns": 0.02, "nape": 0.0},
        "volume": {"front": 0.014, "top": 0.016, "crown": 0.016, "sides": 0.01, "back": 0.012, "nape": 0.004},
        "tie": {"at": [176, 30], "out": 0.03, "escape": int(kw.get("escape", 6)),
                "gather": {"rows": 3, "locks": 44, "lift": 0.014, "width": 0.055, "uneven": 0.6},
                "tail": {"length": 0.3, "fullness": 0.05, "locks": 18, "stiff": 0.62, "uneven": 0.6}},
        "seed": 3,
    },
    "strands": {"wave": 0.012, "wavelength": 0.08, "curl": 0.15, "flyaway": 0.3, "frizz": 0.35, "clump": 0.6,
                "under_length": 0.12, "loose": 0.4, "tips": 0.6},
    "look": {"gap": "#1c110c", "lit": "#5c3b28", "sheen": "#8a6044", "vary": 0.45, "root": 0.1, "tip_amount": 0.5},
}
store.save(name, spec, "hair: strand groom")
print(hair.groom(name, replace=True))
