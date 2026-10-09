"""DAViD on this machine (humannormals' venv) for pictures in MM/img: run.sh david_local.py <name>...  -> MM/pred/david/<name>.npz (raw axes)."""
import sys
import numpy as np
import mm
from hifipushie import humannormals as hn
for n in sys.argv[1:]:
    p = hn.predict(mm.MM / "img" / f"{n}.png")
    np.savez_compressed(mm.PRED / "david" / f"{n}.npz", normal=(p["normal"] * hn.calibration()["flip"]).astype(np.float32), mask=p["mask"].astype(np.float32), depth=p["depth"])
    print(n, p["normal"].shape)
