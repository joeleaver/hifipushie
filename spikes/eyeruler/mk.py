"""mk.py <src> <dst> '<json patch>': a scratch copy of a model with a deep-merged patch (null removes a key);
"__noexpr": true clears base.head.expression. Never touches the source."""
import copy
import json
import shutil
import sys

from hifipushie import store


def merge(a, b):
    for k, v in b.items():
        if v is None:
            a.pop(k, None)
        elif isinstance(v, dict) and isinstance(a.get(k), dict):
            merge(a[k], v)
        else:
            a[k] = v
    return a


def write(dst, sp, src):
    assert dst.startswith("er_"), "scratch models are er_*"
    d = store._dir(dst)
    d.mkdir(parents=True, exist_ok=True)
    (d / "spec.json").write_text(json.dumps(sp))
    shutil.copy(store._dir(src) / "human_refs.json", d / "human_refs.json")


if __name__ == "__main__":
    src, dst, patch = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
    sp = copy.deepcopy(store.load(src))
    sp.pop("hair", None)
    if patch.pop("__noexpr", False):
        sp["base"]["head"].pop("expression", None)
    merge(sp, patch)
    write(dst, sp, src)
    print("wrote", dst)
