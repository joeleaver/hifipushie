"""The attach report (ring loops, girths against ANSUR), and weights. Part of the one mesh (onemesh.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import onemesh
from .onemesh import _reference, asset
from . import onemesh_head
from .onemesh_head import head_desc, head_rest

def _ring_loop(k: int) -> np.ndarray:
    """GNM's neck ring k as an ordered closed loop of GNM vertex ids."""
    key = ("ring_loop", int(k))
    if key not in onemesh._CACHE:
        from . import base_identity
        g = base_identity._gnm_data()
        lev = asset()["g_lev"].astype(int)[:len(g["template_vertex_positions"])]
        ids = set(int(v) for v in np.flatnonzero(lev == k))
        adj = {v: set() for v in ids}
        for q in np.asarray(g["quads"]):
            for a_, b_ in zip(q, np.roll(q, -1)):
                if int(a_) in ids and int(b_) in ids:
                    adj[int(a_)].add(int(b_))
                    adj[int(b_)].add(int(a_))
        loop = [min(ids)]
        prev = None
        while True:
            nx = [w for w in adj[loop[-1]] if w != prev and w not in loop[1:]]
            nx = [w for w in nx if w != loop[0]] or nx
            if not nx or nx[0] == loop[0]:
                break
            prev = loop[-1]
            loop.append(nx[0])
        onemesh._CACHE[key] = np.array(loop, int)
    return onemesh._CACHE[key]


def _girth(X: np.ndarray, rings=range(14, 25)) -> tuple:
    """(the least loop length over GNM's neck rings, its ring) on GNM vertices X (17821, 3)."""
    L = [(float(np.linalg.norm(X[lp] - np.roll(X[lp], -1, 0), axis=1).sum()), k) for k in rings for lp in [_ring_loop(k)]]
    return min(L)


def attach_report(base: dict) -> dict:
    """How the head sits on the body, as numbers with their anthropometric ranges: {"native", "size" (the head over
    GNM's own evaluation), "head_height", "stature", "heads_tall", "eyes_apart", "eyeball_r" (m), "chin_over_pit",
    "top_over_pit" (m; the pit of the throat = the body's suprasternale), "neck": {"head": the head's neck girth at its
    narrowest ring, "body": the body's own neck there, "ring": GNM's girth at the seam ring}, "checks": [{"name",
    "value", "range" (lo, hi), "ok"}], "flags": [text], "ignored": [keys with no effect], "text"}. A wrong neck or
    head-on-shoulders proportion is a FLAG here, not something to find by eye."""
    from . import base_identity
    g = base_identity._gnm_data()
    hd = head_desc(base)
    tpl = onemesh_head.template(base)
    ht = head_rest(base)
    a = asset()
    nat = hd["bound"].get("native")
    W = np.asarray(ht["gnm_world"], float)
    skin = np.asarray(g["skin"], bool) & (np.asarray(g["groups"]["skin_exterior"]) > 0.5)
    lev = a["g_lev"].astype(int)[:len(skin)]
    ci = base_identity._gnm_coeffs(g["identity_names"], hd.get("identity") or {}, hd.get("seed"), hd.get("spread", 1.0))
    Vg = (g["template_vertex_positions"] + np.tensordot(ci, g["vertex_identity_basis"], 1)).astype(float)
    m = skin & (lev >= _reference()["meta"]["RING"] + 12)
    size = float(np.sqrt(((W[m] - W[m].mean(0)) ** 2).sum() / ((Vg[m] - Vg[m].mean(0)) ** 2).sum()))
    P = np.asarray(tpl["P"], float)
    stature = float(P[:, 2].max() - P[:, 2].min())
    chin = float(ht["lm68"][8][2])
    hh = float(W[skin][:, 2].max() - chin)
    mh_rows = np.flatnonzero(a["m2f"] >= 0)
    pit = float(P[int(np.flatnonzero(mh_rows == onemesh.SUPRASTERNALE)[0]), 2])
    bd = onemesh.bound(hd["bound"]["body"], float(hd["bound"].get("toward", 1.0)))
    gh, kr = _girth(W)
    lp = _ring_loop(kr)
    gb = float(np.linalg.norm(bd["B"][lp] - np.roll(bd["B"][lp], -1, 0), axis=1).sum())
    l13 = _ring_loop(_reference()["meta"]["RING"])
    params = hd["bound"]["body"]
    sex = float(np.clip(params.get("sex", 1.0), 0, 1))
    age = float(params.get("age", 25))
    def expect(k):  # (the measure's mean for this sex and stature, its sd)
        w = [(v0 * (stature / s0) ** al, sd_) for (v0, al, sd_), s0 in zip(onemesh.ANSUR[k], onemesh.ANSUR_STATURE)]
        mu_ = (1 - sex) * w[0][0] + sex * w[1][0]
        return mu_, mu_ * ((1 - sex) * w[0][1] + sex * w[1][1])
    out = {"native": bool(nat), "size": size, "head_height": hh, "stature": stature, "heads_tall": stature / hh,
           "eyes_apart": float(np.linalg.norm(np.asarray(ht["eyes"][0]) - np.asarray(ht["eyes"][1]))), "eyeball_r": float(ht["eye_r"]),
           "chin_over_pit": chin - pit, "top_over_pit": float(P[:, 2].max()) - pit,
           "neck": {"head": gh, "body": gb, "ring": float(np.linalg.norm(W[l13] - np.roll(W[l13], -1, 0), axis=1).sum())},
           "ignored": [], "checks": [], "flags": []}

    def check(name, value, mu_, sd_, why):
        lo, hi = mu_ - onemesh.SD_FLAG * sd_, mu_ + onemesh.SD_FLAG * sd_
        ok = bool(lo <= value <= hi)
        out["checks"].append({"name": name, "value": float(value), "expected": float(mu_), "sd": float(sd_),
                              "z": float((value - mu_) / sd_), "range": (float(lo), float(hi)), "ok": ok})
        if not ok:
            out["flags"].append(f"{name} {value * 1000:.0f} mm is outside {lo * 1000:.0f} .. {hi * 1000:.0f} (ANSUR for this sex and "
                                f"stature: {mu_ * 1000:.0f} +- {sd_ * 1000:.0f}): {why}")
    mh_, sh_ = expect("head_height")
    check("head height", hh, mh_, sh_, "the head is the wrong size for this stature (base.body.height / age, or base.head.size)")
    mt_, st_ = expect("top_over_pit")
    check("top of head over the pit of the throat", out["top_over_pit"], mt_, st_, "head + neck too long or too short over the shoulders")
    check("chin over the pit of the throat", out["chin_over_pit"], mt_ - mh_, float(np.hypot(st_, sh_)),
          "the neck is too long or too short in front")
    mu, sd = expect("neck_girth")
    check("neck girth", gh, mu, sd, "the head's neck is too thick or too thin for this body (GNM's identity moves the neck with "
          "no picture read)")
    mu, sd = mu / stature, sd / stature
    out["neck_conflict"] = gh / gb - 1.0
    zh, zb = (gh / stature - mu) / sd, (gb / stature - mu) / sd
    out["neck_z"] = {"head": float(zh), "body": float(zb)}
    if abs(out["neck_conflict"]) > onemesh.NECK_CONFLICT:
        # RULE: the neck from the seam ring up is the HEAD's (GNM's, with its identity); the body's neck base is laid on
        # it whatever the difference. A difference past NECK_CONFLICT is reported with WHICH side is unusual for the
        # stature (ANSUR), so the caller changes that side: it is never settled silently by inflating or thinning.
        who = ("the BODY's own neck is the unusual one" if abs(zb) > abs(zh) + 0.5 else
               "the HEAD's neck is the unusual one" if abs(zh) > abs(zb) + 0.5 else "both are off the mean, opposite ways")
        out["flags"].append(f"NECK CONFLICT: the head's neck is {100 * out['neck_conflict']:+.0f} % against the body's own "
                            f"({gh * 1000:.0f} / {gb * 1000:.0f} mm; {zh:+.1f} / {zb:+.1f} sd of ANSUR for this stature): {who}"
                            + (". The head's neck is used and the body's neck base laid on it. (MakeHuman's female neck is ~295 mm "
                               "at any weight; GNM's female class mean is 365 mm; ANSUR 330.)" if nat and sex < 0.5 else
                               ". The head's neck is used and the body's neck base laid on it." if nat else ""))
    if age < 16:
        out["flags"].append(f"age {age:g}: the ranges above are ADULTS' (ANSUR) and GNM is an adult head model: a child's "
                            "head-on-body proportions are not checked here")
    if nat:
        user = base.get("head") or {}
        from . import humanstyle
        out["ignored"] = [f"base.head.{k}" for k in (*onemesh.NATIVE_DROP, "dimorphism", "toward") if user.get(k) not in (None, 0, 0.0) and not (k == "gnm_base" and float(user[k]) == 1.0)] \
            + [f"base.style.human.{k}" for k in humanstyle.active(base, humanstyle.HEAD + ("exaggerate",))]
        out["body_height"] = float(hd["bound"]["body"]["height"])
        out["own_head"] = float(nat["own"])
    t = [f"head: {'GNM native' if nat else 'carried by the body'}, {size:.3f} x GNM's own size; head height {hh * 1000:.0f} mm, eyes "
         f"{out['eyes_apart'] * 1000:.1f} mm apart, eyeball r {out['eyeball_r'] * 1000:.1f} mm (GNM 14.6)",
         f"figure: stature {stature:.3f} m = {out['heads_tall']:.2f} heads tall; top of head {out['top_over_pit'] * 1000:.0f} mm and chin "
         f"{out['chin_over_pit'] * 1000:.0f} mm over the pit of the throat",
         f"neck: the head's girth {gh * 1000:.0f} mm at its narrowest (ring {kr}), the body's own there {gb * 1000:.0f} mm "
         f"({100 * out['neck_conflict']:+.0f} %); at the seam ring {out['neck']['ring'] * 1000:.0f} mm",
         "checks (value, ANSUR for this sex and stature, sd away): " + "; ".join(
             f"{c['name']} {c['value'] * 1000:.0f} ({c['expected'] * 1000:.0f} +- {c['sd'] * 1000:.0f}, {c['z']:+.1f})" for c in out["checks"])]
    t += [f"  FLAG: {f}" for f in out["flags"]] or ["  all attach checks inside their ranges"]
    if out["ignored"]:
        t.append("  ignored on a native head (they reshape or resize GNM's head): " + ", ".join(out["ignored"]))
    out["text"] = "\n".join(t)
    return out


def weights(tpl: dict) -> tuple:
    """The template's skin weights over MakeHuman's bones: (bone names, (n, 8) bone indices, (n, 8) weights)."""
    a = asset()
    return [str(b) for b in a["bones"]], a["w_idx"][tpl["fid"]].astype(int), a["w"][tpl["fid"]].astype(float)
