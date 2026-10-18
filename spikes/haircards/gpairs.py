"""gpairs.py <out dir> <tag>: game-distance review pairs at native pixels: photo | cards (v views) and
strand groom | cards (back), 1 m and 3 m; writes args.txt for rv.sh."""
import sys, os
from PIL import Image
o, t = sys.argv[1:3]; os.makedirs(o, exist_ok=True)
G = sys.argv[3] if len(sys.argv) > 3 else "/mnt/data/hifipushie/haircards/game/gm_g1.png"
im = Image.open(G)
# cell geometry of gsheet.py: pad 8, label 18; 1 m cells 540, 3 m cells 180; columns photo?, gS, gb15, gb15b, gb14a
def cell(row, col, big):
    s = 540 if big else 180
    y = 8 + row * (540 + 26) + 18 if big else 8 + 4 * 566 + (row - 4) * (180 + 26) + 18
    x = 8 + col * (s + 8)
    return im.crop((x, y, x + s, y + s))
col = int(sys.argv[4]) if len(sys.argv) > 4 else {"gb15": 2, "gb15b": 3, "gb14a": 4}[t]  # sheet column (photo = 0)
items = [("front, 1 m", 0, 0, True), ("three-quarter, 1 m", 1, 0, True), ("profile, 1 m", 2, 0, True),
         ("back three-quarter, 1 m (reference: strand groom)", 3, None, True), ("front, 3 m", 4, 0, False),
         ("back three-quarter, 3 m (reference: strand groom)", 5, None, False)]
args = []
for i, (n, r, rc, big) in enumerate(items):
    if rc is None:  # back rows have no photo column: gS is column 0, cards one left
        ref, res = cell(r, 0, big), cell(r, col - 1, big)
    else:
        ref, res = cell(r, rc, big), cell(r, col, big)
    ref.save(f"{o}/{i}_ref.png"); res.save(f"{o}/{i}_res.png")
    args.append(f'"{n}={o}/{i}_ref.png:{o}/{i}_res.png"')
open(f"{o}/args.txt", "w").write(" ".join(args))
