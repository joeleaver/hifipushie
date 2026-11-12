"""What a fit did besides what was asked: side effects, integrity, the guard against newly broken regions,
the verdict, the table. Part of humanfit (humanfit.py has the overview)."""
from __future__ import annotations

import json

import numpy as np

from . import humanfit
from .humanfit import _points, plausibility, state

def side_effects(st0: dict, st1: dict, asked: set, near=None) -> dict:
    """What changed between two states: every measure before -> after (sorted by how far it moved, in units of its
    own tolerance), those that moved without being asked flagged, and where the vertices went."""
    m0, m1 = st0["measures"], st1["measures"]
    rows = []
    for k in m0:
        d = m1[k] - m0[k]
        lim = humanfit.UNINTENDED_MM if k in humanfit.FACE else max(abs(m0[k]) * humanfit.UNINTENDED_BODY, 1e-6)
        rows.append({"measure": k, "was": round(m0[k], 2), "now": round(m1[k], 2), "moved": round(d, 2),
                     "unit": "mm" if k in humanfit.FACE else ("" if k == "heads" else "cm"),
                     "flag": "asked" if k in asked else "UNINTENDED" if abs(d) > lim else "", "rel": abs(d) / lim})
    rows.sort(key=lambda r: -r["rel"])
    P0, P1 = np.asarray(st0["tpl"]["P"]), np.asarray(st1["tpl"]["P"])
    out = {"measures": rows, "unintended": [r["measure"] for r in rows if r["flag"] == "UNINTENDED"]}
    if P0.shape == P1.shape:
        d = np.linalg.norm(P1 - P0, axis=1)
        nb = st0["tpl"]["n_body"]
        pts = near
        if pts is None:
            ids = sorted({i for p in asked if p in humanfit.FACE for i in _points(p)})
            pts = st0["L"][ids] if ids else None
        outside = np.zeros(len(d), bool)
        if pts is not None and len(pts):
            dm = np.linalg.norm(P0[:, None] - np.asarray(pts)[None], axis=-1).min(1)
            outside = dm > 0.05
        out["moved"] = {"max_mm": round(float(d.max()) * 1000, 2), "head_mean_mm": round(float(d[nb:].mean()) * 1000, 3),
                        "body_max_mm": round(float(d[:nb].max()) * 1000, 3),
                        "over_1mm_share": round(float((d > 0.001).mean()), 4),
                        "outside_region_over_1mm": int(((d > 0.001) & outside).sum()),
                        "outside_region_share": round(float(((d > 0.001) & outside).sum() / max(len(d), 1)), 4)}
    return out


def _regions(tpl: dict) -> dict:
    """Named regions of the template's vertices (bool masks)."""
    from . import base_identity
    from . import onemesh
    a = onemesh.asset()
    g = base_identity._gnm_data()
    gid = a["gnm_id"][tpl["fid"]]
    G = {k: (np.asarray(v) > 0.5) for k, v in g["groups"].items()}
    pick = lambda *names: np.where(gid >= 0, np.any([G[n][np.maximum(gid, 0)] for n in names], axis=0), False)  # noqa: E731
    n0 = int(a["bridge"][0])
    return {"lids": pick("left_orbital_region", "right_orbital_region", "eye_sockets"), "lips": pick("upper_lip", "lower_lip"),
            "nose": pick("nose_region"), "ears": pick("ears"),
            "neck bridge": (tpl["fid"] >= n0) | np.isin(tpl["fid"], np.r_[a["loop_a"], a["loop_c"]]),
            "face": pick("hockey_mask"), "head": gid >= 0, "body": a["mh_id"][tpl["fid"]] >= 0}


def integrity(base: dict, st: dict | None = None, prev: dict | None = None) -> dict:
    """{"ok", "broken": [...], "warnings": [...], "numbers"}: see the module docstring. Compared against the same body
    with a plain head (no identity, features, pose or style), so a child's small head isn't 'compressed'."""
    from . import onemesh
    st = st or state(base)
    tpl, ht = st["tpl"], st["head"]
    key = ("integrity_ref", json.dumps(onemesh.body_params(base), sort_keys=True, default=float))
    ref = onemesh._CACHE.get(key)
    if ref is None:
        ref = onemesh._CACHE[key] = onemesh.template({"body": dict(base["body"]), "head": {"dimorphism": 0}})
    if ht.get("lips_zipped"):  # closed lips are zipped, and the weld depends on the shape: both heads unzipped here
        tpl = onemesh.template({**base, "head": {**(base.get("head") or {}), "zip_lips": False}})
        key = key + (base["head"].get("mouth_gap"),)
        ref = onemesh._CACHE.get(key)
        if ref is None:
            ref = onemesh._CACHE[key] = onemesh.template({"body": dict(base["body"]), "head": {
                "dimorphism": 0, "mouth_gap": base["head"].get("mouth_gap"), "zip_lips": False}})
    P, P0 = np.asarray(tpl["P"], float), np.asarray(ref["P"], float)
    Lf, Sf = np.asarray(tpl["L"]), np.asarray(tpl["S"])
    st_ = np.r_[0, np.cumsum(Sf)[:-1]]
    F = np.stack([Lf[st_], Lf[st_ + 1], Lf[st_ + 2], Lf[st_ + Sf - 1]], 1)  # (a triangle: its last corner twice)
    broken, warn, num = [], [], {}
    same = P.shape == P0.shape and np.array_equal(np.asarray(ref["L"]), np.asarray(tpl["L"]))
    reg = _regions(tpl)
    if not np.isfinite(P).all():
        broken.append("the mesh has NaNs")
    if same:
        def fn(X):
            return np.cross(X[F[:, 2]] - X[F[:, 0]], X[F[:, 3]] - X[F[:, 1]])
        n1, n0 = fn(P), fn(P0)
        dot = (n1 * n0).sum(1) / np.maximum(np.linalg.norm(n1, axis=1) * np.linalg.norm(n0, axis=1), 1e-30)
        flip = dot < 0.0
        num["turned_faces"] = int(flip.sum())

        def where_(mask):
            w_ = {k: int(mask[v[F].any(1)].sum()) for k, v in reg.items() if k not in ("head", "body", "face")}
            return ", ".join(f"{k} {v}" for k, v in w_.items() if v) or "head"
        Pp = None
        if prev is not None:
            ptpl = prev["tpl"] if not ht.get("lips_zipped") else onemesh.template(
                {**prev["base"], "head": {**(prev["base"].get("head") or {}), "zip_lips": False}})
            if np.asarray(ptpl["P"]).shape == P.shape:
                Pp = np.asarray(ptpl["P"], float)
        if Pp is not None:
            # an EDIT's folds: faces that turned over against the state before it
            np_ = fn(Pp)
            new = (n1 * np_).sum(1) < 0
            # (slivers don't count: see SLIVER)
            big = np.maximum(np.linalg.norm(P[F] - P[np.roll(F, 1, 1)], axis=2).max(1), np.linalg.norm(Pp[F] - Pp[np.roll(F, 1, 1)], axis=2).max(1)) >= humanfit.SLIVER
            new &= big
            num["folded_faces"] = int(new.sum())
            if new.sum() >= humanfit.FOLD_LIMIT:
                broken.append(f"{int(new.sum())} faces folded over by this change ({where_(new)})")
            elif new.any():  # (one or two tiny faces inside the lips or lids turn with any change of shape)
                warn.append(f"{int(new.sum())} small faces turned over by this change ({where_(new)})")
        elif flip.sum() > 40:  # against the plain head lids and lips legitimately turn a few faces (an open lid rolls)
            warn.append(f"{int(flip.sum())} faces face the other way than on the plain head ({where_(flip)})")
        E = np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 3]], F[:, [3, 0]]]
        l1 = np.linalg.norm(P[E[:, 0]] - P[E[:, 1]], axis=1)
        l0 = np.maximum(np.linalg.norm(P0[E[:, 0]] - P0[E[:, 1]], axis=1), 1e-9)
        r = l1 / l0
        hsel = reg["head"][E].all(1)
        if hsel.any():  # a style's bigger head is a scale, not a distortion: stretch is read against the head's own size
            num["head_scale"] = round(float(np.median(r[hsel])), 3)
            r = np.where(hsel, r / max(float(np.median(r[hsel])), 1e-6), r)
        num["stretch"] = {}
        rp = None
        if Pp is not None:  # the same edges in the INPUT (the state before this edit), on the same scale
            lp = np.linalg.norm(Pp[E[:, 0]] - Pp[E[:, 1]], axis=1)
            rp = lp / l0
            if hsel.any():
                rp = np.where(hsel, rp / max(float(np.median(rp[hsel])), 1e-6), rp)
        for k in ("lids", "lips", "nose", "ears", "neck bridge", "face"):
            sel = reg[k][E].all(1)
            if not sel.any():
                continue
            lo, hi = float(r[sel].min()), float(np.percentile(r[sel], 99.5))
            num["stretch"][k] = [round(lo, 2), round(hi, 2)]
            past = sel & (((r > 3.0) & (l1 >= humanfit.SLIVER)) | ((r < 0.25) & (l0 >= humanfit.SLIVER_SQUEEZE)))
            if rp is not None:
                # judged against the INPUT: an edge past the limit counts only if this edit made it worse by
                # GUARD_WORSE (v23's lip corners: a 1.7 mm edge already squeezed to 0.55 mm on the plain head), or
                # if the edit alone stretched / squeezed it past the limit
                # and only if its length changed by GUARD_MM or more: v23's lip corner went 0.55 -> 0.47 mm (13%)
                # under a face widened 10 mm two cm away: the mouth's re-solved closure, below the mesh's own noise
                moved = np.abs(l1 - lp) >= humanfit.GUARD_MM
                worse = ((r < rp * (1 - humanfit.GUARD_WORSE)) & (r < 1) | (r > rp * (1 + humanfit.GUARD_WORSE)) & (r > 1)) & moved
                own = ((r / np.maximum(rp, 1e-9) > 3.0) & (l1 >= humanfit.SLIVER)) | ((r / np.maximum(rp, 1e-9) < 0.25) & (lp >= humanfit.SLIVER_SQUEEZE))
                past = (past & worse) | (sel & own)
            if past.any():
                bl, bh = float(r[past].min()), float(r[past].max())
                broken.append(f"{k}: {int(past.sum())} edges stretched to x{bh:.1f} / squeezed to x{bl:.2f} against the plain "
                              "head" + (" (worse than before this change)" if rp is not None else ""))
            elif hi > 1.8 or lo < 0.45:
                warn.append(f"{k}: edges stretched x{hi:.1f} / squeezed x{lo:.2f}")
    else:
        warn.append("this head's topology differs from the plain head's: stretch and folds not compared")
    L = st["L"]
    r_eye = float(ht["eye_r"])
    for side, c, rim in (("left", L[humanfit.EYE_L], L[42:48]), ("right", L[humanfit.EYE_R], L[36:42])):
        d = np.linalg.norm(rim - c, axis=1)
        if d.min() < r_eye - 0.0005:
            broken.append(f"{side} eyeball through its lids by {1000 * (r_eye - d.min()):.1f} mm")
        if d.max() > r_eye + 0.006:
            warn.append(f"{side} lids stand {1000 * (d.max() - r_eye):.1f} mm off the eyeball")
    num["mouth_gap_mm"] = round(float(L[62, 2] - L[66, 2]) * 1000, 2)
    if L[62, 2] - L[66, 2] < -0.0008:
        broken.append(f"the lips cross by {-num['mouth_gap_mm']:.1f} mm")
    if st["measures"]["eye_height"] < 2.0:
        warn.append(f"the eyes are nearly shut ({st['measures']['eye_height']:.1f} mm)")
    asym = float(np.abs(L[:68] - L[_mirror68()] * [-1, 1, 1]).max()) * 1000
    num["asymmetry_mm"] = round(asym, 2)
    pl = plausibility(base)
    num["plausibility"] = pl
    if pl["max_sigma"] > humanfit.CLIP + 1e-6:
        warn.append(f"identity components up to {pl['max_sigma']:.1f} sigma ({pl['over']} past {humanfit.CLIP}): outside the plausible range")
    if pl["rms_sigma"] > 1.6:
        warn.append(f"the identity is {pl['rms_sigma']:.2f} sigma rms from the mean (a seed at spread 1 is 1.0)")
    return {"ok": not broken, "broken": broken, "warnings": warn, "numbers": num}


def _mirror68() -> np.ndarray:
    m = np.arange(68)
    for a, b in ([(i, 16 - i) for i in range(8)] + [(17 + i, 26 - i) for i in range(5)] + [(31, 35), (32, 34), (36, 45), (37, 44),
                 (38, 43), (39, 42), (40, 47), (41, 46), (48, 54), (49, 53), (50, 52), (59, 55), (58, 56), (60, 64), (61, 63), (67, 65)]):
        m[a], m[b] = b, a
    return m


def _guarded(base: dict, cur: dict, rep: dict, force: bool) -> tuple:
    """A fit whose result is BROKEN (integrity) hands back the base it was given, not the broken one, unless
    force=True: rep["refused"] says why and rep["integrity"] is the broken result's (so the caller sees what broke).
    Reporting alone wasn't enough: a script saved a 62 mm mouth with 7 lip faces folded."""
    it = rep.get("integrity")
    if it is None or it["ok"] or force:
        return cur, rep
    new = _newly_broken(base, it)
    if not new:  # (broken already, as the input was: the edit isn't what broke it; it's said in the report)
        rep["already_broken"] = True
        return cur, rep
    rep["refused"] = ("BROKEN result not returned (the input is): " + "; ".join(new)
                      + ". Ask for less, or force=True to take it anyway.")
    return base, rep


def _newly_broken(base: dict, it: dict) -> list:
    """What in a result's integrity the edit broke. Edge stretch and folds are already judged against the input
    (integrity(prev=): an edge counts only where this change made it worse); any other broken line (an eyeball through
    its lids, crossed lips) counts if the input doesn't have it too."""
    STRETCH = ("lids", "lips", "nose", "ears", "neck bridge", "face")
    b0 = None
    out = []
    for line in it["broken"]:
        if line.split(":")[0] in STRETCH or "folded over by this change" in line:
            out.append(line)
            continue
        if b0 is None:
            b0 = integrity(base, state(base))
        if line not in b0["broken"]:
            out.append(line)
    return out


def verdict(integ: dict) -> str:
    lines = ["INTEGRITY: ok" if integ["ok"] else "BROKEN: " + "; ".join(integ["broken"])]
    lines += ["WARNING: " + w for w in integ["warnings"]]
    return "\n".join(lines)


def table(m: dict, ref: dict | None = None) -> str:
    body = "  ".join(f"{k} {m[k]:.1f}" for k in humanfit.BODY if k in m)
    face = "  ".join(f"{k} {m[k]:.1f}" for k in humanfit.FACE)
    r = lambda a, b: m[a] / m[b]  # noqa: E731
    ratios = (f"eye_width/face_width {r('eye_width', 'face_width'):.3f}  eye_to_chin/face_width {r('eye_to_chin', 'face_width'):.3f}  "
              f"interocular/face_width {r('interocular', 'face_width'):.3f}  nose_width/mouth_width {r('nose_width', 'mouth_width'):.3f}  "
              f"jaw_width/face_width {r('jaw_width', 'face_width'):.3f}  chin_height/philtrum {r('chin_height', 'philtrum'):.2f}")
    return f"body (cm; heads = stature / head height): {body}\nface (mm): {face}\nratios: {ratios}"


def effects_text(se: dict, top: int = 12) -> str:
    rows = [r for r in se["measures"] if abs(r["moved"]) > 1e-9][:top]
    lines = []
    if se["unintended"]:
        lines.append("UNINTENDED: " + ", ".join(f"{r['measure']} {r['moved']:+.1f} {r['unit']}".strip() for r in se["measures"]
                                                 if r["flag"] == "UNINTENDED"))
    lines.append("what moved (was -> now): " + ("; ".join(f"{r['measure']} {r['was']:g} -> {r['now']:g}{' (' + r['flag'] + ')' if r['flag'] else ''}"
                                                           for r in rows) or "nothing"))
    mv = se.get("moved")
    if mv:
        lines.append(f"vertices: max {mv['max_mm']} mm, head mean {mv['head_mean_mm']} mm, body max {mv['body_max_mm']} mm, "
                     f"{100 * mv['over_1mm_share']:.1f}% moved over 1 mm, {mv['outside_region_over_1mm']} of them "
                     f"({100 * mv['outside_region_share']:.1f}% of the mesh) more than 5 cm from what was asked")
    return "\n".join(lines)
