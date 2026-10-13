"""riffs7.py [only=<name,name>] [size=460]: th_52's riffs THROUGH THE TOOLS on two default heads (hu_w30, hu_m30;
never Tess): per riff a copy of the head (th_V9<a|b><n>), server.tie_hair(style, look), the first of each head
server.sync (the others look through its scene: look_hair(stage=)), server.look_hair(views) -> $TOUT/rf_<name>.png +
.txt. Nothing is tuned per head: `tie_hair` must just work."""
import json
import os
import sys
import time

from hifipushie import server, store

kw = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
OUT = os.environ["TOUT"]
FLAT = {"variation": 0, "sun": 0, "highlights": 0, "fly_light": 0, "vary": 0.0, "depth": 0}
RIFFS = [
    # (name, head, label, style, look)
    ("a1", "hu_w30", "sleek low | colour FLAT", {"tie": "low", "tightness": 0.9, "neatness": 0.9, "volume": 0}, FLAT),
    ("a2", "hu_w30", "LOOSE low, volume 0.7 | default colour (varied)", {"tie": "low", "tightness": 0.4, "neatness": 0.7, "volume": 0.7}, {}),
    ("a3", "hu_w30", "high ponytail, volume 0.5 | SUN-LIGHTENED", {"tie": "high", "tightness": 0.7, "part": "none", "volume": 0.5,
                                                                 "tail": {"length": 0.3, "wave": 0.3, "fullness": 0.6}}, {"sun": 0.9, "seen": "#5a4030"}),
    ("a4", "hu_w30", "top knot, volume 0.4 | HIGHLIGHTS 0.7", {"tie": "top", "tightness": 0.6, "part": "none", "volume": 0.4, "tail": "bun"},
     {"highlights": 0.7, "highlight_contrast": 0.8}),
    ("a5", "hu_w30", "half up, low side, volume 0.6 | variation 1", {"tie": "mid", "half": True, "length": 0.24, "tightness": 0.5, "volume": 0.6,
                                                                   "tail": {"length": 0.2, "wave": 0.3, "fullness": 0.3}}, {"variation": 1.0}),
    ("b1", "hu_m30", "sleek low | colour FLAT", {"tie": "low", "tightness": 0.9, "neatness": 0.9, "volume": 0, "tail": {"length": 0.16}}, FLAT),
    ("b2", "hu_m30", "LOOSE low side, volume 0.7 | default colour", {"tie": "low", "side": "left", "tightness": 0.4, "neatness": 0.6, "volume": 0.7,
                                                                  "tail": {"length": 0.18, "wave": 0.5}}, {}),
    ("b3", "hu_m30", "man bun, volume 0.5 | SUN-LIGHTENED + grey 0.08", {"tie": "high", "tightness": 0.6, "part": "none", "volume": 0.5, "tail": "bun"},
     {"sun": 0.9, "grey_amount": 0.08}),
    ("b4", "hu_m30", "low plait, volume 0.4 | HIGHLIGHTS 0.6", {"tie": "low", "tightness": 0.6, "volume": 0.4, "tail": {"kind": "plait", "length": 0.3, "fullness": 0.6}},
     {"highlights": 0.6}),
]
only = set(kw["only"].split(",")) if kw.get("only") else None
views = kw.get("views", "front,three_quarter,back").split(",")
stage_of = {}
for name, head, label, style, look in RIFFS:
    dst = f"th_V9{name}"
    first = f"th_V9{name[0]}1"
    if only and name not in only:
        continue
    d = store.HOME / dst
    d.mkdir(exist_ok=True)
    sp = json.loads((store.HOME / head / "spec.json").read_text())
    sp.pop("hair", None)
    (d / "spec.json").write_text(json.dumps(sp, indent=1))
    try:
        t = time.time()
        r = server.tie_hair(dst, style, look=look or None)
        print(dst, f"tie_hair {time.time() - t:.0f} s |", str(r).split("\n")[2][:260], flush=True)
        if dst == first or not (store.HOME / first / "scene.blend").exists():
            t = time.time()
            print(dst, "sync", str(server.sync(dst))[:120].replace("\n", " | "), f"{time.time() - t:.0f} s", flush=True)
            stg = None
        else:
            stg = first
        t = time.time()
        r = server.look_hair(dst, views=views, size=int(kw.get("size", 460)), clay=False, save=f"{OUT}/rf_{name}.png", stage=stg)
        open(f"{OUT}/rf_{name}.txt", "w").write(label + "\n" + json.dumps(style) + "\n" + json.dumps(look) + "\n" + str(r[-1]))
        print(dst, f"look_hair {time.time() - t:.0f} s", flush=True)
    except Exception as e:  # noqa: BLE001 (one riff's failure must not stop the rest; it is reported)
        import traceback
        traceback.print_exc()
        print(dst, "FAILED", type(e).__name__, str(e)[:400], flush=True)
