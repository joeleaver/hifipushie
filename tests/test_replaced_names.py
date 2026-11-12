"""No test (and no module) replaces a name on a hifipushie module that the module does not bind: mock.patch.object,
monkeypatch.setattr, a dotted patch string or a plain `module.NAME = value`. After a move such a line either fails
only when its slow test runs (test_stack_lid_layers_follow_the_export_head patched sl.sp.atlas for two days after
skin_project was split: the fast suite never ran it) or, as a plain assignment, silently replaces nothing."""
import ast
from pathlib import Path

from test_undefined_names import SRC, bound

TREES = {p.stem: ast.parse(p.read_text()) for p in sorted(SRC.glob("*.py"))}
BOUND = {m: bound(t) for m, t in TREES.items()}
STAR = {m for m, t in TREES.items() if any(isinstance(n, ast.ImportFrom) and any(a.name == "*" for a in n.names) for n in t.body)}


def aliases(tree: ast.Module, inside: bool) -> dict:
    """{local name: hifipushie module} from every import in the file (also the ones inside functions)."""
    out = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and not n.module and n.level == 1 and inside or \
                isinstance(n, ast.ImportFrom) and n.module == "hifipushie" and not n.level:
            out.update({a.asname or a.name: a.name for a in n.names if a.name in TREES})
        elif isinstance(n, ast.Import):
            out.update({a.asname: a.name.split(".")[-1] for a in n.names
                        if a.asname and a.name.startswith("hifipushie.") and a.name.split(".")[-1] in TREES})
    return out


INNER = {m: aliases(t, True) for m, t in TREES.items()}


def module_of(e: ast.AST, al: dict):
    """The hifipushie module an expression names: `sl`, `hifipushie.skin`, or `sl.sp` (skin_layers' own alias)."""
    if isinstance(e, ast.Name):
        return al.get(e.id)
    if isinstance(e, ast.Attribute):
        if isinstance(e.value, ast.Name) and e.value.id == "hifipushie" and e.attr in TREES:
            return e.attr
        m = module_of(e.value, al)
        return INNER[m].get(e.attr) if m else None
    return None


def replaced_unbound(tree: ast.Module, al: dict) -> list:
    out = []

    def miss(m, name, line):
        if m and m not in STAR and name not in BOUND[m]:
            out.append(f"{line}: {m}.{name}")
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            fn = getattr(n.func, "attr", getattr(n.func, "id", ""))
            a = n.args
            if fn in ("object", "setattr", "delattr") and len(a) >= 2 and isinstance(a[1], ast.Constant) and isinstance(a[1].value, str):
                miss(module_of(a[0], al), a[1].value, n.lineno)
            if fn in ("patch", "setattr") and a and isinstance(a[0], ast.Constant) and isinstance(a[0].value, str):
                parts = a[0].value.split(".")
                if len(parts) == 3 and parts[0] == "hifipushie" and parts[1] in TREES:
                    miss(parts[1], parts[2], n.lineno)
        elif isinstance(n, (ast.Assign, ast.AugAssign, ast.AnnAssign, ast.Delete)):
            for t in n.targets if isinstance(n, (ast.Assign, ast.Delete)) else [n.target]:
                for x in t.elts if isinstance(t, (ast.Tuple, ast.List)) else [t]:
                    if isinstance(x, ast.Attribute):
                        miss(module_of(x.value, al), x.attr, n.lineno)
    return sorted(out, key=lambda s: int(s.split(":")[0]))  # (by line: ast.walk goes breadth first)


def test_the_check_sees_each_way_of_replacing_a_name():
    src = ("from unittest import mock\nfrom hifipushie import skin_layers as sl, hair\n"
           "def test_a(monkeypatch):\n"
           "    with mock.patch.object(sl.sp, 'no_such_a'), mock.patch('hifipushie.hair.no_such_b'):\n        pass\n"
           "    monkeypatch.setattr(hair, 'no_such_c', 1)\n    hair.no_such_d = 2\n"
           "    monkeypatch.setattr(hair, 'CARD_TIERS', {})\n    hair.CARD_TIERS = {}\n")
    tree = ast.parse(src)
    assert replaced_unbound(tree, aliases(tree, False)) == [
        "4: skin_project.no_such_a", "4: hair.no_such_b", "6: hair.no_such_c", "7: hair.no_such_d"]


def test_no_test_or_module_replaces_a_name_its_module_does_not_bind():
    bad = {}
    for p in sorted(Path(__file__).parent.glob("*.py")):
        tree = ast.parse(p.read_text())
        if found := replaced_unbound(tree, aliases(tree, False)):
            bad[p.name] = found
    for m, tree in TREES.items():
        if found := replaced_unbound(tree, INNER[m]):
            bad[m + ".py"] = found
    assert not bad, f"replaced on a module that does not bind them (the name moved?): {bad}"
