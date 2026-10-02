"""FreeSewing drafts (MIT; the assets pack "freesewing": npm tarballs of 4.10.2) run in Node, cached by content.

`draft(design, measurements_mm, options, sa)` -> {"parts": {name: {"points", "paths", "snippets"}}, "cutlist", "logs"}
in FreeSewing's own units (mm, y down). Drafts are cached on disk (`<HOME>/_cache/freesewing/<key>.json`), so a model
whose draft is cached needs neither Node nor the pack. `freesewing_draft.mjs` is copied into the pack directory and
run there: Node's ES modules resolve packages from the script's own directory (NODE_PATH is ignored for imports).
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).with_name("freesewing_draft.mjs")
NODE_MIN = 20


def _cache_dir() -> Path:
    from . import store
    d = store.HOME / "_cache" / "freesewing"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _node() -> str:
    node = shutil.which("node")
    if not node:
        raise RuntimeError(f"cloth drafts from FreeSewing need Node.js >= {NODE_MIN} on PATH (https://nodejs.org); "
                           "it isn't installed. Drafts already cached still work.")
    v = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip().lstrip("v")
    if int(v.split(".")[0] or 0) < NODE_MIN:
        raise RuntimeError(f"FreeSewing needs Node.js >= {NODE_MIN} (have {v})")
    return node


def key(design: str, measurements: dict, options: dict, sa: float) -> str:
    from . import assets
    ver = next((f["path"] for f in assets.manifest()["freesewing"]["files"] if "core" in f["path"]), "")
    blob = json.dumps([design, measurements, options, sa, ver, hashlib.sha1(SCRIPT.read_bytes()).hexdigest()],
                      sort_keys=True, default=float)
    return hashlib.sha1(blob.encode()).hexdigest()[:20]


def draft(design: str, measurements: dict, options: dict | None = None, sa: float = 10.0) -> dict:
    options = dict(options or {})
    measurements = {k: float(v) for k, v in measurements.items()}
    k = key(design, measurements, options, sa)
    path = _cache_dir() / f"{k}.json"
    if path.exists():
        return json.loads(path.read_text())
    from . import assets
    pack = assets.pack("freesewing")  # says how to fetch it when missing
    run = pack / "draft.mjs"
    if not run.exists() or run.read_bytes() != SCRIPT.read_bytes():
        run.write_bytes(SCRIPT.read_bytes())
    if not (pack / "node_modules" / "@freesewing" / design).exists():
        have = sorted(p.name for p in (pack / "node_modules" / "@freesewing").iterdir())
        raise ValueError(f"no FreeSewing design {design!r} in the pack (have {', '.join(have)})")
    req = json.dumps({"design": design, "measurements": measurements, "options": options, "sa": sa})
    r = subprocess.run([_node(), str(run)], input=req, capture_output=True, text=True, cwd=pack, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"FreeSewing {design} failed: {r.stderr.strip()[-1500:]}")
    out = json.loads(r.stdout)
    errs = out.get("logs", {}).get("error")
    if errs:
        raise ValueError(f"FreeSewing {design}: " + "; ".join(errs[:5]))
    path.write_text(json.dumps(out))
    return out
