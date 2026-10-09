"""dense_<model>.npz (the study's per-vertex calibration of a model's normals) -> src/hifipushie/<model>_normals_gnm.npz
run.sh export_cal.py [david | marigold | marigold_lcm]"""
import sys
import numpy as np
import mm
m = sys.argv[1] if len(sys.argv) > 1 else "david"
z = np.load(mm.MM / f"dense_{m}.npz")
g = np.stack([z[f"g_n_{i}"] for i in range(4)]).astype(np.float16)
s = np.stack([z[f"s_n_{i}"] for i in range(4)]).astype(np.float16)
p = np.stack([z[f"p_n_{i}"] for i in range(4)]).astype(np.float16)
np.savez_compressed(f"src/hifipushie/{m}_normals_gnm.npz", g=g, s=s, p=p, flip=z["flip"].astype(np.float32),
                    note=f"{m} normals vs truth on 80 skinned EEVEE renders of 20 heads (2026-10-09); classes front, left(+40), profile(88), right(-38)")
print(m, g.shape, np.isfinite(s).sum(1), z["flip"])
