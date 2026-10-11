"""stp.py <src> <out> '<moves json>' "<seen>" "<why>": a block-in step, its sheet, then the face ruler's READ rows."""
import sys, json, re
from hifipushie import server
src, out, mv, seen, why = sys.argv[1:6]
R = "/home/joe/dev/hifipushie/workspace/human_renders/"
r = server.block_in_step(src, json.loads(mv), out=out, seen=seen, why=why, save=R + out + ".png")
t = r[-1]
print("\n".join(l for l in t.split("\n") if not re.search(r"\bok$", l) and "MANUAL" not in l and not l.startswith(("- [", "  looks alike"))))
f = server.face_ruler(out)[-1]
ls = f.split("\n")
print("\n".join(l[:118] for l in ls if l.startswith("  ") and "->" in l))
print("\n".join(l[:150] for l in ls if "mm:" in l and "NOT READ" not in l and "inside the reader" not in l))
print("\n".join(l[:200] for l in ls if l.startswith("cameras turned")))
