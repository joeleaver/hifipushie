"""shared.py: every th_* model has tess_a1's head, so they all use ONE dressed stage (the stage of $STAGE_MODEL,
default th_T66) wearing the model's own hair, instead of a 53 s sync and a scene.blend each. `patch()` swaps
stage.ensure for that; `run(script)` then runs a spikes/tesshair script (shots.py, hs.py, hline.py) unchanged."""
import copy, json, os, runpy, sys
import stage
from hifipushie import store

_ensure = stage.ensure
W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ensure(name, with_hair=True, log=print, posed=False, tex=None):
    if not str(name).startswith("th_") or posed or tex is not None:
        return _ensure(name, with_hair=with_hair, log=log, posed=posed, tex=tex)
    sn = _ensure(os.environ.get("STAGE_MODEL", "th_T66"), log=log)
    spec = store.load(name)
    f = store._dir(sn) / "spec.json"
    st = json.loads(f.read_text())
    st["hair"] = copy.deepcopy(spec["hair"])
    f.write_text(json.dumps(st))
    return sn


def patch():
    stage.ensure = ensure


def run(script):
    patch()
    p = f"{W}/tesshair/{script}"
    sys.argv = [p] + sys.argv[1:]
    runpy.run_path(p, run_name="__main__")
