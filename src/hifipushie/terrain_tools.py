"""Terrain specs on disk and built in memory, for the MCP tools (set_terrain, check_terrain, look_terrain,
export_terrain, terrain_history). A terrain lives in workspace/terrain/<name>/: spec.json (the source of truth),
history/ (every version), and what the tools write (map.png, masks.png, views, export/).

A build is cached by the spec's content, so check, look and export after a set don't rebuild. A spec whose kind needs
the designer's answers is still saved: the questions come back as data, and the next set carries the answers.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import threading
import time
import warnings
from pathlib import Path

from . import store

warnings.filterwarnings("ignore", message="Mean of empty slice")  # (an empty region reports n/a, not numpy's noise)
warnings.filterwarnings("ignore", message="invalid value encountered")

_LOCKS: dict[str, threading.Lock] = {}
_BUILT: dict[str, tuple[str, object]] = {}  # name -> (spec hash, Terrain)


def home() -> Path:
    return store.HOME / "terrain"


def _dir(name: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", name):
        raise ValueError("terrain names may only contain letters, digits, _ and -")
    return home() / name


def _lock(name):
    return _LOCKS.setdefault(name, threading.Lock())


def list_terrains() -> list[str]:
    return sorted(p.parent.name for p in home().glob("*/spec.json"))


def load(name: str) -> dict:
    p = _dir(name) / "spec.json"
    if not p.exists():
        raise ValueError(f"no terrain {name!r}; existing: {list_terrains()}")
    return json.loads(p.read_text())


def merge(base: dict, patch: dict) -> dict:
    """JSON merge patch: objects merge key by key, null deletes, anything else replaces."""
    out = copy.deepcopy(base)
    for k, v in patch.items():
        if v is None:
            out.pop(k, None)
        elif isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def save(name: str, spec: dict, note: str = "") -> int:
    d = _dir(name)
    (d / "history").mkdir(parents=True, exist_ok=True)
    version = len(list((d / "history").glob("*.json"))) + 1
    entry = {"version": version, "time": time.strftime("%Y-%m-%d %H:%M:%S"), "note": note, "spec": spec}
    (d / "history" / f"{version:04d}.json").write_text(json.dumps(entry, indent=1))
    (d / "spec.json").write_text(json.dumps(spec, indent=1))
    return version


def history(name: str) -> list[dict]:
    out = []
    for p in sorted((_dir(name) / "history").glob("*.json")):
        e = json.loads(p.read_text())
        out.append({k: e[k] for k in ("version", "time", "note")})
    return out


def version_spec(name: str, version: int) -> dict:
    p = _dir(name) / "history" / f"{version:04d}.json"
    if not p.exists():
        raise ValueError(f"{name} has no version {version}")
    return json.loads(p.read_text())["spec"]


def _hash(spec) -> str:
    return hashlib.sha1(json.dumps(spec, sort_keys=True).encode()).hexdigest()


def build(name: str):
    """The built Terrain for the stored spec (cached by content). Raises terrain_world.Questions when the designer has
    to answer something first."""
    from . import terrain
    from .terrain_world import save_kind
    spec = load(name)
    h = _hash(spec)
    with _lock(name):
        got = _BUILT.get(name)
        if got and got[0] == h:
            return got[1]
        T = terrain.Terrain(spec)
        if T.new_kind:
            save_kind(T.new_kind)
        _BUILT[name] = (h, T)
        return T


def questions_data(q) -> str:
    """Questions for the designer, as JSON the caller relays (never answers itself)."""
    d = q.data()
    d["instructions"] = ("Relay to the designer: first what can't be built, then the questions in their own terms. Don't "
                         "answer for them. Put their answers in world.answers and set_terrain again.")
    return json.dumps({"status": "questions for the designer", **d}, indent=1)


def report(name: str) -> str:
    from .terrain_world import Questions
    try:
        T = build(name)
    except Questions as q:
        return questions_data(q)
    head = "saved kind for next time: " + T.new_kind + "\n" if T.new_kind else ""
    return head + T.report()
