"""The method table with dense models and generated meshes as evidence.   run.sh fits2.py [prefix ...]"""
import sys

import numpy as np

import dense
import fitlib
import fits
import mm
import rs
import tmesh

sys.path.insert(0, str(mm.MM))
FT = ["front", "tq"]


def stack(*rr):
    rr = [r for r in rr if r is not None and len(r[1])]
    if not rr:
        return None
    return np.vstack([r[0] for r in rr]), np.concatenate([r[1] for r in rr])


def read_rows(s):
    import exp2
    from hifipushie import humanmacro as hm
    return hm.prior_rows(exp2.reader(fits.truth(s)))


def dense_fit(s, views, model, use=("z", "n"), rounds=3, extra=None, infl=2.0, regions=None, tab="skin", cut=0.9):
    ev = fits.evs(s, views, tab=tab)
    vs = [v for v in views if fits.ev478(f"{s}_{v}", tab=tab) is not None]
    f = fitlib.fit(ev, robust=True, rows=extra)
    for _ in range(rounds):
        rr = []
        for v, cam in zip(vs, f["cams"]):
            iid = f"{s}_{v}"
            it = mm.item(iid)
            pr = mm.pred(model, iid)
            rr.append(dense.rows(model, pr, f["c"], cam, v, hair=it["hair"] if it["look"]["hair"] else None, use=use, infl=infl, regions=regions, cut=cut))
        f = fitlib.fit(ev, robust=True, rows=stack(extra, *rr), c_init=f["c"])
    return f


def feat_fit(s, views, model, rounds=3, extra=None, normals=False, infl=1.3):
    ev = fits.evs(s, views)
    vs = [v for v in views if fits.ev478(f"{s}_{v}") is not None]
    f = fitlib.fit(ev, robust=True, rows=extra)
    for _ in range(rounds):
        rr = []
        for v, cam in zip(vs, f["cams"]):
            iid = f"{s}_{v}"
            it = mm.item(iid)
            hair = it["hair"] if it["look"]["hair"] else None
            rr.append(dense.rows_feat(model, mm.pred(model, iid), f["c"], cam, v, hair=hair, infl=infl))
            if normals:
                rr.append(dense.rows(model, mm.pred(model, iid), f["c"], cam, v, hair=hair, use=("n",), infl=4.0))
        f = fitlib.fit(ev, robust=True, rows=stack(extra, *rr), c_init=f["c"])
    return f


def methods(model):
    return {
        f"E1 {model} feature depths, front+tq": lambda s: feat_fit(s, FT, model),
        f"E1f {model} feature depths, front only": lambda s: feat_fit(s, ["front"], model),
        f"E2 {model} feature depths + normals x4, front+tq": lambda s: feat_fit(s, FT, model, normals=True),
        f"E3 {model} feature depths + read, front+tq": lambda s: feat_fit(s, FT, model, extra=read_rows(s)),
        f"N1 {model} normals x4, front only": lambda s: dense_fit(s, ["front"], model, use=("n",), infl=4.0),
        f"N2 {model} normals x6, front+tq": lambda s: dense_fit(s, FT, model, use=("n",), infl=6.0),
        f"N3 {model} normals x3, front+tq": lambda s: dense_fit(s, FT, model, use=("n",), infl=3.0),
        f"N4 {model} normals x4 + read, front+tq": lambda s: dense_fit(s, FT, model, use=("n",), infl=4.0, extra=read_rows(s)),
        f"N5 {model} normals x4 + read, front only": lambda s: dense_fit(s, ["front"], model, use=("n",), infl=4.0, extra=read_rows(s)),
        f"N6 {model} normals x4, front+tq+tq2": lambda s: dense_fit(s, FT + ["tq2"], model, use=("n",), infl=4.0),
        f"N7 {model} normals x4, all vertices (cut 2)": lambda s: dense_fit(s, FT, model, use=("n",), infl=4.0, cut=2.0),
        f"D1b {model} normals sigma x4, front+tq": lambda s: dense_fit(s, FT, model, use=("n",), infl=4.0),
        f"D1 {model} normals, front+tq": lambda s: dense_fit(s, FT, model, use=("n",)),
        f"D2 {model} depth, front+tq": lambda s: dense_fit(s, FT, model, use=("z",)),
        f"D3 {model} depth + normals, front+tq": lambda s: dense_fit(s, FT, model),
        f"D3f {model} depth + normals, front only": lambda s: dense_fit(s, ["front"], model),
        f"D4 {model} depth + normals, sigma x1": lambda s: dense_fit(s, FT, model, infl=1.0),
        f"D5 {model} depth + normals, sigma x4": lambda s: dense_fit(s, FT, model, infl=4.0),
        f"D6 {model} depth + normals + read, front+tq": lambda s: dense_fit(s, FT, model, extra=read_rows(s)),
    }


BASE2 = {
    "R1 mp478 skin + read, front+tq": lambda s: fitlib.fit(fits.evs(s, FT), robust=True, rows=read_rows(s)),
    "R1f mp478 skin + read, front only": lambda s: fitlib.fit(fits.evs(s, ["front"]), robust=True, rows=read_rows(s)),
}

if __name__ == "__main__":
    model = sys.argv[1]
    M = dict(BASE2)
    M.update(methods(model))
    res = fits.run(M, sys.argv[2:], out="fits")
