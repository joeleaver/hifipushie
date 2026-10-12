"""Folds: the soft-tissue lines and bulges a face's SHAPE model does not make (GNM's identity space has no eye bags,
no deep nasolabial fold, no crisp lid crease): spec["skin"]["folds"]. Each is a named anatomical feature placed from
the head's own landmarks (a path over the skin in interocular units: FOLDS), with the path's measured placement as
parameters (what skin_read reads off the reference pictures), laid as colour AND relief from ONE unique map on the
head (skin_marks' sphere wrap, as the stubble / freckle / base maps are):

  r  the groove: a soft valley along the path (painted height down + a darker, redder crease line)
  g  the roll beside it: a bulge (painted height up): the bag over a tear trough, the cheek's pad over a nasolabial fold
  b  the fold's own shade: a wider, soft darkening (what the valley's occlusion does to the light)

skin["folds"] = {name: amount | {"amount": 0..1.5, "width": mm (the feature's default), "roll": 0..1.5 (x the
  feature's own roll), "L": {"amount": x (times the fold's), "shift": [mm, ...] (the line moved ACROSS its landmark path,
  at stations evenly spaced along it; + = the feature's `plus` side), "extent": [t0, t1] (the part of the path that
  shows, 0..1)}, "R": {...}}}   (a centre-line fold takes "shift" / "extent" directly)

HONESTY about relief: this is painted height (bump in the look, the unique normal map in an export): it shades like
a groove 0.2-0.8 mm deep seen from the front, it never changes the silhouette, and a raking light or a profile view
shows a flat cheek. A heavy bag, real hooding or a deep jowl needs geometry (the block-in's `hooding` move, sculpt).
"""
from __future__ import annotations

import hashlib
import json

import numpy as np

from .spec import SpecError

VERSION = 2
PX = 0.0001            # m a map pixel at the face
DEPTH = 0.0009         # m: the groove layer's painted depth at map value 1
BULGE = 0.0010         # m: the roll layer's painted height at map value 1
STATION = 0.001        # m between stations along a path (the map's and the reader's)
N_SHIFT = 9            # shift is given at this many stations by default (any number is taken: interpolated)

# name -> path [(anchor joint, offset in interocular units)] on the LEFT side (".L" anchors: mirrored to the right;
# without: one centre-line fold), "plus": the anatomical direction of + shift (a world vector the across direction is
# signed by), width (mm, the valley's full width at half depth), depth (share of DEPTH at amount 1), tint (the crease
# line's darkening at amount 1), shade (the wide soft darkening), roll (bulge: (offset mm toward plus, width mm,
# share of BULGE)) or None, search (mm either side of the path the reader looks), res (mm a picture pixel: coarser
# pictures answer "cannot tell"), about.
FOLDS = {
    "nasolabial": {"path": [("lm_nostril.L", (0.1, 0.02, 0.05)), ("lm_mouth_corner.L", (0.2, 0.05, 0.1)),
                            ("lm_mouth_corner.L", (0.23, 0.08, -0.22))], "plus": (1, 0, 0.3), "width": 3.5, "depth": 0.8,
                   "tint": 0.5, "shade": 0.3, "roll": (4.5, 5.0, 0.35), "search": 6.0, "res": 1.6,
                   "about": "the fold from the nose's wing past the mouth's corner (the cheek's pad over it)"},
    "marionette": {"path": [("lm_mouth_corner.L", (0.06, 0.02, -0.03)), ("lm_mouth_corner.L", (0.12, 0.05, -0.42))],
                   "plus": (1, 0, 0), "width": 3.0, "depth": 0.7, "tint": 0.45, "shade": 0.3, "roll": (4.0, 4.5, 0.3),
                   "search": 4.5, "res": 1.4, "about": "the line down from the mouth's corner (the jowl's front edge)"},
    "mouth_corner": {"path": [("lm_mouth_corner.L", (0.01, 0.0, 0.0)), ("lm_mouth_corner.L", (0.15, 0.06, -0.03))],
                     "plus": (0, 0, 1), "width": 1.4, "depth": 0.45, "tint": 0.5, "shade": 0.15, "roll": None,
                     "search": 2.5, "res": 0.7, "about": "the crease running out from the mouth's corner"},
    "mentolabial": {"path": [("lm_lip_lower", (-0.3, 0.04, -0.13)), ("lm_lip_lower", (0.0, 0.0, -0.15)),
                             ("lm_lip_lower", (0.3, 0.04, -0.13))], "plus": (0, 0, 1), "width": 4.0, "depth": 0.6,
                    "tint": 0.3, "shade": 0.35, "roll": None, "search": 4.0, "res": 1.6,
                    "about": "the groove between the lower lip and the chin"},
    "tear_trough": {"path": [("lm_eye_inner.L", (0.03, 0.0, -0.09)), ("lm_lid_lower.L", (-0.05, 0.02, -0.21)),
                             ("lm_lid_lower.L", (0.24, 0.06, -0.25))], "plus": (0, 0, 1), "width": 3.5, "depth": 0.7,
                    "tint": 0.4, "shade": 0.45, "roll": (4.0, 4.0, 0.8), "search": 5.0, "res": 1.6,
                    "about": "the groove under the lower lid; its roll is the eye bag over it"},
    "lid_fold": {"path": [("lm_eye_inner.L", (0.07, 0.0, 0.045)), ("lm_lid_upper.L", (0.0, 0.0, 0.08)),
                          ("lm_eye_outer.L", (-0.02, 0.02, 0.07))], "plus": (0, 0, 1), "width": 1.2, "depth": 0.3,
                 "tint": 1.3, "shade": 0.5, "roll": None, "search": 2.25, "flank": 1.5, "res": 0.5,
                 "about": "the upper eyelid's crease line (the fold GNM's lids only hint at)"},
    "glabella": {"path": [("lm_brow_inner.L", (-0.035, -0.01, 0.1)), ("lm_brow_inner.L", (-0.015, -0.01, -0.08))],
                 "plus": (1, 0, 0), "width": 1.4, "depth": 0.6, "tint": 0.5, "shade": 0.15, "roll": None, "search": 3.0,
                 "res": 0.7, "about": "the vertical frown lines between the brows"},
}
KEYS = {"amount", "width", "roll", "L", "R", "shift", "extent"}
SIDE_KEYS = {"amount", "shift", "extent"}


def sided(name: str) -> bool:
    return any(a.endswith(".L") for a, _ in FOLDS[name]["path"])


def options(folds: dict | None) -> dict:
    """skin["folds"] validated: {name: {"amount", "width", "roll", "sides": {"L" | "R" | "": {"amount", "shift",
    "extent"}}}} (folds with amount 0 left out)."""
    out = {}
    if not folds:
        return out
    if not isinstance(folds, dict) or set(folds) - set(FOLDS):
        raise SpecError(f"skin folds: {{name: amount | {{...}}}} over {', '.join(FOLDS)}")
    for name, v in folds.items():
        v = {"amount": float(v)} if isinstance(v, (int, float)) else dict(v or {})
        if set(v) - KEYS:
            raise SpecError(f"skin folds.{name}: unknown keys {sorted(set(v) - KEYS)} (have {', '.join(sorted(KEYS))})")
        a = float(v.get("amount", 1.0))
        if not 0 <= a <= 1.5:
            raise SpecError(f"skin folds.{name}: amount is 0..1.5")
        if a <= 0:
            continue
        sides = {}
        for s in ((".L", ".R") if sided(name) else ("",)):
            q = v.get(s[1:]) if s else {k: v[k] for k in ("shift", "extent") if k in v}
            q = dict(q or {})
            if set(q) - SIDE_KEYS:
                raise SpecError(f"skin folds.{name}: a side takes amount, shift, extent")
            ext = [float(x) for x in q.get("extent", (0.0, 1.0))]
            if len(ext) != 2 or not 0 <= ext[0] < ext[1] <= 1:
                raise SpecError(f"skin folds.{name}: extent is [t0, t1] within 0..1")
            sides[s] = {"amount": float(np.clip(q.get("amount", 1.0), 0, 3)), "shift": [float(x) for x in q.get("shift", [])], "extent": ext}
        out[name] = {"amount": a, "width": float(v.get("width", FOLDS[name]["width"])), "roll": float(v.get("roll", 1.0)), "sides": sides}
    return out


class _Surface:
    """The head's skin under the map: a point for any direction from the wrap's centre (smooth: the mesh's radius
    interpolated), and the normal there."""

    def __init__(self, spec: dict, part: str, J: dict):
        from scipy.interpolate import LinearNDInterpolator
        from scipy.spatial import cKDTree
        from . import skin_marks as sm
        self.sp = sm.sphere(J, (-62.0, 72.0), 220.0, PX)
        V, Nn, _ = sm.head_mesh(spec, part, J)
        V, Nn = np.asarray(V, float), np.asarray(Nn, float)
        keep = sm.outward(self.sp, V, Nn, V)
        self.o = np.asarray(self.sp["fr"]["o"], float)
        self._R = LinearNDInterpolator(sm.pix(self.sp, V[keep]), np.linalg.norm(V[keep] - self.o, axis=1))
        self._tree, self._N, self.V, self.Nall, self._Vk = cKDTree(V[keep]), Nn[keep], V, Nn, V[keep]

    def seat(self, P: np.ndarray, snap: bool = False) -> np.ndarray:
        """Points moved along their ray from the wrap's centre onto the skin (left where the wrap does not see).
        snap: first to the nearest point of the skin (a landmark offset floats a few mm off it, and the ray from a centre
        at the mouth's height would carry a point by the eye several mm up the lid)."""
        from . import skin_marks as sm
        P = np.asarray(P, float)
        if snap:
            P = self._Vk[self._tree.query(P)[1]]
        d = P - self.o
        r = np.linalg.norm(d, axis=1)
        R = self._R(sm.pix(self.sp, P))
        R = np.where(np.isfinite(R), R, r)
        return self.o + d / np.maximum(r, 1e-9)[:, None] * R[:, None]

    def normal(self, P: np.ndarray) -> np.ndarray:
        return self._N[self._tree.query(P)[1]]


_SURF: dict = {}


def surface(spec: dict, part: str, J: dict) -> _Surface:
    from . import skin_marks as sm
    V, _, _ = sm.head_mesh(spec, part, J)
    key = hashlib.sha1(json.dumps([np.asarray(V[:50]).round(5).tolist(), len(V)]).encode()).hexdigest()
    if key not in _SURF:
        if len(_SURF) > 3:
            _SURF.pop(next(iter(_SURF)))
        _SURF[key] = _Surface(spec, part, J)
    return _SURF[key]


def _resample(P: np.ndarray, step: float) -> np.ndarray:
    """A polyline as a smooth curve (Catmull-Rom) sampled every `step`."""
    P = np.asarray(P, float)
    if len(P) > 2:
        Q = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
        out = []
        for i in range(1, len(Q) - 2):
            for t in np.linspace(0, 1, 12, endpoint=False):
                p0, p1, p2, p3 = Q[i - 1], Q[i], Q[i + 1], Q[i + 2]
                out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
        P = np.array(out + [P[-1]])
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    n = max(int(round(s[-1] / step)) + 1, 4)
    t = np.linspace(0, s[-1], n)
    return np.stack([np.interp(t, s, P[:, k]) for k in range(3)], 1)


def paths(spec: dict, part: str, J: dict, cfg: dict | None = None, names=None) -> dict:
    """{(name, side): {"P": (m, 3) stations on the skin every STATION, "across": (m, 3) unit vectors in the skin
    toward the fold's plus side, "t": 0..1 along, "amount": (m,) (the side's amount, 0 outside its extent, eased at the
    ends), "width", "roll"}}. cfg = options(skin["folds"]): the measured shift is applied; None: the landmark paths
    themselves (what the reader measures from), amount 1."""
    from .skin import interocular
    io = interocular(J)
    S = surface(spec, part, J)
    out = {}
    for name in (names or (cfg if cfg is not None else FOLDS)):
        fd = FOLDS[name]
        o = (cfg or {}).get(name)
        for sd, sx in (((".L", 1.0), (".R", -1.0)) if sided(name) else (("", 1.0),)):
            try:
                pl = np.array([np.asarray(J[a[:-2] + sd if a.endswith(".L") else a], float) + io * np.array([sx * off[0], off[1], off[2]])
                               for a, off in fd["path"]])
            except KeyError as err:
                raise SpecError(f"skin folds.{name}: needs joint {err.args[0]!r} (a GNM head's lm_* landmarks)")
            P = S.seat(_resample(S.seat(pl, snap=True), STATION))
            nrm = S.normal(P)
            tan = np.gradient(P, axis=0)
            tan /= np.maximum(np.linalg.norm(tan, axis=1, keepdims=True), 1e-12)
            ac = np.cross(nrm, tan)
            ac /= np.maximum(np.linalg.norm(ac, axis=1, keepdims=True), 1e-12)
            plus = np.array([sx * fd["plus"][0], fd["plus"][1], fd["plus"][2]], float)
            if float((ac @ plus).mean()) < 0:
                ac = -ac
            t = np.linspace(0, 1, len(P))
            amount = np.ones(len(P))
            if o is not None:
                q = o["sides"][sd]
                if q["shift"]:
                    sh = np.interp(t, np.linspace(0, 1, len(q["shift"])), q["shift"]) * 0.001
                    P = S.seat(P + sh[:, None] * ac)
                e0, e1 = q["extent"]
                amount = o["amount"] * q["amount"] * ((t >= e0) & (t <= e1))
            ease = np.clip(np.minimum(t - (o["sides"][sd]["extent"][0] if o else 0.0), (o["sides"][sd]["extent"][1] if o else 1.0) - t) / 0.18, 0, 1)
            amount = amount * (0.25 + 0.75 * np.sin(0.5 * np.pi * ease))   # a fold fades toward its ends
            out[(name, sd)] = {"P": P, "across": ac, "t": t, "amount": amount, "width": (o or fd)["width"],
                               "roll": (o["roll"] if o else 1.0)}
    return out


def fold_map(spec: dict, part: str, J: dict, cfg: dict) -> tuple[str, dict, dict]:
    """The fold map's file, the image dict's placement keys, stats. cfg = options(skin["folds"])."""
    from scipy.ndimage import gaussian_filter
    from scipy.spatial import cKDTree
    from . import skin_marks as sm, store
    S = surface(spec, part, J)
    sp = S.sp
    key = hashlib.sha1(json.dumps([cfg, np.asarray(S.V[:50]).round(5).tolist(), len(S.V), sp["img"], VERSION, sm.VERSION, FOLDS],
                                  sort_keys=True, default=str).encode()).hexdigest()[:16]
    path = store.HOME / "_images" / f"mk_folds_{key}.png"
    stats_f = path.with_suffix(".json")
    if path.exists() and stats_f.exists():
        return str(path), sp["img"], json.loads(stats_f.read_text())
    W, H = sp["W"], sp["H"]
    out = np.zeros((H, W, 3), np.float32)
    ps = paths(spec, part, J, cfg)
    rows = sm._pixel_points(sp, S.V, S.Nall, step=2)
    stats = {"size": [W, H], "folds": {}}
    for (name, sd), q in ps.items():
        fd = FOLDS[name]
        if not (q["amount"] > 0).any():
            continue
        x = sm.pix(sp, q["P"])
        reach = 0.001 * (max(q["width"] * 1.5 * 2.5, (fd["roll"][0] + 1.5 * fd["roll"][1]) if fd["roll"] else 0.0) + 2.0)
        pad = int(reach / PX * 1.6) + 4
        x0, x1 = max(int(np.nanmin(x[:, 0])) - pad, 0), min(int(np.nanmax(x[:, 0])) + pad, W)
        y0, y1 = max(int(np.nanmin(x[:, 1])) - pad, 0), min(int(np.nanmax(x[:, 1])) + pad, H)
        if x1 <= x0 or y1 <= y0:
            continue
        Q, ok, _ = rows(y0, y1)
        Q = Q.reshape(y1 - y0, W, 3)[:, x0:x1].reshape(-1, 3)
        ok = ok.reshape(y1 - y0, W)[:, x0:x1].ravel()
        d, i = cKDTree(q["P"]).query(Q)
        s = ((Q - q["P"][i]) * q["across"][i]).sum(1)
        a = q["amount"][i] * ok
        sg = 0.001 * q["width"] / 2.355
        groove = a * fd["depth"] * np.exp(-0.5 * (d / sg) ** 2)
        shade = a * fd["shade"] * np.exp(-0.5 * (d / (2.6 * sg)) ** 2)
        tint = a * fd["tint"] * np.exp(-0.5 * (d / (0.8 * sg)) ** 2)
        roll = np.zeros_like(groove)
        if fd["roll"]:
            r0, rw, rk = fd["roll"]
            along = np.sqrt(np.maximum(d * d - s * s, 0.0))          # past the path's ends
            roll = a * rk * q["roll"] * np.exp(-0.5 * ((s - 0.001 * r0) / (0.001 * rw / 2.355)) ** 2) * np.exp(-0.5 * (along / (0.004)) ** 2)
        blk = out[y0:y1, x0:x1]
        shp = blk.shape[:2]
        # r: the groove's depth (x DEPTH); g: the roll (x BULGE); b: the darkening (crease line + soft shade, 0..1)
        blk[..., 0] = np.maximum(blk[..., 0], (groove / 1.5).reshape(shp))
        blk[..., 1] = np.maximum(blk[..., 1], (roll / 1.5).reshape(shp))
        blk[..., 2] = np.maximum(blk[..., 2], np.clip(np.maximum(tint, shade) / 1.5, 0, 1).reshape(shp))
        stats["folds"][name + sd] = {"stations": int(len(q["P"])), "amount": round(float(q["amount"].max()), 3)}
    for k in range(3):
        out[..., k] = gaussian_filter(out[..., k], 1.0)
    sm._save(path, out)
    stats_f.write_text(json.dumps(stats))
    return str(path), sp["img"], stats


def build(spec: dict, p: dict, J: dict, layer, ctx: dict) -> None:
    """The folds' layers (skin_features.build calls this after the wrinkles): groove, roll, shade."""
    cfg = options(p.get("folds"))
    if not cfg or not ctx.get("face") or "lm_jaw_1.L" not in J:
        return
    path, place, _ = fold_map(spec, p["part"], J, cfg)
    im = lambda ch: {"image": {"file": path, **place, "channel": ch}}  # noqa: E731
    base_r = ctx["base_r"]
    # (map values are amount x share / 1.5: the layers' strengths carry the 1.5 back)
    layer("folds_shade", color=[0.66, 0.53, 0.5], mix="multiply", opacity=1.0, mask=[{**im("b"), "levels": [0.0, 1.0 / 1.5]}])
    layer("folds_groove", height=-round(DEPTH * 1.5, 7), roughness=min(base_r + 0.08, 0.95), opacity=0.6, mask=[im("r")])
    layer("folds_roll", height=round(BULGE * 1.5, 7), mask=[im("g")])


def reference() -> str:
    return "\n".join(["FOLDS (skin.folds: {name: amount | {amount, width mm, roll, L / R: {amount, shift [mm..], extent [t0, t1]}}}; "
                      "colour + painted relief from one map; skin_from_reference reads them off the references):"] +
                     [f"  {k:13s} {v['about']} (width {v['width']} mm" + (", with a roll" if v["roll"] else "") +
                      f"; readable from {v['res']} mm a pixel)" for k, v in FOLDS.items()])
