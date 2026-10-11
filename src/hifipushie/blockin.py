"""blockin.py: the ARTIST BLOCK-IN, the default way to model a person's head from reference pictures (faces6's
method, docs/notes/gnm_atlas.md "THE ARTIST BLOCK-IN METHOD"; Joe, 2026-10-10: "this method should be our default for
all modeling humans going forward").

The model is the artist: start from a base head of the right KIND (the person's body, GNM's sampler class mean for
the sex, an age-dependent GNM base share), look at it beside the pictures the way a sculptor does (eye-registered
photo | clay under the photo's own light | overlay | outline difference | squint), name the single biggest difference
in masses and planes, take ONE small whole-face step, keep it only if the whole face reads closer and the target
table didn't lose an item. Every step is a new model (revert = step again from an earlier one); one log per block-in.

  start(name, refs, ...)        the base of the right kind, with the references' fitted cameras
  look(name, out)               the six-column sheet per view (+ the target table: table / table_text)
  step(src, moves, out, ...)    free / held / data-backed gap directions, base keys, lid pose; logged
  lid_read(name) / lid_match    lid margins vs the iris (MRD-style, in iris radii), photo and render; lids by measure

Direction vocabulary (step moves, in population sd unless said):
  <macro>        humanmacro FREE: the population's conditional mean per +1 sd, the head's SIZE kept (masses,
                 proportions; try first)
  <macro>~       the raw population coupling, size included (faces6's free mode: lean cheeks came with a smaller head)
  <macro>!       humanmacro HELD: that macro alone, every other macro kept (one feature; costs more |c| per unit)
  nd:<gap>       filled vocabulary gaps (newdirs: coupled within sex): see gap_names()
  sex            +1 = GNM's sampler female class mean -> male class mean
  eth0..eth2     the sampler's ethnicity contrasts, per +1 population sd along each
  weight / dimorphism / gnm_base / head_scale    base keys, SET (head_scale = base.style.human.head_size: the head's
                 uniform size about the top of the neck, x the body's own head; 1 = the body's)
  lid_upper / lid_lower                          base.head.pose, SET, metres (-0.001 = that lid 1 mm up)
"""
from __future__ import annotations

import copy
import hashlib
import json
import time
from pathlib import Path

import numpy as np

DATA = Path(__file__).with_name("blockin_data.npz")
_C: dict = {}

# the five target groups (Joe: "Head and jaw shape, eye placement, nose size and shape, mouth size and placement"):
# likeness checklist items read on the photo and on the model through each picture's fitted camera
GROUPS = {
    "head shape": ["face_height", "face_index", "upper_third", "middle_third", "width_temple", "width_cheekbone",
                   "forehead_slope", "prof_forehead_slope"],
    "jaw and chin": ["width_jaw", "width_chin", "jaw_taper", "jaw_gonial", "jaw_angle_height", "chin_height",
                     "chin_shape", "chin_projection", "prof_chin"],
    "eye placement": ["pupil_distance", "intercanthal", "eye_width"],
    "nose": ["nose_length", "alar_width", "width_nose_base", "nose_projection", "prof_nose_length", "prof_bridge_bow",
             "tip_height", "nasolabial_angle"],
    "mouth": ["mouth_width", "mouth_line", "philtrum", "lower_third", "mouth_over_alar"],
}
# items whose reading is not the anatomy their name says: shown, not counted (brow_eye was dropped: it reads GNM's brow
# landmarks, not the person's hair brows)
FLAGGED = {"jaw_angle_height": "reads MediaPipe 172 / 397 (the detector's guess at the jaw contour), not the gonion",
           # (blockin2, Garrett: a held nose_width -1.0 moved the alae 3.4 mm and this row < 0.45 mm; MediaPipe's alar
           # points sit on the cheek past the alae on picture and clay alike)
           "alar_width": "reads MediaPipe's alar points, which sit on the cheek past the alae (blind to the alae)",
           "mouth_over_alar": "its alar width is MediaPipe's (on the cheek past the alae)"}

BODY_KEYS = ("weight", "neck_double", "neck_depth")
HEAD_KEYS = {"dimorphism": "dimorphism", "gnm_base": "gnm_base", "eye_size": "eyes", "eye_radius": "eye_radius",
             "gnm_base_rest": "gnm_base_rest"}
# head_scale: the one mesh's head is the BODY's head (base.head.scale is overwritten by the body's size); a uniform size
# change is base.style.human.head_size (humanstyle: the head scaled about the top of the neck, eyeballs with it)
POSE_KEYS = ("lid_upper", "lid_lower")
# LOCAL residuals (what GNM's identity can't draw: a confirmed capability gap), as faceslide's local sliders, SET, with
# the population sd ICT's scans give them beyond GNM's identity (faces5 regbasis2_nose's 8 leading modes projected on
# each field, blockin/radix.py): the radix width varies 0.09 units (~0.13 mm) past GNM: a real but near-invisible gap
# designed (hand-authored, not data-backed) soft-tissue / age ops a block-in step may SET: faceslide's age sliders (units:
# +1 = the op's unit amount, faceslide.UNITS: age_nasolabial 2 mm crease, cheek_hollow 4 mm ...) and headage's ops
# without a slider (base.head.shape: m, or a share for lips_thin)
SHAPE_MOVES = ("age_nasolabial", "age_prejowl", "age_cheek_flat", "age_lid_fold", "face_planes", "face_lean",
               "cheek_hollow", "eye_bag", "lip_bow", "lip_roll", "lips_thin")
LOCAL_SD = {"nose_radix_width": 0.09, "nose_tip_width": 0.18, "nose_dorsum_width": 0.12}
STRIP = ("sliders", "warp", "fold", "pose", "shape", "seed", "spread", "features", "expression", "habitual")
SQUINT_MM = 9.0
LIGHT = "sh"            # the sheets' light: "sh" (2nd-order spherical harmonics fitted on the skin) | "linear" (c0 + w.n, AO, shadow)
FILL = 0.45             # display fill: the clay's shadow side lifted to this share of the lit skin's median
HAIR_RGB = np.array([62.0, 46.0, 36.0])
BROWS_R = ([70, 63, 105, 66, 107], [46, 53, 52, 65, 55])
BROWS_L = ([300, 293, 334, 296, 336], [276, 283, 282, 295, 285])


# ---------------------------------------------------------------- data, identity, directions

def data() -> dict:
    """The precomputed table (blockin_data.npz, from GNM's semantic sampler via the audit's numpy decoder, and faces6
    newdirs.py): class means m_f / m_m / mean, eth_means (gender x ethnicity), eth_dirs / eth_sd, nd_* (gaps)."""
    if "d" not in _C:
        z = np.load(DATA)
        _C["d"] = {k: (z[k] if z[k].dtype.kind in "US" else np.asarray(z[k], float)) for k in z.files}
    return _C["d"]


def gap_names() -> list[str]:
    return [str(x) for x in data()["nd_names"]]


def default_gnm_base(age: float) -> float:
    """The GNM base share by age (coordinator, 2026-10-10): a young face reads right on half GNM's template (0.5: soft,
    young); an older one on MakeHuman's own aged head (0): linear between 25 and 50."""
    return float(np.clip(0.5 * (50.0 - float(age)) / 25.0, 0.0, 0.5))


def identity(spec: dict) -> np.ndarray:
    v = np.zeros(170)
    idn = (spec["base"]["head"].get("identity") or {})
    if isinstance(idn, dict):
        for k, x in idn.items():
            if k.startswith("head_"):
                v[int(k.split("_")[1])] = float(x)
    else:
        v[:len(idn)] = np.asarray(idn, float)[:170]
    return v


def set_identity(spec: dict, c) -> None:
    spec["base"]["head"]["identity"] = {f"head_{i:03d}": round(float(x), 5) for i, x in enumerate(c)}


def vocabulary() -> str:
    from . import humanmacro as hm
    return ("macros (free, size kept; append ! for held, ~ for the raw coupling incl. size): " + ", ".join(hm.NAMES) + "\ngaps: " + ", ".join("nd:" + n for n in gap_names())
            + "\nsex, eth0, eth1, eth2; base keys (set): weight, dimorphism, gnm_base, head_scale; lids (set, m): "
            "lid_upper, lid_lower, eye_radius; DESIGNED age ops (set, not data): "
            + ", ".join("shape:" + k for k in SHAPE_MOVES) + "; local residuals (set): local:<faceslide slider>, e.g. "
            + ", ".join(f"local:{k} (sd {v})" for k, v in LOCAL_SD.items())
            + "; GNM region principal directions (coupled, size kept): pc:<GNM region><i>, e.g. pc:nose_region0 .. 7"
            + "; SCULPT a zone the GNM way (mm, its mean normal; macros held, locality): sculpt:<zone>, relief:<zone> "
            "(against its surround: - deepens a groove), options |hold=<zone>+..|free=<macro>+..|loc=<w>; zones: "
            "gnm_controls(zones=True); any atlas identity control raw: gnm:<control> (head_042, z:05, label:sex ...)")


def _size_row() -> np.ndarray:
    """head_size's row of humanmacro's table in sd per component (the interocular distance: the head's absolute size)."""
    from . import humanmacro as hm
    t = hm.table()
    i = hm.NAMES.index("head_size")
    return t["A"][i] / t["sd"][i]


def keep_size(d: np.ndarray) -> np.ndarray:
    """d with the least change that keeps head_size (the interocular distance) where it was. The population couples
    size with everything (lean cheeks come with smaller heads: a free cheek_fullness -0.5 shrank Garrett's face 1-2 %
    in every width and length, and faces6's free rounds ended 8-10 % small); a sculptor sets size separately."""
    from . import humanmacro as hm
    a = _size_row()
    d = np.asarray(d, float).copy()
    d[:hm.K] -= a * (a @ d[:hm.K]) / (a @ a)
    return d


_PCS: dict = {}


def region_pcs(region: str, n: int = 8) -> np.ndarray:
    """GNM's OWN principal directions for one region (a GNM vertex group: nose_region, ...): the right singular vectors
    of the identity basis restricted to the region's vertices, i.e. the coefficient directions (unit |c| = 1 population
    sd, the coefficients being unit variance) that move that region most; the rest of the head moves as GNM couples it.
    Sign: + moves the region forward (out of the face) on average. (n, 170)."""
    if region not in _PCS:
        from . import base as basemod
        g = basemod._gnm_data()
        if region not in g["groups"]:
            raise ValueError(f"pc: no GNM region {region!r} (one of {', '.join(sorted(g['groups']))})")
        msk = np.asarray(g["groups"][region]) > 0.5
        B = np.asarray(g["vertex_identity_basis"], float)[:170, msk, :]    # (170, V_region, 3)
        _, S, Vt = np.linalg.svd(B.reshape(170, -1).T, full_matrices=False)
        fwd = B[:, :, 2].mean(1)                                           # GNM faces +Z
        Vt = Vt[:n] * np.sign(Vt[:n] @ fwd + 1e-30)[:, None]
        _PCS[region] = Vt
    return _PCS[region]


def direction(name: str) -> np.ndarray:
    """A move's change of the 170 head components per unit (see the module doc). Free macros, gaps and ethnicity keep
    the head's size (keep_size); `<macro>~` is the raw population coupling, size included (faces6's free mode)."""
    from . import humanmacro as hm
    d = np.zeros(170)
    if name.endswith("!") and name[:-1] in hm.NAMES:
        d[:hm.K] = hm.direction(name[:-1], held=True)
        return d
    if name.endswith("~") and name[:-1] in hm.NAMES:
        d[:hm.K] = hm.direction(name[:-1])
        return d
    if name in hm.NAMES:
        if name == "head_size":
            d[:hm.K] = hm.direction(name)
            return d
        t = hm.table()
        An = t["A"] / t["sd"][:, None]
        d[:hm.K] = np.linalg.pinv(An[[hm.NAMES.index(name), hm.NAMES.index("head_size")]])[:, 0]
        return d
    D = data()
    gn = gap_names()
    if name.startswith("nd:") and name[3:] in gn or name in gn:
        return keep_size(D["nd_dirs"][:, gn.index(name[3:] if name.startswith("nd:") else name)])
    if name in ("sex", "sex_gnm_dir"):
        d = np.asarray(D["m_m"] - D["m_f"], float)
        return d if name == "sex" else d / np.linalg.norm(d)   # (sex_gnm_dir: faces6's unit vector)
    if name.startswith(("eth_dir", "eth")) and name[-1].isdigit():
        k = int(name[-1])
        if k < D["eth_dirs"].shape[1]:
            return keep_size(np.asarray(D["eth_dirs"][:, k], float) * float(D["eth_sd"][k]))
    if name.startswith("pc:"):
        reg, k = name[3:].rstrip("0123456789"), name[3:][len(name[3:].rstrip("0123456789")):]
        return keep_size(region_pcs(reg)[int(k or 0)])
    if name.startswith(("sculpt:", "relief:")):   # (gnmcontrols) a zone moved the GNM way: per +1 mm, macros held
        from . import gnm_controls as gcm
        return gcm.sculpt(**gcm.parse_sculpt(name))["dc"]
    if name.startswith("gnm:"):   # (gnmcontrols) any identity-space control of the atlas, raw (its own unit)
        from . import gnm_controls as gcm
        d = gcm.identity_direction(name[4:])
        if d is None:
            raise ValueError(f"{name}: an expression / pose control, not an identity move (block_in_expression fits a "
                             "picture's expression)")
        return d
    raise ValueError(f"block-in: no direction {name!r}. Vocabulary:\n{vocabulary()}")


def _macro_read(c) -> dict:
    from . import humanmacro as hm
    return hm.read(np.asarray(c, float)[:hm.K])


# ---------------------------------------------------------------- models, references, the log

def _refs(name: str) -> dict:
    from . import store
    p = store.HOME / name / "human_refs.json"
    if not p.exists():
        raise ValueError(f"{name}: no fitted references (human_refs.json); start a block-in with block_in_start(name, refs=...)")
    return json.loads(p.read_text())


def _save(name: str, spec: dict, note: str, refs: dict) -> int:
    from . import store
    v = store.save(name, spec, note, checked=False)   # (only numeric base keys change: a full validate is ~1 min)
    (store.HOME / name / "human_refs.json").write_text(json.dumps(refs, indent=1))
    return v


def _log_path(refs: dict, name: str) -> Path:
    from . import store
    return store.HOME / (refs.get("blockin") or {}).get("root", name) / "blockin_log.json"


def log(name: str) -> list:
    p = _log_path(_refs(name), name)
    return json.loads(p.read_text()) if p.exists() else []


def _adopt_log(src: str) -> list:
    """The history of a model made outside the tools: faces6's artist_log.json (artist.py step) if it has one."""
    from . import store
    p = store.HOME / src / "artist_log.json"
    out = [{"round": 0, "to": src, "start": {"adopted": src}}]
    if p.exists():
        old = json.loads(p.read_text())
        out = [{"round": 0, "to": old[0]["from"], "start": {"adopted": "artist.py (faces6)"}}] if old else out
        for i, e in enumerate(old):
            out.append({"round": i + 1, "from": e["from"], "to": e["to"], "moves": dict(e["moves"]), "c_norm": e.get("c_norm"),
                        "seen": "", "why": "(faces6 artist.py)"})
    return out


def _next_name(name: str) -> str:
    from . import store
    i = len(name)
    while i > 0 and name[i - 1].isdigit():
        i -= 1
    stem, num = name[:i], name[i:]
    n, w = (int(num), len(num)) if num else (0, 2)
    if not num:
        stem += "_"
    while True:
        n += 1
        cand = f"{stem}{n:0{w}d}"
        if not (store.HOME / cand / "spec.json").exists():
            return cand


def start(name: str, refs, sex=None, age: float | None = None, body: dict | None = None, gnm_base: float | None = None,
          ethnicity: str | None = None, cameras: str = "keep", replace: bool = False, expression: bool = False) -> dict:
    """The block-in's first model: the person's body (from the refs model, `body` merged over it), the head's local
    layers off, identity = GNM's sampler class mean for the sex (and ethnicity, if named), gnm_base by age; the
    references' fitted cameras (refs = a model with fitted references, or a views list: cameras fitted on this head).
    cameras="refit" refits a refs model's cameras on this head (camera only). expression=True fits each detector view's
    expression on the start head (see expression_step: on a class mean it may soak up identity; usually later)."""
    from . import humans, store
    if (store.HOME / name / "spec.json").exists() and not replace:
        raise ValueError(f"{name} exists: choose a new name (block-in models are new models) or replace=True")
    if isinstance(refs, str):
        src = store.load(refs)
        rj = _refs(refs)
        if (src.get("base") or {}).get("body", {}).get("source") != "human":
            raise ValueError(f"{refs}: not a one-mesh human (base.body.source 'human')")
        sp = copy.deepcopy(src)
        for k in ("hair", "cloth"):
            sp.pop(k, None)
        sp["base"]["body"].update(body or {})
        views = rj["views"]
        cams = rj["cameras"]
    else:
        views = refs
        b = dict(body or {})
        a = float(age if age is not None else b.pop("age", 30))
        sx = b.pop("sex", sex if sex is not None else 0.5)
        from .spec import empty_spec
        sp = {**empty_spec(), **humans.spec(age=a, sex=sx, source="human", **{k: v for k, v in b.items() if k in ("weight", "muscle", "height")})}
        cams = None
    bd, hd = sp["base"]["body"], sp["base"]["head"]
    if age is not None:
        bd["age"] = float(age)
    a = float(bd.get("age", 30))
    s = sex if sex is not None else bd.get("sex")
    if s is None:
        raise ValueError("block-in start: say the sex (sex='male' | 'female' | 0..1): the base is that sex's class mean")
    male = (s in ("male", "m", "man")) if isinstance(s, str) else float(s) >= 0.5
    for k in STRIP:
        hd.pop(k, None)
    # the rest mouth closed by GNM's own lower-face expression (base.lip_close_delta), not the seal: the seal's
    # membrane flattened the vermilion border (its turn 24 -> 11 deg on Tess) and moved the lips whole (gnmdetail2)
    for k in ("lip_seal", "mouth_gap"):
        hd.pop(k, None)
    hd["lip_close"] = True
    D = data()
    if ethnicity:
        en = [str(x) for x in D["eth_names"]]
        if ethnicity not in en:
            raise ValueError(f"ethnicity: one of {en} (GNM's sampler classes) or omit it")
        c = np.asarray(D["eth_means"][int(male), en.index(ethnicity)], float)
    else:
        c = np.asarray(D["m_m"] if male else D["m_f"], float)
    set_identity(sp, c)
    hd["gnm_base"] = float(default_gnm_base(a) if gnm_base is None else gnm_base)
    hd.setdefault("eye_radius", humans.eye_radius(a))   # an adult eyeball (12 mm), not GNM's eye x the head's scale
    rj = {"views": views, "cameras": cams}
    if cams is None or cameras == "refit":
        rj["cameras"] = fit_cameras(sp["base"], views)
    rj["blockin"] = {"root": name, "boxes": _boxes(sp["base"], rj)}
    if expression:
        rj["expressions"] = [fit_expression(sp["base"], v, c)["expression"] if abs(float(v.get("yaw", 0))) < 70 else {}
                             for v, c in zip(rj["views"], rj["cameras"])]
    _save(name, sp, f"block_in_start: {'male' if male else 'female'} class mean{' (' + ethnicity + ')' if ethnicity else ''}, "
          f"age {a:g}, gnm_base {hd['gnm_base']:.2f}", rj)
    entry = {"round": 0, "to": name, "start": {"refs": refs if isinstance(refs, str) else f"{len(views)} views",
             "sex": "male" if male else "female", "age": a, "gnm_base": hd["gnm_base"], "ethnicity": ethnicity,
             "cameras": "refit" if (cams is None or cameras == "refit") else "kept"},
             "c_norm": round(float(np.linalg.norm(c)), 3), "time": time.strftime("%Y-%m-%d %H:%M:%S")}
    _log_path(rj, name).write_text(json.dumps([entry], indent=1))
    return entry


def fit_cameras(base: dict, views: list, rj: dict | None = None) -> list:
    """Each picture's camera fitted on this head, the head held (humanfit_map's camera-only fit); with rj, each view's
    camera on the head as that picture shows it (its fitted expression)."""
    from . import humanfit_map
    if rj and any(rj.get("expressions") or []):
        return [humanfit_map.fit(view_base(base, rj, i), [v], free=())[1]["cameras"][0] for i, v in enumerate(views)]
    _, rep = humanfit_map.fit(base, views, free=())
    return rep["cameras"]


def _boxes(base: dict, rj: dict) -> list:
    """Each view's crop (picture pixels), from the START head: the same frame every round."""
    from . import humanfit
    L = humanfit.state(base)["L"]
    out = []
    for cam in rj["cameras"]:
        P = humanfit.project(cam, L)
        cc = 0.5 * (P.min(0) + P.max(0))
        side = 1.45 * float(np.max(P.max(0) - P.min(0)))
        out.append([cc[0] - side / 2, cc[1] - side * 0.56, cc[0] + side / 2, cc[1] + side * 0.44])
    return out


# ---------------------------------------------------------------- per-picture expression
# GNM's identity is the relaxed neutral; a picture shows the person WITH an expression (lt19's front: a slight smile:
# fuller lips, lifted corners, a cheek apple). Comparing the neutral clay with it leaks the smile into mouth / cheek
# identity steps. Each view may carry its own fitted expression (human_refs "expressions": one {GNM expression comp:
# value} per view, {} = neutral), applied in look / focus / the table / lid reads / camera refits, never to the model.
# Lower face only by default: with 6 eye-region comps per side lt19's fit dropped the upper lid from 0.75 to 0.36 iris
# radii (the detector's calibrated lid points disagree with the iris-radius lid read that lid_read matches: the comps
# fought the lid pose); EYE_COMPS is the opt-in (a picture that clearly squints)
EXPR_COMPS = {"lower_face_region": 20}
EYE_COMPS = {"left_eye_region": 6, "right_eye_region": 6}
EXPR_SD = {"lower_face_region": 0.8, "left_eye_region": 0.5, "right_eye_region": 0.5}


def view_expression(rj: dict, vi: int) -> dict:
    ex = rj.get("expressions") or []
    return dict(ex[vi] or {}) if vi < len(ex) else {}


def view_base(base: dict, rj: dict, vi: int) -> dict:
    """The base as that picture shows it: base.head.expression + the view's fitted expression (added)."""
    ex = view_expression(rj, vi)
    if not ex:
        return base
    b = copy.deepcopy(base)
    e = dict(b["head"].get("expression") or {})
    for k, v in ex.items():
        e[k] = float(e.get(k, 0.0)) + float(v)
    b["head"]["expression"] = e
    return b


def _per_view(base: dict, rj: dict, VI, make) -> dict:
    """{vi: make(view base)}, one build per distinct expression (views without one share the neutral)."""
    out, by = {}, {}
    for vi in VI:
        key = json.dumps(view_expression(rj, vi), sort_keys=True)
        if key not in by:
            by[key] = make(view_base(base, rj, vi))
        out[vi] = by[key]
    return out


def _expr_names(comps: dict | None = None) -> list:
    from . import base as basemod
    names = [str(n) for n in basemod._gnm_data()["expression_names"]]
    out = []
    for reg, n in (comps or EXPR_COMPS).items():
        out += [nm for nm in names if nm.rsplit("_", 1)[0] == reg][:int(n)]
    return out


def fit_expression(base: dict, view: dict, cam: dict, comps: dict | None = None, sd: dict | None = None,
                   iters: int = 3) -> dict:
    """One picture's expression on this head (identity and camera held): GNM expression comps (EXPR_COMPS, prior
    N(0, EXPR_SD per region)) by Gauss-Newton on the calibrated detector evidence (humanfit_map._evidence), the
    Jacobian by finite differences at the start (chord iterations: the response is near linear). ~(n + 4) head builds.
    Returns {"expression", "chi2": [before, after], "points", "norm"}."""
    from . import humanfit, humanfit_map as hm
    names = _expr_names(comps)
    sd = {**EXPR_SD, **(sd or {})}
    prec = np.array([1.0 / float(sd[n.rsplit("_", 1)[0]]) ** 2 for n in names])
    rj1 = {"expressions": [None]}

    def resid(e):
        rj1["expressions"][0] = {n: float(x) for n, x in zip(names, e) if x}
        st = humanfit.state(view_base(base, rj1, 0))
        ev = hm._evidence(st, hm._resolve(st, [view]))[0]
        mm = cam["t"][2] / cam["f"] * 1000
        return ((humanfit.project(cam, ev["X"]) - ev["uv"]) * (mm / ev["sig"])[:, None]).ravel()

    e = np.zeros(len(names))
    r = r_start = resid(e)
    h = 0.25
    J = np.stack([(resid(np.eye(len(names))[k] * h) - r) / h for k in range(len(names))], 1)
    A = J.T @ J + np.diag(prec)
    for _ in range(iters):
        de = np.linalg.solve(A, -(J.T @ r) - prec * e)
        e = e + de
        r = resid(e)
        if np.linalg.norm(de) < 0.02:
            break
    ex = {n: round(float(x), 4) for n, x in zip(names, e) if abs(x) >= 1e-3}
    return {"expression": ex, "chi2": [round(float(r_start @ r_start), 1), round(float(r @ r), 1)],
            "points": len(r) // 2, "norm": round(float(np.linalg.norm(e)), 3)}


def expression_step(src: str, out: str | None = None, views: list | None = None, clear: bool = False,
                    comps: dict | None = None, eyes: bool = False, seen: str = "", why: str = "") -> dict:
    """A block-in round that changes no shape: <out> = <src> with the views' expressions fitted on its head (default:
    every view with a detector, |yaw| < 70; a profile's few clicks can't separate expression from shape) or cleared.
    Fit it once the big forms are in (on the class mean it would soak up identity), refit after large identity moves.
    The report is step()'s (table before -> after)."""
    from . import store
    sp = copy.deepcopy(store.load(src))
    rj = copy.deepcopy(_refs(src))
    if "blockin" not in rj:
        raise ValueError(f"{src}: not a block-in model (block_in_start first)")
    n = len(rj["views"])
    VI = ([i for i in range(n) if abs(float(rj["views"][i].get("yaw", 0))) < 70] if views is None
          else [int(v) for v in views])
    ex = list(rj.get("expressions") or []) + [{}] * (n - len(rj.get("expressions") or []))
    fits = {}
    for vi in VI:
        if clear:
            ex[vi] = {}
            continue
        f = fit_expression(sp["base"], rj["views"][vi], rj["cameras"][vi], comps=comps or ({**EXPR_COMPS, **EYE_COMPS} if eyes else None))
        ex[vi], fits[vi] = f["expression"], f
    rj["expressions"] = ex
    out = out or _next_name(src)
    if (store.HOME / out / "spec.json").exists():
        raise ValueError(f"{out} exists: block-in steps write new models")
    t0 = table(src)
    _save(out, sp, f"block_in expression from {src}: views {VI}" + (" cleared" if clear else " fitted"), rj)
    t1 = table(out)
    lg = log(src)
    if lg and lg[-1].get("to") != src:
        lg[-1]["reverted"] = f"the next step went from {src}, not {lg[-1].get('to')}"
    c = identity(sp)
    entry = {"round": 1 + max([e.get("round", 0) for e in lg] or [0]), "from": src, "to": out, "moves": {},
             "expression": {str(vi): ("cleared" if clear else {"chi2": fits[vi]["chi2"], "norm": fits[vi]["norm"]})
                            for vi in VI},
             "seen": seen, "why": why or "per-picture expression (the identity unchanged)", "c_norm": round(float(np.linalg.norm(c)), 3),
             "read": {}, "coupled": [], "camera_moves": [], "passes": passes(t1), "time": time.strftime("%Y-%m-%d %H:%M:%S")}
    lg.append(entry)
    _log_path(rj, out).write_text(json.dumps(lg, indent=1))
    return {"entry": entry, "c0": entry["c_norm"], "big": [], "delta": table_delta(t0, t1), "table": t1,
            "before": passes(t0), "fits": fits}


def expression_text(rep: dict) -> str:
    s = []
    for vi, f in (rep.get("fits") or {}).items():
        top = sorted(f["expression"].items(), key=lambda t: -abs(t[1]))[:6]
        s.append(f"view {vi}: expression fitted, chi2 {f['chi2'][0]} -> {f['chi2'][1]} over {f['points']} points, |e| "
                 f"{f['norm']} ({', '.join(f'{k} {v:+.2f}' for k, v in top)})")
    return "\n".join(s + [step_text(rep)])


def step(src: str, moves: dict, out: str | None = None, seen: str = "", why: str = "",
         cameras: list | None = None, feature: str | None = None, _identity=None, _head_set: dict | None = None) -> dict:
    """<out> = <src> moved: directions add (amount x direction), base keys and lids are SET. Logged with what was seen
    and why. cameras = view indices to refit on the result head (camera only). Returns the report (see step_text)."""
    from . import store
    if not moves and not cameras and _identity is None and not _head_set:
        raise ValueError("block_in_step: no moves. Vocabulary:\n" + vocabulary())
    sp = copy.deepcopy(store.load(src))
    rj = _refs(src)
    c0 = identity(sp)
    c = c0.copy()
    big, designed = [], []
    sculpts = {}
    for k, v in (moves or {}).items():
        v = float(v)
        if k in BODY_KEYS:
            sp["base"]["body"][k] = v
        elif k in HEAD_KEYS:
            sp["base"]["head"][HEAD_KEYS[k]] = v
        elif k == "head_scale":
            sp["base"].setdefault("style", {}).setdefault("human", {})["head_size"] = v
        elif k in POSE_KEYS:
            sp["base"]["head"].setdefault("pose", {})[k] = v
        elif k.startswith("shape:"):   # DESIGNED soft-tissue ops (age): not data; flagged in the log and reply
            from . import faceslide, headage
            nm = k[6:]
            if nm not in SHAPE_MOVES:
                raise ValueError(f"shape: one of {', '.join(SHAPE_MOVES)} (designed ops: faceslide's age sliders in "
                                 "their units, headage's ops in m / share)")
            if nm in faceslide.AGE_SLIDERS:
                sp["base"]["head"].setdefault("sliders", {})[nm] = v
            else:
                assert nm in headage.KEYS
                sp["base"]["head"].setdefault("shape", {})[nm] = v
            designed.append(k)
        elif k.startswith("local:"):
            from . import faceslide
            nm = k[6:]
            if nm not in faceslide.UNITS:
                raise ValueError(f"local: no slider {nm!r} (faceslide: {', '.join(sorted(faceslide.UNITS))})")
            sp["base"]["head"].setdefault("sliders", {})[nm] = v
            if nm in LOCAL_SD and abs(v) > 2.5 * LOCAL_SD[nm]:
                big.append(f"{k} (population sd {LOCAL_SD[nm]})")
        elif k.startswith(("sculpt:", "relief:")):
            from . import gnm_controls as gcm
            sc = gcm.sculpt(**gcm.parse_sculpt(k))
            c = c + v * sc["dc"]
            sculpts[k] = {"mm": v, "cost": round(abs(v) * sc["cost"], 2), "released": sc["released"],
                          "outside_mm": round(abs(v) * sc["outside_mm"], 3)}
            if abs(v) * sc["cost"] > 2.0:
                big.append(f"{k} (|dc| {abs(v) * sc['cost']:.1f})")
        else:
            c = c + v * direction(k)
            if abs(v) > 1.0:
                big.append(k)
    if _identity is not None:   # (solved steps: blockin_eyes.eye_step) the identity given, head keys set / cleared
        c = np.asarray(_identity, float)
    for k, v in (_head_set or {}).items():
        if v is None:
            sp["base"]["head"].pop(k, None)
        else:
            sp["base"]["head"][k] = v
    set_identity(sp, c)
    out = out or _next_name(src)
    if (store.HOME / out / "spec.json").exists():
        raise ValueError(f"{out} exists: block-in steps write new models (revert = step again from an earlier one)")
    rj = copy.deepcopy(rj)
    adopted = "blockin" not in rj   # a model made outside the tools (an older loop, a fit): this step roots a new log
    if adopted:
        rj["blockin"] = {"root": out, "boxes": _boxes(store.load(src)["base"], rj)}
    cam_moves = []
    if "head_scale" in (moves or {}):
        # the head scales about the NECK: the face rises / drops, which a refit would answer by moving the camera back
        # (distance trades with size: lt19's 1.06 came back as the same pixels). Each camera follows the face's
        # landmark centre instead (centre shifted with it: the same point at the same pixel, the size change visible)
        from . import humanfit
        d = humanfit.state(sp["base"])["L"][:68].mean(0) - humanfit.state(store.load(src)["base"])["L"][:68].mean(0)
        for i, cam in enumerate(rj["cameras"]):
            if not cameras or i not in [int(j) for j in cameras]:
                cam["centre"] = (np.asarray(cam["centre"], float) + d).tolist()
        cam_moves.append(f"cameras follow the face centre ({1000 * float(np.linalg.norm(d)):.1f} mm)")
    if cameras:
        from . import humanfit
        new = fit_cameras(sp["base"], rj["views"], rj)
        for i in cameras:
            a, b = rj["cameras"][int(i)], new[int(i)]
            Rd = humanfit._cam_rot(a).T @ humanfit._cam_rot(b)
            ang = float(np.degrees(np.arccos(np.clip((np.trace(Rd) - 1) / 2, -1, 1))))
            cam_moves.append(f"view {i}: turned {ang:.1f} deg, distance x{b['t'][2] / a['t'][2]:.3f}, focal x{b['f'] / a['f']:.3f}")
            rj["cameras"][int(i)] = b
    _save(out, sp, f"block_in_step from {src}: {json.dumps(moves)}" + (f" cameras {cameras}" if cameras else ""), rj)
    r0, r1 = _macro_read(c0), _macro_read(c)
    names = {k.rstrip("!") for k in (moves or {})}
    read = {k: [round(r0[k], 2), round(r1[k], 2)] for k in names if k in r1}
    moved = [kv for kv in sorted(((k, r1[k] - r0[k]) for k in r1 if k not in names), key=lambda t: -abs(t[1]))[:5]
             if abs(kv[1]) >= 0.05]
    t0, t1 = table(src), table(out)
    lg = _adopt_log(src) if adopted else log(src)
    rnd = 1 + max([e.get("round", 0) for e in lg] or [0])
    if lg and lg[-1].get("to") != src:
        lg[-1]["reverted"] = f"the next step went from {src}, not {lg[-1].get('to')}"
    if feature and feature not in FEATURES:
        raise ValueError(f"feature: one of {', '.join(FEATURES)}")
    entry = {"round": rnd, "from": src, "to": out, "moves": moves, "cameras": cameras, "camera_moves": cam_moves,
             "feature": feature, "seen": seen, "why": why, **({"designed": designed} if designed else {}),
             **({"sculpt": sculpts} if sculpts else {}),
             "c_norm": round(float(np.linalg.norm(c)), 3), "read": read,
             "coupled": [[k, round(float(x), 2)] for k, x in moved],
             "passes": passes(t1), "time": time.strftime("%Y-%m-%d %H:%M:%S")}
    lg.append(entry)
    _log_path(rj, out).write_text(json.dumps(lg, indent=1))
    if feature:
        ft0, ft1 = feature_table(src, feature), feature_table(out, feature)
        entry["feature_passes"] = [passes(ft0)[feature], passes(ft1)[feature]]
        _log_path(rj, out).write_text(json.dumps(lg, indent=1))
    return {"entry": entry, "c0": float(np.linalg.norm(c0)), "big": big, "delta": table_delta(t0, t1),
            "table": t1, "before": passes(t0)}


def step_text(rep: dict) -> str:
    e = rep["entry"]
    s = [f"{e['to']} (round {e['round']}, from {e['from']}): |c| {rep['c0']:.2f} -> {e['c_norm']:.2f}"]
    if e["read"]:
        s.append("moved (macro sd, before -> after): " + ", ".join(f"{k} {a:+.2f} -> {b:+.2f}" for k, (a, b) in e["read"].items()))
    if e["coupled"]:
        s.append("coupled (largest other macro changes, sd): " + ", ".join(f"{k} {v:+.2f}" for k, v in e["coupled"]))
    for k, v in (e.get("sculpt") or {}).items():
        s.append(f"{k} {v['mm']:+g} mm: |dc| {v['cost']:.2f} (macros held"
                 + (f"; let go as the target itself: {', '.join(v['released'])}" if v["released"] else "")
                 + f"; the face's skin beyond 6 mm of the zone moves {v['outside_mm']:.2f} mm rms)")
    if e.get("camera_moves"):
        s.append("cameras refitted (landmarks only: a camera fit does not see the outline): " + "; ".join(e["camera_moves"]))
    if rep["big"]:
        s.append(f"WARNING: {', '.join(rep['big'])}: more than 1 sd (a local: 2.5 of its population sd) in one step: the "
                 "method takes small steps (0.3-0.7)")
    if e.get("designed"):
        s.append(f"DESIGNED (not data): {', '.join(e['designed'])}: hand-authored soft-tissue ops (sizes chosen by eye, "
                 "not learnt from people); judge them zoomed in under the raking light against the pictures")
    if e.get("feature_passes"):
        s.append(f"ZOOM IN, {e['feature']}'s own checklist rows: {e['feature_passes'][0]} -> {e['feature_passes'][1]} pass")
    s.append("ZOOM OUT, targets before -> after: " + ", ".join(f"{g} {rep['before'].get(g, '-')} -> {p}" for g, p in e["passes"].items()))
    if rep["delta"]:
        s.append("items that changed (model - photo, tol):")
        s += ["  " + x for x in rep["delta"]]
    s.append(f"keep it only if the whole face reads closer AND no target went out; else step again from {e['from']} "
             "(this model stays as the record).")
    return "\n".join(s)


# ---------------------------------------------------------------- the target table

def _spec_hash(name: str) -> str:
    from . import store
    sp = store.load(name)
    rj = _refs(name)
    return hashlib.sha1(json.dumps([sp["base"], rj["cameras"]] + ([rj["expressions"]] if any(rj.get("expressions") or []) else []),
                               sort_keys=True).encode()).hexdigest()[:16]


def rows(name: str) -> list:
    """Every likeness checklist row (photo vs model through the model's fitted cameras): [{id, stage, view, unit,
    photo, model, tol}] with numbers on both sides; cached in the model's directory by its base + cameras."""
    from . import likeness as lk, store
    h = _spec_hash(name)
    p = store.HOME / name / "blockin_rows.json"
    if p.exists():
        d = json.loads(p.read_text())
        if d.get("hash") == h:
            return d["rows"]
    out = []
    base, rj = store.load(name)["base"], _refs(name)
    meshes = None
    if any(rj.get("expressions") or []):   # each picture against the head with ITS expression
        mv = _per_view(base, rj, range(len(rj["views"])), lk.model_mesh)
        meshes = [mv[i] for i in range(len(rj["views"]))]
    for r in lk.compare(name, base, mesh=meshes)["rows"]:
        a, b = r.get("photo"), r.get("model")
        if not isinstance(a, (int, float)) or not isinstance(b, (int, float)) or not np.isfinite(a) or not np.isfinite(b):
            continue
        out.append({"id": r["id"], "stage": r.get("stage"), "view": r.get("view", r.get("vi")), "vi": str(r.get("vi")),
                    "unit": r.get("unit"), "photo": round(float(a), 3), "model": round(float(b), 3),
                    "tol": round(float(r.get("tol") or 0), 3)})
    p.write_text(json.dumps({"hash": h, "rows": out}, indent=1))
    return out


def _row(r: dict) -> dict:
    d = r["model"] - r["photo"]
    row = {k: r[k] for k in ("id", "view", "unit", "photo", "model", "tol")}
    row.update({"diff": round(d, 3), "ok": bool(r["tol"] and abs(d) <= r["tol"])})
    if r["id"] in FLAGGED:
        row["flag"] = FLAGGED[r["id"]]
    elif r["unit"] == "%" and r["model"] == 0.0 and r["photo"] != 0.0:
        # (lt19: radix / dorsum width, nasolabial fold, under-eye read exactly 0.00 on every clay: no reading there)
        row["flag"] = "the clay reader returned nothing (0.00 exactly): shown, not counted"
    return row


def table(name: str) -> dict:
    """{group: [{id, view, unit, photo, model, diff, tol, ok, flag?}]}: the five target groups (likeness items)."""
    R = rows(name)
    out = {}
    for g, ids in GROUPS.items():
        out[g] = [_row(r) for i in ids for r in sorted((r for r in R if r["id"] == i), key=lambda r: r["vi"])]
    return out


def feature_table(name: str, feature: str) -> dict:
    """The feature's own checklist rows (every likeness item of its stages), as one table group."""
    st, extra = FEATURES[feature]["stages"], FEATURES[feature].get("items", ())
    return {feature: [_row(r) for r in rows(name) if r["stage"] in st or r["id"] in extra]}


def passes(t: dict) -> dict:
    return {g: f"{sum(r['ok'] for r in rows if 'flag' not in r)}/{sum('flag' not in r for r in rows)}" for g, rows in t.items()}


def table_text(t: dict) -> str:
    s = []
    for g, rows in t.items():
        s.append(f"== {g} {passes(t)[g]}")
        for r in rows:
            mark = "flag" if "flag" in r else ("ok" if r["ok"] else "MISS")
            pct = f" ({100 * r['diff'] / r['photo']:+.0f}%)" if r["unit"] == "mm" and r["photo"] else ""
            s.append(f"  {r['id']:20s} {str(r['view']):13s} photo {r['photo']:8.2f}  model {r['model']:8.2f}  "
                     f"diff {r['diff']:+7.2f}{pct} tol {r['tol']:.2f} {r['unit'] or ''} {mark}")
    fl = {r["id"]: r["flag"] for rows in t.values() for r in rows if "flag" in r}
    if fl:
        s.append("flag = shown, not counted: " + "; ".join(f"{i}: {fl[i]}" for i in sorted(fl)))
    mm = [r["diff"] / r["photo"] for rows in t.values() for r in rows if r["unit"] == "mm" and r["photo"] > 20 and "flag" not in r]
    if len(mm) >= 5 and (np.median(mm) < -0.03 or np.median(mm) > 0.03) and np.mean(np.sign(mm) == np.sign(np.median(mm))) > 0.75:
        s.append(f"SIZE: the lengths over 20 mm are {100 * np.median(mm):+.0f}% (median) and mostly the same sign: a UNIFORM "
                 "scale, not shape. Check the camera (block_in_step cameras=[...]) and head_scale before identity steps.")
    return "\n".join(s)


def table_delta(t0: dict, t1: dict) -> list:
    out = []
    for g, rows in t1.items():
        old = {(r["id"], str(r["view"])): r for r in t0.get(g, [])}
        for r in rows:
            o = old.get((r["id"], str(r["view"])))
            if o is None:
                continue
            ch = "" if o["ok"] == r["ok"] else (" NOW OK" if r["ok"] else " WENT OUT")
            if ch and abs(r["diff"] - o["diff"]) < 0.15 * max(r["tol"], 1e-9):   # (a hair across the line: noise)
                ch += " (at the edge: the change is under 0.15 tol)"
            if ch or abs(r["diff"] - o["diff"]) > 0.5 * max(r["tol"], 1e-9):
                out.append(f"{r['id']} {r['view']}: {o['diff']:+.2f} -> {r['diff']:+.2f} (tol {r['tol']:.2f}){ch}"
                           + (" [flag]" if "flag" in r else ""))
    return out


# ---------------------------------------------------------------- clay presentation

def haircap(mesh: dict, st: dict) -> np.ndarray:
    """Per-vertex colour: skin, and a neutral dark cap over GNM's scalp (outside its hockey_mask face region, not the
    ears, above the ears' bottom): bald clay reads male."""
    from . import base as basemod, likeness, onemesh
    g = basemod._gnm_data()
    gid = np.asarray(onemesh.asset()["gnm_id"], int)[np.asarray(st["tpl"]["fid"])]
    ok = gid >= 0
    hm_ = np.zeros(len(gid))
    hm_[ok] = np.asarray(g["groups"]["hockey_mask"], float)[gid[ok]]
    ear = np.zeros(len(gid))
    ear[ok] = np.asarray(g["groups"]["ears"], float)[gid[ok]]
    L = st["L"]
    zcut = 0.5 * (L[1, 2] + L[15, 2])
    w = ok * (1 - hm_) * (1 - ear) * np.clip((mesh["V"][:, 2] - zcut) / 0.01, 0, 1)
    return (1 - w)[:, None] * likeness.SKIN + w[:, None] * HAIR_RGB


def eye_presentation(mesh: dict, iris=(128, 112, 82)) -> dict:
    """A presentable eye for whole-face reads (dark iris caps dominated every clay read): a light iris with a darker
    limbal ring and pupil, and a lash line (the skin hugging the upper half of each eyeball, darkened)."""
    from . import likeness
    out = []
    fwd = np.asarray(mesh["state"]["head"].get("forward", [0, -1, 0]), float)
    fwd = fwd / np.linalg.norm(fwd)
    for V, F_, _ in mesh["eyes"]:
        c = V.mean(0)
        cs = ((V - c) / np.linalg.norm(V - c, axis=1, keepdims=True)) @ fwd
        col = np.where(cs[:, None] > 0.97, [20, 16, 14], np.where(cs[:, None] > 0.885, list(iris),
                       np.where(cs[:, None] > 0.86, [60, 50, 40], [238, 234, 228]))).astype(float)
        out.append((V, F_, col))
    mesh["eyes"] = out
    C = np.asarray(mesh["C"] if mesh.get("C") is not None else np.tile(likeness.SKIN, (len(mesh["V"]), 1)), float).copy()
    for V, _, _ in out:
        c = V.mean(0)
        r = float(np.median(np.linalg.norm(V - c, axis=1)))
        dist = np.linalg.norm(mesh["V"] - c, axis=1) - r
        near = (dist < 0.0015) & (mesh["V"][:, 2] > c[2] - 0.0005) & ((mesh["V"] - c) @ fwd > 0.3 * r)
        C[near] = C[near] * 0.35
    mesh["C"] = C
    return mesh


def draw_photo_brows(im, P, to):
    """The PERSON's brows on the clay: the photo detector's brow band (upper and lower contour) as a filled shape,
    through `to` (picture pixels -> this image's). A drawn line on GNM's brow landmarks sat low and heavy."""
    from PIL import ImageDraw
    d = ImageDraw.Draw(im)
    P = np.asarray(P, float)[:, :2]
    for up, lo in (BROWS_R, BROWS_L):
        d.polygon([tuple(p) for p in to(np.r_[P[up], P[lo][::-1]])], fill=(70, 52, 40))
    return im


BROW_RGB = np.array([70.0, 52.0, 40.0])


def brow_source(mesh: dict, rj: dict) -> dict | None:
    """The person's brows SEATED ON THE SURFACE (Joe: 2D-pasted brows stuck out past the 3/4 silhouette and hooked over
    the bridge in profile): the front picture's detector brow band as a mask in that picture, plus the model's depth
    seen through the front camera. seat_brows then paints, in ANY view, the skin points that project into the band from
    the front AND are visible from the front: they follow the surface, foreshorten and are occluded like paint. Cached
    on the mesh dict. None when the front picture's detector misses (draw_brows' landmark line is the fallback)."""
    from PIL import Image, ImageDraw, ImageFilter
    from . import humanfit, likeness
    if "_brows" in mesh:
        return mesh["_brows"]
    vf = _front(rj)
    v, cam = rj["views"][vf], rj["cameras"][vf]
    img = Image.open(v["image"]).convert("RGB")
    P = detect_view(img, v)
    out = None
    if P is not None:
        P = np.asarray(P, float)[:, :2]
        # the band rasterised SUPERSAMPLED over its own box (a full-figure picture's brows are a few pixels tall:
        # nearest samples of a picture-resolution mask came out as stair steps), sampled bilinearly
        polys = [np.r_[P[up], P[lo][::-1]] for up, lo in (BROWS_R, BROWS_L)]
        allp = np.concatenate(polys)
        pad = max(6.0, 0.05 * float(allp[:, 0].max() - allp[:, 0].min()))   # (room for the tails past the band)
        o = allp.min(0) - pad
        ss = 8.0
        size = tuple(int(x) for x in np.ceil((allp.max(0) + pad - o) * ss))
        m = Image.new("L", size, 0)
        d = ImageDraw.Draw(m)
        for poly in polys:
            d.polygon([tuple(q) for q in (poly - o) * ss], fill=255)
        hb = brow_hair_band(img, polys, o, cam, mesh)   # (None for light, fine brows: the detector band, below)
        # the brows' own colour: the picture's pixels under the hair mask (or the band), their darkest quarter (a fair
        # person's light-brown brows painted in the fixed dark brown read as heavy bars)
        Wb, Hb = int(np.ceil(allp.max(0)[0] + pad - o[0])), int(np.ceil(allp.max(0)[1] + pad - o[1]))
        crop = np.asarray(img.crop((int(o[0]), int(o[1]), int(o[0]) + Wb, int(o[1]) + Hb)), float)
        msk = (np.asarray(hb) > 0) if hb is not None else (np.asarray(m.resize((Wb, Hb), Image.BILINEAR)) > 127)
        rgb = BROW_RGB
        if msk.shape == crop.shape[:2] and msk.sum() > 20:
            px_ = crop[msk]
            lum_ = px_.mean(1)
            rgb = np.median(px_[lum_ <= np.percentile(lum_, 25)], 0)
        if hb is not None:
            m = hb.resize(size, Image.BILINEAR)
        L2 = humanfit.project(cam, mesh["state"]["L"])
        c = 0.5 * (L2.min(0) + L2.max(0))
        side = 1.5 * float(np.max(L2.max(0) - L2.min(0)))
        box = (c[0] - side / 2, c[1] - side / 2, c[0] + side / 2, c[1] + side / 2)
        _, k, ps = likeness.render(mesh, cam, box, px=1200, brows=False, passes=True)
        mmpx = likeness._mm_per_px(cam, mesh["state"]["L"][27:48])
        soft = m.filter(ImageFilter.GaussianBlur(max(0.5 / mmpx, 0.4) * ss))   # (a ~0.5 mm soft edge)
        out = {"cam": cam, "rgb": rgb, "mask": np.asarray(soft, float) / 255.0, "mo": o, "ss": ss, "zb": ps["zb"], "part": ps["part"],
               "box": box, "k": k}
    mesh["_brows"] = out
    return out


def brow_hair_band(img, polys, o, cam, mesh, grow_mm: float = 2.0, dark: float = 0.66, density: bool = True,
                   tail_mm: float = 4.0):
    """The brows as the HAIR the picture shows, not the detector's band: MediaPipe's brow contour is a smooth arch of
    a fixed thickness (lt19's straight, dense brows came out thinner and more arched). Inside the detector band grown by
    grow_mm, the pixels darker than `dark` x the surrounding skin; the largest pieces per side kept. A mask over the
    band's own box (origin o, picture pixels) or None when it finds too little. density: the mask is the hair's
    density (its darkness against the skin, 0..1)."""
    from PIL import Image, ImageDraw, ImageFilter
    from scipy import ndimage
    from . import likeness
    allp = np.concatenate(polys)
    hi = allp.max(0) + (allp.min(0) - o)   # (the same margin as the caller gave below the band)
    W, H = int(np.ceil(hi[0] - o[0])), int(np.ceil(hi[1] - o[1]))
    if W < 4 or H < 4:
        return None
    mmpx = likeness._mm_per_px(cam, mesh["state"]["L"][27:48])
    band = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(band)
    for poly in polys:
        d.polygon([tuple(q) for q in (poly - o)], fill=255)
    g = max(1, int(round(grow_mm / mmpx)))
    crop = np.asarray(img.convert("L").crop((int(o[0]), int(o[1]), int(o[0]) + W, int(o[1]) + H)), float)
    xs = np.arange(W)[None, :]
    keep = np.zeros((H, W), bool)
    skin_lvl = np.full((H, W), float(np.median(crop)))
    inner_all = 0
    for poly in polys:   # per side: its own skin level (one side of a face is often lit brighter)
        q = poly - o
        pm = Image.new("L", (W, H), 0)
        ImageDraw.Draw(pm).polygon([tuple(p_) for p_ in q], fill=255)
        inner = np.asarray(pm) > 0
        grown = np.asarray(pm.filter(ImageFilter.MaxFilter(2 * g + 1))) > 0
        # not past the band's own ends (side hair at the temples is dark too)
        # not past the inner end; past the OUTER end by tail_mm (MediaPipe's brow stops short of the tail: lt19's
        # profile showed a short patch)
        outer_left = q[:, 0].mean() < (allp[:, 0].mean() - o[0])
        lo_, hi_ = (tail_mm, 0.5) if outer_left else (0.5, tail_mm)
        grown &= (xs >= q[:, 0].min() - lo_ / mmpx) & (xs <= q[:, 0].max() + hi_ / mmpx)
        ring = grown & ~inner
        if ring.sum() < 20 or inner.sum() < 20:
            return None
        inner_all += int(inner.sum())
        skin = float(np.percentile(crop[ring], 75))
        skin_lvl[grown] = skin
        hair = ndimage.binary_opening(grown & (crop < dark * skin), iterations=1)
        lab, n = ndimage.label(hair)
        if n == 0:
            continue
        ov = ndimage.sum(inner, lab, index=np.arange(1, n + 1))
        if ov.max() <= 0:
            continue
        for i in np.flatnonzero(ov >= 0.25 * ov.max()):   # the piece(s) overlapping the detector band most
            keep |= lab == i + 1
    if keep.sum() < 0.5 * inner_all:   # too little hair found (light brows, a painting): the detector band
        return None
    keep = ndimage.binary_closing(keep, iterations=2)
    if not density:
        return Image.fromarray((keep * 255).astype(np.uint8))
    # DENSITY, not a flat shape (lt19b: a binary mask painted at one strength drew the tails as heavy as the dense inner
    # ends): how far each kept pixel is below the skin level, so sparse tails come out light and thin, the dense heads
    # dark
    dens = np.where(keep, np.clip((skin_lvl - crop) / np.maximum(skin_lvl * (1 - 0.35), 1.0), 0, 1), 0.0)
    dens = ndimage.gaussian_filter(dens, 0.6)
    dn = np.clip(dens / max(np.percentile(dens[keep], 98), 1e-3), 0, 1) ** 1.4   # (p90 saturated: one flat band)
    im = Image.fromarray((dn * 255).astype(np.uint8))
    return im


def seat_brows(im, ps, cam, box, k, B: dict, strength: float = 0.9):
    """Paint the seated brows on a render (its passes ps, through cam / box / k): each skin pixel back-projected to
    the surface, seen from the front camera; inside the front band and visible there (depth within 2.5 mm) = brow."""
    from PIL import Image
    from . import humanfit, likeness_shape as ls
    a = np.asarray(im.convert("RGB"), float).copy()
    rr, cc = np.nonzero(ps["part"] == 0)
    if not len(rr):
        return im
    uv = np.c_[cc / k + box[0], rr / k + box[1]]
    X = ls.unproject(cam, uv, ps["zb"][rr, cc])
    from scipy.ndimage import map_coordinates
    q = humanfit.project(B["cam"], X)
    qm = (q - B["mo"]) * B["ss"]
    al = map_coordinates(B["mask"], [qm[:, 1], qm[:, 0]], order=1, mode="constant", cval=0.0)
    W, H = B["cam"]["size"]
    ok = (q[:, 0] >= 0) & (q[:, 0] < W) & (q[:, 1] >= 0) & (q[:, 1] < H)
    zi = np.round((q - [B["box"][0], B["box"][1]]) * B["k"]).astype(int)
    zh, zw = B["zb"].shape
    inz = ok & (zi[:, 0] >= 0) & (zi[:, 0] < zw) & (zi[:, 1] >= 0) & (zi[:, 1] < zh)
    Rf = humanfit._cam_rot(B["cam"])
    depth = ((X - np.asarray(B["cam"]["centre"], float)) @ Rf.T + np.asarray(B["cam"]["t"], float))[:, 2]
    vis = np.zeros(len(rr), bool)
    vis[inz] = (B["part"][zi[inz, 1], zi[inz, 0]] == 0) & (depth[inz] < B["zb"][zi[inz, 1], zi[inz, 0]] + 0.0025)
    al = al * vis * strength
    a[rr, cc] = a[rr, cc] * (1 - al[:, None]) + np.asarray(B.get("rgb", BROW_RGB), float) * al[:, None]
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def brows_on(im, ps, mesh, rj, cam, box, k):
    """The brows on a clay crop: seated from the front picture where it sees them, GNM's landmark line otherwise."""
    B = brow_source(mesh, rj)
    return seat_brows(im, ps, cam, box, k, B) if B is not None else draw_brows(im.convert("RGB"), mesh, cam, box, k)


def draw_brows(im, mesh, cam, box, k, mm: float = 2.0):
    """Brows as a line through the model's brow landmarks (views the detector can't read)."""
    from PIL import ImageDraw
    from . import humanfit, likeness
    L = humanfit.project(cam, mesh["L"])
    d = ImageDraw.Draw(im)
    wpx = max(1, int(round(mm / likeness._mm_per_px(cam, mesh["L"]) * k)))
    for a, b in ((17, 22), (22, 27)):
        d.line([((L[i, 0] - box[0]) * k, (L[i, 1] - box[1]) * k) for i in range(a, b)], fill=(70, 52, 40), width=wpx,
               joint="curve")
    return im


LIP_TINT = np.array([0.98, 0.74, 0.74])   # the clay's vermilion, x skin: presentation only (no reader sees it)


def lip_tint(mesh: dict, st: dict, share: float = 0.8) -> None:
    """The vermilion tinted on the clay (GNM's upper_lip / lower_lip groups): untinted clay lips barely read as lips."""
    from . import base as basemod, onemesh
    g = basemod._gnm_data()
    gid = np.asarray(onemesh.asset()["gnm_id"], int)[np.asarray(st["tpl"]["fid"])]
    ok = gid >= 0
    w = np.zeros(len(gid))
    for grp in ("upper_lip", "lower_lip"):
        w[ok] = np.maximum(w[ok], np.asarray(g["groups"][grp], float)[gid[ok]])
    C = np.asarray(mesh["C"], float)
    a = (share * np.clip(w, 0, 1))[:, None]
    mesh["C"] = C * (1 - a) + C * LIP_TINT * a


_IRIS: dict = {}


def photo_iris(rj: dict | None):
    """The person's iris colour from the front picture (MediaPipe's iris ring: the median of the annulus between the
    pupil and the limbus, the brightest tenth (catchlights) left out); None without a front detection."""
    if not rj:
        return None
    from PIL import Image
    vf = _front(rj)
    v = rj["views"][vf]
    key = v["image"]
    if key not in _IRIS:
        img = Image.open(v["image"]).convert("RGB")
        P = detect_view(img, v)
        col = None
        if P is not None and len(P) >= 478:
            P = np.asarray(P, float)[:, :2]
            a = np.asarray(img, float)
            px = []
            for c_, ring in ((468, range(469, 473)), (473, range(474, 478))):
                c = P[c_]
                r = float(np.mean([np.linalg.norm(P[i] - c) for i in ring]))
                yy, xx = np.mgrid[int(c[1] - r):int(c[1] + r) + 1, int(c[0] - r):int(c[0] + r) + 1]
                d = np.hypot(xx - c[0], yy - c[1])
                m = (d > 0.45 * r) & (d < 0.85 * r)
                px.append(a[yy[m], xx[m]])
            q = np.concatenate(px)
            lum = q.mean(1)
            q = q[lum <= np.percentile(lum, 90)]
            col = tuple(float(x) for x in np.median(q, 0))
        _IRIS[key] = col
    return _IRIS[key]


def presented_mesh(base: dict, eyes: bool = True, rj: dict | None = None) -> dict:
    """The clay as presented for whole-face reads: hair cap, tinted lips, a presentable eye (the person's iris colour
    from the front picture when rj is given)."""
    from . import humanfit, likeness
    st = humanfit.state(base)
    mesh = likeness.model_mesh_from_state(st)
    mesh["C"] = haircap(mesh, st)
    lip_tint(mesh, st)
    if eyes:
        ir = photo_iris(rj)
        eye_presentation(mesh, iris=ir) if ir else eye_presentation(mesh)
    return mesh


def lit_render(mesh: dict, cam: dict, img, box=None, px=None, soft: float = 8.0):
    """The model at the picture's pixels (box), lit like the photo: the light fitted on the face's skin (two passes:
    c0 + w.n, then the ambient's AO share and the direct's scale with AO and a soft cast shadow)."""
    from PIL import Image
    from . import likeness, likeness_shape as ls
    W, H = cam["size"]
    box = box or (0.0, 0.0, float(W), float(H))
    px = px or int(max(box[2] - box[0], box[3] - box[1]))
    _, k, ps = likeness.render(mesh, cam, box, px=px, brows=False, passes=True)
    Hh, Ww = ps["zb"].shape
    crop = img.crop(tuple(int(round(v)) for v in box)).resize((Ww, Hh), Image.LANCZOS)
    Y = ls._lin(crop)
    P = mesh.get("_photo_P")
    side = likeness.Side(np.asarray(P, float)[:, :2], None) if P is not None else None
    mask = ps["part"] == 0
    if side is not None:
        try:
            mmpx = likeness._mm_per_px(cam, mesh["L"][27:36])
            mask = ls.skin_mask(side, (Hh, Ww), lambda Q: (np.asarray(Q, float) - [box[0], box[1]]) * k, k / mmpx) & mask
        except Exception:  # noqa: BLE001  (a crop the skin mask can't place: the whole skin)
            pass
    elif box[2] - box[0] < 0.6 * W and box[3] - box[1] < 0.6 * H:
        # a feature's crop of a clicked profile: the light is fitted on the whole face (inside a crop of one eye the
        # fit saw lashes, brow hair and wall, and lit the clay to white), then the crop is rendered with it
        _, lt, _ = lit_render(mesh, cam, img, soft=soft)
        im, _, ps = likeness.render(mesh, cam, box, px=px, brows=False, passes=True, ao=True, shadow=soft, light=lt)
        return im, lt, ps
    else:
        # no detector on the picture (a clicked profile): the light is fitted inside the face's landmark hull only;
        # the whole head took in the hair over the skull and the fit lit the face to white
        from scipy.spatial import ConvexHull
        from PIL import ImageDraw
        from . import humanfit
        Q = (humanfit.project(cam, np.asarray(mesh["L"], float)[:68]) - [box[0], box[1]]) * k
        try:
            hv = Q[ConvexHull(Q).vertices]
            hm = Image.new("L", (Ww, Hh), 0)
            ImageDraw.Draw(hm).polygon([tuple(p) for p in hv], fill=1)
            mask = mask & (np.asarray(hm) > 0)
        except Exception:  # noqa: BLE001  (degenerate hull: the whole skin)
            pass
    if mask.sum() < 200:
        mask = ps["part"] == 0
    c0, w, _ = ls.fit_light(Y, ps["nrm"], mask)
    lt = (c0, w, float(np.median(Y[mask])), 1.0)
    if LIGHT == "sh":   # ambient + key + fill / bounce: the c0 + w.n light put the nose's base at black (Garrett:
        # the band under the nose 0.19-0.34 of the tip's light, his picture 0.6-0.7; SH 0.66)
        _, _, p1 = likeness.render(mesh, cam, box, px=px, brows=False, passes=True, ao=True)
        m1 = mask & (p1["part"] == 0) & (np.linalg.norm(p1["nrm"], axis=-1) > 0.5)
        X = likeness.sh9(p1["nrm"][m1]) * p1["ao"][m1][:, None]
        use = np.ones(len(X), bool)
        a = np.zeros(9)
        for _ in range(4):
            if use.sum() < 50:
                break
            a = np.linalg.lstsq(X[use], Y[m1][use], rcond=None)[0]
            r = Y[m1] - X @ a
            use = np.abs(r) < 2.5 * r[use].std()
        if np.all(np.isfinite(a)) and use.sum() >= 50:
            lt = (c0, w, float(np.median(Y[mask])), 1.0, a)
            im, k, ps = likeness.render(mesh, cam, box, px=px, brows=False, passes=True, ao=True, light=lt)
            return im, lt, ps
    _, _, p2 = likeness.render(mesh, cam, box, px=px, brows=False, passes=True, ao=True, shadow=soft, light=lt)
    dn = p2["nrm"] @ np.asarray(w, float)
    m2 = mask & (p2["part"] == 0)
    X = np.c_[np.ones(m2.sum()), p2["ao"][m2], (np.maximum(dn, 0) * p2["lit"])[m2], np.minimum(dn, 0)[m2]]
    A, B, C = np.linalg.lstsq(X, Y[m2], rcond=None)[0][:3]
    c0n = float(A + B)
    aw = float(np.clip(B / c0n, 0.0, 1.0)) if c0n > 1e-6 else 0.0
    # an ambient floor: a painted picture's light is not one light, and the fit put its shadow side at black (Garrett's
    # 3/4 portrait: half the clay face lost); real skin in shadow keeps ~a third of its lit level
    w2 = np.asarray(w, float) * max(float(C), 0.0)
    lt2 = (c0n, w2, lt[2], aw)
    lt = lt2 if np.all(np.isfinite(lt2[1])) and np.isfinite(c0n) else lt
    im, k, ps = likeness.render(mesh, cam, box, px=px, brows=False, passes=True, ao=True, shadow=soft, light=lt)
    return im, lt, ps


def photo_lighting(name: str, template: dict, vi: int | None = None) -> dict:
    """A DRESSED render's lighting (Blender suns, the stage's `template` dict: {"lights": [key, fill], "world", ...})
    re-aimed and re-balanced to the picture's own light, as the clay sheets are (lit_render's SH fit on the face's
    skin): the key along the fitted light's first-order direction, key : fill (a frontal fill from the camera, no
    shadow) from its ambient vs directional parts (the fitted c0 + w.n: ambient c0, key |w|), the face's
    front kept as bright as the template lights it. jw2: the stage's fixed key 42 deg up put the sides of a flat-lit
    phone photo's face in shadow and the dressed head read narrower and harder than the photo and the clay. Returns a
    new dict (+ "fitted": {dir, elevation_deg, key, ambient})."""
    from PIL import Image
    from . import humanfit, store
    rj = _refs(name)
    vi = _front(rj) if vi is None else vi
    v, cam = rj["views"][vi], rj["cameras"][vi]
    img = Image.open(v["image"]).convert("RGB")
    mesh = presented_mesh(view_base(store.load(name)["base"], rj, vi), rj=rj)
    mesh["_photo_P"] = detect_view(img, v)
    _, lt, _ = lit_render(mesh, cam, img)
    R = humanfit._cam_rot(cam)
    # the first pass's c0 + w.n fit (camera-frame normals): w = the directional part, c0 = the ambient (the SH
    # coefficients, fitted with AO multiplied in, gave no stable direction: Tess's key came out from below)
    c0, w = float(lt[0]), np.asarray(lt[1], float)
    I = float(np.linalg.norm(w))
    A = max(c0, 0.1 * I)
    d = R.T @ (w / max(I, 1e-9))                               # toward the light, world
    to_cam = R.T @ np.array([0.0, 0.0, -1.0])                 # the face's front, toward the camera
    out = copy.deepcopy(template)
    key, fill_ = out["lights"][0], (out["lights"][1] if len(out["lights"]) > 1 else None)
    k0 = np.asarray(key["dir"], float) / np.linalg.norm(key["dir"])
    e_front = float(key["energy"]) * max(float(k0 @ to_cam), 0.0) + (float(fill_["energy"]) if fill_ else 0.0)
    K = e_front / max(I * max(float(d @ to_cam), 0.0) + A, 1e-9)
    key["dir"] = [round(float(x), 4) for x in d]
    key["energy"] = round(K * I, 3)
    if fill_ is None:
        fill_ = {"energy": 0.0, "angle": 40, "shadow": False, "specular": 0.0, "color": [1, 1, 1]}
        out["lights"].append(fill_)
    fill_["dir"] = [round(float(x), 4) for x in to_cam]
    fill_["energy"] = round(K * A, 3)
    out["fitted"] = {"dir": key["dir"], "elevation_deg": round(float(np.degrees(np.arcsin(np.clip(d[2], -1, 1)))), 1),
                     "key": round(I, 4), "ambient": round(A, 4)}
    return out


def fill(im, ps, share: float = None):
    """DISPLAY only (the fitted light stays as fitted for anything measured): the shadow side lifted to a fill of
    FILL x the lit skin's median, a soft knee (v' = sqrt(v^2 + f^2)): a painted picture's light put half of Garrett's
    3/4 clay at black, which no one can judge."""
    from PIL import Image
    a = np.asarray(im.convert("RGB"), float)
    on = ps["part"] >= 0
    if not on.any():
        return im.convert("RGB")
    f = (FILL if share is None else share) * float(np.percentile(a[ps["part"] == 0].mean(-1), 75)) if (ps["part"] == 0).any() else 0.0
    b = a.copy()
    b[on] = np.sqrt(a[on] ** 2 + f ** 2)
    return Image.fromarray(np.clip(b, 0, 255).astype(np.uint8))


def detect_view(img, view: dict):
    """MediaPipe on a reference picture; where the face is small in a big picture (a full-figure concept), on a crop
    around the clicked points."""
    from . import likeness
    P = likeness.detect([img])[0]
    if P is not None:
        return P
    pts = np.array([p for p in (view.get("points") or {}).values()], float)
    if len(pts) < 3:
        return None
    lo, hi = pts.min(0), pts.max(0)
    c, s = 0.5 * (lo + hi), 1.8 * float(np.max(hi - lo))
    return likeness.detect_region(img, (c[0] - s / 2, c[1] - s / 2, c[0] + s / 2, c[1] + s / 2))


def profile_contour(view: dict, step: int = 3) -> np.ndarray:
    """A true profile's front contour where the skin meets a plain background (the photo's own pixels), from just above
    the nasion to under the chin; hair / lashes crossing are skipped, the throat cut off. A right-facing picture (yaw > 0)
    is read mirrored and its contour mirrored back."""
    from PIL import Image
    a = np.asarray(Image.open(view["image"]).convert("RGB"), float)
    pts = dict(view.get("points") or {})
    right = float(view.get("yaw", 0)) > 0
    if right:   # (the scan below runs from the image's left: mirror the picture and the clicked points)
        a = a[:, ::-1]
        pts = {k: [a.shape[1] - 1 - float(p[0]), float(p[1])] for k, p in pts.items()}
    eo = pts.get("eye_outer.L", pts.get("eye_outer.R"))
    yb, yc = float(pts["nose_bridge"][1]), float(pts["chin"][1])
    y0, y1 = int(yb - 0.12 * (yc - yb)), int(yc + 0.22 * (yc - yb))
    # the background per row (a profile in front of a wall above and a sofa below has two): a band just in front of the most forward clicked point (a wall's light falls off across
    # the picture: its far edge is another colour), else the row's far end
    xs = [float(p[0]) for p in pts.values()]
    b1 = int(min(xs) - 0.02 * a.shape[1]) if xs else 15
    b0 = max(0, b1 - int(0.04 * a.shape[1]))
    bg = np.median(a[:, b0:max(b1, b0 + 15)], 1)[:, None, :]
    lum = a.mean(-1)
    # differs from the row's background in colour OR in hue alone: a warm wall can be as bright and as red as skin
    # (a tan wall behind a fair face: |rgb| differs by ~35, the chromaticity (rgb / sum) by ~0.07, the wall's own ~0.005)
    from scipy.ndimage import uniform_filter
    ch = uniform_filter(a / np.maximum(a.sum(-1, keepdims=True), 1.0), (5, 5, 1))   # (sensor noise in the hue)
    chb = bg / np.maximum(bg.sum(-1, keepdims=True), 1.0)
    fg = ((np.abs(a - bg).sum(-1) > 40) | (np.abs(ch - chb).sum(-1) > 0.05)) & (lum > 0.55 * np.median(lum[int(yb):int(yc), :]))
    # and skin-like: a textured background (a leather sofa's highlights) differs from its row's left end too; skin is
    # told by its warmth ((r - b) / sum) against a patch of cheek in front of the ear (between nose base and eye)
    if "nose_base" in pts and eo is not None:
        cx, cy = (np.asarray(pts["nose_base"], float) + 2.0 * np.asarray(eo, float)) / 3.0
        r_ = max(4, int(0.04 * (yc - yb)))
        patch = a[int(cy) - r_:int(cy) + r_, int(cx) - r_:int(cx) + r_].reshape(-1, 3)
        if len(patch):
            warm = (a[..., 0] - a[..., 2]) / np.maximum(a.sum(-1), 1.0)
            pw = (patch[:, 0] - patch[:, 2]) / np.maximum(patch.sum(-1), 1.0)
            fg &= (warm > 0.4 * float(np.median(pw))) & (lum > 0.4 * float(np.median(patch.mean(-1))))
    out = []
    for y in range(max(y0, 0), min(y1, a.shape[0]), step):
        run = np.convolve(fg[y].astype(float), np.ones(6), "valid") >= 6
        if not run.any():
            continue
        x = float(np.argmax(run))
        if out and y > yc and x - out[-1][0] > 12.0 * step / 6:
            break
        out.append([x, float(y)])
    out = np.array(out)
    if len(out) >= 5:   # (single rows where lashes / a shadowed fold break the run: a 5-row median)
        from scipy.ndimage import median_filter
        out[:, 0] = median_filter(out[:, 0], 5, mode="nearest")
    if right and len(out):
        out[:, 0] = a.shape[1] - 1 - out[:, 0]
    return out


def _eye_anchor(view, Pd, Lm):
    """Registration: the photo's and the model's eye corners + nasion (a profile: nasion + outer eye corner)."""
    if abs(float(view.get("yaw", 0))) < 70:
        if Pd is not None:
            a_ph = np.asarray(Pd, float)[[33, 133, 263, 362, 168], :2].mean(0)
        else:
            pts = view.get("points") or {}
            got = [pts[k] for k in ("lm36", "lm39", "lm42", "lm45", "lm27") if k in pts]
            if not got:
                return None, None
            a_ph = np.mean(got, 0)
        return np.asarray(a_ph, float), Lm[[36, 39, 42, 45, 27]].mean(0)
    pts = view["points"]
    if "eye_outer.L" in pts:   # (the side the picture shows: her left = lm45, her right = lm36)
        return np.mean([pts["nose_bridge"], pts["eye_outer.L"]], 0), Lm[[27, 45]].mean(0)
    return np.mean([pts["nose_bridge"], pts["eye_outer.R"]], 0), Lm[[27, 36]].mean(0)


def look(name: str, out: str, views: list | None = None, T: int = 330, before: str | None = None) -> dict:
    """The block-in sheet: per view photo | clay under the photo's fitted light (hair cap, the person's brows, a
    presentable eye) | 50 % overlay | outline difference (photo red, clay green) | squinted photo | squinted clay,
    registered at the EYES + nasion (a 2D shift: a tracing over the photo, never on the outline it should judge).
    before = another model (a step's source): per view a second row photo | before | after | the change (|after -
    before| x4) | squint before | squint after: a half-sd step is hard to see side by side with the photo alone.
    Returns {"out", "views": [{"view", "shift_px"}]}."""
    from PIL import Image, ImageDraw, ImageFilter
    from . import humanfit, likeness, store
    rj = _refs(name)
    base = store.load(name)["base"]
    VI = list(range(len(rj["views"]))) if views is None else [int(v) for v in views]
    meshes = _per_view(base, rj, VI, lambda b: presented_mesh(b, rj=rj))   # (each picture's expression, if fitted)
    boxes = (rj.get("blockin") or {}).get("boxes") or _boxes(base, rj)
    cols = ["photo", f"{name} (photo's light)", "50% overlay", "outline: photo red / clay green", "squint photo", "squint clay"]
    meshes_b = _per_view(store.load(before)["base"], rj, VI, lambda b: presented_mesh(b, rj=rj)) if before else None
    per = 2 if before else 1
    sheet = Image.new("RGB", (T * len(cols), (T + 18) * len(VI) * per + 18), "white")
    dr = ImageDraw.Draw(sheet)
    for j, lab in enumerate(cols):
        dr.text((j * T + 4, 2), lab, fill=(0, 0, 0))
    info = []
    for i, vi in enumerate(VI):
        v, cam = rj["views"][vi], rj["cameras"][vi]
        mesh, mesh_b = meshes[vi], (meshes_b[vi] if meshes_b else None)
        st = mesh["state"]
        img = Image.open(v["image"]).convert("RGB")
        box = tuple(boxes[vi])
        side = box[2] - box[0]
        px = 2 * T
        k = px / side
        front = abs(float(v.get("yaw", 0))) < 70
        Pd = detect_view(img, v) if front else None
        mesh["_photo_P"] = Pd
        Lm = humanfit.project(cam, st["L"])
        a_ph, a_md = _eye_anchor(v, Pd, Lm)
        sh = np.zeros(2) if a_ph is None else a_ph - a_md
        pbox = (box[0] + sh[0], box[1] + sh[1], box[2] + sh[0], box[3] + sh[1])
        ph = img.crop(tuple(int(round(b)) for b in pbox)).resize((px, px), Image.LANCZOS)
        cl, _, ps = lit_render(mesh, cam, img, box=box, px=px)
        cl = brows_on(fill(cl, ps), ps, mesh, rj, cam, box, k)
        to = lambda Q: [((q[0] - box[0]) * k, (q[1] - box[1]) * k) for q in Q]  # noqa: E731
        to_ph = lambda Q: [((q[0] - pbox[0]) * k, (q[1] - pbox[1]) * k) for q in Q]  # noqa: E731
        ov = Image.blend(ph, cl, 0.5)
        ol = ph.copy().convert("L").convert("RGB")
        d = ImageDraw.Draw(ol)
        if front:
            if Pd is not None:
                Pp = np.asarray(Pd, float)[likeness.OVAL, :2]
                d.line(to_ph(np.r_[Pp, Pp[:1]]), fill=(230, 30, 30), width=3)
            full, _, pf = lit_render(mesh, cam, img)
            Pm_ = detect_view(fill(full, pf), v)
            if Pm_ is not None:
                Pm = np.asarray(Pm_, float)[likeness.OVAL, :2]
                d.line(to(np.r_[Pm, Pm[:1]]), fill=(30, 200, 30), width=3)
        else:
            try:
                d.line(to_ph(profile_contour(v)), fill=(230, 30, 30), width=3)
            except Exception:  # noqa: BLE001  (a profile without a plain background: the clay's edge alone)
                pass
            e = np.asarray(Image.fromarray((ps["part"] >= 0).astype(np.uint8) * 255).filter(ImageFilter.FIND_EDGES)) > 0
            e[:2], e[-2:], e[:, :2], e[:, -2:] = False, False, False, False   # (the crop's own border is no edge)
            olA = np.asarray(ol).copy()
            olA[e] = (30, 200, 30)
            ol = Image.fromarray(olA)
        sg = float(SQUINT_MM / likeness._mm_per_px(cam, mesh["L"][27:48]) * k)
        sq = lambda im: im.convert("L").filter(ImageFilter.GaussianBlur(sg)).convert("RGB")  # noqa: E731
        y = 18 + i * per * (T + 18)
        for j, im in enumerate((ph, cl, ov, ol, sq(ph), sq(cl))):
            sheet.paste(im.resize((T, T), Image.LANCZOS), (j * T, y))
        xn = len(view_expression(rj, vi))
        dr.text((4, y + T + 2), f"view {vi} (yaw {float(v.get('yaw', 0)):g}): {Path(v['image']).name}; registered at "
                f"the eyes, shift {sh[0]:+.0f}, {sh[1]:+.0f} px" + (f"; clay with the picture's expression ({xn} comps)"
                                                                    if xn else ""), fill=(0, 0, 0))
        if mesh_b is not None:
            mesh_b["_photo_P"] = Pd
            cb_, _, psb = lit_render(mesh_b, cam, img, box=box, px=px)
            cb = brows_on(fill(cb_, psb), psb, mesh_b, rj, cam, box, k)
            dif = np.abs(np.asarray(cl.convert("L"), float) - np.asarray(cb.convert("L"), float))
            dif = Image.fromarray(np.clip(255 - 4 * dif, 0, 255).astype(np.uint8)).convert("RGB")
            y2 = y + T + 18
            for j, im in enumerate((ph, cb, cl, dif, sq(cb), sq(cl))):
                sheet.paste(im.resize((T, T), Image.LANCZOS), (j * T, y2))
            dr.text((4, y2 + T + 2), f"view {vi}: photo | BEFORE {before} | AFTER {name} | the change (|after - before| x4, "
                    "dark = moved) | squint before | squint after", fill=(0, 0, 0))
        info.append({"view": vi, "shift_px": [round(float(sh[0]), 1), round(float(sh[1]), 1)]})
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return {"out": str(out), "views": info}


# ---------------------------------------------------------------- focus: one feature, zoomed in

# Joe (2026-10-10): "having the reviewer focus more on each feature, then zoom back out after making each change".
# Per feature: the model's 68 landmarks that frame and register it, MediaPipe's matching points on the picture (the
# same anatomical points: feature-local registration, a 2D shift), MediaPipe contours drawn for the local outline
# difference, and the checklist stages whose rows are its table.
FEATURES = {
    "eyes": {"lm": list(range(17, 27)) + list(range(36, 48)), "pairs": [(36, 33), (39, 133), (42, 362), (45, 263)],
             "lines": [[33, 246, 161, 160, 159, 158, 157, 173, 133, 155, 154, 153, 145, 144, 163, 7, 33],
                       [263, 466, 388, 387, 386, 385, 384, 398, 362, 382, 381, 380, 374, 373, 390, 249, 263],
                       [70, 63, 105, 66, 107], [300, 293, 334, 296, 336], [46, 53, 52, 65, 55], [276, 283, 282, 295, 285]],
             "stages": ("eyes", "brows"), "items": ("under_eye", "brow_ridge", "prof_brow_ridge"), "squint_mm": 3.0, "pad": 1.12},
    "nose": {"lm": list(range(27, 36)) + [39, 42], "pairs": [(27, 168), (30, 4), (31, 98), (33, 2), (35, 327)],
             "lines": [[168, 6, 197, 195, 5, 4], [64, 98, 97, 2, 326, 327, 294], [48, 115, 220, 45, 4, 275, 440, 344, 278]],
             "stages": ("nose",), "squint_mm": 3.0},
    "mouth": {"lm": list(range(48, 68)) + [33], "pairs": [(48, 61), (54, 291), (51, 0), (57, 17), (62, 13), (66, 14)],
              "lines": [[61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291, 375, 321, 405, 314, 17, 84, 181, 91, 146, 61],
                        [78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308, 324, 318, 402, 317, 14, 87, 178, 88, 95, 78]],
              "stages": ("mouth",), "items": ("nasolabial_fold",), "squint_mm": 3.0},
    "chin_jaw": {"lm": list(range(3, 14)) + [57], "pairs": [(8, 152), (57, 17), (6, 176), (10, 400)],
                 "lines": [[132, 58, 172, 136, 150, 149, 176, 148, 152, 377, 400, 378, 379, 365, 397, 288, 361]],
                 "stages": ("chin_jaw",), "items": ("width_jaw", "width_chin", "jaw_taper", "jaw_gonial", "jaw_ramus",
                                                    "jaw_border", "corner_jaw", "jaw_neck_step"), "squint_mm": 5.0},
    "cheeks": {"lm": [1, 2, 3, 13, 14, 15, 31, 35, 36, 45, 48, 54], "pairs": [(36, 33), (45, 263), (31, 98), (35, 327)],
               "lines": [[127, 234, 93, 132, 58], [356, 454, 323, 361, 288]],
               "stages": (), "items": ("width_cheekbone", "corner_cheekbone", "cheek_hollow", "nasolabial_fold",
                                       "under_eye", "width_temple", "corner_temple"), "squint_mm": 6.0},
    "ears": {"lm": [0, 1, 2, 15, 16], "pairs": [], "lines": [], "stages": ("ears",), "squint_mm": 4.0},
}
RAKE = np.array([-0.85, -0.35, -0.25])   # camera frame: a grazing key from the picture's upper left (forms, not tone)
RAKE = RAKE / np.linalg.norm(RAKE)


def _feature_box(feature, L2, P_ear=None):
    """A square crop (picture pixels) around the feature's projected landmarks (the ear: its projected vertices)."""
    Q = P_ear if feature == "ears" and P_ear is not None and len(P_ear) else L2[FEATURES[feature]["lm"]]
    lo, hi = Q.min(0), Q.max(0)
    c = 0.5 * (lo + hi)
    # (a profile foreshortens the eye corners' span to a few mm: the nasion-chin length doesn't, ~0.75 x the span)
    io = max(float(np.linalg.norm(L2[45] - L2[36])), 0.75 * float(np.linalg.norm(L2[27] - L2[8])))
    side = max(FEATURES[feature].get("pad", 1.5) * float(np.max(hi - lo)), 0.55 * io)
    return (c[0] - side / 2, c[1] - side / 2, c[0] + side / 2, c[1] + side / 2)


def focus(name: str, feature: str, out: str, views: list | None = None, T: int = 300, before: str | None = None) -> dict:
    """ZOOM IN: one feature per view, at native resolution: photo crop | clay crop (the photo's light, filled) | 50 %
    overlay | the local outline difference (the detector's feature contours: photo red, clay green) | clay under a
    raking light | squinted photo | squinted clay. Registered at the feature's OWN landmarks (a 2D shift), so an
    offset elsewhere doesn't hide its shape. before = another model: a second row photo | before | after | change |
    raking before | raking after. Views where the feature isn't seen (the ear in front) are left out."""
    from PIL import Image, ImageDraw, ImageFilter
    from . import humanfit, likeness, store
    if feature not in FEATURES:
        raise ValueError(f"focus: one of {', '.join(FEATURES)}")
    F = FEATURES[feature]
    rj = _refs(name)
    VI = list(range(len(rj["views"]))) if views is None else [int(v) for v in views]
    if feature == "ears":
        VI = [vi for vi in VI if abs(float(rj["views"][vi].get("yaw", 0))) >= 20]
    if not VI:
        raise ValueError(f"focus {feature}: no view shows it (the ear needs a turned view)")
    meshes = _per_view(store.load(name)["base"], rj, VI, lambda b: presented_mesh(b, rj=rj))
    meshes_b = _per_view(store.load(before)["base"], rj, VI, lambda b: presented_mesh(b, rj=rj)) if before else None
    per = 2 if before else 1
    cols = ["photo", "clay (photo's light)", "50% overlay", "outline: photo red / clay green", "raking light",
            "squint photo", "squint clay"]
    sheet = Image.new("RGB", (T * len(cols), (T + 18) * len(VI) * per + 18), "white")
    dr = ImageDraw.Draw(sheet)
    for j, lab in enumerate(cols):
        dr.text((j * T + 4, 2), lab, fill=(0, 0, 0))
    info = []
    for i, vi in enumerate(VI):
        v, cam = rj["views"][vi], rj["cameras"][vi]
        mesh, mesh_b = meshes[vi], (meshes_b[vi] if meshes_b else None)
        st = mesh["state"]
        img = Image.open(v["image"]).convert("RGB")
        L2 = humanfit.project(cam, st["L"])
        Pe = humanfit.project(cam, mesh["V"][mesh["ears"]]) if feature == "ears" and mesh.get("ears") is not None else None
        if Pe is not None:   # (the ear nearer the camera: its vertices on the picture's near side)
            ex = mesh["V"][mesh["ears"]][:, 0]
            near = ex > 0 if float(v.get("yaw", 0)) < 0 else ex < 0
            Pe = Pe[near]
        box = _feature_box(feature, L2, Pe)
        side = box[2] - box[0]
        px = 2 * T
        k = px / side
        front = abs(float(v.get("yaw", 0))) < 70
        Pd = detect_view(img, v) if front else None
        mesh["_photo_P"] = Pd
        pr = [(a, b) for a, b in F["pairs"]] if Pd is not None else []
        clicked = []   # (a turned / profile view: the view's own clicked points that belong to the feature)
        for nm, uv in (v.get("points") or {}).items():
            try:
                ix = humanfit.point_index(nm)
            except Exception:  # noqa: BLE001
                continue
            if ix in F["lm"] or (feature == "nose" and ix in (27, 30, 33)) or (feature == "mouth" and 48 <= ix < 68):
                clicked.append((ix, np.asarray(uv, float)))
        if pr:
            sh = np.mean([np.asarray(Pd[b][:2], float) - L2[a] for a, b in pr], 0)
            how = "the feature's own landmarks"
        elif clicked:
            sh = np.mean([uv - L2[ix] for ix, uv in clicked], 0)
            how = f"the feature's clicked points ({len(clicked)})"
        else:
            a_ph, a_md = _eye_anchor(v, Pd, L2)
            sh = np.zeros(2) if a_ph is None else a_ph - a_md
            how = "the eyes (no feature points on this view)"
        pbox = (box[0] + sh[0], box[1] + sh[1], box[2] + sh[0], box[3] + sh[1])
        ph = img.crop(tuple(int(round(b)) for b in pbox)).resize((px, px), Image.LANCZOS)
        cl_, _, ps = lit_render(mesh, cam, img, box=box, px=px)
        cl = brows_on(fill(cl_, ps), ps, mesh, rj, cam, box, k)
        to = lambda Q: [((q[0] - box[0]) * k, (q[1] - box[1]) * k) for q in Q]  # noqa: E731
        to_ph = lambda Q: [((q[0] - pbox[0]) * k, (q[1] - pbox[1]) * k) for q in Q]  # noqa: E731
        # (from the side the face looks to: a right-facing profile's front is on the picture's right)
        rk_dir = RAKE * [-1.0, 1.0, 1.0] if float(v.get("yaw", 0)) >= 70 else RAKE
        rake = lambda m: fill(*likeness.render(m, cam, box, px=px, brows=False, passes=True, ao=True, shadow=4.0,  # noqa: E731
                                                light=(0.3, rk_dir, 1.0, 0.0))[::2], share=0.3)
        rk = rake(mesh)
        ov = Image.blend(ph, cl, 0.5)
        ol = ph.copy().convert("L").convert("RGB")
        d = ImageDraw.Draw(ol)
        if front and F["lines"]:
            full, _, pf = lit_render(mesh, cam, img)
            Pm = detect_view(fill(full, pf), v)
            for ln in F["lines"]:
                if Pd is not None:
                    d.line(to_ph(np.asarray(Pd, float)[ln, :2]), fill=(230, 30, 30), width=2)
                if Pm is not None:   # (the clay's contour in its own crop: the photo's crop carries the registration)
                    d.line(to(np.asarray(Pm, float)[ln, :2]), fill=(30, 200, 30), width=2)
        else:
            if not front:
                try:
                    d.line(to_ph(profile_contour(v)), fill=(230, 30, 30), width=2)
                except Exception:  # noqa: BLE001
                    pass
            e = np.asarray(Image.fromarray((ps["part"] >= 0).astype(np.uint8) * 255).filter(ImageFilter.FIND_EDGES)) > 0
            e[:2], e[-2:], e[:, :2], e[:, -2:] = False, False, False, False   # (the crop's own border is no edge)
            olA = np.asarray(ol).copy()
            olA[e] = (30, 200, 30)
            ol = Image.fromarray(olA)
        sg = float(F["squint_mm"] / likeness._mm_per_px(cam, mesh["L"][27:48]) * k)
        sq = lambda im: im.convert("L").filter(ImageFilter.GaussianBlur(sg)).convert("RGB")  # noqa: E731
        y = 18 + i * per * (T + 18)
        for j, im in enumerate((ph, cl, ov, ol, rk, sq(ph), sq(cl))):
            sheet.paste(im.resize((T, T), Image.LANCZOS), (j * T, y))
        mm = likeness._mm_per_px(cam, mesh["L"][27:48])
        dr.text((4, y + T + 2), f"{feature}, view {vi} (yaw {float(v.get('yaw', 0)):g}): registered at {how}, shift "
                f"{sh[0]:+.0f}, {sh[1]:+.0f} px; crop {side * mm:.0f} mm", fill=(0, 0, 0))
        if mesh_b is not None:
            mesh_b["_photo_P"] = Pd
            cb_, _, psb = lit_render(mesh_b, cam, img, box=box, px=px)
            cb = brows_on(fill(cb_, psb), psb, mesh_b, rj, cam, box, k)
            dif = np.abs(np.asarray(cl.convert("L"), float) - np.asarray(cb.convert("L"), float))
            dif = Image.fromarray(np.clip(255 - 4 * dif, 0, 255).astype(np.uint8)).convert("RGB")
            y2 = y + T + 18
            for j, im in enumerate((ph, cb, cl, dif, rake(mesh_b), rk)):
                sheet.paste(im.resize((T, T), Image.LANCZOS), (j * T, y2))
            dr.text((4, y2 + T + 2), f"photo | BEFORE {before} | AFTER {name} | change x4 | raking before | raking after",
                    fill=(0, 0, 0))
        info.append({"view": vi, "shift_px": [round(float(sh[0]), 1), round(float(sh[1]), 1)], "registered": how})
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return {"out": str(out), "views": info}


def note(name: str, read: str, keep: bool | None = None) -> dict:
    """ZOOM OUT read of a step's result, logged on the step that made `name` (its whole-face verdict): keep / not."""
    rj = _refs(name)
    p = _log_path(rj, name)
    lg = json.loads(p.read_text()) if p.exists() else []
    e = next((x for x in reversed(lg) if x.get("to") == name), None)
    if e is None:
        raise ValueError(f"{name}: no block-in step made it")
    e["zoom_out"] = read
    if keep is not None:
        e["kept"] = bool(keep)
    p.write_text(json.dumps(lg, indent=1))
    return e


# ---------------------------------------------------------------- lids by measure

def _iris_radius_px(P, rim, c):
    return float(np.mean(np.linalg.norm(P[rim] - P[c], axis=1)))


def lid_photo(img, view: dict | None = None) -> dict | None:
    """The photo's lid margins against the iris (MediaPipe iris 468 / 473 and radius, upper lid 159 / 386, lower
    145 / 374), in iris radii from the iris centre (MRD1 / MRD2 style, scale-free), and the opening's aspect."""
    P = detect_view(img, view or {})
    if P is None:
        return None
    P = np.asarray(P, float)[:, :2]
    if len(P) < 478:
        return None
    out = {}
    for s, (c, rim, up, lo, a, b) in {"R": (468, [469, 470, 471, 472], 159, 145, 33, 133),
                                      "L": (473, [474, 475, 476, 477], 386, 374, 263, 362)}.items():
        r = _iris_radius_px(P, rim, c)
        out[s] = {"upper": float((P[c, 1] - P[up, 1]) / r), "lower": float((P[lo, 1] - P[c, 1]) / r),
                  "aspect": float(np.linalg.norm(P[a] - P[b]) / max(P[lo, 1] - P[up, 1], 1e-6))}
    return out


def lid_model(base: dict, cam: dict) -> dict:
    """The model's lid margins read the same way on its front render: the visible eyeball (render part 1) in the column
    through the iris centre (the eyeball's forward pole), in the drawn iris cap's projected radius."""
    from . import humanfit, likeness
    st = humanfit.state(base)
    mesh = likeness.model_mesh_from_state(st)
    P = humanfit.project(cam, st["L"])
    c = 0.5 * (P.min(0) + P.max(0))
    s = 1.4 * float(np.max(P.max(0) - P.min(0)))
    box = (c[0] - s / 2, c[1] - s / 2, c[0] + s / 2, c[1] + s / 2)
    _, k, ps = likeness.render(mesh, cam, box, px=1400, brows=False, passes=True)
    fwd = np.asarray(st["head"].get("forward", [0, -1, 0]), float)
    r = float(st["head"].get("eye_r", 0.012)) * 0.985
    out = {}
    for ce in st["head"]["eyes"]:
        ce = np.asarray(ce, float)
        pole = humanfit.project(cam, (ce + r * fwd)[None])[0]
        u = np.cross(fwd, [0, 0, 1.0])
        u /= np.linalg.norm(u)
        ring = [ce + r * (0.86 * fwd + 0.51 * (np.cos(t) * u + np.sin(t) * np.array([0, 0, 1.0])))
                for t in np.linspace(0, 2 * np.pi, 16, endpoint=False)]
        R_ = float(np.mean(np.linalg.norm(humanfit.project(cam, np.array(ring)) - pole, axis=1))) * k
        x, y = (pole[0] - box[0]) * k, (pole[1] - box[1]) * k
        xi = int(round(x))
        if not (0 <= xi < ps["part"].shape[1]):
            continue
        col = np.flatnonzero(ps["part"][:, xi] == 1)
        col = col[np.abs(col - y) < 4 * R_]
        if len(col) == 0:
            continue
        a, b = (42, 45) if ce[0] > 0 else (36, 39)   # the eye's corners: the model's own landmarks, as the photo's
        wpx = float(np.linalg.norm(P[a] - P[b])) * k
        out["L" if ce[0] > 0 else "R"] = {"upper": float((y - col.min()) / R_), "lower": float((col.max() - y) / R_),
                                          "aspect": wpx / max(float(col.max() - col.min()), 1.0)}
    return out


def _front(rj: dict) -> int:
    ys = [abs(float(v.get("yaw", 0))) for v in rj["views"]]
    return int(np.argmin(ys))


def lid_read(name: str) -> dict:
    """{"photo": {R/L: {upper, lower, aspect}}, "model": {...}, "pose": base.head.pose} on the front picture."""
    from PIL import Image
    from . import store
    rj = _refs(name)
    vi = _front(rj)
    v = rj["views"][vi]
    base = store.load(name)["base"]
    return {"view": vi, "photo": lid_photo(Image.open(v["image"]).convert("RGB"), v),
            "model": lid_model(view_base(base, rj, vi), rj["cameras"][vi]), "pose": dict(base["head"].get("pose") or {}),
            "expression": bool(view_expression(rj, vi))}


def lid_text(r: dict) -> str:
    s = [f"lid margins vs the iris (in iris radii from its centre; front view {r['view']}): upper (MRD1-like), lower "
         "(MRD2-like), aspect = opening width / height"]
    for side in ("R", "L"):
        p = (r["photo"] or {}).get(side)
        m = (r["model"] or {}).get(side)
        f = lambda d: "-" if d is None else f"upper {d['upper']:.2f} lower {d['lower']:.2f} aspect {d['aspect']:.2f}"  # noqa: E731
        s.append(f"  {side}: photo {f(p)} | model {f(m)}")
    s.append(f"  pose now: {r['pose'] or '{}'} (lid_upper / lid_lower, m: -0.001 = that lid 1 mm up)"
             + ("; model read WITH the picture's fitted expression" if r.get("expression") else ""))
    if r["photo"] is None:
        s.append("  (the detector found no face on the front picture: no photo read)")
    return "\n".join(s)


def lid_match(name: str, out: str | None = None, seen: str = "") -> dict:
    """Lids by measure: lid_upper / lid_lower set so the model's margins (mean of both eyes) equal the photo's: two
    secant steps each (the read is ~linear in the pose), written as a block-in step."""
    from . import store
    r = lid_read(name)
    if not r["photo"]:
        raise ValueError("lid_match: no photo lid read (the detector missed the front picture)")
    tgt = {k: float(np.mean([r["photo"][s][k] for s in r["photo"]])) for k in ("upper", "lower")}
    rj = _refs(name)
    cam = rj["cameras"][r["view"]]
    base = copy.deepcopy(store.load(name)["base"])
    pose = base["head"].setdefault("pose", {})

    def read(p):
        base["head"]["pose"] = {**pose, **p}
        m = lid_model(view_base(base, rj, r["view"]), cam)   # (the picture's expression on top, if fitted)
        return {k: float(np.mean([m[s][k] for s in m])) for k in ("upper", "lower")}
    p = {"lid_upper": float(pose.get("lid_upper", 0.0)), "lid_lower": float(pose.get("lid_lower", 0.0))}
    sgn = {"lid_upper": ("upper", -1.0), "lid_lower": ("lower", 1.0)}   # lid_upper - = up: the upper margin grows
    cur = read(p)
    for key, (m, s) in sgn.items():
        for _ in range(2):
            h = 0.0005
            q = {**p, key: p[key] + s * h}
            alt = read(q)
            slope = (alt[m] - cur[m]) / h
            if abs(slope) < 1e-6:
                break
            p[key] = float(np.clip(p[key] + s * (tgt[m] - cur[m]) / slope, -0.004, 0.004))
            cur = read(p)
    rep = step(name, {k: round(v, 5) for k, v in p.items()}, out=out, seen=seen or "lid margins vs the iris",
               why=f"lids by measure: photo upper {tgt['upper']:.2f} lower {tgt['lower']:.2f} iris radii; model now "
                   f"{cur['upper']:.2f} / {cur['lower']:.2f}")
    rep["lids"] = {"target": tgt, "model": cur, "pose": p}
    return rep
