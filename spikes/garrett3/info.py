"""info.py <model> ...: evidence residual through both references (this head's own best cameras), plausibility,
strongest macros (structure.info), and a pose.json reset to {} when asked: info.py <model> nopose."""
import sys

import structure
from hifipushie import store

for name in [a for a in sys.argv[1:] if a != "nopose"]:
    structure.info(name, store.load(name)["base"])
    if "nopose" in sys.argv:
        (store.HOME / name / "pose.json").write_text("{}")
