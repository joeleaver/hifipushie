"""items.py <model> <item,...>: likeness.compare's photo / model values of the named items, every view."""
import sys

from hifipushie import likeness, store

name, ids = sys.argv[1], sys.argv[2].split(",")
import os
for r in likeness.compare(name, store.load(name)["base"], points_from=os.environ.get("PF"))["rows"]:
    if r["id"] in ids:
        f = lambda x: round(x, 3) if isinstance(x, float) else x  # noqa: E731
        print(r["id"], "view", r["vi"], "photo", f(r.get("photo")), "model", f(r.get("model")), "score", round(r["score"], 2),
              r.get("why", ""), r.get("expression", ""))
