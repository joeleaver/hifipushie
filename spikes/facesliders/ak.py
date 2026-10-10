from hifipushie import onemesh
a = onemesh.asset()
for k, v in a.items():
    try:
        print(k, getattr(v, "shape", None), getattr(v, "dtype", None))
    except Exception:
        print(k)
