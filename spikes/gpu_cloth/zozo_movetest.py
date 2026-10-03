"""ZOZO repro (run with the release's python, zozo.sh env): a sheet in the path of a sphere moved by pin move_to.
Modes: plain (pushed), window (collision window off after 0.1 s: passes), windowgrav (+ a session dyn gravity: the
window is lost, pushed), windowgrav_fix (windows appended to dyn_param.txt: passes)."""
import sys
import numpy as np
from frontend import App
mode = sys.argv[1] if len(sys.argv) > 1 else "plain"
app = App.create(f"movetest_{mode}")
V, F = app.mesh.square(res=24, ex=[1, 0, 0], ey=[0, 0, 1])
V = np.asarray(V) * 0.3
app.asset.add.tri("sheet", V, F)
S, SF = app.mesh.icosphere(r=0.1, subdiv_count=3)
S = np.asarray(S) + [0, -0.2, 0]
app.asset.add.tri("ball", S, SF)
scene = app.scene.create()
sh = scene.add("sheet")
if mode == "allow":
    sh.param.set("allow-existing-intersection", 1.0)
sh.param.set("young-mod", 1000).set("strain-limit", 0.05)
b = scene.add("ball")
if mode.startswith("window"):
    b.collision_windows([(0.0, 0.1)])
p = b.pin()
p.move_to(S + [0, 0.5, 0], 0.2, 1.0)
scene = scene.build()
sess = app.session.create(scene)
sess.param.set("frames", 30).set("dt", 0.01).set("gravity", [0.0, 0.0, 0.0])
if mode.startswith("windowgrav"):
    sess.param.dyn("gravity").time(0.5).hold().change([0.0, 0.0, 0.0])
sess = sess.build()
if mode == "windowgrav_fix":
    from pathlib import Path
    with open(Path(sess.info.path) / "dyn_param.txt", "a") as f:
        for key, wins in scene._collision_windows_data.items():
            f.write(f"[{key}]\n" + "".join(f"{float(a)} {float(b)}\n" for a, b in wins))
    print(open(Path(sess.info.path) / "dyn_param.txt").read())
sess.start(blocking=True)
Vall, fr = sess.get.vertex()
Vall = np.asarray(Vall)
print(mode, "frame", fr, "rows", len(Vall), "sheet y range", Vall[:len(V), 1].min().round(3), Vall[:len(V), 1].max().round(3),
      "ball y mean", Vall[len(V):, 1].mean().round(3))
