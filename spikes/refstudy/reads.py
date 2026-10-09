"""Blind reads of the six-view sheets: `form` writes the form; `store <model> <tag> <json>...` stores readers'
answers ({"views": {view: {"descriptors": {id: {"confidence": ..}}}}}) on the model (with lk_garrett5's reference
reads copied in) and prints the diff against the reference read."""
import json
import sys

import rs
from hifipushie import likeness_read as lr, store

if sys.argv[1] == "form":
    (rs.D / "out" / "read_form.txt").write_text(lr.form())
    print(lr.form()[:3000])
else:
    name, tag = sys.argv[2], sys.argv[3]
    src = json.loads((store.HOME / "lk_garrett5" / lr.READ).read_text())
    dst_f = store.HOME / name / lr.READ
    dst = json.loads(dst_f.read_text()) if dst_f.exists() else {"format": src.get("format"), "reads": {}}
    for k in ("reference", "reference_by"):
        if k in src["reads"]:
            dst["reads"][k] = src["reads"][k]
    for i, f in enumerate(sys.argv[4:]):
        r = json.loads(open(f).read())
        dst["reads"][f"{tag}_r{i + 1}"] = r
    dst_f.write_text(json.dumps(dst, indent=1))
    for i in range(len(sys.argv[4:])):
        print(f"--- reader {i + 1}")
        print(lr.diff(name, f"{tag}_r{i + 1}"))
    if len(sys.argv[4:]) > 1:
        print(lr.agreement(name, [f"{tag}_r{i + 1}" for i in range(len(sys.argv[4:]))]))
