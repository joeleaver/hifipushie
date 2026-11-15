"""THE converter: `block(pat)`, the saved draft + declarations as a cloth.pieces block. Part of garment step 4's own draft (draft_own.py has the overview)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .draft_own import DraftRefused, grain


def _resolve_path(pc: dict, part: dict, edge: str, path: str) -> str:
    """A draft path as an outline arc: its ends and its middle snapped to the outline, named <edge>.a / .m / .b."""
    from . import pattern
    if path not in part["paths"]:
        raise DraftRefused(f"{pc['name']}: edge {edge!r}: the part has no path {path!r} (has {', '.join(part['paths'])})")
    L = pattern.from_freesewing({"paths": {"seam": part["paths"][path]}, "points": {}}, "_")["P"]
    names = []
    for tag, q in (("a", L[0]), ("m", L[len(L) // 2]), ("b", L[-1])):
        i = int(np.argmin(np.linalg.norm(pc["P"] - q, axis=1)))
        if np.linalg.norm(pc["P"][i] - q) > 0.002:
            raise DraftRefused(f"{pc['name']}: edge {edge!r}: path {path!r} isn't on the seam outline ({tag} end "
                               f"{1000 * np.linalg.norm(pc['P'][i] - q):.1f} mm off): name its ends as \"a>b\"")
        pc["names"][f"{edge}.{tag}"] = i
        names.append(f"{edge}.{tag}")
    return ">".join(names)


def _cut_inside_darts(pc: dict, part: dict, nm: str, decl: dict, ped: dict) -> dict:
    """Piece nm's inside darts cut through (draft_dart_cut, C416): its edges with the two legs added."""
    from . import draft_dart_cut as dcut
    for dt in decl.get("darts") or []:
        if dcut.is_inside(dt) and dt.get("piece") == nm:
            try:
                cut = dcut.open_inside(pc, part, dt, ped)
            except dcut.Refused as e:
                raise DraftRefused(str(e)) from None
            names = []
            for i, (ea, eb) in enumerate(cut["pairs"]):
                ped[f"{dt['inside']}.s{i}a"], ped[f"{dt['inside']}.s{i}b"] = ea, eb
                names.append([f"{dt['inside']}.s{i}a", f"{dt['inside']}.s{i}b"])
            pc.setdefault("cuts", {})[dt["inside"]] = names
            for ed, subs in cut["split"].items():  # (an edge the release lands partway along: sewn as its two halves)
                old = pc.setdefault("split", {})
                for k in [k for k, v in old.items() if ed in v]:
                    old[k] = [x for e in old[k] for x in (subs if e == ed else [e])]
                if not any(ed in v for v in old.values()):
                    old[ed] = subs
    return ped


def block(pat: dict) -> dict:
    """THE converter: the saved draft + declarations (pat["dir"]) as a cloth.pieces block."""
    from . import pattern
    d = Path(pat["dir"])
    draft = json.loads((d / "draft.json").read_text())
    from . import draft_pairs
    decl = draft_pairs.expand(json.loads((d / "declarations.json").read_text()), draft["parts"])
    edges = decl.get("edges") or {}
    out, arcs, splits = {}, {}, {}
    for nm, pd in (decl.get("pieces") or {}).items():
        part = draft["parts"][pd["part"]]
        pc = pattern.from_freesewing(part, nm, fold=pd.get("fold"))
        arcs[nm] = {}
        ped = _cut_inside_darts(pc, part, nm, decl, dict(edges.get(nm) or {}))
        splits[nm] = pc.pop("split", {})
        for ed, how in sorted(ped.items(), key=lambda kv: isinstance(kv[1], dict) and "mirror_of" in kv[1]):
            if isinstance(how, dict) and "mirror_of" in how:  # (a folded piece's other half, sewn to a pair's other copy)
                try:
                    arcs[nm][ed] = draft_pairs.mirror_arc(pc, arcs[nm][how["mirror_of"]])
                except (KeyError, ValueError) as e:
                    raise DraftRefused(f"edges.{nm}.{ed} (the mirror of {how['mirror_of']!r}): {e}") from None
                continue
            arcs[nm][ed] = _resolve_path(pc, part, ed, how["path"]) if isinstance(how, dict) else str(how)
            try:
                ix = pattern.arc_indices(pc, arcs[nm][ed])
            except (KeyError, ValueError) as e:
                raise DraftRefused(f"edges.{nm}.{ed} = {arcs[nm][ed]!r}: {e}") from None
            P_ = np.asarray(pc["P"])[ix]
            ln_ = float(np.sum(np.linalg.norm(np.diff(P_, axis=0), axis=1))) if len(P_) > 1 else 0.0
            if not np.isfinite(ln_) or ln_ < 1e-3:  # (C362, t s4-2: "cannot convert float NaN to integer", no name)
                raise DraftRefused(f"edges.{nm}.{ed} = {arcs[nm][ed]!r} on part {pd['part']}: "
                                   + ("its points have no value (NaN): pattern_parts(design, part=...) names them"
                                      if not np.isfinite(ln_) else "it is 0 mm long: its points coincide"))
        if pd.get("mirror"):
            pc = pattern.mirror_x(pc)
        if pd.get("flip_y"):
            pc = pattern.mirror_y(pc)
        pc["wrap"] = dict(pd.get("place") or {"to": "torso"})
        pc["grain"] = grain(pd.get("grain", 90.0))
        pc["cut"] = int(pd.get("cut", 1))
        if pd.get("role"):
            pc["role"] = pd["role"]
        out[nm] = pc
    def arc(e):  # (an edge split where a dart's release lands on it: its halves, in its order)
        p, ed = e.split(":", 1)
        return [f"{p}:{arcs[p][x]}" for x in (splits.get(p) or {}).get(ed, [ed])]
    side = lambda s: (lambda L: L[0] if len(L) == 1 else L)([a for e in ([s] if isinstance(s, str) else s) for a in arc(e)])
    seams, notes = [], {}
    for s in decl.get("seams") or []:
        S = [side(s["a"]), side(s["b"])]
        seams.append(S)
        if s.get("ease") is not None:
            notes[json.dumps(S)] = {"ease": [float(x) for x in s["ease"]], "why": s.get("why", "")}
    darts = []  # (C361: a dart's legs sewn to each other, as a seam of the piece to itself)
    for dt in decl.get("darts") or []:
        for p in [q for q in (dt["piece"], f"{dt['piece']}.L", f"{dt['piece']}.R") if q in arcs]:
            for lg in (out[p].get("cuts") or {}).get(dt["inside"], []) if "inside" in dt else [dt["legs"]]:
                S = [f"{p}:{arcs[p][lg[0]]}", f"{p}:{arcs[p][lg[1]]}"]  # (an inside dart: its cut, then its sides)
                seams.append(S)
                darts.append({"piece": p, "legs": S, "why": dt.get("why", ""), "inside": "inside" in dt})
    folds = []
    for f in decl.get("folds") or []:
        f = dict(f)
        ln = f.get("line")
        if isinstance(ln, str) and ln in arcs.get(f.get("piece"), {}):
            f["line"] = {"edge": arcs[f["piece"]][ln]}
        elif isinstance(ln, dict) and ln.get("edge") in arcs.get(f.get("piece"), {}):
            f["line"] = dict(ln, edge=arcs[f["piece"]][ln["edge"]])
        folds.append(f)
    closures = []
    for c in decl.get("closures") or []:
        c = dict(c)
        if isinstance(c.get("edge"), dict):
            c["edge"] = {k: arcs.get(c.get(k), {}).get(v, v) for k, v in c["edge"].items()}
        closures.append(c)
    vents = [{k: (f"{v[k].split(':', 1)[0]}:{arcs.get(v[k].split(':', 1)[0], {}).get(v[k].split(':', 1)[1])}"
                  if k in ("over", "under") else v[k]) for k in v} for v in decl.get("vents") or []]
    return {"pieces": out, "seams": seams, "stitches": [], "interfaced": list(decl.get("stiff") or []), "vents": vents,
            "draft": {"design": "own", "dir": str(d), "options": decl.get("options") or {}},
            "folds": folds, "closures": closures, "seam_notes": notes, "edge_arcs": arcs, "decl": decl,
            "darts": darts}
