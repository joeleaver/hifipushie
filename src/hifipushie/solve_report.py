"""WHAT THE JOINT SOLVE READ, AND WHAT MOVED WITHOUT A READ (solvereads, 2026-10-12).

face_ruler's solve is linear-Gaussian: observations o = J dc + noise, a prior N(0, tau^2) on every identity component.
A named MEASURE of the head (chin projection, eye depth, cheek fullness: a row r over the 170 components) has a prior sd
tau |r| and a posterior sd sqrt(r Cov r'). Their ratio says how much the pictures told the solve about it:

    read = 1 - posterior variance / prior variance      (0 = UNREAD: left where the prior put it; 1 = pinned)

A measure can still MOVE while unread: the reads that pin other things reach it through shared components (a detector's
brow points on a 110 px painting moved Garrett's eye depth 7.8 mm, 2 sd, with no read of eye depth: garrett_a1, the notes'
"## garrettgood"). `report` lists every measure that left the block-in's start by more than MOVED_SD population sd with a
read under UNREAD ("moved with no read") and every measure with a read under UNREAD ("unread: the prior's"), and says
WHICH reads each measure's posterior is owed to (leave-one-group-out: the group whose removal widens it most).

  rows()                 the measures: gnm_mm's 27 (mm), the chin / lower face set (mm), humanmacro's shape words (sd)
  support(post, obs)     -> per measure: prior sd, posterior sd, read, the groups (type, view) that read it
  report(sup, c, c0)     -> {"rows", "moved_unread", "unread", "text"}
  hold_rows(sup, ...)    pseudo-observations that HOLD the unread measures at the start head's values (solve(hold=))
"""
from __future__ import annotations

import numpy as np

UNREAD = 0.25            # a measure with a read under this is the prior's, not the pictures'
MOVED_SD = 0.7           # ... and having left the start by this many population sd it MOVED WITHOUT A READ
MOVED_MM = 2.0           # (or by this many mm, for the measures in mm)
WEAK = 0.6               # a read under this is WEAK: part measurement, part the prior
WEAK_SD = 1.2            # ... and a move past this many population sd on a weak read is reported
HOLD_SIG = 0.05          # population sd: how tightly solve(hold=) keeps an unread measure at the start head's value
_C: dict = {}

# the measures a profile alone shows: with no view turned past ~60 degrees they are INFERRED whatever the linear model says
PROFILE_ONLY = ("eyes_forward", "forehead_forward", "tip_forward", "subnasale_forward", "upper_lip_forward",
                "lower_lip_forward", "chin_forward", "skull_back", "under_chin", "brow_ridge_forward", "side_rim_forward",
                "under_eye_forward", "pogonion_forward", "mentolabial_depth", "forehead_slope", "eye_depth", "brow_ridge",
                "chin_projection")
# which words a reader looks for under a region's heading
REGIONS = {
    "chin and lower face": ("pogonion_forward", "chin_forward", "chin_length", "lower_face_height", "chin_width",
                            "chin_point", "chin_cleft", "mentolabial_depth", "jaw_width", "gonial_width", "jaw_angle",
                            "jaw_square", "gonial_height", "under_chin"),
    "mouth": ("mouth_width", "philtrum_length", "upper_lip_forward", "lower_lip_forward", "lip_fullness"),
    "nose": ("nose_length", "tip_forward", "subnasale_forward", "nose_width", "nose_upturn", "bridge_hump"),
    "eyes and orbit": ("pupils_apart", "eyes_forward", "eyes_height", "brows_over_eyes", "brow_ridge_forward",
                       "side_rim_forward", "under_eye_forward", "brow_hollow", "orbital_rim"),
    "cheeks": ("cheekbone_width", "cheek_fullness"),
    "skull": ("forehead_forward", "forehead_slope", "skull_width", "skull_top", "skull_back", "neck_width", "ear_out",
              "ear_size"),
}
SAY = {"pogonion_forward": "the chin's front (pogonion) forward of the nasion: the profile's chin projection",
       "lower_face_height": "nose base to the chin's bottom",
       "chin_point": "pointed (+) / square, flat-bottomed (-) chin: the chin's bottom below the jaw line beside it",
       "mentolabial_depth": "the groove between lower lip and chin: its depth behind the lip-to-chin line",
       "gonial_width": "the jaw's width at its angles (landmarks 3-13)"}
MACROS = ("jaw_angle", "jaw_square", "gonial_height", "chin_cleft", "cheek_fullness", "forehead_slope", "lip_fullness",
          "nose_upturn", "bridge_hump", "orbital_rim", "ear_out", "ear_size")


def _chin_sets() -> dict:
    """Template vertices of the chin's midline: the B point (the deepest point between the lower lip and the chin's
    front on the midline), fixed on GNM's template so every measure is linear in the vertices."""
    if "sets" not in _C:
        from . import gnm_mm
        sp = gnm_mm._space()
        T, gr = sp["T"] * 1000, sp["gr"]
        L = sp["WL"] @ T
        pog = T[sp["sets"]["pog"]].mean(0)
        mid = gr["skin_exterior"] & (np.abs(T[:, 0]) < 1.5) & (T[:, 1] < L[57, 1] - 1.0) & (T[:, 1] > pog[1] + 1.0) & (T[:, 2] > pog[2] - 15)
        ids = np.flatnonzero(mid)
        # depth behind the chord lower lip (lm 57) -> pogonion, in the sagittal plane
        d = np.array([pog[1] - L[57, 1], pog[2] - L[57, 2]])
        d /= np.linalg.norm(d)
        n = np.array([-d[1], d[0]])
        if n[1] < 0:
            n = -n                                          # n points forward (+z)
        dep = -((T[ids][:, 1:] - L[57, 1:]) @ n)            # + = behind the chord
        o = ids[np.argsort(-dep)[:4]]
        _C["sets"] = {"B": o, "n": n}
    return _C["sets"]


def chin_readers(V: np.ndarray) -> dict:
    """The chin / lower face set (mm) on GNM-frame vertices V (m): what gnm_mm's 27 leave out."""
    from . import gnm_mm
    sp = gnm_mm._space()
    V = V * 1000
    L = sp["WL"] @ V
    pog = V[sp["sets"]["pog"]].mean(0)
    cs = _chin_sets()
    B = V[cs["B"]].mean(0)
    chord = 0.5 * (L[57, 1:] + pog[1:])
    return {"pogonion_forward": pog[2] - L[27, 2],
            "lower_face_height": L[33, 1] - L[8, 1],
            "chin_point": 0.5 * (L[7, 1] + L[9, 1]) - L[8, 1],
            "mentolabial_depth": float((chord - B[1:]) @ cs["n"]),
            "gonial_width": L[13, 0] - L[3, 0]}


def rows() -> dict:
    """The measures as rows over GNM's 170 head components: {"names", "R" (n, 170), "unit" ("mm" | "sd"), "sd"
    (population sd in the row's own unit: comps ~ N(0, 1)), "say"}. gnm_mm's 27 and the chin set in mm (exact: linear
    in the vertices, at GNM's template); humanmacro's words in population sd (its calibrated linear map)."""
    if "rows" not in _C:
        from . import gnm_mm, humanmacro as hm
        sp = gnm_mm._space()
        names = list(gnm_mm.NAMES)
        R = [gnm_mm.jacobian()[:len(names)]]
        r0 = chin_readers(sp["T"])
        ck = list(r0)
        Jc = np.zeros((len(ck), 170))
        for k in range(170):
            r = chin_readers(sp["T"] + sp["IB"][k] * 1e-3)
            Jc[:, k] = [(r[n] - r0[n]) / 1e-3 for n in ck]
        R.append(Jc)
        names += ck
        unit = ["mm"] * len(names)
        t = hm.table()
        Am = np.zeros((len(MACROS), 170))
        for i, m in enumerate(MACROS):
            j = hm.NAMES.index(m)
            Am[i, :hm.K] = t["A"][j] / t["sd"][j]
        R.append(Am)
        names += list(MACROS)
        unit += ["sd"] * len(MACROS)
        R = np.vstack(R)
        say = {**{n: gnm_mm.SEE[n][1] for n in gnm_mm.NAMES}, **SAY, **{m: hm.MACROS[m][1] for m in MACROS}}
        _C["rows"] = {"names": names, "R": R, "unit": unit, "sd": np.linalg.norm(R, axis=1), "say": say}
    return _C["rows"]


def _cov(Jx, w, pri, n1):
    A = (Jx * w[:, None]).T @ Jx + np.diag(1.0 / pri ** 2)
    return np.linalg.inv(A)[:n1, :n1]


def support(post: dict, obs: list, groups: bool = True) -> dict:
    """What the solved system knows of each measure. post = face_ruler.solve's "post" (the columns as solved: identity,
    cameras, nuisances; each read's final weight: its sigma after adapt / the cmax relaxation / the robust loss), obs
    the same solve's observations. -> {"names", "prior" (sd, row units), "post", "read", "by": per measure the groups
    (type, view) ranked by how much of its posterior precision is theirs (share 0..1), "n": reads per group}."""
    rw = rows()
    R = rw["R"]
    Jx, w, pri, n1 = post["Jx"], np.asarray(post["w"], float), post["pri"], post["n1"]
    tau = float(post.get("tau", 1.0))
    C = _cov(Jx, w, pri, n1)
    prior = tau * rw["sd"]
    pv = np.einsum("ij,jk,ik->i", R, C, R)
    out = {"names": rw["names"], "unit": rw["unit"], "prior": prior, "post": np.sqrt(np.maximum(pv, 0)),
           "read": np.clip(1 - pv / prior ** 2, 0, 1), "by": {}, "n": {}}
    if groups:
        G = {}
        for i, ob in enumerate(obs):
            G.setdefault((ob["type"], ob["view"]), []).append(i)
        out["n"] = {k: len(v) for k, v in G.items()}
        loss = {}
        for key, ii in G.items():
            w2 = w.copy()
            w2[ii] = 0.0
            pv2 = np.einsum("ij,jk,ik->i", R, _cov(Jx, w2, pri, n1), R)
            loss[key] = 1 - pv / np.maximum(pv2, 1e-30)          # the share of the remaining uncertainty this group removes
        for j, n in enumerate(rw["names"]):
            out["by"][n] = sorted(((k, float(v[j])) for k, v in loss.items()), key=lambda t: -t[1])
    return out


# ---- the DIRECT read: does any observation LOOK at the measure's own points? ------------------------------------------
# Under GNM's 170 components and their N(0, 1) prior the solve "reads" everything (gg_A06: cheek_fullness 0.91, eye depth
# 0.94 from the profile's outline): 600 reads pin 170 global components, and every measure is a function of those. That
# is the prior's correlations carrying a measure nothing looks at: true of the population, not a measurement of this
# face. The direct read drops the global model: the surface may move FREELY and locally (a Gaussian process over the
# surface: each axis sd LOCAL_SD mm, correlation length RHO mm), an observation tells the displacement of its own
# surface point along its own picture direction, a measure is its own points' displacements (its FOOTPRINT: d measure /
# d vertex). read = 1 - posterior / prior variance of the measure in THAT model, cameras free as in the solve. A cheek
# 30 mm inside every silhouette: 0. A chin's front in a front view (its normal points at the camera): 0. The same chin
# on a profile's outline: ~1.
RHO = 12.0               # mm: how far along the surface one read speaks for its neighbours
LOCAL_SD = 3.0           # mm: how far a real face may stand off the solved head locally, per axis


def footprint() -> dict:
    """Each measure's gradient over GNM's vertices: {name: (vertex ids, (n, 3) row units per mm, raw GNM frame)}. By
    finite differences on the template over the vertices the readers use; cached on disk."""
    if "fp" in _C:
        return _C["fp"]
    import hashlib
    from pathlib import Path
    from . import gnm_mm, humanmacro as hm, store
    key = hashlib.sha1(Path(__file__).read_bytes() + Path(gnm_mm.__file__).read_bytes() + Path(hm.__file__).read_bytes()).hexdigest()[:16]
    f = store.HOME / "_cache" / f"solve_report_fp_{key}.npz"
    rw = rows()
    if f.exists():
        z = np.load(f)
        _C["fp"] = {n: (z[f"i_{n}"], z[f"g_{n}"]) for n in rw["names"]}
        return _C["fp"]
    sp, hs = gnm_mm._space(), hm.space()
    T, gr = sp["T"], sp["gr"]
    cand = np.zeros(len(T), bool)
    cand[np.flatnonzero(np.abs(sp["WL"]).sum(0) > 0)] = True
    cand[np.flatnonzero(np.abs(hs["W"]).sum(0) > 0)] = True
    for d in (sp["sets"], sp["orb"], hs["sets"]):
        for ids in d.values():
            cand[np.asarray(ids, int)] = True
    cand[_chin_sets()["B"]] = True
    cand |= gr["middle_brow_region"]
    eyes = gr["left_eye"] | gr["right_eye"]
    cand &= ~eyes                                   # the eyeballs are rigid: one probe each, below
    t = hm.table()
    M = np.array([[1.0, 0, 0], [0, 0, -1.0], [0, 1.0, 0]])      # humanmacro's world frame = M @ raw GNM
    mi = [hm.NAMES.index(m) for m in MACROS]
    nmm = len(rw["names"]) - len(MACROS)

    def f_all(V):
        r = {**gnm_mm.readers(V), **chin_readers(V)}
        mm = hm.measures(V @ M.T)
        return np.array([r[n] for n in rw["names"][:nmm]] + [mm[m] / t["sd"][j] for m, j in zip(MACROS, mi)])
    f0 = f_all(T)
    h = 2e-4
    ids = np.flatnonzero(cand)
    G = np.zeros((len(ids) + 2, 3, len(f0)))
    for a, v in enumerate(ids):
        for ax in range(3):
            V = T.copy()
            V[v, ax] += h
            G[a, ax] = (f_all(V) - f0) / (h * 1000)
    for a, g_ in enumerate(("left_eye", "right_eye")):          # each eyeball moved whole
        for ax in range(3):
            V = T.copy()
            V[gr[g_], ax] += h
            G[len(ids) + a, ax] = (f_all(V) - f0) / (h * 1000)
    ids = np.r_[ids, -1, -2]                                    # -1 / -2: the left / right eyeball as one point
    out, sv = {}, {}
    for j, n in enumerate(rw["names"]):
        g = G[:, :, j]
        k = np.abs(g).max(1) > 1e-6 * max(np.abs(g).max(), 1e-30)
        out[n] = (ids[k], g[k])
        sv[f"i_{n}"], sv[f"g_{n}"] = ids[k], g[k]
    f.parent.mkdir(parents=True, exist_ok=True)
    np.savez(f, **sv)
    _C["fp"] = out
    return out


def direct(post: dict, obs: list, views: list, head: dict, groups: bool = True) -> dict:
    """The DIRECT read of every measure (see above). post / obs = the solve's (face_ruler.solve "post"; the cameras' and
    nuisances' columns and priors and each read's final weight come from it), views = its views (their cameras), head =
    face_ruler.model_head. -> {"read" (n,), "by": per measure [(group, share)], "n": the reads that look at a point}."""
    from . import face_ruler as fr
    rw, fp = rows(), footprint()
    Jx, w, pri, n1 = post["Jx"], np.asarray(post["w"], float), post["pri"], post["n1"]
    cams = {}
    for v in views:
        cams.setdefault(v["kind"], v["cam"])
    E = np.asarray(head["eye_X"], float) * 1000.0               # eye centres
    ii, X, N3 = [], [], []
    for i, ob in enumerate(obs):
        if "X" not in ob or ob["view"] not in cams:
            continue
        n = np.asarray(ob["n"], float) if "n" in ob else np.array([1.0, 0.0] if ob["name"].endswith(".x") else [0.0, 1.0])
        Jp, mm1 = fr._proj_jac_pt(cams[ob["view"]], np.asarray(ob["X"], float), np.eye(3))
        x = np.asarray(ob["X"], float) * 1000.0
        if ob["type"] in ("iris", "limbus"):
            x = E[int(np.argmin(np.linalg.norm(E - x, axis=1)))]
        ii.append(i)
        X.append(x)
        N3.append((n[0] * Jp[0] + n[1] * Jp[1]) * mm1 * 1e-3)   # mm of the read per mm of the point's world move
    ii, X, N3 = np.array(ii, int), np.array(X), np.array(N3)
    s2 = LOCAL_SD ** 2
    k_ = lambda A, B: np.exp(-((A[:, None, :] - B[None, :, :]) ** 2).sum(-1) / (2 * RHO ** 2))  # noqa: E731
    C = Jx[ii][:, n1:]
    Koo = s2 * (N3 @ N3.T) * k_(X, X) + (C * pri[n1:] ** 2) @ C.T + np.diag(1.0 / np.maximum(w[ii], 1e-12))
    g2m = fr._gnm_to_model(head)
    R, sc = np.asarray(head["R"], float), float(head["sc"])
    V = np.asarray(head["V"], float) * 1000.0
    eL = int(np.argmax(E[:, 0]))                                # the subject's left eye: world +X
    Kmo, Kmm = np.zeros((len(rw["names"]), len(ii))), np.zeros(len(rw["names"]))
    for j, n in enumerate(rw["names"]):
        ids, g = fp[n]
        P, A = [], []
        for v, a in zip(ids, g):
            if v < 0:
                P.append(E[eL] if v == -1 else E[1 - eL])
            elif int(v) in g2m:
                P.append(V[g2m[int(v)]])
            else:
                continue
            A.append(a @ R.T / sc)                              # raw GNM gradient -> per mm of world move
        if not P:
            continue
        P, A = np.array(P), np.array(A)
        Kmm[j] = s2 * float(((A @ A.T) * k_(P, P)).sum())
        Kmo[j] = s2 * ((A @ N3.T) * k_(P, X)).sum(0)

    def reads(keep):
        Ki = np.linalg.inv(Koo[np.ix_(keep, keep)])
        pv = Kmm - np.einsum("mi,ij,mj->m", Kmo[:, keep], Ki, Kmo[:, keep])
        return np.clip(1 - pv / np.maximum(Kmm, 1e-30), 0, 1) * (Kmm > 0)
    allk = np.arange(len(ii))
    rd = reads(allk)
    out = {"read": rd, "by": {}, "n": len(ii)}
    if groups:
        G = {}
        for a, i in enumerate(ii):
            G.setdefault((obs[i]["type"], obs[i]["view"]), []).append(a)
        loss = {key: rd - reads(np.setdiff1d(allk, np.array(aa))) for key, aa in G.items()}
        for j, n in enumerate(rw["names"]):
            out["by"][n] = sorted(((k, float(v[j])) for k, v in loss.items()), key=lambda t_: -t_[1])
    return out


def report(sup: dict, c, c0, turned: float | None = None, drc: dict | None = None) -> dict:
    """The MOVED WITHOUT A READ report. c = the identity after the solve, c0 = the block-in's start (its class mean),
    sup = support() (the solve's own model: its posterior sd), drc = direct() (does any read LOOK at the measure: the
    row's "read"; without it the model's read is used, and PROFILE_ONLY measures count as unread when no view's camera
    is turned past 60 degrees: `turned` = the largest |yaw|). -> {"rows": [{measure, unit, moved, moved_sd, prior, post,
    read, model_read, by}], "moved_unread", "unread", "text"}."""
    rw = rows()
    mv = rw["R"] @ (np.asarray(c, float) - np.asarray(c0, float))
    out = []
    src = drc if drc is not None else sup
    for j, n in enumerate(rw["names"]):
        rd = float(src["read"][j])
        inferred = drc is None and turned is not None and turned < 60.0 and n in PROFILE_ONLY
        by = [(f"{t} {v}", s) for (t, v), s in (src["by"].get(n) or [])[:2] if s > 0.15]
        out.append({"measure": n, "unit": rw["unit"][j], "moved": float(mv[j]), "moved_sd": float(mv[j] / rw["sd"][j]),
                    "prior": float(sup["prior"][j]), "post": float(sup["post"][j]), "read": rd, "by": by,
                    "model_read": float(sup["read"][j]),
                    "no_side_view": bool(inferred), "unread": bool(rd < UNREAD or inferred)})
    big = lambda r: abs(r["moved_sd"]) >= MOVED_SD or (r["unit"] == "mm" and abs(r["moved"]) >= MOVED_MM)  # noqa: E731
    mu = sorted([r for r in out if r["unread"] and big(r)], key=lambda r: -abs(r["moved_sd"]))
    un = [r for r in out if r["unread"] and not big(r)]

    def one(r):
        a = f"{r['measure']} {r['moved']:+.1f} {'mm' if r['unit'] == 'mm' else 'sd'}"
        if r["unit"] == "mm":
            a += f" ({r['moved_sd']:+.1f} sd)"
        why = "no side view" if r["no_side_view"] and r["read"] >= UNREAD else f"read {r['read']:.2f}"
        if r["by"]:
            why += ", carried by " + " + ".join(b for b, _ in r["by"])
        return f"{a} [{why}]"
    lines = []
    if mu:
        lines.append(f"MOVED WITH NO READ (left the start by > {MOVED_SD:g} sd or {MOVED_MM:g} mm while these pictures do not "
                     "show it: an invention of the prior's correlations, not a measurement): " + "; ".join(one(r) for r in mu))
    # a WEAK read (a 3/4's foreshortened depth through detector points, one cheek's outline for both): the move is
    # partly the pictures', partly the prior's; past WEAK_SD it is worth a look (garrett_a1's eye depth: read 0.52 from
    # the 3/4 painting's detector points, moved -7.3 mm = 1.8 sd; the good set says 4-5 mm of that was wrong)
    wk = sorted([r for r in out if not r["unread"] and r["read"] < WEAK and abs(r["moved_sd"]) >= WEAK_SD], key=lambda r: -abs(r["moved_sd"]))
    for r in out:
        r["weak"] = bool(not r["unread"] and r["read"] < WEAK)
    if wk:
        lines.append(f"MOVED FAR ON A WEAK READ (over {WEAK_SD:g} sd on a read under {WEAK:g}: part measurement, part the prior's "
                     "correlations; INFERRED, check it by eye or get a picture that shows it): " + "; ".join(one(r) for r in wk))
    if un:
        lines.append("unread (left near the start head's: the pictures do not show it): " + ", ".join(r["measure"] for r in un))
    return {"rows": out, "moved_unread": mu, "moved_weak": wk, "unread": un, "text": "\n".join(lines)}


def table_text(rep: dict, region: str | None = None) -> str:
    """The report's rows as a table (one region's, or all)."""
    keep = None if region is None else set(REGIONS[region])
    s = ["measure               moved      population sd   model's posterior sd (its read)   DIRECT read   looked at by"]
    for r in rep["rows"]:
        if keep is not None and r["measure"] not in keep:
            continue
        u = "mm" if r["unit"] == "mm" else "sd"
        s.append(f"{r['measure']:20s} {r['moved']:+6.1f} {u}   {r['prior']:5.2f} {u}       {r['post']:5.2f} {u} ({r['model_read']:.2f})"
                 f"                 {r['read']:.2f}{' *' if r['unread'] else '  '}      " + ", ".join(f"{b} {x:.2f}" for b, x in r["by"]))
    return "\n".join(s)


def hold_rows(read, done=None, names=None) -> list:
    """Pseudo-observations for solve(): every UNREAD measure (read = direct()["read"], under UNREAD; or the measures
    named) held at the start head's value: o = -(its move so far: done = c - c0), sigma HOLD_SIG population sd. The
    solve then cannot carry an unread measure along the prior's correlations with the measures the pictures do show."""
    rw = rows()
    out = []
    mv = rw["R"] @ np.asarray(done, float) if done is not None else np.zeros(len(rw["names"]))
    for j, n in enumerate(rw["names"]):
        if names is not None and n not in names:
            continue
        if names is None and not read[j] < UNREAD:
            continue
        out.append({"type": "hold", "view": "prior", "name": f"hold_{n}", "o": float(-mv[j]), "J": rw["R"][j].copy(),
                    "sig": float(HOLD_SIG * rw["sd"][j])})
    return out


# ---- the TIE (chinread, 2026-10-12): unread widths follow GNM's population, they do not drift ---------------------------
TIE = ("chin_width", "jaw_width", "gonial_width", "jaw_square")       # what no picture of a front / shallow 3/4 / side set reads
TIE_GIVEN = ("pupils_apart", "eyes_height", "mouth_width", "nose_length", "philtrum_length", "chin_length")   # read in a front view
TIE_GIVEN_SIDE = ("chin_forward", "pogonion_forward", "tip_forward", "subnasale_forward", "upper_lip_forward", "lower_lip_forward",
                  "forehead_forward", "mentolabial_depth")            # + read on a side view's outline
TIE_SIG = 0.3            # x the measure's conditional sd: how tightly it is tied to its expectation


def tie_rows(done=None, names=TIE, given=TIE_GIVEN + TIE_GIVEN_SIDE, sig: float = TIE_SIG) -> list:
    """Pseudo-observations for solve(): each named measure TIED to its expectation given the measures the pictures do
    read, in GNM's own population (comps ~ N(0, 1): cov = R R'). The row is the part of the measure that is independent
    of the given ones, r = R_u - K R_g with K = R_u R_g' (R_g R_g')^-1; its whole move since the start (done = c - c0,
    the class mean's head) is held at 0 with sigma = sig x |r| (the conditional sd). So a jaw may widen WITH a face
    that the pictures show to be larger or longer, as people's do; it may not widen on its own account, which is what
    biased reads did to it (+5 .. +9 mm on known heads whatever their truth: the notes' "## chinread")."""
    rw = rows()
    idx = {n: i for i, n in enumerate(rw["names"])}
    G = np.array([rw["R"][idx[g]] for g in given if g not in names]) if given else np.zeros((0, rw["R"].shape[1]))
    out = []
    d = np.asarray(done, float) if done is not None else np.zeros(rw["R"].shape[1])
    for n in names:
        r = rw["R"][idx[n]].copy()
        if len(G):
            r = r - G.T @ np.linalg.solve(G @ G.T, G @ r)
        cs = float(np.linalg.norm(r))
        out.append({"type": "hold", "view": "prior", "name": f"tie_{n}", "o": float(-(r @ d)), "J": r, "sig": float(sig * cs), "cond_sd": cs})
    return out


SIZE_SIG = 0.003         # the head's size held to +-0.3 % of the start head's


SIZE_IRIS_SIG = 0.07     # the iris as a ruler of the head's size: GNM's limbus is 6.0 +- 0.44 mm person to person


def size_gain() -> np.ndarray:
    """The head's SIZE per unit identity component (170,): the hockey mask's similarity scale, linear at the template."""
    return size_row()["J"]


def size_prior_sd() -> float:
    """How much the head's size varies in GNM's population (c ~ N(0, 1) per component): |size_gain|."""
    return float(np.linalg.norm(size_gain()))


def size_row(done=None, sig: float = SIZE_SIG, target: float = 0.0) -> dict:
    """A pseudo-observation for solve(): the face's SIZE stays the start head's. Every camera's scale is free, so no
    picture can tell a head 4 % larger from a camera 4 % closer; left to itself the identity grows (the benchmark's
    heads end 1-8 % large: bobble-heads on their bodies, and every mm measure off by as much). The row is the
    similarity scale of the hockey mask per unit comp (linear at GNM's template)."""
    if "size" not in _C:
        from . import gnm_mm
        sp = gnm_mm._space()
        m = sp["gr"]["hockey_mask"]
        X = sp["T"][m] - sp["T"][m].mean(0)
        D = sp["IB"][:, m] - sp["IB"][:, m].mean(1, keepdims=True)
        _C["size"] = np.einsum("vc,kvc->k", X, D) / float((X ** 2).sum())
    g = _C["size"]
    d = np.asarray(done, float) if done is not None else np.zeros(len(g))
    # target: the size wanted against the start head's (0 = held there; +0.04 = 4 % larger: the iris' say)
    return {"type": "hold", "view": "prior", "name": "hold_size", "o": float(target - (g @ d)), "J": g.copy(), "sig": float(sig)}


# ---- the NECK (nativedefault, 2026-10-12): no picture reads its girth; GNM's identity moves it 36 mm per sd ------------------
NECK_RINGS = range(14, 25)   # GNM's neck rings above the seam ring: the narrowest of them is "the neck's girth"
NECK_SIG = 0.01          # neck="held" / a given girth: +-1 % of the target. The DEFAULT is a PRIOR, not a hold: ANSUR's own
# sd for the sex (women 5.5 %, men 6.3 %: onemesh.ANSUR) about its mean for the stature. Validated on chinread's known
# heads (docs/notes/gnm_atlas.md "## nativedefault"): the free solve already finds a known head's neck to 13.5 mm rms
# (GNM's correlations with the jaw and face it does read), a 1 % hold at the population's mean throws that away (31 mm
# rms; one thin-necked head's lower face +0.9 mm) while the prior keeps it and only takes out GNM's bias (women +11 %)


def neck_girth(c) -> tuple:
    """(girth m, ring, gradient (170,) m per component) of GNM's neck at its NARROWEST ring for the identity c (170):
    the loop's length on GNM's own evaluation (GNM's metres; a native head stands at x base.head.size of it). GNM's
    female class mean is 363 mm (ANSUR II women 330 +- 18), its male mean 385 (398 +- 25), and head_000 / head_001
    carry 33 / 10 mm of it per sd with no picture reading it (docs/notes/headbody.md)."""
    from . import gnm_mm, onemesh
    sp = gnm_mm._space()
    c = np.asarray(c, float)[:170]
    best = None
    for k in NECK_RINGS:
        lp = onemesh._ring_loop(k)
        X = sp["T"][lp] + np.tensordot(c, sp["IB"][:, lp], 1)
        e = X - np.roll(X, -1, 0)
        L = float(np.linalg.norm(e, axis=1).sum())
        if best is None or L < best[0]:
            best = (L, k, lp, e)
    L, k, lp, e = best
    u = e / np.linalg.norm(e, axis=1, keepdims=True)
    D = sp["IB"][:, lp]
    return L, int(k), np.einsum("vc,kvc->k", u, D - np.roll(D, -1, 1))


def neck_row(c, target: float, sig: float = NECK_SIG) -> dict:
    """A pseudo-observation for solve(): the neck's girth (GNM's metres, at its narrowest) is `target`, +- sig x target
    (sig = ANSUR's sd: the anthropometric PRIOR, the default; 0.01: a hold).
    Linearised at the head as it stands (c: the whole identity), re-taken every round. As size_row: a statement no
    picture can make (collars, hair and the jaw's shadow hide the neck; a front view shows a width, not a girth)."""
    L, k, g = neck_girth(c)
    return {"type": "hold", "view": "prior", "name": "hold_neck", "o": float(target - L), "J": g, "sig": float(sig * target)}


def neck_move(c, target: float, hold: float = 5.0, rounds: int = 4) -> dict:
    """The least identity change that brings the neck's girth to `target` (GNM's metres) with the head's SIZE kept and
    every measure of rows() but the neck's own held (weight `hold` per population sd): what a block-in step
    {"neck_mm": mm} applies. -> {"dc", "girth0", "girth", "ring", "cost" (|dc|), "moved": [(measure, change, unit)]}."""
    rw = rows()
    keep = [i for i, n in enumerate(rw["names"]) if "neck" not in n]
    H = hold * rw["R"][keep] / rw["sd"][keep][:, None]
    sz = size_row()["J"]
    c = np.asarray(c, float)[:170].copy()
    c0 = c.copy()
    g0 = neck_girth(c)[0]
    for _ in range(rounds):
        L, k, g = neck_girth(c)
        # min |d|^2 + |H (c + d - c0)|^2  s.t.  g.d = target - L, sz.(c + d - c0) = 0
        M = np.eye(170) + H.T @ H
        rhs = -H.T @ (H @ (c - c0))
        C = np.vstack([g, sz])
        b = np.array([target - L, -float(sz @ (c - c0))])
        Mi = np.linalg.inv(M)
        lam = np.linalg.solve(C @ Mi @ C.T, b - C @ Mi @ rhs)
        c = c + Mi @ (rhs + C.T @ lam)
    L, k, _ = neck_girth(c)
    mv = rw["R"] @ (c - c0)
    top = sorted(((n, float(x), u, float(x / s_)) for n, x, u, s_ in zip(rw["names"], mv, rw["unit"], rw["sd"])), key=lambda t: -abs(t[3]))[:5]
    return {"dc": c - c0, "girth0": g0, "girth": L, "ring": k, "cost": float(np.linalg.norm(c - c0)),
            "moved": [(n, x, u) for n, x, u, _ in top]}
