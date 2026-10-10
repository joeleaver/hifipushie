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
FLAGGED = {"jaw_angle_height": "reads MediaPipe 172 / 397 (the detector's guess at the jaw contour), not the gonion"}

BODY_KEYS = ("weight",)
HEAD_KEYS = {"dimorphism": "dimorphism", "gnm_base": "gnm_base"}
# head_scale: the one mesh's head is the BODY's head (base.head.scale is overwritten by the body's size); a uniform size
# change is base.style.human.head_size (humanstyle: the head scaled about the top of the neck, eyeballs with it)
POSE_KEYS = ("lid_upper", "lid_lower")
STRIP = ("sliders", "warp", "fold", "pose", "shape", "seed", "spread", "features", "expression", "habitual")
SQUINT_MM = 9.0
AMBIENT_FLOOR = 0.18    # the clay's darkest skin under a degenerate (painted) light, x the skin's median luminance
DARK_SHARE = 0.25       # degenerate = more than this share of the face's skin predicted under the floor
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
            "lid_upper, lid_lower")


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
          ethnicity: str | None = None, cameras: str = "keep", replace: bool = False) -> dict:
    """The block-in's first model: the person's body (from the refs model, `body` merged over it), the head's local
    layers off, identity = GNM's sampler class mean for the sex (and ethnicity, if named), gnm_base by age; the
    references' fitted cameras (refs = a model with fitted references, or a views list: cameras fitted on this head).
    cameras="refit" refits a refs model's cameras on this head (camera only)."""
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
    rj = {"views": views, "cameras": cams}
    if cams is None or cameras == "refit":
        rj["cameras"] = fit_cameras(sp["base"], views)
    rj["blockin"] = {"root": name, "boxes": _boxes(sp["base"], rj)}
    _save(name, sp, f"block_in_start: {'male' if male else 'female'} class mean{' (' + ethnicity + ')' if ethnicity else ''}, "
          f"age {a:g}, gnm_base {hd['gnm_base']:.2f}", rj)
    entry = {"round": 0, "to": name, "start": {"refs": refs if isinstance(refs, str) else f"{len(views)} views",
             "sex": "male" if male else "female", "age": a, "gnm_base": hd["gnm_base"], "ethnicity": ethnicity,
             "cameras": "refit" if (cams is None or cameras == "refit") else "kept"},
             "c_norm": round(float(np.linalg.norm(c)), 3), "time": time.strftime("%Y-%m-%d %H:%M:%S")}
    _log_path(rj, name).write_text(json.dumps([entry], indent=1))
    return entry


def fit_cameras(base: dict, views: list) -> list:
    """Each picture's camera fitted on this head, the head held (humanfit_map's camera-only fit)."""
    from . import humanfit_map
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


def step(src: str, moves: dict, out: str | None = None, seen: str = "", why: str = "",
         cameras: list | None = None) -> dict:
    """<out> = <src> moved: directions add (amount x direction), base keys and lids are SET. Logged with what was seen
    and why. cameras = view indices to refit on the result head (camera only). Returns the report (see step_text)."""
    from . import store
    if not moves and not cameras:
        raise ValueError("block_in_step: no moves. Vocabulary:\n" + vocabulary())
    sp = copy.deepcopy(store.load(src))
    rj = _refs(src)
    c0 = identity(sp)
    c = c0.copy()
    big = []
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
        else:
            c = c + v * direction(k)
            if abs(v) > 1.0:
                big.append(k)
    set_identity(sp, c)
    out = out or _next_name(src)
    if (store.HOME / out / "spec.json").exists():
        raise ValueError(f"{out} exists: block-in steps write new models (revert = step again from an earlier one)")
    rj = copy.deepcopy(rj)
    adopted = "blockin" not in rj   # a model made outside the tools (an older loop, a fit): this step roots a new log
    if adopted:
        rj["blockin"] = {"root": out, "boxes": _boxes(store.load(src)["base"], rj)}
    cam_moves = []
    if cameras:
        from . import humanfit
        new = fit_cameras(sp["base"], rj["views"])
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
    entry = {"round": rnd, "from": src, "to": out, "moves": moves, "cameras": cameras, "camera_moves": cam_moves,
             "seen": seen, "why": why,
             "c_norm": round(float(np.linalg.norm(c)), 3), "read": read,
             "coupled": [[k, round(float(x), 2)] for k, x in moved],
             "passes": passes(t1), "time": time.strftime("%Y-%m-%d %H:%M:%S")}
    lg.append(entry)
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
    if e.get("camera_moves"):
        s.append("cameras refitted (landmarks only: a camera fit does not see the outline): " + "; ".join(e["camera_moves"]))
    if rep["big"]:
        s.append(f"WARNING: {', '.join(rep['big'])} moved more than 1 sd in one step: the method takes small steps (0.3-0.7)")
    s.append("targets before -> after: " + ", ".join(f"{g} {rep['before'].get(g, '-')} -> {p}" for g, p in e["passes"].items()))
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
    return hashlib.sha1(json.dumps([sp["base"], rj["cameras"]], sort_keys=True).encode()).hexdigest()[:16]


def table(name: str) -> dict:
    """{group: [{id, view, unit, photo, model, diff, tol, ok, flag?}]} through the model's fitted cameras (likeness
    checklist items); cached in the model's directory by its base + cameras."""
    from . import likeness as lk, store
    h = _spec_hash(name)
    p = store.HOME / name / "blockin_table.json"
    if p.exists():
        d = json.loads(p.read_text())
        if d.get("hash") == h:
            return d["table"]
    rows = lk.compare(name, store.load(name)["base"])["rows"]
    out = {}
    for g, ids in GROUPS.items():
        out[g] = []
        for i in ids:
            for r in sorted((r for r in rows if r["id"] == i), key=lambda r: str(r.get("vi"))):
                a, b = r.get("photo"), r.get("model")
                if not isinstance(a, (int, float)) or not isinstance(b, (int, float)) or not np.isfinite(a) or not np.isfinite(b):
                    continue
                tol = float(r.get("tol") or 0)
                d = float(b) - float(a)
                row = {"id": i, "view": r.get("view", r.get("vi")), "unit": r.get("unit"), "photo": round(float(a), 3),
                       "model": round(float(b), 3), "diff": round(d, 3), "tol": round(tol, 3), "ok": bool(tol and abs(d) <= tol)}
                if i in FLAGGED:
                    row["flag"] = FLAGGED[i]
                out[g].append(row)
    p.write_text(json.dumps({"hash": h, "table": out}, indent=1))
    return out


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
    fl = sorted({r["id"] for rows in t.values() for r in rows if "flag" in r})
    if fl:
        s.append("flag = shown, not counted: " + "; ".join(f"{i}: {FLAGGED[i]}" for i in fl))
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


def presented_mesh(base: dict, eyes: bool = True) -> dict:
    from . import humanfit, likeness
    st = humanfit.state(base)
    mesh = likeness.model_mesh_from_state(st)
    mesh["C"] = haircap(mesh, st)
    if eyes:
        eye_presentation(mesh)
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
    if mask.sum() < 200:
        mask = ps["part"] == 0
    c0, w, _ = ls.fit_light(Y, ps["nrm"], mask)
    lt = (c0, w, float(np.median(Y[mask])), 1.0)
    _, _, p2 = likeness.render(mesh, cam, box, px=px, brows=False, passes=True, ao=True, shadow=soft, light=lt)
    dn = p2["nrm"] @ np.asarray(w, float)
    m2 = mask & (p2["part"] == 0)
    X = np.c_[np.ones(m2.sum()), p2["ao"][m2], (np.maximum(dn, 0) * p2["lit"])[m2], np.minimum(dn, 0)[m2]]
    A, B, C = np.linalg.lstsq(X, Y[m2], rcond=None)[0][:3]
    c0n = float(A + B)
    aw = float(np.clip(B / c0n, 0.0, 1.0)) if c0n > 1e-6 else 0.0
    # an ambient floor: a painted picture's light is not one light, and the fit put its shadow side at black (Garrett's
    # 3/4 portrait: half the clay face lost); real skin in shadow keeps ~a third of its lit level
    med = float(np.median(Y[mask]))
    w2 = np.asarray(w, float) * max(float(C), 0.0)
    wn = float(np.linalg.norm(w2))
    lo = AMBIENT_FLOOR * med
    dark = float(np.mean((c0n + p2["nrm"][m2] @ w2) < lo)) if m2.any() else 0.0
    if wn > 1e-9 and c0n - wn < lo and dark > DARK_SHARE:
        # a quarter of the face's skin under the floor: the fit is degenerate (a painted light); the skin facing away
        # (c0 - |w|) kept at the floor, the lit side (c0 + |w|) as fitted. A photo's light (a few side planes dark) is
        # left as fitted: compressing it flattened Garrett's front clay
        top = c0n + wn
        if top > lo:
            c0n, w2 = 0.5 * (top + lo), w2 * (0.5 * (top - lo)) / wn
    lt2 = (c0n, w2, lt[2], aw)
    lt = lt2 if np.all(np.isfinite(lt2[1])) and np.isfinite(c0n) else lt
    im, k, ps = likeness.render(mesh, cam, box, px=px, brows=False, passes=True, ao=True, shadow=soft, light=lt)
    return im, lt, ps


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
    the nasion to under the chin, for a left-facing picture; hair / lashes crossing are skipped, the throat cut off."""
    from PIL import Image
    a = np.asarray(Image.open(view["image"]).convert("RGB"), float)
    pts = view.get("points") or {}
    yb, yc = float(pts["nose_bridge"][1]), float(pts["chin"][1])
    y0, y1 = int(yb - 0.12 * (yc - yb)), int(yc + 0.22 * (yc - yb))
    bg = np.median(a[:, :15].reshape(-1, 3), 0)
    lum = a.mean(-1)
    fg = (np.abs(a - bg).sum(-1) > 40) & (lum > 0.55 * np.median(lum[int(yb):int(yc), :]))
    out = []
    for y in range(max(y0, 0), min(y1, a.shape[0]), step):
        run = np.convolve(fg[y].astype(float), np.ones(6), "valid") >= 6
        if not run.any():
            continue
        x = float(np.argmax(run))
        if out and y > yc and x - out[-1][0] > 12.0 * step / 6:
            break
        out.append([x, float(y)])
    return np.array(out)


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
    return np.mean([pts["nose_bridge"], pts["eye_outer.L"]], 0), Lm[[27, 45]].mean(0)


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
    mesh = presented_mesh(base)
    st = mesh["state"]
    boxes = (rj.get("blockin") or {}).get("boxes") or _boxes(base, rj)
    VI = list(range(len(rj["views"]))) if views is None else [int(v) for v in views]
    cols = ["photo", f"{name} (photo's light)", "50% overlay", "outline: photo red / clay green", "squint photo", "squint clay"]
    mesh_b = presented_mesh(store.load(before)["base"]) if before else None
    per = 2 if before else 1
    sheet = Image.new("RGB", (T * len(cols), (T + 18) * len(VI) * per + 18), "white")
    dr = ImageDraw.Draw(sheet)
    for j, lab in enumerate(cols):
        dr.text((j * T + 4, 2), lab, fill=(0, 0, 0))
    info = []
    for i, vi in enumerate(VI):
        v, cam = rj["views"][vi], rj["cameras"][vi]
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
        cl = cl.convert("RGB")
        to = lambda Q: [((q[0] - box[0]) * k, (q[1] - box[1]) * k) for q in Q]  # noqa: E731
        to_ph = lambda Q: [((q[0] - pbox[0]) * k, (q[1] - pbox[1]) * k) for q in Q]  # noqa: E731
        if front and Pd is not None:
            cl = draw_photo_brows(cl, Pd, to_ph)
        else:
            cl = draw_brows(cl, mesh, cam, box, k)
        ov = Image.blend(ph, cl, 0.5)
        ol = ph.copy().convert("L").convert("RGB")
        d = ImageDraw.Draw(ol)
        if front:
            if Pd is not None:
                Pp = np.asarray(Pd, float)[likeness.OVAL, :2]
                d.line(to_ph(np.r_[Pp, Pp[:1]]), fill=(230, 30, 30), width=3)
            full, _, _ = lit_render(mesh, cam, img)
            Pm_ = detect_view(full.convert("RGB"), v)
            if Pm_ is not None:
                Pm = np.asarray(Pm_, float)[likeness.OVAL, :2]
                d.line(to(np.r_[Pm, Pm[:1]]), fill=(30, 200, 30), width=3)
        else:
            try:
                d.line(to_ph(profile_contour(v)), fill=(230, 30, 30), width=3)
            except Exception:  # noqa: BLE001  (a profile without a plain background: the clay's edge alone)
                pass
            e = Image.fromarray((ps["part"] >= 0).astype(np.uint8) * 255).filter(ImageFilter.FIND_EDGES)
            olA = np.asarray(ol).copy()
            olA[np.asarray(e) > 0] = (30, 200, 30)
            ol = Image.fromarray(olA)
        sg = SQUINT_MM / likeness._mm_per_px(cam, mesh["L"][27:48]) * k
        sq = lambda im: im.convert("L").filter(ImageFilter.GaussianBlur(sg)).convert("RGB")  # noqa: E731
        y = 18 + i * per * (T + 18)
        for j, im in enumerate((ph, cl, ov, ol, sq(ph), sq(cl))):
            sheet.paste(im.resize((T, T), Image.LANCZOS), (j * T, y))
        dr.text((4, y + T + 2), f"view {vi} (yaw {float(v.get('yaw', 0)):g}): {Path(v['image']).name}; registered at "
                f"the eyes, shift {sh[0]:+.0f}, {sh[1]:+.0f} px", fill=(0, 0, 0))
        if mesh_b is not None:
            mesh_b["_photo_P"] = Pd
            cb = lit_render(mesh_b, cam, img, box=box, px=px)[0].convert("RGB")
            cb = draw_photo_brows(cb, Pd, to_ph) if front and Pd is not None else draw_brows(cb, mesh_b, cam, box, k)
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
            "model": lid_model(base, rj["cameras"][vi]), "pose": dict(base["head"].get("pose") or {})}


def lid_text(r: dict) -> str:
    s = [f"lid margins vs the iris (in iris radii from its centre; front view {r['view']}): upper (MRD1-like), lower "
         "(MRD2-like), aspect = opening width / height"]
    for side in ("R", "L"):
        p = (r["photo"] or {}).get(side)
        m = (r["model"] or {}).get(side)
        f = lambda d: "-" if d is None else f"upper {d['upper']:.2f} lower {d['lower']:.2f} aspect {d['aspect']:.2f}"  # noqa: E731
        s.append(f"  {side}: photo {f(p)} | model {f(m)}")
    s.append(f"  pose now: {r['pose'] or '{}'} (lid_upper / lid_lower, m: -0.001 = that lid 1 mm up)")
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
        m = lid_model(base, cam)
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
