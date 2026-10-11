"""couplings.py: per macro, what its FREE step drags along (other macros, sd per +1 sd), the prior cost |dc| of the free
vs the held step, the face-ID effect per unit (atlas), and where the face moves (top zones) -> out/couplings.txt / .json"""
import json

import numpy as np

import drv
from hifipushie import blockin as bi, gnm_controls as gcm, humanmacro as hm

t = gcm.table()
rows = {}
lines = []
F = None
for m in hm.NAMES:
    out = {}
    for kind, name in (("free", m), ("held", m + "!")):
        d = bi.direction(name)
        c1 = d
        z0 = hm.read(np.zeros(hm.K))
        z1 = hm.read(c1[:hm.K])
        dz = {k: z1[k] - z0[k] for k in z1}
        drag = sorted(((k, v) for k, v in dz.items() if k not in (m, "head_size")), key=lambda kv: -abs(kv[1]))[:5]
        D = np.tensordot(d, drv.IBH, 1) * 1000
        n = np.sqrt((D ** 2).sum(1))
        Z = gcm.zones()
        zr = sorted(((z, float(np.sqrt((n[v] ** 2).mean()))) for z, v in Z.items()
                     if z in gcm.ZONES and z not in ("face", "neck", "cranium", "ears", "iris", "pupil", "sclera",
                                                    "teeth_upper", "teeth_lower", "tongue")), key=lambda kv: -kv[1])[:4]
        out[kind] = {"self": round(dz[m], 2), "cost": round(float(np.linalg.norm(d)), 2),
                     "drag": [(k, round(v, 2)) for k, v in drag], "zones": [(z, round(v, 2)) for z, v in zr],
                     "face_rms": round(float(np.sqrt((n[Z["face"]] ** 2).mean())), 2)}
    i = t["index"].get(m)
    out["perc"] = None if i is None or not np.isfinite(t["perc"][i, 0]) else round(float(t["perc"][i, 0]), 4)
    rows[m] = out
    f, h = out["free"], out["held"]
    lines.append(f"{m}: free |dc| {f['cost']} face {f['face_rms']} mm, drags " + ", ".join(f"{k} {v:+.2f}" for k, v in f["drag"][:4])
                 + f" | held |dc| {h['cost']} face {h['face_rms']} mm, zones " + ", ".join(f"{z} {v:.1f}" for z, v in h["zones"][:3])
                 + f" | face-ID/sd {out['perc']}")
(drv.G / "out" / "couplings.json").write_text(json.dumps(rows, indent=1))
(drv.G / "out" / "couplings.txt").write_text("\n".join(lines))
print("\n".join(lines))
