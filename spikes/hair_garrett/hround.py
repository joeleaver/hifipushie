"""hround.py <head> <dst> [patch=@file.json] [seed=0] [read=1]: dst = a copy of head with the hair READER's start
(hair_read.apply(head, out=dst)); then an optional round patch {"groom": {...}, "strands": {...}, "look": {...}}
through server.groom_hair (the MCP path). read=0: skip the reader (dst must exist), patch only.
Prints the reader's text and the groom's reply; writes $TOUT/start_<dst>.txt."""
import json
import os
import sys
import time

from hifipushie import hair_read, server

head, dst = sys.argv[1:3]
kw = dict(a.split("=", 1) for a in sys.argv[3:])
assert dst.startswith(("hg_", "hj_", "hl_")), dst
t = time.time()
if kw.get("read", "1") == "1":
    r = hair_read.apply(head, out=dst, seed=int(kw.get("seed", 0)))
    open(os.path.join(os.environ["TOUT"], f"start_{dst}.txt"), "w").write(r["text"])
    print(r["text"])
    print(f"reader + groom {time.time() - t:.0f} s")
if kw.get("patch"):
    p = json.loads(open(kw["patch"][1:]).read() if kw["patch"].startswith("@") else kw["patch"])
    g = dict(p.get("groom") or {})
    if kw.get("seed") is not None:
        g["seed"] = int(kw["seed"])
    print(server.groom_hair(dst, groom=g or None, replace=True, strands=p.get("strands"), look=p.get("look"),
                            note=f"hair-garrett round patch {kw['patch']}"))
    print(f"patch {time.time() - t:.0f} s")
