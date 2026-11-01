import sys, pickle, time
from pathlib import Path
import numpy as np
from hifipushie import zozo_hang as zh
job = sys.argv[1]; jd = Path(f"/mnt/data/hifipushie/folds_ab/H/{job}"); t0 = time.time()
out, lines = zh.run(jd, timeout=float(sys.argv[2]) if len(sys.argv) > 2 else 10800)
print("done", round(time.time() - t0), "s", list(out.keys())[:10]); print("\n".join(str(l) for l in (lines or [])[-6:]))
pickle.dump(out, open(jd / "out.pkl", "wb"))
