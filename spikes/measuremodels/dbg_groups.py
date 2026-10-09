import rs, numpy as np
g = rs.gnm()
for k, v in g["gr"].items():
    if any(s in k for s in ("eye", "scler", "iris", "pupil", "cornea", "lens", "lash", "teeth")):
        print(k, int(v.sum()), np.round(g["V0"][v].mean(0), 3) if v.sum() else "")
print(sorted(g["gr"].keys()))
