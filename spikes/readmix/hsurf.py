"""hsurf.py <k> <pose> <label>=<model> ..: a solved head against the SCAN's SURFACE (not the fit's vertices: two clean
scans of one person give direct-fit identities 1-4 mm apart, so vertex rms has a floor; surface distance does not).
The solved identity gets the scan's own expression (the Part 1 identity + expression fit's e), is laid on that fit by a
similarity over the fit vertices (pose and size: the cameras' business), and each region's vertices are measured to the
scan (in GNM world through the fit's similarity): mean |d| and mean signed d (+ = the head stands OUTSIDE the scan), mm.
Regions: groundtruth's report regions (lips, nose, chin, cheeks, face)."""
import json, os, sys
import numpy as np
sys.path.insert(0, "/home/joe/dev/hifipushie/.claude/worktrees/groundtruth/spikes/groundtruth")
import gt, hsrdset as H
from hifipushie import blockin as bi, store

k, pose = sys.argv[1], sys.argv[2]
mods = dict(a.split("=") for a in sys.argv[3:])
P = H.Pose(pose)
ie = P.fit()["identity_expression"]
ce, e = np.asarray(ie["c"]), np.asarray(ie["e"])
S = (ie["S"]["s"], np.asarray(ie["S"]["R"]), np.asarray(ie["S"]["t"]))
sc = P.scan()
G = gt.gnm()
Vs = gt.apply(S, sc["V"])
skin = np.asarray(sc.get("skin", np.ones(len(sc["V"]), bool)), bool)
surf = gt.Surface(Vs, sc["F"])
fn = gt.face_normals(Vs, sc["F"])
Vt = gt.verts(ce, e)
fit = np.asarray(G["fit"], bool)
REG = ("lips", "nose", "chin", "cheeks", "face")
out = {}
for lab, m in mods.items():
    c = bi.identity(store.load(m))
    V = gt.verts(c, e)
    M = gt.umeyama(V[fit], Vt[fit], scale=True)
    V = gt.apply(M, V)
    row = {}
    for r in REG:
        mk = np.asarray(G["regions"][r], bool) & fit
        Q, d, fi, bw = surf.closest(V[mk])
        ok = skin[sc["F"][fi]].all(1)
        sg = np.sign(((V[mk] - Q) * fn[fi]).sum(1)) * d
        row[r] = (float(np.mean(d[ok]) * 1000), float(np.mean(sg[ok]) * 1000))
    out[lab] = row
    print(f"| {k} | {lab} | " + " | ".join(f"{row[r][0]:.2f} ({row[r][1]:+.2f})" for r in REG) + " |", flush=True)
json.dump(out, open(f"{os.environ['HIFIPUSHIE_READMIX']}/out/hsurf_{k}.json", "w"))
