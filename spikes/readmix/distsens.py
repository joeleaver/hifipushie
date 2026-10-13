"""distsens.py: what a camera-DISTANCE error costs in apparent widths (geometry only, GNM's class-mean heads): the front
camera believed `err` % too far (the lens lengthened to match: the picture's scale at the eyes' plane stays), per true
distance the change in the PROJECTED alar, cheekbone, jaw (gonial) and ear-to-ear width, in mm at the face: what the solve
must then explain as shape. Also the nose's enlargement against the ear plane, d_ear / d_nose."""
import sys
import numpy as np
from hifipushie import blockin as bi, face_ruler as fr, gnm_mm

err = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
D = bi.data()
print(f"| true distance m | nose against the ear plane | a {err:+.0f} % distance error shows as: alar width | mouth width | cheekbone width | jaw (gonial) width | ear to ear |")
print("|---|---|---|---|---|---|---|")
for d in (0.3, 0.4, 0.5, 0.7, 1.0, 1.5, 2.0, 3.0):
    rows = []
    for sex in ("m_m", "m_f"):
        h = fr.gnm_head(np.asarray(D[sex], float))
        L, V, gr = h["L"], h["V"], h["gr"]
        eye = L[36:48].mean(0)
        ear = V[gr["ears"]]
        pairs = {"alar": (L[31], L[35]), "mouth": (L[48], L[54]), "cheek": (L[1], L[15]), "jaw": (L[4], L[12]),
                 "ear": (ear[np.argmin(ear[:, 0])], ear[np.argmax(ear[:, 0])])}

        def width(dist):
            # a pinhole in front of the eyes' plane at `dist`, magnification 1 at that plane: x' = x * dist / (dist + depth behind the plane)
            out = {}
            for k, (a, b) in pairs.items():
                za, zb = a[1] - eye[1], b[1] - eye[1]            # world +Y = away from a camera in front (the head faces -Y)
                out[k] = (b[0] * dist / (dist + zb) - a[0] * dist / (dist + za)) * 1000
            return out
        w0, w1 = width(d), width(d * (1 + err / 100))
        nose_z, ear_z = L[30][1] - eye[1], ear[:, 1].mean() - eye[1]
        rows.append([(d + ear_z) / (d + nose_z)] + [w0[k] - w1[k] for k in ("alar", "mouth", "cheek", "jaw", "ear")])
    r = np.mean(rows, 0)
    print(f"| {d:.1f} | x{r[0]:.2f} | {r[1]:+.2f} mm | {r[2]:+.2f} | {r[3]:+.2f} | {r[4]:+.2f} | {r[5]:+.2f} |")
