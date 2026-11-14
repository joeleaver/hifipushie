"""estep.py <src ob_*> <dst ob_*> [expression] [donor=<name>] [noorbit]: the EYE STEP (blockin_eyes.eye_step: orbit
check, opening, the lid as one structure, the eyeball guard) on a scratch model; the block-in log is rooted in the
scratch model first (never in a real model's directory). Prints the step's report."""
import json
import sys

from hifipushie import blockin as bi, blockin_eyes as be, store
from hifipushie import blockin_eyes_solve
from hifipushie import blockin_models, blockin_steps

src, dst = sys.argv[1:3]
assert src.startswith("ob_") and dst.startswith("ob_")
p = store.HOME / src / "human_refs.json"
rj = json.loads(p.read_text())
if (rj.get("blockin") or {}).get("root") != src:
    rj["blockin"] = {**(rj.get("blockin") or {}), "root": src}
    rj["blockin"].setdefault("boxes", blockin_models._boxes(store.load(src)["base"], rj))
    p.write_text(json.dumps(rj, indent=1))
    (store.HOME / src / "blockin_log.json").write_text(json.dumps([{"round": 0, "to": src, "start": {"adopted": "orbit scratch"}}]))
donor = next((a.split("=")[1] for a in sys.argv[3:] if a.startswith("donor=")), None)
lines = []
rep = blockin_eyes_solve.eye_step(src, out=dst, log=lambda s: (lines.append(s), print(s, flush=True)), expression="expression" in sys.argv,
                  donor=donor, orbit="noorbit" not in sys.argv)
print(blockin_steps.step_text(rep))
print(blockin_eyes_solve.text(rep["eyes"]))
