"""gnmnative: the lids against the eyeball, per ring, on a model's head with our 12 mm ball (eye_radius, as stored)
and with GNM's own (the key dropped).   standoff.py <model> [<model> ...]   or   standoff.py class:male class:female

Per variant: the ball (centre's depth behind the upper-lid margin, radius), GNM's eye numbers, the stand-off
|P - c| - r of GNM's lid rings (lidrings: 0 = the margin, negative = the socket lining behind it, positive = the lid's
skin) over the middle of the eye (|u| < 7 mm), upper and lower halves, both eyes' mean; the opening (base.eye_opening:
where the ball shows in front of the skin), iris and white; the profile (the cornea's apex ahead of the lid margins)."""
import json
import sys

import numpy as np

from hifipushie import base as basemod
from hifipushie import lidrings, onemesh, store


def head_of(b):
    return onemesh.head_rest(b) if onemesh.applies(b) else None


def measure(b, spec=None):
    ht = head_of(b)
    V = np.asarray(ht["gnm_world"], float)  # every GNM vertex by its own id (ht["verts"] leaves the mouth sock out)
    t = lidrings.topo()
    mir = lidrings.mirror()
    g = basemod._gnm_data()
    T = g["template_vertex_positions"].astype(float)
    J = g["template_joint_positions"].astype(float)
    fwd = np.asarray(ht["forward"], float)
    r = float(ht["eye_r"])
    out = {"r_mm": r * 1000, "eye_gnm": ht.get("eye_gnm")}
    rows = {}
    for k in range(-3, 6):
        ids = t["loops"][k]
        P0 = (T[ids] - J[2]) * 1000
        mid = np.abs(P0[:, 0]) < 7.0
        for half, sel in (("up", P0[:, 1] > 0.5), ("lo", P0[:, 1] < -0.5)):
            vals = []
            for c, idd in ((ht["eyes"][0], ids), (ht["eyes"][1], mir[ids])):
                idd = idd[mid & sel]
                idd = idd[idd < len(V)]
                if len(idd):
                    vals.append((np.linalg.norm(V[idd] - c, axis=1) - r) * 1000)
            if vals:
                v = np.concatenate(vals)
                rows[(k, half)] = (float(v.mean()), float(v.min()), float(v.max()))
    out["rings"] = rows
    op = basemod.eye_opening(ht)
    out["opening"] = op
    eg = ht.get("eye_gnm")
    drawn = (((spec or {}).get("skin") or {}).get("eyes") or {}).get("iris_size")
    iris = 1000 * float(drawn) if drawn else (2000 * eg["limbus"] if eg else 2 * 0.51 * 0.985 * r * 1000)
    out["iris_mm"] = iris
    # profile: how far the ball's front (and the cornea's apex) stands ahead of the lid margins at the pupil's column
    c = np.asarray(ht["eyes"][0], float)
    m_up = V[t["loops"][0]]
    P0 = (T[t["loops"][0]] - J[2]) * 1000
    col = np.abs(P0[:, 0]) < 2.5
    up = m_up[col & (P0[:, 1] > 0)]
    lo = m_up[col & (P0[:, 1] < 0)]
    ahead = lambda P: float(((P - c) @ fwd).mean() * 1000)  # noqa: E731
    apex = (eg["apex"] if eg else r) * 1000
    if not eg and b.get("cornea"):
        apex = r * 1000 * 1.09
    out["profile"] = {"ball_front": r * 1000, "apex": apex, "upper_margin": ahead(up), "lower_margin": ahead(lo),
                      "apex_ahead_of_upper": apex - ahead(up), "apex_ahead_of_lower": apex - ahead(lo)}
    lm = np.asarray(ht["lm68"], float)
    out["centre_behind_nasion_mm"] = float(((lm[27] - c) @ fwd) * 1000)
    return out


def show(tag, q):
    print(f"\n== {tag}: ball r {q['r_mm']:.2f} mm, centre {q['centre_behind_nasion_mm']:.1f} mm behind the nasion")
    eg = q["eye_gnm"]
    if eg:
        print("   GNM eye: limbus r %.2f, iris disc r %.2f at depth %.2f, pupil r %.2f (%.2f of the iris), cornea r %.2f, apex %.2f mm"
              % (eg["limbus"] * 1000, eg["iris_r"] * 1000, eg["iris_depth"] * 1000, eg["pupil_r"] * 1000, eg["pupil"],
                 eg["cornea_r"] * 1000, eg["apex"] * 1000))
    print("   ring:      " + " ".join(f"{k:+6d}" for k in range(-3, 6)))
    for half in ("up", "lo"):
        print(f"   {half} mean:  " + " ".join(f"{q['rings'][(k, half)][0]:6.2f}" if (k, half) in q["rings"] else "     -" for k in range(-3, 6)))
        print(f"   {half} min:   " + " ".join(f"{q['rings'][(k, half)][1]:6.2f}" if (k, half) in q["rings"] else "     -" for k in range(-3, 6)))
    op = [o for o in q["opening"] if o]
    if op:
        w, h = np.mean([o["w"] for o in op]), np.mean([o["h"] for o in op])
        top, bot = np.mean([o["top"] for o in op]), np.mean([o["bottom"] for o in op])
        ir = q["iris_mm"] / 2
        print(f"   opening {w:.1f} x {h:.1f} mm (top {top:.1f}, bottom {bot:.1f} from the centre); iris {2 * ir:.2f} mm: "
              f"upper lid covers {ir - top:+.1f} mm of it, lower {ir - bot:+.1f}; white each side ~{(w - 2 * ir) / 2:.1f} mm")
    p = q["profile"]
    print(f"   profile: ball front {p['ball_front']:.2f}, apex {p['apex']:.2f}; upper margin {p['upper_margin']:.2f}, lower "
          f"{p['lower_margin']:.2f} mm ahead of the centre -> apex ahead of the upper margin {p['apex_ahead_of_upper']:+.2f}, "
          f"of the lower {p['apex_ahead_of_lower']:+.2f} mm")


def main():
    res = {}
    for name in sys.argv[1:]:
        if name.startswith("class:"):
            from hifipushie import blockin
            src = store.load("tn_T00" if name.endswith("female") else "gj_G00")
            sp = json.loads(json.dumps(src))
            D = blockin.data()
            blockin.set_identity(sp, np.asarray(D["m_f"] if name.endswith("female") else D["m_m"], float))
        else:
            sp = store.load(name)
        b = sp["base"]
        hd = b["head"]
        variants = {}
        if hd.get("eye_radius"):
            variants[f"eye_radius {hd['eye_radius']} (ours)"] = b
        nat = json.loads(json.dumps(b))
        nat["head"].pop("eye_radius", None)
        variants["GNM's own ball"] = nat
        # GNM alone (its template + this identity, no body, no style): the stand-off its own design has
        g = basemod._gnm_data()
        ci = basemod._gnm_coeffs(g["identity_names"], hd.get("identity"))
        Vr = g["template_vertex_positions"].astype(float) + np.tensordot(ci, g["vertex_identity_basis"], 1)
        eg = basemod.gnm_eyes(Vr, g)
        t, mir = lidrings.topo(), lidrings.mirror()
        T, J = g["template_vertex_positions"].astype(float), g["template_joint_positions"].astype(float)
        print(f"\n== {name} | RAW GNM (its identity alone): ball r {eg[0]['r'] * 1000:.2f} mm")
        for half in ("up", "lo"):
            row = []
            for k in range(-3, 6):
                ids = t["loops"][k]
                P0 = (T[ids] - J[2]) * 1000
                sel = (np.abs(P0[:, 0]) < 7.0) & ((P0[:, 1] > 0.5) if half == "up" else (P0[:, 1] < -0.5))
                v = np.r_[np.linalg.norm(Vr[ids[sel]] - eg[0]["c"], axis=1) - eg[0]["r"],
                          np.linalg.norm(Vr[mir[ids[sel]]] - eg[1]["c"], axis=1) - eg[1]["r"]] * 1000
                row.append(v.mean())
            print(f"   {half} mean:  " + " ".join(f"{x:6.2f}" for x in row))
        for tag, bb in variants.items():
            q = measure(bb, sp)
            show(f"{name} | {tag}", q)
            res[f"{name}|{tag}"] = {"r_mm": q["r_mm"], "rings": {f"{k}{h}": v for (k, h), v in q["rings"].items()},
                                    "profile": q["profile"], "opening": q["opening"], "iris_mm": q["iris_mm"]}
    json.dump(res, open("/mnt/data/hifipushie/gnmnative/out/standoff.json", "w"), indent=1, default=float)


main()
