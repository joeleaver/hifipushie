"""start.py <name> <refs model> <sex> [key=value ..]: block_in_start through the server tool (the new defaults), the reply printed."""
import sys
from hifipushie import server
name, refs, sex = sys.argv[1:4]
kw = dict(a.split("=", 1) for a in sys.argv[4:])
kw = {k: (v == "1" if v in "01" else v) for k, v in kw.items()}
out = server.block_in_start(name, refs, sex=sex, replace=True, save=f"/mnt/data/hifipushie/nativedefault/out/start_{name}.png", **kw)
print(out[1])
