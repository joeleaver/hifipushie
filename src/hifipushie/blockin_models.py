"""Block-in models, their references and log: start, native_step, fork, the cameras' carry and fit. Part of the block-in (blockin.py has the overview)."""
from __future__ import annotations

import copy
import json
import time
from pathlib import Path

import numpy as np

from .blockin import STRIP, data, default_gnm_base, identity, set_identity
from .blockin_expression import fit_expression, view_base

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
          ethnicity: str | dict | None = None, cameras: str = "keep", replace: bool = False, expression: bool = False,
          attach: str = "native", carry: bool = False) -> dict:
    """The block-in's first model: the person's body (from the refs model, `body` merged over it), the head's local
    layers off, identity = GNM's sampler class mean for the sex (and ethnicity, if named); the references' fitted
    cameras (refs = a model with fitted references, or a views list: cameras fitted on this head).
    attach="native" (THE DEFAULT, nativedefault 2026-10-12): the head is GNM's OWN: the true base (gnm_base 1,
    dimorphism 0, eyes 1, no head style sliders), GNM's eyeball / mouth / teeth / tongue, at GNM's own size on the
    body (base.head.attach "native": onemesh); and NOTHING OF OURS on its surface: the refs model's sculpt `strokes`,
    `skin.folds` (+ fold_expressions) and painted wrinkle relief (`skin.wrinkles`) are NOT carried (entry["start"]
    ["dropped"] names them). attach="body" = the old path (the head carried at the body's own head size, gnm_base by
    age); carry=True keeps the refs model's strokes / folds / wrinkles (the old behaviour).
    cameras="keep": the refs model's cameras; when its head stood elsewhere or at another size (a body-carried head
    under a native start) they are CARRIED onto the new head by the two heads' similarity (same view, same yaw);
    "refit" refits them on this head (camera only). expression=True fits each detector view's expression on the start
    head (see expression_step: on a class mean it may soak up identity; usually later)."""
    from . import humans, store
    if (store.HOME / name / "spec.json").exists() and not replace:
        raise ValueError(f"{name} exists: choose a new name (block-in models are new models) or replace=True")
    if attach not in ("native", "body"):
        raise ValueError('block-in start: attach = "native" (GNM\'s own head at its own size: the default) or "body" (the old '
                         "body-carried head)")
    if attach == "native" and gnm_base is not None and float(gnm_base) != 1.0:
        raise ValueError(f"block-in start: gnm_base {gnm_base:g} means nothing on a GNM-native head (it IS the true GNM base); "
                         'attach="body" gives the old body-carried head that blends it')
    src_base = None
    if isinstance(refs, str):
        src = store.load(refs)
        rj = _refs(refs)
        if (src.get("base") or {}).get("body", {}).get("source") != "human":
            raise ValueError(f"{refs}: not a one-mesh human (base.body.source 'human')")
        sp = copy.deepcopy(src)
        src_base = copy.deepcopy(src["base"])
        for k in ("hair", "cloth"):
            sp.pop(k, None)
        sp["base"]["body"].update(body or {})
        views = rj["views"]
        cams = rj["cameras"]
    else:
        views = refs = with_anchor_points(refs)
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
    # the rest mouth closed by GNM's own lower-face expression (base_gnm_parts.lip_close_delta), not the seal: the seal's
    # membrane flattened the vermilion border (its turn 24 -> 11 deg on Tess) and moved the lips whole (gnmdetail2)
    for k in ("lip_seal", "mouth_gap"):
        hd.pop(k, None)
    hd["lip_close"] = True
    D = data()
    blend = class_blend(ethnicity, male)
    c = blend["c"]
    set_identity(sp, c)
    dropped = []
    if attach == "native":
        # (nativedefault, 2026-10-12; Joe's decisions) THE DEFAULT: GNM's head as GNM makes it, at GNM's own size, the
        # body fitted to it (onemesh "native"); head keys that resize or re-place it are dead there and dropped
        from . import humanstyle
        hd["attach"] = "native"
        for k in ("scale", "gnm_base_rest", "gnm_base_blend", "gnm_base_age", "toward"):
            if hd.pop(k, None) is not None:
                dropped.append(f"base.head.{k}")
        hs = (sp["base"].get("style") or {}).get("human") or {}
        for k in [k for k in hs if k in humanstyle.HEAD or k == "exaggerate"]:
            dropped.append(f"base.style.human.{k} {hs.pop(k):g}")
    else:
        hd.pop("attach", None)
        hd.pop("size", None)
    if not carry:
        # NOTHING OF OURS ON THE SURFACE of a new head: the refs model's sculpt strokes (garrett_a1's nine went onto every
        # gn_* / ng_* head unseen: "no hand sculpting" was reported of a head that had them), its fold layer and its
        # painted wrinkle relief are that model's dressing, not this person's read
        st = sp.get("strokes")
        if st:
            dropped.append(f"strokes ({len(st)}: {', '.join(list(st)[:9] if isinstance(st, dict) else [str(x.get('name', '?')) for x in st[:9]])})")
            sp["strokes"] = {} if isinstance(st, dict) else []
        sk = sp.get("skin")
        if isinstance(sk, dict):
            for k in ("folds", "fold_expressions"):
                if sk.get(k):
                    dropped.append(f"skin.{k}" + (f" ({', '.join(sorted(sk[k]))})" if isinstance(sk[k], dict) else ""))
                sk.pop(k, None)
            w = sk.get("wrinkles")
            if not (isinstance(w, dict) and float(w.get("amount", 1) or 0) == 0.0 and len(w) == 1):
                dropped.append("skin.wrinkles (" + (", ".join(sorted(w)) if isinstance(w, dict) and w else "the age's own") + ": amount 0)")
            sk["wrinkles"] = {"amount": 0.0}
    hd["gnm_base"] = float(1.0 if attach == "native" else (default_gnm_base(a) if gnm_base is None else gnm_base))
    if hd["gnm_base"] >= 1.0:
        # (garrettnative, 2026-10-12) THE TRUE GNM BASE asked for: nothing of MakeHuman's head may stay in the face.
        # gnm_base 1 alone left the one-mesh dimorphism field (default 0.8: MakeHuman's sex difference laid on GNM's
        # vertices), a refs model's eye scaling and its face style sliders (base.style.human eye_spacing, jaw ...:
        # humanstyle.HEAD) on the head: each pulls GNM's lids off GNM's ball (gnmnative's outer-corner ladder).
        # head_size stays: the head's size on the body is not the face's shape
        from . import humanstyle
        hd["dimorphism"], hd["eyes"] = 0.0, 1.0
        hs = (sp["base"].get("style") or {}).get("human") or {}
        for k in [k for k in hs if k in humanstyle.HEAD and k != "head_size"]:
            dropped.append(f"base.style.human.{k} {hs.pop(k):g}")
    # (gnmnative, 2026-10-12; Joe: "we might have done better to accept their eyeball, since their lid shapes are
    # built around it") GNM's OWN eyeball: no eye_radius (2026-10-10 .. 12 every start set 0.012; a refs model's is
    # dropped too). The key stays as an explicit override (block_in_step {"eye_radius": m})
    hd.pop("eye_radius", None)
    # GNM's own mouth too (the default without base.head.interior: a refs model's kit interior is dropped), and the
    # iris at GNM's limbus for the identity: a refs model's drawn size (skin.eyes.iris_size) would hide it. The read
    # sets it: iris_check -> block_in_step {"iris_mm": mm} (the identity's eyes_000)
    for k in ("interior", "mouth"):
        hd.pop(k, None)
    if isinstance((sp.get("skin") or {}).get("eyes"), dict):
        sp["skin"]["eyes"].pop("iris_size", None)
    rj = {"views": views, "cameras": cams}
    cam_note = "kept"
    if cams is None or cameras == "refit":
        rj["cameras"] = fit_cameras(sp["base"], views)
        cam_note = "refit"
    elif src_base is not None and _placement(src_base) != _placement(sp["base"]):
        # the refs model's head stood elsewhere / at another size (a body-carried head under a native start: Tess's is
        # 0.85 of GNM's size): its cameras follow the head by the two heads' similarity (same view, same yaw)
        rj["cameras"], cc = carry_cameras(src_base, sp["base"], cams)
        cam_note = f"carried onto the new head (x{cc['scale']:.3f}, moved {1000 * cc['shift']:.0f} mm)"
    rj["blockin"] = {"root": name, "boxes": _boxes(sp["base"], rj), "attach": attach, "placement": list(_placement(sp["base"])),
                     **({"cam_carried": True} if cam_note != "kept" else {})}
    if expression:
        rj["expressions"] = [fit_expression(sp["base"], v, c)["expression"] if abs(float(v.get("yaw", 0))) < 70 else {}
                             for v, c in zip(rj["views"], rj["cameras"])]
    left = []
    if isinstance(sp.get("skin"), dict):
        left.append(f"skin (tone, zones, features, lips, eyes; micro relief skin.detail {float(sp['skin'].get('detail', 1)):g})")
    if sp.get("paint"):
        left.append(f"paint layers ({len(sp['paint'])})")
    if carry and sp.get("strokes"):
        left.append(f"strokes ({len(sp['strokes'])}: carry=True)")
    rj.setdefault("blockin", {})["fallback"] = {k_: v_ for k_, v_ in blend.items() if k_ != "c"}
    _save(name, sp, f"block_in_start: {'male' if male else 'female'} class mean ({blend['say']}), "
          f"age {a:g}, " + ("GNM native" if attach == "native" else f"gnm_base {hd['gnm_base']:.2f}"), rj)
    entry = {"round": 0, "to": name, "start": {"refs": refs if isinstance(refs, str) else f"{len(views)} views",
             "sex": "male" if male else "female", "age": a, "gnm_base": hd["gnm_base"], "ethnicity": ethnicity,
             "fallback": {k_: v_ for k_, v_ in blend.items() if k_ != "c"},
             "attach": attach, "dropped": dropped, "left": left, "carry": bool(carry),
             "cameras": cam_note if cam_note != "kept" else "kept"},
             "c_norm": round(float(np.linalg.norm(c)), 3), "time": time.strftime("%Y-%m-%d %H:%M:%S")}
    _log_path(rj, name).write_text(json.dumps([entry], indent=1))
    return entry


def class_blend(ethnicity, male: bool) -> dict:
    """THE FALLBACK CENTRE (readmix, 2026-10-13): the identity the block-in starts from and the solve's prior is centred on.
    None = the sex's POOLED class mean (GNM's sampler, its four classes together); a class name = that class's mean; a
    dict {class: weight} = a BLEND of the class means (weights >= 0, normalised to 1: never outside the simplex). A
    SHAPE parameter of the start, not a label of the person. -> {"c", "weights" | None, "source": "GIVEN" | "DEFAULT", "say"}.
    Measured (docs/notes/readmix.md "## Fallback blend"): the classes' means differ by 1-3 mm in nose / mouth width;
    the people tested differ from the nearest class mean by 3-8 mm: the fallback is a small part of a wide nose."""
    D = data()
    en = [str(x) for x in D["eth_names"]]
    if not ethnicity:
        return {"c": np.asarray(D["m_m"] if male else D["m_f"], float), "weights": None, "source": "DEFAULT",
                "say": "the pooled mean of GNM's classes (none given)"}
    w = {ethnicity: 1.0} if isinstance(ethnicity, str) else {str(k_): float(v_) for k_, v_ in dict(ethnicity).items()}
    bad = [k_ for k_ in w if k_ not in en]
    if bad:
        raise ValueError(f"ethnicity: one of {en} (GNM's sampler classes), or a blend {{class: weight}} of them; not {bad}")
    if any(v_ < 0 for v_ in w.values()) or sum(w.values()) <= 0:
        raise ValueError("ethnicity blend: weights must be >= 0 and not all 0 (a blend inside the classes, never beyond them)")
    tot = sum(w.values())
    w = {k_: v_ / tot for k_, v_ in w.items() if v_ > 0}
    E = np.asarray(D["eth_means"][int(male)], float)
    c = sum(v_ * E[en.index(k_)] for k_, v_ in w.items())
    return {"c": np.asarray(c, float), "weights": {k_: round(v_, 3) for k_, v_ in w.items()}, "source": "GIVEN",
            "say": "GIVEN: " + " + ".join(f"{v_:.2f} {k_}" for k_, v_ in w.items())}


def with_anchor_points(views: list) -> list:
    """A views list's front and 3/4 pictures given WITHOUT landmark points get the detector's lm17..67 as their stored
    points (what human_reference writes). The joint solve takes its detector anchors, the chin's read and a 3/4's two
    iris centres from the stored points' NAMES: a bare {"image", "yaw"} view silently had none of them (Garrett's good
    set, 2026-10-11: 0 anchors, the 3/4's yaw unpinned). Views with any lm point, profiles and views without a face
    are returned as they are."""
    from . import likeness
    if not likeness.detector_available():
        return views
    from PIL import Image
    out = []
    for v in views:
        pts = v.get("points") or {}
        if (abs(float(v.get("yaw", 0.0))) < 70 and v.get("image")
                and not any(str(k).startswith("lm") and str(k)[2:].isdigit() for k in pts)):
            P = likeness.detect([Image.open(v["image"]).convert("RGB")])[0]
            if P is not None:
                v = {**v, "points": {**{f"lm{i}": [round(float(P[likeness.MP68[i]][0]), 2), round(float(P[likeness.MP68[i]][1]), 2)]
                                        for i in range(17, 68)}, **pts}}
        out.append(v)
    return out


def _placement(base: dict) -> tuple:
    """What decides where and how large a model's head stands, beyond its identity: (attach, base.head.size, the
    style's head_size, gnm_base). Cameras fitted under one placement do not fit another."""
    hd = base.get("head") or {}
    nat = hd.get("attach") == "native"
    hs = ((base.get("style") or {}).get("human") or {}).get("head_size", 1.0)
    return ("native", hd.get("size")) if nat else ("body", float(hs), float(hd.get("gnm_base", 0.0)), float(hd.get("dimorphism", 0.8)))


def carry_cameras(base0: dict, base1: dict, cams: list) -> tuple:
    """Cameras fitted on base0's head carried onto base1's head: the similarity (scale + translation, no turn) of the
    68 landmarks takes head 0 to head 1, and each camera goes with it (centre' = d + s x centre, t' = s x t, the focal
    length kept): head 1 lies in every picture where head 0 lay, each view's yaw and pitch as fitted. Exact when the
    two heads have one shape; a start for block_in_solve(cameras="refit") when they do not.
    -> (cameras, {"scale", "shift" (m)})."""
    from . import humanfit
    A = np.asarray(humanfit.state(base0)["L"], float)[:68]
    B = np.asarray(humanfit.state(base1)["L"], float)[:68]
    a0, b0 = A.mean(0), B.mean(0)
    s = float(((A - a0) * (B - b0)).sum() / ((A - a0) ** 2).sum())
    d = b0 - s * a0
    out = []
    for cam in cams:
        c = dict(cam)
        c["centre"] = (d + s * np.asarray(cam["centre"], float)).tolist()
        c["t"] = (s * np.asarray(cam["t"], float)).tolist()
        out.append(c)
    return out, {"scale": s, "shift": float(np.linalg.norm(b0 - a0))}


CAM_STALE = (0.10, 0.30)     # cameras are STALE when the head's landmarks through them are this far off the pictures' own
# stored points: 10 % in size, or 0.3 of the face's spread in place (a head switched to native is 10-20 % larger)
def cameras_fit(base: dict, rj: dict) -> dict:
    """Do the fitted cameras belong to THIS head? Per view with stored landmark points (lm0..67, six or more): the model's same
    landmarks through its camera against the picture's points: {"scale": size ratio model / picture (median over
    views), "off": the centres' distance / the picture points' spread, "n": views read, "stale": bool}. A measured
    answer (no flag in the file can go stale itself)."""
    from . import humanfit
    L = np.asarray(humanfit.state(base)["L"], float)
    sc, of = [], []
    for v, cam in zip(rj["views"], rj["cameras"]):
        ids = [int(k[2:]) for k in (v.get("points") or {}) if str(k).startswith("lm") and str(k)[2:].isdigit() and int(k[2:]) < 68]
        if len(ids) < 6 or not cam:
            continue
        P = np.array([v["points"][f"lm{i}"] for i in ids], float)
        Q = humanfit.project(cam, L[ids])
        sp_, sq = float(np.sqrt(((P - P.mean(0)) ** 2).sum(1).mean())), float(np.sqrt(((Q - Q.mean(0)) ** 2).sum(1).mean()))
        sc.append(sq / sp_)
        of.append(float(np.linalg.norm(Q.mean(0) - P.mean(0))) / sp_)
    if not sc:
        return {"scale": 1.0, "off": 0.0, "n": 0, "stale": False}
    r, o = float(np.median(sc)), float(np.median(of))
    return {"scale": r, "off": o, "n": len(sc), "stale": bool(abs(r - 1) > CAM_STALE[0] or o > CAM_STALE[1])}


NATIVE_REFUSE = {
    "head_scale": "a GNM-native head stands at GNM's own size (x base.head.size, by default the stature's allometry); the "
                  "style's head_size is not applied to it",
    "gnm_base": "a GNM-native head IS GNM's true base: there is no MakeHuman head under it to blend",
    "gnm_base_rest": "a GNM-native head IS GNM's true base: there is no MakeHuman head under it to blend",
    "dimorphism": "the dimorphism field is MakeHuman's sex difference laid on the body-carried head; a GNM-native head has none "
                  "(the sex is in the identity: the `sex` move)",
    "eye_size": "a GNM-native head has GNM's own eyeball at its real size (the lids are shaped on it); the iris is the "
                "identity's limbus (iris_mm)",
}


def native_step(src: str, out: str | None = None, seen: str = "") -> dict:
    """<out> = <src> with its head switched to GNM-native (base.head.attach "native": the true base at GNM's own
    size, the body fitted) and its fitted CAMERAS CARRIED onto the head's new size and place (carry_cameras). The
    head keys that mean nothing there are dropped and named. The next block_in_solve lays the cameras on the head
    first (cameras="refit", forced for that call). block_in_step(name, {"attach": "native"}) is this."""
    from . import humanstyle, onemesh, store
    sp = copy.deepcopy(store.load(src))
    rj = copy.deepcopy(_refs(src))
    b0 = copy.deepcopy(sp["base"])
    if onemesh.native(b0):
        cf = cameras_fit(b0, rj)
        if not cf["stale"]:
            raise ValueError(f"{src}: the head is GNM-native already and its cameras lie on it (size x{cf['scale']:.3f})")
        b0["head"].pop("attach", None)       # switched by an edit: the cameras are still the body-carried head's
    hd = sp["base"]["head"]
    dropped = []
    hd["attach"] = "native"
    for k, v in (("gnm_base", 1.0), ("dimorphism", 0.0), ("eyes", 1.0)):
        if hd.get(k) is not None and float(hd[k]) != v:
            dropped.append(f"base.head.{k} {float(hd[k]):g}")
        hd[k] = v
    for k in ("scale", "gnm_base_rest", "gnm_base_blend", "gnm_base_age", "toward"):
        if hd.pop(k, None) is not None:
            dropped.append(f"base.head.{k}")
    hs = (sp["base"].get("style") or {}).get("human") or {}
    for k in [k for k in hs if k in humanstyle.HEAD or k == "exaggerate"]:
        dropped.append(f"base.style.human.{k} {hs.pop(k):g}")
    rj["cameras"], cc = carry_cameras(b0, sp["base"], rj["cameras"])
    out = out or _next_name(src)
    if (store.HOME / out / "spec.json").exists():
        raise ValueError(f"{out} exists: block-in steps write new models")
    adopted = "blockin" not in rj
    lg = _adopt_log(src) if adopted else log(src)
    rj["blockin"] = {**(rj.get("blockin") or {"root": out}), "attach": "native", "cam_carried": True,
                     "placement": list(_placement(sp["base"]))}
    rj["blockin"].pop("cam_done", None)
    rj["blockin"]["boxes"] = _boxes(sp["base"], rj)
    _save(out, sp, f"block_in_step from {src}: attach native, cameras carried", rj)
    entry = {"round": 1 + max([e.get("round", 0) for e in lg] or [0]), "from": src, "to": out, "moves": {"attach": "native"},
             "seen": seen, "why": "the head switched to GNM-native; cameras carried onto its new size and place",
             "dropped": dropped, "camera_moves": [f"every camera carried: x{cc['scale']:.3f}, the face moved {1000 * cc['shift']:.0f} mm"],
             "c_norm": round(float(np.linalg.norm(identity(sp))), 3), "time": time.strftime("%Y-%m-%d %H:%M:%S")}
    lg.append(entry)
    _log_path(rj, out).write_text(json.dumps(lg, indent=1))
    return {"entry": entry, "scale": cc["scale"], "shift": cc["shift"], "dropped": dropped}


def fork(src: str, name: str, replace: bool = False) -> dict:
    """A block-in model copied as the ROOT of a new block-in (its own log, the cameras as they stand = the new start):
    reruns and tests step from the copy, so the source's log and directory are never written."""
    from . import store
    if (store.HOME / name / "spec.json").exists() and not replace:
        raise ValueError(f"{name} exists: choose a new name or replace=True")
    sp, rj = copy.deepcopy(store.load(src)), copy.deepcopy(_refs(src))
    rj["blockin"] = {**(rj.get("blockin") or {}), "root": name}
    rj["blockin"].pop("cam_done", None)
    _save(name, sp, f"block_in fork of {src}", rj)
    c = identity(sp)
    entry = {"round": 0, "to": name, "start": {"fork": src}, "c_norm": round(float(np.linalg.norm(c)), 3),
             "time": time.strftime("%Y-%m-%d %H:%M:%S")}
    _log_path(rj, name).write_text(json.dumps([entry], indent=1))
    return entry


FIT_LENS_SD = 0.05      # block_in_start's camera fit: the lens at its prior (EXIF / lens_mm, else a 70 mm portrait), +- this
FIT_PITCH_SD = 5.0      # ... and the camera level with the head, +- this many degrees


def fit_cameras(base: dict, views: list, rj: dict | None = None) -> list:
    """Each picture's camera fitted on this head, the head held (humanfit_map's camera-only fit); with rj, each view's
    camera on the head as that picture shows it (its fitted expression)."""
    from . import humanfit_map
    # (solvecams) the detector's points cannot tell the camera's PITCH or its LENS / distance (known heads: pitch 4.6 deg
    # rms, distance -78 .. +94 %): both under a prior here (level; the view's lens); the joint solve refines them
    cp = {"lens_sd": FIT_LENS_SD, "pitch_sd": FIT_PITCH_SD}
    if rj and any(rj.get("expressions") or []):
        return [humanfit_map.fit(view_base(base, rj, i), [v], free=(), cam_prior=cp)[1]["cameras"][0] for i, v in enumerate(views)]
    _, rep = humanfit_map.fit(base, views, free=(), cam_prior=cp)
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
