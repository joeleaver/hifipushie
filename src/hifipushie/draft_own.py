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
  pieces {piece: {"part": draft part, "fold": "x0", "mirror", "flip_y", "cut": n, "grain": deg, "place": {wrap}}}
  edges {piece: {edge: "pointA>pointB" | "a>via>b" | {"path": a path of the part}}}
  seams [{"a": "piece:edge" | [chain], "b": ..., "ease": [lo, hi] (a over b, -1), "why"}]: step 1's seams, sewn
  stiff [piece] (interfaced); folds [{"name", "piece", "line": edge | arc | {"edge", "offset"}, "kind", ...}] (style
  folds too: a rolled cuff); closures [closures.py entries, "edge": {"over": edge, "under": edge}]; omit {piece: why};
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
TIMEOUT = 60  # s
DECL_KEYS = {"pieces", "edges", "seams", "stiff", "folds", "closures", "omit", "notes", "marks"}
PIECE_KEYS = {"part", "fold", "mirror", "flip_y", "cut", "grain", "place", "role"}
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
    if miss:
        raise DraftRefused(f"design.mjs needs measurements step 3 hasn't taken: {', '.join(miss)} (have "
                           f"{', '.join(sorted(req['measurements']))}): measure them by name with body_tape, or use these")
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


def _folded(r: dict, decl: dict) -> bool:
    """A step-1 seam of kind "fold" (a piece folded on itself: a collar's fall edge) is made by a declared fold of
    that name on that piece, not by a seam."""
    if r.get("kind") != "fold":
        return False
    p, ed = _edge_of(r["a"])
    return any(f.get("piece") == p and ed in (f.get("name"), f.get("line")) for f in decl.get("folds") or [])


def validate(decl: dict, step1: dict, parts: dict | None = None) -> list:
    """Refusals (one line each, by name); [] = usable."""
    bad = [f"declarations: unknown key {k!r} (have {', '.join(sorted(DECL_KEYS))})" for k in decl if k not in DECL_KEYS]
    pcs, edges, omit = decl.get("pieces") or {}, decl.get("edges") or {}, decl.get("omit") or {}
    inv = step1.get("pieces") or {}
    for nm, pd in pcs.items():
        if nm not in inv:
            bad.append(f"piece {nm!r} is drafted but not in step 1's inventory (have {', '.join(inv)})")
        for k in set(pd) - PIECE_KEYS:
            bad.append(f"piece {nm!r}: unknown key {k!r} (have {', '.join(sorted(PIECE_KEYS))})")
        if parts is not None and pd.get("part") not in parts:
            bad.append(f"piece {nm!r}: the draft has no part {pd.get('part')!r} (has {', '.join(parts)})")
    for nm, it in inv.items():
        if it.get("build") in BUILT and nm not in pcs and not str(omit.get(nm, "")).strip():
            bad.append(f"step 1 piece {nm!r} (build {it.get('build')}) is not drafted: draft it, or omit {{\"{nm}\": why}}")
    sewn = []
    for i, s in enumerate(decl.get("seams") or []):
        for side in ("a", "b"):
            for e in _sides(s.get(side)):
                p, ed = _edge_of(e)
                if p not in pcs:
                    bad.append(f"seam {i} {e!r}: no drafted piece {p!r}")
                elif ed not in (edges.get(p) or {}):
                    bad.append(f"seam {i} {e!r}: no edge {ed!r} declared on {p!r} (edges.{p}: {', '.join(edges.get(p) or {}) or 'none'})")
        if s.get("ease") is not None and not str(s.get("why", "")).strip():
            bad.append(f"seam {i} ({s.get('a')} | {s.get('b')}): an eased seam says why")
        sewn.append((set(_sides(s.get("a"))), set(_sides(s.get("b")))))
    for r in step1.get("seams") or []:
        a, b = r.get("a"), r.get("b")
        if any(_edge_of(x)[0] in omit for x in (a, b)):
            continue
        if _folded(r, decl):
            continue
        if r.get("kind") == "fold":
            bad.append(f"step 1 fold {a}: declare folds [{{\"name\": \"{_edge_of(a)[1]}\", \"piece\": \"{_edge_of(a)[0]}\", \"line\": ...}}]")
            continue
        for x in (a, b):
            p, ed = _edge_of(x)
            if p in pcs and ed not in (edges.get(p) or {}):
                bad.append(f"step 1 seam {a} <-> {b}: no drafted edge {x!r} (declare edges.{p}.{ed})")
        if not any((a in A and b in B) or (b in A and a in B) for A, B in sewn):
            bad.append(f"step 1 seam {a} <-> {b} is not sewn: a declared seam with {a} on one side and {b} on the other")
    for c in decl.get("closures") or []:
        for k in ("over", "under"):
            if c.get(k) and c[k] not in pcs:
                bad.append(f"closure {c.get('name')!r}: {k} {c[k]!r} is not a drafted piece")
    return bad + validate_marks(decl, step1)


def validate_marks(decl: dict, step1: dict) -> list:
    """The details' marks (T10, C290): every built step-1 detail is marked on the pattern (or is a closure's own button
    / a cloth piece); every mark names a step-1 detail, on drafted pieces, with position keys only."""
    from . import garment_details as gd
    bad, mk, pcs = [], decl.get("marks") or {}, decl.get("pieces") or {}
    det = step1.get("details") or {}
    if not isinstance(mk, dict):
        return ["marks: {detail: mark | [marks]} (garment_details.py docstring)"]
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
    for n, x in det.items():
        if x.get("build") in BUILT and n not in mk and n not in byclosure and not gd.cloth_made(x.get("what")):
            bad.append(f"step 1 detail {n!r} (build {x.get('build')}) has no mark: declare marks.{n} (where it sits on "
                       "the pattern: at / rows / points / follows / path)")
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
    decl = json.loads((d / "declarations.json").read_text())
    edges = decl.get("edges") or {}
    out, arcs = {}, {}
    for nm, pd in (decl.get("pieces") or {}).items():
        part = draft["parts"][pd["part"]]
        pc = pattern.from_freesewing(part, nm, fold=pd.get("fold"))
        arcs[nm] = {}
        for ed, how in (edges.get(nm) or {}).items():
            arcs[nm][ed] = _resolve_path(pc, part, ed, how["path"]) if isinstance(how, dict) else str(how)
            try:
                pattern.arc_indices(pc, arcs[nm][ed])
            except (KeyError, ValueError) as e:
                raise DraftRefused(f"edges.{nm}.{ed} = {arcs[nm][ed]!r}: {e}") from None
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
            "folds": folds, "closures": closures, "seam_notes": notes, "edge_arcs": arcs}


# ---------------------------------------------------------------- the flat gate
def gate(B: dict, decl: dict, step1: dict, stand_ref: dict | None = None) -> list:
    """General flat rows: seams (each pair within its declared ease, else PLAIN_TOL), cut (every built inventory piece
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
    rows.append({"id": "seams", "status": "FAIL" if bad else "PASS", "value": f"{len(sm)} seams, {len(bad)} off",
                 "target": "each pair within its declared ease, else +-1 %", "why": "; ".join(bad[:8]),
                 "fix": "redraft the shorter side, or declare the ease with why", "back_to": "4", "detail": sm})
    inv = step1.get("pieces") or {}
    cut = set(B["pieces"]) | set(decl.get("omit") or {})
    miss = [n for n, it in inv.items() if it.get("build") in BUILT and n not in cut]
    extra = [n for n in B["pieces"] if n not in inv]
    rows.append({"id": "cut", "status": "FAIL" if miss or extra else "PASS",
                 "value": f"{len(B['pieces'])} cut, {len(decl.get('omit') or {})} omitted",
                 "target": "every built step-1 piece cut, nothing else", "why": "; ".join(
                     [f"not cut: {n}" for n in miss] + [f"not in step 1: {n}" for n in extra]), "back_to": "4"})
    sewn = [(set(_sides(s.get("a"))), set(_sides(s.get("b")))) for s in decl.get("seams") or []]
    omit = set(decl.get("omit") or {})
    uns = [f"{r['a']} <-> {r['b']}" for r in step1.get("seams") or []
           if not any(_edge_of(x)[0] in omit for x in (r["a"], r["b"])) and not _folded(r, decl)
           and not any((r["a"] in A and r["b"] in Bs) or (r["b"] in A and r["a"] in Bs) for A, Bs in sewn)]
    rows.append({"id": "sewn", "status": "FAIL" if uns else "PASS", "value": f"{len(step1.get('seams') or []) - len(uns)} of "
                 f"{len(step1.get('seams') or [])} step-1 seams sewn", "target": "every step-1 seam", "why": "; ".join(uns[:8]),
                 "back_to": "4"})
    cl, why = decl.get("closures") or [], []
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
    return rows + draft_shape.rows(B, decl, step1, stand_ref)


def verdict(rows: list) -> str:
    return "FAIL" if any(r["status"] == "FAIL" for r in rows) else "PASS"
