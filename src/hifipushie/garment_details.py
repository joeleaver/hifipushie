"""Garment step 7: DETAILS AND TRIMS placed on the FLAT PATTERN, carried by the cloth wherever it goes (tooling run T10).

Why the pattern: a button, a braid or a frog is sewn to the cloth at a place on the PIECE, so it is said in the pattern's
own terms (named points, named edges, mm) and anchored barycentrically on the flat mesh. Its geometry is then re-made on
ANY positions of that mesh (the flat layout, the build, the hung garment): it follows the cloth, never the other way
round. Details never enter the sim (they are carried: re-evaluated from their anchors on the hung mesh). Nothing here
knows a garment: step 1's inventory names the details, the call says where each goes.

Vocabulary (kind):
  point   a small solid at a pattern point: button, tab end, knot. size_mm (diameter), thickness_mm, shape dome|disc|box.
  line    a strip of width_mm along named edges (follows, default: the inventory's follows) inset by `in` mm (default
          half the width: the strip's outer side on the edge), or along a polyline of positions (path): braid, binding,
          cord, zip tape. thickness_mm (default the cloth's).
  motif   a small set of lines / points in a local frame (across = into the piece from the edge, along = the edge),
          repeated at rows along an edge: a frog. lines [[[across, along] mm, ...], ...], points [{at, size_mm, ...}].
Where (pattern terms; mm; pattern x right, y up):
  position  {"point": name, "dx", "dy"} | {"edge": "cf" | "A>B" | "piece:edge", "mm" | "t" (fraction), "in": mm inward}
  rows      {"edge", "count", "from_mm" | "from_t", "pitch_mm" | "pitch_t" (of the edge's length) | "to_mm" | "to_t", "in"}
  points    "button*": the piece's named points matching (marks too)
  an edge: the step-4 declarations' edge name, or "pointA>pointB" / "a>via>b" along the piece's border (shorter way).
A spec may say "mirror": true: placed again on the mirrored piece (.L <-> .R) by the same names.
"""
from __future__ import annotations

import fnmatch
import pickle
import re
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

KINDS = ("point", "line", "motif")
SHAPES = ("dome", "disc", "box")
KEYS = {"kind", "piece", "mirror", "at", "rows", "points", "follows", "path", "in", "lines", "size_mm", "width_mm",
        "thickness_mm", "shape", "colour"}
LIFT = 0.0008  # m: a detail sits this far off the cloth's surface (the closures' lift)
OUT_TOL = 0.003  # m: a position farther than this outside its piece is refused
STEP = 0.004  # m: the longest piece of a strip


class DetailRefused(ValueError):
    """A detail spec can't be placed; the message names the detail and what."""


def mirror_name(p: str) -> str:
    return re.sub(r"\.L$", ".R", p) if p.endswith(".L") else re.sub(r"\.R$", ".L", p) if p.endswith(".R") else p


def load_result(path) -> dict:
    """built.pkl / final.pkl ({X, M, bV, bT, ...}); a worker-pickled build (its class in __main__) loads too."""
    class _U(pickle.Unpickler):
        def find_class(self, m, n):
            return super().find_class("hifipushie.chain_garment" if m == "__main__" else m, n)
    with open(path, "rb") as f:
        return _U(f).load()


# ---------------------------------------------------------------- the flat pattern
class Flat:
    """The flat mesh M (uv, piece, F, names, points, marks) + the declared edges {piece: {edge: "A>B"}}."""

    def __init__(self, M: dict, edges: dict | None = None):
        self.M, self.edges = M, edges or {}
        self.uv = np.asarray(M["uv"], float)
        self.F = np.asarray(M["F"], np.int64)
        self.pc = np.asarray(M["piece"])
        self.names = list(M["names"])
        self.pts = {**(M.get("marks") or {}), **(M.get("points") or {})}
        self._kd, self._loops = {}, {}

    def piece_id(self, p: str) -> int:
        if p not in self.names:
            raise DetailRefused(f"piece {p!r}: not on the pattern ({', '.join(self.names)})")
        return self.names.index(p)

    def faces(self, p: str) -> np.ndarray:
        return np.where(self.pc[self.F[:, 0]] == self.piece_id(p))[0]

    def point(self, p: str, n: str) -> int:
        k = f"{p}:{n}"
        if k not in self.pts:
            have = sorted(x.split(":", 1)[1] for x in self.pts if x.startswith(p + ":"))
            raise DetailRefused(f"point {k!r}: not on the pattern ({p}'s points: {', '.join(have[:40])})")
        return int(self.pts[k])

    def glob(self, p: str, pat: str) -> list:
        ns = sorted((x.split(":", 1)[1] for x in self.pts if x.startswith(p + ":") and fnmatch.fnmatch(x.split(":", 1)[1], pat)),
                    key=lambda s: [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)])
        if not ns:
            raise DetailRefused(f"points {pat!r} on {p}: none match")
        return ns

    # -- locating a uv position in a piece's triangles: (face index, barycentric, distance outside)
    def locate(self, p: str, q) -> tuple:
        q = np.atleast_2d(np.asarray(q, float))
        if p not in self._kd:
            fi = self.faces(p)
            self._kd[p] = (fi, cKDTree(self.uv[self.F[fi]].mean(1)))
        fi, kd = self._kd[p]
        k = min(16, len(fi))
        _, nn = kd.query(q, k=k)
        nn = np.asarray(nn).reshape(len(q), k)
        T = self.uv[self.F[fi[nn]]]  # (n, k, 3, 2)
        a, b, c = T[..., 0, :], T[..., 1, :], T[..., 2, :]
        v0, v1, v2 = b - a, c - a, q[:, None, :] - a
        d00, d01, d11 = (v0 * v0).sum(-1), (v0 * v1).sum(-1), (v1 * v1).sum(-1)
        d20, d21 = (v2 * v0).sum(-1), (v2 * v1).sum(-1)
        den = d00 * d11 - d01 * d01 + 1e-30
        w1, w2 = (d11 * d20 - d01 * d21) / den, (d00 * d21 - d01 * d20) / den
        W = np.stack([1 - w1 - w2, w1, w2], -1)
        best = W.min(-1).argmax(1)
        r = np.arange(len(q))
        Wb = np.clip(W[r, best], 0, None)
        Wb /= Wb.sum(1, keepdims=True)
        tri = fi[nn[r, best]]
        out = np.linalg.norm((Wb[..., None] * T[r, best]).sum(1) - q, axis=1)
        return tri, Wb, out

    def inside(self, p: str, q) -> np.ndarray:
        return self.locate(p, q)[2] < 1e-5

    # -- the border and its named edges
    def loops(self, p: str) -> list:
        if p not in self._loops:
            F = self.F[self.faces(p)]
            E = np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), 1)
            u, c = np.unique(E, axis=0, return_counts=True)
            nb: dict = {}
            for a, b in u[c == 1]:
                nb.setdefault(int(a), []).append(int(b))
                nb.setdefault(int(b), []).append(int(a))
            seen, loops = set(), []
            for s in nb:
                if s in seen:
                    continue
                L, prev, cur = [s], None, s
                seen.add(s)
                while True:
                    nxt = [x for x in nb[cur] if x != prev and (x not in seen or (x == s and len(L) > 2))]
                    if not nxt or nxt[0] == s:
                        break
                    prev, cur = cur, nxt[0]
                    L.append(cur)
                    seen.add(cur)
                loops.append(L)
            self._loops[p] = loops
        return self._loops[p]

    def _on_border(self, p: str, v: int) -> tuple:
        best = None
        for li, L in enumerate(self.loops(p)):
            d = np.linalg.norm(self.uv[L] - self.uv[v], axis=1)
            j = int(d.argmin())
            if best is None or d[j] < best[2]:
                best = (li, j, float(d[j]))
        if best is None or best[2] > 0.001:
            raise DetailRefused(f"a point of {p} ({v}) is not on its border: an edge runs between border points")
        return best

    def _walk(self, p: str, a: int, b: int) -> list:
        la, ia, _ = self._on_border(p, a)
        lb, ib, _ = self._on_border(p, b)
        if la != lb:
            raise DetailRefused(f"{p}: the two ends of an edge are on different borders")
        L = self.loops(p)[la]
        n = len(L)
        fw = [L[(ia + k) % n] for k in range((ib - ia) % n + 1)]
        bw = [L[(ia - k) % n] for k in range((ia - ib) % n + 1)]
        ln = lambda s: float(np.linalg.norm(np.diff(self.uv[s], axis=0), axis=1).sum())
        return fw if ln(fw) <= ln(bw) else bw

    def edge(self, p: str, e: str) -> np.ndarray:
        """uv polyline of a named edge: "piece:edge" | "edge" (declared) | "A>B" | "a>via>b"."""
        if ":" in e:
            q, e = e.split(":", 1)
            if q != p:
                p = q
        how = (self.edges.get(p) or {}).get(e, e if ">" in e else None)
        if not isinstance(how, str):
            raise DetailRefused(f"edge {p}:{e}: not a declared edge of {p} ({', '.join(self.edges.get(p) or {}) or 'none declared'})"
                                f" nor 'pointA>pointB' along its border")
        ns = how.split(">")
        vs = [self.point(p, n) for n in ns]
        path = []
        for a, b in zip(vs, vs[1:]):
            s = self._walk(p, a, b)
            path += s if not path else s[1:]
        return self.uv[path]

    def piece_of_edge(self, p: str | None, e: str) -> str:
        return e.split(":", 1)[0] if ":" in e else p


# ---------------------------------------------------------------- polylines in uv
def arclen(P) -> np.ndarray:
    return np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])


def at_len(P, s) -> tuple:
    """Point and unit tangent at arc length(s) s along P."""
    S = arclen(P)
    s = np.clip(np.atleast_1d(np.asarray(s, float)), 0, S[-1])
    i = np.clip(np.searchsorted(S, s, side="right") - 1, 0, len(P) - 2)
    seg = P[i + 1] - P[i]
    L = np.linalg.norm(seg, axis=1) + 1e-30
    return P[i] + seg * ((s - S[i]) / L)[:, None], seg / L[:, None]


def normal_in(fl: Flat, p: str, P, T) -> np.ndarray:
    """The unit normals (in uv) pointing into piece p at points P with tangents T (one sign for the whole line)."""
    N = np.stack([-T[:, 1], T[:, 0]], 1)
    ok = fl.inside(p, P + 0.002 * N).sum()
    bad = fl.inside(p, P - 0.002 * N).sum()
    return N if ok >= bad else -N


def resample(P, step=STEP) -> np.ndarray:
    S = arclen(P)
    n = max(2, int(np.ceil(S[-1] / step)) + 1)
    return at_len(P, np.linspace(0, S[-1], n))[0]


def offset(fl: Flat, p: str, P, d: float) -> np.ndarray:
    """P moved d (m) into the piece along its per-vertex normals."""
    if abs(d) < 1e-9:
        return P
    T = np.gradient(P, axis=0)
    T /= np.linalg.norm(T, axis=1, keepdims=True) + 1e-30
    return P + d * normal_in(fl, p, P, T)


# ---------------------------------------------------------------- positions in pattern terms
def _mm(x, what: str) -> float:
    if not isinstance(x, (int, float)) or isinstance(x, bool):
        raise DetailRefused(f"{what}: a number (mm)")
    return float(x) / 1000.0


def position(fl: Flat, p: str, pos: dict) -> tuple:
    """(uv, text) of one position: {"point", "dx", "dy"} | {"edge", "mm" | "t", "in"}."""
    if not isinstance(pos, dict) or not ({"point", "edge"} & set(pos)):
        raise DetailRefused(f"position {pos!r}: {{\"point\": name, \"dx\", \"dy\"}} or {{\"edge\", \"mm\" | \"t\", \"in\"}} (mm)")
    if "point" in pos:
        dx, dy = _mm(pos.get("dx", 0), "dx"), _mm(pos.get("dy", 0), "dy")
        uv = fl.uv[fl.point(p, pos["point"])] + [dx, dy]
        return uv, f"{p}:{pos['point']}" + (f" {dx * 1000:+.0f},{dy * 1000:+.0f} mm" if dx or dy else "")
    P = fl.edge(p, pos["edge"])
    S = arclen(P)[-1]
    s = _mm(pos["mm"], "mm") if "mm" in pos else float(pos.get("t", 0)) * S
    if s > S + 1e-6:
        raise DetailRefused(f"{p}:{pos['edge']} at {s * 1000:.0f} mm: past the edge's end ({S * 1000:.0f} mm)")
    q, T = at_len(P, s)
    N = normal_in(fl, p, q, T)
    d = _mm(pos.get("in", 0), "in")
    return q[0] + d * N[0], f"{p}:{pos['edge']} {s * 1000:.0f} mm" + (f", in {d * 1000:.0f}" if d else "")


def rows(fl: Flat, p: str, r: dict) -> tuple:
    """[(uv, along, across)] of count rows along an edge + the text."""
    if not isinstance(r, dict) or "edge" not in r or not isinstance(r.get("count"), int) or r["count"] < 1:
        raise DetailRefused(f"rows {r!r}: {{\"edge\", \"count\", \"from_mm\" | \"from_t\", \"pitch_mm\" | \"pitch_t\" | \"to_mm\" | \"to_t\", \"in\"}}")
    P = fl.edge(p, r["edge"])
    S = arclen(P)[-1]
    a = _mm(r["from_mm"], "from_mm") if "from_mm" in r else float(r.get("from_t", 0)) * S
    n = r["count"]
    if "pitch_mm" in r or "pitch_t" in r:
        pitch = _mm(r["pitch_mm"], "pitch_mm") if "pitch_mm" in r else float(r["pitch_t"]) * S
    elif "to_mm" in r or "to_t" in r:
        b = _mm(r["to_mm"], "to_mm") if "to_mm" in r else float(r["to_t"]) * S
        pitch = (b - a) / max(n - 1, 1)
    else:
        raise DetailRefused(f"rows on {p}:{r['edge']}: a pitch (pitch_mm | pitch_t of the edge) or an end (to_mm | to_t)")
    s = a + pitch * np.arange(n)
    if s.max() > S + 1e-6 or s.min() < -1e-6:
        raise DetailRefused(f"rows on {p}:{r['edge']}: row {int(s.argmax()) + 1} at {s.max() * 1000:.0f} mm is past the "
                            f"edge's end ({S * 1000:.0f} mm long)")
    q, T = at_len(P, s)
    N = normal_in(fl, p, q, T)
    d = _mm(r.get("in", 0), "in")
    txt = (f"{p}:{r['edge']} ({S * 1000:.0f} mm): {n} rows from {a * 1000:.0f} mm, pitch {pitch * 1000:.1f} mm "
           f"({pitch / S:.3f} of the edge)" + (f", in {d * 1000:.0f} mm" if d else ""))
    return [(q[i] + d * N[i], T[i], N[i]) for i in range(n)], txt


# ---------------------------------------------------------------- placing one detail (pattern only)
def _pt(fl, p, uv, size, thick, shape, where) -> dict:
    tri, W, out = fl.locate(p, [uv, uv + [0.001, 0], uv + [0, 0.001]])
    if out[0] > OUT_TOL:
        raise DetailRefused(f"{where}: lands {out[0] * 1000:.0f} mm outside {p}")
    return {"kind": "point", "piece": p, "uv": np.asarray(uv, float), "tri": tri, "W": W, "size": size,
            "thick": thick, "shape": shape, "where": where}


def _strip(fl, p, C, width, thick, where) -> dict:
    C = resample(np.asarray(C, float))
    T = np.gradient(C, axis=0)
    T /= np.linalg.norm(T, axis=1, keepdims=True) + 1e-30
    N = np.stack([-T[:, 1], T[:, 0]], 1)
    _, _, out = fl.locate(p, C)
    if out.max() > OUT_TOL:
        raise DetailRefused(f"{where}: runs {out.max() * 1000:.0f} mm outside {p}")
    ta, Wa, _ = fl.locate(p, C + 0.5 * width * N)
    tb, Wb, _ = fl.locate(p, C - 0.5 * width * N)
    return {"kind": "strip", "piece": p, "C": C, "tri": (ta, tb), "W": (Wa, Wb), "width": width, "thick": thick,
            "where": where, "length": float(arclen(C)[-1])}


def _remap(x, p: str, q: str):
    if isinstance(x, str):
        return q + x[len(p):] if x.startswith(p + ":") else x
    if isinstance(x, list):
        return [_remap(v, p, q) for v in x]
    if isinstance(x, dict):
        return {k: _remap(v, p, q) for k, v in x.items()}
    return x


def _piece(s: dict, inv: dict, name: str) -> str:
    if s.get("piece"):
        return s["piece"]
    for k in ("follows", "rows", "at", "path"):
        v = s.get(k)
        v = v[0] if isinstance(v, list) and v else v
        e = v.get("edge") if isinstance(v, dict) else v
        if isinstance(e, str) and ":" in e:
            return e.split(":", 1)[0]
    on = inv.get("on") or []
    if len(on) == 1:
        return on[0]
    raise DetailRefused(f"{name}: say its piece (\"piece\": one of {', '.join(on)}) or name edges as 'piece:edge'")


def place(fl: Flat, name: str, spec, inv: dict, cloth: dict | None = None) -> dict:
    """One detail (spec or [specs]) -> {"instances", "count", "where" [texts], "pieces"}; refused by name."""
    specs = spec if isinstance(spec, list) else [spec]
    cloth = cloth or {}
    insts, where, count = [], [], 0
    for s in specs:
        if not isinstance(s, dict):
            raise DetailRefused(f"{name}: each spec is a dict")
        bad = set(s) - KEYS
        if bad:
            raise DetailRefused(f"{name}: unknown keys {sorted(bad)}; keys: {', '.join(sorted(KEYS))}")
        kind = s.get("kind")
        if kind not in KINDS:
            raise DetailRefused(f"{name}.kind {kind!r}: one of {', '.join(KINDS)}")
        p0 = _piece(s, inv, name)
        passes = [(p0, s)] + ([(mirror_name(p0), _remap(s, p0, mirror_name(p0)))] if s.get("mirror") else [])
        for p, t in passes:
            if inv.get("on") and p not in inv["on"]:
                raise DetailRefused(f"{name} on {p}: the inventory puts it on {', '.join(inv['on'])}")
            fl.piece_id(p)
            try:
                c, w, i = _place_one(fl, name, kind, p, t, inv, cloth)
            except DetailRefused as e:
                raise DetailRefused(f"{name}: {e}") from None
            insts += i
            where += w
            count += c
    return {"instances": insts, "count": count, "where": where, "pieces": sorted({i["piece"] for i in insts})}


def _place_one(fl, name, kind, p, s, inv, cloth) -> tuple:
    cth = cloth.get("thickness_mm")
    if kind == "point":
        size = _mm(s.get("size_mm"), "size_mm")
        thick = _mm(s.get("thickness_mm", size * 300), "thickness_mm")
        shape = s.get("shape", "dome")
        if shape not in SHAPES:
            raise DetailRefused(f"shape {shape!r}: one of {', '.join(SHAPES)}")
        pos = []
        for q in s.get("at") or []:
            pos.append(position(fl, p, q))
        if s.get("rows"):
            R, txt = rows(fl, p, s["rows"])
            pos += [(uv, f"row {k + 1}") for k, (uv, _, _) in enumerate(R)]
            where = [txt]
        else:
            where = []
        for g in ([s["points"]] if isinstance(s.get("points"), str) else s.get("points") or []):
            pos += [position(fl, p, {"point": n}) for n in fl.glob(p, g)]
        if not pos:
            raise DetailRefused("a point detail needs at, rows or points")
        where += [t for _, t in pos if not t.startswith("row ")]
        return len(pos), [f"{p}: " + "; ".join(where)], [_pt(fl, p, uv, size, thick, shape, t) for uv, t in pos]
    width = _mm(s.get("width_mm"), "width_mm")
    thick = _mm(s.get("thickness_mm", cth if cth else 1.0), "thickness_mm")
    if kind == "line":
        fol = s.get("follows", inv.get("follows") or [])
        if s.get("path"):
            pts = [position(fl, p, q) for q in s["path"]]
            C = np.array([uv for uv, _ in pts])
            return 1, [f"{p}: path " + " -> ".join(t for _, t in pts)], [_strip(fl, p, C, width, thick, f"{name} path on {p}")]
        fol = [e for e in fol if fl.piece_of_edge(p, e) == p]
        if not fol:
            raise DetailRefused(f"a line on {p} needs follows ['{p}:edge'] or a path")
        d = _mm(s["in"], "in") if "in" in s else 0.5 * width
        out, txt = [], []
        for e in fol:
            C = offset(fl, p, resample(fl.edge(p, e)), d)
            out.append(_strip(fl, p, C, width, thick, f"{name} along {e}"))
            txt.append(f"{e if ':' in e else p + ':' + e} ({out[-1]['length'] * 1000:.0f} mm, in {d * 1000:.1f})")
        return 1, [f"{p}: along " + ", ".join(txt)], out
    R, txt = rows(fl, p, s.get("rows") or {})
    out = []
    for k, (o, T, N) in enumerate(R):
        for li, L in enumerate(s.get("lines") or []):
            L = np.asarray(L, float) / 1000.0
            if L.ndim != 2 or L.shape[1] != 2 or len(L) < 2:
                raise DetailRefused(f"motif line {li}: [[across, along] mm, ...] (2 or more)")
            out.append(_strip(fl, p, o + L[:, :1] * N + L[:, 1:] * T, width, thick, f"{name} row {k + 1} line {li + 1}"))
        for q in s.get("points") or []:
            a = np.asarray(q.get("at", [0, 0]), float) / 1000.0
            sz = _mm(q.get("size_mm"), "points.size_mm")
            out.append(_pt(fl, p, o + a[0] * N + a[1] * T, sz, _mm(q.get("thickness_mm", sz * 300), "points.thickness_mm"),
                           q.get("shape", "dome"), f"{name} row {k + 1} point"))
    if not out:
        raise DetailRefused("a motif needs lines (with width_mm) or points")
    return len(R), [f"{p}: motif of {len(s.get('lines') or [])} lines + {len(s.get('points') or [])} points at {txt}"], out


# ---------------------------------------------------------------- carried: the geometry on any positions of the mesh
def vnormals(X, M, bV=None, bT=None) -> np.ndarray:
    """Vertex normals facing OUT (away from the body; +z on the flat layout), piece by piece."""
    X = np.asarray(X, float)
    F = np.asarray(M["F"], np.int64).copy()
    pc = np.asarray(M["piece"])
    if bV is not None:
        from .chain_garment import cn_vnormals
        bN = cn_vnormals(np.asarray(bV, float), np.asarray(bT, np.int64))
        kd = cKDTree(bV)
    for p in np.unique(pc):
        fi = np.where(pc[F[:, 0]] == p)[0]
        n = np.cross(X[F[fi, 1]] - X[F[fi, 0]], X[F[fi, 2]] - X[F[fi, 0]])
        ref = bN[kd.query(X[F[fi]].mean(1))[1]] if bV is not None else np.array([0, 0, 1.0])
        if (n * ref).sum() < 0:
            F[fi] = F[fi][:, [0, 2, 1]]
    fn = np.cross(X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]])
    N = np.zeros_like(X)
    for k in range(3):
        np.add.at(N, F[:, k], fn)
    return N / (np.linalg.norm(N, axis=1, keepdims=True) + 1e-30)


def _ev(X, N, F, tri, W):
    P = (W[..., None] * X[F[tri]]).sum(1)
    n = (W[..., None] * N[F[tri]]).sum(1)
    return P, n / (np.linalg.norm(n, axis=1, keepdims=True) + 1e-30)


def _strip_mesh(A, B, nA, nB, t) -> tuple:
    V = np.stack([A + LIFT * nA, B + LIFT * nB, B + (LIFT + t) * nB, A + (LIFT + t) * nA], 1)  # (n, 4, 3)
    n = len(V)
    F = []
    for i in range(n - 1):
        for k in range(4):
            a, b = 4 * i + k, 4 * i + (k + 1) % 4
            F += [[a, b, b + 4], [a, b + 4, a + 4]]
    F += [[0, 2, 1], [0, 3, 2], [4 * (n - 1), 4 * (n - 1) + 1, 4 * (n - 1) + 2], [4 * (n - 1), 4 * (n - 1) + 2, 4 * (n - 1) + 3]]
    return V.reshape(-1, 3), np.asarray(F, np.int64)


def _point_mesh(c, n, xd, size, t, shape, k=16) -> tuple:
    x = xd - (xd @ n) * n
    x /= np.linalg.norm(x) + 1e-30
    y = np.cross(n, x)
    r = 0.5 * size
    if shape == "box":
        prof, k, rot = [(r * 1.414, 0.0), (r * 1.414, t)], 4, np.pi / 4
    elif shape == "disc":
        prof, rot = [(r, 0.0), (r, t)], 0.0
    else:
        prof, rot = [(r * np.cos(a), t * np.sin(a)) for a in np.linspace(0, np.pi / 2 * 0.92, 5)], 0.0
    ang = rot + np.linspace(0, 2 * np.pi, k, endpoint=False)
    ring = np.cos(ang)[:, None] * x + np.sin(ang)[:, None] * y
    V = [c + (LIFT + h) * n + rr * ring for rr, h in prof]
    V = np.concatenate(V + [[c + LIFT * n], [c + (LIFT + prof[-1][1]) * n]])
    m = len(prof)
    F = []
    for j in range(m - 1):
        for i in range(k):
            a, b = j * k + i, j * k + (i + 1) % k
            F += [[a, b, b + k], [a, b + k, a + k]]
    lo, hi = m * k, m * k + 1
    F += [[lo, (i + 1) % k, i] for i in range(k)] + [[hi, (m - 1) * k + i, (m - 1) * k + (i + 1) % k] for i in range(k)]
    return V, np.asarray(F, np.int64)


def carry(insts: list, X, M, N=None) -> tuple:
    """The detail's mesh (V, F) on positions X of the pattern mesh (built, hung or flat): from the anchors alone."""
    X = np.asarray(X, float)
    F = np.asarray(M["F"], np.int64)
    N = vnormals(X, M) if N is None else N
    Vs, Fs, o = [], [], 0
    for it in insts:
        if it["kind"] == "point":
            P, n = _ev(X, N, F, it["tri"], it["W"])
            V, f = _point_mesh(P[0], n[0], P[1] - P[0], it["size"], it["thick"], it["shape"])
        else:
            (A, nA), (B, nB) = (_ev(X, N, F, it["tri"][j], it["W"][j]) for j in (0, 1))
            V, f = _strip_mesh(A, B, nA, nB, it["thick"])
        Vs.append(V)
        Fs.append(f + o)
        o += len(V)
    return np.concatenate(Vs), np.concatenate(Fs)


def flat_positions(M) -> np.ndarray:
    """The flat layout as positions (uv, 0): details placed here are the pattern's own look."""
    uv = np.asarray(M["uv"], float)
    return np.c_[uv, np.zeros(len(uv))]
