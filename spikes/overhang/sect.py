"""sect.py <out.png> <label>=<source> ...: sagittal sections of GNM's RAW upper lid (left eye) on radial ring chains:
three columns (inner, pupil, outer) per head, forward (w) across, height (v) up, rings as dots, GNM's 14.5 mm ball as
an arc; numbers from ohlib.read. Sources as lidstruct.ident; an .npz path with keys c (and e) gives both."""
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

import lidmap as lm  # noqa: E402
import lidstruct as ls  # noqa: E402
import ohlib as oh  # noqa: E402


def load(src):
    if src.startswith("npzV:"):          # raw vertices (a designed target): returns V in place of c
        z = np.load(src[5:])
        return z["c"][:170], z["V"]
    if src.endswith(".npz"):
        z = np.load(src)
        return z["c"][:170], (z["e"] if "e" in z.files and np.any(z["e"]) else None)
    return ls.ident(src), None


if __name__ == "__main__":
    out = sys.argv[1]
    items = [a.split("=", 1) for a in sys.argv[2:]]
    ch = oh.chains(10.0)
    ch7 = oh.chains(7.0)
    pick = [1, len(ch) // 2, len(ch) - 2]
    fig, ax = plt.subplots(1, len(items), figsize=(4.4 * len(items), 6.2), squeeze=False)
    for a, (lab, src) in zip(ax[0], items):
        c, e = load(src)
        if e is not None and np.ndim(e) == 2:
            V, e = e, None
        else:
            V = oh.verts(c, e)
        ctr, r = lm.eye_frame_raw(c)
        q = oh.read(V, ch7)
        for j, col in zip(pick, ("tab:green", "black", "tab:blue")):
            P = V[ch[j]] - ctr
            u = P[0, 0]
            rr = np.sqrt(max(r * r - u * u, 1e-6))
            th = np.linspace(-0.2, 1.3, 80)
            a.plot(rr * np.cos(th), rr * np.sin(th), color=col, lw=0.5, alpha=0.4)
            a.plot(P[:, 2], P[:, 1], "-o", color=col, ms=3, lw=1.2, label=f"u {u:+.0f} mm")
            a.plot(P[0, 2], P[0, 1], "o", color="red", ms=5)
        a.set_aspect("equal")
        a.set_xlim(6, 24)
        a.set_ylim(-2, 22)
        a.grid(alpha=0.3)
        a.set_title(f"{lab}\nhang {q['hang_mean']:.2f} mm (max {q['hang_max']:.2f}), turn {q['turn_mean']:.0f} deg\n"
                    f"crease ring {q['k_mode']} at {q['h_mean']:.1f} mm; |c| {np.linalg.norm(c):.1f}"
                    + (f" |e| {np.linalg.norm(e) / np.sqrt(2):.1f}/eye" if e is not None else ""), fontsize=9)
        a.legend(fontsize=7, loc="lower right")
        a.set_xlabel("forward, mm (eye frame)")
    ax[0][0].set_ylabel("height over the ball's centre, mm")
    fig.tight_layout()
    fig.savefig(out, dpi=110)
    print("wrote", out)
