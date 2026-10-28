"""THE DESIGN TOOLS' CONTRACT IS STRICT (trials lesson 4, codified C241): every key a design call takes is checked when
design_garment / alter_pattern is called, and an unknown one is an error that names the valid ones with their units,
sign and default. Blind trial agents spent ~5 rounds per garment learning what the tools accept from silent drops and
tracebacks (hoodie t6: a sleeve op's "ease" ignored, "biceps width 346 mm (ease 5%)" unchanged; reshape "move"
passed design_garment and failed at look_pattern "missing 1 required positional argument: 'by'". Shirt t7: Simon's
lengthBonus 0.05 REPLACED the 0.25 default and two probes cut 17 cm; move's y axis (up) unstated, the first move went
14 cm the wrong way; round_corner silently ignored as a design op on a Simon draft and refused as an alteration;
"expected 2, got 1" naming no argument; ~22 of ~29 design / alteration rounds were tool friction).

The valid sets come from the code, so a new op or option is covered without edits here:
  - draft ops (pattern_draft.OPS, filled by pattern_draft / pattern_styles / pattern_tailor / pattern_jacket): each op
    function's named parameters, plus the keys its **kwargs are read by (o.get("k"), o["k"], "k" in o; followed into
    the functions it forwards them to). An op whose kwargs escape where the scan can't follow (stored whole, passed
    to a builtin) gets its keys from KWARGS_FROM (computed from code too: the sleeve's from SLEEVE_DEFAULTS + the
    sleeve draft's reads). An op still unresolved is "open" (accepts any key) and tests/test_design_contract.py fails
    on it: an open op is the silent drop this module exists to end.
  - block options: pattern_blocks.*_DEFAULTS + the keys each block function reads.
  - FreeSewing options: freesewing_options.json (each design's patternConfig.options, dumped by
    refresh_freesewing_options; FreeSewing's own units: a pct option is a FRACTION, 0.25 = 25 %).
  - alteration ops: pattern.ALTER_OPS (the table pattern.apply dispatches on).
  - design-sheet keys: garment_design.SHEET_KEYS; detail params: DETAIL_PARAM_KEYS.

Errors read: '<where> ops[3] (sleeve): unknown key "ease"; sleeve takes: biceps_ease (fraction of the biceps
girth, + = roomier; default 0.15), ...'. A FreeSewing option set on the sheet is reported in design_garment's output as
REPLACING its default ("lengthBonus 0.05 replaces the default 0.25 (FreeSewing pct 25): total 0.05").
"""
from __future__ import annotations

import ast
import functools
import inspect
import json
import textwrap
from pathlib import Path

FS_OPTIONS_PATH = Path(__file__).with_name("freesewing_options.json")
DETAIL_PARAM_KEYS = {"options": "raw options of the draft source (FreeSewing designs only; a drafted design takes "
                                "block_options or the op's params)",
                     "op": "params laid over the detail's own draft op (drafted designs)",
                     "generate": "params laid over the detail's generated band (height m, ratio, ...)",
                     "trim": "params laid over the detail's trims (buttons...)"}
# op keys every op takes: "op" (its kind), "source" (provenance, popped by pattern_draft.apply)
OP_META = {"op", "source"}

# units and sign of the parameter NAMES the ops share (pattern coordinates: metres, x right / outward from centre,
# y UP: +y toward the neck on a bodice, toward the cap on a sleeve; pattern.py, pattern_blocks.py)
PARAM_DOC = {
    "piece": "piece name", "pieces": "piece names (list)", "point": "named point on the piece's outline",
    "corner": "named point (the corner)", "edge": 'edge "a>b" or an edge name', "edges": "edge names (list)",
    "line": "line name or [[x, y], [x, y]] (m) or two point names", "name": "name given to what the op makes",
    "by": "[dx, dy] m in pattern coordinates: x right (out from centre), y UP (toward the neck / the cap)",
    "amount": "m (+ = more cloth)", "width": "m", "height": "m", "depth": "m",
    "length": "m, or a body level name (sleeve: short / elbow / three_quarter / long)",
    "radius": "m", "falloff": "m (how far along the outline the move fades out)", "drop": "m (down)",
    "angle": "deg", "deg": "deg", "spread_deg": "deg", "n": "count", "ratio": "fraction (band / edge length)",
    "share": "fraction", "overlap": "m", "stand": "m", "rise": "m (up)", "spacing": "m", "gap": "m",
    "tack": "m", "x": "m from centre", "y": "m (pattern y, up)", "up": "m (up)", "down": "m (down)",
    "front": "m the centre front is lowered", "back": "m the centre back is lowered",
    "widen": "m the neck point moves out along the shoulder", "break_y": "m (pattern y of the lapel break)",
    "biceps_ease": "fraction of the biceps girth (+ = roomier)", "cap_ease": "fraction of the armhole (cap over armhole)",
    "wrist_ease": "fraction of the wrist girth", "length_bonus": "fraction of the sleeve length ADDED (+ = longer)",
    "cap_height": "fraction of the armhole depth", "hem_width": "m (finished)",
    "chest_ease": "fraction of the chest girth (+ = roomier)", "waist_ease": "fraction of the waist girth",
    "hips_ease": "fraction of the hip girth", "seat_ease": "fraction of the seat girth",
    "collar_ease": "fraction of the neck girth", "shoulder_ease": "fraction of the shoulder width",
    "armhole_depth": "fraction of waist-to-armpit (+ = deeper)", "rise_ease": "m added to the rise",
    "waist_drop": "m the top sits below the natural waist", "flare": "m added at the hem per side",
    "underarm": "m below the armpit", "band_width": "m", "front_neck": "m (front neck depth)",
}


# where a block option's name means something else than the op parameter of that name
BLOCK_DOC = {"length_bonus": "m ADDED to the bodice length (+ = longer)",
             "length": 'a body level {"to": "waist" | "hips" | "seat" | "crotch", "below": m}, a level name, or m '
                       "below the neck point at CB",
             "cb": "fold | seam | open", "cf": "fold | seam | open", "neckline": "upper_loop | ring | crew",
             "fitted": "true / false", "darts": "true / false", "bust_dart": "true / false / null (auto)",
             "across_back": "fraction of the shoulder width", "across_front": "fraction of the shoulder width",
             "back_neck": "fraction of the neck girth", "front_balance": '"auto" or m',
             "shoulder_from": '"seam" (the neck point to shoulder tape) or null',
             "knee": "m (finished half girth) or null", "hem": "m (finished half girth) or null",
             "rise": "m or null (from the body)", "back_dart": "m (intake)", "dart_length": "m or null",
             "dart_taper": "fraction", "leg": "skinny | slim | tapered | straight | wide | null"}


class ContractError(ValueError):
    pass


# ---------------------------------------------------------------- reading what a function accepts


def _lit(node):
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except Exception:
        return ast.unparse(node)


@functools.lru_cache(maxsize=None)
def _fn_tree(fn):
    src = textwrap.dedent(inspect.getsource(fn))
    tree = ast.parse(src).body[0]
    parents = {}
    for p in ast.walk(tree):
        for c in ast.iter_child_nodes(p):
            parents[c] = p
    return tree, parents


def _resolve(expr, glb):
    """A call's target as a Python function (a module-level name or module.attr), else None."""
    try:
        if isinstance(expr, ast.Name):
            f = glb.get(expr.id)
        elif isinstance(expr, ast.Attribute) and isinstance(expr.value, ast.Name):
            f = getattr(glb.get(expr.value.id), expr.attr, None)
        else:
            return None
    except Exception:
        return None
    return f if inspect.isfunction(f) else None


def _named_params(fn) -> dict:
    """{name: default (inspect.Parameter.empty when required)} of fn's keyword-passable parameters, D excluded."""
    out = {}
    for i, p in enumerate(inspect.signature(fn).parameters.values()):
        if i == 0 and p.name == "D":
            continue
        if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY):
            out[p.name] = p.default
    return out


def _var_kw(fn) -> str | None:
    return next((p.name for p in inspect.signature(fn).parameters.values() if p.kind == p.VAR_KEYWORD), None)


def dict_keys(fn, var: str, _seen=None) -> tuple[dict, list]:
    """The string keys fn reads off its dict variable `var` ({key: default or None}) and the uses the scan can't
    follow (escapes: the dict stored whole, iterated, passed to a builtin)."""
    _seen = set() if _seen is None else _seen
    if (fn, var) in _seen:
        return {}, []
    _seen.add((fn, var))
    try:
        tree, parents = _fn_tree(fn)
    except (OSError, TypeError, SyntaxError):
        return {}, [f"{getattr(fn, '__name__', fn)}: no source"]
    glb = fn.__globals__
    keys, esc = {}, []

    def add(k, d=None):
        if k not in keys or keys[k] is None:
            keys[k] = d

    for n in ast.walk(tree):
        if not (isinstance(n, ast.Name) and n.id == var and isinstance(n.ctx, ast.Load)):
            continue
        p = parents.get(n)
        if isinstance(p, ast.Attribute) and p.attr in ("get", "pop", "setdefault"):
            c = parents.get(p)
            if isinstance(c, ast.Call) and c.func is p and c.args and isinstance(c.args[0], ast.Constant) \
                    and isinstance(c.args[0].value, str):
                add(c.args[0].value, _lit(c.args[1]) if len(c.args) > 1 else None)
                continue
        if isinstance(p, ast.Subscript) and p.value is n and isinstance(p.slice, ast.Constant) \
                and isinstance(p.slice.value, str):
            add(p.slice.value)
            continue
        if isinstance(p, ast.Compare) and n in p.comparators and isinstance(p.left, ast.Constant) \
                and all(isinstance(o_, (ast.In, ast.NotIn)) for o_ in p.ops):
            add(p.left.value)
            continue
        kvar = (p.slice if isinstance(p, ast.Subscript) and p.value is n else
                p.left if isinstance(p, ast.Compare) and n in p.comparators else None)
        if isinstance(kvar, ast.Name):
            # {k: o[k] for k in CUTAWAY if k in o}: the keys of the module table the comprehension walks
            got = None
            for up in ast.walk(tree):
                if isinstance(up, ast.comprehension) and isinstance(up.target, ast.Name) and up.target.id == kvar.id \
                        and isinstance(up.iter, ast.Name):
                    tbl = glb.get(up.iter.id)
                    if isinstance(tbl, (dict, list, tuple, set)) and all(isinstance(x, str) for x in tbl):
                        got = tbl
            if got is not None:
                for x in got:
                    add(x, got.get(x) if isinstance(got, dict) else None)
                continue
        if isinstance(p, ast.Attribute) and p.attr == "items":
            # {k: v for k, v in o.items() if k in ("from", "to", ...)}: the keys the filter lets through
            c = parents.get(p)
            comp = parents.get(c) if isinstance(c, ast.Call) else None
            ok = False
            if isinstance(comp, ast.comprehension) and isinstance(comp.target, ast.Tuple) and comp.target.elts:
                kn = comp.target.elts[0]
                for cond in comp.ifs:
                    if isinstance(cond, ast.Compare) and isinstance(cond.left, ast.Name) and isinstance(kn, ast.Name) \
                            and cond.left.id == kn.id and isinstance(cond.ops[0], ast.In) \
                            and isinstance(cond.comparators[0], (ast.Tuple, ast.List, ast.Set)):
                        for e in cond.comparators[0].elts:
                            if isinstance(e, ast.Constant) and isinstance(e.value, str):
                                add(e.value)
                        ok = True
            if ok:
                continue
        # (`**(o or {})`, `o or {}`: the same dict)
        q, node_ = p, n
        if isinstance(q, ast.BoolOp):
            node_, q = q, parents.get(q)
        if isinstance(q, ast.keyword) and q.arg is None:
            call = parents.get(q)
            f = _resolve(call.func, glb) if isinstance(call, ast.Call) else None
            if f is not None:
                for k, d in _named_params(f).items():
                    add(k, None if d is inspect.Parameter.empty else d)
                vk = _var_kw(f)
                if vk:
                    k2, e2 = dict_keys(f, vk, _seen)
                    for k, d in k2.items():
                        add(k, d)
                    esc += e2
                continue
        if isinstance(q, ast.Call) and node_ in q.args:
            f = _resolve(q.func, glb)
            if f is not None and f.__name__ == "refuse_unknown":
                # (pattern_tailor.refuse_unknown(op, o, allowed): the op refuses any kwarg outside `allowed` itself)
                al = q.args[2] if len(q.args) > 2 else next((kw.value for kw in q.keywords if kw.arg == "allowed"), None)
                for x in (_lit(al) or ()) if al is not None else ():
                    if isinstance(x, str):
                        add(x)
                keys["__closed__"] = True  # (no free label key either: the op itself refuses it)
                continue
            if f is not None:
                ps = list(inspect.signature(f).parameters)
                i = q.args.index(node_)
                if i < len(ps):
                    k2, e2 = dict_keys(f, ps[i], _seen)
                    for k, d in k2.items():
                        add(k, d)
                    esc += e2
                    continue
        esc.append(f"{fn.__name__}: {ast.unparse(p)[:80]}")
    return keys, esc


# kwargs that escape where the scan can't follow, read from code all the same
def _sleeve_keys() -> dict:
    from . import pattern_blocks as pb
    k, _ = dict_keys(pb.sleeve, "o")
    out = dict(pb.SLEEVE_DEFAULTS)
    out.update({x: d for x, d in k.items() if x not in out})
    # (op_sleeve lays the block's biceps ease under the op's; a knit's cap takes no ease)
    out["biceps_ease"] = "the block's biceps_ease (bodice 0.15, knit 0.05)"
    out["cap_ease"] = f"{pb.SLEEVE_DEFAULTS['cap_ease']} (knit 0.0)"
    return out


def _waistband_keys() -> dict:
    from . import pattern_draft as pdm
    k, _ = dict_keys(pdm.unfold, "wb")  # (op_waistband stores its kwargs whole; unfold reads them)
    return k


KWARGS_FROM = {"sleeve": _sleeve_keys, "waistband": _waistband_keys}


@functools.lru_cache(maxsize=None)
def _op_table_cached(ops_key: tuple) -> dict:
    from . import pattern_draft as pdm
    out = {}
    for kind, fn in pdm.OPS.items():
        named = _named_params(fn)
        params = {k: {"required": d is inspect.Parameter.empty, "default": None if d is inspect.Parameter.empty else d}
                  for k, d in named.items()}
        vk = _var_kw(fn)
        open_ = False
        if vk:
            if kind in KWARGS_FROM:
                extra, esc = KWARGS_FROM[kind](), []
            else:
                extra, esc = dict_keys(fn, vk)
            for k, d in extra.items():
                if not k.startswith("_") and k not in params:
                    params[k] = {"required": False, "default": d}
            open_ = bool(esc)
            if "name" not in params and not extra.get("__closed__"):  # (a label: garment_design keys ops by kind + name; harmless where unread)
                params["name"] = {"required": False, "default": None}
        out[kind] = {"params": params, "open": open_, "escapes": esc if vk else [],
                     "module": fn.__module__.rsplit(".", 1)[-1], "doc": (fn.__doc__ or "").strip().split("\n")[0]}
    out["unfold"] = {"params": {}, "open": False, "escapes": [], "module": "pattern_draft",
                     "doc": "unfold the half pieces into whole ones now (it runs at the end anyway)"}
    return out


def op_table() -> dict:
    """{op kind: {"params": {name: {"required", "default"}}, "open", "escapes", "module", "doc"}} for every
    registered draft op (pattern_draft.OPS as it is now: ops registered later are read then)."""
    from . import pattern_draft as pdm
    return _op_table_cached(tuple(sorted((k, id(f)) for k, f in pdm.OPS.items())))


def _fmt_param(name: str, e: dict, docs: dict | None = None) -> str:
    bits = []
    doc = (docs or {}).get(name) or PARAM_DOC.get(name)
    if doc:
        bits.append(doc)
    bits.append("REQUIRED" if e.get("required") else f"default {e.get('default')!r}")
    return f"{name} ({'; '.join(bits)})"


def takes(kind: str) -> str:
    """'<kind> takes: a (...), b (...)' for a draft op."""
    t = op_table().get(kind)
    if t is None:
        return ""
    ps = t["params"]
    req = [k for k, e in ps.items() if e["required"]]
    opt = sorted(k for k, e in ps.items() if not e["required"])
    return f"{kind} takes: " + ", ".join(_fmt_param(k, ps[k]) for k in req + opt)


def check_ops(ops, where: str = "design") -> None:
    """Every draft op known, every parameter known to it, every required one given."""
    if ops is None:
        return
    if not isinstance(ops, list):
        raise ContractError(f'{where} ops is a list of {{"op": kind, params...}}, got {type(ops).__name__}')
    T = op_table()
    for i, op in enumerate(ops):
        at = f"{where} ops[{i}]"
        if not isinstance(op, dict) or "op" not in op:
            raise ContractError(f'{at}: an op is {{"op": kind, params...}}, got {op!r}')
        kind = op["op"]
        if kind not in T:
            alt = ""
            from . import pattern
            if kind in pattern.ALTER_OPS:
                alt = (f" ({kind!r} is an ALTERATION op: alter_pattern, or the garment key \"alter\", on the drafted "
                       "pieces)")
            raise ContractError(f"{at}: unknown draft op {kind!r}{alt}; draft ops: {', '.join(sorted(T))}")
        t = T[kind]
        given = set(op) - OP_META
        if not t["open"]:
            bad = sorted(given - set(t["params"]))
            if bad:
                raise ContractError(f"{at} ({kind}): unknown key{'s' if len(bad) > 1 else ''} "
                                    + ", ".join(f'"{b}"' for b in bad) + f"; {takes(kind)}")
        miss = [k for k, e in t["params"].items() if e["required"] and k not in op]
        if miss:
            raise ContractError(f"{at} ({kind}): missing " + ", ".join(f'"{m}"' for m in miss) + f"; {takes(kind)}")


# ---------------------------------------------------------------- block options


def block_options(block: str) -> dict:
    """{option: default} a block takes: its *_DEFAULTS + every key its draft function reads."""
    from . import pattern_blocks as pb
    if block in ("bodice", "knit"):
        base = dict(pb.BODICE_DEFAULTS)
        if block == "knit":
            base.update(pb.KNIT_DEFAULTS)
        fn = pb.bodice
    elif block == "trouser":
        base, fn = dict(pb.TROUSER_DEFAULTS), pb.trouser
    elif block == "skirt":
        base, fn = dict(pb.SKIRT_DEFAULTS), pb.skirt
    else:
        return {}
    k, _ = dict_keys(fn, "o")
    for x, d in k.items():
        if not x.startswith("_"):
            base.setdefault(x, d)
    return base


def check_block_options(block: str, bo, where: str = "design") -> None:
    if not bo:
        return
    if not isinstance(bo, dict):
        raise ContractError(f"{where} block_options is {{option: value}}, got {type(bo).__name__}")
    have = block_options(block)
    if not have:
        return
    bad = sorted(set(bo) - set(have) - {"source"})
    if bad:
        raise ContractError(f"{where} block_options: unknown for the {block} block: " + ", ".join(f'"{b}"' for b in bad)
                            + f"; the {block} block takes: "
                            + ", ".join(_fmt_param(k, {"default": v}, BLOCK_DOC) for k, v in sorted(have.items())))


# ---------------------------------------------------------------- FreeSewing options


@functools.lru_cache(maxsize=1)
def _fs_table(mtime: float) -> dict:
    return json.loads(FS_OPTIONS_PATH.read_text())


def fs_options(design: str) -> dict | None:
    """{option: {type, default, min, max, list}} of a FreeSewing design (None: not in the table)."""
    if not FS_OPTIONS_PATH.exists():
        return None
    return _fs_table(FS_OPTIONS_PATH.stat().st_mtime).get(design)


def _fs_doc(k: str, e: dict) -> str:
    t = e.get("type")
    if t == "pct":
        return (f"{k} (fraction, default {e['default']:g} = FreeSewing pct {e['default'] * 100:g}, "
                f"{e['min']:g}..{e['max']:g}; a value REPLACES the default)")
    if t in ("deg", "mm", "count"):
        return f"{k} ({t}, default {e['default']}, {e.get('min')}..{e.get('max')})"
    if t == "bool":
        return f"{k} (true / false, default {str(e['default']).lower()})"
    if t == "list":
        return f"{k} (one of {', '.join(map(str, e.get('list') or []))}; default {e.get('default')})"
    return f"{k} (default {e.get('default')!r})"


def check_fs_options(design: str, opts, where: str = "design") -> None:
    if not opts:
        return
    T = fs_options(design)
    if T is None:
        return
    if not isinstance(opts, dict):
        raise ContractError(f"{where} options is {{FreeSewing option: value}}, got {type(opts).__name__}")
    bad = sorted(set(opts) - set(T))
    if bad:
        near = [k for k in T if any(b.lower()[:5] in k.lower() for b in bad)]
        raise ContractError(f"{where}: {design} has no option " + ", ".join(f'"{b}"' for b in bad)
                            + (f" (close: {', '.join(near[:8])})" if near else "")
                            + f"; {design}'s options: " + "; ".join(_fs_doc(k, T[k]) for k in sorted(T)))
    for k, v in opts.items():
        e = T[k]
        if e.get("type") == "list" and e.get("list") and v not in e["list"]:
            raise ContractError(f"{where}: {design} option {k} is one of {', '.join(map(str, e['list']))}, got {v!r}")
        if e.get("type") == "bool" and not isinstance(v, bool):
            raise ContractError(f"{where}: {design} option {k} is true / false, got {v!r}")
        if e.get("type") in ("pct", "deg", "mm", "count") and (isinstance(v, bool) or not isinstance(v, (int, float))):
            raise ContractError(f"{where}: {design} option {k} is a number ({_fs_doc(k, e)}), got {v!r}")


def fs_replacements(design: str, opts: dict, table_opts: dict | None = None) -> list:
    """One line per option the garment sets: what it replaces (lesson 4: lengthBonus 0.05 replaced the default 0.25,
    shirt t7 cut 17 cm in two probes)."""
    T = fs_options(design) or {}
    out = []
    for k, v in (opts or {}).items():
        e = T.get(k)
        if not e:
            continue
        d = (table_opts or {}).get(k, e.get("default"))
        src = "the design table's" if table_opts and k in table_opts else "FreeSewing's default"
        if v == d:
            continue
        if e.get("type") == "pct" and isinstance(v, (int, float)) and isinstance(d, (int, float)):
            rng = "" if e["min"] <= v <= e["max"] else f" (outside FreeSewing's {e['min']:g}..{e['max']:g})"
            out.append(f"{k} {v:g} replaces {src} {d:g} (pct {d * 100:g}): total {v:g}{rng}")
        elif v != d:
            out.append(f"{k} {v!r} replaces {src} {d!r}")
    return out


def refresh_freesewing_options(designs=None) -> dict:
    """Re-dump freesewing_options.json from the FreeSewing pack (Node + the pack; run when the pack changes)."""
    import shutil
    import subprocess
    from . import assets, freesewing
    pack = assets.pack("freesewing")
    if designs is None:
        from .cloth import designs as cdesigns
        designs = sorted(k for k, v in cdesigns().items() if not k.startswith("_") and isinstance(v, dict)
                         and (pack / "node_modules" / "@freesewing" / k).exists())
    script = Path(__file__).with_name("freesewing_option_table.mjs")
    run = pack / "option_table.mjs"
    shutil.copyfile(script, run)
    r = subprocess.run([freesewing._node(), str(run), *designs], capture_output=True, text=True, cwd=pack, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-1500:])
    out = json.loads(r.stdout)
    FS_OPTIONS_PATH.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    return out


# ---------------------------------------------------------------- the design sheet and the compiled garment


def check_sheet(sheet: dict, where: str = "design", route: bool = True) -> None:
    """What garment_design.validate adds: detail params, the draft's ops and block options, the FreeSewing options,
    truing keys; route=True also refuses ops / block options / raw options on a route that never runs them.
    (garment_design.validate, run on EVERY save, passes route=False: a model saved before the contract with dead ops
    on a FreeSewing draft, trial_shirt_t7, keeps saving its fits; design_garment, where the sheet is being written,
    refuses them.)"""
    from . import garment_design as gd
    K = gd.kb()
    kind = sheet.get("kind")
    kd = K["kinds"].get(kind) or {}
    fr = sheet.get("from")
    drafted = fr == "draft" or (fr is None and (sheet.get("block") or kd.get("draft")))
    for d, v in (sheet.get("details") or {}).items():
        if isinstance(v, dict):
            bad = sorted(set(v) - {"type"} - set(DETAIL_PARAM_KEYS))
            if bad:
                raise ContractError(f"{where} details.{d}: unknown key{'s' if len(bad) > 1 else ''} "
                                    + ", ".join(f'"{b}"' for b in bad) + "; a detail is {\"type\": choice, "
                                    + ", ".join(f'"{k}": {doc}' for k, doc in DETAIL_PARAM_KEYS.items()) + "}")
            if route and drafted and v.get("options"):
                raise ContractError(f"{where} details.{d}.options: raw options are a FreeSewing draft's; this design is "
                                    "drafted from a block: give block_options, or the detail's \"op\" params")
            if route and not drafted and v.get("op"):
                raise ContractError(f"{where} details.{d}.op: op params run only on a drafted design (block + ops); "
                                    f"{fr} is a FreeSewing draft: use its options (details.{d}.options) or alter_pattern")
    if route and not drafted:
        for k in ("ops", "block_options", "block"):
            if sheet.get(k):
                what = {"ops": "draft ops", "block_options": "block options", "block": "a block"}[k]
                raise ContractError(
                    f"{where} {k}: {what} run only on a design drafted from a block (\"from\": \"draft\", \"block\": "
                    f"bodice | knit | trouser | skirt); this one is drafted by {fr} (FreeSewing), which never runs them "
                    "(shirt t7: round_corner on a Simon draft saved with no error and did nothing). On a FreeSewing "
                    "draft: its options (\"pattern\": {\"options\": {...}}, or a detail's \"options\") or alteration "
                    "ops on the drafted pieces (alter_pattern: " + ", ".join(_alter_names()) + "). Remove it: design={\"" + k
                    + "\": null}")
    for k in ("auto_true", "tie"):
        if sheet.get(k) is not None and not isinstance(sheet[k], bool):
            raise ContractError(f"{where} {k} is true / false, got {sheet[k]!r}")
    check_truing_corners(sheet.get("truing_corners"), where)
    comp = gd.compile_sheet(sheet)
    check_pattern(comp.get("pattern"), where, route)


def _alter_names() -> list:
    from . import pattern
    return list(pattern.ALTER_OPS)


def check_truing_corners(v, where: str) -> None:
    if v is None:
        return
    if not (isinstance(v, list) and all(isinstance(x, str) for x in v)):
        raise ContractError(f"{where} truing_corners is a list of seam-end labels that are corners by design (as the "
                            "truing row prints them, e.g. \"collar:standTip\"), got " + repr(v)[:80]
                            + "; to true every failing seam end use \"auto_true\": true")


def check_pattern(pat, where: str = "garment", route: bool = True) -> None:
    """A compiled garment's pattern: a draft's block + options + ops, or a FreeSewing draft's options."""
    if not isinstance(pat, dict):
        return
    fr = pat.get("from")
    if fr == "draft":
        if route and pat.get("options"):
            raise ContractError(f"{where} pattern.options: a drafted design takes block_options and op params; "
                                "\"options\" are a FreeSewing draft's raw options and would be dropped")
        check_block_options(pat.get("block") or "bodice", pat.get("block_options"), where)
        check_ops(pat.get("ops"), where)
    elif fs_options(fr) is not None:
        check_fs_options(fr, pat.get("options"), f"{where} pattern.options")


def check_garment(g: dict, where: str = "garment", design: bool = True) -> None:
    """The garment as design_garment / alter_pattern will save it: garment keys, the alteration ops and (design=True,
    design_garment) the sheet and the compiled pattern, route included. All checked before anything is saved."""
    from . import cloth, garment_design as gd, pattern
    for k in ("auto_true",):
        if g.get(k) is not None and not isinstance(g[k], bool):
            raise ContractError(f"{where} {k} is true / false, got {g[k]!r}")
    check_truing_corners(g.get("truing_corners"), where)
    if design:
        if g.get("design"):
            gd.validate(g["design"], where)
            check_sheet(g["design"], where, route=True)
        check_pattern(cloth.expanded(g).get("pattern"), where)
    if g.get("alter") is not None:
        pattern.check_alter(g["alter"], f"{where} alter")


def design_notes(g: dict) -> list:
    """Lines for design_garment's output: what each option the garment sets replaces."""
    from . import cloth
    try:
        gx = cloth.expanded(g)
    except Exception:
        return []
    pat = gx.get("pattern") or {}
    fr = pat.get("from")
    out = []
    if fs_options(fr) is not None:
        tbl = (cloth.designs().get(fr) or {}).get("options") or {}
        opts = dict(pat.get("options") or {})
        words = (cloth.designs().get(fr) or {}).get("words", {})
        for k, v in pat.items():  # (design words: "length" -> lengthBonus ...)
            if k in words and k != "ease" and isinstance(words[k], str):
                opts[words[k]] = v
        for k, v in (pat.get("ease") or {}).items():
            if k in words.get("ease", {}):
                opts[words["ease"][k]] = v
        out += fs_replacements(fr, opts, tbl)
    elif fr == "draft":
        have = block_options(pat.get("block") or "bodice")
        for k, v in (pat.get("block_options") or {}).items():
            if k in have and have[k] is not None and v != have[k] and k != "length_bonus":
                out.append(f"block {k} {v!r} replaces the default {have[k]!r}")
    return out
