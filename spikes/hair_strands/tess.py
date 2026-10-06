"""tess.py [style] : give hc_tess a tied, wavy groom and save it."""
import sys
from hifipushie import hair, store

name = "hc_tess"
spec = store.load(name)
style = sys.argv[1] if len(sys.argv) > 1 else "cards"
FRONT = float(sys.argv[2]) if len(sys.argv) > 2 else 0.72
spec["hair"] = {
    "style": style,
    "groom": {
        "hairline": {"front": FRONT, "temples": 0.004, "sideburns": 0.02, "nape": 0.0},
        "volume": {"front": 0.014, "top": 0.016, "crown": 0.016, "sides": 0.01, "back": 0.012, "nape": 0.004},
        "tie": {"at": [176, 22], "out": 0.03, "escape": 8,
                "gather": {"rows": 3, "locks": 34, "lift": 0.014, "width": 0.055, "uneven": 0.6},
                "tail": {"length": 0.3, "fullness": 0.05, "locks": 18, "stiff": 0.5, "uneven": 0.6}},
        "seed": 3,
    },
    "strands": {"wave": 0.007, "wavelength": 0.075, "curl": 0.35, "flyaway": 0.3, "layers": 3, "frizz": 0.35,
                "clump": 0.6},
    "look": {"gap": "#1c110c", "lit": "#5c3b28", "sheen": "#8a6044", "vary": 0.3, "root": 0.1, "tip_amount": 0.5},
}
store.save(name, spec, "hair: tied wavy groom")
print(hair.groom(name))
