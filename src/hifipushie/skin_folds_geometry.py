"""The folds as geometry: the profile, tissue kept and moved, keep lines, `prims`, expression folds, `build`, `reference`. Part of the skin's folds (skin_folds.py has the overview)."""
from __future__ import annotations

import hashlib

import numpy as np

from . import skin_folds
from .skin_folds import geometry_key, options
from .skin_folds_map import fold_map, paths
from .skin_folds_surface import field_surface

# ---------------------------------------------------------------- the folds as geometry
def profile(t: np.ndarray, pr: dict, j: np.ndarray) -> np.ndarray:
    """The skin's move along its normal (m, + = out) at signed distance t (m) across a fold's line (+ = its plus
    side), per sample j's parameters: the groove (G deep, sg wide), the roll (O high, peaking r0 out, so wide,
    rising from the line over sh), the platform on the minus side (Pl in, over ph)."""
    G, sg = pr["G"][j], pr["sg"][j]
    # (a fold with a roll is a STEP: steep under the roll, a long gentle wall on the other side; symmetric it read
    # as a channel cut with a gouge)
    out = -G * np.exp(-0.5 * (t / np.where(t < 0, sg * pr["lee"], sg)) ** 2)
    if pr["has_roll"]:
        tr = np.abs(t) if pr.get("sym") else t       # (sym: a roll on both sides: a chin's two lobes)
        ur = np.clip(tr / pr["sh"], 0, 1)
        out = out + pr["O"][j] * ur * ur * (3 - 2 * ur) * np.exp(-0.5 * ((tr - pr["r0"]) / pr["so"]) ** 2)
    if pr["has_plat"]:
        x = np.clip(-t / pr["ph"], 0, 1)
        out = out - pr["Pl"][j] * np.where(t < 0, np.sin(np.pi * x) ** 2, 0.0)
    if pr.get("has_over"):
        uo = np.clip(t / pr["osh"], 0, 1)
        out = out + pr["Ov"][j] * uo * uo * (3 - 2 * uo) * np.exp(-0.5 * (np.maximum(t - pr["or0"], 0.0) / pr["oso"]) ** 2)
    return out


def _keep_tree(pr: dict):
    from scipy.spatial import cKDTree
    k = pr["keep_key"]
    if k not in skin_folds._KEEP_TREES:
        if len(skin_folds._KEEP_TREES) > 8:
            skin_folds._KEEP_TREES.pop(next(iter(skin_folds._KEEP_TREES)))
        skin_folds._KEEP_TREES[k] = cKDTree(pr["keep"])
    return skin_folds._KEEP_TREES[k]


def mod_tissue(cur: np.ndarray, p: np.ndarray, pr: dict, chunk: int = 4096) -> np.ndarray:
    """sdf's modifier "tissue": the field moved by `profile` of the distance across the fold's line. Smooth along the
    line (a normalised Gaussian over the nearest samples, as sdf.mod_fold); it fades over the line's ends (`taper`),
    past `reach` along the normal, toward the keep-out lines (lid margins, lips: `keep`), and where it pushes the
    skin IN it stops BALL outside each eyeball (`balls`: centre + radius)."""
    P, Nn, U, T = pr["pts"], pr["nrm"], pr["up"], pr["along"]
    flat = p.reshape(-1, 3)
    c0 = cur.reshape(-1)
    out = c0.copy()
    K, R, sa, H = pr["k"], pr["radius"], pr["sa"], pr["reach"]
    kt = _keep_tree(pr) if len(pr["keep"]) else None
    for s_ in range(0, len(flat), chunk):
        q = flat[s_:s_ + chunk].astype(np.float64)
        dist, idx = pr["tree"].query(q, k=K, distance_upper_bound=R)
        idx = idx.reshape(len(q), K)
        ok = idx < len(P)
        hit = ok.any(1)
        if not hit.any():
            continue
        q, ok, idx = q[hit], ok[hit], idx[hit]
        j = np.where(ok, idx, 0)
        r = q[:, None, :] - P[j]
        h = (r * Nn[j]).sum(-1)
        t = (r * U[j]).sum(-1)
        a = (r * T[j]).sum(-1)
        w = np.where(ok, np.exp(-0.5 * (a / sa) ** 2), 0.0)
        ws = w.sum(1)
        d = (w * profile(t, pr, j)).sum(1) / np.maximum(ws, 1e-12)
        tap = (w * pr["taper"][j]).sum(1) / np.maximum(ws, 1e-12)
        fade = np.clip(ws / (0.3 * pr["wfull"]), 0, 1) * tap
        hn = (w * np.abs(h)).sum(1) / np.maximum(ws, 1e-12)
        x = np.clip((hn - H) / H, 0, 1)
        fade = fade * (1 - x * x * (3 - 2 * x))
        if kt is not None:
            kd = pr.get("keep_d", skin_folds.KEEP)
            x = np.clip((kt.query(q)[0] - kd[0]) / (kd[1] - kd[0]), 0, 1)
            fade = fade * x * x * (3 - 2 * x)
        c = c0[s_:s_ + chunk][hit]
        new = c - d * fade
        for b in pr["balls"]:           # pushed in: never onto the eyeball
            sd = np.linalg.norm(q - b[:3], axis=1) - b[3] - skin_folds.BALL
            near = (new > c) & (sd < 0.006)
            new = np.where(near, np.minimum(new, np.maximum(c, sd)), new)
        o = out[s_:s_ + chunk]
        o[hit] = new
    return out.reshape(cur.shape)


def keep_lines(J: dict) -> np.ndarray:
    """(n, 3) points along what the folds' displacement keeps off: the lid margins (the opening's landmarks, a closed
    line per eye) and the lips (the vermilion's borders, the seam, and the lips' bodies between them)."""
    def dense(P, closed=False):
        P = np.asarray(P, float)
        if closed:
            P = np.r_[P, P[:1]]
        n = np.maximum(np.ceil(np.linalg.norm(np.diff(P, axis=0), axis=1) / 0.0005).astype(int), 1)
        return np.concatenate([P[i] + np.linspace(0, 1, k, endpoint=False)[:, None] * (P[i + 1] - P[i]) for i, k in enumerate(n)] + [P[-1:]])
    out = []
    for sd in (".L", ".R"):
        ring = [f"lm_eye_inner{sd}", f"lm_lid_upper_in{sd}", f"lm_lid_upper{sd}", f"lm_lid_upper_out{sd}", f"lm_eye_outer{sd}",
                f"lm_lid_lower_out{sd}", f"lm_lid_lower{sd}", f"lm_lid_lower_in{sd}"]
        ring = [J[k] for k in ring if k in J]
        if len(ring) >= 4:
            out.append(dense(ring, closed=True))
    rows = {}
    for tag in ("verm_u", "verm_iu", "verm_il", "verm_l"):
        ks = sorted(k for k in J if k.startswith(tag) and k[len(tag):].isdigit())
        if len(ks) >= 3:
            rows[tag] = np.array([J[k] for k in ks])
    for tag, Q in rows.items():
        out.append(dense(Q))
    for a, b in (("verm_u", "verm_iu"), ("verm_il", "verm_l")):      # the lips' bodies
        if a in rows and b in rows and len(rows[a]) == len(rows[b]):
            for f in (0.33, 0.67):
                out.append(dense((1 - f) * rows[a] + f * rows[b]))
    return np.concatenate(out) if out else np.zeros((0, 3))


def prims(s: dict, stream: list) -> list:
    """The folds' modifiers for an expanded geometry spec (spec._compile; s["tissue"] = geometry_key(skin)): one per
    fold and side with an amount, on the skin's part. `stream`: that part's primitives without them (what the paths
    are seated on: the same field the paint map and the reader seat theirs on)."""
    from scipy.ndimage import gaussian_filter1d
    from scipy.spatial import cKDTree
    from .spec import Prim
    tis = s.get("tissue") or {}
    cfg = tis.get("folds") or {}
    J = {k: np.asarray(v["pos"], float) for k, v in s["joints"].items() if "pos" in v}
    if not cfg or "lm_jaw_1.L" not in J:
        return []
    part = tis.get("part", "body")
    S = field_surface(stream, J)
    keep = keep_lines(J)
    kkey = hashlib.sha1(np.ascontiguousarray(keep).tobytes()).hexdigest()
    balls = np.zeros((0, 4))
    if s.get("base"):
        from . import base_measures
        head = base_measures.head_of(s, s["base"])
        if head is not None and head.get("eyes") is not None:
            balls = np.array([[*np.asarray(c, float), float(head["eye_r"])] for c in head["eyes"]])
    layer = max([p.layer for p in stream if p.op != "intersect"] or [0])
    out = []
    for (name, sd), q in paths(None, part, J, cfg, S=S).items():
        if not (q["amount"] > 0).any():
            continue
        rl = skin_folds.RELIEF[name]
        # the samples: the stations (1 mm) refined to STEP, normals and across smoothed along the line
        n = int(round((len(q["P"]) - 1) * skin_folds.STATION / skin_folds.STEP)) + 1
        tt = np.linspace(0, 1, n)
        fine = lambda arr: np.stack([np.interp(tt, q["t"], arr[:, k_]) for k_ in range(arr.shape[1])], 1)  # noqa: E731
        P = gaussian_filter1d(fine(q["P"]), 1.5 if not skin_folds.FOLDS[name].get("smooth") else skin_folds.FOLDS[name]["smooth"] * 0.001 / skin_folds.STEP, axis=0, mode="nearest")
        Nn = gaussian_filter1d(fine(q["normal"]), 4.0, axis=0, mode="nearest")
        Nn /= np.linalg.norm(Nn, axis=1, keepdims=True)
        T = np.gradient(P, axis=0)
        T -= (T * Nn).sum(1, keepdims=True) * Nn
        T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-12)
        U = fine(q["across"])
        U -= (U * Nn).sum(1, keepdims=True) * Nn
        U -= (U * T).sum(1, keepdims=True) * T
        U /= np.maximum(np.linalg.norm(U, axis=1, keepdims=True), 1e-12)
        am = np.interp(tt, q["t"], q["amount"])
        on = np.flatnonzero(am > 0)
        e = np.clip(np.minimum(np.arange(n) - on[0], on[-1] - np.arange(n)) * skin_folds.STEP / skin_folds.END, 0, 1)
        am = am * e * e * e * (e * (6 * e - 15) + 10)       # (no visible start: cut ends read as knife marks)
        sp = float(np.median(np.linalg.norm(np.diff(P, axis=0), axis=1)))
        sa = 1.5 * sp
        G = am * rl["depth"] * q["depth"] * 0.001
        sg = np.full(n, 0.001 * q["width"] / 2.355)
        roll, plat = rl.get("roll"), rl.get("plat")
        # (the roll swells toward the fold's middle: a bag is a crescent, a cheek's pad fullest beside the nose's wing)
        er = np.clip(np.minimum(np.arange(n) - on[0], on[-1] - np.arange(n)) / max(0.3 * (on[-1] - on[0]), 1), 0, 1)
        O = am * er * er * (3 - 2 * er) * (roll[2] * q["roll"] * 0.001 if roll else 0.0)
        Pl = am * (plat[0] * 0.001 if plat else 0.0)
        hood = float(q.get("hood", 0.0))
        if hood:      # the roll fuller over the outer half (its skin hanging toward the lashes)
            u_ = np.clip((tt - 0.4) / 0.5, 0, 1)
            O = O * (1.0 + skin_folds.HOOD_ROLL * hood * u_ * u_ * (3 - 2 * u_))
        # THE EYEBALL AS A CONSTRAINT, not a stop: where the lid lies thin over the ball the groove takes what room
        # there is (85 % of the clearance) and the rest of its depth stands out as the fold's lip (`over`)
        over = rl.get("over")
        Ov = np.zeros(n)
        if len(balls):
            cl = np.min([np.linalg.norm(P - b[:3], axis=1) - b[3] for b in balls], 0) - skin_folds.BALL
            cl = gaussian_filter1d(np.maximum(cl, 0.0), 2.0 / (skin_folds.STEP * 1000), mode="nearest")
            Gc = np.minimum(G, 0.85 * cl)
            if over:
                Ov = (G - Gc) * (over[3] if len(over) > 3 else 1.0)
            G = Gc
        so = 0.001 * roll[1] if roll else 0.001
        reach = 0.001 * rl["reach"]
        Rr = float(max((0.001 * roll[0] + 3 * so) if roll else 0.0, 3.5 * float(sg.max()) * (2.2 if roll else 1.0), (0.001 * plat[1]) if plat else 0.0, 3 * sa,
                       0.001 * (over[0] + 3 * over[1]) if over else 0.0) + 0.001)
        params = {"pts": P, "nrm": Nn, "up": U, "along": T, "taper": np.ones(n), "sa": sa,
                  "wfull": float(np.sqrt(2 * np.pi) * sa / sp) * 0.98, "reach": reach, "G": G, "sg": sg, "O": O, "Pl": Pl,
                  "lee": 2.2 if (roll and not rl.get("sym")) else 1.0, "sym": bool(rl.get("sym")), "has_roll": bool(roll), "r0": 0.001 * roll[0] if roll else 0.0, "so": so, "sh": 0.001 * roll[3] if roll else 0.001,
                  "has_plat": bool(plat), "ph": 0.001 * plat[1] if plat else 0.001,
                  "has_over": bool(over) and bool((Ov > 0).any()), "Ov": Ov, "or0": 0.001 * over[0] if over else 0.0,
                  "oso": 0.001 * over[1] if over else 0.001, "osh": 0.001 * over[2] if over else 0.001,
                  "keep_d": tuple(k_ * (1.0 - skin_folds.HOOD_KEEP * min(hood, 1.0)) for k_ in skin_folds.KEEP),
                  "keep": keep, "keep_key": kkey, "balls": balls, "radius": float(np.hypot(Rr, 2 * reach)),
                  "k": int(min(n, 2 * (3.5 * sa) / sp + 6)), "tree": cKDTree(P)}
        lo, hi = P.min(0) - Rr - reach, P.max(0) + Rr + reach
        gm, om = float(am.max()) * rl["depth"] * q["depth"] * 0.001, float(am.max()) * (roll[2] * q["roll"] * 0.001 if roll else 0.0)
        lip = 1.0 + 0.61 * gm / float(sg.min()) + 0.61 * om / min(so, params["sh"]) + 1.5 * float(Ov.max()) / params["osh"]
        out.append(Prim(f"fold_{name}{sd}", "tissue", "modify", 0.0, layer, lo, hi, params, lip=lip, part=part))
    return out


def expression(spec: dict, parts: dict, log: list) -> dict:
    """The folds' share of each face shape, added to the export's morph targets in place (asset.export, after
    faceshapes_apply.apply; parts: {part: {"verts", "corner_vert", "shapes": {name: (delta, n0, n1)}}}). Per fold prim and
    vertex the fold's own displacement there is measured on the field (the part's field without that fold minus with
    it, along the fold-free normal); a shape with gain g adds (g - 1) x it. skin["fold_expressions"] = False turns it
    off. Returns {fold side: {shape: max mm}}."""
    from . import sdf
    from . import images_frame
    from .faceshapes import vertex_normals
    sk = spec.get("skin") or {}
    if geometry_key(sk) is None or sk.get("fold_expressions", True) is False:
        return {}
    part = sk.get("part", "body")
    out = {}
    for pn, p in parts.items():
        if pn.split("/")[-1].split("~")[0] != part or not p.get("shapes"):
            continue
        prims_all = images_frame.prims_on(spec, [part])
        folds = [q for q in prims_all if q.kind == "tissue"]
        if not folds:
            continue
        X = np.asarray(p["verts"], np.float64)
        T = p["corner_vert"].reshape(-1, 3)
        add = {}
        for fp in folds:
            name, sd = fp.name[len("fold_"):], ""
            if name.endswith((".L", ".R")):
                name, sd = name[:-2], name[-2:]
            gains = skin_folds.EXPRESSION.get(name)
            if not gains:
                continue
            near = np.flatnonzero(((X >= np.asarray(fp.lo) - 0.001) & (X <= np.asarray(fp.hi) + 0.001)).all(1))
            if not len(near):
                continue
            rest = [q for q in prims_all if q is not fp]
            f_wo, f_w = sdf.field_at(rest, X[near]), sdf.field_at(prims_all, X[near])
            base = [q for q in prims_all if q.kind != "tissue"]
            e = 0.0003
            g = np.stack([sdf.field_at(base, X[near] + e * ax) - sdf.field_at(base, X[near] - e * ax) for ax in np.eye(3)], 1)
            g /= np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-12)
            disp = (f_wo - f_w)[:, None] * g                       # the fold's own move of the skin there (m, world)
            for nm in p["shapes"]:
                side = ".L" if nm.endswith("Left") else ".R" if nm.endswith("Right") else ""
                stem = nm[:-4] if side == ".L" else nm[:-5] if side == ".R" else nm
                if stem not in gains or (sd and side and sd != side) or "_" in nm:
                    continue
                d = (gains[stem] - 1.0) * disp
                a = add.setdefault(nm, np.zeros_like(X))
                a[near] += d
                out.setdefault(name + sd, {})[nm] = round(1000 * float(np.linalg.norm(d, axis=1).max()), 3)
        for nm, a in add.items():
            d0, n0, _ = p["shapes"][nm]
            d1 = np.asarray(d0, np.float64) + a
            p["shapes"][nm] = (d1.astype(np.asarray(d0).dtype), n0, vertex_normals(X + d1, T))
    if out:
        log.append("folds under expression (skin_folds.EXPRESSION: each fold's gain per shape baked into that shape's morph target; max mm added): " +
                   "; ".join(f"{k}: " + ", ".join(f"{s} {v}" for s, v in sorted(d.items(), key=lambda kv: -kv[1])[:4]) for k, d in out.items()) +
                   ". The fold's normal map and painted line do NOT change with a shape (one texture): fading them needs a wrinkle-map blend in the engine")
    return out


def build(spec: dict, p: dict, J: dict, layer, ctx: dict) -> None:
    """The folds' layers (skin_features_build.build calls this after the wrinkles): groove, roll, shade."""
    cfg = options(p.get("folds"))
    if not cfg or not ctx.get("face") or "lm_jaw_1.L" not in J:
        return
    path, place, _ = fold_map(spec, p["part"], J, cfg)
    im = lambda ch: {"image": {"file": path, **place, "channel": ch}}  # noqa: E731
    base_r = ctx["base_r"]
    # (map values are amount x share / 1.5: the layers' strengths carry the 1.5 back)
    # (no "levels" on the image: a post-processed mask is measured per vertex, and a lid's 1 mm line came out as dots)
    # (a shade, not a stain: near neutral. At [0.66, 0.53, 0.5] with the first tints a tear trough under a flat frontal
    # light, where painted relief hardly shades, read as a brown smudge under Garrett's eye)
    layer("folds_shade", color=[0.74, 0.66, 0.64], mix="multiply", opacity=1.0, mask=[im("b")])
    if geometry_key(spec.get("skin") or {}) is not None:
        # the relief is in the surface itself (prims): the map carries colour only: the shade, and the crease's occlusion
        # (the map holds amount x share / 1.5: full strength at amount 1.5)
        layer("folds_crease", color=[0.5, 0.33, 0.27], mix="multiply", opacity=1.0, mask=[im("r")])
        return
    layer("folds_groove", height=-round(skin_folds.DEPTH * 1.5, 7), roughness=min(base_r + 0.08, 0.95), opacity=0.6, mask=[im("r")])
    layer("folds_roll", height=round(skin_folds.BULGE * 1.5, 7), mask=[im("g")])


def reference() -> str:
    return "\n".join(["FOLDS (skin.folds: {name: amount | {amount, width mm, depth, roll, L / R: {amount, shift [mm..], extent [t0, t1]}}}; "
                      "GEOMETRY (a groove + roll in the surface itself) + their tint; lid_fold also takes hood 0..1.5 (the roll hanging toward the lashes at the outer end); "
                      "skin_from_reference reads them off the references):"] +
                     [f"  {k:13s} {v['about']} (width {v['width']} mm, {skin_folds.RELIEF[k]['depth']} mm deep" + (f", a roll {skin_folds.RELIEF[k]['roll'][2]} mm high" if skin_folds.RELIEF[k].get("roll") else "") +
                      f"; readable from {v['res']} mm a pixel)" for k, v in skin_folds.FOLDS.items()])
