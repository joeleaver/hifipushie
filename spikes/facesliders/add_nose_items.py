"""add_nose_items.py: the nose's dorsal widths as checklist items (likeness.json, kind "shape": the side wall's shading
a few mm off the dorsal line against the dorsum's own, the photo against the model lit like it), after nose_width.
Rewrites likeness.json with its own one-space indent."""
import json
from pathlib import Path

p = Path("/home/joe/dev/hifipushie/.claude/worktrees/agent-abc45e5f0969ff6fa/src/hifipushie/likeness.json")
d = json.loads(p.read_text())
have = {i["id"] for i in d["items"]}
rel = ("shading: the side wall's shade off the dorsal line against the dorsum's (likeness_shape), the photo against the "
       "model lit like it; a wider dorsum keeps the side wall lit further out. faceslide.nose_widths reads the same as mm")
new = [
    {"id": "radix_width", "name": "Nasal root width (between the eyes)", "region": "nose", "stage": "nose",
     "look": "How broad the bridge is between the inner corners: a narrow pinched root or a broad flat one.",
     "views": ["front"], "measure": {"kind": "shape", "region": {"at": 168, "dx_mm": 6, "r_mm": 2},
                                     "ref": {"at": 168, "r_mm": 2}}, "unit": "%", "tol": 8.0,
     "control": "sliders.nose_radix_width", "reliability": rel},
    {"id": "dorsum_width", "name": "Nasal dorsum width (the middle of the nose)", "region": "nose", "stage": "nose",
     "look": "How wide the bony / cartilage vault reads partway down, between the two dorsal lines of light and shade.",
     "views": ["front"], "measure": {"kind": "shape", "region": {"from": 6, "to": 4, "t": 0.5, "dx_mm": 5, "r_mm": 2},
                                     "ref": {"from": 6, "to": 4, "t": 0.5, "r_mm": 2}}, "unit": "%", "tol": 8.0,
     "control": "sliders.nose_dorsum_width", "reliability": rel},
]
lines = p.read_text().split("\n")
k = next(j for j, ln in enumerate(lines) if '"id": "nose_length"' in ln)
assert lines[k].rstrip().endswith(","), "nose_length isn't followed by another item"
add = ["  " + json.dumps(it, ensure_ascii=False) + "," for it in new if it["id"] not in have]
lines[k + 1:k + 1] = add
p.write_text("\n".join(lines))
json.loads(p.read_text())  # (still valid)
print("added", len(add))
