"""The orbit's rows and text, and the limbus in a turned view. Part of the face ruler (face_ruler.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import face_ruler
from .face_ruler import _bil, _cam_points, _proj_jac_pt

def orbit_rows(res: dict, head: dict) -> list:
    """The orbit as a side view shows it (gnm_mm.ORBIT_SEEN: each a combination of the measures): [{"row", "current",
    "gap", "err", "sd" (the row's population sd), "read"}], the error from the solve's covariance (the cameras' yaw
    included when it was left free)."""
    from . import gnm_mm
    names = list(res["names"])
    g = {r["measure"]: r["gap"] for r in res["gaps"]}
    J = gnm_mm.jacobian()
    sp = gnm_mm._space()
    cur = gnm_mm.orbit(sp["T"] + np.tensordot(np.asarray(head["c"], float), sp["IB"], 1))
    out = []
    for row, comb in gnm_mm.ORBIT_SEEN.items():
        a = np.zeros(len(names))
        for k, w in comb.items():
            a[names.index(k)] = w
        gap = float(sum(w * g[k] for k, w in comb.items()))
        err = float(np.sqrt(max(a @ res["cov"] @ a, 0.0)))
        psd = float(np.linalg.norm(a @ J[:len(names)]))
        out.append({"row": row, "current": float(cur[row]), "gap": gap, "err": err, "sd": psd,
                    "read": float(max(0.0, 1 - (err / psd) ** 2))})
    return out


def orbit_text(rows: list) -> str:
    """The orbit's table: what a side view shows, model -> picture, +- the reader's error."""
    out = ["ORBIT (eye depth; a big-mass decision: set it BEFORE any lid work)   model -> picture   gap +-err"]
    for r in rows:
        flag = "" if abs(r["gap"]) > 2 * r["err"] else "  (inside the reader's error)"
        if r["read"] < 0.75:
            flag = "  NOT READ (these pictures do not pin it: the population's guess)"
        out.append(f"  {r['row']:24s} {r['current']:6.1f} -> {r['current'] + r['gap']:6.1f} mm  {r['gap']:+5.1f} +-{r['err']:.1f} "
                   f"(sd {r['sd']:.1f})  {face_ruler.ORBIT_SAY[r['row']]}{flag}")
    return "\n".join(out)


# ---- the limbus in a turned view (orbit, 2026-10-11) ------------------------------------------------------------------
def limbus_model(head: dict, iris_mm: float | None = None) -> list:
    """The model's two limbus circles in 3D: [{"X" centre, "r", "fwd", "lat" (unit, toward that eye's temple), "up",
    "B" (K, 3): the centre's move per identity comp}], the subject's right eye first. iris_mm: the iris' diameter to
    draw (the PICTURE's, read on the front view; default the model's own)."""
    out = []
    if head.get("kind") == "gnm":
        gr, V = head["gr"], head["V"]
        fwd, up = np.array([0.0, -1.0, 0.0]), np.array([0.0, 0.0, 1.0])
        for side in ("right", "left"):
            ids = np.where(gr[f"{side}_eye"] & gr["irises"])[0]
            P = V[ids] - V[ids].mean(0)
            rad = np.linalg.norm(P - np.outer(P @ fwd, fwd), axis=1)
            rim = ids[rad > 0.92 * rad.max()]
            X = V[rim].mean(0)
            out.append({"X": X, "r": float(rad[rad > 0.92 * rad.max()].mean()) if iris_mm is None else iris_mm / 2000.0,
                        "fwd": fwd, "up": up, "lat": np.array([np.sign(X[0] - head["L"][27, 0]), 0.0, 0.0]),
                        "B": head["B"][:, rim].astype(np.float64).mean(1)})
        return out
    from . import humanfit
    st = humanfit.state(head["spec"]["base"])
    ht = st["head"]
    fwd = np.asarray(ht.get("forward", [0, -1, 0]), float)
    r = float(ht["eye_r"])
    from . import base_implied
    ri = base_implied.drawn_iris(head["spec"], r)   # skin.eyes.iris_size, else GNM's limbus (its eyeball), else 0.51 r
    if iris_mm:
        ri = iris_mm / 2000.0
    up = np.array([0.0, 0.0, 1.0]) - fwd * fwd[2]
    up /= np.linalg.norm(up)
    xs = [float(e[0]) for e in head["eye_X"]]
    for j in (int(np.argmin(xs)), int(np.argmax(xs))):
        c = np.asarray(head["eye_X"][j], float)
        lat = np.cross(up, fwd) * (1.0 if j == int(np.argmax(xs)) else -1.0)
        lat = lat * np.sign(lat[0] * (c[0] - np.mean(xs)) + 1e-12) * 1.0
        out.append({"X": c + fwd * np.sqrt(max(0.985 ** 2 * r * r - ri * ri, 0.0)), "r": ri, "fwd": fwd, "up": up, "lat": lat,
                    "B": np.asarray(head["eye_B"][j], float)})
    return out


def _lum(img):
    """The picture as WHITENESS (the least of R, G, B; 0..1): the sclera is the only white thing round an eye (skin's
    blue is ~0.6 of its red), so sclera -> iris is the strongest step and skin -> lash a weaker one."""
    a = np.asarray(img.convert("RGB"), float) / 255.0
    return a.min(-1)


def limbus_read(lum, cam, lb: dict, origin=(0.0, 0.0), scale: float = 1.0, reach_mm: float = 7.0, far: bool = False,
                part=None, valid=None) -> dict | None:
    """One eye's limbus in a picture, near where the model's is: the shift (picture px) of the model's projected limbus
    circle that puts its side arcs on the picture's sclera -> iris edge (bright outside, dark inside; +-40 deg about the
    eye line, the lids cover the rest). Turned away from the camera the circle is a thin ellipse: the edge is then read
    ALONG THE EYE'S AXIS at the side arc nearer the camera (in a profile the iris shows through the cornea in front of
    the limbus' plane, the sclera lies behind it), and the far (nose-side) arc is used only when the disc is still
    open (cos > 0.45). -> {"d": (dx, dy) px, "p": the model's centre px, "q": the picture's, "score", "sharp", "open"}
    or None when the eye faces away. part: the model's own part picture through this camera (likeness_render.render's pass:
    >= 1 = eyeball): an arc the MODEL hides behind the nose bridge or a lid (under 60 % of it on the eyeball) is not
    read, and no read at all without the arc nearer the camera (a 45 deg view hides most of the far eye)."""
    from . import humanfit
    Rc = humanfit._cam_rot(cam)
    X, r, fwd, up, lat = lb["X"], lb["r"], lb["fwd"], lb["up"], lb["lat"]
    eye_c = np.asarray(cam["centre"], float) - Rc.T @ np.asarray(cam["t"], float)
    to = eye_c - X
    to /= np.linalg.norm(to)
    op = float(to @ fwd)                              # how open the disc is to the camera (1 = face on)
    if op < -0.05 or (far and op < face_ruler.FAR_OPEN):
        return None
    near_side = 1.0 if (to @ lat) >= 0 else -1.0      # which side arc is nearer the camera (+ = temple)
    th = np.radians(np.arange(-40, 41, 10.0))
    pin, pout, arc = [], [], []
    for sg in (1.0, -1.0):
        if sg != near_side and op < 0.45:
            continue
        if part is not None:
            tv = th[np.abs(th) < 0.4]            # (+-20 deg: the lids cover the arc's ends on any eye)
            Pa = X + r * 0.9 * (sg * np.cos(tv)[:, None] * lat + np.sin(tv)[:, None] * up)
            qa = np.round((_cam_points(cam, Pa)[1] - np.asarray(origin, float)) * scale).astype(int)
            ok = (qa[:, 0] >= 0) & (qa[:, 1] >= 0) & (qa[:, 0] < part.shape[1]) & (qa[:, 1] < part.shape[0])
            seen = np.mean([part[y, x] >= 1 for x, y in qa[ok]]) if ok.any() else 0.0
            if seen < 0.5:
                if sg == near_side or far:     # the FAR eye is read only whole (both arcs on the eyeball): with one arc
                    return None                # behind the bridge it latched onto lashes / the outline (3 of 8, 2.6-5.8 mm)
                continue
        for a in th:
            arc.append(sg)
            rad = sg * np.cos(a) * lat + np.sin(a) * up
            P = X + r * rad
            ax = (0.0007 * (1 - op)) * fwd if sg == near_side else 0.0 * fwd
            pin.append(P - 0.0009 * rad * max(op, 0.0) - 0.0002 * rad + ax)
            pout.append(P + 0.0009 * rad * max(op, 0.0) + 0.0002 * rad - ax)
    o = np.asarray(origin, float)
    qi = (_cam_points(cam, np.array(pin))[1] - o) * scale
    qo = (_cam_points(cam, np.array(pout))[1] - o) * scale
    pc = (_cam_points(cam, X[None])[1][0] - o) * scale
    mmpx = float(((X - np.asarray(cam["centre"], float)) @ Rc.T + np.asarray(cam["t"], float))[2] / cam["f"] * 1000.0) / scale
    from scipy.ndimage import gaussian_filter
    Ls = gaussian_filter(lum, max(0.15 / mmpx, 0.6))

    arc = np.array(arc)
    two = len(set(arc.tolist())) == 2

    Vd = None if valid is None else gaussian_filter(np.asarray(valid, np.float32), 1.0)

    def score(dx, dy):
        xo, yo = qo[:, 0][None] + dx[:, None], qo[:, 1][None] + dy[:, None]
        st = _bil(Ls, xo, yo) - _bil(Ls, qi[:, 0][None] + dx[:, None], qi[:, 1][None] + dy[:, None])
        st = np.clip(st, -0.08, 0.3)
        if Vd is not None:      # the "sclera" side must be on the figure: a white backdrop past the far eye's lashes is not
            st = np.where(_bil(Vd, xo, yo) > 0.9, st, -0.08)
        if not two:
            return st.mean(1)
        # BOTH side arcs must sit on an edge: one arc on a strong edge (the far eye's sclera against the nose, a lash
        # line) scored as well as the limbus (3 of 8 far eyes read 2.6-5.8 mm off)
        a, b = st[:, arc > 0].mean(1), st[:, arc < 0].mean(1)
        return 0.5 * (a + b) - 0.5 * np.maximum(face_ruler.LIMBUS_MIN - np.minimum(a, b), 0.0)
    R = reach_mm / mmpx
    best = None
    for step, span, c0 in ((0.3 / mmpx, R, np.zeros(2)), (0.06 / mmpx, 0.45 / mmpx, None)):
        c0 = best[1] if c0 is None else c0
        g = np.arange(-span, span + 1e-9, step)
        DX, DY = np.meshgrid(c0[0] + g, c0[1] + g)
        S = score(DX.ravel(), DY.ravel()) - 0.0015 * ((DX.ravel() ** 2 + DY.ravel() ** 2) * mmpx ** 2) / 10.0
        i = int(np.argmax(S))
        best = (float(S[i]), np.array([DX.ravel()[i], DY.ravel()[i]]), S.reshape(DX.shape), g)
    sc, d, S, g = best
    # how much better than the next best place 1.5+ mm away (a lash line, the other limbus): the read's sharpness
    g0 = np.arange(-R, R + 1e-9, 0.3 / mmpx)
    DX, DY = np.meshgrid(g0, g0)
    S0 = score(DX.ravel(), DY.ravel())
    away = np.hypot(DX.ravel() - d[0], DY.ravel() - d[1]) * mmpx > 1.5
    sharp = float(sc - S0[away].max()) if away.any() else 0.0
    f2 = (_cam_points(cam, (X + 0.001 * fwd)[None])[1][0] - o) * scale - pc      # the picture's direction of "forward"
    f2 = f2 / max(np.linalg.norm(f2), 1e-9)
    if op < 0.5:      # a side view: the reader puts the edge LIMBUS_SIDE_BIAS mm forward of the model's own limbus
        d = d - face_ruler.LIMBUS_SIDE_BIAS / mmpx * f2 * (1.0 if face_ruler.LIMBUS_SIDE_BIAS else 0.0)
    return {"d": d, "p": pc, "q": pc + d, "score": sc, "sharp": sharp, "open": op, "mmpx": mmpx, "fwd": f2}


def _limbus_obs(head, view, iris_mm=None):
    """The limbus of each eye that shows in a TURNED view (3/4: both; profile: the near one): where the picture has it
    against where the model has it, moving with the model's eye centres. Triangulated by the solve itself: the front
    picture gives each eye's place across the face, a turned one its depth; the camera's yaw moves the two eyes
    opposite ways, so both eyes of a 3/4 view pin depth without it, the one eye of a profile does not."""
    cam = view["cam"]
    lum = view.get("_lum")
    if lum is None:
        lum = view["_lum"] = _lum(view["img"])
    lbs = limbus_model(head, iris_mm or view.get("iris_mm"))
    from . import humanfit
    Rc = humanfit._cam_rot(cam)
    eye_c = np.asarray(cam["centre"], float) - Rc.T @ np.asarray(cam["t"], float)
    dist = [float(np.linalg.norm(lb["X"] - eye_c)) for lb in lbs]
    out = []
    for j, lb in enumerate(lbs):
        rd = limbus_read(lum, cam, lb, view.get("origin", (0.0, 0.0)), float(view.get("scale", 1.0)), far=dist[j] > min(dist) + 1e-6,
                         part=view.get("_part"), valid=view.get("_valid"))
        if rd is None or rd["score"] < face_ruler.LIMBUS_MIN or rd["sharp"] <= 0.0:
            continue
        Jp, mm1 = _proj_jac_pt(cam, lb["X"], lb["B"])
        s = float(view.get("scale", 1.0))
        for ax in (0, 1):
            out.append({"type": "limbus", "view": view["kind"], "name": f"limbus_{'rl'[j]}.{'xy'[ax]}", "o": float(rd["d"][ax]) * mm1 / s,
                        "J": Jp[ax] * mm1, "sig": (face_ruler.SIG_LIMBUS if rd["open"] >= 0.5 else face_ruler.SIG_LIMBUS_SIDE)[ax], "p": list(map(float, rd["p"])), "q": list(map(float, rd["q"])),
                        "X": list(map(float, lb["X"])), "score": rd["score"], "sharp": rd["sharp"], "open": rd["open"]})
    return out


def text(rows: list, top: int = 0, floor: float = 0.0) -> str:
    """The ruler's table: one line per measure, target - current, the reader's error, the move that closes it."""
    out = ["measure            target - current   +-err   move that closes it          what + looks like"]
    for r in rows[: top or None]:
        if abs(r["gap"]) < floor:
            continue
        mv = '"mm:%s": %+.1f' % (r["measure"], r["gap"])
        flag = "" if abs(r["gap"]) > 2 * r["err"] else "  (inside the reader's error)"
        if r.get("read", 1.0) < 0.75:      # the error is over half the population's sd
            flag = "  NOT READ (these pictures do not show it: the number is the population's guess)"
        out.append(f"{r['measure']:18s} {r['gap']:+6.1f} mm ({r['sd']:+.1f} sd) +-{r['err']:.1f}  {mv:28s} "
                   f"[{r['view']}] {r['see']}{flag}")
    return "\n".join(out)
