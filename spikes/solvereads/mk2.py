"""mk2.py <tag>: the benchmark head sx_<tag> from its FRONT and 3/4 pictures only (no side view: the paintings' case):
sx_<tag>2_R (holder) and the class-mean start sx_<tag>2_00; scored against the same truth sx_<tag>_T."""
import copy, json, sys
from hifipushie import blockin as bi, server, store
tag = sys.argv[1]
S = "/mnt/data/hifipushie/solvereads/synth"
src = f"sx_{tag}_R"
rj = bi._refs(src)
holder = f"sx_{tag}2_R"
d = store._dir(holder); d.mkdir(parents=True, exist_ok=True)
(d / "spec.json").write_text(json.dumps(store.load(src)))
(d / "human_refs.json").write_text(json.dumps({"views": copy.deepcopy(rj["views"][:2]), "cameras": [None, None]}))
r = server.block_in_start(f"sx_{tag}2_00", holder, sex="male", age=52, cameras="refit", replace=True, save=f"{S}/sx_{tag}2_00.png")
print("\n".join(x for x in r if isinstance(x, str))[-600:])
