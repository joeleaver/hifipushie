"""hlE.py <th_E name> ... [views=side,three_quarter,front size=560]: the hairline BEFORE / AFTER on a copy of another
human: <name>b = the same spec with groom.hairline.ear_from "brow" (the old guess), both regrown THROUGH THE TOOL
(server.groom_hair replace=True: the only difference is the line), each looked at (server.look_hair, EEVEE) ->
$TOUT/E_<name>.png / E_<name>b.png + their texts. Never the originals."""
import json
import os
import sys
import time

from hifipushie import server, store

kw = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
names = [a for a in sys.argv[1:] if "=" not in a]
out = os.environ.get("TOUT", "/mnt/data/hifipushie/tesshair6/out")
views = kw.get("views", "side,three_quarter,front").split(",")
for n in names:
    assert n.startswith("th_E"), n
    b = n + "b"
    (store.HOME / b).mkdir(exist_ok=True)
    sp = json.loads((store.HOME / n / "spec.json").read_text())
    (store.HOME / b / "spec.json").write_text(json.dumps(sp, indent=1))
    for m, patch in ((b, {"hairline": {"ear_from": "brow"}}), (n, {"hairline": {"ear_from": "mesh"}})):
        t = time.time()
        try:
            r = server.groom_hair(m, groom=patch, replace=True)
            print(m, "groom_hair", f"{time.time() - t:.0f} s", str(r)[:300].replace("\n", " | "))
            t = time.time()
            r = server.look_hair(m, views=views, size=int(kw.get("size", 560)), clay=False, save=f"{out}/E_{m}.png")
            open(f"{out}/E_{m}.txt", "w").write(str(r[-1]))
            print(m, "look_hair", f"{time.time() - t:.0f} s", str(r[-1])[:200].replace("\n", " | "))
        except Exception as e:  # (one model's failure must not stop the rest)
            print(m, "FAILED", type(e).__name__, str(e)[:500])
