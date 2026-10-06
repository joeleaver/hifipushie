"""golfer.py <out.png> [k=v strands]: matched-camera sheet for the golfer: solid locks | strands | reference, with
the gates on each."""
import json, os, sys
from pathlib import Path
from PIL import Image, ImageDraw
from hifipushie import hair, store
name, out = "hs_golfer", sys.argv[1]
S = {"clump": 0.9, "clump_size": 0.012, "clump_shape": 0.3, "tip_spread": 0.1, "loose": 0.12, "frizz": 0.15,
     "flyaway": 0.05, "tips": 0.3, "flat": 1.6, "roots": 0.2, "under_length": 0.03, "wave": 0.0}
for a in sys.argv[2:]:
    k, v = a.split("=", 1)
    S[k] = json.loads(v)
size = 420
rows, text = [], []
for style in ("locks", "strands"):
    spec = store.load(name)
    spec["hair"]["style"] = style
    if style == "strands":
        spec["hair"]["strands"] = S
    hair.validate(spec)
    sheet, sec, fr = hair.look(name, views=("front", "three_quarter", "side", "back"), size=size, spec=spec, clay=False)
    rows.append(sheet)
    f = hair.look.fit or {}
    g = hair.look.gate or {}
    line = (f"{style}: {sec}s  IoU {f.get('iou')}  part {f.get('part_px')} px  flow err {f.get('clump_dir_deg')} deg  "
            f"bare {hair.look.mass_share.get('matched')} (front {hair.look.mass_share.get('front')})  "
            f"gate front L/R {g.get('front', {}).get('left')}/{g.get('front', {}).get('right')} mm, 3/4 {g.get('three_quarter', {}).get('left')} mm  pass {g.get('pass')}")
    text.append(line)
    print(line)
    print("  fit", {k: v for k, v in f.items() if k not in ("clumps", "regions", "front_edge", "front_flow")})
    fe = f.get("front_edge") or {}
    print("  front_edge", {k: fe.get(k) for k in ("rough_mm", "tooth_mm")}, "regions", {k: v.get("err") for k, v in (f.get("regions") or {}).items()})
W = max(r.width for r in rows)
img = Image.new("RGB", (W, sum(r.height for r in rows) + 18 * len(rows)), (30, 31, 35))
d = ImageDraw.Draw(img)
y = 0
for r, t in zip(rows, text):
    d.text((6, y + 3), t, fill=(240, 220, 160))
    img.paste(r, (0, y + 18))
    y += r.height + 18
img.save(os.path.join(os.environ["HR"], out))
