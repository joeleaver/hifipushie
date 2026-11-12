"""nobag.py <model> <copy> <out dir> ref= own=: cu.py on a copy of <model> rendered with the skin's mouth_bag layer OFF (a test)."""
import copy, runpy, sys
from hifipushie import blockin as bi, skin_features, store
from hifipushie import blockin_models, skin_features_mouth
m, cp, out = sys.argv[1:4]
s = copy.deepcopy(store.load(m))
rj = copy.deepcopy(blockin_models._refs(m))
blockin_models._save(cp, s, f"{m}: test copy (mouth bag off)", rj)
skin_features_mouth._gnm_mouth = lambda *a, **k: None
sys.argv = ["cu.py", cp, out] + sys.argv[4:]
runpy.run_path("spikes/projskin/cu.py", run_name="__main__")
