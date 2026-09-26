import bpy, numpy as np
body = bpy.data.objects["GEO-body_male_stylized"]
V = np.array([body.matrix_world @ v.co for v in body.data.vertices])
sx, sz = -(V[:, 0].min() + V[:, 0].max()) / 2, -V[:, 2].min()
for n in ("GEO-body_male_stylized.eye.L", "GEO-body_male_stylized.eye.R"):
    ob = bpy.data.objects[n]
    P = np.array([ob.matrix_world @ v.co for v in ob.data.vertices])
    c = (P.min(0) + P.max(0)) / 2
    print("@@", n, [round(c[0] + sx, 4), round(c[1], 4), round(c[2] + sz, 4)], "r", round((P.max(0) - P.min(0)).max() / 2, 4))
