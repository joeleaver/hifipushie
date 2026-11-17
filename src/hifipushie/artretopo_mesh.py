"""Artist retopo: the sculpt as data (numpy + scipy; no trimesh). PLY in and out, plane sections, rays, nearest points.

`read_ply` / `write_ply`: binary little-endian or ASCII; vertex x y z (+ red green blue [alpha] as uchar), faces as
lists. `Mesh` keeps V (n, 3) float64, F (m, 3) int (polygons fan-triangulated on read), C (n, 4) uint8 or None; vertices
are welded on load (exact duplicates), so a section walks across every triangle edge.

Queries (what the cage tools need, all in the sculpt's own frame):
- `section(origin, normal, u, v)`: closed loops where the plane cuts the surface, in the plane's (u, v), as
  artretopo_poly regions (exterior + holes). Open chains (a cut-open mesh) are dropped: slice the closed sculpt.
- `rays(origin, d)`: every forward hit distance along one ray (Moller-Trumbore over all triangles, ~10 ms per ray at
  350k triangles).
- `closest(points)`: the nearest surface point and its triangle (exact point-triangle test over the triangles round
  the nearest few vertices).
- `signed_volume()`: > 0 when the faces wind outward (check it: a fused mesh once came inside out)."""
from __future__ import annotations

import sys

import numpy as np

from . import artretopo_poly as poly

_PLY_T = {"float": "f4", "float32": "f4", "double": "f8", "float64": "f8", "uchar": "u1", "uint8": "u1",
          "char": "i1", "int8": "i1", "short": "i2", "int16": "i2", "ushort": "u2", "uint16": "u2",
          "int": "i4", "int32": "i4", "uint": "u4", "uint32": "u4"}


def read_ply(path) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
    """(V float64 (n,3), faces as a list of index arrays, colours uint8 (n,4) or None)"""
    data = open(path, "rb").read()
    end = data.index(b"end_header") + len(b"end_header")
    while data[end:end + 1] in (b"\r", b"\n"):
        end += 1
        if data[end - 1:end] == b"\n":
            break
    head = data[:end].decode("ascii", "replace").split("\n")
    fmt = next(l.split()[1] for l in head if l.startswith("format"))
    elems, cur = [], None
    for l in head:
        w = l.split()
        if not w:
            continue
        if w[0] == "element":
            cur = {"name": w[1], "n": int(w[2]), "props": []}; elems.append(cur)
        elif w[0] == "property" and cur is not None:
            cur["props"].append(("list", w[2], w[3], w[4]) if w[1] == "list" else (w[1], w[2]))
    V = C = None; faces = []
    if fmt == "ascii":
        toks = data[end:].split(); k = 0
        for e in elems:
            if e["name"] == "vertex":
                names = [p[1] for p in e["props"]]; w = len(names)
                arr = np.asarray(toks[k:k + w * e["n"]], float).reshape(e["n"], w); k += w * e["n"]
                V = arr[:, [names.index(a) for a in "xyz"]]
                if "red" in names:
                    C = np.full((e["n"], 4), 255, np.uint8)
                    for j, a in enumerate(("red", "green", "blue", "alpha")):
                        if a in names:
                            C[:, j] = arr[:, names.index(a)]
            else:
                for _ in range(e["n"]):
                    if e["props"] and e["props"][0][0] == "list":
                        m = int(toks[k]); faces.append(np.asarray(toks[k + 1:k + 1 + m], int)); k += 1 + m
                    else:
                        k += len(e["props"])
        return V, faces, C
    if fmt != "binary_little_endian":
        raise ValueError(f"{path}: PLY format {fmt} not supported")
    off = end
    for e in elems:
        if e["name"] == "vertex":
            dt = np.dtype([(p[1], "<" + _PLY_T[p[0]]) for p in e["props"]])
            arr = np.frombuffer(data, dt, e["n"], off); off += dt.itemsize * e["n"]
            V = np.stack([arr[a].astype(float) for a in "xyz"], 1)
            if "red" in arr.dtype.names:
                C = np.full((e["n"], 4), 255, np.uint8)
                for j, a in enumerate(("red", "green", "blue", "alpha")):
                    if a in arr.dtype.names:
                        C[:, j] = arr[a]
        elif e["name"] == "face" and e["props"] and e["props"][0][0] == "list":
            _, ct, it, _ = e["props"][0]
            ct, it = np.dtype("<" + _PLY_T[ct]), np.dtype("<" + _PLY_T[it])
            extra = e["props"][1:]
            n0 = int(np.frombuffer(data, ct, 1, off)[0])
            simple = not extra
            if simple:      # every face the same size (a triangle mesh): one strided read
                dt = np.dtype([("n", ct), ("i", it, (n0,))])
                arr = np.frombuffer(data, dt, e["n"], off)
                if (arr["n"] == n0).all():
                    faces = list(arr["i"].astype(np.int64)); off += dt.itemsize * e["n"]; continue
            for _ in range(e["n"]):
                m = int(np.frombuffer(data, ct, 1, off)[0]); off += ct.itemsize
                faces.append(np.frombuffer(data, it, m, off).astype(np.int64)); off += it.itemsize * m
                for p in extra:
                    off += np.dtype(_PLY_T[p[0]]).itemsize
        else:
            dt = np.dtype([(p[1], "<" + _PLY_T[p[0]]) for p in e["props"]]); off += dt.itemsize * e["n"]
    return V, faces, C


def write_ply(path, V, faces, C=None):
    """binary little-endian; faces of any size"""
    V = np.asarray(V, "<f4")
    head = ["ply", "format binary_little_endian 1.0", f"element vertex {len(V)}",
            "property float x", "property float y", "property float z"]
    if C is not None:
        head += ["property uchar red", "property uchar green", "property uchar blue", "property uchar alpha"]
    head += [f"element face {len(faces)}", "property list uchar int vertex_indices", "end_header"]
    with open(path, "wb") as f:
        f.write(("\n".join(head) + "\n").encode())
        if C is None:
            f.write(V.tobytes())
        else:
            dt = np.dtype([("p", "<f4", (3,)), ("c", "u1", (4,))]); arr = np.empty(len(V), dt)
            arr["p"] = V; arr["c"] = np.asarray(C, np.uint8)[:, :4]; f.write(arr.tobytes())
        for q in faces:
            f.write(np.uint8(len(q)).tobytes() + np.asarray(q, "<i4").tobytes())


class Mesh:
    def __init__(self, V, F, C=None, weld=True):
        V = np.asarray(V, float); F = np.asarray(F, np.int64)
        if weld:
            u, inv = np.unique(V, axis=0, return_inverse=True)
            inv = inv.reshape(-1)
            if C is not None:
                C2 = np.zeros((len(u), 4), np.uint8); C2[inv] = C; C = C2
            V, F = u, inv[F]
            F = F[(F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])]
        self.V, self.F, self.C = V, F, C
        self._tri = None; self._kd = None; self._vf = None

    @classmethod
    def load(cls, path):
        V, faces, C = read_ply(path)
        tris = []
        for q in faces:
            for k in range(1, len(q) - 1):
                tris.append((q[0], q[k], q[k + 1]))
        return cls(V, np.asarray(tris, np.int64).reshape(-1, 3), C)

    # ---- geometry
    @property
    def tri(self):
        if self._tri is None:
            self._tri = self.V[self.F]
        return self._tri

    @property
    def face_normals(self):
        t = self.tri; n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        return n / np.maximum(np.linalg.norm(n, axis=1), 1e-30)[:, None]

    def signed_volume(self) -> float:
        t = self.tri
        return float(np.einsum("ij,ij->i", t[:, 0], np.cross(t[:, 1], t[:, 2])).sum() / 6)

    def bounds(self):
        return self.V.min(0), self.V.max(0)

    def edges_open(self) -> int:
        """edges used by one face only (0 = watertight)"""
        e = np.sort(np.concatenate([self.F[:, [0, 1]], self.F[:, [1, 2]], self.F[:, [2, 0]]]), axis=1)
        _, cnt = np.unique(e, axis=0, return_counts=True)
        return int((cnt == 1).sum())

    def components(self) -> np.ndarray:
        """component label per face"""
        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import connected_components
        n = len(self.V); f = self.F
        a = np.concatenate([f[:, 0], f[:, 1]]); b = np.concatenate([f[:, 1], f[:, 2]])
        _, lab = connected_components(coo_matrix((np.ones(len(a)), (a, b)), shape=(n, n)), directed=False)
        return lab[f[:, 0]]

    def submesh(self, keep_faces) -> "Mesh":
        F = self.F[keep_faces]; used = np.unique(F); remap = -np.ones(len(self.V), np.int64)
        remap[used] = np.arange(len(used))
        return Mesh(self.V[used], remap[F], None if self.C is None else self.C[used], weld=False)

    # ---- section
    def section(self, origin, normal, u, v) -> list[poly.Poly]:
        o, n = np.asarray(origin, float), np.asarray(normal, float)
        d = (self.V - o) @ n
        d = np.where(np.abs(d) < 1e-12, 1e-12, d)         # a vertex on the plane counts as above it
        s = d > 0
        F = self.F
        cross = (s[F[:, 0]] != s[F[:, 1]]) | (s[F[:, 1]] != s[F[:, 2]])
        Fc = F[cross]
        if not len(Fc):
            return []
        segs = []
        for (i, j) in ((0, 1), (1, 2), (2, 0)):
            a, b = Fc[:, i], Fc[:, j]
            segs.append(np.where((s[a] != s[b])[:, None], np.stack([np.minimum(a, b), np.maximum(a, b)], 1), -1))
        E = np.stack(segs, 1)                               # (m, 3 edges, 2): -1 where the edge doesn't cross
        ends = [e[e[:, 0] >= 0] for e in E]
        keys = {}
        for k, (e1, e2) in enumerate(ends):
            for e in (e1, e2):
                keys.setdefault((int(e[0]), int(e[1])), []).append(k)
        def point(e):
            a, b = e; t = d[a] / (d[a] - d[b]); return self.V[a] + t * (self.V[b] - self.V[a])
        seen = np.zeros(len(ends), bool); loops = []
        ek = [tuple(tuple(int(x) for x in e) for e in en) for en in ends]
        for k0 in range(len(ends)):
            if seen[k0]:
                continue
            seen[k0] = True
            start, cur = ek[k0]
            chain = [start]; prev = k0; closed = False
            while True:
                nxt = [j for j in keys[cur] if j != prev]
                if not nxt:
                    break                                   # an open chain (a cut mesh): dropped
                j = nxt[0]
                if j == k0:
                    closed = True; break
                if seen[j]:
                    break
                seen[j] = True; chain.append(cur)
                e1, e2 = ek[j]; cur = e2 if e1 == cur else e1; prev = j
            if closed and len(chain) >= 3:
                P = np.array([point(e) for e in chain]) - o
                loops.append(np.stack([P @ np.asarray(u, float), P @ np.asarray(v, float)], 1))
        return poly.polygons(loops)

    # ---- rays
    def rays(self, origin, direction) -> np.ndarray:
        """distances t > 0 of every hit along origin + t * direction (direction normalised here)"""
        o = np.asarray(origin, float); dvec = np.asarray(direction, float); dvec = dvec / np.linalg.norm(dvec)
        if getattr(self, "_edges", None) is None:
            t = self.tri; self._edges = (t[:, 0].copy(), t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        t0, e1, e2 = self._edges
        # only triangles whose bounding sphere the ray's line passes near (cheap prefilter)
        if getattr(self, "_sph", None) is None:
            cen = t0 + (e1 + e2) / 3
            self._sph = (cen, np.sqrt(np.maximum((e1 ** 2).sum(1), (e2 ** 2).sum(1))) + 1e-9)
        cen, rad = self._sph
        w = cen - o; along = w @ dvec
        near = ((w * w).sum(1) - along ** 2 <= rad ** 2) & (along >= -rad)
        t0, e1, e2 = t0[near], e1[near], e2[near]
        p = np.cross(dvec, e2); det = np.einsum("ij,ij->i", e1, p)
        ok = np.abs(det) > 1e-14
        inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        s = o - t0; uu = np.einsum("ij,ij->i", s, p) * inv
        q = np.cross(s, e1); vv = (q @ dvec) * inv; tt = np.einsum("ij,ij->i", e2, q) * inv
        hit = ok & (uu >= 0) & (vv >= 0) & (uu + vv <= 1) & (tt > 1e-9)
        t = np.sort(tt[hit])
        if len(t) > 1:              # a ray through a shared edge or vertex hits each triangle there: count it once
            t = t[np.concatenate([[True], np.diff(t) > 1e-7])]
        return t

    # ---- nearest
    def closest(self, pts, k: int = 12):
        """(points (n,3), triangle index (n,)) nearest on the surface"""
        from scipy.spatial import cKDTree
        if self._kd is None:
            self._kd = cKDTree(self.V)
            order = np.argsort(self.F.reshape(-1), kind="stable")
            self._vf = (order // 3, np.searchsorted(self.F.reshape(-1)[order], np.arange(len(self.V) + 1)))
        pts = np.atleast_2d(np.asarray(pts, float)); out = np.zeros_like(pts); tri = np.zeros(len(pts), np.int64)
        _, nn = self._kd.query(pts, k=min(k, len(self.V)))
        fid, start = self._vf
        for i, p in enumerate(pts):
            cand = np.unique(np.concatenate([fid[start[j]:start[j + 1]] for j in np.atleast_1d(nn[i])]))
            q = _closest_on_tris(p, self.tri[cand]); dd = ((q - p) ** 2).sum(1); b = int(np.argmin(dd))
            out[i], tri[i] = q[b], cand[b]
        return out, tri


def _closest_on_tris(p, T):
    """closest point to p on each triangle of T (m,3,3) (Ericson's region test, vectorised)"""
    a, b, c = T[:, 0], T[:, 1], T[:, 2]
    ab, ac, ap = b - a, c - a, p - a
    d1, d2 = (ab * ap).sum(1), (ac * ap).sum(1)
    bp = p - b; d3, d4 = (ab * bp).sum(1), (ac * bp).sum(1)
    cp = p - c; d5, d6 = (ab * cp).sum(1), (ac * cp).sum(1)
    va = d3 * d6 - d5 * d4; vb = d5 * d2 - d1 * d6; vc = d1 * d4 - d3 * d2
    den = np.where(va + vb + vc == 0, 1e-30, va + vb + vc)
    v = vb / den; w = vc / den
    res = a + ab * v[:, None] + ac * w[:, None]
    with np.errstate(divide="ignore", invalid="ignore"):
        # edges
        m = (vc <= 0) & (d1 >= 0) & (d3 <= 0); t = d1 / (d1 - d3); res[m] = (a + ab * t[:, None])[m]
        m = (vb <= 0) & (d2 >= 0) & (d6 <= 0); t = d2 / (d2 - d6); res[m] = (a + ac * t[:, None])[m]
        m = (va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0); t = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        res[m] = (b + (c - b) * t[:, None])[m]
    # vertices
    m = (d1 <= 0) & (d2 <= 0); res[m] = a[m]
    m = (d3 >= 0) & (d4 <= d3); res[m] = b[m]
    m = (d6 >= 0) & (d5 <= d6); res[m] = c[m]
    return res


if __name__ == "__main__":     # python -m hifipushie.artretopo_mesh mesh.ply: a quick summary
    M = Mesh.load(sys.argv[1]); lo, hi = M.bounds()
    print(len(M.V), "verts", len(M.F), "tris; bounds", lo.round(3), hi.round(3), "volume", round(M.signed_volume(), 5),
          "open edges", M.edges_open())
