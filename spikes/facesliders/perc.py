"""perc.py [what]: the PERCEPTUAL effect of face directions (faces4 M0b; Joe: "the human brain is really good at
perceiving tiny changes when they're related to identity"): each direction at -1 and +1 (its own unit: 1 sd for GNM
components and coupled sliders, 1 slider unit for residual morphs / extensions) on a few heads, rendered the SAME way on
both sides (GNM's head mesh alone, clay with eyes and brows, likeness.render through 3 views), and the face-ID embedding
distance (1 - cosine; faceid.py: SFace (Apache), ArcFace (InsightFace, non-commercial: measuring only)) between the two
renders, next to the move in mm.

what (comma list, default all): calib, identity, expression, sliders, ext.
Env: HEADS (default mean,tess,garrett: GNM's mean, f3_t1's identity, fs_gj8's), VIEWS (yaw deg, default 0,-30,30),
OUT (default /mnt/data/hifipushie/faces4/out/perc). Writes <OUT>/perc_<what>.json and prints a ranked table.
Fast: no one-mesh build (the identity / expression / slider fields are applied to GNM's raw vertices directly)."""
import json
import os
import sys
from pathlib import Path

import numpy as np

from hifipushie import base as basemod, faceatlas, faceid, faceslide, likeness, store

OUT = Path(os.environ.get("OUT", "/mnt/data/hifipushie/faces4/out/perc"))
OUT.mkdir(parents=True, exist_ok=True)
VIEWS = [float(v) for v in os.environ.get("VIEWS", "0,-30,30").split(",")]
PX = 256
g = basemod._gnm_data()
TPL = np.asarray(g["template_vertex_positions"], float)
N = len(TPL)
IB = np.asarray(g["vertex_identity_basis"], float)
EB = np.asarray(g["expression_basis"], float)
ID_NAMES = [str(x) for x in g["identity_names"]]
EX_NAMES = [str(x) for x in g["expression_names"]]
grp = lambda k: np.asarray(g["groups"][k], float) > 0.5  # noqa: E731
Q = np.asarray(g["quads"], int)
EXT = grp("skin_exterior")


def _faces(mask):
    q = Q[mask[Q].all(1)]
    return np.r_[q[:, [0, 1, 2]], q[:, [0, 2, 3]]].astype(np.int64)


F_SKIN = _faces(grp("skin"))
EYE_PARTS = [(_faces(grp("scleras")), np.array([235.0, 232.0, 225.0])),
             (_faces(grp("irises") & ~grp("pupils")), np.array([95.0, 70.0, 50.0])),
             (_faces(grp("pupils")), np.array([20.0, 18.0, 16.0]))]
ROWS = g["lm68"]
WLM = np.zeros((68, N))
for i, r in enumerate(ROWS):
    for v, w in zip(r[0::2], r[1::2]):
        WLM[i, int(v)] += float(w)


def world(V):
    """GNM frame (x left, y up, z forward) -> world (Z up, facing -Y)."""
    return np.c_[V[:, 0], -V[:, 2], V[:, 1]]


def coeffs(names, d):
    c = np.zeros(len(names))
    idx = {n: i for i, n in enumerate(names)}
    for k, v in (d or {}).items():
        if k in idx:
            c[idx[k]] = float(v)
    return c


def head(spec_name):
    if spec_name == "mean":
        return np.zeros(len(ID_NAMES))
    m = {"tess": "f3_t1", "garrett": "fs_gj8"}.get(spec_name, spec_name)
    h = store.load(m)["base"]["head"]
    return coeffs(ID_NAMES, h.get("identity"))


def verts(c, e=None, D=None):
    V = TPL + np.tensordot(c, IB, 1)
    if e is not None:
        V = V + np.tensordot(e, EB, 1)
    if D is not None:
        V = V + D[:N]
    return V


def render(V, yaw):
    W = world(V)
    L = WLM @ W
    cen = L[[36, 45, 48, 54]].mean(0)
    half = 0.095
    cam = {"r": [0.0, 0.0, 0.0], "t": [0.0, 0.0, 0.8], "f": PX / 2 * 0.8 / half, "size": [PX, PX],
           "centre": list(map(float, cen)), "yaw": yaw}
    mesh = {"V": W, "F": F_SKIN, "eyes": [(W, f, col) for f, col in EYE_PARTS], "L": L}
    im, _ = likeness.render(mesh, cam, (0, 0, PX, PX), px=PX, brows=True)
    return im


def dist(ims_a, ims_b):
    """per view {model: 1 - cos} between two lists of renders (one embed call)."""
    E = faceid.embed(list(ims_a) + list(ims_b))
    n = len(ims_a)
    out = []
    for i in range(n):
        a, b = E[i], E[n + i]
        out.append({m: (None if a is None or b is None else 1.0 - faceid.cosine(a[m], b[m])) for m in faceid.MODELS})
    return out


def mm(D):
    m = np.linalg.norm(D[:N][EXT], axis=1)
    return float(m.max() * 1e3), float(np.sqrt((m ** 2).mean()) * 1e3)


def where(D):
    """the region of the largest move (GNM's region groups)."""
    m = np.linalg.norm(D[:N], axis=1) * EXT
    i = int(np.argmax(m))
    for k in g["groups"]:
        if k.endswith("_region") and grp(k)[i]:
            return k.replace("_region", "")
    return "-"


def measure(name, plus, minus, heads):
    """plus / minus: functions head c -> V. Returns the row."""
    row = {"name": name, "views": VIEWS, "heads": {}}
    for hn, c in heads.items():
        Vp, Vm = plus(c), minus(c)
        d = dist([render(Vp, y) for y in VIEWS], [render(Vm, y) for y in VIEWS])
        row["heads"][hn] = d
        row.setdefault("mm", mm(Vp - Vm))
        row.setdefault("where", where(Vp - Vm))
    vals = {m: [v[m] for h in row["heads"].values() for v in h if v[m] is not None] for m in faceid.MODELS}
    row["id"] = {m: (float(np.mean(v)) if v else None) for m, v in vals.items()}
    return row


def table(rows, title):
    rows = sorted(rows, key=lambda r: -(r["id"]["sface"] or 0))
    lines = [f"== {title}: 1 - cos between -1 and +1 (mean over heads x views); mm = largest / rms move on the skin"]
    for r in rows:
        lines.append(f"{r['name']:24s} sface {r['id']['sface'] or 0:.4f} arcface {r['id']['arcface'] or 0:.4f} | "
                     f"{r['mm'][0]:5.2f} / {r['mm'][1]:4.2f} mm | {r['where']}")
    return "\n".join(lines)


def run(what, heads):
    rows = []
    if what == "calib":
        hs = list(heads.items())
        base_c = hs[0][1]
        V0 = verts(base_c)
        # noise floor: the same head with the camera turned 1 deg (the measure's own wobble)
        for dy in (0.5, 1.0, 2.0):
            d = dist([render(V0, y) for y in VIEWS], [render(V0, y + dy) for y in VIEWS])
            rows.append({"name": f"camera +{dy} deg", "id": {m: float(np.mean([v[m] for v in d])) for m in faceid.MODELS},
                         "mm": (0.0, 0.0), "where": "-", "heads": {hs[0][0]: d}})
        # different people: the heads against each other and random GNM heads
        rng = np.random.default_rng(0)
        hc = [i for i, n in enumerate(ID_NAMES) if n.startswith("head")]
        rnd = []
        for k in range(6):
            c = np.zeros(len(ID_NAMES))
            c[hc] = rng.standard_normal(len(hc))
            rnd.append((f"gnm_random{k}", c))
        people = hs + rnd
        for i in range(len(people)):
            for j in range(i + 1, len(people)):
                a, b = people[i], people[j]
                d = dist([render(verts(a[1]), y) for y in VIEWS], [render(verts(b[1]), y) for y in VIEWS])
                rows.append({"name": f"{a[0]} vs {b[0]}", "id": {m: float(np.mean([v[m] for v in d])) for m in faceid.MODELS},
                             "mm": mm(verts(a[1]) - verts(b[1])), "where": "-", "heads": {"pair": d}})
    elif what == "identity":
        for i, n in enumerate(ID_NAMES):
            if not n.startswith("head"):
                continue
            e = np.zeros(len(ID_NAMES))
            e[i] = 1.0
            rows.append(measure(n, lambda c, e=e: verts(c + e), lambda c, e=e: verts(c - e), heads))
            print(n, rows[-1]["id"], flush=True)
    elif what == "expression":
        K = int(os.environ.get("NEXPR", "20"))
        for pre in ("lower_face_region", "eye_pair"):
            if pre == "eye_pair":
                pairs = [(f"left_eye_region_{k:03d}", f"right_eye_region_{k:03d}") for k in range(K)]
            else:
                pairs = [(f"lower_face_region_{k:03d}",) for k in range(K)]
            for p in pairs:
                e = np.zeros(len(EX_NAMES))
                for n in p:
                    e[EX_NAMES.index(n)] = 1.0
                nm = p[0] if len(p) == 1 else p[0].replace("left_", "both_")
                rows.append(measure(nm, lambda c, e=e: verts(c, e), lambda c, e=e: verts(c, -e), heads))
                print(nm, rows[-1]["id"], flush=True)
    elif what in ("sliders", "ext"):
        t = faceatlas.table()
        comps = faceatlas._gnm()["comps"]
        names = [k for k in faceslide.UNITS if k.startswith("mh_")] if what == "ext" else \
            [k for k in faceslide.UNITS if not k.startswith("mh_")]
        for k in names:
            attr = faceatlas.COUPLED.get(k)
            if attr is not None or k in faceslide.COUPLED_ONLY:
                attr = attr or {"eye_opening": "lid_aperture", "gonion_height": "gonion_height",
                                "ramus_angle": "ramus_angle"}[k]
                dc = np.zeros(len(ID_NAMES))
                dc[comps] = faceatlas.direction({attr: float(t["sd"][t["index"][attr]])})
                rows.append(measure(f"{k} (coupled)", lambda c, dc=dc: verts(c + dc), lambda c, dc=dc: verts(c - dc), heads))
            else:
                if k in faceslide.AGE_SLIDERS if hasattr(faceslide, "AGE_SLIDERS") else False:
                    pass
                Dp = faceslide.delta({k: 1.0})
                Dm = faceslide.delta({k: -1.0})
                if Dm is None:   # one-sided: 0 vs +1
                    Dm = np.zeros_like(Dp)
                rows.append(measure(k, lambda c, D=Dp: verts(c, D=D), lambda c, D=Dm: verts(c, D=D), heads))
            print(k, rows[-1]["id"], flush=True)
    (OUT / f"perc_{what}.json").write_text(json.dumps(rows))
    txt = table(rows, what)
    (OUT / f"perc_{what}.txt").write_text(txt)
    print(txt)


if __name__ == "__main__":
    heads = {h: head(h) for h in os.environ.get("HEADS", "mean,tess,garrett").split(",")}
    for w in (sys.argv[1] if len(sys.argv) > 1 else "calib,identity,expression,sliders,ext").split(","):
        run(w, heads)
