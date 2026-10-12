"""nullstart.py <start model> <truth model> <name>: the benchmark's NULL: a block-in start on the benchmark's pictures whose
head already IS the truth (blockin.fork of the class-mean start, identity = the truth's), the prior still centred on the
class-mean start (blockin.root). A solve from here should stay: where it goes is the reads' own bias."""
import json, sys
from hifipushie import blockin as bi, store
src, truth, name = sys.argv[1:4]
bi.fork(src, name, replace=True)
sp = store.load(name)
bi.set_identity(sp, bi.identity(store.load(truth)))
(store.HOME / name / "spec.json").write_text(json.dumps(sp))
p = store.HOME / name / "human_refs.json"
rj = json.loads(p.read_text())
rj["blockin"]["root"] = src
p.write_text(json.dumps(rj))
print(name, "identity of", truth, "root", src)
