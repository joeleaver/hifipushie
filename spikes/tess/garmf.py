"""garmf.py <model> <garment> <json file {"design", "spec"}>: the garment's design sheet onto the model, then the checks
($STAGES, default pattern,construction,place; images $T/out/<model>_<garment>*)."""
import json, os, sys
from hifipushie import server

name, g, f = sys.argv[1:4]
d = json.load(open(f))
r = server.design_garment(name, g, design=d["design"], spec=d["spec"], note=f"tess2: {g} design sheet ({os.path.basename(f)})")
print(r if isinstance(r, str) else "\n".join(x for x in r if isinstance(x, str)))
r = server.check_garment(name, g, stages=os.environ.get("STAGES", "pattern,construction,place").split(","),
                         save=os.path.join(os.environ["T"], "out", f"{name}_{g}.png"))
print(r if isinstance(r, str) else "\n".join(x for x in r if isinstance(x, str))[:8000])
