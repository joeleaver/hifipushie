"""Cut pairs at the draft (F3, blind trial t8): a piece the body wears on both sides, drafted once.

Why: t8's agent declared `mirror: true` meaning "cut two"; mirror only flips the one piece, so the build met half a
garment ("front is half a garment", "sleeve has no side") long after step 4 had passed. Now step 4 refuses it by name,
with the declaration that makes the pair, and the converter makes the pair itself.

`pieces.<name>.pair: true` = cut 2 as a mirrored pair. `expand(decl, parts)` turns it into NAME.L + NAME.R (the
drafted copy keeps its flat, the other is its mirror; the copy whose flat lies on +x is .L, the repo's rule ".L" = +X)
and rewrites everything that names the piece, per side:
  edges        copied to both;
  seams        a seam between paired pieces is sewn on each side (P.L | Q.L, P.R | Q.R); a paired piece sewn to itself
               on the SAME edge (`front:crotch | front:crotch`) is the seam BETWEEN the two (P.L:e | P.R:e); on two edges
               (`sleeve:underarm_a | sleeve:underarm_b`) each side closes its own; a centre piece cut on the fold sewn to
               a pair: its drafted half to the drafted copy, its mirrored half (edge `<e>.m`, made by the converter) to
               the other; a centre piece NOT on the fold sewn to a pair is refused (name each half's edge and sew
               P.L / P.R explicitly);
  closures     over and under the same paired piece -> over P.L, under P.R (name P.R / P.L to lap the other way);
  folds, stiff per side; place.to "<limb>.L" swaps to ".R" on the other copy.
Explicit P.L / P.R in seams and closures pass through. `faults(decl, parts, step1)`: the refusals (step 4): a soft
unsided piece whose flat lies off the centre line (half a garment), a limb piece with no side, a pair that is whole.
Nothing here knows a garment."""
from __future__ import annotations

import copy
import json

import numpy as np

SIDE_TOL = 0.01  # m: as chain_roles.sided_faults: a centre piece's flat centred on x = 0 within this + 10 % of its width
LIMB_WORDS = ("arm", "leg", "wrist", "ankle", "hand", "foot")
TUBE_ROLES = ("sleeve", "leg_front", "leg_back")
PAIR_HOW = ('cut 2 as a mirrored pair: pieces.{n} {{"pair": true}} (built as {n}.L + {n}.R, every seam that names it '
            'sewn per side; "mirror" only flips the one piece)')


def _side(n: str) -> str:
    return n[-1] if n[-2:] in (".L", ".R") else ""


def outline(part: dict, nm: str, pd: dict) -> np.ndarray:
    """The piece's flat outline as the converter makes it (fold, mirror, flip), metres."""
    from . import pattern
    pc = pattern.from_freesewing(part, nm, fold=pd.get("fold"))
    if pd.get("mirror"):
        pc = pattern.mirror_x(pc)
    if pd.get("flip_y"):
        pc = pattern.mirror_y(pc)
    return np.asarray(pc["P"], float)


def _off_centre(P: np.ndarray) -> bool:
    x = P[:, 0]
    return abs(x.min() + x.max()) / 2 > 0.1 * float(np.ptp(x)) + SIDE_TOL


def _limb(pd: dict, nm: str, decl: dict) -> bool:
    to = str((pd.get("place") or {}).get("to", "")).lower()
    if any(w in to for w in LIMB_WORDS) or pd.get("role") in TUBE_ROLES:
        return True
    for s in decl.get("seams") or []:  # sewn to itself on two edges: a tube round a limb
        a = [s.get("a")] if isinstance(s.get("a"), str) else list(s.get("a") or [])
        b = [s.get("b")] if isinstance(s.get("b"), str) else list(s.get("b") or [])
        pa, pb = {str(e).split(":", 1)[0] for e in a}, {str(e).split(":", 1)[0] for e in b}
        if pa == pb == {nm} and set(a) != set(b):
            return True
    return False


def faults(decl: dict, parts: dict, step1: dict) -> list:
    """Step 4 refusals by name, each with the declaration that fixes it."""
    out = []
    stiff = set(decl.get("stiff") or [])
    for nm, pd in (decl.get("pieces") or {}).items():
        if _side(nm) or pd.get("part") not in parts:
            continue
        try:
            P = outline(parts[pd["part"]], nm, pd)
        except (KeyError, ValueError, IndexError):
            continue  # (the converter names it)
        x = P[:, 0] * 1e3
        if pd.get("pair"):
            if pd.get("fold"):
                out.append(f"piece {nm!r}: \"pair\" and \"fold\" both: a fold makes one whole piece, a pair two halves; keep one")
            elif not _off_centre(P) and not _limb(pd, nm, decl):
                out.append(f"piece {nm!r}: \"pair\": true but its flat is whole (centred, x {x.min():.0f} to {x.max():.0f} mm): "
                           "a pair is two halves; drop \"pair\" (or cut it on the fold if it is drafted half)")
            continue
        if _limb(pd, nm, decl):  # (stiff ones too: a cuff on one wrist)
            out.append(f"piece {nm!r}: a limb piece with no side (the body has two): " + PAIR_HOW.format(n=nm))
        elif nm in stiff:
            continue  # (a band's ends are its own)
        elif _off_centre(P):
            out.append(f"piece {nm!r}: half a garment (its flat lies off the centre line, x {x.min():.0f} to {x.max():.0f} mm) "
                       "with no other half: " + PAIR_HOW.format(n=nm) + ', or cut on the fold (fold: "x0")')
    return out


def paired(decl: dict) -> set:
    return {n for n, pd in (decl.get("pieces") or {}).items() if pd.get("pair") and not _side(n)}


def expand(decl: dict, parts: dict) -> dict:
    """The declarations with every pair made two pieces (module docstring). No pair: returned as is."""
    from .draft_own import DraftRefused
    D = _fold_closures(fold_halves(decl, parts))
    pr = paired(D)
    if not pr:
        return D
    D = copy.deepcopy(D)
    pcs, edges = D.get("pieces") or {}, D.get("edges") or {}
    drafted = {}  # pair -> the side its drafted copy takes
    newp = {}
    for nm, pd in pcs.items():
        if nm not in pr:
            newp[nm] = pd
            continue
        P = outline(parts[pd["part"]], nm, pd)
        d = "L" if (P[:, 0].min() + P[:, 0].max()) >= 0 else "R"
        drafted[nm] = d
        o = "R" if d == "L" else "L"
        base = {k: v for k, v in pd.items() if k != "pair"}
        newp[f"{nm}.{d}"] = copy.deepcopy(base)
        other = copy.deepcopy(base)
        other["mirror"] = not base.get("mirror", False)
        to = str((other.get("place") or {}).get("to", ""))
        if _side(to):
            newp[f"{nm}.{d}"]["place"] = dict(base["place"], to=to[:-1] + d)
            other["place"] = dict(other["place"], to=to[:-1] + o)
        elif to and any(w in to.lower() for w in LIMB_WORDS):
            newp[f"{nm}.{d}"]["place"] = dict(base["place"], to=f"{to}.{d}")
            other["place"] = dict(other["place"], to=f"{to}.{o}")
        newp[f"{nm}.{o}"] = other
        if nm in edges:
            E = edges.pop(nm)
            edges[f"{nm}.L"], edges[f"{nm}.R"] = copy.deepcopy(E), copy.deepcopy(E)
    D["pieces"], D["edges"] = newp, edges
    folded = {n for n, pd in pcs.items() if pd.get("fold") and n not in pr}

    def piece(e):
        return str(e).split(":", 1)[0]

    def as_list(s):
        return [s] if isinstance(s, str) else list(s or [])

    def on(e, side, ref):
        """e on this side: a paired piece's copy; a folded centre piece's half matching ref's drafted copy."""
        p, ed = str(e).split(":", 1)
        if p in pr:
            return f"{p}.{side}:{ed}"
        if p in folded and ref is not None and side != drafted[ref]:
            edges.setdefault(p, {}).setdefault(f"{ed}.m", {"mirror_of": ed})
            return f"{p}:{ed}.m"
        return e

    seams = []
    for i, s in enumerate(D.get("seams") or []):
        A, B = as_list(s.get("a")), as_list(s.get("b"))
        ps = [piece(e) for e in A + B]
        refs = [p for p in ps if p in pr]
        if not refs:
            seams.append(s)
            continue
        loose = [p for p in ps if p not in pr and p not in folded and not _side(p)]
        if loose:
            raise DraftRefused(f"seam {i} ({s.get('a')} | {s.get('b')}): {loose[0]!r} is sewn to the pair {refs[0]!r} but "
                               f"isn't cut on the fold: declare each half of its edge (edges.{loose[0]}.<edge>_L / _R) and "
                               f"sew them to {refs[0]}.L / {refs[0]}.R by name")
        if len(A) == len(B) == 1 and piece(A[0]) == piece(B[0]) and A[0] == B[0]:
            p, ed = A[0].split(":", 1)
            seams.append(dict(s, a=f"{p}.L:{ed}", b=f"{p}.R:{ed}"))
            continue
        for side in ("L", "R"):
            f = lambda X: [on(e, side, refs[0]) for e in X]
            a, b = f(A), f(B)
            seams.append(dict(s, a=a[0] if isinstance(s.get("a"), str) else a,
                              b=b[0] if isinstance(s.get("b"), str) else b))
    D["seams"] = seams
    cls = []
    for c in D.get("closures") or []:
        c = dict(c)
        if c.get("over") in pr and c.get("over") == c.get("under"):
            c["over"], c["under"] = f"{c['over']}.L", f"{c['under']}.R"
        else:
            for k in ("over", "under"):
                if c.get(k) in pr:
                    c[k] = f"{c[k]}.L"
        cls.append(c)
    if cls:
        D["closures"] = cls
    if D.get("folds"):
        D["folds"] = [dict(f, piece=f"{f['piece']}.{sd}") for f in D["folds"] for sd in ("L", "R")
                      if f.get("piece") in pr] + [f for f in D["folds"] if f.get("piece") not in pr]
    if D.get("stiff"):
        D["stiff"] = [x for n in D["stiff"] for x in ((f"{n}.L", f"{n}.R") if n in pr else (n,))]
    _twin_seams(D, pr)
    if D.get("darts"):  # (C366, t s4-5: darts and marks naming a pair weren't expanded)
        dd = []
        for dt in D["darts"]:
            p = str(dt.get("piece"))
            if p in pr:
                dd += [dict(dt, piece=f"{p}.L"), dict(dt, piece=f"{p}.R")]
            else:
                dd.append(dt)
                if p[:-2] in pr and _side(p) and not any(x.get("piece") == _swap(p) for x in D["darts"]):
                    dd.append(dict(dt, piece=_swap(p)))
        D["darts"] = dd
    if D.get("marks"):
        D["marks"] = {n: _pair_mark(m, n, pr) for n, m in D["marks"].items()}
    return D


def _swap(n: str) -> str:
    return n[:-2] + (".R" if n.endswith(".L") else ".L") if n.endswith((".L", ".R")) else n


def _twin_seams(D: dict, pr: set):
    """A seam naming ONE side of a pair explicitly (front.L:shoulder = back.L:shoulder, step 1's own names) brings its
    other side's twin unless that is declared too (C366, t s4-5: the .R seams were reported "not sewn"; the rule of
    step 1: ".L" brings ".R"). A centre piece whose EDGE carries the side (undercollar:neck_front.L) swaps that edge to
    its declared .R twin (C376, t s4-6: the collar's right-hand seams had to be declared by hand)."""
    edges = D.get("edges") or {}

    def side_of(e):
        p, _, ed = str(e).partition(":")
        if _side(p):
            return p[-1]
        if _side(ed) and _swap(ed) in (edges.get(p) or {}):
            return ed[-1]
        return None
    els = lambda s: [e for k in ("a", "b") for e in ([s.get(k)] if isinstance(s.get(k), str) else s.get(k) or [])]
    have = {json.dumps([s.get("a"), s.get("b")], sort_keys=True) for s in D.get("seams") or []}
    add = []
    for s in D.get("seams") or []:
        es = els(s)
        sides = [side_of(e) for e in es]
        if None in sides or len(set(sides)) != 1 or not any(_side(str(e).split(":", 1)[0]) and
                                                             str(e).split(":", 1)[0][:-2] in pr for e in es):
            continue
        sw = lambda x: [_swap_edge(e) for e in x] if isinstance(x, list) else _swap_edge(x)
        t = dict(s, a=sw(s.get("a")), b=sw(s.get("b")))
        if json.dumps([t["a"], t["b"]], sort_keys=True) not in have:
            add.append(t)
            have.add(json.dumps([t["a"], t["b"]], sort_keys=True))
    D["seams"] = (D.get("seams") or []) + add


def _swap_edge(e: str) -> str:
    p, _, ed = str(e).partition(":")
    return f"{_swap(p)}:{ed}" if _side(p) else f"{p}:{_swap(ed)}"


def _pair_mark(m, detail: str, pr: set):
    """A mark on a pair's bare name lands on the copy its detail's side names (else .L, mirrored to .R)."""
    out = []
    for x in m if isinstance(m, list) else [m]:
        if isinstance(x, dict) and x.get("piece") in pr:
            side = detail[-1] if detail.endswith((".L", ".R")) else "L"
            q = f"{x['piece']}.{side}"
            x = dict(_remap_piece(x, x["piece"], q), piece=q)
            if not detail.endswith((".L", ".R")):
                x.setdefault("mirror", True)
        out.append(x)
    return out if isinstance(m, list) else out[0]


def _remap_piece(x, p: str, q: str):
    if isinstance(x, str):
        return q + x[len(p):] if x.startswith(p + ":") else x
    if isinstance(x, list):
        return [_remap_piece(v, p, q) for v in x]
    if isinstance(x, dict):
        return {k: _remap_piece(v, p, q) for k, v in x.items()}
    return x


def _fold_closures(decl: dict) -> dict:
    """A closure on ONE piece cut on the fold whose over and under name the same edge (t8: the waistband's fly
    `end` / `end`, the shirt stand's `end` / `end`, buttons at [btn, btn]): the edge / mark and its mirror on the
    other half, the two ends that close (read as the same edge / mark it closed to 0 mm)."""
    pcs = decl.get("pieces") or {}
    cl = decl.get("closures") or []
    hit = [i for i, c in enumerate(cl) if c.get("over") and c.get("over") == c.get("under")
           and (pcs.get(c["over"]) or {}).get("fold")]
    if not hit:
        return decl
    D = copy.deepcopy(decl)
    for i in hit:
        c = D["closures"][i]
        e = (c.get("edge") or {}).get("over") if isinstance(c.get("edge"), dict) else None
        if e and c["edge"].get("under") == e:
            D.setdefault("edges", {}).setdefault(c["over"], {}).setdefault(f"{e}.m", {"mirror_of": e})
            c["edge"] = dict(c["edge"], under=f"{e}.m")
        if c.get("at"):  # (its buttons: the same mark on both ends is the mark and its mirror image)
            c["at"] = [[a, f"{b}.m"] if a == b and not str(b).endswith(".m") else [a, b] for a, b in c["at"]]
    return D


def mirror_arc(pc: dict, arc: str) -> str:
    """A folded piece's arc "a>b>..." on its other half: each point's mirror image (x -> -x) named "<name>.m" (points on
    the fold keep their name)."""
    P = np.asarray(pc["P"], float)
    out = []
    for k in arc.split(">"):
        i = pc["names"][k]
        if abs(P[i][0]) < 1e-5:
            out.append(k)
            continue
        if k + ".m" not in pc["names"]:
            j = int(np.argmin(np.linalg.norm(P - P[i] * [-1, 1], axis=1)))
            if np.linalg.norm(P[j] - P[i] * [-1, 1]) > 1e-4:
                raise ValueError(f"{pc['name']}: no mirror image of point {k!r} (is the piece cut on the fold? an edge "
                                 "ON the fold line has no other half: the fold isn't sewn, declare no seam there)")
            pc["names"][k + ".m"] = j
        out.append(k + ".m")
    return ">".join(out)


def fold_halves(decl: dict, parts: dict) -> dict:
    """Step 1's half names on a piece cut on the fold, as that piece's own (C382, t s4-12: `collar.L:top` was refused
    as "no drafted piece", `collar.R:...` too, and the agent found "x" / "x.m" by trial, then cut halves sewn at CB):
    for each pieces.P {fold} (no pair), "P.<its drafted half's side>:e" -> "P:e", "P.<other>:e" -> "P:e.m" (its mirror,
    edges.P["e.m"] made), and "P.L" / "P.R" as a piece -> "P". The drafted half's side: its flat's x (".L" = +x)."""
    pcs = decl.get("pieces") or {}
    folded = [n for n, pd in pcs.items() if isinstance(pd, dict) and pd.get("fold") and not pd.get("pair")
              and pd.get("part") in (parts or {})]
    if not folded:
        return decl
    D = copy.deepcopy(decl)
    edges = D.setdefault("edges", {})
    side = {}
    for n in folded:
        P = outline(parts[pcs[n]["part"]], n, {k: v for k, v in pcs[n].items() if k != "fold"})
        side[n] = "L" if float(np.mean(P[:, 0])) >= 0 else "R"

    def name(x):
        if not isinstance(x, str):
            return x
        for n in folded:
            if x in (f"{n}.L", f"{n}.R"):
                return n
            for sd in "LR":
                if x.startswith(f"{n}.{sd}:"):
                    e = x.split(":", 1)[1]
                    if sd == side[n] or e.endswith(".m"):
                        return f"{n}:{e}"
                    edges.setdefault(n, {}).setdefault(f"{e}.m", {"mirror_of": e})
                    return f"{n}:{e}.m"
        return x

    def walk(v):
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, dict):
            return {name(k) if isinstance(k, str) and ":" in k else k: walk(x) for k, x in v.items()}
        return name(v)
    # a seam naming one side (front.L:neckline = collar.L:neck_front, step 1's names) brings its other side's twin, as
    # for a pair (_twin_seams), unless declared too
    sd = lambda e: str(e).split(":", 1)[0][-2:] if ":" in str(e) else ""
    els = lambda x: [x] if isinstance(x, str) else list(x or [])
    have = {json.dumps([x.get("a"), x.get("b")], sort_keys=True) for x in D.get("seams") or []}
    for x in list(D.get("seams") or []):
        es = els(x.get("a")) + els(x.get("b"))
        sides = {sd(e) for e in es}
        if len(sides) != 1 or not sides <= {".L", ".R"} or not any(str(e).split(":", 1)[0][:-2] in folded for e in es):
            continue
        o = {".L": ".R", ".R": ".L"}[sides.pop()]
        sw = lambda v: [sw(e) for e in v] if isinstance(v, list) else (v.split(":", 1)[0][:-2] + o + ":" + v.split(":", 1)[1])
        t = dict(x, a=sw(x.get("a")), b=sw(x.get("b")))
        key = json.dumps([t["a"], t["b"]], sort_keys=True)
        if key not in have:
            have.add(key)
            D["seams"].append(t)
    for k in ("seams", "closures", "marks", "darts", "folds", "stiff", "departs"):
        if k in D:
            D[k] = walk(D[k])
    return D


def base_name(n: str, decl: dict) -> str:
    """P.L / P.R of a paired P -> P (explicit sides in seams and closures)."""
    return n[:-2] if _side(n) and n[:-2] in paired(decl) else n


def halves(decl: dict, step1: dict) -> set:
    """Centre pieces cut on the fold (pieces.P {fold}, no pair) that stand for step 1's two halves P.L + P.R (C381,
    t s4-11: step 1 named collar.L / collar.R joined by a fold at CB; only a pair could answer to those names, so the
    agent cut two loose halves and put a press fold on one, and the collar was never joined at CB)."""
    inv = step1.get("pieces") or {}
    return {n for n, pd in (decl.get("pieces") or {}).items() if isinstance(pd, dict) and pd.get("fold")
            and not pd.get("pair") and n not in inv and f"{n}.L" in inv and f"{n}.R" in inv}


def canon(e, H: set):
    """An edge named for step 1's half (P.L:e, P.R:e) or the converter's mirrored half (P:e.m) of a fold-cut piece in
    H, as the one piece's edge P:e; any other edge as is."""
    if not isinstance(e, str) or ":" not in e:
        return e
    p, ed = e.split(":", 1)
    if p[-2:] in (".L", ".R") and p[:-2] in H:
        p = p[:-2]
    if p in H and ed.endswith(".m"):
        ed = ed[:-2]
    return f"{p}:{ed}"

