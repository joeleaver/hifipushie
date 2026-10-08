"""Built terrains cached on disk: a second export, look or check of the same spec (and the same code) skips the
build (terrain.load: 50-150 s on the bigger maps; a cached one loads in about a second).

Keyed by the spec's content without its 3D-only sections (`THREE_D`: caves, volumes, export, views, styles, which only the
tile export and the views read), the saved terrain kinds (kinds.json: a kind the designer defined changes how its spec
builds) and `codehash.digest("terrain")`: the source of every module the build imports, so a cache entry can't be
read after a code change. The build itself never sees the 3D sections (they are attached after it, cached or not),
so a hit and a miss give the same terrain by construction, and editing a cave or an arch reuses the build.

Entries are zlib-compressed pickles (t3_alps: 128 MB pickled, 39 MB on disk) in $HIFIPUSHIE_TERRAIN_CACHE (else
$XDG_CACHE_HOME/hifipushie/terrain, else ~/.cache/hifipushie/terrain), capped at $HIFIPUSHIE_TERRAIN_CACHE_GB (default
1.5): the least recently used entries go first. HIFIPUSHIE_TERRAIN_CACHE=0 turns the disk cache off."""

from __future__ import annotations

import hashlib
import json
import os
import pickle
import time
import zlib
from pathlib import Path

THREE_D = ("caves", "volumes", "export", "views", "styles")
SUFFIX = ".terrain.z"
_STATS = {"hits": 0, "misses": 0, "last": None}


def directory() -> Path | None:
    v = os.environ.get("HIFIPUSHIE_TERRAIN_CACHE")
    if v in ("0", "off", "false", "none"):
        return None
    if v:
        return Path(v)
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "hifipushie" / "terrain"


def cap_gb() -> float:
    return float(os.environ.get("HIFIPUSHIE_TERRAIN_CACHE_GB", "1.5"))


def key(spec: dict) -> str:
    from . import codehash
    from .terrain_world import _user_kinds
    flat = {k: v for k, v in spec.items() if k not in THREE_D}
    kinds, _ = _user_kinds()
    h = hashlib.sha1()
    h.update(json.dumps(flat, sort_keys=True).encode())
    h.update(b"\0kinds\0" + json.dumps(kinds, sort_keys=True).encode())
    h.update(b"\0code\0" + codehash.digest("terrain").encode())
    return h.hexdigest()


def _attach(T, spec: dict):
    """The 3D-only sections onto a terrain built without them (in the spec's units, as normalise gives them)."""
    from .terrain import normalise
    full = normalise(spec)
    for k in THREE_D:
        if k in full:
            T.spec[k] = full[k]
        else:
            T.spec.pop(k, None)
    T.source = spec
    return T


def _register_kind(T):
    """A mixture ("crater + coast") or a saved kind lives only in the building process's KINDS table: a terrain loaded
    from the cache in a fresh process must put it back, or its report fails (KeyError 'crater+coast')."""
    from . import terrain_world as tw
    k = (getattr(T, "world", None) or {}).get("kind")
    if not k or k in tw.KINDS:
        return
    parts = k.split("+")
    if len(parts) > 1:
        keys = [tw.kind_of(p) for p in parts]
        if all(keys):
            tw.mix(keys)
    else:
        tw.kind_of(k, (T.spec or {}).get("kinds"))


def build(spec: dict, log=None):
    """The Terrain for `spec`: from the disk cache when this spec (minus its 3D sections) was built by this code
    before, else built and cached. Raises terrain_world.Questions like Terrain()."""
    from .terrain import Terrain
    d = directory()
    flat = {k: v for k, v in spec.items() if k not in THREE_D}
    if d is None:
        return _attach(Terrain(flat), spec)
    k = key(spec)
    f = d / f"{k}{SUFFIX}"
    if f.exists():
        try:
            t0 = time.time()
            T = pickle.loads(zlib.decompress(f.read_bytes()))
            os.utime(f)  # (least recently used goes first)
            _STATS["hits"] += 1
            _STATS["last"] = {"hit": True, "file": str(f), "mb": round(f.stat().st_size / 1e6, 1),
                              "load_s": round(time.time() - t0, 2)}
            if log:
                log(f"terrain build from the cache ({_STATS['last']['mb']} MB, {_STATS['last']['load_s']} s)")
            _register_kind(T)
            return _attach(T, spec)
        except Exception as e:  # (a truncated or foreign file: rebuilt)
            if log:
                log(f"terrain cache entry unreadable ({e}): rebuilding")
    t0 = time.time()
    T = Terrain(flat)
    took = time.time() - t0
    _STATS["misses"] += 1
    try:
        d.mkdir(parents=True, exist_ok=True)
        blob = zlib.compress(pickle.dumps(T, protocol=pickle.HIGHEST_PROTOCOL), 1)
        tmp = f.with_name(f"{f.name}.{os.getpid()}.tmp")
        tmp.write_bytes(blob)
        os.replace(tmp, f)
        pruned = prune()
        _STATS["last"] = {"hit": False, "file": str(f), "mb": round(len(blob) / 1e6, 1), "build_s": round(took, 1),
                          "pruned": pruned, "cache_mb": round(size_mb(), 1)}
        if log:
            log(f"terrain built in {took:.0f} s, cached ({_STATS['last']['mb']} MB; cache {_STATS['last']['cache_mb']}"
                f" MB of {cap_gb():g} GB{', pruned ' + str(pruned) if pruned else ''})")
    except OSError as e:  # (a full disk must not fail the build)
        if log:
            log(f"terrain cache not written: {e}")
    return _attach(T, spec)


def entries() -> list[Path]:
    d = directory()
    return sorted(d.glob(f"*{SUFFIX}"), key=lambda p: p.stat().st_mtime) if d and d.exists() else []


def size_mb() -> float:
    return sum(p.stat().st_size for p in entries()) / 1e6


def prune(cap: float | None = None) -> int:
    """Deletes the least recently used entries until the cache is under `cap` GB (and stray temp files); returns how
    many went."""
    cap = cap_gb() if cap is None else cap
    d = directory()
    n = 0
    if d and d.exists():
        for t in d.glob("*.tmp"):
            if time.time() - t.stat().st_mtime > 3600:
                t.unlink(missing_ok=True)
    es = entries()
    total = sum(p.stat().st_size for p in es)
    for p in es:  # (oldest first; the newest entry always stays)
        if total <= cap * 1e9 or p is es[-1]:
            break
        total -= p.stat().st_size
        p.unlink(missing_ok=True)
        n += 1
    return n


def stats() -> dict:
    return {**_STATS, "dir": str(directory()), "entries": len(entries()), "cache_mb": round(size_mb(), 1),
            "cap_gb": cap_gb()}
