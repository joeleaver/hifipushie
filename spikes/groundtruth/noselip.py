"""groundtruth: SIGNED nose and lip shape measures of a GNM identity (mm), for the bias question "is the solved nose
wide and round, are the lips the average's?". Every measure is taken on FIXED template vertices / the 68 standard
landmarks, so two identities are compared on the same material points; a solved head is first scaled onto the truth
(errmap's similarity: size is the cameras' business).
  alar_width        across the nostril wings (the nose region's widest pair below the tip)
  nose_base_width   landmarks 31-35 (gnm_mm's nose_width: the nostril sills)
  tip_width         across the tip 5 mm behind its front point (horizontal section through the tip)
  tip_radius_h/_v   circle through the tip's horizontal / sagittal section, 7 mm either side (large = round, blunt)
  nose_length       nasion to subnasale (vertical); nose_projection: the tip ahead of the subnasale
  nostril_show      the tip's height above the subnasale (+ = turned up: more nostril seen from the front)
  mouth_width       corner to corner; upper/lower_vermilion_mid, _quarter: red-lip heights at the midline and at the
                    quarter points; cupid_bow: the peaks above the dip; seam_curve: the lip seam's middle above the
                    corners' line (- = corners above the middle: a smile's curve; + = corners down)
table(tag, models): truth = the Part 1 direct fit."""
import json
import numpy as np
import gt

_C = {}
NAMES = ("alar_width", "nose_base_width", "tip_width", "tip_radius_h", "tip_radius_v", "nose_length", "nose_projection", "nostril_show",
         "mouth_width", "upper_vermilion_mid", "upper_vermilion_quarter", "lower_vermilion_mid", "lower_vermilion_quarter", "cupid_bow", "seam_curve")


def _sets():
    if "s" not in _C:
        G = gt.gnm()
        T, L = G["T"], G["L"]
        nose = G["gr"]["nose_region"] & G["ext"]
        tip = T[nose][np.argmin(T[nose][:, 1])]          # the most forward nose vertex (forward = -Y)
        ids = np.flatnonzero(nose)
        low = ids[(T[ids, 2] < tip[2] + 0.004) & (T[ids, 2] > L[33, 2] - 0.004)]
        aL, aR = low[np.argmax(T[low, 0])], low[np.argmin(T[low, 0])]
        hb = ids[(np.abs(T[ids, 2] - tip[2]) < 0.0022) & (T[ids, 1] < tip[1] + 0.009) & (np.abs(T[ids, 0]) < 0.012)]
        sb = ids[(np.abs(T[ids, 0]) < 0.0016) & (np.linalg.norm(T[ids][:, 1:] - tip[1:], axis=1) < 0.008)]
        _C["s"] = {"alar": (aL, aR), "hband": hb, "sband": sb, "tipv": ids[np.argmin(T[ids, 1])]}
    return _C["s"]


def _circle(P):
    A = np.c_[2 * P, np.ones(len(P))]
    x, *_ = np.linalg.lstsq(A, (P ** 2).sum(1), rcond=None)
    return float(np.sqrt(max(x[2] + x[0] ** 2 + x[1] ** 2, 0.0)))


def measures(c, scale: float = 1.0) -> dict:
    G = gt.gnm()
    S = _sets()
    V = gt.verts(c) * 1000 * scale
    L = G["WL"] @ V
    tip = V[S["tipv"]]
    H = V[S["hband"]]
    d = H[:, 1] - tip[1]
    w = []
    for sgn in (1, -1):
        m = sgn * H[:, 0] > 0.3
        o = np.argsort(d[m])
        w.append(float(np.interp(5.0, d[m][o], np.abs(H[m][o, 0]))))
    near = np.abs(H[:, 0]) < 7.0
    z = lambda i: L[i, 2]
    return {
        "alar_width": float(V[S["alar"][0], 0] - V[S["alar"][1], 0]), "nose_base_width": float(L[35, 0] - L[31, 0]),
        "tip_width": w[0] + w[1], "tip_radius_h": _circle(H[near][:, :2]), "tip_radius_v": _circle(V[S["sband"]][:, 1:]),
        "nose_length": float(z(27) - z(33)), "nose_projection": float(L[33, 1] - tip[1]), "nostril_show": float(tip[2] - z(33)),
        "mouth_width": float(L[54, 0] - L[48, 0]),
        "upper_vermilion_mid": float(z(51) - z(62)), "upper_vermilion_quarter": float(0.5 * (z(50) + z(52)) - 0.5 * (z(61) + z(63))),
        "lower_vermilion_mid": float(z(66) - z(57)), "lower_vermilion_quarter": float(0.5 * (z(67) + z(65)) - 0.5 * (z(58) + z(56))),
        "cupid_bow": float(0.5 * (z(50) + z(52)) - z(51)), "seam_curve": float(0.5 * (z(62) + z(66)) - 0.5 * (z(48) + z(54))),
    }


def ident(what, tag=None):
    if isinstance(what, str) and what.startswith("fit:"):
        return np.asarray(json.loads((gt.WORK / tag / f"fit_{what[4:]}.json").read_text())["c"])
    if isinstance(what, str) and what == "mean":
        return gt.class_mean(gt.load_scan(tag)["info"]["sex"]) if tag else None
    if isinstance(what, str):
        from hifipushie import blockin as bi, store
        return bi.identity(store.load(what))
    return np.asarray(what, float)


def compare(ct, c0, models: dict) -> dict:
    """truth ct, the start (class mean) c0, {label: identity}: per measure the truth, the start's error, each model's
    error (model - truth, the model scaled onto the truth), and the share of the needed move it made."""
    import errmap
    mt = measures(ct)
    m0 = measures(c0, errmap.rms(c0, ct)["scale"])
    out = {"truth": mt, "mean_err": {k: m0[k] - mt[k] for k in NAMES}, "models": {}}
    for lab, c in models.items():
        m = measures(c, errmap.rms(c, ct)["scale"])
        out["models"][lab] = {k: m[k] - mt[k] for k in NAMES}
    return out


def text(cmp: dict, title="") -> str:
    labs = list(cmp["models"])
    rows = [title, "| measure | truth mm | class mean - truth | " + " | ".join(f"{l} - truth" for l in labs) + " |", "|---|---|---|" + "---|" * len(labs)]
    for k in NAMES:
        rows.append(f"| {k} | {cmp['truth'][k]:.1f} | {cmp['mean_err'][k]:+.1f} | " + " | ".join(f"{cmp['models'][l][k]:+.1f}" for l in labs) + " |")
    return "\n".join(rows)


if __name__ == "__main__":
    import sys
    tag = sys.argv[1]
    ct = ident("fit:p1b3", tag)
    c0 = ident("mean", tag)
    print(text(compare(ct, c0, {a.split("=")[0]: ident(a.split("=")[-1], tag) for a in sys.argv[2:]}), f"\n#### {tag}: nose and lips, signed (mm)\n"))
