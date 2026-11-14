"""The table of what each control moves (built once), and the query: zones matched from words, `query`, `describe`, `text`. Part of GNM's controls (gnm_controls.py has the overview)."""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from . import gnm_controls
from .gnm_controls import gnm
from .gnm_controls_latent import (
    coefficients, family, field, identity_direction, macro_effect, names, vertices, zone_stats,
)

# ---------------------------------------------------------------- the table
def table() -> dict:
    if "t" not in gnm_controls._C:
        if not gnm_controls.DATA.exists():
            raise FileNotFoundError(f"{gnm_controls.DATA.name} is missing: build it with gnm_controls.build() (the gnmcontrols study)")
        z = np.load(gnm_controls.DATA)
        gnm_controls._C["t"] = {k: (z[k] if z[k].dtype.kind in "US" else np.asarray(z[k], float)) for k in z.files}
        gnm_controls._C["t"]["index"] = {str(n): i for i, n in enumerate(gnm_controls._C["t"]["names"])}
    return gnm_controls._C["t"]


def build(perc: dict | None = None, sheets: dict | None = None, out: Path | None = None, verbose: bool = False) -> dict:
    """Measure every control (zones, face rms / max, macros, nearest block-in moves) into gnm_controls.npz.
    perc: {name: (sface, arcface)} from the perception runs; sheets: {name: "page.png#row"}."""
    from . import humanmacro as hm
    allnames = names()
    fams = [family(n) for n in allnames]
    nz = len(gnm_controls.ZONES)
    Zs = np.zeros((len(allnames), nz, len(gnm_controls.STATS)), np.float32)
    face = np.zeros((len(allnames), 3), np.float32)
    mac = np.zeros((len(allnames), len(hm.NAMES)), np.float32)
    zi = list(gnm_controls.ZONES)
    ext = np.flatnonzero(gnm()["groups"]["skin_exterior"])
    # the block-in moves' identity directions, for "nearest"
    bnames = [n for n in allnames if family(n) in ("blockin", "region_pc")]
    B = np.array([identity_direction(n) for n in bnames])
    Bn = B / np.maximum(np.linalg.norm(B, axis=1, keepdims=True), 1e-12)
    near_n = np.full((len(allnames), 3), "", dtype=object)
    near_c = np.zeros((len(allnames), 3), np.float32)
    lin = np.full(len(allnames), np.nan, np.float32)
    cost = np.full(len(allnames), np.nan, np.float32)
    for i, nm in enumerate(allnames):
        D = field(nm)
        if fams[i] != "joints":
            cp, ep, _ = coefficients(nm, 1.0)
            cm, em, _ = coefficients(nm, -1.0)
            cost[i] = np.linalg.norm(np.r_[cp - cm, ep - em]) / 2
        Zs[i] = zone_stats(D)
        fz = Zs[i, zi.index("face"), 0]
        m = np.linalg.norm(D[ext], axis=1) * gnm_controls.MM
        face[i] = [fz, m.max(), np.sqrt((m ** 2).mean())]
        mac[i] = macro_effect(nm)
        d = identity_direction(nm)
        if d is not None and np.linalg.norm(d) > 1e-9:
            cs = Bn @ (d / np.linalg.norm(d))
            top = [j for j in np.argsort(-np.abs(cs)) if bnames[j] != nm][:3]
            near_n[i] = [bnames[j] for j in top]
            near_c[i] = cs[top]
        if fams[i] in ("sampler_latent", "sampler_label"):
            vp, vm = vertices(*coefficients(nm, 2.0)), vertices(*coefficients(nm, -2.0))
            v0 = vertices(*coefficients(nm, 0.0))
            lin[i] = np.linalg.norm((vp + vm - 2 * v0)[ext]) / max(np.linalg.norm((vp - vm)[ext]), 1e-12)
        if verbose and i % 50 == 0:
            print("build", i, "/", len(allnames), nm, flush=True)
    P = np.full((len(allnames), 2), np.nan, np.float32)
    for i, nm in enumerate(allnames):
        if perc and nm in perc:
            P[i] = [np.nan if v is None else v for v in perc[nm]]
    sh = np.array([(sheets or {}).get(nm, "") for nm in allnames])
    res = {"names": np.array(allnames), "family": np.array(fams), "zone_names": np.array(zi), "stats": np.array(gnm_controls.STATS),
           "Z": Zs.astype(np.float16), "face": face, "macros": mac.astype(np.float16), "macro_names": np.array(hm.NAMES),
           "perc": P, "near": near_n.astype(str), "near_cos": near_c, "nonlin": lin, "sheet": sh, "cost": cost}
    np.savez_compressed(out or gnm_controls.DATA, **res)
    gnm_controls._C.pop("t", None)
    return res


# ---------------------------------------------------------------- the query
def _words(s: str) -> list[str]:
    return [w for w in re.split(r"[\s,;/]+", s.lower().replace("_", "-")) if w]


def match_zones(text: str) -> list[str]:
    """The zones a phrase names ("alar crease" -> alar_crease; "lip border" -> both vermilion borders)."""
    t = text.lower().strip()
    if t.replace(" ", "_") in gnm_controls.ZONES:
        return [t.replace(" ", "_")]
    phrase = t.replace("_", "-").replace(" ", "-")
    hits = [k for k, (_, syn) in gnm_controls.ZONES.items() if phrase in syn.split()]
    if hits:
        return hits
    ws = _words(t)
    score = {}
    for k, (desc, syn) in gnm_controls.ZONES.items():
        toks = set(syn.replace("-", " ").split()) | set(k.split("_"))
        s = sum(1 for w in ws if w in toks or w.rstrip("s") in toks)
        if s:
            score[k] = s
    if not score:
        return []
    best = max(score.values())
    return [k for k, s in score.items() if s == best]


def query(text: str = "", zones_: list | None = None, families: list | None = None, top: int = 12,
          sort: str = "score", sign: int = 0, per_family: int = 0) -> dict:
    """The controls that move a zone. text: a feature in words ("alar crease", "jowl", "lip border") or zone names;
    families: restrict (default every shape family); sort: score (efficiency x specificity (capped at 4): the cheapest, most
    local movers) | efficiency (local mm per unit of PRIOR COST: |coefficient change| in population sd, so a whole
    expression prototype and a single comp compare fairly) | local (mm per control unit) | specific (local / face rms)
    | perc (face-ID effect) | relief (|the zone's move against its 5 mm surround| per unit cost: deepening or
    softening a groove / line); sign: +1 / -1 keeps controls whose + moves the zone out / in (the signed mean normal;
    with sort=relief: rises / sinks against its surround);
    per_family: the top k of every family instead of one ranking. Returns {"zones", "rows": [{name, family, local,
    efficiency, specific, sgn, face_rms, cost, perc, macros (top 3), near, sheet}]}."""
    t = table()
    zn = list(t["zone_names"])
    zs = list(zones_ or []) or match_zones(text)
    if not zs:
        raise ValueError(f"no zone matches {text!r}; zones: {', '.join(zn)}")
    fams = set(families or gnm_controls.SHAPE_FAMILIES)
    keep = np.array([f in fams for f in t["family"]])
    idx = [zn.index(z) for z in zs]
    Zsub = t["Z"][:, idx, :].astype(float)
    local = np.max(Zsub[:, :, [1, 4]], axis=2).mean(1)
    sgn = Zsub[:, :, 2].mean(1)
    fr = t["face"][:, 0]
    spec = local / np.maximum(fr, 1e-6)
    cost = t["cost"] if "cost" in t else np.ones(len(local))
    eff = local / np.maximum(cost, 1e-6)
    score = eff * np.minimum(spec, 4.0)
    rel = Zsub[:, :, 5].mean(1) if Zsub.shape[2] > 5 else np.zeros(len(local))
    key = {"score": score, "efficiency": eff, "local": local, "specific": np.where(local > 0.02, spec, 0),
           "perc": np.nan_to_num(t["perc"][:, 0]), "relief": np.abs(rel) / np.maximum(cost, 1e-6)}[sort]
    m = keep & np.isfinite(key)
    if sign:
        m &= np.sign(rel if sort == "relief" else sgn) == np.sign(sign)
    ranked = [i for i in np.argsort(-np.where(m, key, -np.inf)) if m[i]]
    if per_family:
        order = []
        for f in gnm_controls.FAMILIES:
            order += [i for i in ranked if t["family"][i] == f][:per_family]
    else:
        order = ranked[:top]
    mn = list(t["macro_names"])
    rows = []
    for i in order:
        mv = t["macros"][i].astype(float)
        tm = np.argsort(-np.abs(mv))[:3]
        rows.append({"name": str(t["names"][i]), "family": str(t["family"][i]), "local": round(float(local[i]), 3),
                     "efficiency": round(float(eff[i]), 3), "cost": round(float(cost[i]), 2),
                     "specific": round(float(spec[i]), 2), "relief": round(float(rel[i]), 3), "sgn": round(float(sgn[i]), 3),
                     "face_rms": round(float(fr[i]), 3), "perc": None if not np.isfinite(t["perc"][i, 0]) else round(float(t["perc"][i, 0]), 4),
                     "macros": {mn[j]: round(float(mv[j]), 2) for j in tm},
                     "near": [f"{n} {c:+.2f}" for n, c in zip(t["near"][i], t["near_cos"][i]) if n],
                     "sheet": str(t["sheet"][i])})
    return {"zones": zs, "rows": rows}


def describe(name: str) -> dict:
    """One control: where it acts (its top zones by local shape change), the macros it moves, perception, near."""
    t = table()
    i = t["index"][name]
    zn = list(t["zone_names"])
    Z = t["Z"][i].astype(float)
    loc = np.max(Z[:, [1, 4]], axis=1)
    fr = float(t["face"][i, 0])
    skip = ("face", "neck", "cranium", "iris", "pupil", "sclera", "teeth_upper", "teeth_lower", "tongue")
    order = [j for j in np.argsort(-loc) if zn[j] not in skip][:6]
    if not order or loc[order[0]] < 1e-3:   # (eyeballs, teeth, tongue, pose: what moves is not the face's skin)
        order = [j for j in np.argsort(-loc) if zn[j] != "face"][:6]
    mv = t["macros"][i].astype(float)
    mn = list(t["macro_names"])
    tm = np.argsort(-np.abs(mv))[:5]
    hint = ", ".join(f"{zn[j]} {'out' if Z[j, 2] > 0 else 'in'}" for j in order[:2])
    if len(tm):
        hint += f"; {mn[tm[0]]} {mv[tm[0]]:+.2f} sd"
    return {"name": name, "family": str(t["family"][i]), "hint": hint, "face_rms": round(fr, 3), "face_max": round(float(t["face"][i, 1]), 3),
            "zones": {zn[j]: {"local": round(float(loc[j]), 3), "sgn": round(float(Z[j, 2]), 3), "specific": round(float(loc[j] / max(fr, 1e-6)), 2)} for j in order},
            "macros": {mn[j]: round(float(mv[j]), 2) for j in tm},
            "perc": None if not np.isfinite(t["perc"][i, 0]) else {"sface": round(float(t["perc"][i, 0]), 4), "arcface": round(float(t["perc"][i, 1]), 4)},
            "near": [f"{n} {c:+.2f}" for n, c in zip(t["near"][i], t["near_cos"][i]) if n],
            "nonlinearity": None if not np.isfinite(t["nonlin"][i]) else round(float(t["nonlin"][i]), 2),
            "sheet": str(t["sheet"][i])}


def text(res: dict) -> str:
    """A query's or describe's reply as text."""
    if "rows" in res:
        z = ", ".join(f"{k} ({gnm_controls.ZONES[k][0]})" for k in res["zones"])
        out = [f"zones: {z}", "control | family | local mm/unit | mm per unit prior cost (|coef| per unit) | specificity "
               "(local / face rms) | relief vs its surround (+ rises) | + moves out/in | face rms | face-ID effect (sface, -1 vs +1) | macros moved (sd/unit) | "
               "nearest block-in moves | sheet"]
        for r in res["rows"]:
            out.append(f"{r['name']} | {r['family']} | {r['local']:.3f} | {r['efficiency']:.3f} ({r['cost']:.2f}) | {r['specific']:.2f} | "
                       f"relief {r['relief']:+.3f} | {'out' if r['sgn'] > 0 else 'in'} "
                       f"{r['sgn']:+.3f} | {r['face_rms']:.3f} | {r['perc'] if r['perc'] is not None else '-'} | "
                       + ", ".join(f"{k} {v:+.2f}" for k, v in r["macros"].items()) + " | " + "; ".join(r["near"]) + f" | {r['sheet']}")
        return "\n".join(out)
    r = res
    return (f"{r['name']} ({r['family']}): face rms {r['face_rms']} mm/unit, max {r['face_max']}; zones "
            + ", ".join(f"{k} {v['local']:.2f} mm ({'out' if v['sgn'] > 0 else 'in'}, x{v['specific']:.1f})" for k, v in r["zones"].items())
            + "; macros " + ", ".join(f"{k} {v:+.2f}" for k, v in r["macros"].items())
            + f"; face-ID {r['perc']}; nearest block-in " + "; ".join(r["near"])
            + ("" if r["nonlinearity"] is None else f"; non-linearity {r['nonlinearity']}") + f"; sheet {r['sheet']}")
