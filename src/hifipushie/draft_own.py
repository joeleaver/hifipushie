"""Garment step 4: the agent drafts its OWN pattern in FreeSewing, with the record's step-3 measurements.

Why: "I don't want to keep building specific drafters. Agents should have enough general intelligence to build a fresh
pattern using FreeSewing, based on 3d measurements of the model" (Joe, docs/state/garment_steps.md). A published design
(Simon) needed per-design glue (garment_kb recipes, collar rules, measure_defs adapters); here the agent writes the
design (usually extending a block: brian, bent, jaeger parts) and DECLARES what FreeSewing can't draw. Nothing in this
module knows a garment: the design and the declarations carry it.

`node_draft(source, measurements, options, sa, d)`: design.mjs run in Node in scratch dir d (under the model's
  workspace): no network (a user + network namespace), fs reads only (Node's permission model), TIMEOUT s. A Node error
  comes back as DraftRefused naming design.mjs's line and its text, never a stack.
Declarations (JSON beside the code; names are step 1's):
  pieces {piece: {"part": draft part, "fold": "x0", "mirror", "flip_y", "pair", "cut": n, "grain": deg, "place": {wrap}}}
  ("pair": true = cut 2 as a mirrored pair, NAME.L + NAME.R, seams per side: draft_pairs.py; "mirror" only flips)
  edges {piece: {edge: "pointA>pointB" | "a>via>b" | {"path": a path of the part}}}
  seams [{"a": "piece:edge" | [chain], "b": ..., "ease": [lo, hi] (a over b, -1), "why"}]: step 1's seams, sewn
  stiff [piece] (interfaced); folds [{"name", "piece", "line": edge | arc | {"edge", "offset"}, "kind", ...}] (style
  folds too: a rolled cuff); closures [closures.py entries, "edge": {"over": edge, "under": edge}]; omit {piece: why};
  darts [{"piece", "legs": [edge, edge], "why"?}] (C361; each leg declared "outline point>tip"): a dart OPEN on the outline (the seam path runs in along one
  leg to the tip and out along the other), its two legs declared edges of the piece, sewn to each other (the seam check
  holds them to one length; they must meet at the tip). A dart drawn inside a piece (a fish dart's closed path) isn't
  sewn: open it on the outline (cut the seam path to its tip) to take its suppression.
  departs {edge: why} (C381): a step-1 seam drafted more than 30 % off its approved estimate, said with what the
  reference shows there (else row style_lengths FAILs).
  marks {detail: mark | [marks]}: WHERE each step-1 detail sits on the pattern, decided here once (garment_details.py
  docstring: at / rows / points / follows / path / lines; stiffens: a trim that stiffens its edge); a closure's
  buttons are its own marks. A step-1 detail built full / simplified with no mark is refused (cloth-made ones: pieces).
`validate` refuses by name (a step-1 seam with no drafted edge or not sewn, a drafted piece not in the inventory, a built
  inventory piece not drafted). `block(pat)` is the ONE converter: the draft + declarations as cloth.pieces' block
  (pieces, seams, seam_notes, interfaced, folds, closures), so cloth.mesh makes chain_garment.PATTERN_KEYS as for every
  other draft. `gate` = the flat gate rows; `run` = the MCP tool body (server.draft_pattern).
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np

RUNNER = Path(__file__).with_name("draft_own_run.mjs")
MARK_FORM = ("a mark = {piece, mirror?: true, and one of: at: [{point, dx, dy} | {edge, mm | t, in}] (dx, dy mm in the "
             "FLAT pattern's frame: dy UP the piece, so FreeSewing's y (down) is -dy: C380), rows: {edge, count, "
             "from_mm | from_t, pitch_mm | pitch_t | to_mm | to_t, in}, points: 'button*', follows: ['piece:edge'], path: "
             "[positions]}; an edge: a declared edge name or 'a>b' along the outline (C361: the form was only in a "
             "docstring a blind agent can't read)")
TIMEOUT = 60  # s
DECL_KEYS = {"pieces", "edges", "seams", "stiff", "folds", "closures", "omit", "notes", "marks", "darts", "departs"}
def _roles() -> list:
    from .garment_design import kb
    return [r for r in kb()["roles"] if not r.startswith("_")] + ["collar_band"]


PIECE_KEYS = {"part", "fold", "mirror", "flip_y", "cut", "grain", "place", "role", "pair"}
BUILT = ("full", "simplified")  # step 1's "build" values that are cut
PLAIN_TOL = 0.01  # a seam with no declared ease: its two sides agree within 1 % (cloth_check KINDS "plain")
CLOSURE_TOL = 0.01  # a lapped closure's over and under edges agree within 1 % (the buttons line up)


class DraftRefused(ValueError):
    """The agent's draft or declarations can't be used; the message names what and where."""


# ---------------------------------------------------------------- Node
def _at(source: str, line, msg: str) -> str:
    if not line:
        return f"design.mjs: {msg}"
    src = source.splitlines()
    code = src[line - 1].strip() if 0 < line <= len(src) else ""
    return f"design.mjs line {line}: {msg}" + (f"\n  {line}| {code[:160]}" if code else "")


def _sandbox(cmd: list) -> list:
    """No network: a fresh user + network namespace (unshare -rn) when the kernel allows it."""
    u = shutil.which("unshare")
    if u and subprocess.run([u, "-rn", "true"], capture_output=True).returncode == 0:
        return [u, "-rn"] + cmd
    return cmd


def node_draft(source: str, measurements: dict, options: dict | None = None, sa: float = 10.0, d: Path | None = None,
               timeout: float = TIMEOUT) -> dict:
    from . import assets, freesewing
    d = Path(d)
    d.mkdir(parents=True, exist_ok=True)
    req = {"measurements": {k: float(v) for k, v in measurements.items()}, "options": dict(options or {}), "sa": float(sa)}
    key = hashlib.sha1(json.dumps([source, req, RUNNER.read_text()], sort_keys=True).encode()).hexdigest()[:16]
    cached = d / f"draft_{key}.json"
    if cached.exists():
        return json.loads(cached.read_text())
    pack = assets.pack("freesewing")
    (d / "design.mjs").write_text(source)
    (d / "run.mjs").write_bytes(RUNNER.read_bytes())
    nm = d / "node_modules"
    if not nm.exists():
        nm.symlink_to(pack / "node_modules")
    node = freesewing._node()
    perm = ["--permission", f"--allow-fs-read={d.resolve()}", f"--allow-fs-read={(pack / 'node_modules').resolve()}"]
    try:
        chk = subprocess.run(_sandbox([node, "--check", "design.mjs"]), capture_output=True, text=True, cwd=d, timeout=timeout)
        if chk.returncode:
            err = chk.stderr.strip().splitlines()
            line = next((int(x.rsplit(":", 1)[1]) for x in err[:1] if x.rsplit(":", 1)[-1].isdigit()), None)
            msg = next((x for x in err if "Error" in x), err[-1] if err else "syntax error")
            raise DraftRefused(_at(source, line, msg.strip()))
        r = subprocess.run(_sandbox([node, *perm, "run.mjs"]), input=json.dumps(req), capture_output=True, text=True,
                           cwd=d, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise DraftRefused(f"design.mjs: no draft after {timeout:.0f} s (a loop that never ends?)") from None
    if r.returncode != 0 or not r.stdout.strip():
        err = [x for x in r.stderr.strip().splitlines() if x.strip()]
        raise DraftRefused("design.mjs: Node failed: " + (next((x for x in err if "Error" in x), err[-1] if err else "?"))[:300])
    out = json.loads(r.stdout)
    if "error" in out:
        raise DraftRefused(_at(source, out.get("line"), out["error"]))
    errs = (out.get("logs") or {}).get("error")
    if errs:
        first = [e.splitlines()[0] for e in errs[:3]]
        raise DraftRefused(_at(source, (out.get("logs") or {}).get("line"), "FreeSewing: " + "; ".join(first)))
    miss = [m for m in out.get("measurements") or [] if m not in req["measurements"]]
    miss += [m for m in out.get("measurements_missing") or [] if m not in miss]  # (read by a part, not declared: C361)
    if miss:
        raise DraftRefused(f"design.mjs needs measurements step 3 hasn't taken: {', '.join(miss)} (have "
                           f"{', '.join(sorted(req['measurements']))}): add them to step 3 by name (body_tape(name, "
                           "[only these], garment=..., add=true): step 3's other measurements are kept as recorded), or use these; never "
                           "drop one from a block's list or supply it in the design")
    if out.get("measurements_set"):  # (t s4-1: hpsToBust written into the measurements as hpsToWaistBack - 226)
        raise DraftRefused(f"design.mjs sets measurements: {', '.join(out['measurements_set'])}: the body's measurements "
                           "are step 3's only; take the missing one there by name and read it here")
    if not out.get("parts"):
        raise DraftRefused("design.mjs: the draft has no visible parts (every part hidden?)")
    for pn, p in out["parts"].items():
        if "seam" not in p["paths"]:
            raise DraftRefused(f"design.mjs: part {pn!r} has no path 'seam' (its sewing line, closed): draw paths.seam")
    cached.write_text(json.dumps(out))
    return out


# ---------------------------------------------------------------- declarations
def _edge_of(e: str) -> tuple[str, str]:
    if not isinstance(e, str) or ":" not in e:
        raise DraftRefused(f"{e!r}: an edge is \"piece:edge\" (step 1's names)")
    return tuple(e.split(":", 1))


def _sides(s) -> list:
    return [s] if isinstance(s, str) else list(s or [])


def _fold_line_seams(decl: dict) -> list:
    """A seam joining a fold-cut piece's edge to its own mirror (P:e = P:e.m, step 1's P.L:cb = P.R:cb): that edge is
    the fold line, which joins the halves itself (C382, t s4-12)."""
    out, pcs = [], FOLDED(decl.get("pieces") or {})
    for i, s in enumerate(decl.get("seams") or []):
        A, B = _sides(s.get("a")), _sides(s.get("b"))
        if len(A) == len(B) == 1 and ":" in str(A[0]) and ":" in str(B[0]):
            (pa, ea), (pb, eb) = A[0].split(":", 1), B[0].split(":", 1)
            if pa == pb and pa in pcs and {ea, eb} == {ea.removesuffix(".m"), ea.removesuffix(".m") + ".m"}:
                out.append(f"seam {i} ({s.get('a')} | {s.get('b')}): that edge is the fold line of {pa} (cut on the "
                           "fold): the fold joins the halves, no seam; drop it (step 1's fold there is made by the "
                           "fold: C382)")
    return out


FOLDED = lambda pcs: {n for n, pd in pcs.items() if isinstance(pd, dict) and pd.get("fold") and not pd.get("pair")}


def _folded(r: dict, decl: dict, H: set = frozenset()) -> bool:
    """A step-1 seam of kind "fold" (a piece folded on itself: a collar's fall edge) is made by a declared fold of
    that name on that piece, not by a seam. One between two pieces (P.L:cb <-> P.R:cb: the halves of one piece cut on
    the fold) is made by cutting P on the fold (pieces.P.fold: H) or by a seam, never by a fold on one half (C381)."""
    if r.get("kind") != "fold":
        return False
    from .draft_pairs import canon
    ca, cb = canon(r["a"], H), canon(r["b"], H)
    if isinstance(r.get("b"), str) and _edge_of(ca)[0] != _edge_of(cb)[0]:
        return False
    if _edge_of(ca)[0] in H and ca == cb:
        return True
    p, ed = _edge_of(r["a"])
    return any(f.get("piece") == p and ed in (f.get("name"), f.get("line")) for f in decl.get("folds") or [])


def validate(decl: dict, step1: dict, parts: dict | None = None) -> list:
    """Refusals (one line each, by name); [] = usable. A declared pair (pieces.X {pair: true}) is expanded to X.L + X.R
    first and the expansion validated (C364, t s4-3: "pair never produced the right-hand pieces": the inventory check ran
    on the unexpanded name and refused it)."""
    from . import draft_pairs as dp
    if parts is not None:
        decl = dp.fold_halves(decl, parts)
        on_fold = _fold_line_seams(decl)
        if on_fold:
            return on_fold
    inv_ = step1.get("pieces") or {}
    sided = [nm for nm, pd in (decl.get("pieces") or {}).items() if isinstance(pd, dict) and pd.get("pair")
             and nm not in inv_ and f"{nm}.L" in inv_ and f"{nm}.R" in inv_]  # (step 1 names the two sides)
    if parts is not None and sided:
        bad0 = [f"declarations: unknown key {k!r} (have {', '.join(sorted(DECL_KEYS))})" for k in decl if k not in DECL_KEYS]
        bad0 += dp.faults(decl, parts, step1)
        if bad0:
            return bad0
        try:
            ex = dp.expand(json.loads(json.dumps(decl)), parts)
        except DraftRefused as e:
            return [str(e)]
        return validate(ex, step1, parts)
    bad = [f"declarations: unknown key {k!r} (have {', '.join(sorted(DECL_KEYS))})" for k in decl if k not in DECL_KEYS]
    pcs, edges, omit = decl.get("pieces") or {}, decl.get("edges") or {}, decl.get("omit") or {}
    inv = step1.get("pieces") or {}
    H = dp.halves(decl, step1)
    cn = lambda e: dp.canon(e, H)
    for nm, pd in pcs.items():
        if nm not in inv and nm not in H:
            bad.append(f"piece {nm!r} is drafted but not in step 1's inventory (have {', '.join(inv)})")
        for k in set(pd) - PIECE_KEYS:
            bad.append(f"piece {nm!r}: unknown key {k!r} (have {', '.join(sorted(PIECE_KEYS))})")
        if pd.get("role") is not None and pd["role"] not in _roles():  # (t s4-7: "stand" was taken silently)
            bad.append(f"piece {nm!r}: role {pd['role']!r} is not a role (have {', '.join(_roles())}); a layer sewn "
                       "edge to edge onto a piece (canvas, facing, lining of it) needs none: it takes that piece's (C377)")
        if pd.get("grain") is not None and (isinstance(pd["grain"], bool) or not isinstance(pd["grain"], (int, float))):
            bad.append(f"piece {nm!r}: grain {pd['grain']!r}: degrees from the part's x axis (90 = lengthwise, the usual "
                       "straight grain; 0 = crosswise; 45 = bias) (C363)")
        if parts is not None and pd.get("part") not in parts:
            bad.append(f"piece {nm!r}: the draft has no part {pd.get('part')!r} (has {', '.join(parts)})")
    for nm, it in inv.items():
        if it.get("build") in BUILT and nm not in pcs and nm[:-2] not in H and not str(omit.get(nm, "")).strip():
            bad.append(f"step 1 piece {nm!r} (build {it.get('build')}) is not drafted: draft it, or omit {{\"{nm}\": why}}")
    sewn = []
    for i, s in enumerate(decl.get("seams") or []):
        for side in ("a", "b"):
            for e in _sides(s.get(side)):
                p, ed = _edge_of(e)
                p = dp.base_name(p, decl)
                if p not in pcs:
                    bad.append(f"seam {i} {e!r}: no drafted piece {p!r}")
                elif ed not in (edges.get(p) or {}):
                    bad.append(f"seam {i} {e!r}: no edge {ed!r} declared on {p!r} (edges.{p}: {', '.join(edges.get(p) or {}) or 'none'})")
        if s.get("ease") is not None and not str(s.get("why", "")).strip():
            bad.append(f"seam {i} ({s.get('a')} | {s.get('b')}): an eased seam says why")
        sewn.append(({cn(e) for e in _sides(s.get("a"))}, {cn(e) for e in _sides(s.get("b"))}))
    for r in step1.get("seams") or []:
        a, b = r.get("a"), r.get("b")
        if any(_edge_of(x)[0] in omit for x in (a, b)):
            continue
        if _folded(r, decl, H):
            continue
        two = r.get("kind") == "fold" and isinstance(b, str) and _edge_of(cn(a))[0] != _edge_of(cn(b))[0]
        if r.get("kind") == "fold" and not two:
            bad.append(f"step 1 fold {a}: declare folds [{{\"name\": \"{_edge_of(a)[1]}\", \"piece\": \"{_edge_of(a)[0]}\", \"line\": ...}}]")
            continue
        a_, b_ = cn(a), cn(b)
        if two and not any((a_ in A and b_ in B) or (b_ in A and a_ in B) for A, B in sewn):
            base = _edge_of(a)[0][:-2] if _edge_of(a)[0].endswith((".L", ".R")) else _edge_of(a)[0]
            bad.append(f"step 1 fold {a} <-> {b} joins two halves: cut them as ONE piece on the fold (pieces.{base} "
                       f"{{part, fold: \"x0\"}}, no pair: it stands for both halves, its edges named once) or sew them "
                       f"(a seam {a} = {b}); a fold declared on one half doesn't join them (C381)")
            continue
        for x in (a_, b_):
            p, ed = _edge_of(x)
            if p in pcs and ed not in (edges.get(p) or {}):
                tw = p[:-2] + (".L" if p.endswith(".R") else ".R") if p.endswith((".L", ".R")) else None
                hint = (f"; or declare the pair ONCE: pieces.{p[:-2]} {{part, pair: true}} with edges.{p[:-2]} "
                        "(copied to both sides, C362)") if tw and not edges.get(p) and edges.get(tw) else ""
                bad.append(f"step 1 seam {a} <-> {b}: no drafted edge {x!r} (declare edges.{p}.{ed}{hint})")
        if not any((a_ in A and b_ in B) or (b_ in A and a_ in B) for A, B in sewn):
            bad.append(f"step 1 seam {a} <-> {b} is not sewn: a declared seam with {a} on one side and {b} on the other "
                       "(either may be one edge of a chain: a two-piece sleeve's cap set into the whole armhole as ONE seam, "
                       "[cap edges] = [armhole edges], sews every cap / armhole pair of step 1: C365)")
    for i, dt in enumerate(decl.get("darts") or []):
        p, legs = dp.base_name(str((dt or {}).get("piece")), decl), (dt or {}).get("legs")
        if p not in pcs:
            bad.append(f"darts[{i}]: no drafted piece {dt.get('piece')!r}")
        elif not (isinstance(legs, list) and len(legs) == 2 and legs[0] != legs[1]):
            bad.append(f"darts[{i}] on {p}: legs = [two edges of the piece] (the dart's sides, sewn to each other)")
        else:
            miss = [e for e in legs if e not in (edges.get(p) or {})]
            if miss:
                bad.append(f"darts[{i}] on {p}: no edge {', '.join(miss)} declared (edges.{p}: "
                           f"{', '.join(edges.get(p) or {}) or 'none'})")
    for c in decl.get("closures") or []:
        for k in ("over", "under"):
            if c.get(k) and dp.base_name(c[k], decl) not in pcs:
                bad.append(f"closure {c.get('name')!r}: {k} {c[k]!r} is not a drafted piece")
    if parts is not None and not bad:
        bad += dp.faults(decl, parts, step1)  # (F3: half a garment / a limb with no side, by name, with the pair)
        if not bad:
            try:
                dp.expand(decl, parts)
            except DraftRefused as e:
                bad.append(str(e))
    return bad + validate_marks(decl, step1)


def validate_marks(decl: dict, step1: dict) -> list:
    """The details' marks (T10, C290): every built step-1 detail is marked on the pattern (or is a closure's own button
    / a cloth piece); every mark names a step-1 detail, on drafted pieces, with position keys only."""
    from . import garment_details as gd
    bad, mk, pcs = [], decl.get("marks") or {}, decl.get("pieces") or {}
    det = step1.get("details") or {}
    if not isinstance(mk, dict):
        return [f"marks: {{detail: mark | [marks]}}; {MARK_FORM}"]
    kinds = {x.get("name"): x.get("kind") for x in decl.get("closures") or []}
    byclosure = {d for nm, c in (step1.get("closures") or {}).items() for d in c.get("details") or []
                 if kinds.get(nm) == "buttons" or (kinds.get(nm) == "zip" and (det.get(d) or {}).get("cloth"))}
    for n, m in mk.items():
        if n not in det:
            bad.append(f"marks.{n}: not a step-1 detail ({', '.join(det) or 'none'})")
            continue
        bad += gd.check_mark(n, m)
        for x in m if isinstance(m, list) else [m]:
            p = x.get("piece") if isinstance(x, dict) else None
            if p and p not in pcs:
                bad.append(f"marks.{n}: piece {p!r} is not drafted")
    mirrored = {gd.mirror_name(n) for n, m in mk.items()
                for x in (m if isinstance(m, list) else [m]) if isinstance(x, dict) and x.get("mirror")}
    for n, x in det.items():  # (a .L mark with mirror: true places the .R detail too, any kind: C366, t s4-5)
        if x.get("build") in BUILT and n not in mk and n not in byclosure and n not in mirrored \
                and not gd.cloth_made(x.get("what")):
            bad.append(f"step 1 detail {n!r} (build {x.get('build')}) has no mark: declare marks.{n}; {MARK_FORM}")
    return bad


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


def block(pat: dict) -> dict:
    """THE converter: the saved draft + declarations (pat["dir"]) as a cloth.pieces block."""
    from . import pattern
    d = Path(pat["dir"])
    draft = json.loads((d / "draft.json").read_text())
    from . import draft_pairs
    decl = draft_pairs.expand(json.loads((d / "declarations.json").read_text()), draft["parts"])
    edges = decl.get("edges") or {}
    out, arcs = {}, {}
    for nm, pd in (decl.get("pieces") or {}).items():
        part = draft["parts"][pd["part"]]
        pc = pattern.from_freesewing(part, nm, fold=pd.get("fold"))
        arcs[nm] = {}
        for ed, how in sorted((edges.get(nm) or {}).items(), key=lambda kv: isinstance(kv[1], dict) and "mirror_of" in kv[1]):
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
        pc["grain"] = float(pd.get("grain", 90.0))
        pc["cut"] = int(pd.get("cut", 1))
        if pd.get("role"):
            pc["role"] = pd["role"]
        out[nm] = pc
    arc = lambda e: "{}:{}".format(e.split(":", 1)[0], arcs[e.split(":", 1)[0]][e.split(":", 1)[1]])
    side = lambda s: arc(s) if isinstance(s, str) else [arc(e) for e in s]
    seams, notes = [], {}
    for s in decl.get("seams") or []:
        S = [side(s["a"]), side(s["b"])]
        seams.append(S)
        if s.get("ease") is not None:
            notes[json.dumps(S)] = {"ease": [float(x) for x in s["ease"]], "why": s.get("why", "")}
    darts = []  # (C361: a dart's legs sewn to each other, as a seam of the piece to itself)
    for dt in decl.get("darts") or []:
        for p in [q for q in (dt["piece"], f"{dt['piece']}.L", f"{dt['piece']}.R") if q in arcs]:
            S = [f"{p}:{arcs[p][dt['legs'][0]]}", f"{p}:{arcs[p][dt['legs'][1]]}"]
            seams.append(S)
            darts.append({"piece": p, "legs": S, "why": dt.get("why", "")})
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
    return {"pieces": out, "seams": seams, "stitches": [], "interfaced": list(decl.get("stiff") or []),
            "draft": {"design": "own", "dir": str(d), "options": decl.get("options") or {}},
            "folds": folds, "closures": closures, "seam_notes": notes, "edge_arcs": arcs, "decl": decl,
            "darts": darts}


# ---------------------------------------------------------------- the flat gate
def gate(B: dict, decl: dict, step1: dict, stand_ref: dict | None = None, step3: dict | None = None,
         fit: dict | None = None, body: dict | None = None, step2: dict | None = None) -> list:
    """General flat rows: seams (each pair within its declared ease, else PLAIN_TOL), seam_ends (each seam's edges run
    the same way: draft_seam_ends.py), cut (every built inventory piece
    cut), sewn (every step-1 seam), closures (every step-1 closure declared; lapped edges line up), truing (INFO), and
    the SHAPE rows per role (draft_shape.py: stand / band rise and lean, fall spread, sleeve cap, curved-to-straight seams)."""
    from . import cloth_check as cc, pattern
    rows = []
    sm = cc.seams(B)
    bad = []
    for r in sm:
        n = (B.get("seam_notes") or {}).get(json.dumps([r["a"], r["b"]]))
        lo, hi = n["ease"] if n else (-PLAIN_TOL, PLAIN_TOL)
        e = r["len_a_mm"] / r["len_b_mm"] - 1 if r["len_b_mm"] else 0.0
        ok = lo - 1e-6 <= e <= hi + 1e-6
        r.update(ease=e, band=(lo, hi), ok=ok, kind="declared" if n else "plain")
        if not ok:
            bad.append(f"{r['a']} || {r['b']}: {r['len_a_mm']:.1f} vs {r['len_b_mm']:.1f} mm, ease {100 * e:+.1f}% "
                       f"outside [{100 * lo:+.1f}, {100 * hi:+.1f}]%")
        seen_n = set()
        for na, nb, d in r.get("notches_off") or []:  # (C387, t s4-16 / s4-17: listed "FAIL" under a PASS row)
            na = na.lstrip("|").split(">")[-1].split(":")[-1].removesuffix("-notch")  # (a notch, or a chain's joint)
            if (na, nb) in seen_n:
                continue
            seen_n.add((na, nb))
            first = lambda x: (x if isinstance(x, str) else x[0]).split(">")[0] + ("..." if not isinstance(x, str) else "")
            bad.append(f"{first(r['a'])} || {first(r['b'])}: {na} sits {float(d):.1f} mm from {nb} along the seam "
                       f"(> {cc.NOTCH_MM:.0f} mm): they meet when sewn")
    rows.append({"id": "seams", "status": "FAIL" if bad else "PASS", "value": f"{len(sm)} seams, {len(bad)} off",
                 "target": f"each pair within its declared ease, else +-1 %; its notches within {cc.NOTCH_MM:.0f} mm",
                 "why": "; ".join(bad[:8]),
                 "fix": "redraft the shorter side, or declare the ease with why; a notch off: move it (or the chain's "
                        "start) so the two meet, e.g. a sleeve's top notch onto the shoulder seam", "back_to": "4",
                 "detail": sm})
    if B.get("darts"):  # (C361: a dart's legs meet at its tip; each declared from the outline toward the tip)
        from . import pattern
        far = []
        for dt in B["darts"]:
            ends = []
            for e in dt["legs"]:
                p, arc = e.split(":", 1)
                pc = B["pieces"][p]
                ends.append(pc["P"][pattern.arc_indices(pc, arc)][-1])
            gap = float(np.linalg.norm(ends[0] - ends[1])) * 1000
            if gap > 1.0:
                far.append(f"{dt['piece']}: its legs end {gap:.1f} mm apart")
        rows.append({"id": "darts", "status": "FAIL" if far else "PASS", "value": f"{len(B['darts'])} darts",
                     "target": "each dart's two legs run from the outline to ONE tip (declare both toward the tip)",
                     "why": "; ".join(far), "fix": "declare each leg 'outline point>tip'", "back_to": "4"})
    from . import draft_seam_ends
    rows += draft_seam_ends.rows(B)  # (F6: a seam sewn the wrong way round passes every length row)
    if step3 is not None:  # (F6: the pattern against the body it was measured on, before any build)
        from . import draft_body_lengths
        rows += draft_body_lengths.rows(B, step1, step3, fit)
        rows += draft_body_lengths.style_rows(B, step1, step3)
        from . import draft_girths  # (C383: the pattern round the body at its girths' levels)
        rows += draft_girths.rows(B, step3, fit, body)
    inv = step1.get("pieces") or {}
    from .draft_pairs import base_name
    dx = B.get("decl") or decl  # (pairs expanded: draft_pairs)
    # (a cut copy counts under its own name or its pair's base, whichever step 1 uses: C366, t s4-5's "not cut: front.L
    # ... not in step 1: front.L" read the expanded copies against the unexpanded declaration)
    from .draft_pairs import halves, canon
    H = halves(dx, step1)
    own = lambda n: n if n in inv else (n[:-2] if n.endswith((".L", ".R")) and n[:-2] in inv else base_name(n, decl))
    cut = {own(n) for n in B["pieces"]} | set(decl.get("omit") or {}) | {f"{n}.{s}" for n in H for s in "LR"}
    miss = [n for n, it in inv.items() if it.get("build") in BUILT and n not in cut]
    extra = [n for n in B["pieces"] if own(n) not in inv and n not in H]
    rows.append({"id": "cut", "status": "FAIL" if miss or extra else "PASS",
                 "value": f"{len(B['pieces'])} cut, {len(decl.get('omit') or {})} omitted",
                 "target": "every built step-1 piece cut, nothing else", "why": "; ".join(
                     [f"not cut: {n}" for n in miss] + [f"not in step 1: {n}" for n in extra]), "back_to": "4"})
    sewn = [({canon(e, H) for e in _sides(s.get("a"))}, {canon(e, H) for e in _sides(s.get("b"))})
            for s in decl.get("seams") or []]
    omit = set(decl.get("omit") or {})
    uns = [f"{r['a']} <-> {r['b']}" for r in step1.get("seams") or []
           if not any(_edge_of(x)[0] in omit for x in (r["a"], r["b"])) and not (_folded(r, dx, H) or _folded(r, decl, H))
           and not any((canon(r["a"], H) in A and canon(r["b"], H) in Bs) or (canon(r["b"], H) in A and
                       canon(r["a"], H) in Bs) for A, Bs in sewn)]
    rows.append({"id": "sewn", "status": "FAIL" if uns else "PASS", "value": f"{len(step1.get('seams') or []) - len(uns)} of "
                 f"{len(step1.get('seams') or [])} step-1 seams sewn", "target": "every step-1 seam", "why": "; ".join(uns[:8]),
                 "back_to": "4"})
    cl, why = dx.get("closures") or [], []
    for nm, c1 in (step1.get("closures") or {}).items():
        want = set(c1.get("pieces") or []) & set(B["pieces"])
        if want and not any(want <= {c.get("over"), c.get("under")} or nm == c.get("name") for c in cl):
            why.append(f"step 1 closure {nm!r} ({', '.join(sorted(want))}) has no declared closure")
    arcs = B.get("edge_arcs") or {}
    for c in cl:
        e = {k: arcs.get(c.get(k), {}).get(v, v) for k, v in (c.get("edge") or {}).items()}  # (edge names -> arcs)
        if c.get("over") and c.get("under") and c["over"] != c["under"] and e.get("over") and e.get("under"):
            try:
                lo = pattern.length(B["pieces"][c["over"]]["P"][pattern.arc_indices(B["pieces"][c["over"]], e["over"])])
                lu = pattern.length(B["pieces"][c["under"]]["P"][pattern.arc_indices(B["pieces"][c["under"]], e["under"])])
            except (KeyError, ValueError) as x:
                why.append(f"closure {c.get('name')!r}: {x}")
                continue
            if abs(lo / lu - 1) > CLOSURE_TOL:
                why.append(f"closure {c.get('name')!r}: over {1000 * lo:.0f} mm vs under {1000 * lu:.0f} mm (the holes "
                           f"won't meet their buttons)")
    rows.append({"id": "closures", "status": "FAIL" if why else "PASS", "value": f"{len(cl)} declared",
                 "target": "every step-1 closure declared; lapped edges within 1 %", "why": "; ".join(why[:6]), "back_to": "4"})
    try:
        jn = cc.junctions(B)
        off = [j for j in jn if not j.get("ok", True)]
        rows.append({"id": "truing", "status": "INFO", "value": f"{len(off)} of {len(jn)} seam ends not trued",
                     "target": "info: drafts are auto-trued in the build", "why": "; ".join(str(j.get("at", j))[:60] for j in off[:4])})
    except (KeyError, ValueError, TypeError) as x:
        rows.append({"id": "truing", "status": "INFO", "value": "n/a", "why": str(x)[:120]})
    from . import draft_shape
    from . import fold_bends
    fr = fold_bends.draft_row(decl, step2)  # (R2 C392: every planned fold drafted, every roll planned)
    if fr:
        rows.append(fr)
    return rows + draft_shape.rows(B, dx, step1, stand_ref)


def verdict(rows: list) -> str:
    return "FAIL" if any(r["status"] == "FAIL" for r in rows) else "PASS"
