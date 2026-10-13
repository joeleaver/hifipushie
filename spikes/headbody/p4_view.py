"""p4_view.py <model> [tag]: the fused template's neck, current attach | native, PIL wire tiles (no Blender)."""
import copy, os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "onemesh"))
import wire
from hifipushie import onemesh, store

OUT = "/mnt/data/hifipushie/headbody/out"
mname = sys.argv[1]
a = onemesh.asset()
lev = a["g_lev"].astype(int)
for tag in ("old", "native"):
    base = copy.deepcopy(store.load(mname)["base"])
    if tag == "native":
        base["head"]["attach"] = "native"
    tpl = onemesh.template(base)
    P = tpl["P"]; nb = tpl["n_body"]; nmh = tpl["n_mh"]
    faces = []; i = 0
    for n_ in tpl["S"]:
        faces.append(tpl["L"][i:i + n_]); i += n_
    ht = onemesh.head_rest(base)
    chin = ht["lm68"][8]
    col = []
    for f in faces:
        f = np.asarray(f)
        col.append((205, 200, 192) if (f >= nb).all() else (170, 190, 215) if (f < nmh).all() else (215, 190, 150))
    fid = tpl["fid"]
    ring = set(int(v) for v in np.flatnonzero(np.isin(fid, a["loop_a"])))
    hi = [(int(f[j]), int(f[(j + 1) % len(f)])) for f in faces for j in range(len(f)) if int(f[j]) in ring and int(f[(j + 1) % len(f)]) in ring]
    c = np.array([0.0, chin[1] + 0.07, chin[2] - 0.06])
    for nm, az, el in (("front", 0, 0), ("q", 40, 5), ("side", 90, 0), ("back", 180, 0), ("qb", 140, 10)):
        for wtag, line, hi_ in (("wire", 1, hi), ("clay", 0, None)):
            im = wire.view(P, faces, c, 0.34, az=az, el=el, px=700, colors=col if wtag == "wire" else None, line=line, hi_edges=hi_, title=f"{mname} {tag} {nm}")
            im.save(f"{OUT}/{mname}_{tag}_{nm}_{wtag}.png")
    cf = np.array([0.0, 0.0, P[:, 2].max() / 2])
    for nm, az in (("front", 0), ("side", 90)):
        wire.view(P, faces, cf, P[:, 2].max() * 1.08, az=az, px=900, line=0, title=f"{mname} {tag}").save(f"{OUT}/{mname}_{tag}_fig_{nm}.png")
print("done")
