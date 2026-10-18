"""count.py <review.md>...: MAJORs by scope with ONE fixed rule set (successor 17), so rounds compare.
Classifies each MAJOR by its first sentence; order: skin (OTHER STAGES), strand-render, direction, colour, shape."""
import re, sys
R = [("strand", r"noise|speckl|grit|stucco|felt|carpet|smear|brushstroke|stubble|spiky|clumped"),
     ("direction", r"comb|swirl|fan(s|ning)? out|stripe|sweep|whorl|spoke"),
     ("colour", r"colou?r|light|white|silver|dark|blotch|seam|band|beige|charcoal|tone|patch")]
def classify(s):
    first = re.split(r"(?<=[.!?])\s|\*\*\s", re.sub(r"^\d+\.\s*|\*\*MAJOR[:,]?\*\*:?|\*\*MAJOR[:,]?\s*", "", s).strip(), maxsplit=1)[0].lower()
    for k, rx in R:
        if re.search(rx, first): return k, first
    return "shape", first
for f in sys.argv[1:]:
    other = False; c = {"shape": 0, "colour": 0, "direction": 0, "strand": 0, "skin": 0}; rows = []
    for ln in open(f):
        if ln.startswith("## "): other = "OTHER" in ln.upper()
        if "MAJOR" not in ln: continue
        if other: c["skin"] += 1; continue
        k, first = classify(ln); c[k] += 1; rows.append((k, first[:90]))
    print(f, " ".join(f"{k} {v}" for k, v in c.items()), "| hair", sum(v for k, v in c.items() if k != "skin"))
    if "-v" in sys.argv[0:1] or len(sys.argv) == 2:
        for r in rows: print("   ", *r)
