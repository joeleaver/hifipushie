"""fitface.py <name> <tag> [read json] [views: v5 | v5v4]: human_reference on the v5 front face (+ v4 turned)."""
import json, os, sys
from hifipushie import server

name, tag = sys.argv[1], sys.argv[2]
read = json.loads(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] else None
which = sys.argv[4] if len(sys.argv) > 4 else "v5v4"
R = os.environ["T"] + "/ref/"
views = [{"image": R + "v5_face_x3.png", "size": [900, 900], "yaw": 0}]
if "v4" in which:
    views.append({"image": R + "v4_face_x3.png", "size": [900, 900], "yaw": 45})
r = server.human_reference(name, views, read=read, note=f"tess: MAP face fit {which} read={read}")
for x in r:
    if isinstance(x, str):
        print(x)
    else:
        open(os.path.join(os.environ["T"], "out", tag + ".png"), "wb").write(x.data)
