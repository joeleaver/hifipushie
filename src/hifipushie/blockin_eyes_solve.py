"""The solve: `solve`, the orbit's status, `eye_step`, and their texts. Part of the block-in's eyes (blockin_eyes.py has the overview)."""
from __future__ import annotations

import copy

import numpy as np

from . import blockin_eyes
from .blockin_eyes import _names
from .blockin_eyes_evidence import crease_target, iris_check, photo_evidence, ruler_evidence, socket
from .blockin_eyes_reader import Reader

# ---- the solve -----------------------------------------------------------------------------------------------------
def _head(base, c, e, Ln, Rn):
    from . import blockin as bi, onemesh
    from . import onemesh_head
    b = copy.deepcopy(base)
    bi.set_identity({"base": b}, c)
    ex = {**{Ln[k]: round(float(e[k]), 6) for k in range(blockin_eyes.NE)}, **{Rn[k]: round(float(e[k]), 6) for k in range(blockin_eyes.NE)}}
    b["head"]["expression"] = {k: v for k, v in ex.items() if v}
    ht = onemesh_head.head_template(b)
    for kk in [k for k in onemesh._CACHE if isinstance(k, tuple) and k and k[0] == "head_t"]:
        onemesh._CACHE.pop(kk, None)   # (each evaluation is a new head: don't keep hundreds)
    return ht, b


def solve(base: dict, ev: dict, iters: int = 6, log=print, d_line: float | None = None,
          hold_socket: float | None = blockin_eyes.SIG_SOCKET, crease: str | None = "default", ne: int = 0,
          crisp: float | None = None, hold_mm: float | None = "default") -> dict:
    """The opening: the identity (ne = 0, the default; ne = NE adds GNM's eye-region expression pairs for a real pose)
    for evidence ev (photo_evidence + the eye ruler's rows). base: the block-in's base (its lid pose cleared here;
    with ne = 0 any eye-region expression it carries is cleared too: the lids are identity). crease: "default" = CREASE
    = "lid": no fold term here (blockin_lid's whole-lid solve follows); a crease_shape template name = the older
    three-section match; None = the oldest target (the line's height + d_line). hold_socket: the socket readings'
    sigma (sd; None = not held). Returns {"c", "expression", "read0", "read", "cost", "dc", "e", "socket0", "socket",
    "crease", "shape0" / "shape" (section rms vs the template, mm)}."""
    crease = blockin_eyes.CREASE if crease == "default" else crease
    hold_mm = blockin_eyes.SIG_MM if hold_mm == "default" else hold_mm
    from . import gnm_mm
    Jmm = gnm_mm.jacobian() if hold_mm else None
    whole_lid = crease == "lid"
    use_shape = bool(crease) and not whole_lid and not ev.get("hooded") and np.isfinite(ev.get("tps", np.nan))
    shape = None
    sig_lid = blockin_eyes.SIG_LID_SHAPE if use_shape else blockin_eyes.SIG_LID
    d_line = blockin_eyes.D_LINE if d_line is None else float(d_line)
    from . import blockin as bi
    Ln, Rn, _ = _names()
    b0 = copy.deepcopy(base)
    pose = dict(b0["head"].get("pose") or {})
    pose.pop("lid_upper", None)
    pose.pop("lid_lower", None)
    b0["head"]["pose"] = pose
    if not pose:
        b0["head"].pop("pose", None)
    c0 = bi.identity({"base": b0})
    e0 = np.zeros(blockin_eyes.NE)
    ex0 = b0["head"].get("expression") or {}
    for k in range(blockin_eyes.NE):
        e0[k] = 0.5 * (float(ex0.get(Ln[k], 0.0)) + float(ex0.get(Rn[k], 0.0)))
    if not ne and np.abs(e0).max() > 1e-6:
        log(f"eye step: the base carries an eye-region expression (|e| {np.linalg.norm(e0):.2f}): cleared, the lids are "
            "solved in the identity (expression=True keeps and solves it: a real pose only)")
        e0[:] = 0.0
    ht0, _ = _head(b0, c0, e0, Ln, Rn)
    rd = Reader(ht0)
    heights = None
    if use_shape:
        # the picture's fold line (mm at an 11.7 mm iris) -> ours, per column; a column with no line takes the median
        k_iris = rd.read(ht0)["r_iris_mm"] / 5.85
        tc = [t if np.isfinite(t) else ev["tps"] for t in (ev.get("tps_cols") or [ev["tps"]] * 3)]
        heights = [t * k_iris for t in tc]
        if ev.get("ruler") and ev["ruler"].get("crease_cols"):   # (the ruler's line is in mm at the model already)
            heights = [float(t) for t in ev["ruler"]["crease_cols"]]
        shape = crease_target(crease, heights)
    rv = ev.get("ruler")
    if rv:
        rv_up, rv_lo = np.asarray(rv["up"], float), np.asarray(rv["lo"], float) - blockin_eyes.LO_BIAS
        rv_w = np.where(np.abs(blockin_eyes.RULER_COLS) > 7, 0.5, 1.0)
    ex_other = {k: v for k, v in ex0.items() if k not in set(Ln) | set(Rn)}

    def sock(c, e):
        return socket(c, {**ex_other, **{Ln[k]: e[k] for k in range(blockin_eyes.NE)}, **{Rn[k]: e[k] for k in range(blockin_eyes.NE)}})
    s0 = sock(c0, e0)
    L0 = np.asarray(ht0["lm68"], float)
    tps_k = None

    def resid(x):
        ht, _ = _head(b0, c0 + x[:170], e0 + x[170:], Ln, Rn)
        q = rd.read(ht)
        if rv:
            mg = rd.margins(ht)
            q["margins"] = mg
            r = []
            for a, b in ((mg["up"], rv_up), (mg["lo"], rv_lo)):
                d = (a - b) * rv_w / blockin_eyes.SIG_MARGIN
                r += list(np.where(np.isfinite(b), np.where(np.isfinite(d), d, 10.0), 0.0))
            r += list((mg["inner"] - np.asarray(rv["inner"], float)) * [1.0, 0.3] / blockin_eyes.SIG_CORNER)
            r.append((mg["ring_out"][0] - (float(rv["outer"][0]) + blockin_eyes.OUT_RING)) / blockin_eyes.SIG_CORNER)
        else:
            r = [(q["up"] - ev["up"]) / sig_lid if np.isfinite(q["up"]) else 50.0,
                 (q["lo"] - ev["lo"]) / sig_lid if np.isfinite(q["lo"]) else 50.0]
        if shape is not None:
            d = (rd.sections(ht) - shape) / blockin_eyes.SIG_SHAPE
            r += list(np.where(np.isfinite(d), d, 20.0).ravel())
        elif np.isfinite(ev.get("tps", np.nan)):
            want = ev["tps"] * q["r_iris_mm"] / (5.85)   # the picture's mm at an 11.7 mm iris -> ours
            if ev.get("hooded"):
                r.append((q["vis"] - want) / blockin_eyes.SIG_HOODED if np.isfinite(q["vis"]) else 20.0)
            elif whole_lid:
                pass                                     # (the fold is the whole-lid solve's, after the opening)
            else:
                r.append((q["hsoft"] - want) / blockin_eyes.SIG_TPS if np.isfinite(q["hsoft"]) else 20.0)
                r.append(min(q["lsoft"] - d_line, 0.0) / blockin_eyes.SIG_LINE)
        if crisp:   # (an experiment: the crease's depth inside a 0.75 mm chord at least `crisp` mm: #376 has 0.4-0.5)
            r.append(min(q["narrow"] - float(crisp), 0.0) / 0.05)
        if Jmm is not None:   # the head's millimetre measures held: pupils apart, eyes forward / height, skull, neck ...
            r += list(Jmm @ x[:170] / hold_mm)
        L = np.asarray(ht["lm68"], float)
        if hold_socket:
            s = sock(c0 + x[:170], e0 + x[170:])
            r += [(s[k] - s0[k]) / hold_socket for k in blockin_eyes.SOCKET]
        r += list(((L[blockin_eyes.HOLD] - L0[blockin_eyes.HOLD]) * 1000 / blockin_eyes.SIG_HOLD).ravel())
        r += list(((L[blockin_eyes.BROWS] - L0[blockin_eyes.BROWS]) * 1000 / blockin_eyes.SIG_BROW).ravel())
        return np.array(r), q
    n = 170 + int(ne)                      # (ne = 0: identity only; the expression the base already has stays)
    x = np.zeros(n)
    lam = 0.01
    _resid = resid

    def resid(x):  # noqa: F811
        return _resid(np.r_[x, np.zeros(170 + blockin_eyes.NE - len(x))])
    r, q0 = resid(x)
    log(f"eye step start: picture up {ev['up']:.2f} lo {ev['lo']:.2f} tps {ev.get('tps', np.nan):.2f} mm dark "
        f"{ev.get('dark', 0):.2f} | model up {q0['up']:.2f} lo {q0['lo']:.2f} show {q0['show']:.2f} mm crease local "
        f"{q0['local']:.2f} mm at {q0['height']:.1f}")
    f = float(r @ r + x @ x)
    for it in range(iters):
        J = np.zeros((len(r), n))
        h = 0.25
        for j in range(n):
            ej = np.zeros(n)
            ej[j] = h
            J[:, j] = (resid(x + ej)[0] - r) / h
        while True:
            step = np.linalg.solve(J.T @ J + (1 + lam) * np.eye(n), -(J.T @ r + x))
            xn = x + step
            rn, qn = resid(xn)
            fn = float(rn @ rn + xn @ xn)
            if fn < f:
                x, r, f, lam = xn, rn, fn, lam * 0.5
                break
            lam *= 4
            if lam > 1e4:
                break
        q = resid(x)[1]
        log(f"  it {it}: cost {f:.2f} |dc| {np.linalg.norm(x[:170]):.2f} |e| {np.linalg.norm(e0 + np.r_[x[170:], np.zeros(170 + blockin_eyes.NE - len(x))]):.2f} | up "
            f"{q['up']:.2f} lo {q['lo']:.2f} platform {q['vis']:.2f} (hood {q['drop']:.2f}) crease {q['lsoft']:.2f} mm at {q['hsoft']:.2f}")
        if lam > 1e4:
            break
    q = resid(x)[1]
    x = np.r_[x, np.zeros(170 + blockin_eyes.NE - len(x))]
    e = e0 + x[170:]
    s1 = sock(c0 + x[:170], e)
    log("  socket " + ", ".join(f"{k} {s0[k]:+.2f} -> {s1[k]:+.2f}" for k in blockin_eyes.SOCKET))

    def shape_rms(c, e):
        if shape is None:
            return float("nan")
        d = rd.sections(_head(b0, c, e, Ln, Rn)[0]) - shape
        return float(np.sqrt(np.nanmean(np.sum(d ** 2, -1))))
    sh0, sh1 = shape_rms(c0, e0), shape_rms(c0 + x[:170], e)
    if shape is not None:
        log(f"  crease shape ({crease}): section rms {sh0:.2f} -> {sh1:.2f} mm")
    return {"socket0": s0, "socket": s1, "c": c0 + x[:170], "expression": {**{Ln[k]: round(float(e[k]), 5) for k in range(blockin_eyes.NE) if abs(e[k]) > 1e-5},
                                              **{Rn[k]: round(float(e[k]), 5) for k in range(blockin_eyes.NE) if abs(e[k]) > 1e-5}},
            "read0": q0, "read": q, "cost": f, "dc": float(np.linalg.norm(x[:170])), "e": float(np.linalg.norm(e)),
            "pose": pose, "crease": crease if shape is not None else None, "shape0": sh0, "shape": sh1, "heights": heights}


def orbit_status(name: str, log=print) -> dict:
    """Is the ORBIT set? face_ruler's orbit rows for this model against its pictures (cached in the model's directory
    by its base + cameras): {"state": "unread" (no row these pictures pin: no side view, or inside the reader's error
    everywhere) | "off" (a read row is out by more than twice its error) | "ok", "rows", "text"}."""
    import json
    from . import store
    from . import blockin_table
    from . import face_ruler_compare
    h = blockin_table._spec_hash(name)
    p = store.HOME / name / "blockin_orbit.json"
    rows = None
    if p.exists():
        d = json.loads(p.read_text())
        if d.get("hash") == h:
            rows = d["rows"]
    if rows is None:
        try:
            rows = face_ruler_compare.compare(name)["orbit"]
        except Exception as e:  # noqa: BLE001
            return {"state": "unread", "rows": [], "text": f"ORBIT: not read ({e}). The eye's depth and the brow over it are "
                    "set BEFORE the lid (face_ruler; mm:eyes_forward, mm:brows_over_eyes, mm:brow_ridge_forward)."}
        p.write_text(json.dumps({"hash": h, "rows": rows}, indent=1))
    read = [r for r in rows if r["read"] >= 0.75]
    off = [r for r in read if abs(r["gap"]) > 2 * r["err"]]
    state = "off" if off else ("ok" if read else "unread")
    say = {"unread": "ORBIT: UNREAD: these pictures do not pin the eye's depth (every orbit row is inside the reader's "
                     "error or has no side view). The lid hangs between the brow and the ball: a lid solved on a wrong "
                     "orbit is solved again after it moves.",
           "off": "ORBIT: OFF: " + "; ".join(f"{r['row']} {r['gap']:+.1f} +-{r['err']:.1f} mm" for r in off)
                  + ". Set the orbit FIRST (face_ruler's table; block_in_step mm:eyes_forward / mm:brow_ridge_forward / "
                    "mm:brows_over_eyes ...), then run the eye step: the lid hangs between the brow and the ball.",
           "ok": "ORBIT: read and within the reader's error (" + "; ".join(f"{r['row']} {r['gap']:+.1f} +-{r['err']:.1f}" for r in read) + ")"}[state]
    return {"state": state, "rows": rows, "text": say}


def eye_step(name: str, out: str | None = None, seen: str = "", iters: int = 6, log=print, expression: bool = False,
             donor: str | None = None, orbit: bool = True, crease: str | None = "default", fold: str | None = None) -> dict:
    """The block-in step: the opening (solve), the lid as one structure with the eyeball guard (blockin_lid), written
    as a new model (blockin_steps.step with the identity set). fold: the lid's shape term: "crisp" (the default: recipe A,
    blockin_lid.fold_step: a designed crisp fold on the picture's fold line, brows held), "none" (the opening only:
    the fold costs |dc| 10-20 and moves the rest of the face ~0.6 mm rms; skip it while the masses are open) or "donor" (the older
    lid_step toward a donor head's lid; implied by donor= and by expression=True). expression=True: GNM's eye-region
    pairs solved too (a real pose: a squint); donor: the lid's donor (blockin_lid.donor; default s376); orbit=False
    skips the orbit check."""
    fold = fold or ("donor" if donor or expression else blockin_eyes.FOLD)
    if fold not in ("crisp", "donor", "none"):
        raise ValueError('eye step: fold = "crisp" (recipe A, the default), "donor" or "none" (the opening only)')
    if fold == "crisp" and expression:
        raise ValueError('eye step: fold="crisp" is identity only; with expression=True the lid is solved toward a donor (fold="donor")')
    from PIL import Image
    from . import blockin as bi, blockin_lid as bl, store
    from . import blockin_clay, blockin_models, blockin_steps
    orb = orbit_status(name, log) if orbit else None
    if orb:
        log(orb["text"])
    rj = blockin_models._refs(name)
    vi = blockin_clay._front(rj)
    v = rj["views"][vi]
    ev = photo_evidence(Image.open(v["image"]).convert("RGB"), v)
    base = store.load(name)["base"]
    rv = None
    try:   # the ruler's margins and corners in mm (edges, the iris as a circle); a small or cut-off eye: the detector's read
        rv = ruler_evidence(name)
        if rv["iris"] / rv["mm"] >= blockin_eyes.RULER_MIN_PX and all(np.isfinite(rv[k]).sum() >= 5 for k in ("up", "lo")):
            ev["ruler"] = {k: rv[k] for k in ("up", "lo", "inner", "outer", "crease_cols", "iris")}
        else:
            log(f"eye step: the ruler is not used (iris {rv['iris'] / rv['mm']:.0f} px across; it needs {blockin_eyes.RULER_MIN_PX:.0f}): "
                "the detector's lids in iris radii instead")
    except Exception as e:  # noqa: BLE001
        log(f"eye step: the ruler could not read the picture ({e}): the detector's lids in iris radii instead")
    s = solve(base, ev, iters=iters, log=log, ne=blockin_eyes.NE if expression else 0, crease=crease)
    c1, lid = s["c"], None
    if (blockin_eyes.CREASE if crease == "default" else crease) == "lid":
        # the fold line the lid's turn is put on: the ruler's (mm at the model, per column), else the detector's one height
        heights = cols = corners = None
        if ev.get("ruler") and rv is not None and np.isfinite(np.asarray(rv["crease"], float)).sum() >= 3 and rv["crease_dark"] >= 0.5 * blockin_eyes.DARK_LINE:
            heights, cols, corners = np.asarray(rv["crease"], float), blockin_eyes.RULER_COLS, (float(rv["inner"][0]), float(rv["outer"][0]))
        elif not ev.get("hooded") and np.isfinite(ev.get("tps", np.nan)):
            h1 = ev["tps"] * s["read"]["r_iris_mm"] / 5.85
            heights, cols, corners = np.array([h1, h1, h1]), np.array([-6.0, 0.0, 6.0]), (-12.0, 10.0)
        if fold == "none":
            log("eye step: fold=\"none\": the opening only (margins and corners); the lid's fold is left as the head has it")
        elif ev.get("hooded"):
            log("eye step: no fold line on the picture (hooded): the whole-lid solve is not run (its donor's platform "
                "would show); the visible platform was the opening's target")
        else:
            b1 = copy.deepcopy(base)
            bi.set_identity({"base": b1}, s["c"])
            b1["head"]["expression"] = s["expression"]
            b1["head"].pop("pose", None) if not s["pose"] else b1["head"].__setitem__("pose", s["pose"])
            if not s["expression"]:
                b1["head"].pop("expression", None)
            if fold == "crisp":
                lid = bl.fold_step(b1, heights, cols, corners, log=log)
            else:
                lid = bl.lid_step(b1, heights, cols, corners, donor_name=donor or bl.DONOR, log=log)
            c1 = lid["c"]
            if ev.get("ruler"):       # the margins after the lid solve, against the picture's rows again
                b2 = copy.deepcopy(b1)
                bi.set_identity({"base": b2}, c1)
                from . import onemesh_head
                ht2 = onemesh_head.head_template(b2)
                mg2 = Reader(ht2).margins(ht2)
                lid["margins_after"] = {k: np.asarray(x, float).tolist() for k, x in mg2.items()}
                d = np.r_[mg2["up"] - np.asarray(ev["ruler"]["up"], float), mg2["lo"] - (np.asarray(ev["ruler"]["lo"], float) - blockin_eyes.LO_BIAS)]
                lid["margin_miss"] = float(np.nanmax(np.abs(d[np.abs(np.r_[blockin_eyes.RULER_COLS, blockin_eyes.RULER_COLS]) < 7])))
                s["read"]["margins"] = mg2
    rep = blockin_steps.step(name, {}, out=out, seen=seen or "lids and fold vs the picture (eye step)",
                  why=(f"eye step ({'identity + GNM eye-region expression' if expression else 'identity only'}; no lidfold, no "
                       f"lid pose): picture up {ev['up']:.2f} lo {ev['lo']:.2f} iris radii, fold line {ev['tps']:.2f} mm; "
                       f"opening |dc| {s['dc']:.2f}, |e| {s['e']:.2f}"
                       + (f"; the lid as one structure, a crisp fold (recipe A) at {lid['crease']:.1f} mm: |dc| {lid['dc']:.2f}, "
                          f"turn {lid['before']['turn_mean']:.0f} -> {lid['after']['turn_mean']:.0f} deg, brow ring "
                          f"{lid['brow_drop']:+.1f} mm down, eyeball guard {lid['ball']['upper']:.2f} mm (stand-off "
                          f"{lid['standoff']:.1f})" if lid and lid.get("kind") == "crisp" else
                          f"; the lid as one structure (donor {lid['donor_name']}): |dc| {lid['dc']:.2f}, turn "
                          f"{lid['structure0']['tuck']:.0f} -> {lid['structure']['tuck']:.0f} deg, eyeball guard "
                          f"{lid['ball']['min']:.2f} mm (platform lifted {lid['clear']:.1f})" if lid else "")
                       + (f"; orbit {orb['state']}" if orb else "")),
                  _identity=c1, _head_set={"expression": s["expression"] or None, "pose": s["pose"] or None})
    if s["read"].get("margins") is not None:
        mg = s["read"]["margins"]
        rep["ruler"] = {"target": {**ev["ruler"], "lo": (np.asarray(ev["ruler"]["lo"], float) - blockin_eyes.LO_BIAS).tolist()},
                        "model": {k: np.asarray(x, float).tolist() for k, x in mg.items()}}
    rep["eyes"] = {"evidence": {k: v for k, v in ev.items() if k != "columns"}, "lid": lid, "orbit": orb,
                   "identity_only": not expression,
                   **{k: s[k] for k in ("read0", "read", "dc", "e", "crease", "shape0", "shape", "heights")}}
    try:   # the drawn iris against the picture's (a wrong iris size makes a right-in-radii opening wrong in mm)
        rep["eyes"]["iris"] = iris_check(name)["text"]
    except Exception:  # noqa: BLE001  (no readable iris: no line)
        pass
    return rep


def ruler_text(rv: dict, mg: dict) -> str:
    f = lambda a: " ".join("   - " if not np.isfinite(x) else f"{x:5.1f}" for x in np.asarray(a, float))  # noqa: E731
    return (f"\n  RULER (mm from the iris centre, u {blockin_eyes.RULER_COLS[0]:+.0f} .. {blockin_eyes.RULER_COLS[-1]:+.0f}): the lids were matched to the picture's "
            f"margins and corners, not to the detector's lids in iris radii"
            f"\n    upper margin  picture {f(rv['up'])} | model {f(mg['up'])}"
            f"\n    lower margin  picture {f(np.asarray(rv['lo'], float) - blockin_eyes.LO_BIAS)} | model {f(mg['lo'])}   (picture - {blockin_eyes.LO_BIAS}: the waterline)"
            f"\n    inner canthus picture u {rv['inner'][0]:.1f} | model (lm68) {mg['inner'][0]:.1f};  outer: picture {rv['outer'][0]:.1f} "
            f"| model's ring end {mg['ring_out'][0]:.1f} (the eyeball shows to ~{blockin_eyes.OUT_RING} mm short of it)")


def text(e: dict) -> str:
    """The eye step's report (eye_step's rep["eyes"])."""
    ev, a, b = e["evidence"], e["read0"], e["read"]
    fold = (f"no fold line on the picture (hooded: the platform target {blockin_eyes.HOODED_SHOW} mm visible)" if ev.get("hooded")
            else f"fold line {ev['tps']:.2f} mm over the lashes (at an 11.7 mm iris), darkness {ev['dark']:.2f}")
    from . import blockin_lid as bl
    lid = e.get("lid")
    kind = "identity only" if e.get("identity_only", False) else "identity + GNM eye-region expression (a pose)"
    return ((e["orbit"]["text"] + "\n" if e.get("orbit") else "")
            + f"EYE STEP ({kind}, the rest of the face held; no lidfold, no lid pose): "
            f"picture lids {ev['up']:.2f} / {ev['lo']:.2f} iris radii, {fold}\n"
            f"  opening before: lids {a['up']:.2f} / {a['lo']:.2f}, platform {a['show']:.2f} mm, crease {a['lsoft']:.2f} mm deep "
            f"at {a['hsoft']:.2f} mm\n"
            f"  opening after:  lids {b['up']:.2f} / {b['lo']:.2f} | |dc| {e['dc']:.2f}, eye expression |e| {e['e']:.2f}"
            + (ruler_text(e["evidence"]["ruler"], b["margins"]) if e["evidence"].get("ruler") and b.get("margins") is not None else "")
            + (f"\n    (margins re-read after the lid solve: within {lid['margin_miss']:.2f} mm of the picture's rows at u -6 .. 6)"
               if lid and lid.get("margin_miss") is not None else "")
            + ("\n" + bl.text(lid) if lid else "")
            + (f"\n  crease SHAPE (older three-section term): the {e['crease']!r} template's fold carried to the picture's line ("
               + "/".join(f"{h:.1f}" for h in (e.get("heights") or [])) + " mm over the margin, inner/pupil/outer): section rms "
               f"{e['shape0']:.2f} -> {e['shape']:.2f} mm" if e.get("crease") else "")
            + "\n  The fold's FORM is geometry (above). Her line's darkness is not a target and is not added (decision "
              "2026-10-11: the skin-over-skin overhang is left alone; no painted fold line, crease make-up or liner)."
            + (f"\n  {e['iris']}" if e.get("iris") else ""))
