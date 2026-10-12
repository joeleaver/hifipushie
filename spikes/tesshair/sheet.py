"""sheet.py <out png> <title>=<model>[:cyc] ...: reference | best result (first) | earlier results. Rows: the three
reference pictures through their fitted cameras, the back from her left (beside the unfitted back picture), then two
views the pictures do not show. Tiles from shots.py ($TOUT/s_<model>_<view>[_cyc].png)."""
import os, sys, json
from PIL import Image, ImageDraw
from hifipushie import store
import hline

OUT = os.environ["TOUT"]
N = int(os.environ.get("SIZE", "512"))
out, cols = sys.argv[1], [a.split("=", 1) for a in sys.argv[2:]]
REF = "/home/joe/dev/s0urc3/docs/img/tess_ref_full"
rows = [("v0", "front (fitted camera)"), ("v1", "three-quarter left (fitted camera)"), ("v2", "left profile (fitted camera)"),
        ("backl", "back from her left (reference: unfitted picture)"), ("backq", "back from her right (not in the references)"),
        ("right", "right profile (not in the references)")]
refs = json.loads((store.HOME / cols[0][1].split(":")[0] / "human_refs.json").read_text())
HEAD = 34
sh = Image.new("RGB", (N * (1 + len(cols)), HEAD + N * len(rows)), "white")
d = ImageDraw.Draw(sh)
d.text((6, 10), "reference", fill=(0, 0, 0))
for j, (t, m) in enumerate(cols):
    d.text(((j + 1) * N + 6, 10), t + ("  << BEST" if j == 0 else ""), fill=(0, 0, 0))
for i, (v, label) in enumerate(rows):
    y = HEAD + i * N
    if v.startswith("v"):
        ref = hline.photo_tile(refs["views"][int(v[1])]["image"], N)
    elif v == "backl":
        ref = hline.photo_tile(f"{REF}/tess_head_hair_as_worn_back.png", N)
    else:
        ref = Image.new("RGB", (N, N), (235, 235, 235))
    sh.paste(ref, (0, y))
    d.text((6, y + 4), label, fill=(0, 0, 0))
    for j, (t, m) in enumerate(cols):
        m, _, eng = m.partition(":")
        f = f"{OUT}/s_{m}_{v}{'_cyc' if eng == 'cyc' else ''}.png"
        if os.path.exists(f):
            sh.paste(Image.open(f).convert("RGB").resize((N, N), Image.LANCZOS), ((j + 1) * N, y))
sh.save(out)
print(out)
