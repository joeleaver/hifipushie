"""foldopt.py: FORM an upper-lid overhang on purpose (library + CLI). Everything is linear in GNM's coefficients, so the
best coefficients for a wanted fold are a closed-form constrained least squares, no sampling:

  x = [dc (170 identity), e_L (ne left-eye expression), e_R (ne, tied to e_L by mirror symmetry)]
  maximise   hang(x) = mean over the lid's columns, both eyes, of  v[ka] - v[kb]     (ring kb's skin BELOW ring ka's)
  subject to v[ka] - v[0] = H               (the crease ring ka at height H over the margin; mean over columns)
             w[kb] - w[ka] >= gap           (the hanging skin in FRONT of the platform: an overhang, not a pinch)
  cost       lam |dc|^2 + lam_e |e|^2  +  |held verts moved / hold|^2  +  |lid margins moved / 0.05|^2
Solved as: minimise cost - mu * hang  (mu sweeps the frontier), or cost s.t. hang = d exactly.

CLI: foldopt.py <identity source> [ka=5] [kb=7] [H=4.7] [expr=0|n comps] [hold=1] [lam=1] [d=0.5,1,1.5,2]
prints the frontier (overhang measured on the TRUE mesh by ohlib.read, |dc|, |e|, what moved)."""
import sys

import numpy as np
from scipy.spatial import cKDTree

import ohlib as oh
from hifipushie import gnm_controls as gc

g = oh.g
NC = 170
MIR = cKDTree(g["T"]).query(g["T"] * [-1, 1, 1])[1]
EL = [i for i, n in enumerate(g["ex_names"]) if n.startswith("left_eye")]
ER = [i for i, n in enumerate(g["ex_names"]) if n.startswith("right_eye")]
_C = {}


def setup(ne=0, umax=10.0):
    """Shared matrices: B (nx, V, 3) mm per unit of x = [identity 170, eye expression ne (left + mirrored right as ONE
    coefficient each)], chains (left) and their mirror (right), column weights."""
    key = (ne, umax)
    if key in _C:
        return _C[key]
    B = [g["IB"][:NC].astype(np.float64) * 1000.0]
    if ne:
        B.append((g["EB"][EL[:ne]].astype(np.float64) + g["EB"][ER[:ne]].astype(np.float64)) * 1000.0)
    B = np.concatenate(B)
    ch = oh.chains(umax)
    u = oh.T[ch[:, 0], 0] - oh.JL[0]
    wc = np.clip(1.5 - np.abs(u) / (umax / 1.5), 0.15, 1.0)     # full over the middle, tapering to the corners
    wc = wc / wc.sum()
    _C[key] = {"B": B, "ch": ch, "chR": MIR[ch], "wc": wc, "ne": ne}
    return _C[key]


def rows(S, ka, kb):
    """Linear rows (nx,) of the mean-over-columns quantities, both eyes averaged, and their template values."""
    B, ch, chR, wc = S["B"], S["ch"], S["chR"], S["wc"]

    def lin(k, ax):
        return 0.5 * (np.tensordot(B[:, ch[:, k], ax], wc, 1) + np.tensordot(B[:, chR[:, k], ax], wc, 1))

    def tem(k, ax):
        return 0.5 * (oh.T[ch[:, k], ax] @ wc + oh.T[chR[:, k], ax] @ wc)
    # stand-off of ring ka from the eyeball (linearised along each vertex's template direction from the ball's centre;
    # the ball itself is held, so its own motion is left out)
    ctrL = oh.T[g["groups"]["left_eye"] & g["groups"]["scleras"]].mean(0)
    nL = oh.T[ch[:, ka]] - ctrL
    r0 = np.linalg.norm(nL, axis=1)
    nL /= r0[:, None]
    nR = nL * [-1, 1, 1]
    so = 0.5 * (np.einsum("cna,na,n->c", B[:, ch[:, ka]], nL, wc) + np.einsum("cna,na,n->c", B[:, chR[:, ka]], nR, wc))
    return {"so": so, "so0": float(r0 @ wc) - 14.5,
            "hang": lin(ka, 1) - lin(kb, 1), "hang0": tem(ka, 1) - tem(kb, 1),
            "H": lin(ka, 1) - lin(0, 1), "H0": tem(ka, 1) - tem(0, 1),
            "gap": lin(kb, 2) - lin(ka, 2), "gap0": tem(kb, 2) - tem(ka, 2)}


def hold_gram(S, hold=1.0, mh=0.05, free_rings=(1, 11), face_only=False):
    """Q of the quadratic cost for moving what is HELD: every exterior skin vertex and the eyeballs at `hold` mm, the
    lid margins (ring 0, both lids, both eyes) at mh mm, the upper lids' rings free_rings FREE."""
    key = ("Q", S["ne"], hold, mh, free_rings)
    if key in _C:
        return _C[key]
    B = S["B"]
    ring = oh.t["ring"]
    ringR = ring[MIR]
    rr = np.minimum(np.abs(ring), np.abs(ringR))
    up = (oh.T[:, 1] > oh.JL[1] + 0.5)
    free = (rr >= free_rings[0]) & (rr <= free_rings[1]) & up & (np.minimum(ring, ringR) > 0)
    hm = (g["groups"]["skin_exterior"] | g["groups"]["eyes"]) & ~free
    w = np.where(rr == 0, 1.0 / mh, 1.0 / hold)[hm]
    A = (B[:, hm] * w[None, :, None]).reshape(len(B), -1)
    _C[key] = (A @ A.T, hm)
    return _C[key]


def solve(c0, ka=5, kb=7, H=None, d=1.0, gap=0.6, ne=0, hold=1.0, lam=1.0, lam_e=1.0, e0=None, umax=10.0, about="dc",
          free=(1, 11), gap_eq=False, so=None):
    """The least-cost coefficients giving a front-view overhang of d mm (ring kb's skin d below ring ka's, gap mm in front
    of it), the crease ring ka at H mm over the margin (None: where it is). Returns (c1, e1 (383) or None, info)."""
    S = setup(ne, umax)
    R = rows(S, ka, kb)
    Q, hm = hold_gram(S, hold, free_rings=tuple(free))
    nx = len(S["B"])
    x0 = np.zeros(nx)
    c0 = np.asarray(c0, float)[:NC]
    x0[:NC] = c0
    P = np.diag(np.r_[np.full(NC, lam), np.full(ne, lam_e)])
    # equality rows on the absolute values: template + row @ (x0 + dx) = target
    A, b = [R["hang"]], [d - (R["hang0"] + R["hang"] @ x0)]
    if H is not None:
        A.append(R["H"])
        b.append(H - (R["H0"] + R["H"] @ x0))
    if so is not None:          # the crease ring this far off the ball (the platform's top lies on it)
        A.append(R["so"])
        b.append(so - (R["so0"] + R["so"] @ x0))
    lin = np.zeros(nx)
    if about == "c":            # the prior on |c0 + dc| (GNM's N(0, I)) rather than on the move
        lin[:NC] = -lam * c0

    def kkt(A, b):
        A = np.array(A)
        K = np.block([[Q + P, A.T], [A, np.zeros((len(A), len(A)))]])
        return np.linalg.solve(K, np.r_[lin, b])[:nx]
    dx = kkt(A, b)
    g_now = R["gap0"] + R["gap"] @ (x0 + dx)
    if g_now < gap or gap_eq:
        dx = kkt(A + [R["gap"]], b + [gap - (R["gap0"] + R["gap"] @ x0)])
    c1 = c0 + dx[:NC]
    e1 = None
    if ne:
        e1 = np.zeros(len(g["ex_names"]))
        e1[EL[:ne]] = dx[NC:]
        e1[ER[:ne]] = dx[NC:]
    mv = np.tensordot(dx, S["B"][:, hm], 1)
    info = {"dc": float(np.linalg.norm(dx[:NC])), "c": float(np.linalg.norm(c1)), "e": float(np.linalg.norm(dx[NC:])),
            "held_rms": float(np.sqrt((mv ** 2).sum(1).mean())), "held_max": float(np.linalg.norm(mv, axis=1).max()),
            "hang_lin": float(R["hang0"] + R["hang"] @ (x0 + dx)), "H_lin": float(R["H0"] + R["H"] @ (x0 + dx)),
            "gap_lin": float(R["gap0"] + R["gap"] @ (x0 + dx)), "so_lin": float(R["so0"] + R["so"] @ (x0 + dx)), "dx": dx}
    return c1, e1, info


if __name__ == "__main__":
    import lidstruct as ls
    src = sys.argv[1]
    kw = dict(a.split("=", 1) for a in sys.argv[2:])
    c0 = ls.ident(src)
    ne = int(kw.get("expr", 0))
    ch = oh.chains(7.0)
    print(f"{src}: |c| {np.linalg.norm(c0):.2f}; as is: {oh.fmt(oh.read(oh.verts(c0), ch))}")
    kas = [int(x) for x in kw.get("ka", "5").split(",")]
    for ka in kas:
        kb = int(kw["kb"]) if "kb" in kw else ka + 2
        for H in [None if x == "-" else float(x) for x in kw.get("H", "-").split(",")]:
            for hold in [float(x) for x in kw.get("hold", "1").split(",")]:
                print(f" ka {ka} kb {kb} H {H} hold {hold} expr {ne} lam {kw.get('lam', 1)}")
                for d in [float(x) for x in kw.get("d", "0,0.5,1,1.5,2").split(",")]:
                    c1, e1, I = solve(c0, ka, kb, H, d, ne=ne, hold=hold, lam=float(kw.get("lam", 1)), lam_e=float(kw.get("lam_e", 1)),
                                      gap=float(kw.get("gap", 0.6)), gap_eq=kw.get("gapeq") == "1",
                                      free=[int(x) for x in kw.get("free", "1,11").split(",")],
                                      so=float(kw["so"]) if "so" in kw else None)
                    q = oh.read(oh.verts(c1, e1), ch)
                    if "save" in kw:
                        import os
                        np.savez(os.environ["G"] + f"/out/{kw['save']}_ka{ka}_h{hold:g}_e{ne}_d{d:g}.npz", c=c1,
                                 e=e1 if e1 is not None else np.zeros(383))
                    print(f"   d {d:3.1f}: |dc| {I['dc']:5.2f} |c| {I['c']:5.2f} |e| {I['e']:4.2f} held rms {I['held_rms']:.2f} max {I['held_max']:.2f} "
                          f"gap {I['gap_lin']:.2f} H {I['H_lin']:.2f} so {I['so_lin']:.2f} | {oh.fmt(q)}")
