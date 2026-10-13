"""tess.py start <name> | chain <start> <prefix> <n> [dense=1] [cameras=free]: Tess on the solvecams solve. start =
server.block_in_start(<name>, "tess_a1", sex="female") with nothing else (the default native path, as nativedefault built
nd_T00; tess_a1 is only READ). chain = n block_in_solve calls, each call's CAMERA / DISAGREE / AT THE BOUND lines."""
import sys
import numpy as np
from hifipushie import blockin as bi, face_ruler as fr, server, store

if sys.argv[1] == "start":
    r = server.block_in_start(sys.argv[2], "tess_a1", sex="female", replace=True)
    print("\n".join(x for x in r if isinstance(x, str))[:3000])
else:
    src, pre, n = sys.argv[2], sys.argv[3], int(sys.argv[4])
    kw = dict(a.split("=", 1) for a in sys.argv[5:])
    dense = kw.get("dense", "0") == "1"
    for i in range(1, n + 1):
        out = f"{pre}{i:02d}"
        rep = bi.solve_step(src, out=out, cameras=kw.get("cameras", "free"), dense=dense)
        so = rep["solve"]
        rw = __import__("hifipushie.solve_report", fromlist=["x"]).rows()
        c = bi.identity(store.load(out))
        mm = rw["R"] @ c
        print(f"-- {out}: reads {so['n']}; |dc| {so['dc']:.2f}; |c| {so['c']:.2f}; largest {so['max_sd']:.2f} sd; bound {so.get('bound')}; damped {so.get('damped')}; table "
              f"{sum(int(str(v).split('/')[0]) for v in rep['entry']['passes'].values())} / {sum(int(str(v).split('/')[1]) for v in rep['entry']['passes'].values())}")
        print("   turn " + str(so["view_yaw"]) + " stated " + str(so["stated_yaw"]) + "; identity (mm from GNM's mean): " + ", ".join(f"{k} {mm[rw['names'].index(k)]:+.1f}" for k in ("jaw_width", "gonial_width", "chin_width", "cheekbone_width", "chin_length")))
        for x in (so.get("camera_lines") or []) + [x for x in so.get("notes") or [] if x[:4] in ("DISA", "AT T", "VIEW")]:
            print("   " + x[:420])
        sys.stdout.flush()
        src = out
