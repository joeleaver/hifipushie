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


def test_the_skin_reference_tool_gives_its_text():
    """(the case above, at the tool) the description's keys from skin.py's docstring, the marks' text from
    skin_features.py's, and nothing of the paragraph that says where the code is."""
    from hifipushie import server
    text = server.skin_reference()
    assert text.startswith("ZONES") and 'spec["skin"] = {' in text and "tattoo" in text
    assert "Where the code is" not in text and "moved.refuse" not in text
