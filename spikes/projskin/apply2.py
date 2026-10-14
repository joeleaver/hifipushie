"""apply2.py <src> <prefix> [k=v]: one skin_project.make of <src>, saved twice: <prefix>_p (the de-lit projection) and
<prefix>_r (the RAW blend: same exclusions and fill, no de-lighting), each a copy of src with its references. LIGHT."""
import sys
from hifipushie import skin_project as sp
src, pre = sys.argv[1:3]
kw = dict(a.split("=", 1) for a in sys.argv[3:])
kw = {k: (v == "1" if v in ("0", "1") else v) for k, v in kw.items()}
r = sp.make(src, **kw)
a = sp.apply(src, out=pre + "_p", made=r)
print(a["text"])
b = sp.apply(src, out=pre + "_r", made=r, raw=True)
print("raw ->", pre + "_r", b["dir"])
