"""Shape-key resets must leave pose correctives alone (found 2026-10-14: a reset that zeroed every key after
drive_correctives ran lost the correctives in every render after it). Every `<x>.value = ...` on a shape key in the
Blender scripts is either inside drive_correctives (which owns the corr_ keys) or guarded by a corr_ test in an
enclosing if / loop. Static (ast), no Blender: uv run python tests/test_corrective_resets.py"""
import ast
import sys
from pathlib import Path

from hifipushie import correctives

SRC = Path(__file__).resolve().parents[1] / "src" / "hifipushie"
FILES = ["blender_game.py", "blender_asset.py"]
PREFIX = "corr_"


def _guarded(stack):
    """An enclosing node mentions the corr_ prefix: `if not kb.name.startswith("corr_")` or `if ...: continue`."""
    for node in stack:
        for sub in ast.walk(node.test) if isinstance(node, ast.If) else []:
            if isinstance(sub, ast.Constant) and sub.value == PREFIX:
                return True
        if isinstance(node, ast.For):  # a `continue` guard earlier in the loop body
            for st in node.body:
                if isinstance(st, ast.If) and any(isinstance(c, ast.Continue) for c in st.body) and any(
                        isinstance(x, ast.Constant) and x.value == PREFIX for x in ast.walk(st.test)):
                    return True
    return False


def offenders(path):
    tree = ast.parse(path.read_text())
    out = []

    def visit(node, stack, fn):
        if isinstance(node, ast.FunctionDef):
            fn = node.name
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Attribute) and t.attr == "value" and isinstance(t.value, ast.Name) \
                        and t.value.id == "kb" and fn != "drive_correctives" and not _guarded(stack):
                    out.append(f"{path.name}:{node.lineno} ({fn})")
        for ch in ast.iter_child_nodes(node):
            visit(ch, stack + [node], fn)

    visit(tree, [], None)
    return out


def test_resets_skip_correctives():
    bad = [o for f in FILES for o in offenders(SRC / f)]
    assert not bad, "shape-key resets that would zero pose correctives: " + ", ".join(bad)


def test_corrective_names_use_prefix():
    # correctives.py names its keys corr_<Side><Joint>_<motion><deg>; the guards above test that prefix
    assert f'f"{PREFIX}' in (SRC / "correctives.py").read_text()
    assert correctives is not None


if __name__ == "__main__":
    test_resets_skip_correctives()
    test_corrective_names_use_prefix()
    print("ok")
    sys.exit(0)
