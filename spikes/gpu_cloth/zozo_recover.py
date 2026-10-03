"""zozo_recover.py <ZOZO session dir> <job sim dir> [snap every]: out.npz from a finished ZOZO session's vert_N.bin files
(float32 rows; the garment matched on frame 0), for when run_zozo.py died after the sim (the session dir is
<ppf>/local/share/ppf-cts/git-unknown/hp_<model>_<job>/session)."""
import json, sys
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
sd, jd = Path(sys.argv[1]), Path(sys.argv[2])
every = int(sys.argv[3]) if len(sys.argv) > 3 else 24
d = np.load(jd / "in.npz"); X = d["X"]; n = len(X)
frames = sorted(int(p.stem.split("_")[1]) for p in (sd / "output").glob("vert_*.bin"))
load = lambda f: np.fromfile(sd / "output" / f"vert_{f}.bin", np.float32).reshape(-1, 3).astype(float)
F0 = load(0)
if np.abs(F0[:n] - X).max() < 1e-4:
    rows = np.arange(n)
else:
    dd, rows = cKDTree(F0).query(X)
    assert dd.max() < 1e-4, dd.max()
out = {"V": load(frames[-1])[rows]}
for f in frames:
    if f and f % every == 0 and f != frames[-1]:
        out[f"S{f}"] = load(f)[rows]
np.savez(jd / "out.npz", **out, log=np.array([f"recovered from {sd}: {frames[-1]} frames"]))
print("frames", frames[-1], "rows", "direct" if rows[0] == 0 and rows[-1] == n - 1 else "matched")
