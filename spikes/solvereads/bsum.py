"""bsum.py [log ...]: the benchmark's logs (chain.py with truth=) as one table: per run and call |dc|, the
down-weighting, |c - c_true|, the face's surface rms mm, the measures' rms error (sd), a few measures' errors (mm)."""
import glob, re, sys
logs = sys.argv[1:] or sorted(glob.glob("/mnt/data/hifipushie/solvereads/out/bench_*.log"))
print("run            call  |dc|   relax  |c-ct|  face mm  meas sd | pogonion chin_fwd chin_len chin_wid jaw_wid under_chin mentolab eyes_fwd brow_ridge mouth_w")
for f in logs:
    t = open(f).read()
    name = f.split("bench_")[-1][:-4]
    calls = re.split(r"\n-- ", t)
    rows = []
    for i, blk in enumerate(calls):
        m = re.search(r"\|c - c_true\| ([0-9.]+); face surface rms ([0-9.]+) mm.*?rms error ([0-9.]+) sd", blk)
        if not m:
            continue
        ch = re.search(r"chin etc \(mm\): (.*)", blk)
        vals = [float(x.split()[-1]) for x in ch.group(1).split(", ")] if ch else []
        d = re.search(r"\|dc\| ([0-9.]+)", blk) if i else None
        rx = re.search(r"relax x([0-9.]+)( DAMPED)?", blk) if i else None
        rows.append((i, d.group(1) if d else "-", (rx.group(1) + ("d" if rx.group(2) else "")) if rx else "-", m.group(1), m.group(2), m.group(3), vals))
    for i, d, rx, a, b, c, vals in rows:
        print(f"{name if i == rows[0][0] else '':14s} {i:3d}  {d:>5s}  {rx:>6s}  {a:>5s}   {b:>5s}    {c:>5s}  | " + " ".join(f"{v:+7.1f}" for v in vals))
    ex = re.findall(r"expression (\w+): (.*)", calls[-1]) if len(calls) > 1 else []
    for pc, s in ex:
        print(f"{'':14s} expression {pc}: {s}")
