"""dense_david.npz (the study's per-vertex calibration of DAViD's normals) -> src/hifipushie/david_normals_gnm.npz"""
import numpy as np
import mm
z = np.load(mm.MM / "dense_david.npz")
g = np.stack([z[f"g_n_{i}"] for i in range(4)]).astype(np.float16)
s = np.stack([z[f"s_n_{i}"] for i in range(4)]).astype(np.float16)
p = np.stack([z[f"p_n_{i}"] for i in range(4)]).astype(np.float16)
np.savez_compressed("src/hifipushie/david_normals_gnm.npz", g=g, s=s, p=p, flip=z["flip"].astype(np.float32),
                    note="DAViD multi-task ViT-L normals vs truth on 80 skinned EEVEE renders of 20 heads (2026-10-09); classes front, left(+40), profile(88), right(-38)")
print(g.shape, np.isfinite(s).sum(1), z["flip"])
