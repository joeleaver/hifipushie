"""No module reads a global name it never binds. Such a read is a NameError waiting in a body no test runs (C419:
blockin.ruler read `store` without importing it, so gnm_controls(ruler="a,b") failed on every call). A split or a
deletion that leaves a name behind fails here too."""
import ast
import builtins
import symtable
from pathlib import Path

SRC = Path(__file__).parent.parent / "src" / "hifipushie"
# __conditional_annotations__: Python's own name in a module with annotated module-level names
ALWAYS = set(dir(builtins)) | {"__file__", "__name__", "__doc__", "__spec__", "__package__", "__conditional_annotations__"}


def bound(tree: ast.Module) -> set:
    """Every name the module itself binds at its top level (also inside a top-level if / try / with / for)."""
    have = set(ALWAYS)
    for node in tree.body:
        for n in ast.walk(node) if isinstance(node, (ast.If, ast.Try, ast.With, ast.For, ast.While)) else [node]:
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                have |= {(a.asname or a.name).split(".")[0] for a in n.names}
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                have.add(n.name)
            elif isinstance(n, ast.Assign):
                have |= {x.id for t in n.targets for x in ast.walk(t) if isinstance(x, ast.Name)}
            elif isinstance(n, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr)) and isinstance(n.target, ast.Name):
                have.add(n.target.id)
            elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                have.add(n.id)
    for n in ast.walk(tree):  # a function that declares a name global and assigns it binds it too
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            g = {x for s in ast.walk(n) if isinstance(s, ast.Global) for x in s.names}
            have |= {x.id for x in ast.walk(n) if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Store) and x.id in g}
    return have


def unbound(src: str, name: str = "<module>") -> list:
    tree = ast.parse(src)
    if any(isinstance(n, ast.ImportFrom) and any(a.name == "*" for a in n.names) for n in tree.body):
        return []  # (a star import binds names this cannot see)
    have, missing = bound(tree), set()

    def walk(tb):
        for s in tb.get_symbols():
            if not s.is_referenced() or s.get_name() in have:
                continue
            if tb.get_type() == "module":
                if not s.is_assigned() and not s.is_imported():
                    missing.add(s.get_name())
            # symtable calls every table NAMED "top" module scope, so a function called top shows its locals as globals
            elif s.is_declared_global() or (s.is_global() and not s.is_local()):
                missing.add(s.get_name())
        for ch in tb.get_children():
            walk(ch)
    walk(symtable.symtable(src, name, "exec"))
    return sorted(missing)


def test_the_check_sees_a_name_read_but_never_bound():
    src = "import json\n\ndef f(x):\n    def g(y):\n        return store.load(y)\n    return json.dumps(g(x))\n"
    assert unbound(src) == ["store"]
    assert unbound("from . import store\n" + src) == []
    assert unbound("def top(mask):\n    cols = mask[1:]\n    return cols\n") == []  # (the function-called-top case)


def test_no_module_reads_a_name_it_never_binds():
    bad = {p.name: names for p in sorted(SRC.glob("*.py")) if (names := unbound(p.read_text(), p.name))}
    assert not bad, f"read as globals but never bound in their module: {bad}"
