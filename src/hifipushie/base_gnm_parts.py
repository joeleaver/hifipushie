"""A GNM head's own pieces: the eyes, the mouth (lips, teeth, tongue, sock), the mouth's mode, the lips' close and zip. Part of base (base.py has the overview)."""
from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

from . import base
from .base import source
from .base_identity import _gnm_data
from .base_imls import _catmull_clark, _imls, _normals_and_h, _unit

def mouth_lips(head: dict) -> dict:
    """The grafted head's mouth for the face kit's interior and face shapes, from its landmarks: the parting line
    (inner-lip midpoints) by u = |x| / the corner's, the frame, lip radii, width and gap."""
    lm = head["lm68"]
    out = _unit(head["forward"])
    up = np.array([0.0, 0.0, 1.0])
    up = _unit(up - out * (up @ out))
    side = np.cross(-out, up)
    M = 0.5 * (lm[62] + lm[66])
    pts = [M, 0.5 * (lm[63] + lm[65]), lm[64], lm[54]]
    xs = [(p - M) @ side for p in pts]
    knots = np.clip(np.array(xs) / xs[-1], 0, 1)
    return {"M": M, "out": out, "up": up, "side": side, "knots": knots, "pts": np.array(pts),
            "width": float((lm[54] - lm[48]) @ side), "ru": 0.5 * float(np.linalg.norm(lm[51] - lm[62])),
            "rl": 0.5 * float(np.linalg.norm(lm[57] - lm[66])), "gap": float(np.linalg.norm(lm[62] - lm[66]))}


def _gnm_piece_sets(g: dict) -> list:
    """GNM's loose pieces and the skin each follows: [(piece vertex ids, anchor skin vertex ids)]. An eyeball (its
    inner and outer shells): that eye's lid margins and the socket lining behind them (lidrings -2 .. 2), so it keeps
    GNM's own relation to the lids. Upper teeth, lower teeth and tongue, as ONE piece (the rows stay registered):
    GNM's lip and chin regions (wide on purpose: a seal that presses the lips together must not shrink the teeth)."""
    if "piece_sets" not in base._CACHE:
        from . import lidrings
        gr = {k: np.asarray(v) > 0.5 for k, v in g["groups"].items()}
        t, mir = lidrings.topo(), lidrings.mirror()
        ring = np.concatenate([t["loops"][k] for k in range(-2, 3)])
        mouth = gr["upper_teeth_and_gums"] | gr["lower_teeth_and_gums"] | gr["tongue"]
        base._CACHE["piece_sets"] = [(np.flatnonzero(gr["left_eye"]), ring), (np.flatnonzero(gr["right_eye"]), mir[ring]),
                                (np.flatnonzero(mouth), np.flatnonzero(gr["upper_lip_region"] | gr["lower_lip_region"]
                                                                        | gr["chin_region"]))]
    return base._CACHE["piece_sets"]


def _gnm_pieces(V: np.ndarray, Vg: np.ndarray, g: dict, En: np.ndarray | None = None, fade=None) -> np.ndarray:
    """GNM's loose pieces (eyeballs, teeth and gums, tongue) on a head our steps have moved: each is GNM's OWN shape
    for these coefficients (Vg: template + identity + expression, one evaluation of its bases; En: the expression's
    share of it), carried by the translation and uniform scale that take the skin beside it, in the NEUTRAL, from
    GNM's evaluation to where our steps put it; the expression's own offsets are then added as the skin takes them
    (unscaled). So an expression moves a piece exactly as GNM's basis says (the lower teeth and tongue with the jaw,
    the upper teeth never), and with nothing of ours on the head the pieces are exactly GNM's. (Before, 2026-10-12:
    they went through the skin's own fields (the body's head, the dimorphism field, style sliders, the eye scaling):
    an eyeball up to 1.9 mm out of round, tooth rows bent by up to 6 mm. Nobody saw it: our own ball and the kit's
    teeth were shown.)"""
    V = np.array(V, float)
    En = np.zeros_like(V) if En is None else En
    Vn = Vg - En
    for ids, anc in _gnm_piece_sets(g):
        A1 = V[anc] - (En[anc] if fade is None else En[anc] * fade[anc, None])  # (the skin as it stands in the neutral)
        c0, c1 = Vn[anc].mean(0), A1.mean(0)
        k = float(np.sqrt(((A1 - c1) ** 2).sum() / max(((Vn[anc] - c0) ** 2).sum(), 1e-30)))
        V[ids] = c1 + k * (Vn[ids] - c0) + En[ids]
    return V


def gnm_eyes(V: np.ndarray, g: dict) -> list:
    """GNM's own TWO-SPHERE eye read off posed GNM vertices V (its frame; any unit), per eye (left, right): the scleral
    sphere ("c", "r": the outer shell's, what the lids lie on; GNM holds it at 14.6 mm for every identity), the gaze
    "axis", the corneal sphere ("cornea_r", "apex": its front pole's distance from c), the "limbus" (the circle where
    the two spheres meet: the iris as seen from outside), the iris disc behind the cornea ("iris_r", "iris_depth") and
    the pupil ("pupil_r"; "pupil" = pupil_r / iris_r). Limbus and cornea come from the identity's `eyes_*` components,
    the pupil from the expression component `pupils_000`; the head's components only carry the ball with its joint."""
    gr = g["groups"]
    out = []
    for side in ("left_eye", "right_eye"):
        m = np.asarray(gr[side]) > 0.5
        ext = V[m & (np.asarray(gr["eye_exteriors"]) > 0.5)]
        scl = V[m & (np.asarray(gr["scleras"]) > 0.5)]
        A = np.c_[2 * scl, np.ones(len(scl))]
        x = np.linalg.lstsq(A, (scl ** 2).sum(1), rcond=None)[0]
        c = x[:3]
        pup = V[m & (np.asarray(gr["pupils"]) > 0.5)] - c
        iris = V[m & (np.asarray(gr["irises"]) > 0.5)] - c
        ax = _unit(pup.mean(0))
        rad = lambda P: np.linalg.norm(P - np.outer(P @ ax, ax), axis=1)  # noqa: E731
        e = ext - c
        d = np.linalg.norm(e, axis=1)
        ri = float(rad(iris).max())
        ae, ze = rad(e), e @ ax
        # the ball the lids lie on: the outer shell's FRONT outside the cornea (the eye components reshape the shell's
        # front by +-0.3 mm against its back; the limbus component moves the cornea's base)
        ring = (ze > 0) & (ae > 1.55 * ri) & (ae < 2.6 * ri)
        r = float(np.median(d[ring])) if ring.sum() >= 8 else float(np.median(d[ze < 0]))
        apex = float(ze.max())
        # the corneal sphere through the apex and the cap's inner points (GNM's shell eases the junction, so the
        # limbus is where the two SPHERES meet, the paper's limbus radius)
        cap = (ze > 0) & (ae < 0.75 * ri) & (ae > 0.25 * ri)
        if cap.sum() >= 4 and apex > r * 1.01:
            h = apex - ze[cap]
            rc = float(np.median((h ** 2 + ae[cap] ** 2) / (2 * h)))
            cz = apex - rc  # the corneal sphere's centre, along the axis from c
            zl = (r * r - rc * rc + cz * cz) / (2 * cz) if cz > 1e-9 else r
            limbus = float(np.sqrt(max(r * r - zl * zl, 0.0)))
        else:  # no bulge (a head whose eye vertices were flattened): the iris disc's own edge
            rc, limbus = r, ri
        out.append({"c": c, "r": r, "axis": ax, "cornea_r": rc, "apex": apex, "limbus": limbus, "iris_r": ri,
                    "iris_depth": float((iris @ ax)[np.argmax(rad(iris))]), "pupil_r": float(rad(pup).max()),
                    "pupil": float(rad(pup).max() / max(ri, 1e-12))})
    return out


def mouth_mode(b: dict, head: dict | None = None) -> str:
    """Which mouth a base's head has: "gnm" (GNM's own mouth bag, teeth and gums, tongue: THE DEFAULT for a GNM head),
    "kit" (the face kit's slit / bag / teeth / tongue behind the lips: base.head.interior, as every head made before
    2026-10-12 with an interior; or the FALLBACK when a style pushed the lips off GNM's surface, see mouth_note) or
    "none" (lips with a fill behind them). base.head.mouth = "gnm" | "kit" | "none" asks for one; unset: "kit" if
    base.head.interior is given (old specs keep their mouth), else "gnm"."""
    hd = b.get("head") if isinstance(b.get("head"), dict) else None
    if hd is None or hd.get("source", "gnm") != "gnm":
        return "none"
    m = hd.get("mouth")
    if m is None:
        m = "kit" if hd.get("interior") else "gnm"
    if m in (False, "none"):
        return "none"
    if m not in ("gnm", "kit"):
        raise ValueError('base.head.mouth: "gnm" (GNM\'s own bag, teeth and tongue), "kit" (the face kit\'s interior: '
                         'base.head.interior) or "none"')
    if m == "kit":
        return "kit" if hd.get("interior") else "none"
    if head is not None and float(head.get("mouth_off") or 0.0) > base.MOUTH_PUSHED:
        return "kit" if hd.get("interior") else "none"
    return "gnm"


def mouth_open(b: dict, head: dict) -> bool:
    """Whether a GNM head's lips are parted, i.e. whether its field needs a mouth cavity (GNM's bag) instead of the
    fill behind closed lips. The one mesh: as its template decides the closed mouth's seam field (lip_seal, or GNM's
    contact ring closed: onemesh_head.template's "seal_field"); a grafted head: the inner lips' landmarks further apart
    than MOUTH_PARTED and the lips not zipped."""
    if head.get("skin_index") is not None:
        return False
    if (b.get("body") or {}).get("source") == "human":
        return source(b).get("seal_field") is None
    lm = head["lm68"]
    return float(np.linalg.norm(lm[62] - lm[66])) > base.MOUTH_PARTED


def mouth_note(b: dict, head: dict | None) -> str | None:
    """What a build says about the mouth when GNM's own was asked for (or the default) and could not be used."""
    hd = b.get("head") if isinstance(b.get("head"), dict) else None
    if hd is None or head is None or hd.get("mouth", "gnm" if not hd.get("interior") else "kit") != "gnm":
        return None
    off = float(head.get("mouth_off") or 0.0)
    if off > base.MOUTH_PUSHED:
        return (f"mouth: the head's style moved the lips {off * 1000:.1f} mm off GNM's own surface (pushes / simplify / "
                f"shape ops on the built head), so GNM's teeth and tongue no longer sit behind them: "
                + ("the face kit's interior (base.head.interior) is used instead" if hd.get("interior") else
                   "no mouth interior is built (give base.head.interior for the face kit's)")
                + ". GNM's own mouth needs the lips where GNM puts them (identity / expression moves keep them there)")
    return None


def gnm_mouth(head: dict) -> dict:
    """GNM's own mouth on a built head, world: {"teeth_upper" / "teeth_lower" / "tongue" / "sock": {"ids" (GNM vertex
    ids), "verts", "faces" (quads, local), "gum" (teeth: per vertex, True on the gums)}, "frame": (M, out, up, side)}.
    Every piece comes from the head's one evaluation of GNM's bases (gnm_head's "gnm_world"): the teeth from the
    identity's 80 teeth components, the lower row and the tongue moved by the lower-face and tongue expressions."""
    if head.get("_mouth") is not None:
        return head["_mouth"]
    g = _gnm_data()
    gr = {k: np.asarray(v) > 0.5 for k, v in g["groups"].items()}
    Q = np.asarray(g["quads"])
    W = np.asarray(head["gnm_world"], float)
    out = {}
    for name, m in (("teeth_upper", gr["upper_teeth_and_gums"]), ("teeth_lower", gr["lower_teeth_and_gums"]),
                    ("tongue", gr["tongue"]), ("sock", gr["mouth_sock"])):
        q = Q[m[Q].any(1)] if name == "sock" else Q[m[Q].all(1)]  # (the sock with the quads joining it to the lips)
        ids = np.unique(q)
        loc = np.full(len(m), -1)
        loc[ids] = np.arange(len(ids))
        out[name] = {"ids": ids, "verts": W[ids], "faces": loc[q]}
        if name.startswith("teeth"):
            out[name]["gum"] = (gr["gums"] & ~gr["teeth"])[ids]
    ml = mouth_lips(head)
    for name, sgn in (("teeth_upper", 1.0), ("teeth_lower", -1.0)):
        out[name]["verts"] = _grow_crowns(out[name]["verts"], out[name]["gum"], ml, sgn)
    # (r37) base.head.teeth_place = {"upper": [up mm, forward mm], "lower": [...]}: each row moved RIGIDLY in the mouth's
    # frame (teeth are rigid to the skull / jaw). Solved from the person's expression photos (the incisal edge's line
    # against the lips: assembly r37 teethline), not by eye: GNM's identity puts the rows where its population does
    tp = head.get("teeth_place") or {}
    for name, key in (("teeth_upper", "upper"), ("teeth_lower", "lower")):
        if tp.get(key):
            du, df = (float(x) * 1e-3 for x in tp[key][:2])
            out[name]["verts"] = out[name]["verts"] + du * np.asarray(ml["up"]) + df * np.asarray(ml["out"])
    out["frame"] = (ml["M"], ml["out"], ml["up"], ml["side"])
    out["gap"] = ml["gap"]
    head["_mouth"] = out
    return out


def _grow_crowns(V: np.ndarray, gum: np.ndarray, ml: dict, sgn: float) -> np.ndarray:
    """A tooth row with its crowns TEETH_CROWN_GROW taller, from the biting edge (it stays put) toward the gum, the
    gum carried along rigidly by the extra height; the arch TEETH_WIDEN wider about the midline. sgn: +1 the upper
    row (crowns grow up), -1 the lower."""
    V = np.asarray(V, float)
    up, side, M = np.asarray(ml["up"], float), np.asarray(ml["side"], float), np.asarray(ml["M"], float)
    h = sgn * ((V - M) @ up)
    crown = ~np.asarray(gum, bool)
    if not crown.any():
        return V
    x = (V - M) @ side
    mid = float(np.median(x))
    # the biting edge levelled onto a smile arc: GNM's mean row has its canines ~1 mm BELOW the centrals and 1 mm
    # of left / right difference (lips/teethsize.py on v21), which read as "irregular, fang-like canines" (expr_r8 / r9).
    # Per vertex: the edge across its neighbours within TEETH_LEVEL_BAND, moved onto the arc, fading to 0 at the gum
    from scipy.spatial import cKDTree
    ci = np.where(crown)[0]
    tr = cKDTree(x[ci, None])
    dd, nb = tr.query(x[:, None], k=min(64, len(ci)))
    hh = np.where(dd <= max(base.TEETH_LEVEL_BAND, 0.0), h[ci[nb]], np.nan)
    hh[:, 0] = h[ci[nb[:, 0]]]  # (a gum vertex past the crowns' ends: its nearest crown vertex's tooth)
    tip, gtop = np.nanmin(hh, 1), np.nanmax(hh, 1)
    c0 = float(np.percentile(tip[ci][np.abs(x[ci] - mid) < 0.006], 50))
    target = c0 + base.TEETH_ARC * ((x - mid) / 0.016) ** 2
    wv = np.clip(1 - (h - tip) / np.maximum(gtop - tip, 1e-4), 0, 1) * crown
    V = V + (sgn * (target - tip) * wv)[:, None] * up[None]
    h = sgn * ((V - M) @ up)
    edge = float(np.percentile(h[crown], 1))
    top = float(np.percentile(h[crown], 97))
    t = h - edge
    ht = top - edge
    grow = np.where(t <= 0, 0.0, np.where(t < ht, t, ht)) * (base.TEETH_CROWN_GROW - 1)
    return V + (sgn * grow)[:, None] * up[None] + ((x - mid) * (base.TEETH_WIDEN - 1))[:, None] * side[None]


def _piece_points(V, faces, rounds: int = base.MOUTH_SUBDIVIDE) -> dict:
    """A GNM piece's quads as an IMLS point set (verts, normals, h, tree): subdivided, normals outward."""
    F = [list(map(int, f)) for f in faces]
    for _ in range(rounds):
        V, F = _catmull_clark(V, F)
    N, h = _normals_and_h(V, F)
    return {"verts": V, "normals": N, "h": h, "hmax": float(h.max()), "tree": cKDTree(V), "seam": None}


def gnm_mouth_field(head: dict) -> list:
    """GNM's mouth as field elements for spec.compile_prims: [{"name", "part", "op", "kind", "blend", "layer",
    "params", "lo", "hi"}]: the two tooth rows with their gums (parts "teeth" = upper, "teeth_lower") and the tongue (part "tongue"), each the
    solid under GNM's own surface (sd_gnm_piece). The mouth BAG is not an element: with the lips parted GNM's mouth
    sock joins the head's own point set (surface: sock_points), as it joins GNM's skin."""
    mp = gnm_mouth(head)
    out = []
    for name, part in (("teeth_upper", base.TEETH_PARTS[0]), ("teeth_lower", base.TEETH_PARTS[1]), ("tongue", "tongue")):
        pr = _piece_points(mp[name]["verts"], mp[name]["faces"])
        pr["t"] = base.MOUTH_SHELL[part]
        pad = 2 * pr["hmax"]
        out.append({"name": f"gnm_{name}", "part": part, "op": "add", "kind": "gnmpiece", "blend": 0.0, "layer": 0,
                    "params": pr, "lo": pr["verts"].min(0) - pad, "hi": pr["verts"].max(0) + pad})
    return out


def sd_gnm_piece(p: np.ndarray, pr: dict) -> np.ndarray:
    """One of GNM's loose mouth pieces as a solid: the space up to `t` under its surface (IMLS over its vertices),
    within reach of its own vertices. GNM's tooth rows and tongue are OPEN shells (the gums end in a free edge at the
    back, the tongue at its root): the plain IMLS made everything behind that edge "inside", a slab of tooth through
    the whole mouth. Crowns are thinner than 2 t, so they come out solid; a gum is a sheet t thick."""
    X = p.reshape(-1, 3)
    d0, i0 = pr["tree"].query(X)
    t = float(pr["t"])
    out = d0 - t  # far from the piece: a (conservative) distance to the shell
    near = d0 < t + 3 * pr["hmax"]
    if near.any():
        s = _imls(X[near], pr)
        # past a free edge the nearest vertex lies SIDEWAYS of the point, not over it: outside (the slab under the
        # tongue's front edge came out through the chin as a red bar)
        j = i0[near]
        s0 = ((X[near] - pr["verts"][j]) * pr["normals"][j]).sum(1)
        lat = np.sqrt(np.maximum(d0[near] ** 2 - s0 ** 2, 0.0)) - 2.5 * pr["h"][j]
        out[near] = np.maximum(np.maximum(s, -s - t), lat)
    return out.reshape(p.shape[:-1])


def sock_points(head: dict) -> dict:
    """GNM's mouth sock (and the quads that join it to the lips' inner loop) as IMLS points for the head's own field,
    when the lips are parted (mouth_open) and GNM's mouth is in use: the mouth's cavity is then GNM's bag, closed
    behind the lips as it is in GNM's skin (without it the lips' inner rolls ended in a free edge)."""
    mp = gnm_mouth(head)
    if "points" not in mp["sock"]:
        mp["sock"]["points"] = _piece_points(mp["sock"]["verts"], mp["sock"]["faces"], rounds=2)
    return mp["sock"]["points"]


def lip_close_delta(V: np.ndarray, g: dict, scale: float = 1.4) -> np.ndarray:
    """head["lip_close"]: GNM's OWN closing of the rest mouth (gnmdetail2), in place of the seal's membrane: the least
    change of the lower-face EXPRESSION (its first 40 comps, unit prior) that puts the contact ring's two halves
    together from corner to corner (one-sided: they may overlap 0.2 mm), the lower half not ahead of the upper, the
    68 landmarks off the mouth held (0.3 mm; the corners 0.6). Re-solved on every head, so identity steps keep the
    mouth closed. The vermilion border keeps GNM's turn (the seal halved it); the field leaves the crossed inner rolls
    out (onemesh.CLOSED_SEAL_V). V: GNM's raw vertices (its frame: Y up, facing +Z). Returns the (n, 3) move."""
    from . import faceslide
    P = base.LIP_CLOSE
    if "sub" not in base._LIPC:
        R = faceslide._lip_rings()
        C = R["rings"][R["contact"]]
        up = R["upper"][C]
        lower = [i for i, nm in enumerate(g["expression_names"]) if str(nm).startswith("lower_face")][:P["n"]]
        lm_ids = [np.asarray(r[0::2], int) for r in g["lm68"]]
        lm_w = [np.asarray(r[1::2], float) for r in g["lm68"]]
        sub = np.unique(np.concatenate([C] + lm_ids))
        pos = {v: i for i, v in enumerate(sub)}
        W = np.zeros((68, len(sub)))
        for k in range(68):
            for v, w in zip(lm_ids[k], lm_w[k]):
                W[k, pos[int(v)]] += w
        base._LIPC.update(sub=sub, U=np.array([pos[int(v)] for v in C[up]]), L=np.array([pos[int(v)] for v in C[~up]]),
                     lower=lower, Bfull=np.asarray(g["expression_basis"], float)[lower], W=W,
                     hold=[i for i in range(68) if not 48 <= i < 68])
        base._LIPC["B"] = base._LIPC["Bfull"][:, sub]
    S = base._LIPC
    mm = 1000.0 * float(scale)
    Vs0 = V[S["sub"]]
    L0 = S["W"] @ Vs0

    def resid(c):
        Vs = Vs0 + np.tensordot(c, S["B"], 1)
        U, Lo = Vs[S["U"]], Vs[S["L"]]
        ou, ol = np.argsort(U[:, 0]), np.argsort(Lo[:, 0])
        lo, hi = max(U[:, 0].min(), Lo[:, 0].min()), min(U[:, 0].max(), Lo[:, 0].max())
        mid, half = 0.5 * (lo + hi), 0.5 * (hi - lo) * P["span"]
        xx = np.linspace(mid - half, mid + half, P["x"])
        iu = lambda j: np.interp(xx, U[ou, 0], U[ou, j])  # noqa: E731
        il = lambda j: np.interp(xx, Lo[ol, 0], Lo[ol, j])  # noqa: E731
        gap = (iu(1) - il(1)) * mm
        lead = (il(2) - iu(2)) * mm
        L = S["W"] @ Vs
        return np.r_[np.maximum(gap, 0) / P["gap"], np.minimum(gap + P["overlap"], 0) / P["gap"],
                     np.maximum(lead, 0) / P["lead"], ((L[S["hold"]] - L0[S["hold"]]) * mm / P["hold"]).ravel(),
                     ((L[[48, 54]] - L0[[48, 54]]) * mm / P["corner"]).ravel()]
    n = len(S["lower"])
    c = np.zeros(n)
    r = resid(c)
    f, lam = float(r @ r), 0.01
    if np.abs(r[:2 * P["x"]]).max() < 1e-6:   # closed already
        return np.zeros_like(V)
    for _ in range(P["iters"]):
        J = np.stack([(resid(c + 0.25 * np.eye(n)[j]) - r) / 0.25 for j in range(n)], 1)
        while True:
            step = np.linalg.solve(J.T @ J + (1 + lam) * np.eye(n), -(J.T @ r + c))
            rn = resid(c + step)
            fn = float(rn @ rn + (c + step) @ (c + step))
            if fn < f + c @ c:
                c, r, f, lam = c + step, rn, float(rn @ rn), lam * 0.5
                break
            lam *= 4
            if lam > 1e4:
                break
        if lam > 1e4:
            break
    return np.tensordot(c, S["Bfull"], 1)


def _zip_lips(W, faces, seam, reach=0.045, ring=base.LIP_RING):
    """Closed lips as one surface: GNM's skin (mouth bag left out) ends in an open loop a few mm inside the lips,
    and its inner lip rolls face each other behind the contact. Over closed lips those rolls left sealed air pockets
    in the field behind the lips, and a slot the export's low poly and its bake fell into (a dark jagged slit with
    flecks). The rings from the open loop out to the contact ring (`ring` rings out: the inner-lip landmarks
    62/66 sit on it) are dropped and the contact ring's upper half welded to its lower half by arc length (corners
    at its extremes in x), so the lips meet in one seam line, an edge loop of the head's quads. Returns (W, faces,
    skin_index: old -> new vertex index or -1, upper-lip vertices welded)."""
    import collections
    W = np.asarray(W, float)
    cnt: dict = {}
    for f in faces:
        for k in range(len(f)):
            e = (min(f[k], f[(k + 1) % len(f)]), max(f[k], f[(k + 1) % len(f)]))
            cnt[e] = cnt.get(e, 0) + 1
    adj = collections.defaultdict(set)
    for a, b in cnt:
        adj[a].add(b)
        adj[b].add(a)
    loop = [v for (a, b), c in cnt.items() if c == 1 for v in (a, b)
            if np.linalg.norm(W[a] - seam) < reach and np.linalg.norm(W[b] - seam) < reach]
    if not loop:
        return W, faces, None, 0
    lev = {v: 0 for v in set(loop)}
    dq = collections.deque(lev)
    while dq:
        v = dq.popleft()
        if lev[v] >= ring:
            continue
        for w in adj[v]:
            if w not in lev:
                lev[w] = lev[v] + 1
                dq.append(w)
    rv = [v for v, lv in lev.items() if lv == ring]
    rs = set(rv)
    nb = {v: [w for w in adj[v] if w in rs] for v in rv}
    if any(len(n) != 2 for n in nb.values()):
        return W, faces, None, 0
    lp, prev = [rv[0]], None
    while True:
        nx = [w for w in nb[lp[-1]] if w != prev]
        prev = lp[-1]
        if nx[0] == lp[0]:
            break
        lp.append(nx[0])
    if len(lp) != len(rv):
        return W, faces, None, 0
    x = W[lp, 0]
    i0, i1, m = int(np.argmin(x)), int(np.argmax(x)), len(lp)
    a = [lp[(i0 + k) % m] for k in range((i1 - i0) % m + 1)]
    b = [lp[(i1 + k) % m] for k in range((i0 - i1) % m + 1)][::-1]
    up, lo = (a, b) if W[a, 2].mean() > W[b, 2].mean() else (b, a)

    def arc(P):
        d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(W[P], axis=0), axis=1))]
        return d / max(float(d[-1]), 1e-12)
    su, sl = arc(up), arc(lo)
    to = np.arange(len(W))
    for v, t in zip(lo[1:-1], sl[1:-1]):
        to[v] = up[int(np.argmin(np.abs(su - t)))]
    W = W.copy()
    for k, v in enumerate(up[1:-1], 1):  # the seam halfway between the lips (lower position by arc, interpolated)
        q = np.array([np.interp(su[k], sl, W[lo, j]) for j in range(3)])
        W[v] = 0.5 * (W[v] + q)
    gone = {v for v, lv in lev.items() if lv < ring}
    out = []
    for f in faces:
        if any(v in gone for v in f):
            continue
        g = [int(to[v]) for v in f]
        g = [v for k, v in enumerate(g) if v != g[k - 1]]
        if len(set(g)) >= 3:
            out.append(g)
    used = sorted({v for f in out for v in f})
    rm = np.full(len(W), -1)
    rm[used] = np.arange(len(used))
    return W[used], [[int(rm[v]) for v in f] for f in out], rm, len(up) - 2
