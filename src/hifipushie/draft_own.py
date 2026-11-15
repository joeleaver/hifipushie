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
  seams [{"a": "piece:edge" | [chain: edges in order, each starting where the one before ended], "b": ..., "ease": [lo,
  hi] (a over b, -1), "why"}]: step 1's seams, sewn
  stiff [piece] (interfaced); folds [{"name", "piece", "line": edge | arc | {"edge", "offset"} | a path of the part by
  name (a CURVED fold line: draw it as a path in design.mjs, e.g. a collar's roll line through its CB) | [point, point,
  ...] (outline points or snippets; points inside the part are dropped by the converter), "kind", ...}] (style
  folds too: a rolled cuff; pattern.fold_line; a name it hasn't is refused naming the fold, what it may name and the
  nearest names: C408); closures [closures.py entries, "edge": {"over": edge, "under": edge}]; omit {piece: why};
  darts [{"piece", "legs": [edge, edge], "why"?}] (C361; each leg declared "outline point>tip"): a dart OPEN on the outline (the seam path runs in along one
  leg to the tip and out along the other), its two legs declared edges of the piece, sewn to each other (the seam check
  holds them to one length; they must meet at the tip). A dart drawn INSIDE a piece (a fish dart; a dart ending in a
  pocket mouth): {"piece", "inside": <its closed path of the part>, "release": [part points..., named outline point]}:
  drawn as it is, never cut by hand; the tool cuts it through along release and sews dart and cut shut (draft_dart_cut.py,
  C416).
  tapes {piece: [step-3 tape names] | {edge: tape name}} (P1): the tapes each piece was drafted on, merged into the
  record's piece_measurements (step 5 starts the piece on them); an edge map names the tape an edge LAID ON THE BODY lies
  along (kept as edge_tapes): a stiff piece sewn to soft cloth names one for that edge (a collar's neck edge on the
  neckline tape). Row piece_tapes (draft_tapes.py) FAILs a piece with none, a name step 3 hasn't taken (back to 3).
  departs {edge: why} (C381): a step-1 seam drafted more than 30 % off its approved estimate, said with what the
  reference shows there (else row style_lengths FAILs).
  vents [{"name", "over": "piece:edge", "under": "piece:edge"}]: a vent's two sides, open below its top and lapped
  (draft_vents.py: the girths row counts the overlap once).
  moves [{"seam": [A edge, B edge], "at": [[mm along A, mm toward B], ...]}] (F5): a seam line moved between the two
  pieces it joins; the converter re-cuts both so the seam still sews (draft_moves.py).
  marks {detail: mark | [marks]}: WHERE each step-1 detail sits on the pattern, decided here once (garment_details.py
  docstring: at / rows / points / follows / path / lines; stiffens: a trim that stiffens its edge); a closure's
  buttons are its own marks. A step-1 detail built full / simplified with no mark is refused (cloth-made ones: pieces).
`validate` refuses by name (a step-1 seam with no drafted edge or not sewn, a drafted piece not in the inventory, a built
  inventory piece not drafted). `block(pat)` is the ONE converter: the draft + declarations as cloth.pieces' block
  (pieces, seams, seam_notes, interfaced, folds, closures), so cloth.mesh makes chain_garment.PATTERN_KEYS as for every
  other draft. `gate` = the flat gate rows; `run` = the MCP tool body (server.draft_pattern).

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at draft_own.NAME: C422). draft_own_validate: the declarations checked against step 1: `validate` and
`validate_marks` refuse by name. draft_own_block: THE converter: `block(pat)`, the saved draft + declarations as a
cloth.pieces block. draft_own_gate: the flat gate: `gate` (its rows) and `verdict`.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from . import moved

RUNNER = Path(__file__).with_name("draft_own_run.mjs")
MARK_FORM = ("a mark = {piece, mirror?: true, and one of: at: [{point, dx, dy} | {edge, mm | t, in}] (dx, dy mm in the "
             "FLAT pattern's frame: dy UP the piece, so FreeSewing's y (down) is -dy: C380), rows: {edge, count, "
             "from_mm | from_t, pitch_mm | pitch_t | to_mm | to_t, in}, points: 'button*', follows: ['piece:edge'], path: "
             "[positions]}; an edge: a declared edge name or 'a>b' along the outline (C361: the form was only in a "
             "docstring a blind agent can't read)")
TIMEOUT = 60  # s
DECL_KEYS = {"pieces", "edges", "seams", "stiff", "folds", "closures", "omit", "notes", "marks", "darts", "departs", "tapes",
             "vents", "moves"}
GRAIN_WORDS = {"lengthwise": 90.0, "straight": 90.0, "crosswise": 0.0, "bias": 45.0}  # (s4-26: "lengthwise" refused)
def _roles() -> list:
    from .garment_design import kb
    return [r for r in kb()["roles"] if not r.startswith("_")] + ["collar_band"]


PIECE_KEYS = {"part", "fold", "mirror", "flip_y", "cut", "grain", "place", "role", "pair"}
BUILT = ("full", "simplified")  # step 1's "build" values that are cut
PLAIN_TOL = 0.01  # a seam with no declared ease: its two sides agree within 1 % (cloth_check KINDS "plain")
CLOSURE_TOL = 0.01  # a lapped closure's over and under edges agree within 1 % (the buttons line up)


def grain(v) -> float | None:
    """A piece's grain in degrees from a number or a word (GRAIN_WORDS); None: neither."""
    if isinstance(v, str):
        return GRAIN_WORDS.get(v.strip().lower())
    return None if isinstance(v, bool) or not isinstance(v, (int, float)) else float(v)


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


FOLDED = lambda pcs: {n for n, pd in pcs.items() if isinstance(pd, dict) and pd.get("fold") and not pd.get("pair")}


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("draft_own_validate", "draft_own_block", "draft_own_gate")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C426)
