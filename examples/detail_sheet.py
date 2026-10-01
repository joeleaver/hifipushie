"""Side-by-side sheet of detail_round's variants for one view, labelled with each variant's bake cost.
uv run python examples/detail_sheet.py <round dir> <terrain> <pass> <view png name> <out png> <variant ...>"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

LABEL = {"u": "unique maps {d:g}/m", "m": "macro {d:g}/m + tiling detail"}


def main():
    rd, name, ps, view, out = Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
    variants = sys.argv[6:]
    costs = json.loads((rd / "costs.json").read_text())
    ims = [Image.open(rd / f"{name}_{ps}_{v}" / view).convert("RGB") for v in variants]
    w, h = ims[0].size
    sc = 0.5 if len(ims) > 2 else 0.75
    W, H = int(w * sc), int(h * sc)
    sheet = Image.new("RGB", (W * len(ims), H + 46), (20, 20, 20))
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 15)
    except OSError:
        font = ImageFont.load_default()
    for k, (v, im) in enumerate(zip(variants, ims)):
        sheet.paste(im.resize((W, H), Image.LANCZOS), (k * W, 46))
        c = costs.get(f"{name}_{ps}_{v}", {})
        used = (c.get("density") or [float(v[1:])])[0]
        d.text((k * W + 8, 4), LABEL[v[0]].format(d=round(used, 1)), fill=(255, 255, 255), font=font)
        d.text((k * W + 8, 24), f"{c.get('texels', 0) / 1e6:.2f}M texels, bake {c.get('bake_cpu_s', 0):.0f} CPU s",
               fill=(200, 200, 200), font=font)
    sheet.save(out)


if __name__ == "__main__":
    main()
