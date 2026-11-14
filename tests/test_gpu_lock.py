"""Every environment render (terrain views, plant looks, clutter looks) takes the machine's GPU lock (C445).

They ran Blender bare: two at once, or one beside a character render, shared the iGPU with the desktop (the laptop has
gone down under that). resources.heavy(..., gpu=True) is the queue every other render waits in; nested in a heavy job
of the same thread it claims the GPU alone, so a tool that already holds one does not wait on itself."""
import ast
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "hifipushie"
SITES = ("terrain_views.py", "veg_look.py", "clutter_kit.py")


def blender_runs(path: Path) -> list[tuple[int, bool]]:
    """[(line, inside `with resources.heavy(..., gpu=True)`)] for every Blender batch run in the module."""
    out, held = [], []

    class V(ast.NodeVisitor):
        def visit_With(self, node):
            ok = any(isinstance(i.context_expr, ast.Call) and ast.unparse(i.context_expr.func) == "resources.heavy"
                     and any(k.arg == "gpu" and isinstance(k.value, ast.Constant) and k.value.value is True
                             for k in i.context_expr.keywords) for i in node.items)
            held.append(ok)
            self.generic_visit(node)
            held.pop()

        def visit_Call(self, node):
            if ast.unparse(node.func) in ("subprocess.run", "resources.run") and '"-b"' in ast.unparse(node).replace("'", '"'):
                out.append((node.lineno, any(held)))
            self.generic_visit(node)
    V().visit(ast.parse(path.read_text()))
    return out


def test_every_environment_render_takes_the_gpu_lock():
    for f in SITES:
        runs = blender_runs(SRC / f)
        assert runs, f"{f}: no Blender run found (the rule reads subprocess.run / resources.run with -b)"
        assert all(ok for _, ok in runs), f"{f}: a Blender run outside resources.heavy(..., gpu=True): {runs}"


def test_the_rule_sees_a_bare_run(tmp_path):
    bare = tmp_path / "m.py"
    bare.write_text('import subprocess\nfrom . import resources\n'
                    'def a():\n    subprocess.run(["blender", "-b", "x"])\n'
                    'def b():\n    with resources.heavy("x", gb=1):\n        subprocess.run(["blender", "-b", "x"])\n'
                    'def c():\n    with resources.heavy("x", gb=1, gpu=True):\n        resources.run([B, "-b", "x"])\n')
    assert [ok for _, ok in blender_runs(bare)] == [False, False, True]
