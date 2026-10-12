"""sheet_rows.py <out.png> <title> <new model> <old model> <new label> <old label> <row label>=<tile> ...: a sheet
REFERENCE | new | current, one row per <tile> (shots.py's names, e.g. face_v0, eyes_v1; a tile with no reference
picture shows "(no picture)"), LARGE labels. [tile=N] first among the rows sets the tile size."""
import os
import sys

from strip import row, stack

O = "/mnt/data/hifipushie/gnmnative/out"
out, title, new, old, nl, ol = sys.argv[1:7]
rows = sys.argv[7:]
T = 520
if rows and rows[0].startswith("tile="):
    T = int(rows.pop(0)[5:])


def t(m, f):
    p = f"{O}/{m}/{f}.png"
    return p if os.path.exists(p) else None


R = []
for k, a in enumerate(rows):
    lab, tile = a.split("=", 1)
    nm, om = new, old
    if ":" in tile:      # <tile>:<new model>:<old model>[:<reference picture>] (a posed fork for this row)
        parts = tile.split(":")
        tile, nm, om = parts[0], parts[1], parts[2]
        ref = parts[3] if len(parts) > 3 and parts[3] else None
    else:
        ref = t(new, tile + "_ref")
    R.append(row([(("REFERENCE: " if k == 0 else "") + lab, ref), (nl if k == 0 else "", t(nm, tile)), (ol if k == 0 else "", t(om, tile))], T))
os.makedirs(os.path.dirname(out), exist_ok=True)
stack(R, title, fs=44).save(out)
print(out)
