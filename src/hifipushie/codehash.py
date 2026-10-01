"""A digest of the code a result depends on, for caches that must never be read after a code change (the terrain
build cache, the tile export's incremental state).

`closure(roots)` follows this package's imports statically (ast: `from . import x`, `from .x import y`, `import
hifipushie.x`, including imports inside functions, which is where most lazy imports live), so a module that a build
only imports half way through is still in its closure. `digest(roots)` hashes those modules' sources, the package's
data files (*.json: quantile tables read at import) and the versions of the numeric libraries whose results the
caches hold (numpy, scipy, numba, pyfqmr, fastscapelib, scikit-image, pillow)."""

from __future__ import annotations

import ast
import hashlib
from functools import lru_cache
from pathlib import Path

PKG = Path(__file__).resolve().parent
NAME = "hifipushie"
LIBS = ("numpy", "scipy", "numba", "pyfqmr", "fastscapelib", "scikit-image", "pillow")


def _imports(mod: str) -> set[str]:
    p = PKG / f"{mod}.py"
    if not p.exists():
        return set()
    out = set()
    for node in ast.walk(ast.parse(p.read_text(), str(p))):
        if isinstance(node, ast.ImportFrom):
            if node.level >= 1 or node.module == NAME:  # from . import x / from .x import y / from hifipushie import x
                if node.module and node.module != NAME:
                    out.add(node.module.split(".")[0])
                else:
                    out.update(a.name for a in node.names)
            elif node.module and node.module.startswith(NAME + "."):
                out.add(node.module.split(".")[1])
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith(NAME + "."):
                    out.add(a.name.split(".")[1])
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.startswith(NAME + "."):
            out.add(node.value.split(".")[1])  # (__import__("hifipushie.x", ...), importlib.import_module)
    return {m for m in out if (PKG / f"{m}.py").exists()}


def closure(*roots: str) -> list[str]:
    """Package modules reachable from `roots` by import (sorted), `__init__` always included."""
    seen, todo = set(), ["__init__", *roots]
    while todo:
        m = todo.pop()
        if m in seen:
            continue
        seen.add(m)
        todo.extend(_imports(m) - seen)
    return sorted(m for m in seen if (PKG / f"{m}.py").exists())


def _versions() -> list[str]:
    from importlib import metadata
    out = []
    for lib in LIBS:
        try:
            out.append(f"{lib}={metadata.version(lib)}")
        except metadata.PackageNotFoundError:
            out.append(f"{lib}=-")
    return out


@lru_cache(maxsize=None)
def _digest(roots: tuple, stamp: tuple) -> str:
    h = hashlib.sha1()
    for m in closure(*roots):
        h.update(m.encode() + b"\0" + (PKG / f"{m}.py").read_bytes() + b"\0")
    for p in sorted(PKG.glob("*.json")):
        h.update(p.name.encode() + b"\0" + p.read_bytes() + b"\0")
    h.update("\n".join(_versions()).encode())
    return h.hexdigest()


def digest(*roots: str) -> str:
    """sha1 of the code `roots` import (transitively), the package's data files and the numeric libraries' versions.
    Re-read whenever any package file changes (keyed on their mtimes and sizes), so a long-lived process (the MCP
    server) sees edits."""
    stamp = tuple((p.name, p.stat().st_mtime_ns, p.stat().st_size) for p in sorted(PKG.glob("*.py")) +
                  sorted(PKG.glob("*.json")))
    return _digest(tuple(sorted(roots)), stamp)
