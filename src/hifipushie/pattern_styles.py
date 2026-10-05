"""Style operations for pattern_draft: the ones that make a garment's character (collars on the roll line, raglan and
kimono sleeves, hoods, pleats, cut-away necklines, darts joined into seams, closures). Registered into
pattern_draft.OPS. Same contract: named points, named edges kept, mating edges matched or their ease declared.

  shawl          a shawl collar cut on with the front: a roll line from the break point past the neck point, the
                 collar's neck seam the back neck's length beyond the shoulder, a centre-back collar seam, the outer
                 edge curved back to the break point; a roll fold. (Threads / Mueller & Sohn: drafted on the break line.)
  lapel          a notched lapel: the front edge extended, the lapel's point shaped, a roll line from the break point
                 to the neck; the separate collar is then `collar` with "stop" (it ends at the gorge).
  cut_away       cut a piece along a line and discard one side (a V neckline, a cut-away front, a cropped hem line).
  darts_to_seam  two darts of one piece joined through their tips into a panel seam: the dart legs become the seam.
  raglan         front and back cut from the neckline to the armhole; the shoulder parts joined to the sleeve cap
                 (an overarm dart where the shoulder seam was).
  kimono         the sleeve cut in one with the body: the shoulder line run on to the wrist, an underarm curve.
  hood           a two-piece hood from head measures, its neck edge the neckline's length.
  pleat          fullness folded away along a line that crosses the piece: the piece is spread by twice the depth,
                 the seams skip the underlay, two fold lines press it.
  buttons        button marks along a line of a paired piece, stitched left to right.
  neckline       the neckline redrawn on front and back together: widened along the shoulder by the same amount on
                 both (the shoulder seams stay equal), lowered at centre front / back, round, V or square.
"""
from __future__ import annotations

import copy
import json
import math

import numpy as np

from . import pattern, pattern_blocks as pb
from . import pattern_draft as pd
from .pattern_draft import DraftError, _flat, _insert, _point, _remap, _replace, _rot, edge_length


def _unit(v):
    v = np.asarray(v, float)
    return v / max(np.linalg.norm(v), 1e-12)


def _ring_from(pc: dict, pts: list) -> None:
    """Replace a piece's outline by [(name | None, xy)]: names not listed are dropped."""
    new = pb.make_piece(pc["name"], pts, pc.get("role"), pc.get("wrap") or {}, pc.get("sym", "pair"))
    pc["P"], pc["names"] = new["P"], new["names"]


def _walk(pc: dict, a: str, b: str, via: str | None = None) -> list:
    return pattern.arc_indices(pc, f"{a}>{via}>{b}" if via else f"{a}>{b}")


def _shoulder_dir(D: dict, piece: str) -> np.ndarray:
    """Unit vector along the front shoulder seam from the shoulder point toward the neck point (the seam may have
    been cut by a style line: taken from the draft's shoulder_front edge)."""
    P = np.concatenate(pd.edge_points(D, D["edges"]["shoulder_front"]))
    hps = D["pieces"][piece]["P"][D["pieces"][piece]["names"]["hps"]]
    far = P[int(np.argmax(np.linalg.norm(P - hps, axis=1)))]
    return _unit(hps - far)


def _avoiding(pc: dict, a: str, b: str, avoid: str) -> list:
    """Outline indices from a to b the way round that doesn't pass the point `avoid`."""
    n = len(pc["P"])
    ia, ib, iv = pc["names"][a], pc["names"][b], pc["names"][avoid]
    fwd = [(ia + k) % n for k in range((ib - ia) % n + 1)]
    return fwd if iv not in fwd else [(ia - k) % n for k in range((ia - ib) % n + 1)]


def _named(pc: dict, ix: list, skip: tuple = ()) -> list:
    """[(name | None, xy)] for outline indices, keeping the names that sit on them."""
    by = {}
    for k, v in pc["names"].items():
        if k not in skip and not k.startswith("_"):
            by.setdefault(v, k)
    return [(by.get(i), pc["P"][i].copy()) for i in ix]


def op_shawl(D: dict, piece: str = "front", break_y: float | None = None, stand: float = 0.02, height: float = 0.075,
             width: float = 0.07, roll_stand: float = 0.02, spring: float | None = None, **o) -> None:
    """spring: how much longer the collar's outer edge is than its neck seam round the back of the neck (m; default:
    what the fall needs to lie down over the stand onto the shoulders). The back collar is an arc, not a strip run
    straight on from the roll line: a straight one has no length to turn down and stands up round the neck."""
    pc = D["pieces"][piece]
    if "neck_back" not in D["edges"] or "hps" not in pc["names"]:
        raise DraftError("shawl: needs a bodice front with its neckline (do it before unfold)")
    hps = pc["P"][pc["names"]["hps"]]
    sdir = _shoulder_dir(D, piece)
    low = "cfHem" if "cfHem" in pc["names"] else "cfWaist"
    y_low = pc["P"][pc["names"][low], 1]
    yb = (D["meta"].get("waist_y", -0.45) + 0.06) if break_y is None else -abs(float(break_y))
    yb = max(yb, y_low + 0.03)
    B = np.array([-stand, yb])
    Rp = hps + roll_stand * sdir  # the roll line passes this far inside the neck point
    u = _unit(Rp - B)
    n = np.array([-u[1], u[0]])
    if n @ (Rp - hps) < 0:
        n = -n
    Lbn = edge_length(D, D["edges"]["neck_back"])
    # the back collar: an annular sector beyond the line through the neck point square to the roll line. Its neck
    # seam (the back neck's length) is an arc that leaves the neck point along the roll line's direction and bends
    # back toward the shoulder, so the outer edge is longer than the seam by `spring`
    alpha = float((Rp - hps) @ n)  # the roll line's distance from the neck seam (the stand at the back)
    r_neck = Lbn / (math.pi / 2)  # the back neck as a quarter circle
    if spring is None:
        spring = Lbn * max(height - 2 * alpha, 0.005) * 0.8 / r_neck
    rho = Lbn * height / max(float(spring), 1e-4)  # the seam arc's radius in the flat
    Phi = Lbn / rho
    C0 = hps - n * rho
    arc = lambda r, ph: C0 + r * (math.cos(ph) * n + math.sin(ph) * u)
    Dp = arc(rho, Phi)  # the collar's neck seam ends at centre back
    E = arc(rho + height, Phi)  # the centre-back collar seam, square to the neck seam there
    tE = -math.sin(Phi) * n + math.cos(Phi) * u
    ln = np.linalg.norm(E - B)
    Eh = arc(rho + height, 0.0)  # the outer edge where it crosses the neck point's line
    curve = np.r_[pb.bez(B, B + n * width * 1.6 + u * 0.30 * ln, Eh - u * 0.30 * np.linalg.norm(Eh - B), Eh, 16),
                  [arc(rho + height, ph) for ph in np.linspace(0, Phi, 7)[1:]]]
    mid = len(curve) // 2
    old = copy.deepcopy(pc)
    keep = _avoiding(pc, "hps", low, "cfNeck")  # hps .. shoulder .. hem .. the centre front's low point
    pts = _named(pc, keep, skip=("cfNeck",))
    pts += [("standHem", [-stand, y_low]), ("break", B)]
    pts += [(("lapelMid" if k == mid else None), q) for k, q in enumerate(curve[:-1])]
    pts += [("collarTop", E), ("collarCB", Dp)] + [(None, arc(rho, ph)) for ph in np.linspace(Phi, 0, 7)[1:-1]]
    extra = {k: v for k, v in pc.items() if k not in ("P", "names")}
    _ring_from(pc, pts)
    pc.update({k: v for k, v in extra.items() if k not in ("name",)})
    pc["lines"] = dict(pc.get("lines") or {})
    pc["lines"]["cf"] = np.array([[0.0, yb + 0.02], [0.0, y_low]])
    imap = {}
    for i, q in enumerate(old["P"]):
        j = np.where(np.linalg.norm(pc["P"] - q, axis=1) < 1e-9)[0]
        if len(j):
            imap[i] = [(piece, int(j[0]))]
    _remap(D, piece, old, imap, {piece: pc})
    D["edges"]["neck_front"] = []
    D["edges"]["centre_front"] = [f"{piece}:break>standHem"]
    D["edges"]["hem_front"] = list(D["edges"].get("hem_front") or []) + [f"{piece}:{low}>standHem"]
    D["edges"]["shawl_edge"] = [f"{piece}:break>lapelMid>collarTop"]
    D["edges"]["collar_cb"] = [f"{piece}:collarCB>collarTop"]
    D["seams"].append([f"{piece}:collarCB>hps", list(D["edges"]["neck_back"])])
    D.setdefault("pair_seams", []).append(f"{piece}:collarCB>collarTop")
    D["centre"][piece] = "open"
    roll_a = B
    roll_pts = [B.tolist()] + [arc(rho + alpha, ph).tolist() for ph in np.linspace(0, Phi, 7)]
    # the flap's side of the roll line, named by a mark just inside the lapel (the curve's middle may lie either
    # side of the hinge below)
    fl = roll_a + 0.3 * (Rp - roll_a) + n * 0.008
    half = math.degrees(math.asin(min(1.0, (girth_ := 2 * (D["meta"].get("neck_front", 0.0) + D["meta"].get("neck_back", Lbn)))
                                      / (2 * math.pi) / rho)))
    pc["marks"] = dict(pc.get("marks") or {})
    pc["marks"]["lapelFlap"] = fl
    D["folds"].append({"piece": piece, "line": roll_pts, "angle": 10, "kind": "roll",
                       "radius": float(o.get("roll_radius", 0.004)), "strength": 0.5, "flap": "lapelFlap", "name": "shawl roll"})
    # one cloth, two placements: the front on the torso, the collar (past the neck point) round the back of the
    # neck, its neck seam along the bottom, standing `roll_stand`, the fall turned down over it
    girth = girth_
    D.setdefault("hinges", []).append({
        "piece": piece, "name": "neckHinge", "part": "collar", "at": hps.tolist(), "dir": n.tolist(),
        "mid": (hps + n * height * 0.5).tolist(), "origin": Dp.tolist(), "x": tE.tolist(), "role": "collar_fall",
        "wrap": {"to": "neck", "edge": "collarCB", "flip": True, "fixed_above": True, "girth": float(girth), "out": float(o.get("collar_out", 0.006)),
                 "apart": 0.0015},
        # (a curved crease folds isometrically at one angle: the fall is the stand's cone reflected)
        # (and as ONE crease: a roll's rows round a curved line stretch the flap 70%)
        "fold": {"flap": "collarTop", "angle": round(2 * half, 1), "kind": "press", "radius": 0.0, "strength": 0.3}})
    D["meta"]["break"] = [float(B[0]), float(B[1])]
    D["log"].append(f"shawl collar on {piece}: break point {abs(yb) * 1000:.0f} mm below the neck point, roll line "
                    f"{pattern.length(np.asarray(roll_pts)) * 1000:.0f} mm, neck seam {Lbn * 1000:.0f} mm (= the back neck), outer edge "
                    f"{spring * 1000:.0f} mm longer round the back (spring), "
                    f"collar {height * 1000:.0f} mm at CB ({roll_stand * 1000:.0f} stand + {(height - roll_stand) * 1000:.0f} "
                    f"fall), front edge extended {stand * 1000:.0f} mm")


def op_lapel(D: dict, piece: str = "front", break_y: float | None = None, stand: float = 0.02, width: float = 0.08,
             rise: float = 0.02, roll_stand: float = 0.02, **o) -> None:
    """A notched lapel on the front: the centre front extended by `stand`, the lapel's point (the top corner of the
    extension) pushed out to `width` from the roll line and up by `rise`, a roll line from the break point to
    `roll_stand` inside the neck point. Then {"op": "collar", "type": "roll", "stop": gorge} drafts the collar."""
    pc = D["pieces"][piece]
    low = "cfHem" if "cfHem" in pc["names"] else "cfWaist"
    pd.op_extend(D, piece, f"cfNeck>{low}", stand, name="stand")
    pc = D["pieces"][piece]
    hps = pc["P"][pc["names"]["hps"]]
    sdir = _shoulder_dir(D, piece)
    yb = (D["meta"].get("waist_y", -0.45) + 0.06) if break_y is None else -abs(float(break_y))
    ib = _point(D, pc, {"edge": "stand.a>stand.b", "y": yb}, "break")
    B = pc["P"][pc["names"]["break"]].copy()
    Rp = hps + roll_stand * sdir
    u = _unit(Rp - B)
    n = np.array([-u[1], u[0]])
    if n @ (hps - Rp) > 0:
        n = -n  # away from the garment: the lapel's side
    top = pc["P"][pc["names"]["stand.a"]]
    t_along = float((top - B) @ u)
    P_new = B + u * t_along + n * width + np.array([0.0, rise])
    pc["P"][pc["names"]["stand.a"]] = P_new
    pc["names"]["lapelPoint"] = pc["names"]["stand.a"]
    # the edge from the break point to the lapel point: straight (inner points of the pushed edge go onto it)
    ix = pattern.arc_indices(pc, "break>lapelPoint")
    for k, i in enumerate(ix[1:-1], start=1):
        pc["P"][i] = B + (P_new - B) * k / (len(ix) - 1)
    if o.get("gorge") == "straight":
        # a tailored gorge: the front neck is ONE straight line from the neck point to the lapel's point; the collar
        # ends `notch` short of the point (the lapel's own top edge beyond it is the notch's lower side)
        if o.get("gorge_drop") is not None:  # the lapel point's height below the neck point, kept `width` off the roll
            yv = hps[1] - abs(float(o["gorge_drop"]))
            base = B + n * width
            P_new = base + u * ((yv - base[1]) / u[1])
            pc["P"][pc["names"]["lapelPoint"]] = P_new
            ix = pattern.arc_indices(pc, "break>lapelPoint")
            for k, i in enumerate(ix[1:-1], start=1):
                pc["P"][i] = B + (P_new - B) * k / (len(ix) - 1)
        notch = float(o.get("notch", 0.035))
        gdir = _unit(hps - P_new)
        C = P_new + gdir * notch
        ixn = _avoiding(pc, "hps", "cfNeck", "shoulder")
        for k, i in enumerate(ixn):
            pc["P"][i] = hps + (C - hps) * k / (len(ixn) - 1)
    D["edges"]["lapel_edge"] = [f"{piece}:break>lapelPoint"]
    D["edges"]["gorge"] = [f"{piece}:lapelPoint>cfNeck"]
    D["centre"][piece] = "open"
    D["folds"].append({"piece": piece, "line": [B.tolist(), (Rp + u * 0.02).tolist()], "angle": 15, "kind": "roll",
                       "radius": 0.006, "strength": 0.5, "flap": "lapelPoint", "name": "lapel roll"})
    D["meta"]["break"] = [float(B[0]), float(B[1])]
    D["log"].append(f"lapel on {piece}: front edge extended {stand * 1000:.0f} mm, break point {abs(yb) * 1000:.0f} mm "
                    f"below the neck point, lapel point {width * 1000:.0f} mm from the roll line; gorge "
                    f"{edge_length(D, D['edges']['gorge']) * 1000:.0f} mm (the collar stops there)")


def op_cut_away(D: dict, piece: str, keep: str, name: str | None = None, **o) -> None:
    """Cut `piece` along a line ("from", "to", "via" as style_line) and keep the side holding the point `keep`."""
    name = name or f"cut{pd._counter(D)}"
    centre = D["centre"].get(piece)
    pd.op_style_line(D, piece, name=name, names=[f"{piece}__a", f"{piece}__b"], **{k: v for k, v in o.items()
                                                                               if k in ("from", "to", "via", "curve")})
    a, b = D["pieces"][f"{piece}__a"], D["pieces"][f"{piece}__b"]
    kp, drop = (a, b) if keep in a["names"] else (b, a)
    if keep not in kp["names"]:
        raise DraftError(f"cut_away: neither side holds the point {keep!r}")
    kn, dn = kp["name"], drop["name"]
    kp["name"] = piece
    order = [piece if k == kn else k for k in D["pieces"] if k != dn]
    pcs = {piece if k == kn else k: v for k, v in D["pieces"].items() if k != dn}
    D["pieces"] = {k: pcs[k] for k in order}
    ren = lambda e: e.replace(kn + ":", piece + ":")
    seams = []
    for A, Bs in D["seams"]:
        key = json.dumps([A, Bs])
        fa = [ren(e) for e in _flat(A) if not e.startswith(dn + ":")]
        fb = [ren(e) for e in _flat(Bs) if not e.startswith(dn + ":")]
        if not fa or not fb:  # the cut's own seam, and seams of the part cut away
            continue
        ns = [fa[0] if len(fa) == 1 else fa, fb[0] if len(fb) == 1 else fb]
        if key in D["notes"]:
            D["notes"][json.dumps(ns)] = D["notes"].pop(key)
        seams.append(ns)
    D["seams"] = seams
    for k in list(D["edges"]):
        D["edges"][k] = [ren(e) for e in D["edges"][k] if not e.startswith(dn + ":")]
    sa, sb = D["lines"].pop(name)
    D["edges"][name] = [ren(sa if sa.startswith(kn + ":") else sb)]
    D["centre"].pop(kn, None)
    D["centre"].pop(dn, None)
    if centre is not None:
        D["centre"][piece] = centre
    D["log"].append(f"cut away on {piece}: the side with {keep} kept; the new edge is \"{name}\" "
                    f"({edge_length(D, D['edges'][name]) * 1000:.0f} mm)")


def op_darts_to_seam(D: dict, piece: str, darts: list, names: list | None = None, name: str | None = None, **o) -> None:
    """Join two darts of `piece` through their tips into a panel seam."""
    pc = D["pieces"][piece]
    name = name or f"panel{pd._counter(D)}"
    d1, d2 = darts
    for d in darts:
        if d not in pc.get("darts", {}):
            raise DraftError(f"{piece}: no dart {d!r} (has {', '.join(pc.get('darts', {})) or 'none'})")
    old = copy.deepcopy(pc)
    n = len(pc["P"])
    idx = lambda d: [pc["names"][k] for k in pc["darts"][d]]
    (a1, t1, b1), (a2, t2, b2) = idx(d1), idx(d2)
    step = lambda a, t: 1 if (a + 1) % n == t else -1
    # put both darts in ring order a -> tip -> b
    if step(a1, t1) < 0:
        a1, b1 = b1, a1
    if step(a2, t2) < 0:
        a2, b2 = b2, a2

    def run(start, end):
        out, k = [start], start
        while k != end:
            k = (k + 1) % n
            out.append(k)
        return out
    r1 = run(b1, a2)  # one side of both darts
    r2 = run(b2, a1)  # the other
    T1, T2 = pc["P"][t1].copy(), pc["P"][t2].copy()
    halves = []
    for r, tips, tn in ((r1, [T2, T1], ["t2", "t1"]), (r2, [T1, T2], ["t1", "t2"])):
        P = np.r_[pc["P"][r], tips]
        h = {"P": P, "names": {}, "marks": {}, "lines": {}, "grain": pc["grain"], "role": pc.get("role"),
             "wrap": dict(pc.get("wrap") or {}), "sym": pc.get("sym", "pair"), "darts": {}}
        pos = {w: k for k, w in enumerate(r)}
        for k_, w in pc["names"].items():
            if w in pos and k_ not in pc["darts"][d1] and k_ not in pc["darts"][d2]:
                h["names"][k_] = pos[w]
        h["names"][f"{name}.start"], h["names"][f"{name}.end"] = 0, len(r) - 1
        h["names"][f"{name}.{tn[0]}"], h["names"][f"{name}.{tn[1]}"] = len(r), len(r) + 1
        from .cloth import _inside
        for k_, v in pc["marks"].items():
            if _inside(P, np.asarray(v, float)[None])[0]:
                h["marks"][k_] = v
        for k_, Ln in pc["lines"].items():
            if _inside(P, np.asarray(Ln, float).mean(0)[None])[0]:
                h["lines"][k_] = Ln
        for dn_, pts_ in pc["darts"].items():
            if dn_ not in darts and all(p in h["names"] for p in pts_):
                h["darts"][dn_] = pts_
        halves.append((h, pos))
    cx = [float(np.abs(h["P"][:, 0]).min()) for h, _ in halves]
    order = [0, 1] if cx[0] <= cx[1] else [1, 0]
    names = names or [f"{piece}_centre", f"{piece}_side"]
    new, imap = {}, {}
    for nm, k in zip(names, order):
        h, pos = halves[k]
        h["name"] = nm
        new[nm] = h
        for w, j in pos.items():
            imap.setdefault(w, []).append((nm, j))
    D["seams"] = [s for s in D["seams"] if not (all(isinstance(x, str) for x in s) and all(
        x.startswith(piece + ":") and any(p in x for p in pc["darts"][d1] + pc["darts"][d2]) for x in s))]
    _replace(D, piece, new)
    _remap(D, piece, old, imap, new)
    na, nb = names[order[0]], names[order[1]]  # (halves[0] = the b1..a2 side, halves[1] = b2..a1)
    s0 = f"{halves[0][0]['name']}:{name}.start>{name}.t1>{name}.end"  # b1 -> t1 -> t2 -> a2
    s1 = f"{halves[1][0]['name']}:{name}.end>{name}.t1>{name}.start"  # a1 -> t1 -> t2 -> b2
    D["seams"].append([s0, s1])
    D["lines"][name] = (s0, s1)
    D["edges"][name] = [s0]
    D["log"].append(f"darts {d1} + {d2} of {piece} joined into the seam {name}: {na} + {nb}; edges "
                    f"{edge_length(D, s0) * 1000:.1f} / {edge_length(D, s1) * 1000:.1f} mm (the dart legs)")


def op_raglan(D: dict, neck: float = 0.035, arm: float = 0.35, **o) -> None:
    """Raglan: front and back are cut from the neckline (`neck` m from the neck point) to the armhole (`arm` of the
    way up it from the underarm); the cut-off shoulder parts join the sleeve at the cap."""
    if "sleeve" not in D["pieces"]:
        raise DraftError("raglan: draft the sleeve first (op sleeve), then raglan")
    e = D["meta"]["sleeve"].get("cap_ease", 0.0)
    parts = {}
    for which, nk, ak in (("front", "neck_front", "armhole_front"), ("back", "neck_back", "armhole_back")):
        pc = D["pieces"][which]
        cn = "cfNeck" if which == "front" else "cbNeck"
        ln_ = pb.edge_length(pc, f"hps>{cn}")
        pd.op_style_line(D, which, name=f"rg{which[0]}", **{"from": {"edge": f"hps>{cn}", "dist": min(neck, 0.8 * ln_)},
                                                             "to": {"edge": "armhole>armholePitch", "t": arm * 2},
                                                             "names": [which, f"{which}_yoke"], "curve": False})
        parts[which] = D["pieces"].pop(f"{which}_yoke")
    sl = D["pieces"]["sleeve"]
    cap_top = sl["P"][sl["names"]["capTop"]].copy()

    def cap_point(side: str, s: float, nm: str) -> np.ndarray:
        i = _point(D, sl, {"edge": f"capTop>underarm{side}", "dist": s}, nm)
        return sl["P"][sl["names"][nm]].copy()
    placed = {}
    for which, side, mirror in (("front", "F", True), ("back", "B", False)):
        y = parts[which]
        nm_ = f"rg{which[0]}"
        ix = pattern.arc_indices(y, f"{nm_}.b>{nm_}.a>hps>shoulder")  # raglan line, neck, shoulder seam
        arm_len = pb.edge_length(y, f"shoulder>{nm_}.b")
        P = y["P"][ix].copy()
        A0, S0 = P[0].copy(), P[-1].copy()
        if mirror:
            P[:, 0] *= -1
            A0[0] *= -1
            S0[0] *= -1
        Q = cap_point(side, arm_len * (1 + e), f"q{side}")
        ang = math.atan2(*(Q - cap_top)[::-1]) - math.atan2(*(A0 - S0)[::-1])
        P = _rot(P, S0, ang) + (cap_top - S0)
        # one cloth, two placements: the shoulder part stays on the TORSO, in the coordinates it was cut from the
        # body in (beside the body's raglan line), the sleeve below it goes round the arm. Laid along the arm with
        # the sleeve it started 17 cm and 60 deg from the body's cut and crumpled at the shoulder in the sim
        ca, sa = math.cos(-ang), math.sin(-ang)
        Minv = np.array([[ca, -sa], [sa, ca]])
        if mirror:
            Minv = np.diag([-1.0, 1.0]) @ Minv
        S_orig = y["P"][y["names"]["shoulder"]].copy()
        out_dir = _unit(y["P"][ix].mean(0) - D["pieces"][which]["P"].mean(0))  # away from the body piece
        D.setdefault("hinges", []).append({
            "piece": "sleeve", "name": f"raglanHinge{side}", "part": f"{which}_shoulder", "at": Q.tolist(),
            "dir": _unit(cap_top - Q).tolist(), "mid": (0.5 * (Q + cap_top)).tolist(), "far": P[len(P) // 2].tolist(),
            "origin": cap_top.tolist(), "x": [1.0, 0.0], "matrix": Minv.tolist(), "offset": S_orig.tolist(),
            "role": which, "wrap": {"to": "torso", "side": which, "shift": (0.002 * out_dir).round(5).tolist()}})
        names = [None] * len(ix)
        names[0] = f"r{side}"
        names[ix.index(y["names"][f"{nm_}.a"])] = f"n{side}"
        names[ix.index(y["names"]["hps"])] = f"hps{side}"
        placed[side] = (P, names, arm_len)
    # the new sleeve outline: back underarm, up the back cap to qB, the back shoulder part, capTop, the front one, qF,
    # down the front cap, and round the rest of the sleeve
    up_b = pattern.arc_indices(sl, "underarmB>qB")
    down_f = pattern.arc_indices(sl, "qF>underarmF")
    rest = pattern.arc_indices(sl, "underarmF>wristF>underarmB") if "wristF" in sl["names"] else []
    pts = _named(sl, up_b)
    Pb, nb_, _ = placed["B"]
    pts += [(nb_[k], Pb[k]) for k in range(len(Pb) - 1)]
    pts += [("capTop", cap_top)]
    Pf, nf_, _ = placed["F"]
    pts += [(nf_[k], Pf[k]) for k in range(len(Pf) - 2, -1, -1)]
    pts += _named(sl, down_f)
    pts += _named(sl, rest[1:-1])
    lines, marks = sl.get("lines"), sl.get("marks")
    _ring_from(sl, pts)
    sl["lines"], sl["marks"] = lines or {}, marks or {}
    # seams: drop the cap, the shoulder and the two style seams; add the raglan seams, the lower cap and the overarm
    def has(s, frag):
        return any(frag in e for side in s for e in _flat(side))
    D["seams"] = [s for s in D["seams"] if not (has(s, "_yoke:") or has(s, "sleeve:underarmF>capTop") or has(s, ":rgf.") or has(s, ":rgb."))]
    for k in list(D["notes"]):
        if "_yoke:" in k or "sleeve:underarmF>capTop" in k:
            D["notes"].pop(k)
    for which, side in (("front", "F"), ("back", "B")):
        nm_ = f"rg{which[0]}"
        body_line = next(x for x in D["lines"][nm_] if x.startswith(which + ":"))
        D["seams"].append([f"sleeve:n{side}>r{side}", body_line])
        low = [x for x in D["edges"][f"armhole_{which}"] if x.startswith(which + ":")]
        cap_low = f"sleeve:underarm{side}>q{side}"
        s_ = [cap_low, low[0] if len(low) == 1 else low]
        D["seams"].append(s_)
        D["notes"][json.dumps(s_)] = {"ease": [max(e - 0.012, -0.012), e + 0.012], "why": f"cap ease {e * 100:.1f}% under the raglan"}
        D["edges"][f"neck_{which}"] = [x for x in D["edges"][f"neck_{which}"] if x.startswith(which + ":")] + \
            [f"sleeve:hps{side}>n{side}" if which == "front" else f"sleeve:n{side}>hps{side}"]
        D["edges"].pop(f"armhole_{which}", None)
        D["edges"].pop(f"shoulder_{which}", None)
        D["lines"].pop(nm_, None)
        D["centre"].pop(f"{which}_yoke", None)
    D["edges"]["neck_back"] = [x for x in D["edges"]["neck_back"] if not x.startswith("sleeve:")] + ["sleeve:nB>hpsB"]
    D["seams"].append(["sleeve:hpsB>capTop", "sleeve:hpsF>capTop"])
    D["edges"]["cap"] = []
    D["meta"]["raglan"] = True
    D["log"].append(f"raglan: front and back cut {neck * 1000:.0f} mm from the neck point to {arm * 100:.0f}% up the "
                    f"armhole; the shoulder parts ({placed['F'][2] * 1000:.0f} / {placed['B'][2] * 1000:.0f} mm of armhole) "
                    "joined to the sleeve cap, the shoulder seam now an overarm dart")


def op_kimono(D: dict, length: float | None = None, angle: float = 25.0, wrist: float | None = None, drop: float = 0.06,
              **o) -> None:
    """The sleeve cut in one with the body (kimono / dolman): on front and back alike, the shoulder line runs on to
    the wrist at `angle` deg below horizontal, the underarm curves from the wrist to the side seam `drop` under the
    armhole. Pattern only for now: placement wraps body pieces round the torso, not round an arm."""
    m = D["meta"]["measurements"]
    Ls = float(length) if length else float(m["shoulderToWrist"]) / 1000.0
    hw = (float(wrist) if wrist else float(m["wrist"]) / 1000.0 * 1.6) / 2
    for which in ("front", "back"):
        pc = D["pieces"][which]
        old = copy.deepcopy(pc)
        sh = pc["P"][pc["names"]["shoulder"]].copy()
        ah = pc["P"][pc["names"]["armhole"]].copy()
        d = np.array([math.cos(math.radians(angle)), -math.sin(math.radians(angle))])
        nrm = np.array([d[1], -d[0]])  # down from the overarm line
        w1 = sh + d * Ls
        w2 = w1 + nrm * 2 * hw
        g = ah + np.array([0.0, -drop])
        low = D["meta"]["low"]
        cn = "cfNeck" if which == "front" else "cbNeck"
        a = pattern.arc_indices(pc, f"{cn}>hps>shoulder")
        b = pattern.arc_indices(pc, f"armhole>{low}")
        cl = ("cfHem" if which == "front" else "cbHem") if low == "hem" else ("cfWaist" if which == "front" else "cbWaist")
        c = pattern.arc_indices(pc, f"{low}>{cl}")
        under = pb.bez(w2, w2 - d * 0.5 * Ls, g + np.array([0.10, 0.02]), g, 14)
        pts = _named(pc, a) + [("wristTop", w1), ("wristBottom", w2)] + [(None, q) for q in under[:-1]] + [("armhole", g)]
        pts += _named(pc, [i for i in b[1:] if pc["P"][i, 1] < g[1] - 1e-6], skip=("armhole",)) + _named(pc, c[1:])
        keepl, keepm, darts = pc.get("lines"), pc.get("marks"), pc.get("darts")
        _ring_from(pc, pts)
        pc["lines"], pc["marks"], pc["darts"] = keepl or {}, keepm or {}, darts or {}
        # one cloth, two placements: the body on the torso, the sleeve (past the line from the underarm to the
        # shoulder point) round the arm, its overarm seam along the top of the arm (the front half goes round the
        # front, the back half round the back)
        ex = np.array([-d[1], d[0]])
        D.setdefault("hinges", []).append({
            "piece": which, "name": "sleeveHinge", "part": "sleeve", "at": g.tolist(), "dir": _unit(sh - g).tolist(),
            "mid": (0.5 * (g + sh)).tolist(), "far": w1.tolist(), "origin": sh.tolist(), "x": ex.tolist(), "role": "sleeve",
            "wrap": {"to": "arm.L", "front": -1 if which == "front" else 1, "cx": 0.0}})
    D["seams"] = [s for s in D["seams"] if not any(x in e for side in s for e in _flat(side)
                                                   for x in (":shoulder>hps", ":armhole>"))]
    low = D["meta"]["low"]
    D["seams"] += [["front:hps>shoulder>wristTop", "back:hps>shoulder>wristTop"],
                   [f"front:wristBottom>armhole>{low}", f"back:wristBottom>armhole>{low}"]]
    for k in ("armhole_front", "armhole_back"):
        D["edges"].pop(k, None)
    D["edges"]["sleeve_hem"] = ["front:wristTop>wristBottom", "back:wristTop>wristBottom"]
    D["meta"]["kimono"] = True
    D["log"].append(f"kimono sleeve: overarm {Ls * 1000:.0f} mm at {angle:.0f} deg, wrist {2 * hw * 1000:.0f} mm, underarm "
                    f"{drop * 1000:.0f} mm under the armhole; front and back alike; placed in two parts each (body on the "
                    "torso, sleeve round the arm)")


def op_hood(D: dict, height: float | None = None, depth: float | None = None, name: str = "hood", **o) -> None:
    """A two-piece hood: each side's neck edge is the half neckline's length; height from the neck base over the
    crown, depth from the face edge to the back of the head (from the head girth when measured, else from height)."""
    m = D["meta"]["measurements"]
    Ln = edge_length(D, D["edges"]["neck_back"]) + edge_length(D, D["edges"]["neck_front"])
    head = float(m.get("head", 0.32 * float(m.get("height", 1750)))) / 1000.0
    H = float(height) if height else 0.52 * head + 0.05  # neck base to crown over the head + ease
    Dp = float(depth) if depth else max(0.44 * head, Ln * 0.95)
    dip = 0.035
    F = np.array([math.sqrt(max(Ln ** 2 - dip ** 2, 1e-9)), -dip])  # the neck edge: Ln long, dipping to the front
    pts = [("neckBack", [0.0, 0.0])] + [(None, [F[0] * t, -dip * t]) for t in (0.25,)] + [("neckMid", F * 0.5)]
    pts += [(None, F * 0.75), ("neckFront", F), ("faceTop", [max(F[0], Dp) + 0.01, H * 0.96])]
    pts += [(None, q) for q in pb.bez([max(F[0], Dp) + 0.01, H * 0.96], [Dp * 0.75, H * 1.03], [Dp * 0.35, H * 1.02], [0.06, H * 0.9])[:-1]]
    pts += [("crown", [0.06, H * 0.9])]
    pts += [(None, q) for q in pb.bez([0.06, H * 0.9], [-0.035, H * 0.72], [-0.03, H * 0.25], [0.0, 0.0])[:-1]]
    pc = pb.make_piece(name, pts, "hood", {"to": "head", "apart": 0.0015}, "pair")
    # the neck edge as drawn is a little under Ln (straight): scale x so it is exact
    k = Ln / pb.edge_length(pc, "neckBack>neckMid>neckFront")
    pc["P"][:, 0] *= k
    # (the centre seam bows past x = 0 over the back of the head: each side starts that far off the middle, or the
    # two sides start through each other)
    pc["wrap"]["apart"] = round(float(-pc["P"][:, 0].min()) + 0.002, 4)
    D["pieces"][name] = pc
    nb, nf = D["edges"]["neck_back"], D["edges"]["neck_front"]
    D["seams"].append([f"{name}:neckBack>neckMid>neckFront", list(nb) + list(nf)])
    D.setdefault("pair_seams", []).append(f"{name}:faceTop>crown>neckBack")
    D["edges"]["hood_face"] = [f"{name}:neckFront>faceTop"]
    D["log"].append(f"hood: neck edge {Ln * 1000:.0f} mm (the half neckline), {H * 1000:.0f} mm high, {Dp * 1000:.0f} mm deep "
                    f"(head girth {'measured' if 'head' in m else 'estimated'} {head * 1000:.0f} mm); two sides, a centre seam "
                    "placed round the head")


def op_pleat(D: dict, piece: str, depth: float = 0.02, name: str | None = None, **o) -> None:
    """A pleat along a line that crosses the piece ("from" -> "to", outline points): the piece is spread by twice the
    depth across the line; the seams at both ends skip the underlay (it is folded away); two fold lines press it
    (the outer fold on the line, the inner one a depth beyond)."""
    pc = D["pieces"][piece]
    name = name or f"pleat{pd._counter(D)}"
    old = copy.deepcopy(pc)
    work = copy.deepcopy(pc)
    _point(D, work, o["from"], f"{name}.a")
    _point(D, work, o["to"], f"{name}.b")
    ia, ib = work["names"][f"{name}.a"], work["names"][f"{name}.b"]
    n = len(work["P"])
    fwd = [(ia + k) % n for k in range((ib - ia) % n + 1)]
    bwd = [(ib + k) % n for k in range((ia - ib) % n + 1)]
    A, B = work["P"][ia], work["P"][ib]
    cen = lambda r: int(np.sum(np.abs(work["P"][r, 0]) < 1e-6))
    stay, move = (fwd, bwd) if cen(fwd) >= cen(bwd) else (bwd, fwd)
    d = _unit(B - A)
    nrm = np.array([-d[1], d[0]])
    if nrm @ (work["P"][move].mean(0) - A) < 0:
        nrm = -nrm
    v = nrm * 2 * depth
    P = np.r_[work["P"][stay], work["P"][move] + v]
    names = {}
    pos_s = {w: k for k, w in enumerate(stay)}
    pos_m = {w: len(stay) + k for k, w in enumerate(move)}
    for k_, w in work["names"].items():
        if k_ in (f"{name}.a", f"{name}.b"):
            continue
        if w in pos_s and w not in (ia, ib):
            names[k_] = pos_s[w]
        elif w in pos_m:
            names[k_] = pos_m[w]
        else:
            names[k_] = pos_s[w]
    names[f"{name}.a"], names[f"{name}.b"] = pos_s[ia], pos_s[ib]
    names[f"{name}.a2"], names[f"{name}.b2"] = pos_m[ia], pos_m[ib]
    new = dict(work, P=P, names=names)
    from .cloth import _inside
    poly_m = work["P"][move]
    new["marks"] = {k_: (np.asarray(q) + v if _inside(poly_m, np.asarray(q, float)[None])[0] else q)
                    for k_, q in work["marks"].items()}
    new["lines"] = {k_: (np.asarray(Ln) + v if _inside(poly_m, np.asarray(Ln, float).mean(0)[None])[0] else Ln)
                    for k_, Ln in work["lines"].items()}
    imap = {}
    for w in range(n):
        if w in (ia, ib):
            imap[w] = [(piece, pos_s[w]), (piece, pos_m[w])]
        elif w in pos_s:
            imap[w] = [(piece, pos_s[w])]
        else:
            imap[w] = [(piece, pos_m[w])]
    new["underlays"] = list(work.get("underlays") or []) + [
        {"y": [float(min(A[1], B[1])), float(max(A[1], B[1]))], "width": float(2 * depth)}]  # (not girth: cloth.sizing)
    D["pieces"][piece] = new
    _remap(D, piece, work, imap, {piece: new})
    D["folds"].append({"piece": piece, "line": [A.tolist(), B.tolist()], "angle": 0, "kind": "press", "name": f"{name} outer",
                       "in_wrap": True})
    D["folds"].append({"piece": piece, "line": [(A + v / 2).tolist(), (B + v / 2).tolist()], "angle": 360, "kind": "press",
                       "name": f"{name} inner", "in_wrap": True})
    # laid closed by the wrap (cloth.place): the folds above give the mesh its rows and the solver its creases
    new["wrap"] = dict(new.get("wrap") or {})
    new["wrap"]["pleats"] = list(new["wrap"].get("pleats") or []) + [
        {"a": A.tolist(), "b": B.tolist(), "depth": float(depth), "sign": 1.0 if nrm[0] >= 0 else -1.0}]
    D["log"].append(f"pleat {name} on {piece}: {depth * 1000:.0f} mm deep ({2 * depth * 1000:.0f} mm of cloth folded away) "
                    f"along {np.linalg.norm(B - A) * 1000:.0f} mm; the seams at its ends skip the underlay")


def op_buttons(D: dict, piece: str, n: int = 1, top: float | None = None, spacing: float = 0.09, x: float = 0.0,
               **o) -> None:
    """n button marks down the line x (the centre front) from `top` (m below the neck point; default the break
    point), stitched left front to right front when the piece is a pair."""
    pc = D["pieces"][piece]
    y0 = -abs(float(top)) if top is not None else float(D["meta"].get("break", [0, -0.3])[1]) - 0.015
    for k in range(int(n)):
        nm = f"button{k + 1}"
        pc["marks"][nm] = np.array([float(x), y0 - k * spacing])
        D.setdefault("pair_stitches", []).append(f"{piece}:{nm}")
    D["log"].append(f"buttons on {piece}: {n} at x {x * 1000:.0f} mm from y {y0 * 1000:.0f} mm, {spacing * 1000:.0f} mm apart")


def op_stitch(D: dict, a: str, b: str, **o) -> None:
    """A point stitch between two points or marks ("piece:name"): a tie, a tack, a button on a whole piece."""
    D["stitches"].append([a, b])
    D["log"].append(f"stitch {a} to {b}")


def op_neckline(D: dict, widen: float = 0.0, front: float = 0.0, back: float = 0.0, shape: str = "round",
                shape_back: str = "round", **o) -> None:
    """Redraw the neckline: the neck point moved `widen` along the shoulder on front AND back (so the shoulder seams
    still match), the centre front lowered by `front`, the centre back by `back`; "round" (leaves the centre square to
    it and the shoulder square to the seam), "v" (straight) or "square". Do it before a collar, facing or cut."""
    moved = {}
    for edge, low, shp in (("neck_front", front, shape), ("neck_back", back, shape_back)):
        chain = D["edges"].get(edge) or []
        if len(chain) != 1:
            raise DraftError(f"neckline: {edge} is cut into {len(chain)} parts; redraw the neckline before style lines")
        pn, arc = chain[0].split(":", 1)
        pc = D["pieces"][pn]
        cname = "cfNeck" if "cfNeck" in pc["names"] else "cbNeck"
        ix = pattern.arc_indices(pc, arc)
        if pc["names"][cname] != ix[0]:
            ix = ix[::-1]
        if pc["names"][cname] != ix[0] or pc["names"]["hps"] != ix[-1]:
            raise DraftError(f"neckline: {edge} doesn't run from {cname} to hps")
        while len(ix) < 8:  # a straight neckline: give it points to carry a curve
            k = int(np.argmax(np.linalg.norm(np.diff(pc["P"][ix], axis=0), axis=1)))
            a, b = ix[k], ix[k + 1]
            _insert(pc, a if (a + 1) % len(pc["P"]) == b else b, 0.5 * (pc["P"][a] + pc["P"][b]))
            ix = pattern.arc_indices(pc, arc)
            if pc["names"][cname] != ix[0]:
                ix = ix[::-1]
        sh_edge = D["edges"]["shoulder_front" if edge == "neck_front" else "shoulder_back"]
        Ps = np.concatenate(pd.edge_points(D, sh_edge))
        hps = pc["P"][ix[-1]].copy()
        far = Ps[int(np.argmax(np.linalg.norm(Ps - hps, axis=1)))]
        sdir = _unit(far - hps)
        if widen >= np.linalg.norm(far - hps) - 0.02:
            raise DraftError("neckline: widened past the shoulder")
        H = hps + sdir * widen
        C = pc["P"][ix[0]] + np.array([0.0, -abs(low)])
        n = len(ix)
        if shp == "v":
            new = C + (H - C) * np.linspace(0, 1, n)[:, None]
        elif shp == "square":
            corner = np.array([H[0], C[1]])
            cum = np.r_[0, np.linalg.norm(corner - C), np.linalg.norm(corner - C) + np.linalg.norm(H - corner)]
            s_ = np.linspace(0, cum[-1], n)
            pl = np.array([C, corner, H])
            new = np.c_[np.interp(s_, cum, pl[:, 0]), np.interp(s_, cum, pl[:, 1])]
            new[int(np.argmin(np.linalg.norm(new - corner, axis=1)))] = corner
        else:
            # leaves the centre at right angles to it, arrives at the neck point square to the shoulder seam
            perp = np.array([-sdir[1], sdir[0]])
            if perp[1] > 0:
                perp = -perp
            d = np.linalg.norm(H - C)
            B = np.r_[[C], pb.bez(C, C + np.array([0.45 * d, 0.0]), H + perp * min(0.35 * d, 0.9 * abs(H[1] - C[1])), H, n=4 * n)]
            cum = np.r_[0, np.cumsum(np.linalg.norm(np.diff(B, axis=0), axis=1))]
            s_ = np.linspace(0, cum[-1], n)
            new = np.c_[np.interp(s_, cum, B[:, 0]), np.interp(s_, cum, B[:, 1])]
        pc["P"][ix] = new
        moved[edge] = edge_length(D, chain)
    D["log"].append(f"neckline: neck point moved {widen * 1000:.0f} mm along the shoulder on front and back, centre front "
                    f"{front * 1000:.0f} mm lower ({shape}), centre back {back * 1000:.0f} mm lower; neckline now front "
                    f"{moved['neck_front'] * 1000:.0f} + back {moved['neck_back'] * 1000:.0f} mm per half")


pd.OPS.update({"neckline": op_neckline, "shawl": op_shawl, "lapel": op_lapel, "cut_away": op_cut_away, "darts_to_seam": op_darts_to_seam,
               "raglan": op_raglan, "kimono": op_kimono, "hood": op_hood, "pleat": op_pleat, "buttons": op_buttons,
               "stitch": op_stitch})
