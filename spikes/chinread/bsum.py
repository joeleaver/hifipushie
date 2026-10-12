"""bsum.py <log> ...: the chinread benchmark logs as one table (the start and the last call of each): |c - ct|, the face's
and the jaw / chin region's surface rms mm, then the measures' errors (mm; macros sd)."""
import re, sys
cols = ("chin_width", "jaw_width", "gonial_width", "jaw_square", "jaw_angle", "cheekbone_width", "chin_length", "chin_forward", "under_chin", "eyes_forward", "mouth_width")
print(f"{'run':16s} call |c-ct|  face jawchin  meas | " + " ".join(f"{c[:9]:>9s}" for c in cols))
for f in sys.argv[1:]:
    t = open(f).read()
    blocks = re.split(r"\n-- ", t)
    for i, blk in enumerate(blocks):
        if i not in (0, len(blocks) - 1):
            continue
        m = re.search(r"\|c - c_true\| ([0-9.]+); face surface rms ([0-9.]+) mm; jaw / chin rms ([0-9.]+) mm; measures' rms error ([0-9.]+) sd", blk)
        ch = re.search(r"chin etc \(mm\): (.*)", blk)
        if not m or not ch:
            continue
        v = dict((x.rsplit(" ", 1)[0], float(x.rsplit(" ", 1)[1])) for x in ch.group(1).split(", "))
        mx = re.search(r"largest ([0-9.]+) sd; relax x([0-9.]+)", blk)
        print(f"{f.split('/')[-1][:-4] if i else '  (start)':16s} {i:3d}  {m.group(1):>5s} {m.group(2):>5s} {m.group(3):>6s} {m.group(4):>5s} | " + " ".join(f"{v[c]:+9.1f}" for c in cols)
              + (f"   max {mx.group(1)} relax {mx.group(2)}" if mx else ""))
