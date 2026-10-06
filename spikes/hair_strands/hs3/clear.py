"""clear.py <model> [tiers]: card vertices under the skin per tier, as measured before the clearance fix."""
import sys, json
from hifipushie import hair, store
name = sys.argv[1]
for tier in (sys.argv[2].split(",") if len(sys.argv) > 2 else ["hero", "main", "npc", "far"]):
    spec = store.load(name)
    spec["hair"]["style"] = "cards"
    j = hair.job(name, spec, budget=tier)
    print(tier, json.dumps(j["cards"]["clearance"]))
