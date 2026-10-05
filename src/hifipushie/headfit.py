"""A GNM head (base.head) given an age, a sex and a weight: by its body, or by name.

GNM's identities are seeded adults with no age or sex controls. MakeHuman's macro targets shape a whole head for any
age, sex and weight on a FIXED topology, so they were sampled once:
- `makehuman_lm68.json` (spikes/headfit/make_table.py): the MakeHuman vertices at GNM's 68 face landmarks, four cranium
  points and ~350 dense pairs over the face, cranium and neck (the two neutral heads aligned, nearest vertices, forced
  symmetric, checked in a picture);
- `head_axes.npz` (spikes/headfit/make_axes.py): how those points MOVE from MakeHuman's reference head (25 years, sex
  0.5, weight 0.5) across ages x sex and with weight, in interocular units round the eye midpoint.
Neither needs the MakeHuman pack at runtime.

The move for the asked age / sex / weight is added to the seeded GNM head's own points (delta transfer: the tables'
millimetres of mismatch cancel) and made in two steps: GNM's identity components by ridge least squares (eye centres
held), then what they leave undone (30-40% of a move: jaw and chin width, brow ridge, the neck's girth) as a smooth
warp of the head (Gaussian RBF on the points' residuals; the lids and lips take little of either). The seed first
loses its OWN sex / age / weight (its component along those directions): a random person leans male or female as
much as the move itself, and a heavy-jawed seed left a woman a man.

base.head keys (all off / neutral unless given: existing characters keep their heads bit for bit):
  follow_body  true | strength 0..1.5: the head takes its MakeHuman body's age, sex and weight, and its size
               (scale = the body's interocular over the head's)
  like         {"age", "sex" (0 female .. 1 male), "weight" (0..1)}: the same controls set apart from the body
               ("an older face on a young body"), or on any body (the stylised template too). Keys left out follow
               the body with follow_body, else stay neutral.
  features     {"brow_ridge", "jaw", "chin", "nose", "lips", "cheeks", "eyes", "cranium": -1.5..1.5}: one part of
               those moves on its own (+ = more: a heavier brow, a wider jaw, a bigger chin or nose, fuller lips and
               cheeks, bigger eyes, more cranium over the face). The brow, jaw, chin, nose and lips are
               the sex move's own parts (a man's lower heavier brow, longer wider jaw and chin, bigger nose, thinner
               lips), the eyes and cranium the child's; cheeks are pushed out.
The head's own `identity` entries and a given `scale` win over what this solves.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

_CACHE: dict = {}
N = 120  # identity components solved
LAM = 1.5e-6  # ridge on the components (they are in standard deviations; the equations in metres)
CLIP = 2.6
# what the move is trusted for: the outline, brows and nose in full; the lids and lips less (their moves are
# millimetres, near the table's own error, and pushed hard they tore the lid margins and twisted the lips)
W_LM = np.r_[np.ones(36), np.full(12, 0.3), np.full(12, 0.5), np.full(8, 0.15)]
CRANIUM = ("top", "back", "side.L", "side.R")
W_CRANIUM = 1.0
W_EYES = 4.0
W_DENSE = 0.45  # each dense pair. They also hold the neck and bib to the body's: left free, the fit flared the bib up
# to the graft plane (a stand-up collar round old bodies' necks)
WARP_SIGMA = 0.42  # interoculars
WARP_RIDGE = 0.02
REF = {"age": 25.0, "sex": 0.5, "weight": 0.5}
AXES = ({"sex": 1.0}, {"sex": 0.0}, {"age": 8}, {"age": 80}, {"weight": 0.9}, {"weight": 0.15})
# features: (landmark ids the region is centred on, radius in interoculars, which move, its sign)
FEATURES = {"brow_ridge": (list(range(17, 27)) + [27], 0.3, "sex", 1.0),
            "jaw": (list(range(0, 7)) + list(range(10, 17)), 0.42, "sex", 1.0),
            "chin": ([7, 8, 9], 0.33, "sex", 1.0),
            "nose": (list(range(27, 36)), 0.28, "sex", 1.0),
            "lips": (list(range(48, 68)), 0.24, "sex", -1.0),
            "cheeks": ([2, 3, 4, 12, 13, 14, 31, 35, 48, 54], 0.4, "out", 1.0),
            "eyes": (list(range(36, 48)), 0.26, "child", 1.0),
            "cranium": (["top", "back", "side.L", "side.R", 19, 24], 0.75, "child", 1.0)}
KEYS = ("follow_body", "like", "features", "toward", "dimorphism")
DIMORPHISM = 0.8


def table() -> dict:
    if "table" not in _CACHE:
        _CACHE["table"] = json.loads(Path(__file__).with_name("makehuman_lm68.json").read_text())
    return _CACHE["table"]


def axes() -> dict:
    if "axes_data" not in _CACHE:
        z = np.load(Path(__file__).with_name("head_axes.npz"))
        _CACHE["axes_data"] = {k: np.asarray(z[k], float) for k in z.files}
    return _CACHE["axes_data"]


def mh_points(params: dict) -> tuple:
    """(points, 3) of a MakeHuman head (needs its pack: the one-off scripts and the body's own size use it): the
    table's landmarks, cranium points and dense pairs in GNM's frame (x = the head's left, y up, z forward),
    interocular units round the eye midpoint; and the interocular in metres."""
    from . import makehuman
    t = table()
    b = makehuman.body(params)
    P = np.asarray(b["P"], float)
    if len(P) != t["vertices"]:
        raise ValueError(f"MakeHuman's mesh has {len(P)} vertices, the landmark table was made for {t['vertices']}: "
                         "remake it (spikes/headfit/make_table.py, make_axes.py)")
    el = np.array(b["face"]["landmarks"]["eye.L"], float)
    io = 2 * abs(el[0])
    X = P[t["lm68"] + [t["extra"][k] for k in CRANIUM] + t["dense_mh"]] - el * [0, 1, 1]
    return np.c_[X[:, 0], X[:, 2], -X[:, 1]] / io, io


def shape_delta(age: float, sex: float, weight: float = 0.5) -> tuple:
    """The points' move (interoculars) from the reference head to a head of this age, sex (0 female .. 1 male) and
    weight, from the sampled table; and that head's interocular (m, at MakeHuman's own height)."""
    a = axes()
    ages = a["ages"]
    s = float(np.clip(sex, 0, 1))
    x = float(np.clip(age, ages[0], ages[-1]))
    i = int(np.clip(np.searchsorted(ages, x) - 1, 0, len(ages) - 2))
    f = (x - ages[i]) / (ages[i + 1] - ages[i])
    at = lambda T: (1 - f) * ((1 - s) * T[i, 0] + s * T[i, 1]) + f * ((1 - s) * T[i + 1, 0] + s * T[i + 1, 1])
    d = at(a["age_sex"])
    if "zero" not in a:  # sex 0.5 isn't exactly the mean of the two sexes' heads (each is in its own interoculars)
        j = int(np.searchsorted(ages, REF["age"]))
        a["zero"] = 0.5 * (a["age_sex"][j, 0] + a["age_sex"][j, 1])
    d = d - a["zero"] * (1 - abs(2 * s - 1)) * max(0.0, 1 - abs(x - REF["age"]) / 7)
    w = float(np.clip(weight, 0, 1)) - 0.5
    k = 0 if w < 0 else 1
    d = d + abs(w) / 0.4 * ((1 - s) * a["weight"][0, k] + s * a["weight"][1, k])
    return d, float(at(a["io"]))


def fields() -> dict:
    """MakeHuman's heads as displacement fields on GNM's vertices (spikes/headfit/make_field.py)."""
    if "fields" not in _CACHE:
        z = np.load(Path(__file__).with_name("head_fields.npz"))
        _CACHE["fields"] = {k: z[k] for k in z.files}
    return _CACHE["fields"]


def field_vertices(desc: dict) -> np.ndarray:
    """(GNM vertices, 3), interoculars: the mean GNM head -> MakeHuman's head of desc's age / sex / weight
    (`toward` x the reference head + `amount` x the move from it)."""
    key = ("field", json.dumps(desc, sort_keys=True))
    if key not in _CACHE:
        f = fields()
        ages = f["ages"]
        s = float(np.clip(desc["sex"], 0, 1))
        x = float(np.clip(desc["age"], ages[0], ages[-1]))
        i = int(np.clip(np.searchsorted(ages, x) - 1, 0, len(ages) - 2))
        t = (x - ages[i]) / (ages[i + 1] - ages[i])
        T = f["age_sex"]
        d = ((1 - t) * ((1 - s) * T[i, 0].astype(float) + s * T[i, 1]) + t * ((1 - s) * T[i + 1, 0].astype(float) + s * T[i + 1, 1]))
        # sexual dimorphism a little past MakeHuman's own (its sexes differ by ~6 mm rms; on a bald head, under another
        # person's individuality, that much reads as neither)
        dm = float(desc.get("dimorphism", 0.0)) * (1 - 2 * s)
        if dm:
            d = d + 0.5 * dm * ((1 - t) * (T[i, 0].astype(float) - T[i, 1]) + t * (T[i + 1, 0].astype(float) - T[i + 1, 1]))
        j = int(np.searchsorted(ages, REF["age"]))  # (sex 0.5 isn't exactly the mean of the two sexes' heads)
        d = d - 0.5 * (T[j, 0].astype(float) + T[j, 1]) * (1 - abs(2 * s - 1)) * max(0.0, 1 - abs(x - REF["age"]) / 7)
        w = float(np.clip(desc["weight"], 0, 1)) - 0.5
        k = 0 if w < 0 else 1
        d = d + abs(w) / 0.4 * ((1 - s) * f["weight"][0, k].astype(float) + s * f["weight"][1, k])
        _CACHE[key] = desc.get("toward", 1.0) * f["ref"].astype(float) + desc.get("amount", 1.0) * d
    return _CACHE[key]


def _follows(base: dict) -> bool:
    f = (base.get("head") or {}).get("follow_body")
    return bool(f) and float(f) > 0 and (base.get("body") or {}).get("source") == "makehuman"


def applies(base: dict) -> bool:
    head = base.get("head") or {}
    if head.get("source", "gnm") != "gnm":
        return False
    return _follows(base) or bool(head.get("like")) or bool(head.get("features"))


def wanted(base: dict) -> dict:
    """{"age", "sex", "weight", "amount", "features", "follow"}: what the head is asked to be."""
    head = base.get("head") or {}
    body = base.get("body") or {}
    f = head.get("follow_body")
    follow_on = _follows(base)
    like = dict(head.get("like") or {})
    bad = set(like) - {"age", "sex", "weight"}
    if bad:
        raise ValueError(f"base head like: unknown {sorted(bad)} (have age, sex, weight)")
    feats = dict(head.get("features") or {})
    bad = set(feats) - set(FEATURES)
    if bad:
        raise ValueError(f"base head features: unknown {sorted(bad)} (have {', '.join(FEATURES)})")
    src = {"age": float(body.get("age", 25)), "sex": float(body.get("sex", 1.0)), "weight": float(body.get("weight", 0.5))} \
        if follow_on else dict(REF)
    out = {k: float(like.get(k, src[k])) for k in REF}
    out.update(amount=(1.0 if f is True else float(f)) if follow_on else 1.0, follow=follow_on,
               features={k: float(np.clip(v, -1.5, 1.5)) for k, v in sorted(feats.items()) if v})
    return out


def _gnm():
    from . import base
    g = base._gnm_data()
    if "gnm" not in _CACHE:
        t = table()
        names = [str(n) for n in g["identity_names"]]
        comps = [i for i, n in enumerate(names) if n.startswith("head")][:N]
        rows = ([list(zip(r[0::2], r[1::2])) for r in g["lm68"]] + [[(t["gnm_extra"][k], 1.0)] for k in CRANIUM]
                + [[(v, 1.0)] for v in t["dense_gnm"]])
        V0 = g["template_vertex_positions"].astype(float)
        B = g["vertex_identity_basis"]
        L0 = np.array([sum(float(w) * V0[int(v)] for v, w in r) for r in rows])
        LB = np.array([[sum(float(w) * B[i][int(v)] for v, w in r) for r in rows] for i in comps], float)
        _CACHE["gnm"] = {"names": names, "comps": comps, "L0": L0, "LB": LB, "rows": rows,
                         "J0": g["template_joint_positions"].astype(float)[2:4],
                         "JB": np.array([g["joint_identity_basis"][i][2:4] for i in comps], float)}
    return _CACHE["gnm"]


def _weights():
    return np.r_[W_LM, np.full(len(CRANIUM), W_CRANIUM), np.full(len(table()["dense_gnm"]), W_DENSE)]


def _solve(d, c0, io_g, w):
    """The components' change that moves the fitted points by d (interoculars) from the identity c0."""
    g = _gnm()
    mb = g["JB"].mean(1)  # (n, 3): how each component moves the eye midpoint
    A = ((g["LB"] - mb[:, None, :]) * w[None, :, None]).reshape(len(c0), -1).T
    b = ((d * io_g) * w[:, None]).ravel()
    Ae = (g["JB"] * W_EYES).reshape(len(c0), -1).T
    M = np.vstack([A, Ae])
    rhs = np.r_[b, np.zeros(Ae.shape[0])]
    dc = np.linalg.solve(M.T @ M + LAM * np.eye(len(c0)), M.T @ rhs)
    for _ in range(6):  # components past the clip are fixed there and the rest solved again
        fixed = np.abs(c0 + dc) >= CLIP
        if not fixed.any():
            break
        dcf = np.where(fixed, np.clip(c0 + dc, -CLIP, CLIP) - c0, 0.0)
        free = ~fixed
        Mf = M[:, free]
        dc = dcf.copy()
        dc[free] = np.linalg.solve(Mf.T @ Mf + LAM * np.eye(int(free.sum())), Mf.T @ (rhs - M @ dcf))
    return dc


def _body_axes():
    """Orthonormal directions in identity space along which sex, age and weight move a head: MakeHuman's own moves
    (the fields) fitted in GNM's components over the whole skin. A seed loses its part along them (a random person
    leans male or female, old or heavy, as much as the asked head does)."""
    if "axes" not in _CACHE:
        from . import base
        g, gd = _gnm(), base._gnm_data()
        skin = np.asarray(gd["skin"], bool)
        io = float(abs(g["J0"][0][0] - g["J0"][1][0]))
        B = np.asarray(gd["vertex_identity_basis"])[g["comps"]][:, skin].reshape(len(g["comps"]), -1).astype(float).T
        fv = lambda **kw: field_vertices({**REF, "toward": 0.0, "amount": 1.0, **kw})[skin].ravel() * io  # noqa: E731
        moves = [fv(sex=1.0) - fv(sex=0.0), fv(age=80), fv(age=8), fv(weight=0.9) - fv(weight=0.15),
                 fv(age=70, sex=1.0) - fv(age=70, sex=0.0)]
        M = np.linalg.solve(B.T @ B + 1e-4 * np.eye(B.shape[1]), B.T @ np.array(moves).T)
        _CACHE["axes"] = np.linalg.qr(M)[0]
    return _CACHE["axes"]


def feature_masks() -> dict:
    """Per feature, a 0..1 weight per fitted point (soft, by distance to the feature's landmarks on the mean head)."""
    if "masks" not in _CACHE:
        g = _gnm()
        io = float(abs(g["J0"][0][0] - g["J0"][1][0]))
        X = (g["L0"] - g["J0"].mean(0)) / io
        idx = lambda k: 68 + CRANIUM.index(k) if isinstance(k, str) else int(k)
        out = {}
        for name, (lms, r, _, _) in FEATURES.items():
            C = X[[idx(k) for k in lms]]
            dmin = np.sqrt(((X[:, None, :] - C[None, :, :]) ** 2).sum(-1)).min(1)
            out[name] = np.exp(-0.5 * (dmin / r) ** 2)
        _CACHE["masks"] = out
    return _CACHE["masks"]


def _feature_move(feats: dict) -> np.ndarray:
    g = _gnm()
    X = (g["L0"] - g["J0"].mean(0)) / float(abs(g["J0"][0][0] - g["J0"][1][0]))
    out = X * [1.0, 0.0, 0.5] - [0.0, 0.0, 0.2]  # away from the head's axis (MakeHuman's weight hardly fills a face)
    moves = {"sex": 0.5 * (shape_delta(25, 1.0)[0] - shape_delta(25, 0.0)[0]),
             "out": 0.07 * out / np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-6),
             "child": shape_delta(6, 0.5)[0]}
    M = feature_masks()
    d = 0.0
    for name, v in feats.items():
        _, _, mv, sign = FEATURES[name]
        d = d + v * sign * M[name][:, None] * moves[mv]
    return d


def _key(base: dict, head: dict) -> str:
    w = wanted(base)
    io = None
    if w["follow"]:
        from . import makehuman
        b = makehuman.body({k: v for k, v in (base.get("body") or {}).items() if k != "source"})
        io = round(2 * abs(float(b["face"]["landmarks"]["eye.L"][0])), 6)
    return json.dumps([w, io, head.get("seed"), head.get("spread", 1.0), bool(head.get("like")), head.get("toward", 1.0), head.get("dimorphism", DIMORPHISM)], sort_keys=True, default=float)


def follow(base: dict, head: dict) -> dict:
    """The head dict with the asked shape in it: "identity" (the seeded identity + the solved move; the head's own
    identity entries win), "warp" (the rest of the move), "scale" (with follow_body, unless given). Cached."""
    key = _key(base, head)
    if key not in _CACHE:
        from . import base as basemod
        g = _gnm()
        want = wanted(base)
        shaped = want["follow"] or bool((head.get("like") or {}))
        d = _feature_move(want["features"]) if want["features"] else np.zeros((len(g["L0"]), 3))
        w = _weights()
        c0 = basemod._gnm_coeffs(g["names"], None, head.get("seed"), head.get("spread", 1.0))[g["comps"]]
        Q = _body_axes()
        c0 = c0 - Q @ (Q.T @ c0) * min(want["amount"], 1.0)  # the seed without its own sex / age / weight
        L = g["L0"] + np.tensordot(c0, g["LB"], 1)
        J = g["J0"] + np.tensordot(c0, g["JB"], 1)
        io_g = float(abs(J[0][0] - J[1][0]))
        # the points relative to the eye midpoint move by d x interocular; the eye centres stay where they are
        dc = _solve(d, c0, io_g, w)
        c = np.clip(c0 + dc, -CLIP, CLIP)
        Lf = g["L0"] + np.tensordot(c, g["LB"], 1)
        Jf = g["J0"] + np.tensordot(c, g["JB"], 1)
        io_f = float(abs(Jf[0][0] - Jf[1][0]))
        got = ((Lf - Jf.mean(0)) / io_f - (L - J.mean(0)) / io_g)
        # the rest as a warp: residual moves (m, GNM's frame) at the fitted points, lids and lips by their trust
        trust = np.r_[W_LM, np.ones(len(w) - 68)]
        res = (d - got) * io_f * trust[:, None]
        sg = WARP_SIGMA * io_f
        D2 = ((Lf[:, None, :] - Lf[None, :, :]) ** 2).sum(-1)
        K = np.exp(-D2 / (2 * sg * sg))
        coef = np.linalg.solve(K + WARP_RIDGE * np.eye(len(Lf)), res)
        moved = (K @ coef) / io_f
        after = got + moved
        # the warp's largest local stretch: the distance change between points ~a centimetre apart (nearer pairs, a
        # landmark and a dense point 1 mm apart, measure nothing)
        nb = np.argsort(np.where(D2 < (0.15 * io_f) ** 2, np.inf, D2), 1)[:, :3]
        Lw = Lf + moved * io_f
        l0 = np.linalg.norm(Lf[:, None, :] - Lf[nb], axis=-1)
        l1 = np.linalg.norm(Lw[:, None, :] - Lw[nb], axis=-1)
        rms = lambda e: float(np.sqrt((e ** 2).sum(1).mean()))
        asked = rms(d)
        out = {"identity": {g["names"][i]: round(float(v), 4) for i, v in zip(g["comps"], c)},
               "warp": {"at": np.round(Lf, 6).tolist(), "coef": np.round(coef, 7).tolist(), "sigma": round(sg, 6)},
               "report": {"asked_io": round(asked, 4),
                          "reached_identity": round(1 - rms(got - d) / max(asked, 1e-9), 3) if asked else 1.0,
                          "reached": round(1 - rms(after - d) / max(asked, 1e-9), 3) if asked else 1.0,
                          "stretch_max": round(float(np.abs(l1 / np.maximum(l0, 1e-9) - 1).max()), 3),
                          "components_max": round(float(np.abs(c).max()), 2)}}
        if shaped:  # the age / sex / weight itself: MakeHuman's head of that description, as a field on the vertices
            out["field"] = {"age": want["age"], "sex": want["sex"], "weight": want["weight"], "amount": round(want["amount"], 4),
                            "toward": round(min(want["amount"], 1.0) * float(head.get("toward", 1.0)), 4),
                            "dimorphism": round(float(head.get("dimorphism", DIMORPHISM)) * want["amount"], 4)}
            fv = field_vertices(out["field"])
            out["report"]["field_io"] = round(float(np.sqrt((fv[np.asarray(fields()["valid"])] ** 2).sum(1).mean())), 4)
        if want["follow"]:
            out["scale"] = round(json.loads(key)[1] / io_f, 5)
        _CACHE[key] = out
    f = _CACHE[key]
    out = dict(head)
    out["identity"] = {**f["identity"], **(head.get("identity") or {})}
    if "scale" in f:
        out.setdefault("scale", f["scale"])
    out["plane_follows_chin"] = True
    out["warp"] = f["warp"]
    if "field" in f:
        out["field"] = f["field"]
    return out


def solved_points(h: dict) -> np.ndarray:
    """The fitted points (68 landmarks, cranium, dense; interoculars round the eye midpoint) of a head dict as
    `follow` returns it: identity, then the field, then the warp."""
    g = _gnm()
    c = np.array([h["identity"][g["names"][i]] for i in g["comps"]])
    L = g["L0"] + np.tensordot(c, g["LB"], 1)
    J = g["J0"] + np.tensordot(c, g["JB"], 1)
    io = float(abs(J[0][0] - J[1][0]))
    if h.get("field"):
        F = field_vertices(h["field"])
        L = L + io * np.array([sum(float(w) * F[int(v)] for v, w in r) for r in g["rows"]])
    wp = h.get("warp")
    if wp:
        P, C = np.asarray(wp["at"]), np.asarray(wp["coef"])
        L = L + np.exp(-((L[:, None] - P[None]) ** 2).sum(-1) / (2 * wp["sigma"] ** 2)) @ C
    return (L - J.mean(0)) / io


def report(base: dict) -> dict:
    """How far the head went: the move asked (rms, interoculars), the share of it the identity components made and
    the share after the warp, and the warp's largest local stretch."""
    head = base.get("head") or {}
    if not applies(base):
        return {}
    follow(base, head)
    return _CACHE[_key(base, head)]["report"]
