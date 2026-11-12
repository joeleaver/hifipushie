"""Bend helpers (half-angle joints): bend_on, the arc frames, limb girth, the arc and shared bends. Part of rig (rig.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import rig

def bend_on(spec: dict) -> list[str]:
    """spec["rig"]["bend"]: false (none), true / left out (all: elbow, knee, shoulder, hip), or a list of joints."""
    b = (spec.get("rig") or {}).get("bend", True)
    if b is False:
        return []
    if b is True or b is None:
        return list(rig.BEND)
    bad = [x for x in b if x not in rig.BEND]
    if bad:
        raise ValueError(f"rig.bend: unknown joint(s) {bad} (have {', '.join(rig.BEND)})")
    return list(b)


def _add_bend(bones: list[dict], joints: list[str]) -> list[dict]:
    idx = {b["name"]: i for i, b in enumerate(bones)}
    extra = []
    for S in ("Left", "Right"):
        for jn in joints:
            par = rig.BEND[jn]
            i = idx.get(rig.PREFIX + S + jn)
            pi = idx.get(rig.PREFIX + (par if par == "Hips" else S + par))
            if i is None or pi is None:
                continue
            extra.append({"name": f"{rig.PREFIX}{S}{jn}Bend", "head": np.asarray(bones[i]["head"], float).copy(),
                          "parent": pi, "end": False, "src": f"bend helper at {S}{jn}",
                          "bend": {"driver": bones[i]["name"], "share": rig.BEND_SHARE, "of": bones[pi]["name"]}})
    return bones + extra


def bend_table(bones: list[dict]) -> list[dict]:
    return [{"bone": b["name"], "parent": b["bend"]["of"], "driver": b["bend"]["driver"], "share": b["bend"]["share"]}
            for b in bones if b.get("bend")]


def _sstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def arc_frames(rb: list[dict], girth: dict | None = None) -> list[dict]:
    """Per bend helper: pivot, axis u, outer direction o, zone half widths, reach, and the side mask's centre.
    girth {driver joint index: m}: the zone's length unit is max(segment length, girth / ARC_GIRTH)."""
    names = [b["name"] for b in rb]
    out = []
    hips = rb[names.index(rig.PREFIX + "Hips")]["head"] if rig.PREFIX + "Hips" in names else None
    for hi, hb in enumerate(rb):
        if not hb.get("bend"):
            continue
        dn, pn = hb["bend"]["driver"], hb["bend"]["of"]
        short = dn[len(rig.PREFIX):]
        side = "Left" if short.startswith("Left") else "Right"
        jn = short[len(side):]
        if jn not in rig.BEND_ARC or (rig.PREFIX + side + rig.ARC_CHILD[jn]) not in names:
            continue
        outer, k_out, k_in, k_reach, kind = rig.BEND_ARC[jn]
        jd, jp = names.index(dn), names.index(pn)
        piv = np.asarray(rb[jd]["head"], float)
        ch = np.asarray(rb[names.index(rig.PREFIX + side + rig.ARC_CHILD[jn])]["head"], float)
        ln = float(np.linalg.norm(ch - piv))
        ud = (ch - piv) / ln
        gr = float((girth or {}).get(jd, 0.0))
        stub = jn in rig.ARC_ROOTS and gr > rig.ARC_GIRTH * ln
        unit = gr / rig.ARC_STUB_UNIT if stub else ln
        up = piv - np.asarray(rb[jp]["head"], float)
        up /= max(np.linalg.norm(up), 1e-9)
        u = ud if kind == "ball" else (ud + up) / max(np.linalg.norm(ud + up), 1e-9)
        if isinstance(outer, str):  # the convex side of the rest bend
            o = -(ud - (ud @ up) * up)
        else:
            o = np.asarray(outer, float)
        o = o - (o @ u) * u
        o /= max(np.linalg.norm(o), 1e-9)
        out.append({"helper": hi, "driver": jd, "of": jp, "pivot": piv, "u": u, "o": o, "len": ln,
                    "outer": k_out * unit, "inner": k_in * unit, "stub": gr if stub else None, "reach": k_reach * unit, "joint": jn,
                    "side": (1.0 if side == "Left" else -1.0), "mid": None if hips is None else float(hips[0])})
    return out


def limb_girth(rb: list[dict], V: np.ndarray, J: np.ndarray, W: np.ndarray) -> dict:
    """{bend driver joint index: girth (m)}: the median distance from the segment's axis (joint -> its ARC_CHILD) of
    the vertices on the segment's middle half whose biggest weight is that joint or below it in the chain."""
    names = [b["name"] for b in rb]
    V = np.asarray(V, float)
    top = np.asarray(J)[np.arange(len(V)), np.argmax(W, 1)]
    out = {}
    for b in rb:
        if not b.get("bend"):
            continue
        dn = b["bend"]["driver"]
        short = dn[len(rig.PREFIX):]
        side = "Left" if short.startswith("Left") else "Right"
        jn = short[len(side):]
        if jn not in rig.ARC_CHILD or (rig.PREFIX + side + rig.ARC_CHILD[jn]) not in names:
            continue
        jd = names.index(dn)
        below = {jd}
        for i, c in enumerate(rb):  # the chain under the joint (rb lists parents first) and its twist joints
            if c["parent"] in below:
                below.add(i)
        piv = np.asarray(rb[jd]["head"], float)
        ax = np.asarray(rb[names.index(rig.PREFIX + side + rig.ARC_CHILD[jn])]["head"], float) - piv
        ln = float(np.linalg.norm(ax))
        if ln < 1e-6:
            continue
        d = V - piv
        t = (d @ ax) / ln ** 2
        sel = np.isin(top, list(below)) & (t > 0.25) & (t < 0.75)
        if sel.sum() >= 8:
            # the lower quartile: a stub's middle half reaches into the fillet and the belly around it
            out[jd] = float(np.percentile(np.linalg.norm(d[sel] - np.outer(t[sel], ax), axis=1), 25))
    return out


def _arc_bend(rb: list[dict], V: np.ndarray, J: np.ndarray, W: np.ndarray):
    """BEND_ARC's repaint (see above) of every hinge with a helper; vertices out of a zone keep their weights."""
    fr = arc_frames(rb, limb_girth(rb, V, J, W))
    if not fr:
        return J, W
    fam = np.arange(len(rb))
    for i, b in enumerate(rb):
        if b.get("twist"):
            fam[i] = b["parent"]
    V = np.asarray(V, float)
    D = np.zeros((len(V), len(rb)))
    np.add.at(D, (np.repeat(np.arange(len(V)), J.shape[1]), np.asarray(J).ravel()), np.asarray(W, float).ravel())
    geo = []
    for f in fr:
        d = V - f["pivot"]
        s = d @ f["u"]
        q = d - s[:, None] * f["u"]
        geo.append((s, q, np.linalg.norm(q, axis=1)))
    for f, (s, q, rho) in zip(fr, geo):  # a stub's body skin: the parent's, with every weight of its limb's chain
        if not f["stub"]:
            continue
        chain = {f["driver"], f["helper"]}
        for i, b in enumerate(rb):  # (rb lists parents first)
            if b["parent"] in chain and i != f["helper"]:
                chain.add(i)
        cols = np.array(sorted(chain))
        g = _sstep((rho - rig.ARC_BODY[0] * f["stub"]) / ((rig.ARC_BODY[1] - rig.ARC_BODY[0]) * f["stub"]))
        g *= 1 - _sstep((np.abs(s) - rig.ARC_AXIAL * f["outer"]) / f["outer"])
        if f["mid"] is not None:
            g *= _sstep(1.0 + ((V[:, 0] - f["mid"]) * f["side"]) / rig.ARC_MID)
        D[:, f["of"]] += g * D[:, cols].sum(1)
        D[:, cols] *= (1 - g)[:, None]
    for f, (s, q, rho) in zip(fr, geo):
        c = (q @ f["o"]) / np.maximum(rho, 1e-9)
        L = f["inner"] + (f["outer"] - f["inner"]) * (1 + c) / 2
        phi = _sstep(s / (2 * L) + 0.5)
        m = (1 - _sstep((rho - 0.7 * f["reach"]) / (0.3 * f["reach"]))) if not f["stub"] else np.ones(len(V))
        if f["stub"]:
            b0, b1 = rig.ARC_BODY[0] * f["stub"], rig.ARC_BODY[1] * f["stub"]
            phi = phi * (1 - _sstep((rho - b0) / (b1 - b0)))  # (else the repaint hands the body skin back)
        m *= 1 - _sstep((np.abs(s) - rig.ARC_AXIAL * f["outer"]) / f["outer"])
        if f["mid"] is not None:  # this side of the body only (a hip's reach crosses to the other thigh); a stub's
            # repaint runs on across the midline (half of the leak it clears stayed there: a crack up the belly)
            m *= _sstep((1.0 if f["stub"] else 0.5) + ((V[:, 0] - f["mid"]) * f["side"]) / rig.ARC_MID)
        famp, famd = fam == f["of"], fam == f["driver"]
        wp, wd, wh = D[:, famp].sum(1), D[:, famd].sum(1), D[:, f["helper"]]
        S = wp + wd + wh
        sel = np.flatnonzero((m > 1e-4) & (S > 1e-6))
        if not len(sel):
            continue
        ph, mm, Ss = phi[sel], m[sel], S[sel]
        np_, nh, nd = Ss * np.maximum(0, 1 - 2 * ph), Ss * (1 - np.abs(2 * ph - 1)), Ss * np.maximum(0, 2 * ph - 1)
        for mask, w_old, w_new, own in ((famp, wp, np_, f["of"]), (famd, wd, nd, f["driver"])):
            cols = np.flatnonzero(mask)
            old = D[np.ix_(sel, cols)]
            share = np.where(w_old[sel, None] > 1e-9, old / np.maximum(w_old[sel, None], 1e-12),
                             (cols == own)[None, :].astype(float))
            D[np.ix_(sel, cols)] = (1 - mm[:, None]) * old + mm[:, None] * share * w_new[:, None]
        D[sel, f["helper"]] = (1 - mm) * wh[sel] + mm * nh
    k = J.shape[1]
    order = np.argsort(-D, axis=1, kind="stable")[:, :k]
    Wk = np.take_along_axis(D, order, 1)
    Wk /= np.maximum(Wk.sum(1, keepdims=True), 1e-12)
    Jk = np.where(Wk > 0, order, 0)
    return Jk.astype(np.asarray(J).dtype), Wk


def _share_bend(rb: list[dict], J: np.ndarray, W: np.ndarray, V: np.ndarray | None = None):
    """The bend helpers' weights: BEND_WEIGHTS "arc" repaints each hinge from geometry (`_arc_bend`, needs V); else
    the helpers take each vertex's overlap between a hinge's two bones (parent and joint, their twist joints
    counted as them): 2 x min(w parent, w joint) x BEND_TAKE, half from each side."""
    hs = [(i, b) for i, b in enumerate(rb) if b.get("bend")]
    if not hs:
        return J, W
    if rig.BEND_WEIGHTS == "arc" and V is not None:
        return _arc_bend(rb, V, J, W)
    names = [b["name"] for b in rb]
    fam = np.arange(len(rb))
    for i, b in enumerate(rb):
        if b.get("twist"):
            fam[i] = b["parent"]
    J = np.asarray(J).copy()
    W = np.asarray(W, np.float64).copy()
    kk = J.shape[1]
    J2 = np.concatenate([J, np.zeros((len(J), 1), J.dtype)], 1)
    W2 = np.concatenate([W, np.zeros((len(W), 1))], 1)
    FJ = fam[J]
    for hi, hb in hs:
        jd, jp = names.index(hb["bend"]["driver"]), names.index(hb["bend"]["of"])
        wd = np.where(FJ == jd, W, 0).sum(1)
        wp = np.where(FJ == jp, W, 0).sum(1)
        take = 2 * np.minimum(wd, wp) * rig.BEND_TAKE
        sel = np.flatnonzero((take > 1e-4) & (W2[:, kk] == 0))
        if not len(sel):
            continue
        for fb, wf in ((jd, wd), (jp, wp)):  # half from each side, in proportion over its (twist) bones
            m = (FJ[sel] == fb)
            frac = np.where(m, W[sel] / np.maximum(wf[sel, None], 1e-12), 0.0)
            W2[sel, :kk] -= frac * (take[sel, None] / 2)
        J2[sel, kk], W2[sel, kk] = hi, take[sel]
    W2 = np.maximum(W2, 0.0)
    order = np.argsort(-W2, axis=1, kind="stable")[:, :kk]  # (the smallest of five goes; renormalised)
    Jk = np.take_along_axis(J2, order, 1)
    Wk = np.take_along_axis(W2, order, 1)
    Wk /= np.maximum(Wk.sum(1, keepdims=True), 1e-12)
    Jk[Wk <= 0] = 0
    return Jk, Wk
