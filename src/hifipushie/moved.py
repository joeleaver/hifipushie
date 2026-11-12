"""Where a name went when its module was split (C427).

Scripts outside the repo (every round's working scripts, the export scripts) call the package by module name:
hair.export_hair, blockin.step, likeness.render. A split moves functions and classes to the family's other modules
(constants stay where they were: C422), and such a script then failed with a bare AttributeError. So:

  refuse(base, modules)    the module-level __getattr__ a split module installs: the AttributeError for a name that
                           moved names the module that holds it now, and the fix
  repoint(path, write)     a script's `module.NAME` uses and `from hifipushie.module import NAME` pointed at the
                           modules that hold the names now: bin/repoint <script.py> ... [--write]

A family is a module that installs the refusal (tests/test_moved.py: every module with a MODULES tuple does).
Standard library only, and nothing of the package: every split module imports this one."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

SRC = Path(__file__).parent
PKG = "hifipushie"
_TOP: dict = {}


def _names(mod: str) -> tuple[set, set]:
    """(names the module defines at its top level, names it imports there), from its source."""
    p = SRC / f"{mod}.py"
    try:
        key = (mod, p.stat().st_mtime_ns)
    except OSError:
        return set(), set()
    if key not in _TOP:
        own, imported = set(), set()
        for n in ast.parse(p.read_text()).body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                own.add(n.name)
            elif isinstance(n, (ast.Import, ast.ImportFrom)):
                imported |= {(a.asname or a.name).split(".")[0] for a in n.names}
            else:
                own |= {x.id for x in ast.walk(n) if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Store)}
        _TOP[key] = (own, imported)
    return _TOP[key]


def where(base: str, modules, name: str) -> str | None:
    """The module of the family that defines `name` now (None: no module of the family has it)."""
    for m in modules:
        if m != base and name in _names(m)[0]:
            return m
    return None


def refuse(base: str, modules):
    """The __getattr__ of a split module: `__getattr__ = moved.refuse(__name__, MODULES)`."""
    short = base.rsplit(".", 1)[-1]
    mods = tuple(modules)

    def __getattr__(name: str):
        if not name.startswith("__"):
            m = where(short, mods, name)
            if m:
                raise AttributeError(f"{short}.{name} is {m}.{name} now ({short}.py was split by responsibility); "
                                     f"`bin/repoint <script.py> --write` points a script at the new modules")
        raise AttributeError(f"module '{base}' has no attribute '{name}'")
    return __getattr__


def families() -> dict:
    """{base: [its modules]} for every module that installs the refusal, read from the sources."""
    out = {}
    for p in sorted(SRC.glob("*.py")):
        src = p.read_text()
        if "moved.refuse(" not in src:
            continue
        tuples = {}
        for n in ast.parse(src).body:
            if not isinstance(n, ast.Assign) or len(n.targets) != 1 or not isinstance(n.targets[0], ast.Name):
                continue
            if isinstance(n.value, (ast.Tuple, ast.List)):
                tuples[n.targets[0].id] = [e.value for e in n.value.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
            elif n.targets[0].id == "__getattr__" and isinstance(n.value, ast.Call) and len(n.value.args) == 2:
                a = n.value.args[1]
                mods = tuples.get(a.id, []) if isinstance(a, ast.Name) else \
                    [e.value for e in getattr(a, "elts", []) if isinstance(e, ast.Constant)]
                out[p.stem] = [m for m in mods if m != p.stem]
    return out


def files(*modules: str) -> list:
    """The source files of these modules, each with every module it was split into: for a key that hashes code by
    file name (a cache listing "skin.py" must go on hashing skin's code after skin.py is split)."""
    fam = families()
    return [f"{x}.py" for m in modules for x in (m, *fam.get(m, ()))]


# ---------------------------------------------------------------- a script pointed at the new modules
def _bound_otherwise(tree: ast.Module, name: str) -> bool:
    """`name` is also a variable, an argument or a def in the script (then `name.x` may not be the module)."""
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and n.id == name and isinstance(n.ctx, (ast.Store, ast.Del)):
            return True
        if isinstance(n, ast.arg) and n.arg == name:
            return True
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == name:
            return True
        if isinstance(n, ast.ExceptHandler) and n.name == name:
            return True
    return False


def repoint(path, write: bool = False) -> list:
    """The script's uses of names that moved, as report lines "file:line: old -> new"; with write=True the script is
    rewritten (each `alias.NAME` to `<module>.NAME`, with the module imported where the alias was; a
    `from hifipushie.x import a, b` statement split by where a and b are now). What cannot be done safely is reported
    as "by hand" and left as it is."""
    path = Path(path)
    src = path.read_text()
    tree = ast.parse(src)
    fam = families()
    lines = src.split("\n")
    report, edits, inserts, replaces = [], [], {}, []
    alias = {}          # bound name -> package module
    binders = {}        # bound name -> [import statements that bind it]
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.level == 0 and n.module == PKG:
            for a in n.names:
                alias[a.asname or a.name] = a.name
                binders.setdefault(a.asname or a.name, []).append(n)
        elif isinstance(n, ast.Import):
            for a in n.names:
                if a.name.startswith(PKG + ".") and a.asname:
                    alias[a.asname] = a.name.split(".", 1)[1]
                    binders.setdefault(a.asname, []).append(n)
        elif isinstance(n, ast.ImportFrom) and n.level == 0 and (n.module or "").startswith(PKG + "."):
            mod = n.module.split(".", 1)[1]
            if mod not in fam:
                continue
            own, imported = _names(mod)
            by = {}
            for a in n.names:
                tgt = mod if (a.name in own or a.name in imported or a.name == "*") else where(mod, fam[mod], a.name)
                if tgt is None:
                    report.append(f"{path}:{n.lineno}: {mod}.{a.name} is in no module of {mod}'s family: by hand")
                    tgt = mod
                elif tgt != mod:
                    report.append(f"{path}:{n.lineno}: from {PKG}.{mod} import {a.name} -> from {PKG}.{tgt} import {a.name}")
                by.setdefault(tgt, []).append(a)
            if set(by) != {mod}:
                ind = " " * n.col_offset
                replaces.append((n.lineno, n.end_lineno, [ind + ast.unparse(ast.ImportFrom(module=f"{PKG}.{t}", names=by[t], level=0))
                                                          for t in sorted(by)]))
    skip = {y for y in alias if _bound_otherwise(tree, y)}
    need = {}           # alias -> modules to import where it is bound
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in alias):
            continue
        y, mod = n.value.id, alias[n.value.id]
        if mod not in fam or n.attr.startswith("__"):
            continue
        own, imported = _names(mod)
        if n.attr in own or n.attr in imported:
            continue
        tgt = where(mod, fam[mod], n.attr)
        if tgt is None:
            report.append(f"{path}:{n.lineno}: {mod}.{n.attr} is in no module of {mod}'s family: by hand")
        elif y in skip:
            report.append(f"{path}:{n.lineno}: {mod}.{n.attr} is {tgt}.{n.attr} now, but `{y}` is also a variable in this "
                          f"script: by hand")
        elif _bound_otherwise(tree, tgt):
            report.append(f"{path}:{n.lineno}: {mod}.{n.attr} is {tgt}.{n.attr} now, but `{tgt}` is a variable in this "
                          f"script: by hand")
        else:
            report.append(f"{path}:{n.lineno}: {y}.{n.attr} -> {tgt}.{n.attr}")
            edits.append((n.value.lineno, n.value.col_offset, n.value.end_col_offset, tgt))
            need.setdefault(y, set()).add(tgt)
    if not write or not (edits or replaces):
        return report
    for y, mods in need.items():
        have = {a.asname or a.name for st in ast.walk(tree) if isinstance(st, ast.ImportFrom) and st.level == 0
                and st.module == PKG for a in st.names}
        add = sorted(mods - have)
        for st in binders[y] if add else []:
            inserts.setdefault(st.end_lineno, (" " * st.col_offset, set()))[1].update(add)
    for ln, c0, c1, text in sorted(set(edits), reverse=True):
        b = lines[ln - 1].encode()
        lines[ln - 1] = (b[:c0] + text.encode() + b[c1:]).decode()
    ops = [(end, "ins", [f"{ind}from {PKG} import {', '.join(sorted(mods))}"]) for end, (ind, mods) in inserts.items()] + \
          [(l1, "rep", (l0, new)) for l0, l1, new in replaces]
    for at, kind, val in sorted(ops, key=lambda o: (-o[0], o[1] == "rep")):
        if kind == "ins":
            lines[at:at] = val
        else:
            lines[val[0] - 1:at] = val[1]
    new = "\n".join(lines)
    ast.parse(new)  # (never write a script that no longer parses)
    path.write_text(new)
    return report


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    write = "--write" in argv
    paths = [a for a in argv if not a.startswith("--")]
    if not paths:
        print("usage: bin/repoint <script.py> ... [--write]\n" + __doc__.split("\n\n")[1])
        return 2
    total = 0
    for p in paths:
        try:
            rep = repoint(p, write)
        except (OSError, SyntaxError, UnicodeDecodeError) as e:
            print(f"{p}: not read ({type(e).__name__}: {e})")
            continue
        total += len(rep)
        for line in rep:
            print(line)
    done = "rewritten" if write else "to rewrite (--write does it)"
    print(f"{total} uses of moved names in {len(paths)} script(s): {done}; lines marked `by hand` are left as they are")
    return 0


if __name__ == "__main__":
    sys.exit(main())
