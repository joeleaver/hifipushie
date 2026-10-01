"""Incremental tile export: after a spec edit, only the tiles the edit can reach are meshed, decimated and baked
again; every other tile's files are left as they are on disk (terrain_mesh.export_tiles).

The rule is the invariant: an incremental export equals a cold export of the same spec, byte for byte (the manifest's
timing fields aside). So nothing is decided from the spec. Each tile's work is keyed by the inputs it actually reads:

- the FIELD KEY of a tile: everything the export's field, materials, cliff region, bake fields and detail projection
  read inside the tile's box grown by MARGIN (the AO's 6.4 m reach, the bake's surface search, fallen blocks seated
  from cells 4 m off, the detail's 1.5 m normal average, gutters, the pushed heightmap's ball; 24 m covers them with
  room). `Fingerprint` walks those objects: arrays on a known grid (the terrain's cells [iy, ix], the cliff region's
  heightmap lattice [ix, iy], `_gridded` spline coefficients) are cropped to the window (+3 cells for the cubic
  B-spline's support); volumes (tubes, mounds) count where their reach box meets the window, in their order;
  everything else (scalars, settings, non-grid arrays, the swatch) is GLOBAL: when it changes, every tile is redone
  (and the export says what changed). A type it can't fingerprint turns incremental off (cold, with the reason).
- the later stages chain on it: a tile's dense LOD 0 on its field key plus its canonical border vertices (positions,
  normals, and their order where welds use it), its border collapses on that plus which of its border vertices each
  LOD keeps, its LODs/maps/GLBs on that plus the border vertices' weights, colours, skirt depths and directions, and
  the texel density. The parent's global steps (canonical border vertices, chains, which vertices each LOD keeps,
  skirts, density) always run in full, exactly as a cold export runs them, so a changed tile whose shared chain moved
  changes its unchanged neighbour's key too, and the neighbour is redone: the border rule needs no special case.

State lives in <out>/_incremental/state.pkl (written at the end of every export, deleted at the start: an export that
dies leaves a cold one next). Code changes make it cold (`codehash.digest("terrain_mesh")`)."""

from __future__ import annotations

import hashlib
import os
import pickle
import types
from functools import partial
from pathlib import Path

import numpy as np

FORMAT = 2
MARGIN = 24.0  # m: how far past a tile's box anything its outputs read can lie (see the docstring)
PAD = 3  # cells round a window: a cubic B-spline reads +-2, nearest/linear +-1
STATE = "_incremental/state.pkl"
OUT_DIRS = ("maps", "heightmaps", "splats")  # the export's per-tile files live at the top and in these


def _h(*parts) -> str:
    h = hashlib.sha1()
    for p in parts:
        h.update(_bytes(p))
        h.update(b"\x1f")
    return h.hexdigest()


def _bytes(p) -> bytes:
    if isinstance(p, bytes):
        return p
    if isinstance(p, np.ndarray):
        a = np.ascontiguousarray(p)
        return f"{a.dtype.str}{a.shape}".encode() + a.tobytes()
    if isinstance(p, float):
        return p.hex().encode()
    return repr(p).encode()


class Frame:
    """A grid's place in the world: arrays whose first two dims are `shape`, indexed [iy, ix] ("yx") or [ix, iy]
    ("xy"), node (a, b) at (x0 + a dx, y0 + b dy)."""

    def __init__(self, name, shape, order, x0, y0, d):
        self.name, self.shape, self.order = name, tuple(int(s) for s in shape), order
        self.x0, self.y0, self.d = float(x0), float(y0), float(d)

    def window(self, lo, hi):
        """Index slices (axis 0, axis 1) of the nodes a point in [lo, hi] can read."""
        def rng(a, b, o, n):
            i0 = int(np.floor((a - o) / self.d)) - PAD
            i1 = int(np.ceil((b - o) / self.d)) + PAD + 1
            return max(0, min(i0, n)), max(0, min(i1, n))
        nx, ny = (self.shape[1], self.shape[0]) if self.order == "yx" else self.shape
        ix = rng(lo[0], hi[0], self.x0, nx)
        iy = rng(lo[1], hi[1], self.y0, ny)
        return (iy, ix) if self.order == "yx" else (ix, iy)


def vol_box(v, pad):
    """The plan box a volume can change the export's field in (its own reach box, the cliff shell's grown void box
    round it: terrain_cliffs.CliffField._boxes)."""
    lo, hi = np.asarray(v.lo, float), np.asarray(v.hi, float)
    if hasattr(v, "nodes"):
        r = float(np.max(np.maximum(v.rw, v.rh))) + 2.0 + pad
        lo, hi = np.minimum(lo, v.nodes.min(0) - r), np.maximum(hi, v.nodes.max(0) + r)
    else:
        lo, hi = lo - pad, hi + pad
    return lo[:2], hi[:2]


class Fingerprint:
    """What a tile export's outputs depend on, split into a global part and per-tile windows (see the docstring).
    roots: {name: object} walked; frames: grids whose arrays are cropped; vols: the field's volume list (its order is
    the field's)."""

    # T: the terrain object (what the export reads of it is passed as roots of its own); _bx: CliffField's void boxes,
    # made lazily from the volumes (which count per tile)
    SKIP_ATTRS = {"T", "_bx"}

    def __init__(self, roots: dict, frames: list[Frame], vols: list, vol_pad: float):
        self.frames = frames
        self.vols = list(vols)
        self._vol_ids = {id(v) for v in self.vols}
        self.arrays = []  # (path, array, [frames])
        self.unknown = []
        self._seen, self._keep = {}, []
        self.parts = {}
        for name in sorted(roots):  # (per root and its first-level members: the log can say which one changed)
            o = roots[name]
            kids = None
            if isinstance(o, dict):
                kids = [(repr(k), o[k]) for k in sorted(o, key=repr)]
            elif (type(o).__module__ or "").startswith("hifipushie") and not isinstance(o, type) and \
                    id(o) not in self._vol_ids and hasattr(o, "__dict__"):
                kids = [(k, v) for k, v in sorted(vars(o).items()) if k not in self.SKIP_ATTRS]
            if kids is None or id(o) in self._seen:
                h = hashlib.sha1()
                self._walk(o, name, h)
                self.parts[name] = h.hexdigest()
                continue
            self._seen[id(o)] = name
            self._keep.append(o)
            h = hashlib.sha1()
            self._walk(type(o), f"{name}.__class__", h)
            self.parts[f"{name}.__class__"] = h.hexdigest()
            for k, v in kids:
                h = hashlib.sha1()
                self._walk(v, f"{name}.{k}", h)
                self.parts[f"{name}.{k}"] = h.hexdigest()
        self.global_key = _h(*sorted(self.parts.items()))
        self.vol_keys = []
        for n, v in enumerate(self.vols):  # (whole: a volume's own arrays are its nodes and radii)
            sub = Fingerprint.__new__(Fingerprint)
            sub.frames, sub.vols, sub._vol_ids, sub.arrays, sub.unknown = [], [], set(), [], []
            sub._seen, sub._keep = {}, []
            h = hashlib.sha1()
            sub._walk(v, f"vol{n}", h)
            self.unknown += sub.unknown
            self.vol_keys.append(h.hexdigest())
        self.vol_boxes = [vol_box(v, vol_pad) for v in self.vols]

    # ---- the walk
    def _tok(self, h, *t):
        h.update(_bytes(t))

    def _walk(self, o, path, h):
        if o is None or isinstance(o, (bool, int, str, bytes, complex)):
            return self._tok(h, type(o).__name__, o)
        if isinstance(o, float):
            return self._tok(h, "f", o.hex())
        if isinstance(o, np.generic):
            return self._tok(h, "np", o.dtype.str, o.tobytes())
        if isinstance(o, (types.ModuleType, types.BuiltinFunctionType, np.ufunc)):
            return self._tok(h, "named", getattr(o, "__name__", repr(o)))
        if id(o) in self._vol_ids:
            return  # (volumes count per tile, never globally)
        if id(o) in self._seen:
            return self._tok(h, "ref", self._seen[id(o)])
        self._seen[id(o)] = path
        self._keep.append(o)  # (alive until the walk ends: a freed temporary's id reused would read as a "ref")
        if isinstance(o, np.ndarray):
            if o.dtype == object:
                self._tok(h, "objarray", o.shape)
                for n, x in enumerate(o.ravel()):
                    self._walk(x, f"{path}[{n}]", h)
                return
            fr = [f for f in self.frames if o.ndim >= 2 and o.shape[:2] == f.shape]
            if fr:
                self.arrays.append((path, o, fr))
                return self._tok(h, "grid", path, o.dtype.str, o.shape)
            return self._tok(h, "array", o)
        if isinstance(o, dict):
            self._tok(h, "dict", len(o))
            for k in sorted(o, key=repr):
                self._tok(h, "key", repr(k))
                self._walk(o[k], f"{path}.{k}", h)
            return
        if isinstance(o, (list, tuple)):
            items = [x for x in o if id(x) not in self._vol_ids]
            self._tok(h, type(o).__name__, len(items))
            for n, x in enumerate(items):
                self._walk(x, f"{path}[{n}]", h)
            return
        if isinstance(o, (set, frozenset)):
            self._tok(h, "set", sorted(repr(x) for x in o))
            return
        if isinstance(o, partial):
            self._tok(h, "partial")
            for n, x in enumerate((o.func, o.args, o.keywords)):
                self._walk(x, f"{path}.p{n}", h)
            return
        if isinstance(o, types.MethodType):
            self._tok(h, "method", o.__func__.__qualname__)
            return self._walk(o.__self__, f"{path}.self", h)
        if isinstance(o, types.FunctionType):
            # (its code is in the code digest; what it closes over is data)
            self._tok(h, "fn", o.__module__, o.__qualname__)
            fr = getattr(o, "frame", None)  # (terrain_mesh._gridded: a spline over its own grid)
            if isinstance(fr, Frame):
                self.arrays.append((f"{path}.grid", o.grid, [fr]))
                self._tok(h, "gridfn", fr.x0, fr.y0, fr.d, fr.order, fr.shape)
                return
            self._walk(o.__defaults__, f"{path}.defaults", h)
            self._walk(o.__kwdefaults__, f"{path}.kwdefaults", h)
            for name, cell in zip(o.__code__.co_freevars, o.__closure__ or ()):
                try:
                    v = cell.cell_contents
                except ValueError:
                    v = "<empty cell>"
                self._walk(v, f"{path}.{name}", h)
            if o.__dict__:
                self._walk(dict(o.__dict__), f"{path}.__dict__", h)
            return
        if isinstance(o, type):
            self._tok(h, "class", o.__module__, o.__qualname__)
            if "<locals>" in o.__qualname__:  # (a class made in a function: its body closes over data)
                for k in sorted(o.__dict__):
                    if not k.startswith("__"):
                        self._walk(o.__dict__[k], f"{path}.{k}", h)
            return
        mod = type(o).__module__ or ""
        if mod.startswith("hifipushie"):
            self._tok(h, "obj", type(o).__qualname__)
            self._walk(type(o), f"{path}.__class__", h)
            for k in sorted(vars(o)):
                if k not in self.SKIP_ATTRS:
                    self._walk(vars(o)[k], f"{path}.{k}", h)
            return
        self.unknown.append(f"{path}: {type(o).__module__}.{type(o).__qualname__}")
        self._tok(h, "unknown", type(o).__qualname__)

    # ---- per tile
    def tile(self, lo, hi):
        """(key, {input path: digest}) of a tile [lo, hi] (plan, m)."""
        wlo, whi = np.asarray(lo, float) - MARGIN, np.asarray(hi, float) + MARGIN
        parts = {}
        for path, a, frs in self.arrays:
            sl = None
            for f in frs:  # (several grids of one shape: the union of their windows)
                w = f.window(wlo, whi)
                sl = w if sl is None else tuple((min(p[0], q[0]), max(p[1], q[1])) for p, q in zip(sl, w))
            sub = a[sl[0][0]:sl[0][1], sl[1][0]:sl[1][1]]
            parts[path] = _h(sl, sub)
        vk = [self.vol_keys[n] for n, (a, b) in enumerate(self.vol_boxes)
              if np.all(b >= wlo) and np.all(a <= whi)]
        parts["volumes"] = _h(*vk)
        return _h(*sorted(parts.items())), parts


def rank(a):
    """Each value's rank among the array's distinct values (what an order-only use of row numbers sees)."""
    a = np.asarray(a)
    return np.unique(a, return_inverse=True)[1].reshape(a.shape).astype(np.int64) if len(a) else a.astype(np.int64)


def entry_files(e) -> list[str]:
    """The files a manifest entry names (GLBs, maps, heightmaps, splats), relative to the export dir."""
    out = []

    def walk(x):
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        elif isinstance(x, str) and x.endswith((".glb", ".png", ".npy", ".jpg")):
            out.append(x)
            if x.startswith("heightmaps/height_") and x.endswith(".npy"):  # (its 16-bit PNG beside it, unnamed)
                out.append(x[:-4] + ".png")
    walk(e)
    return sorted(set(out))


def files_ok(out: Path, files: dict) -> bool:
    """Every file there with the size it was written at."""
    for f, size in files.items():
        p = out / f
        try:
            if p.stat().st_size != size:
                return False
        except OSError:
            return False
    return True


def sizes(out: Path, names) -> dict:
    return {f: (out / f).stat().st_size for f in names if (out / f).exists()}


def load(out: Path, code: str, glob_key: str, glob_parts: dict, log=print):
    """The previous export's per-tile state if it can be built on (same code, same global inputs), else None; says
    why not. The file is removed: this export writes a new one when it finishes."""
    p = out / STATE
    if not p.exists():
        return None, "no previous export state"
    try:
        s = pickle.loads(p.read_bytes())
    except Exception as e:
        p.unlink(missing_ok=True)
        return None, f"the previous state is unreadable ({e})"
    p.unlink(missing_ok=True)
    if s.get("format") != FORMAT:
        return None, "the previous state is from another format"
    if s.get("code") != code:
        return None, "the export's code changed since the previous export"
    if s.get("global") != glob_key:
        old = s.get("global_parts", {})
        what = sorted(k for k in set(old) | set(glob_parts) if old.get(k) != glob_parts.get(k))
        return None, f"a global input changed ({', '.join(what) or '?'}): every tile depends on it"
    return s, ""


def save(out: Path, state: dict):
    p = out / STATE
    p.parent.mkdir(exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_bytes(pickle.dumps(state, protocol=pickle.HIGHEST_PROTOCOL))
    os.replace(tmp, p)


def why(prev_parts: dict, parts: dict, n=3) -> str:
    """The inputs whose window changed (for the log: what made a tile dirty)."""
    d = sorted(k for k in set(prev_parts) | set(parts) if prev_parts.get(k) != parts.get(k))
    return ", ".join(d[:n]) + (f" (+{len(d) - n})" if len(d) > n else "")


_FILE_HASH = {}


def file_hash(p: Path) -> str:
    """sha1 of a file's bytes (remembered by path, size and mtime within the process)."""
    st = p.stat()
    k = (str(p), st.st_size, st.st_mtime_ns)
    if k not in _FILE_HASH:
        _FILE_HASH[k] = hashlib.sha1(p.read_bytes()).hexdigest()
    return _FILE_HASH[k]


def files_key(out: Path, names) -> str:
    """What a set of output files hold (their names and bytes): a key for results computed from them."""
    return _h(*[(n, file_hash(out / n)) for n in names])


class Memo:
    """Check results computed from files, kept by their content key in <out>/_incremental/<name>.pkl between exports.
    Always valid (the key is what they were computed from, and the code that computes them), so it isn't tied to the
    export state. Entries this export didn't use are dropped when it's saved."""

    def __init__(self, out: Path, name: str, code: str):
        self.path = out / "_incremental" / f"{name}.pkl"
        self.code = code
        try:
            self.old = pickle.loads(self.path.read_bytes())
        except Exception:
            self.old = {}
        self.new = {}
        self.hits = self.misses = 0

    def get(self, key):
        k = _h(self.code, key)
        v = self.new.get(k, self.old.get(k))
        if v is None:
            self.misses += 1
        else:
            self.hits += 1
            self.new[k] = v
        return v

    def put(self, key, v):
        self.new[_h(self.code, key)] = v

    def save(self):
        self.path.parent.mkdir(exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_bytes(pickle.dumps(self.new, protocol=pickle.HIGHEST_PROTOCOL))
        os.replace(tmp, self.path)
