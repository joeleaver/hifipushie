"""A split module keeps its constants: `module.NAME` stays the ONE place a constant is set and read (C421).

Export scripts, specs and tests set module constants by name (HP_FS_SET="SMILE_FIT_SOFT=0", hair.SHELL_EDGE_LIFT = 0.0,
hk.FILL=1). When hair.py and faceshapes.py were split, their constants went with their sections: the scripts' values
landed on a name nothing read any more, silently. So in every split family (a module with a MODULES tuple naming the
modules it was split into) the constants live in the base module, and the other modules neither define one nor copy
one at import: they read base.NAME when they use it."""
import ast
import re
from pathlib import Path

SRC = Path(__file__).parent.parent / "src" / "hifipushie"
CONST = re.compile(r"_?[A-Z][A-Z0-9_]*$")


def const_names(node):
    """The names a top-level statement binds or changes when all of them are constants (NAME / _NAME), else None."""
    def root(x):
        while isinstance(x, (ast.Subscript, ast.Attribute, ast.Starred)):
            x = x.value
        return x.id if isinstance(x, ast.Name) and CONST.match(x.id) else None
    if isinstance(node, ast.Assign):
        flat = [e for t in node.targets for e in (t.elts if isinstance(t, (ast.Tuple, ast.List)) else [t])]
        names = [root(e) for e in flat]
        return names if all(names) else None
    if isinstance(node, (ast.AnnAssign, ast.AugAssign)):
        r = root(node.target)
        return [r] if r else None
    return None


def families() -> dict:
    out = {}
    for p in sorted(SRC.glob("*.py")):
        for node in ast.parse(p.read_text()).body:
            if isinstance(node, ast.Assign) and [getattr(t, "id", None) for t in node.targets] == ["MODULES"]:
                mods = [e.value for e in getattr(node.value, "elts", []) if isinstance(e, ast.Constant) and isinstance(e.value, str)]
                if mods and all((SRC / f"{m}.py").exists() for m in mods):
                    out[p.stem] = mods
    return out


def strays(base: str, mods: list) -> list:
    fam = {base, *mods}
    base_consts = {n for node in ast.parse((SRC / f"{base}.py").read_text()).body for n in (const_names(node) or [])}
    bad = []
    for m in mods:
        for node in ast.parse((SRC / f"{m}.py").read_text()).body:
            names = const_names(node)
            if names:
                bad.append(f"{m}.py:{node.lineno} defines {', '.join(names)}: it belongs in {base}.py")
            if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module in fam:
                copied = [a.name for a in node.names if a.name in base_consts or CONST.match(a.name)]
                if copied:
                    bad.append(f"{m}.py:{node.lineno} copies {', '.join(copied)} at import: read {base}.NAME where it is used")
    return bad


def test_split_families_are_found():
    fam = families()
    assert {"hair", "faceshapes", "base", "terrain_mesh"} <= set(fam), sorted(fam)


def test_a_split_modules_constants_stay_in_it():
    bad = [b for base, mods in families().items() for b in strays(base, mods)]
    assert not bad, "constants outside their family's base module:\n  " + "\n  ".join(bad[:40]) + \
        (f"\n  ... {len(bad) - 40} more" if len(bad) > 40 else "")
