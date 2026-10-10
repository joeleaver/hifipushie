"""fstrace.py <model> <garment> <piece> [piece ...]: dress() up to the fine settle's start check, recording the named
pieces' worst stretch after every step of the fine start (_press_plan's clear / relax / untangle calls)."""
import sys
import numpy as np
from hifipushie import cloth, server
from hifipushie.cloth_zozo import _start_stretch

name, g, pieces = sys.argv[1], sys.argv[2], sys.argv[3:]
ctx = {}


def report(tag, V, M):
    F = M["F"]
    s = _start_stretch(np.c_[M["uv"], np.zeros(len(M["uv"]))], V, F)
    P = M["piece"][F[:, 0]]
    print(f"  {tag:28s} " + ", ".join(f"{nm} {s[P == M['names'].index(nm)].max():.2f}" for nm in pieces), flush=True)


def wrap(fn_name, getM):
    orig = getattr(cloth, fn_name)

    def w(*a, **k):
        r = orig(*a, **k)
        M = getM(a)
        if M is not None and "M" in ctx:
            V = r[0] if isinstance(r, tuple) else r
            if hasattr(V, "shape") and V.shape == (len(ctx["M"]["uv"]), 3):
                report(fn_name, V, ctx["M"])
        return r
    setattr(cloth, fn_name, w)


orig_transfer = cloth.transfer


def tr(Ms, V, M):
    r = orig_transfer(Ms, V, M)
    if r.shape == (len(M["uv"]), 3) and all(n in M["names"] for n in pieces):
        ctx["M"] = M
        report("transfer", r, M)
    return r


cloth.transfer = tr
for f in ("_clear_of_body", "_relax_stretch", "_clear_of_held", "_untangle", "_relax_strain"):
    wrap(f, lambda a: True)
orig_check = cloth.fine_start_check


def spy(M, plan, limit=cloth.FINE_START_MAX, allow=None):
    print("CHECK:", orig_check(M, plan, limit, allow) or "clean", "| untangled", ctx.get("Bp_untangled"), flush=True)
    raise SystemExit(0)


cloth.fine_start_check = spy
r = server.dress(name, garment=g, quality="final", wait=600, note=f"tess2: {g} fstrace")
print(r if isinstance(r, str) else "\n".join(x for x in r if isinstance(x, str))[:2000])
