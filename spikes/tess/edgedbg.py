"""edgedbg.py <model> <garment>: the place stage with cloth._lay_on_edge instrumented (per band: sewn partners'
pieces, x range, the laid band's extent and its longest edge)."""
import os, sys
import numpy as np
from hifipushie import cloth, server

orig = cloth._lay_on_edge


def dbg(X, M, nm):
    Y = orig(X, M, nm)
    k = M["names"].index(nm)
    sel = np.where(M["piece"] == k)[0]
    sw = np.asarray(M["sew"]).reshape(-1, 2)
    part = sorted({M["names"][M["piece"][b]] for a, b in sw if M["piece"][a] == k and M["piece"][b] != k}
                  | {M["names"][M["piece"][a]] for a, b in sw if M["piece"][b] == k and M["piece"][a] != k})
    F = M["F"][np.isin(M["F"][:, 0], sel)]
    el = np.linalg.norm(Y[F[:, 0]] - Y[F[:, 1]], axis=1)
    print(f"{nm}: partners {part}, uv x {M['uv'][sel, 0].min():.3f}..{M['uv'][sel, 0].max():.3f}, y "
          f"{M['uv'][sel, 1].min():.3f}..{M['uv'][sel, 1].max():.3f}; laid bbox {np.round(Y[sel].min(0), 3).tolist()} .. "
          f"{np.round(Y[sel].max(0), 3).tolist()}, longest edge {el.max() * 1000:.0f} mm, nan {int(np.isnan(Y[sel]).sum())}",
          flush=True)
    return Y


cloth._lay_on_edge = dbg
r = server.check_garment(sys.argv[1], sys.argv[2], stages=["place"], save=os.path.join(os.environ["T"], "out", "edgedbg.png"))
print((r if isinstance(r, str) else "\n".join(x for x in r if isinstance(x, str)))[-3000:])
