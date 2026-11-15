"""A name that moved when its module was split says where it is now, and bin/repoint rewrites a script (C427).

Working scripts outside the repo call the package by module name (hair.export_hair, blockin.step). The splits moved
those functions; the scripts then failed with a bare AttributeError and nothing said where the function was."""
import ast
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from hifipushie import moved

ROOT = Path(__file__).parent.parent
SRC = ROOT / "src" / "hifipushie"


def test_a_moved_name_says_where_it_is_and_how_to_fix_the_script():
    from hifipushie import hair
    with pytest.raises(AttributeError) as e:
        hair.export_hair
    assert "hair_export.export_hair" in str(e.value) and "bin/repoint" in str(e.value)
    with pytest.raises(AttributeError) as e:  # a name no module of the family has: the plain error
        hair.no_such_name_anywhere
    assert "bin/repoint" not in str(e.value)
    assert getattr(hair, "no_such_name_anywhere", None) is None and not hasattr(hair, "__no_such_dunder__")
    assert hair.SHELL_CARD_VALUE is not None  # (a constant is still read at hair.NAME: C422)


def test_every_split_module_installs_the_refusal():
    """A module with a MODULES tuple was split: it installs moved.refuse over exactly those modules."""
    fam = moved.families()
    split = {}
    for p in sorted(SRC.glob("*.py")):
        for node in ast.parse(p.read_text()).body:
            if isinstance(node, ast.Assign) and [getattr(t, "id", None) for t in node.targets] == ["MODULES"]:
                split[p.stem] = [e.value for e in node.value.elts if e.value != p.stem]
    assert len(split) >= 14 and "server" in fam
    missing = sorted(set(split) - set(fam))
    assert not missing, f"split modules without `__getattr__ = moved.refuse(__name__, MODULES)`: {missing}"
    assert all(fam[b] == mods for b, mods in split.items())
    # every function and class of a family's other modules is found from its base
    for base, mods in split.items():
        for m in mods:
            for node in ast.parse((SRC / f"{m}.py").read_text()).body:
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name not in moved._names(base)[0]:
                    assert moved.where(base, fam[base], node.name) is not None, (base, m, node.name)


SCRIPT = '''import sys
from hifipushie import hair, blockin as bi
from hifipushie.likeness import render, CHECKLIST
import hifipushie.terrain as tr

def run(m):
    from hifipushie import face_ruler as fr
    T = tr.Terrain({})
    return hair.export_hair(m, "out"), bi.step(m), fr.read(m), hair.SHELL_CARD_VALUE, render, T, tr.PROFILES

def other(hair):
    return hair.scalp
'''


def test_repoint_rewrites_a_script(tmp_path):
    p = tmp_path / "work.py"
    p.write_text(SCRIPT)
    rep = moved.repoint(p)
    assert p.read_text() == SCRIPT  # (a dry run changes nothing)
    text = "\n".join(rep)
    assert "bi.step -> blockin_steps.step" in text and "fr.read -> face_ruler_solve.read" in text
    assert "tr.Terrain -> terrain_model.Terrain" in text
    assert "from hifipushie.likeness import render -> from hifipushie.likeness_render import render" in text
    assert "`hair` is also a variable in this script: by hand" in text  # (a parameter is called hair: left alone)
    moved.repoint(p, write=True)
    new = p.read_text()
    tree = ast.parse(new)
    assert "bi.step(" not in new and "blockin_steps.step(m)" in new and "face_ruler_solve.read(m)" in new
    assert "from hifipushie.likeness_render import render" in new and "from hifipushie.likeness import CHECKLIST" in new
    assert "tr.PROFILES" in new and "hair.SHELL_CARD_VALUE" in new  # (constants did not move)
    assert "hair.export_hair(m" in new  # (by hand: not touched)
    # each module the script now names is imported in a scope that sees its use
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run")
    inner = {a.name for n in ast.walk(fn) if isinstance(n, ast.ImportFrom) for a in n.names}
    top = {a.asname or a.name for n in tree.body if isinstance(n, ast.ImportFrom) and n.module == "hifipushie" for a in n.names}
    assert "face_ruler_solve" in inner and {"blockin_steps", "terrain_model"} <= top | inner
    assert all("by hand" in line for line in moved.repoint(p))  # nothing left that the tool can do


def test_bin_repoint_runs_without_the_environment(tmp_path):
    p = tmp_path / "w.py"
    p.write_text("from hifipushie import blockin\nprint(blockin.step)\n")
    r = subprocess.run([sys.executable, "-I", str(ROOT / "bin" / "repoint"), str(p)], capture_output=True, text=True)
    assert r.returncode == 0 and "blockin.step -> blockin_steps.step" in r.stdout, r.stdout + r.stderr
    spec = importlib.util.spec_from_file_location("moved_alone", SRC / "moved.py")
    assert spec is not None


def test_no_script_in_the_repo_names_a_moved_name():
    """The repo's own scripts too (spikes/, examples/, bin/). Slow tests import helpers from spikes/; the splits
    rewrote the package and the tests but not those scripts, and seven slow test files failed on a moved name for two
    days before one ran (C428). A split runs bin/repoint over them; this test says when one was left behind."""
    fam = moved.families()
    left = []
    for d in ("spikes", "examples", "bin"):
        for p in sorted((ROOT / d).rglob("*.py")):
            try:
                left += [line for line in moved.repoint(p, fam=fam) if " -> " in line]
            except (SyntaxError, UnicodeDecodeError):
                pass
    assert not left, "scripts that name a function where it used to be (bin/repoint <script> --write):\n  " + "\n  ".join(left[:20])


def own_source_reads(src: str) -> list:
    """Lines where a module reads its own docstring, or reads its own file whole (a code key over this file alone)."""
    out = []
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Name) and n.id == "__doc__" and isinstance(n.ctx, ast.Load):
            out.append(f"{n.lineno}: __doc__")
        elif (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ("read_bytes", "read_text")
              and any(isinstance(x, ast.Name) and x.id == "__file__" for x in ast.walk(n.func.value))
              and not any(isinstance(x, ast.Attribute) and x.attr in ("with_name", "parent") for x in ast.walk(n.func.value))):
            out.append(f"{n.lineno}: {n.func.attr} of __file__")
    return sorted(out, key=lambda s: int(s.split(":")[0]))


def test_a_split_off_module_reads_no_docstring_or_source_of_its_own():
    """A function moved out of its file takes the names it reads with it, but __doc__ and __file__ stay the module's
    own: skin_reference's text quoted skin.py's docstring through a bare __doc__ and was an IndexError for two days
    after the split (no test called the tool, and every syntax tree was equal); veg_leaf's atlas cache hashed
    Path(__file__), which became one file of five. The docstring is the base's (<base>.__doc__); a code key is
    moved.files(<base>)."""
    assert own_source_reads('def f():\n    return __doc__.split("x")\n') == ["2: __doc__"]
    assert own_source_reads("from pathlib import Path\nk = Path(__file__).read_bytes()\n") == ["2: read_bytes of __file__"]
    assert own_source_reads("from pathlib import Path\ns = Path(__file__).with_name('a.json').read_text()\n"
                            "d = skin.__doc__\nh = (Path(__file__).parent / f).read_bytes()\n") == []
    bad = {}
    for base, mods in moved.families().items():
        for m in mods:
            p = SRC / f"{m}.py"
            if p.exists() and (found := own_source_reads(p.read_text())):
                bad[p.name] = found
    assert not bad, f"reads its own docstring or hashes only its own file, in a module split off another: {bad}"


def read_by_its_other_name(src: str) -> list:
    """`function line N: reads M where only ALIAS was imported`: one function imports one module under two names, and
    a line reads one of them on a path where only the other was certainly imported (both branches of an `if` count; a
    loop's, a handler's or a case's body counts for itself only; nested functions are functions of their own)."""
    skip = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)

    def bound(node) -> set:
        return {(a.asname or a.name) for a in node.names}

    def groups(fn) -> list:
        names = {}

        def walk(node):
            for ch in ast.iter_child_nodes(node):
                if isinstance(ch, skip):
                    continue
                if isinstance(ch, (ast.Import, ast.ImportFrom)):
                    mod = f"{'.' * ch.level}{ch.module or ''}:" if isinstance(ch, ast.ImportFrom) else ":"
                    for a in ch.names:
                        names.setdefault(mod + a.name, set()).add(a.asname or a.name)
                walk(ch)

        walk(fn)
        return [g for g in names.values() if len(g) > 1]

    def reads(node, have, gs, out):
        if isinstance(node, skip):
            return
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id not in have:
            for g in gs:
                if node.id in g and (g - {node.id}) & have:
                    out.append((node.lineno, node.id, sorted((g - {node.id}) & have)[0]))
        for ch in ast.iter_child_nodes(node):
            reads(ch, have, gs, out)

    def run(stmts, have, gs, out) -> set:
        have = set(have)
        for s in stmts:
            if isinstance(s, skip):
                continue
            if isinstance(s, (ast.Import, ast.ImportFrom)):
                have |= bound(s)
            elif isinstance(s, ast.If):
                reads(s.test, have, gs, out)
                have = run(s.body, have, gs, out) & run(s.orelse, have, gs, out)
            elif isinstance(s, (ast.For, ast.AsyncFor, ast.While)):
                reads(s.test if isinstance(s, ast.While) else s.iter, have, gs, out)
                run(s.body, have, gs, out)
                run(s.orelse, have, gs, out)
            elif isinstance(s, (ast.With, ast.AsyncWith)):
                for it in s.items:
                    reads(it.context_expr, have, gs, out)
                have = run(s.body, have, gs, out)
            elif isinstance(s, ast.Try):
                run(s.orelse, run(s.body, have, gs, out), gs, out)
                for h in s.handlers:
                    run(h.body, have, gs, out)
                have = run(s.finalbody, have, gs, out)
            elif isinstance(s, ast.Match):
                reads(s.subject, have, gs, out)
                for c in s.cases:
                    run(c.body, have, gs, out)
            else:
                reads(s, have, gs, out)
        return have

    found = []
    for fn in ast.walk(ast.parse(src)):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and (gs := groups(fn)):
            out = []
            run(fn.body, set(), gs, out)
            found += [f"{fn.name} line {ln}: reads {n} where only {other} was imported" for ln, n, other in sorted(set(out))]
    return found


def test_no_function_reads_a_module_by_a_name_its_path_did_not_import():
    """An import inside a function makes its name a local of the WHOLE function. cards_job imported hair_clumps under
    its own name on the clumps path and as `_hk` in two later blocks; the split of hair_clumps wrote those blocks'
    `_hk.ARCH` as `hair_clumps.ARCH` (a constant is read by its module's name) and left `import hair_clumps as _hk`,
    so they read a local that only the clumps path had bound: UnboundLocalError for every strand groom cut by lock at
    the tiers main / npc / far, for four days (C477). No name was undefined for a reader of the file, every moved
    unit was unchanged, and no test ran the job (tests/test_hair_cards_job.py does now)."""
    old = ("def job(clumped):\n    if clumped:\n        from . import hair_clumps\n        hair_clumps.cut()\n"
           "    if not clumped:\n        from . import hair_clumps as _hk\n        return hair_clumps.ARCH, _hk.strands\n")
    assert read_by_its_other_name(old) == ["job line 7: reads hair_clumps where only _hk was imported"]
    assert read_by_its_other_name(old.replace(" as _hk", "").replace("_hk.", "hair_clumps.")) == []
    assert read_by_its_other_name("def f(a):\n    if a:\n        import json as _js\n        _js.dumps(1)\n"
                                  "    else:\n        import json\n        json.dumps(1)\n") == []
    bad = {}
    for p in sorted(SRC.glob("*.py")) + sorted((ROOT / "tests").glob("*.py")):
        if found := read_by_its_other_name(p.read_text()):
            bad[p.name] = found
    assert not bad, f"a module read by a name this path did not import (import it where it is read, under ONE name): {bad}"


def test_the_skin_reference_tool_gives_its_text():
    """(the case above, at the tool) the description's keys from skin.py's docstring, the marks' text from
    skin_features.py's, and nothing of the paragraph that says where the code is."""
    from hifipushie import server
    text = server.skin_reference()
    assert text.startswith("ZONES") and 'spec["skin"] = {' in text and "tattoo" in text
    assert "Where the code is" not in text and "moved.refuse" not in text
